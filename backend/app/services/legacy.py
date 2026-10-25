"""Our Legacy: serializers, outcome math, and impact metrics (deterministic)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import BoardReflection, EventPhoto, HistoricalEvent, HistoricalLesson

REFLECTION_QUESTIONS = [
    ("went_well", "What worked particularly well?"),
    ("challenges", "What did not go as planned?"),
    ("unexpected_costs", "Were there unexpected expenses or complications?"),
    ("attendee_feedback", "What feedback did attendees provide?"),
    ("should_repeat", "What should we repeat?"),
    ("do_differently", "What should we change?"),
    ("advice", "What advice would you give to the board planning the next event?"),
    # Community questions (the foundation's philosophy). Board observations, never treated as verified outcomes.
    ("welcome_inclusion", "Did attendees seem to feel welcomed and included?"),
    ("connection_moments", "Which activities or moments created connection?"),
    ("volunteer_appreciation", "Did volunteers seem to feel appreciated?"),
    ("accessibility_issues", "Were any accessibility or inclusion problems reported?"),
]
ACTIVE_LESSON = ("new", "reviewed", "adopted", None)


def net_usd(e: HistoricalEvent) -> float | None:
    if e.funds_raised_usd is None or e.total_cost_usd is None:
        return None
    return round(e.funds_raised_usd - e.total_cost_usd, 2)


def goal_pct(e: HistoricalEvent) -> float | None:
    if not e.fundraising_goal_usd or e.funds_raised_usd is None:
        return None
    return round(100 * e.funds_raised_usd / e.fundraising_goal_usd, 1)


def reflection_out(r: BoardReflection) -> dict:
    return {
        "id": r.id, "event_id": r.historical_event_id, "author": r.author_label or "Board member", "user_id": r.user_id,
        "answers": [{"key": k, "question": q, "answer": getattr(r, k) or ""} for k, q in REFLECTION_QUESTIONS],
        "rating": r.rating, "is_demo": r.is_demo, "created_at": r.created_at.isoformat(),
    }


def photo_out(p: EventPhoto) -> dict:
    return {"id": p.id, "caption": p.caption, "url": f"/api/legacy/photos/{p.id}", "is_demo": bool(p.is_demo),
            "created_at": p.created_at.isoformat()}


def event_out(e: HistoricalEvent, *, detail: bool = False) -> dict:
    out = {
        "id": e.id, "name": e.name, "event_date": e.event_date.isoformat() if e.event_date else None,
        "location": e.location, "event_type": e.event_type, "venue": e.venue, "attendance": e.attendance,
        "fundraising_goal_usd": e.fundraising_goal_usd, "funds_raised_usd": e.funds_raised_usd,
        "total_cost_usd": e.total_cost_usd, "net_usd": net_usd(e), "goal_pct": goal_pct(e),
        "sponsorship_usd": e.sponsorship_usd, "sponsorship_info": e.sponsorship_info, "summary": e.summary,
        "notes": e.notes, "is_demo": e.is_demo, "reflection_count": len(e.reflections),
        "volunteers_count": e.volunteers_count, "repeat_participants": e.repeat_participants,
        "partnerships_formed": e.partnerships_formed, "funds_directed_usd": e.funds_directed_usd,
        "community_outcomes": e.community_outcomes,
        "photos": [photo_out(p) for p in sorted(e.photos, key=lambda p: p.id)],
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }
    if detail:
        out["reflections"] = [reflection_out(r) for r in sorted(e.reflections, key=lambda r: r.created_at)]
    return out


def history_stats(events: list[HistoricalEvent]) -> dict:
    """Plain arithmetic over recorded events. No AI involved."""
    with_money = [e for e in events if e.funds_raised_usd is not None and e.total_cost_usd is not None]
    best = max(with_money, key=lambda e: e.funds_raised_usd - e.total_cost_usd, default=None)
    efficient = max((e for e in with_money if e.total_cost_usd), key=lambda e: e.funds_raised_usd / e.total_cost_usd, default=None)
    return {
        "events_recorded": len(events),
        "total_raised_usd": round(sum(e.funds_raised_usd or 0 for e in events), 2),
        "total_net_usd": round(sum(e.funds_raised_usd - e.total_cost_usd for e in with_money), 2),
        "highest_net_event": {"name": best.name, "net_usd": round(best.funds_raised_usd - best.total_cost_usd, 2)} if best else None,
        "most_efficient_event": {"name": efficient.name, "raised_per_dollar": round(efficient.funds_raised_usd / efficient.total_cost_usd, 2)}
        if efficient else None,
        "is_demo": any(e.is_demo for e in events),
    }


def lesson_evidence_labels(db: Session, org_id: int, lessons: list[HistoricalLesson]) -> dict[int, list[dict]]:
    names = dict(db.execute(select(HistoricalEvent.id, HistoricalEvent.name).where(HistoricalEvent.organization_id == org_id)).all())
    refl = {r.id: (r.author_label or "Board member", names.get(r.historical_event_id, "event"), r.historical_event_id)
            for r in db.scalars(select(BoardReflection).join(HistoricalEvent).where(HistoricalEvent.organization_id == org_id))}
    out: dict[int, list[dict]] = {}
    for l in lessons:
        items = []
        for e in l.evidence or []:
            if e.get("type") == "event" and e.get("id") in names:
                items.append({"type": "event", "id": e["id"], "event_id": e["id"], "label": names[e["id"]]})
            elif e.get("type") == "reflection" and e.get("id") in refl:
                author, ev, ev_id = refl[e["id"]]
                items.append({"type": "reflection", "id": e["id"], "event_id": ev_id, "label": f"{author} on {ev}"})
        out[l.id] = items
    return out


def lesson_out(l: HistoricalLesson, evidence: list[dict]) -> dict:
    return {"id": l.id, "run_id": l.run_id, "lesson": l.lesson, "kind": l.kind, "theme": l.theme, "confidence": l.confidence,
            "applies_to": l.applies_to, "scope": l.scope, "focus_event_id": l.focus_event_id, "status": l.status or "new",
            "reviewed_at": l.reviewed_at.isoformat() if l.reviewed_at else None, "based_on_demo_data": l.based_on_demo_data,
            "evidence": evidence, "created_at": l.created_at.isoformat()}


def recurring_issues(lessons: list[HistoricalLesson]) -> list[dict]:
    """A recurring issue = a current 'recurring_problem' lesson whose evidence spans 2+ distinct records."""
    by_theme: dict[str, set[str]] = {}
    for l in lessons:
        if l.kind != "recurring_problem" or not l.theme or (l.status or "new") not in ("new", "reviewed", "adopted"):
            continue
        refs = {f"{e.get('type')}:{e.get('id')}" for e in (l.evidence or [])}
        if len(refs) >= 2:
            theme = l.theme.strip().lower()
            # Merge near-duplicate theme names from different analyses ("late changes" / "late changes and rush work").
            key = next((k for k in by_theme if k in theme or theme in k), theme)
            if key != theme and len(theme) < len(key):
                by_theme[theme] = by_theme.pop(key)
                key = theme
            by_theme.setdefault(key, set()).update(refs)
    return [{"theme": t, "evidence_count": len(r)} for t, r in sorted(by_theme.items(), key=lambda x: -len(x[1]))]


def legacy_metrics(db: Session, org_id: int) -> dict:
    events = db.scalars(select(HistoricalEvent).where(HistoricalEvent.organization_id == org_id)).all()
    refl = db.scalars(select(BoardReflection).join(HistoricalEvent).where(HistoricalEvent.organization_id == org_id)).all()
    lessons = db.scalars(select(HistoricalLesson).where(HistoricalLesson.organization_id == org_id)).all()
    current = [l for l in lessons if (l.status or "new") != "superseded"]
    status_counts: dict[str, int] = {}
    for l in current:
        status_counts[l.status or "new"] = status_counts.get(l.status or "new", 0) + 1
    contributors = {r.user_id or r.author_label for r in refl}
    photos = db.scalar(select(func.count(EventPhoto.id)).join(HistoricalEvent).where(HistoricalEvent.organization_id == org_id)) or 0
    return {
        "events_recorded": len(events),
        "events_demo": sum(1 for e in events if e.is_demo),
        "reflections_collected": len(refl),
        "reflections_demo": sum(1 for r in refl if r.is_demo),
        "contributors": len(contributors),
        "photos": photos,
        "lessons_generated": len(lessons),
        "lessons_current": len(current),
        "recurring_issues": recurring_issues(current),
        "recommendations_reviewed": status_counts.get("reviewed", 0),
        "recommendations_adopted": status_counts.get("adopted", 0),
        "recommendations_dismissed": status_counts.get("dismissed", 0),
        "outcome_improvement": "not_measured",
        "outcome_note": "No outcome improvement is claimed. Measuring it needs the results of a future event planned with these lessons.",
    }
