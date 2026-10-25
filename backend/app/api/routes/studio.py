"""Event Studio: edit plans, recalculate the financial model, and read the strategy packet.

Recalculation is deterministic, so editing an assumption never calls a model.
The packet is assembled from the stored run, and finance sections are
redacted for roles without financial access.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.permissions import Permission
from ...db.models import AgentRun, EventPlan, FinancialRecord
from ...services import calculators as calc
from ...services import event_model as em
from ...services.packet import build_packet, packet_markdown
from ..deps import CurrentUser, audit, current_user, get_db, require
from .workspace import EventPlanIn, plan_out

router = APIRouter(prefix="/api", tags=["studio"])

LIMITS = {"attendance": (1, 5000), "contingency_pct": (0, 0.6), "deposit_pct": (0, 1)}


def _clean_assumptions(values: dict) -> dict:
    out = {}
    for key, value in values.items():
        if key not in em.ASSUMPTION_LABELS:
            raise HTTPException(422, f"Unknown assumption: {key}")
        if isinstance(value, dict):
            value = value.get("value")
        if value is None:
            out[key] = None
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise HTTPException(422, f"{em.ASSUMPTION_LABELS[key]} must be a number.") from None
        lo, hi = LIMITS.get(key, (0, 10_000_000))
        if not lo <= value <= hi:
            raise HTTPException(422, f"{em.ASSUMPTION_LABELS[key]} must be between {lo:g} and {hi:g}.")
        out[key] = int(value) if key == "attendance" else value
    return out


def _get_plan(db: Session, cu: CurrentUser, plan_id: int) -> EventPlan:
    plan = db.get(EventPlan, plan_id)
    if plan is None or plan.organization_id != cu.organization_id:
        raise HTTPException(404, "Event plan not found.")
    return plan


@router.put("/events/{plan_id}")
def update_plan(plan_id: int, body: EventPlanIn, cu: CurrentUser = Depends(require(Permission.MANAGE_EVENTS)),
                db: Session = Depends(get_db)) -> dict:
    plan = _get_plan(db, cu, plan_id)
    for key, value in body.model_dump().items():
        setattr(plan, key, value)
    audit(db, cu, "event_plan_updated", f"event_plan:{plan.id}")
    db.commit()
    return {"event": plan_out(plan)}


class AssumptionsIn(BaseModel):
    assumptions: dict = Field(default_factory=dict)


@router.put("/events/{plan_id}/assumptions")
def save_assumptions(plan_id: int, body: AssumptionsIn, cu: CurrentUser = Depends(require(Permission.MANAGE_EVENTS)),
                     db: Session = Depends(get_db)) -> dict:
    plan = _get_plan(db, cu, plan_id)
    cleaned = {k: v for k, v in _clean_assumptions(body.assumptions).items() if v is not None}
    plan.assumptions = cleaned or None
    audit(db, cu, "event_assumptions_saved", f"event_plan:{plan.id}", keys=sorted(cleaned))
    db.commit()
    return {"event": plan_out(plan)}


@router.get("/events/{plan_id}/strategies")
def plan_strategies(plan_id: int, cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    _get_plan(db, cu, plan_id)
    runs = db.scalars(select(AgentRun).where(AgentRun.event_plan_id == plan_id, AgentRun.workflow_type == "plan_event")
                      .order_by(AgentRun.started_at.desc()).limit(10)).all()
    return {"strategies": [{"run_id": r.id, "status": r.status, "research_mode": r.research_mode, "started_at": r.started_at.isoformat(),
                            "headline": ((r.result or {}).get("recommendation") or {}).get("headline"),
                            "verdict": ((r.result or {}).get("finance") or {}).get("verdict") if Permission.VIEW_FINANCIALS in cu.permissions else None,
                            "spent_usd": r.spent_usd} for r in runs]}


class CalculateIn(BaseModel):
    assumptions: dict
    max_budget_usd: float | None = Field(default=None, ge=0, le=100_000_000)
    target_usd: float | None = Field(default=None, ge=0, le=100_000_000)
    min_contingency_pct: float | None = Field(default=None, ge=0, le=0.6)


@router.post("/event-model/calculate")
def calculate(body: CalculateIn, cu: CurrentUser = Depends(require(Permission.VIEW_FINANCIALS)), db: Session = Depends(get_db)) -> dict:
    values = _clean_assumptions(body.assumptions)
    required = ("attendance", "venue_rental_usd", "catering_per_guest_usd", "entertainment_usd", "marketing_usd", "staffing_usd",
                "insurance_usd", "contingency_pct", "deposit_pct")
    missing = [em.ASSUMPTION_LABELS[k] for k in required if values.get(k) is None]
    if missing:
        raise HTTPException(422, "These cost assumptions are required: " + ", ".join(missing))
    original = body.assumptions
    assumptions = {k: {"value": v, "kind": (original.get(k) or {}).get("kind", "board") if isinstance(original.get(k), dict) else "board",
                       "basis": (original.get(k) or {}).get("basis", "Edited by the board") if isinstance(original.get(k), dict) else "Edited by the board"}
                   for k, v in values.items()}
    model = em.compute(assumptions, max_budget_usd=body.max_budget_usd, target_usd=body.target_usd)
    model["catering_minimum_risk"] = em.catering_minimum_risk(assumptions)
    records = [{"period": r.period, "kind": r.kind, "amount_usd": r.amount_usd}
               for r in db.scalars(select(FinancialRecord).where(FinancialRecord.organization_id == cu.organization_id))]
    position = calc.financial_position(records)
    return {"model": model, "affordability": em.affordability(model, position, body.min_contingency_pct), "position": position}


def _packet_or_404(request: Request, run_id: int, cu: CurrentUser) -> dict:
    packet = build_packet(request.app.state.db, run_id, cu.organization_id, Permission.VIEW_FINANCIALS in cu.permissions)
    if packet is None:
        raise HTTPException(404, "Strategy not found.")
    return packet


@router.get("/runs/{run_id}/packet")
def get_packet(run_id: int, request: Request, cu: CurrentUser = Depends(current_user)) -> dict:
    return {"packet": _packet_or_404(request, run_id, cu)}


@router.get("/runs/{run_id}/packet.md", response_class=PlainTextResponse)
def get_packet_markdown(run_id: int, request: Request, cu: CurrentUser = Depends(current_user)) -> PlainTextResponse:
    packet = _packet_or_404(request, run_id, cu)
    return PlainTextResponse(packet_markdown(packet), headers={"Content-Disposition": f'attachment; filename="event-strategy-{run_id}.md"'})
