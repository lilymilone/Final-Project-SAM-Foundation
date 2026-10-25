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

from ...mission import REFLECTION_LENSES
from ..base import BaseAgent
from ..contracts import AgentName, AgentResult, AgentTask, Constraint, Finding
from ..outputs import LessonsOutput
from ..registry import LESSONS
from ..runtime import RunContext, dedupe_sources

INSTRUCTIONS_TEMPLATE = """Analyze the foundation's past events and the board's structured reflections (7 questions each).
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
- community_insights: through the lenses below, what the records say about the community experience. Each needs a
  "quote" copied WORD FOR WORD from one cited reflection (or an event's community_outcomes), an observation (your short
  reading of it), and evidence_type: board_observation (a board member's impression), attendee_feedback_reported (what
  the board says attendees told them), or verified_outcome (only a recorded event outcome, e.g. community_outcomes).
  Opinions are never outcomes. If the records say nothing about a lens, skip it; never infer how people felt.
  Lenses: {lenses}
Reflections are the board's original words: quote or paraphrase faithfully, never invent feedback."""


INSTRUCTIONS = INSTRUCTIONS_TEMPLATE.replace("{lenses}", " ".join(REFLECTION_LENSES))
LENS_LABELS = {"welcomed": "Welcome and inclusion", "connection": "Connection", "volunteers": "Volunteer appreciation",
               "community": "Sense of community", "accessibility": "Accessibility and inclusion", "improvement": "Improvements"}
EVIDENCE_LABELS = {"board_observation": "Board observation (not a verified outcome)",
                   "attendee_feedback_reported": "Attendee feedback, as reported by the board",
                   "verified_outcome": "Recorded outcome"}
REFLECTION_TEXT_FIELDS = ("what_worked", "did_not_go_as_planned", "unexpected_costs_or_complications", "attendee_feedback", "repeat",
                          "change", "advice_for_next_board", "welcome_inclusion", "connection_moments", "volunteer_appreciation",
                          "accessibility_issues")


def _norm(text: str) -> str:
    return " ".join(str(text or "").lower().replace("’", "'").replace("“", '"').replace("”", '"').split())


def check_community_insights(insights: list, reflections: list[dict], events: list[dict], warnings: list[str]) -> list[dict]:
    """Keep only insights whose quote really appears in a cited record (no fabricated sentiment).
    'verified_outcome' stands only when the quote is from an event's recorded community outcomes."""
    refl = {r["id"]: _norm(" ".join(str(r.get(k) or "") for k in REFLECTION_TEXT_FIELDS)) for r in reflections}
    outcomes = {e["id"]: _norm(e.get("community_outcomes") or "") for e in events}
    names_by_event = {e["id"]: e["name"] for e in events}
    names_by_reflection = {r["id"]: r.get("event_name") or names_by_event.get(r.get("event_id"), "a past event") for r in reflections}
    kept = []
    for c in insights or []:
        quote = _norm(c.quote).strip('"')
        r_ids = [i for i in c.evidence_reflection_ids if i in refl and quote and quote in refl[i]]
        e_ids = [i for i in c.evidence_event_ids if i in outcomes and quote and quote in outcomes[i]]
        if not quote or not (r_ids or e_ids):
            warnings.append(f"Dropped a community insight whose quote is not in the cited records: “{c.observation[:60]}…”")
            continue
        evidence_type = c.evidence_type
        if evidence_type == "verified_outcome" and not e_ids:
            evidence_type = "board_observation"  # an opinion is never promoted to an outcome
        names = sorted({names_by_reflection[i] for i in r_ids} | {names_by_event[i] for i in e_ids})
        kept.append({"lens": c.lens, "lens_label": LENS_LABELS[c.lens], "observation": c.observation, "quote": c.quote.strip(),
                     "reflection_ids": r_ids, "event_ids": e_ids, "event_names": names, "evidence_type": evidence_type,
                     "evidence_label": EVIDENCE_LABELS[evidence_type]})
    return kept


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

        community = check_community_insights(out.community_insights or [], reflections.data, events.data, warnings)

        scope = f"event:{focus_event_id}" if focus_event_id else f"{mode}:{focus}"
        for lesson in kept:
            evidence = [{"type": "event", "id": i} for i in lesson["event_ids"]] + [{"type": "reflection", "id": i} for i in lesson["reflection_ids"]]
            saved = self.tool(ctx, "save_historical_lesson", lesson=lesson["text"], kind=lesson["kind"], theme=lesson["theme"],
                              confidence=lesson["confidence"], applies_to=str(focus)[:120], evidence=evidence,
                              based_on_demo_data=demo, scope=scope, focus_event_id=focus_event_id)
            lesson["id"] = saved.data["id"] if saved.ok else None
        for c in community:  # saved as lessons so later planning can cite the board's community feedback
            evidence = [{"type": "event", "id": i} for i in c["event_ids"]] + [{"type": "reflection", "id": i} for i in c["reflection_ids"]]
            saved = self.tool(ctx, "save_historical_lesson", lesson=f"{c['observation']} (“{c['quote']}”, {c['evidence_label'].lower()})",
                              kind="community_insight", theme=c["lens_label"], confidence="medium", applies_to=str(focus)[:120],
                              evidence=evidence, based_on_demo_data=demo, scope=scope, focus_event_id=focus_event_id)
            c["id"] = saved.data["id"] if saved.ok else None

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
                  "focus_event_id": focus_event_id, "scope": scope, "community_insights": community},
        )
