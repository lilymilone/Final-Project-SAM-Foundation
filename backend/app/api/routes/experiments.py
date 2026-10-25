"""Controlled experiments: the same plan without and with historical insights.

Run A skips Event Intelligence. Run B consults it. Everything else (request,
event plan, research data, strategy) is identical. The runs execute one after
the other, and the comparison is computed in code from the stored results.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.config import Settings
from ...core.permissions import Permission
from ...db.models import AgentRun, EventPlan, Experiment
from ...services.comparison import compare_runs, comparison_markdown, run_snapshot
from ..deps import CurrentUser, audit, current_user, get_db, get_settings_dep, require

router = APIRouter(prefix="/api/experiments", tags=["experiments"])
DEFAULT_REQUEST = "Plan a 150-person Manhattan fundraising gala and check whether we can afford it."
FINANCE_KEYS = ("Projected total (USD)", "Upfront cash (USD)", "Contingency")


class HistoryABIn(BaseModel):
    request: str = Field(default=DEFAULT_REQUEST, min_length=5, max_length=2000)
    event_plan_id: int | None = None
    research_mode: Literal["synthetic", "live"] = "synthetic"


def experiment_out(e: Experiment, can_see_finance: bool) -> dict:
    out = {"id": e.id, "kind": e.kind, "request": e.request_text, "research_mode": e.research_mode, "run_a_id": e.run_a_id,
           "run_b_id": e.run_b_id, "status": e.status, "error": e.error, "created_at": e.created_at.isoformat(),
           "finished_at": e.finished_at.isoformat() if e.finished_at else None, "comparison": e.result}
    if e.result and not can_see_finance:
        comp = dict(e.result)
        comp["numbers"] = {k: v for k, v in comp["numbers"].items() if k not in FINANCE_KEYS}
        comp["summary_of_changes"] = [x for x in comp["summary_of_changes"] if "$" not in x or x.startswith("Extra cost")]
        comp.pop("runs", None)
        out["comparison"] = comp
    return out


def _execute(app_state, exp_id: int, user_id: int, org_id: int, permissions, strategy: str, mode: str, request: str, plan_id: int | None,
             run_a: int, run_b: int) -> None:
    wf = app_state.workflows
    db = app_state.db
    try:
        for run_id, use_history in ((run_a, False), (run_b, True)):
            wf.start(run_id, user_id=user_id, organization_id=org_id, permissions=permissions, strategy=strategy, research_mode=mode,
                     request=request, intent_hint="plan_event", event_plan_id=plan_id, synchronous=True,
                     options={"use_history": use_history})
        comparison = compare_runs(run_snapshot(db, run_a), run_snapshot(db, run_b))
        status_, error = "completed", None
    except Exception as exc:  # keep whatever finished; record the error
        comparison, status_, error = None, "failed", f"{type(exc).__name__}: {str(exc)[:300]}"
    with db.transaction() as s:
        exp = s.get(Experiment, exp_id)
        exp.status, exp.error, exp.result = status_, error, comparison
        exp.finished_at = datetime.now(timezone.utc)


@router.post("/history-ab", status_code=status.HTTP_202_ACCEPTED)
def start_history_ab(body: HistoryABIn, request: Request, cu: CurrentUser = Depends(require(Permission.RUN_AGENTS)),
                     db: Session = Depends(get_db), settings: Settings = Depends(get_settings_dep)) -> dict:
    if settings.provider is None:
        raise HTTPException(400, "No AI key is configured.")
    if request.app.state.workflows.active_run(cu.organization_id):
        raise HTTPException(409, "Another workflow is running. Try again when it finishes.")
    plan_id = body.event_plan_id
    if plan_id is None:
        plan_id = db.scalar(select(EventPlan.id).where(EventPlan.organization_id == cu.organization_id, EventPlan.is_demo.is_(True)).limit(1))
    elif (plan := db.get(EventPlan, plan_id)) is None or plan.organization_id != cu.organization_id:
        raise HTTPException(404, "Event plan not found.")
    runs = []
    for use_history in (False, True):
        run = AgentRun(organization_id=cu.organization_id, user_id=cu.user.id, workflow_type="plan_event", request_text=body.request,
                       status="queued", strategy=cu.user.model_strategy, provider=settings.provider, budget_usd=settings.workflow_budget_usd,
                       research_mode=body.research_mode, event_plan_id=plan_id, plan={"options": {"use_history": use_history}})
        db.add(run)
        db.flush()
        runs.append(run.id)
    exp = Experiment(organization_id=cu.organization_id, created_by=cu.user.id, kind="history_ab", request_text=body.request,
                     research_mode=body.research_mode, run_a_id=runs[0], run_b_id=runs[1], status="running")
    db.add(exp)
    db.flush()
    audit(db, cu, "experiment_started", f"experiment:{exp.id}", runs=runs)
    db.commit()
    threading.Thread(target=_execute, args=(request.app.state, exp.id, cu.user.id, cu.organization_id, cu.permissions,
                                            cu.user.model_strategy, body.research_mode, body.request, plan_id, runs[0], runs[1]),
                     name=f"experiment-{exp.id}", daemon=True).start()
    return {"experiment": experiment_out(exp, Permission.VIEW_FINANCIALS in cu.permissions)}


@router.get("")
def list_experiments(cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(Experiment).where(Experiment.organization_id == cu.organization_id).order_by(Experiment.created_at.desc()).limit(20)).all()
    return {"experiments": [experiment_out(e, Permission.VIEW_FINANCIALS in cu.permissions) for e in rows]}


@router.get("/{exp_id}")
def get_experiment(exp_id: int, cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    e = db.get(Experiment, exp_id)
    if e is None or e.organization_id != cu.organization_id:
        raise HTTPException(404, "Experiment not found.")
    return {"experiment": experiment_out(e, Permission.VIEW_FINANCIALS in cu.permissions)}


@router.get("/{exp_id}/report.md", response_class=PlainTextResponse)
def experiment_report(exp_id: int, cu: CurrentUser = Depends(require(Permission.VIEW_FINANCIALS)), db: Session = Depends(get_db)) -> str:
    e = db.get(Experiment, exp_id)
    if e is None or e.organization_id != cu.organization_id or not e.result:
        raise HTTPException(404, "Finished experiment not found.")
    return comparison_markdown(experiment_out(e, True))
