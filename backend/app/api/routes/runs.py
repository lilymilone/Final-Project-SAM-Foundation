"""Workflow runs: start, watch live, stop.

The run detail shows real handoffs, statuses, tool calls, and model calls. It
never shows prompts or keys. Finance and donor details are redacted for board
roles that cannot see them directly.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.config import Settings
from ...core.permissions import Permission
from ...db.models import AgentHandoff, AgentRun, AgentToolCall, EventPlan, HistoricalEvent, ModelUsage
from ..deps import CurrentUser, audit, current_user, get_db, get_settings_dep, require

router = APIRouter(prefix="/api/runs", tags=["runs"])

Intent = Literal["plan_event", "mission_discovery", "partnership_outreach", "financial_review", "donations_review", "event_learning"]
INTENT_PERMISSION = {"financial_review": Permission.VIEW_FINANCIALS, "donations_review": Permission.VIEW_DONOR_DATA}
FINANCE_AGENT, DONATIONS_AGENT = "financial_analysis", "donations_compliance"


class RunIn(BaseModel):
    request: str = Field(min_length=5, max_length=2000)
    intent: Intent | None = None
    research_mode: Literal["synthetic", "live"] = "synthetic"
    event_plan_id: int | None = None
    historical_event_id: int | None = None
    use_history: bool = True

    @field_validator("request")
    @classmethod
    def _clean(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 5:
            raise ValueError("Please describe what you need in a sentence.")
        return v


def run_summary(r: AgentRun) -> dict:
    return {
        "id": r.id, "request": r.request_text, "workflow_type": r.workflow_type,
        "intent": (r.result or {}).get("intent"), "status": r.status, "strategy": r.strategy, "provider": r.provider,
        "research_mode": r.research_mode, "budget_usd": r.budget_usd, "spent_usd": round(r.spent_usd or 0, 6),
        "model_calls": r.model_calls, "started_at": r.started_at.isoformat(),
        "finished_at": r.finished_at.isoformat() if r.finished_at else None, "duration_ms": r.duration_ms, "error": r.error,
        "event_plan_id": r.event_plan_id, "options": (r.plan or {}).get("options"),
    }


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def start_run(
    body: RunIn,
    request: Request,
    cu: CurrentUser = Depends(require(Permission.RUN_AGENTS)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> dict:
    if settings.provider is None:
        raise HTTPException(400, "No AI key is configured. Add OPENAI_API_KEY (or PORTKEY_API_KEY) to .env and restart.")
    if body.intent in INTENT_PERMISSION and INTENT_PERMISSION[body.intent] not in cu.permissions:
        raise HTTPException(403, f"Your board role ({cu.role}) cannot run this workflow.")
    manager = request.app.state.workflows
    active = manager.active_run(cu.organization_id)
    if active:
        raise HTTPException(409, f"Workflow #{active} is still running. Wait for it to finish or stop it first.")
    if body.event_plan_id is not None:
        plan = db.get(EventPlan, body.event_plan_id)
        if plan is None or plan.organization_id != cu.organization_id:
            raise HTTPException(404, "Event plan not found.")
    options = {"use_history": body.use_history}
    if body.historical_event_id is not None:
        past = db.get(HistoricalEvent, body.historical_event_id)
        if past is None or past.organization_id != cu.organization_id:
            raise HTTPException(404, "Past event not found.")
        options.update(historical_event_id=past.id, historical_event_name=past.name)
    run = AgentRun(
        organization_id=cu.organization_id, user_id=cu.user.id, workflow_type=body.intent or "auto", request_text=body.request,
        status="queued", strategy=cu.user.model_strategy, provider=settings.provider, budget_usd=settings.workflow_budget_usd,
        research_mode=body.research_mode, event_plan_id=body.event_plan_id, plan={"options": options},
    )
    db.add(run)
    db.flush()
    audit(db, cu, "workflow_started", f"run:{run.id}", intent=body.intent or "auto", research_mode=body.research_mode)
    db.commit()
    manager.start(run.id, user_id=cu.user.id, organization_id=cu.organization_id, permissions=cu.permissions,
                  strategy=cu.user.model_strategy, research_mode=body.research_mode, request=body.request,
                  intent_hint=body.intent, event_plan_id=body.event_plan_id, options=options)
    return {"run": run_summary(run)}


@router.get("")
def list_runs(cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    runs = db.scalars(select(AgentRun).where(AgentRun.organization_id == cu.organization_id)
                      .order_by(AgentRun.started_at.desc()).limit(30)).all()
    return {"runs": [run_summary(r) for r in runs]}


@router.get("/{run_id}")
def run_detail(run_id: int, cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    run = db.get(AgentRun, run_id)
    if run is None or run.organization_id != cu.organization_id:
        raise HTTPException(404, "Run not found.")
    hidden_agents = set()
    if Permission.VIEW_FINANCIALS not in cu.permissions:
        hidden_agents.add(FINANCE_AGENT)
    if Permission.VIEW_DONOR_DATA not in cu.permissions:
        hidden_agents.add(DONATIONS_AGENT)

    handoffs = db.scalars(select(AgentHandoff).where(AgentHandoff.run_id == run_id).order_by(AgentHandoff.id)).all()
    tools = db.scalars(select(AgentToolCall).where(AgentToolCall.run_id == run_id).order_by(AgentToolCall.id)).all()
    calls = db.scalars(select(ModelUsage).where(ModelUsage.run_id == run_id).order_by(ModelUsage.id)).all()

    steps = []
    for h in handoffs:
        redacted = h.to_agent in hidden_agents
        steps.append({
            "id": h.id, "step_key": h.step_key, "kind": h.kind, "revision_round": h.revision_round,
            "from_agent": h.from_agent, "to_agent": h.to_agent, "objective": h.objective, "status": h.status,
            "started_at": h.started_at.isoformat() if h.started_at else None,
            "completed_at": h.completed_at.isoformat() if h.completed_at else None,
            "duration_ms": h.duration_ms, "error": h.error, "redacted": redacted,
            "constraints": (h.payload or {}).get("constraints", []),
            "result": None if redacted or h.result is None else h.result,
            "tool_calls": [{"id": t.id, "tool": t.tool_name, "allowed": t.allowed, "ok": t.ok, "duration_ms": t.duration_ms,
                            "summary": None if redacted else t.result_summary, "denial": t.denial_reason, "error": t.error}
                           for t in tools if t.handoff_id == h.id],
            "model_calls": [{"id": c.id, "task": c.task, "tier": c.requested_tier, "model": c.selected_model, "model_used": c.model_used,
                             "reason": c.selection_reason, "substitution": c.substitution_note, "input_tokens": c.input_tokens,
                             "cached_input_tokens": c.cached_input_tokens, "output_tokens": c.output_tokens,
                             "web_search_calls": c.web_search_calls, "cost_usd": c.estimated_cost_usd, "latency_ms": c.latency_ms,
                             "attempt": c.attempt, "status": c.status, "error": c.error}
                            for c in calls if c.handoff_id == h.id],
        })
    result = dict(run.result or {})
    if FINANCE_AGENT in hidden_agents:
        for key in ("finance", "figures"):
            result.pop(key, None)
    if DONATIONS_AGENT in hidden_agents:
        result.pop("donations", None)
    totals = {
        "model_calls": len(calls),
        "input_tokens": sum(c.input_tokens or 0 for c in calls),
        "cached_input_tokens": sum(c.cached_input_tokens or 0 for c in calls),
        "output_tokens": sum(c.output_tokens or 0 for c in calls),
        "web_search_calls": sum(c.web_search_calls or 0 for c in calls),
        "cost_usd": round(sum(c.estimated_cost_usd or 0 for c in calls), 6),
        "tool_calls": len(tools),
        "denied_tool_calls": sum(1 for t in tools if not t.allowed),
        "handoffs": len(handoffs),
        "revisions": sum(1 for h in handoffs if h.kind == "revision"),
    }
    return {"run": run_summary(run), "steps": steps, "result": result or None, "totals": totals}


@router.post("/{run_id}/stop")
def stop_run(run_id: int, request: Request, cu: CurrentUser = Depends(require(Permission.RUN_AGENTS)), db: Session = Depends(get_db)) -> dict:
    run = db.get(AgentRun, run_id)
    if run is None or run.organization_id != cu.organization_id:
        raise HTTPException(404, "Run not found.")
    if run.status not in ("queued", "running"):
        return {"stopping": False, "status": run.status}
    stopping = request.app.state.workflows.stop(run_id)
    audit(db, cu, "workflow_stop_requested", f"run:{run_id}")
    db.commit()
    return {"stopping": stopping, "status": run.status}
