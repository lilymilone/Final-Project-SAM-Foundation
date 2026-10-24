"""Agent 7: Event Intelligence & Learning.

Reads the real event and reflection records and compares outcomes with
deterministic metrics. Then asks the model for lessons that each cite the
event and reflection IDs behind them. Lessons whose evidence does not exist
are dropped (not trusted), disagreements are kept visible, and the surviving
lessons go to the Events agent as planning constraints.
"""

from __future__ import annotations

from ..base import BaseAgent
from ..contracts import AgentName, AgentResult, AgentTask, Constraint, Finding
from ..outputs import LessonsOutput
from ..registry import LESSONS
from ..runtime import RunContext, dedupe_sources

INSTRUCTIONS = """Analyze the foundation's past events and the board's reflections.
Return:
- lessons: what worked, recurring problems, and recommendations for the event in "focus". EVERY lesson must cite
  evidence_event_ids and/or evidence_reflection_ids taken from the data. Do not cite IDs that are not in the data.
- disagreements: where reflections conflict (different ratings, opposite views). Show both sides; never hide a disagreement.
- planning_constraints: concrete rules the Events agent must follow (e.g. "lock the guest count two weeks out").
- recommended_contingency_pct: a fraction (0.15 = 15%) if reflections report cost overruns, citing those reflections; else null.
- uncertainties: what the records cannot tell us (small sample, demo data, missing costs)."""


class EventIntelligenceAgent(BaseAgent):
    name = AgentName.EVENT_INTELLIGENCE

    def execute(self, task: AgentTask, ctx: RunContext) -> AgentResult:
        events = self.tool(ctx, "read_historical_events")
        reflections = self.tool(ctx, "read_board_reflections")
        if not events.data:
            return self.result(task, "completed", "No past events are recorded yet, so there are no lessons to share.",
                               next_steps=["Record past events and reflections in Our Legacy."])
        comparison = self.tool(ctx, "compare_event_outcomes", events=events.data)
        out = self.think(ctx, LESSONS, INSTRUCTIONS, {
            "focus": task.inputs.get("focus") or "future fundraising events",
            "events": events.data, "comparison": comparison.data, "reflections": reflections.data,
        }, LessonsOutput)

        # Verification: keep only evidence that exists.
        event_ids = {e["id"] for e in events.data}
        refl_ids = {r["id"] for r in reflections.data}
        demo = any(e["is_demo"] for e in events.data)
        warnings, kept = [], []
        for lesson in out.lessons:
            ev = [i for i in lesson.evidence_event_ids if i in event_ids]
            rf = [i for i in lesson.evidence_reflection_ids if i in refl_ids]
            dropped = (len(lesson.evidence_event_ids) - len(ev)) + (len(lesson.evidence_reflection_ids) - len(rf))
            if dropped:
                warnings.append(f"Removed {dropped} citation(s) to records that do not exist from: “{lesson.text[:60]}…”")
            if not ev and not rf:
                warnings.append(f"Dropped a lesson with no valid evidence: “{lesson.text[:60]}…”")
                continue
            kept.append({"kind": lesson.kind, "text": lesson.text, "event_ids": ev, "reflection_ids": rf, "confidence": lesson.confidence})

        contingency = out.recommended_contingency_pct
        cont_refs = [i for i in out.contingency_evidence_reflection_ids if i in refl_ids]
        if contingency is not None and not cont_refs:
            warnings.append("Ignored the suggested contingency because it cited no valid reflection.")
            contingency = None

        for lesson in kept:
            evidence = [{"type": "event", "id": i} for i in lesson["event_ids"]] + [{"type": "reflection", "id": i} for i in lesson["reflection_ids"]]
            self.tool(ctx, "save_historical_lesson", lesson=lesson["text"], kind=lesson["kind"], confidence=lesson["confidence"],
                      applies_to=str(task.inputs.get("focus") or "")[:120], evidence=evidence, based_on_demo_data=demo)

        constraints = [Constraint(name=c.name, detail=c.detail, source_agent=AgentName.EVENT_INTELLIGENCE)
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
        return self.result(
            task, "completed", out.summary, findings=findings, sources=sources, assumptions=assumptions,
            warnings=warnings + out.uncertainties,
            next_steps=["Share these lessons with the Events agent."],
            data={"lessons": kept, "disagreements": [d.model_dump() for d in out.disagreements],
                  "constraints": [c.model_dump(mode="json") for c in constraints], "recommended_contingency_pct": contingency,
                  "comparison": comparison.data},
        )
