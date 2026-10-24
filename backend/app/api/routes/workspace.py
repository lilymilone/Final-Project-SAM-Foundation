"""Overview, Event Studio, and Our Legacy routes."""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.permissions import Permission
from ...db.models import (
    AgentRun,
    BoardReflection,
    EventPlan,
    FinancialRecord,
    HistoricalEvent,
    HistoricalLesson,
    OutreachDraft,
    ResearchFinding,
)
from ...services.finance import finance_summary
from ..deps import CurrentUser, audit, current_user, get_db, require

router = APIRouter(prefix="/api", tags=["workspace"])

ACTIVE_PLAN_STATUSES = ("idea", "planning", "board_review")
MILESTONE_FUNDS_STEP = 25_000


# --- serializers --------------------------------------------------------------


def plan_out(p: EventPlan) -> dict:
    return {
        "id": p.id, "name": p.name, "event_type": p.event_type, "city": p.city,
        "target_date": p.target_date.isoformat() if p.target_date else None,
        "expected_attendance": p.expected_attendance, "fundraising_goal_usd": p.fundraising_goal_usd,
        "budget_limit_usd": p.budget_limit_usd, "status": p.status, "notes": p.notes, "is_demo": p.is_demo,
        "created_at": p.created_at.isoformat(),
    }


def reflection_out(r: BoardReflection) -> dict:
    return {
        "id": r.id, "author": r.author_label, "went_well": r.went_well, "challenges": r.challenges,
        "do_differently": r.do_differently, "rating": r.rating, "is_demo": r.is_demo,
        "created_at": r.created_at.isoformat(),
    }


def history_out(e: HistoricalEvent) -> dict:
    net = None
    if e.funds_raised_usd is not None and e.total_cost_usd is not None:
        net = round(e.funds_raised_usd - e.total_cost_usd, 2)
    return {
        "id": e.id, "name": e.name, "event_date": e.event_date.isoformat() if e.event_date else None,
        "location": e.location, "event_type": e.event_type, "attendance": e.attendance,
        "funds_raised_usd": e.funds_raised_usd, "total_cost_usd": e.total_cost_usd, "net_usd": net,
        "summary": e.summary, "is_demo": e.is_demo,
        "reflections": [reflection_out(r) for r in sorted(e.reflections, key=lambda r: r.created_at)],
    }


def history_stats(events: list[HistoricalEvent]) -> dict:
    """Plain arithmetic over recorded events. No AI involved."""
    with_money = [e for e in events if e.funds_raised_usd is not None and e.total_cost_usd is not None]
    best = max(with_money, key=lambda e: e.funds_raised_usd - e.total_cost_usd, default=None)
    efficient = max(
        (e for e in with_money if e.total_cost_usd), key=lambda e: e.funds_raised_usd / e.total_cost_usd, default=None
    )
    return {
        "events_recorded": len(events),
        "total_raised_usd": round(sum(e.funds_raised_usd or 0 for e in events), 2),
        "total_net_usd": round(sum(e.funds_raised_usd - e.total_cost_usd for e in with_money), 2),
        "highest_net_event": {"name": best.name, "net_usd": round(best.funds_raised_usd - best.total_cost_usd, 2)}
        if best else None,
        "most_efficient_event": {
            "name": efficient.name,
            "raised_per_dollar": round(efficient.funds_raised_usd / efficient.total_cost_usd, 2),
        } if efficient else None,
        "is_demo": any(e.is_demo for e in events),
    }


# --- overview -----------------------------------------------------------------


@router.get("/overview")
def overview(cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    org = cu.organization_id
    runs = db.scalars(select(AgentRun).where(AgentRun.organization_id == org).order_by(AgentRun.started_at.desc()).limit(5)).all()
    findings = db.scalars(
        select(ResearchFinding).where(ResearchFinding.organization_id == org, ResearchFinding.saved.is_(True))
        .order_by(ResearchFinding.created_at.desc()).limit(5)
    ).all()
    plans = db.scalars(
        select(EventPlan).where(EventPlan.organization_id == org, EventPlan.status.in_(ACTIVE_PLAN_STATUSES))
        .order_by(EventPlan.target_date)
    ).all()
    drafts = db.scalars(
        select(OutreachDraft).where(OutreachDraft.organization_id == org, OutreachDraft.status == "draft")
        .order_by(OutreachDraft.created_at.desc()).limit(5)
    ).all()
    lessons = db.scalars(
        select(HistoricalLesson).where(HistoricalLesson.organization_id == org).order_by(HistoricalLesson.created_at.desc()).limit(3)
    ).all()
    history = db.scalars(select(HistoricalEvent).where(HistoricalEvent.organization_id == org)).all()

    financial: dict = {"restricted": True, "flags": []}
    if Permission.VIEW_FINANCIALS in cu.permissions:
        records = db.scalars(select(FinancialRecord).where(FinancialRecord.organization_id == org)).all()
        summary = finance_summary(records, plans)
        financial = {"restricted": False, "flags": summary["flags"], "is_demo": summary["is_demo"]}

    return {
        "first_name": cu.user.first_name,
        "recent_activity": [
            {"id": r.id, "workflow_type": r.workflow_type, "status": r.status, "started_at": r.started_at.isoformat(),
             "spent_usd": r.spent_usd}
            for r in runs
        ],
        "saved_opportunities": [
            {"id": f.id, "title": f.title, "category": f.category, "source_url": f.source_url,
             "verification_status": f.verification_status}
            for f in findings
        ],
        "planned_events": [plan_out(p) for p in plans],
        "drafts_awaiting_review": [
            {"id": d.id, "subject": d.subject, "recipient_org": d.recipient_org, "draft_type": d.draft_type}
            for d in drafts
        ],
        "financial": financial,
        "history": history_stats(list(history)),
        "lessons": [{"id": l.id, "lesson": l.lesson, "confidence": l.confidence} for l in lessons],
    }


# --- Event Studio -------------------------------------------------------------


class EventPlanIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    event_type: str = Field(default="fundraiser", max_length=60)
    city: str = Field(default="", max_length=120)
    target_date: date | None = None
    expected_attendance: int | None = Field(default=None, ge=0, le=100_000)
    fundraising_goal_usd: float | None = Field(default=None, ge=0, le=100_000_000)
    budget_limit_usd: float | None = Field(default=None, ge=0, le=100_000_000)
    status: Literal["idea", "planning"] = "idea"
    notes: str = Field(default="", max_length=4000)

    @field_validator("name", "city", "event_type", "notes")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip()


@router.get("/events")
def list_events(cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    plans = db.scalars(
        select(EventPlan).where(EventPlan.organization_id == cu.organization_id).order_by(EventPlan.created_at.desc())
    ).all()
    return {"events": [plan_out(p) for p in plans]}


@router.post("/events", status_code=status.HTTP_201_CREATED)
def create_event(
    body: EventPlanIn,
    cu: CurrentUser = Depends(require(Permission.MANAGE_EVENTS)),
    db: Session = Depends(get_db),
) -> dict:
    plan = EventPlan(organization_id=cu.organization_id, created_by=cu.user.id, **body.model_dump())
    db.add(plan)
    db.flush()
    audit(db, cu, "event_plan_created", f"event_plan:{plan.id}", name=plan.name)
    db.commit()
    return {"event": plan_out(plan)}


# --- Our Legacy ---------------------------------------------------------------


class HistoricalEventIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    event_date: date | None = None
    location: str = Field(default="", max_length=200)
    event_type: str = Field(default="fundraiser", max_length=60)
    attendance: int | None = Field(default=None, ge=0, le=1_000_000)
    funds_raised_usd: float | None = Field(default=None, ge=0, le=100_000_000)
    total_cost_usd: float | None = Field(default=None, ge=0, le=100_000_000)
    summary: str = Field(default="", max_length=4000)


class ReflectionIn(BaseModel):
    went_well: str = Field(default="", max_length=4000)
    challenges: str = Field(default="", max_length=4000)
    do_differently: str = Field(default="", max_length=4000)
    rating: int | None = Field(default=None, ge=1, le=5)


@router.get("/legacy/events")
def list_history(cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    events = db.scalars(
        select(HistoricalEvent).where(HistoricalEvent.organization_id == cu.organization_id)
        .order_by(HistoricalEvent.event_date.desc())
    ).all()
    return {"events": [history_out(e) for e in events], "stats": history_stats(list(events))}


@router.post("/legacy/events", status_code=status.HTTP_201_CREATED)
def create_history(
    body: HistoricalEventIn,
    cu: CurrentUser = Depends(require(Permission.MANAGE_EVENTS)),
    db: Session = Depends(get_db),
) -> dict:
    org = cu.organization_id
    raised_before = db.scalar(
        select(func.coalesce(func.sum(HistoricalEvent.funds_raised_usd), 0.0)).where(HistoricalEvent.organization_id == org)
    ) or 0.0
    event = HistoricalEvent(organization_id=org, created_by=cu.user.id, **body.model_dump())
    db.add(event)
    db.flush()
    count = db.scalar(select(func.count(HistoricalEvent.id)).where(HistoricalEvent.organization_id == org)) or 0
    raised_after = raised_before + (body.funds_raised_usd or 0)

    milestone = None
    if raised_after // MILESTONE_FUNDS_STEP > raised_before // MILESTONE_FUNDS_STEP:
        milestone = f"Recorded lifetime funds raised passed ${int(raised_after // MILESTONE_FUNDS_STEP * MILESTONE_FUNDS_STEP):,}."
    elif count % 5 == 0:
        milestone = f"{count} events now preserved in Our Legacy."
    audit(db, cu, "historical_event_created", f"historical_event:{event.id}", name=event.name)
    db.commit()
    db.refresh(event)
    return {"event": history_out(event), "milestone": milestone}


@router.post("/legacy/events/{event_id}/reflections", status_code=status.HTTP_201_CREATED)
def add_reflection(
    event_id: int,
    body: ReflectionIn,
    cu: CurrentUser = Depends(require(Permission.WRITE_REFLECTIONS)),
    db: Session = Depends(get_db),
) -> dict:
    event = db.get(HistoricalEvent, event_id)
    if event is None or event.organization_id != cu.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    if not (body.went_well.strip() or body.challenges.strip() or body.do_differently.strip()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Please write at least one reflection.")
    reflection = BoardReflection(
        historical_event_id=event.id,
        user_id=cu.user.id,
        author_label=f"{cu.user.first_name} {cu.user.last_name}".strip(),
        **body.model_dump(),
    )
    db.add(reflection)
    db.flush()
    audit(db, cu, "reflection_created", f"historical_event:{event.id}")
    db.commit()
    return {"reflection": reflection_out(reflection)}
