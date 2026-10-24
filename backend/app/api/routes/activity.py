"""Agent Activity: real runs, handoffs, tool calls, and per-call model usage."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ...agents.registry import AGENT_SPECS
from ...db.models import AgentHandoff, AgentRun, AgentToolCall, ModelUsage
from ..deps import CurrentUser, current_user, get_db

router = APIRouter(prefix="/api", tags=["activity"])


@router.get("/agents")
def agents(_: CurrentUser = Depends(current_user)) -> dict:
    return {
        "agents": [
            {
                "name": s.name.value, "display_name": s.display_name, "purpose": s.purpose,
                "allowed_tools": list(s.allowed_tools), "status": s.status,
            }
            for s in AGENT_SPECS
        ]
    }


@router.get("/activity")
def activity(cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    org = cu.organization_id
    runs = db.scalars(select(AgentRun).where(AgentRun.organization_id == org).order_by(AgentRun.started_at.desc()).limit(20)).all()
    run_ids = [r.id for r in runs]
    # Model calls belong to this workspace's runs (or to system checks with no run).
    in_org = or_(ModelUsage.run_id.is_(None), ModelUsage.run_id.in_(select(AgentRun.id).where(AgentRun.organization_id == org)))
    usage = db.scalars(select(ModelUsage).where(in_org).order_by(ModelUsage.created_at.desc()).limit(100)).all()
    handoffs = db.scalars(select(AgentHandoff).where(AgentHandoff.run_id.in_(run_ids))).all() if run_ids else []
    tools = db.scalars(select(AgentToolCall).where(AgentToolCall.run_id.in_(run_ids))).all() if run_ids else []
    totals = db.execute(
        select(
            func.count(ModelUsage.id),
            func.coalesce(func.sum(ModelUsage.input_tokens), 0),
            func.coalesce(func.sum(ModelUsage.cached_input_tokens), 0),
            func.coalesce(func.sum(ModelUsage.output_tokens), 0),
            func.coalesce(func.sum(ModelUsage.estimated_cost_usd), 0.0),
        ).where(in_org)
    ).one()
    return {
        "runs": [
            {"id": r.id, "workflow_type": r.workflow_type, "status": r.status, "strategy": r.strategy,
             "provider": r.provider, "spent_usd": r.spent_usd, "model_calls": r.model_calls,
             "started_at": r.started_at.isoformat(), "finished_at": r.finished_at.isoformat() if r.finished_at else None}
            for r in runs
        ],
        "model_calls": [
            {"id": u.id, "run_id": u.run_id, "agent": u.agent, "task": u.task, "strategy": u.strategy,
             "provider": u.provider, "requested_tier": u.requested_tier, "selected_model": u.selected_model,
             "model_used": u.model_used, "selection_reason": u.selection_reason,
             "substitution_note": u.substitution_note, "input_tokens": u.input_tokens,
             "cached_input_tokens": u.cached_input_tokens, "output_tokens": u.output_tokens,
             "estimated_cost_usd": u.estimated_cost_usd, "latency_ms": u.latency_ms, "status": u.status,
             "created_at": u.created_at.isoformat()}
            for u in usage
        ],
        "handoffs": [
            {"id": h.id, "run_id": h.run_id, "from_agent": h.from_agent, "to_agent": h.to_agent,
             "objective": h.objective, "status": h.status}
            for h in handoffs
        ],
        "tool_calls": [
            {"id": t.id, "run_id": t.run_id, "agent": t.agent, "tool_name": t.tool_name, "allowed": t.allowed,
             "denial_reason": t.denial_reason, "created_at": t.created_at.isoformat()}
            for t in tools
        ],
        "totals": {
            "model_calls": totals[0], "input_tokens": totals[1], "cached_input_tokens": totals[2],
            "output_tokens": totals[3], "estimated_cost_usd": round(float(totals[4]), 6),
        },
    }
