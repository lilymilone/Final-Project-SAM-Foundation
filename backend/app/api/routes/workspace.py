"""Overview, Event Studio, and Our Legacy routes."""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.permissions import Permission
from ...db.models import (
    AgentRun,
    EventPlan,
    FinancialRecord,
    HistoricalEvent,
    HistoricalLesson,
    OutreachDraft,
    ResearchFinding,
)
from ...services.finance import finance_summary
from ...services.legacy import history_stats
from ..deps import CurrentUser, audit, current_user, get_db, require

router = APIRouter(prefix="/api", tags=["workspace"])

ACTIVE_PLAN_STATUSES = ("idea", "planning", "board_review")


# --- serializers --------------------------------------------------------------


def plan_out(p: EventPlan) -> dict:
    return {
        "id": p.id, "name": p.name, "event_type": p.event_type, "city": p.city,
        "target_date": p.target_date.isoformat() if p.target_date else None,
        "expected_attendance": p.expected_attendance, "fundraising_goal_usd": p.fundraising_goal_usd,
        "budget_limit_usd": p.budget_limit_usd, "status": p.status, "notes": p.notes, "is_demo": p.is_demo,
        "created_at": p.created_at.isoformat(),
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
