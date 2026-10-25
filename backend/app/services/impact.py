"""Community impact metrics, computed only from stored records.

Each metric carries one evidence label:
  * Actual observation: a count or amount the board recorded for an event
  * Self-reported:      board members' reflections, including what they say attendees told them
  * AI interpretation:  community insights from the Event Intelligence agent (each quotes its record)
  * Estimate:           a ratio derived from recorded totals, labeled as an estimate

A metric with no records shows "Not recorded", never zero. Nothing here calls
a model, and no testimonial or figure is generated.
"""

from __future__ import annotations

from sqlalchemy import select

from ..db.models import BoardReflection, HistoricalEvent, HistoricalLesson

ACTUAL, SELF, AI, ESTIMATE = "Actual observation", "Self-reported", "AI interpretation", "Estimate"


def _metric(key: str, label: str, value, kind: str, basis: str, recorded: int, total: int, display: str | None = None,
            examples: list | None = None) -> dict:
    shown = display if display is not None else ("Not recorded" if value is None else f"{value:,}")
    return {"key": key, "label": label, "value": value, "display": shown, "type": kind, "basis": basis,
            "coverage": f"{recorded} of {total} event{'s' if total != 1 else ''} recorded" if total else "No events recorded",
            "examples": examples or []}


def impact_metrics(db, organization_id: int) -> dict:
    with db.session() as s:
        events = s.scalars(select(HistoricalEvent).where(HistoricalEvent.organization_id == organization_id)
                           .order_by(HistoricalEvent.event_date)).all()
        reflections = s.execute(select(BoardReflection, HistoricalEvent.name).join(
            HistoricalEvent, HistoricalEvent.id == BoardReflection.historical_event_id).where(
            HistoricalEvent.organization_id == organization_id)).all()
        insights = s.scalars(select(HistoricalLesson).where(
            HistoricalLesson.organization_id == organization_id, HistoricalLesson.kind == "community_insight",
            HistoricalLesson.status.in_(("new", "reviewed", "adopted")))).all()
    n = len(events)

    def total(attr: str) -> tuple[float | None, int]:
        vals = [getattr(e, attr) for e in events if getattr(e, attr) is not None]
        return (sum(vals) if vals else None), len(vals)

    attendance, a_n = total("attendance")
    volunteers, v_n = total("volunteers_count")
    repeat, r_n = total("repeat_participants")
    partners, p_n = total("partnerships_formed")
    directed, d_n = total("funds_directed_usd")
    nets = [e.funds_raised_usd - e.total_cost_usd for e in events if e.funds_raised_usd is not None and e.total_cost_usd is not None]
    pairs = [(e.funds_directed_usd, e.attendance) for e in events if e.funds_directed_usd is not None and e.attendance]

    def quotes(field: str) -> list[dict]:
        return [{"text": getattr(r, field), "source": f"{r.author_label or 'Board member'}, {name}", "reflection_id": r.id}
                for r, name in reflections if getattr(r, field)]

    feedback, welcome = quotes("attendee_feedback"), quotes("welcome_inclusion")
    event_of_reflection = {r.id: r.historical_event_id for r, _ in reflections}
    insight_events = {x.get("id") if x.get("type") == "event" else event_of_reflection.get(x.get("id"))
                      for i in insights for x in (i.evidence or [])} - {None}
    outcomes = [{"text": e.community_outcomes, "source": e.name, "event_id": e.id} for e in events if e.community_outcomes]
    metrics = [
        _metric("participants", "Community participants", int(attendance) if attendance is not None else None, ACTUAL,
                "Sum of recorded attendance.", a_n, n),
        _metric("volunteers", "Volunteers", int(volunteers) if volunteers is not None else None, ACTUAL,
                "Sum of recorded volunteer counts.", v_n, n),
        _metric("repeat_participants", "Repeat participants", int(repeat) if repeat is not None else None, ACTUAL,
                "Returning participants, where the board recorded them.", r_n, n),
        _metric("partnerships_formed", "Partnerships formed", int(partners) if partners is not None else None, ACTUAL,
                "Partnerships the board recorded for each event.", p_n, n),
        _metric("funds_directed", "Funds directed to charitable programs", directed, ACTUAL,
                "Sum of the amounts the board recorded as directed to programs.", d_n, n,
                display=f"${directed:,.0f}" if directed is not None else "Not recorded"),
        _metric("net_raised", "Net raised (funds raised minus expenses)", sum(nets) if nets else None, ACTUAL,
                "Calculated in code from recorded funds raised and expenses.", len(nets), n,
                display=f"${sum(nets):,.0f}" if nets else "Not recorded"),
        _metric("participant_feedback", "Participant feedback recorded", len(feedback), SELF,
                "Reflections that relay attendee feedback (board members' words, not a survey).",
                len({q["source"].split(", ", 1)[1] for q in feedback}), n, display=f"{len(feedback)} reflection(s)" if feedback else "Not recorded",
                examples=feedback[:3]),
        _metric("reported_belonging", "Reported welcome and belonging", len(welcome), SELF,
                "Board observations of whether attendees seemed welcomed. Observations, not measured outcomes.",
                len({q["source"].split(", ", 1)[1] for q in welcome}), n, display=f"{len(welcome)} observation(s)" if welcome else "Not recorded",
                examples=welcome[:3]),
        _metric("community_outcomes", "Documented community outcomes", len(outcomes), ACTUAL,
                "Outcomes the board recorded for an event.", len(outcomes), n,
                display=f"{len(outcomes)} documented" if outcomes else "Not recorded", examples=outcomes[:3]),
        _metric("community_insights", "Community insights from Event Intelligence", len(insights), AI,
                "Each insight quotes the reflection it came from; code checked every quote.", len(insight_events), n,
                display=f"{len(insights)} insight(s)" if insights else "Not generated yet",
                examples=[{"text": i.lesson, "source": i.theme, "lesson_id": i.id} for i in insights[:3]]),
    ]
    if pairs:
        ratio = sum(d for d, _ in pairs) / sum(a for _, a in pairs)
        metrics.append(_metric("directed_per_participant", "Funds directed per participant", round(ratio, 2), ESTIMATE,
                               "Ratio of recorded totals for events with both figures. It does not measure impact on any person.",
                               len(pairs), n, display=f"${ratio:,.0f}"))
    return {"metrics": metrics, "events_recorded": n, "is_demo": any(e.is_demo for e in events),
            "labels": {ACTUAL: "A count or amount the board recorded.", SELF: "Board reflections, including what attendees told them.",
                       AI: "An agent's reading of the records, quoting its source.", ESTIMATE: "Derived from recorded totals; approximate."}}
