"""Agent 7: Event Intelligence & Learning.

Reads the authorized event and reflection records. Compares outcomes with
deterministic metrics, but only when at least two events have both funds
raised and expenses. Asks the model for recurring themes, strengths,
weaknesses, disagreements, and recommendations, each citing the event and
reflection IDs behind it.

Code then checks every citation. Lessons citing records that do not exist are
dropped. The rest are stored with their evidence, theme, and scope, and a
newer analysis of the same scope supersedes unreviewed older lessons.
Reflections are only read, never modified. In planning mode the surviving
lessons go to the Events agent as advisory constraints.
"""

from __future__ import annotations

from ..base import BaseAgent
from ..contracts import AgentName, AgentResult, AgentTask, Constraint, Finding
from ..outputs import LessonsOutput
from ..registry import LESSONS
from ..runtime import RunContext, dedupe_sources

INSTRUCTIONS = """Analyze the foundation's past events and the board's structured reflections (7 questions each).
Return:
- themes: recurring themes across events and reflections (e.g. "food and catering costs", "pledge collection"), each marked
  strength, weakness, or mixed, citing evidence_event_ids and evidence_reflection_ids.
- lessons: what worked (strengths), recurring problems (weaknesses), and recommendations for "focus". Give each a short theme.
  EVERY lesson must cite event and/or reflection IDs from the data. Never cite IDs that are not in the data.
- disagreements: where board members disagree. Show every side in its own words; never resolve or hide a disagreement.
- planning_constraints: concrete, evidence-backed rules for planning the next event (e.g. "compare venue catering
  minimums before choosing a venue").
- recommended_contingency_pct: a fraction (0.15 = 15%) only if reflections report cost overruns, citing them; else null.
- numeric_comparison_note: interpret the computed comparison ONLY if comparison.sufficient is true; else null.
  Never compute numbers yourself.
- uncertainties: what the records cannot tell us (small sample, demo data, missing figures).
Reflections are the board's original words: quote or paraphrase faithfully, never invent feedback."""


class EventIntelligenceAgent(BaseAgent):
    name = AgentName.EVENT_INTELLIGENCE

    def execute(self, task: AgentTask, ctx: RunContext) -> AgentResult:
        events = self.tool(ctx, "read_historical_events")
        reflections = self.tool(ctx, "read_board_reflections")
        if not events.data:
            return self.result(task, "completed", "No past events are recorded yet, so there are no lessons to share.",
                               next_steps=["Record past events and reflections in Our Legacy."])
        focus_event_id = task.inputs.get("focus_event_id")
        focus = task.inputs.get("focus") or "future fundraising events"
        mode = task.inputs.get("mode", "planning")
        comparison = self.tool(ctx, "compare_event_outcomes", events=events.data).data
        prior = self.tool(ctx, "get_historical_lessons", statuses=["adopted", "reviewed"]).data or []
        payload = {
            "focus": focus, "mode": mode, "focus_event_id": focus_event_id, "events": events.data,
            "comparison": comparison, "reflections": reflections.data,
            "lessons_the_board_already_adopted_or_reviewed": prior,
        }
        out = self.think(ctx, LESSONS, INSTRUCTIONS, payload, LessonsOutput)

        event_ids = {e["id"] for e in events.data}
        refl_ids = {r["id"] for r in reflections.data}
        demo = any(e["is_demo"] for e in events.data)
        warnings: list[str] = []

        def valid(ev: list[int], rf: list[int], label: str) -> tuple[list[int], list[int]]:
            good_ev, good_rf = [i for i in ev if i in event_ids], [i for i in rf if i in refl_ids]
            dropped = len(ev) + len(rf) - len(good_ev) - len(good_rf)
            if dropped:
                warnings.append(f"Removed {dropped} citation(s) to records that do not exist from: “{label[:60]}…”")
            return good_ev, good_rf

        kept = []
        for lesson in out.lessons:
            ev, rf = valid(lesson.evidence_event_ids, lesson.evidence_reflection_ids, lesson.text)
            if not ev and not rf:
                warnings.append(f"Dropped a lesson with no valid evidence: “{lesson.text[:60]}…”")
                continue
            kept.append({"kind": lesson.kind, "theme": lesson.theme, "text": lesson.text, "event_ids": ev, "reflection_ids": rf,
                         "confidence": lesson.confidence})
        themes = []
        for t in out.themes:
            ev, rf = valid(t.evidence_event_ids, t.evidence_reflection_ids, t.name)
            if ev or rf:
                themes.append({"name": t.name, "polarity": t.polarity, "description": t.description, "event_ids": ev, "reflection_ids": rf})
        disagreements = [{**d.model_dump(), "evidence_reflection_ids": [i for i in d.evidence_reflection_ids if i in refl_ids]}
                         for d in out.disagreements]

        contingency = out.recommended_contingency_pct
        if contingency is not None and not [i for i in out.contingency_evidence_reflection_ids if i in refl_ids]:
            warnings.append("Ignored the suggested contingency because it cited no valid reflection.")
            contingency = None

        scope = f"event:{focus_event_id}" if focus_event_id else f"{mode}:{focus}"
        for lesson in kept:
            evidence = [{"type": "event", "id": i} for i in lesson["event_ids"]] + [{"type": "reflection", "id": i} for i in lesson["reflection_ids"]]
            saved = self.tool(ctx, "save_historical_lesson", lesson=lesson["text"], kind=lesson["kind"], theme=lesson["theme"],
                              confidence=lesson["confidence"], applies_to=str(focus)[:120], evidence=evidence,
                              based_on_demo_data=demo, scope=scope, focus_event_id=focus_event_id)
            lesson["id"] = saved.data["id"] if saved.ok else None

        # History constraints live in their own namespace, so they can never pose as Finance's limits.
        constraints = [Constraint(name=f"history:{c.name}", detail=c.detail, source_agent=AgentName.EVENT_INTELLIGENCE)
                       for c in out.planning_constraints if not c.evidence_reflection_ids or set(c.evidence_reflection_ids) & refl_ids]
        if contingency is not None:
            constraints.append(Constraint(name="min_contingency_pct", value=contingency, source_agent=AgentName.EVENT_INTELLIGENCE,
                                          detail=f"Past reflections report overruns; plan at least {contingency:.0%} contingency."))
        findings = [Finding(claim=l["text"], kind="recommendation" if l["kind"] == "recommendation" else "opinion",
                            source_ids=[f"event:{i}" for i in l["event_ids"]] + [f"reflection:{i}" for i in l["reflection_ids"]],
                            confidence=l["confidence"]) for l in kept]
        cited = {s for f in findings for s in f.source_ids}
        sources = [s for s in dedupe_sources(events.sources + reflections.sources) if s.id in cited]
        assumptions = ["Lessons are based on synthetic demo records."] if demo else []
        if not comparison["sufficient"]:
            assumptions.append(comparison["note"])
        return self.result(
            task, "completed", out.summary, findings=findings, sources=sources, assumptions=assumptions,
            warnings=warnings + out.uncertainties,
            next_steps=["Review the lessons in Our Legacy: mark them reviewed, adopted, or dismissed."] +
                       (["Share these lessons with the Events agent."] if mode == "planning" else []),
            data={"lessons": kept, "themes": themes, "disagreements": disagreements,
                  "strengths": [l for l in kept if l["kind"] == "what_worked"],
                  "weaknesses": [l for l in kept if l["kind"] == "recurring_problem"],
                  "recommendations": [l for l in kept if l["kind"] == "recommendation"],
                  "constraints": [c.model_dump(mode="json") for c in constraints], "recommended_contingency_pct": contingency,
                  "comparison": comparison, "numeric_comparison_note": out.numeric_comparison_note if comparison["sufficient"] else None,
                  "focus_event_id": focus_event_id, "scope": scope},
        )
