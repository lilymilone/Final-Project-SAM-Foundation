"""Analytics & Safety: limits, the agent permission matrix, safety test results, and security events.

Everything shown comes from code or from logged records. The chair (manage_users) can change limits within the
hard caps and sees full event details; other board members see categories and counts only.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...agents.registry import AGENT_SPECS
from ...core.config import Settings
from ...core.permissions import Permission
from ...db.models import SafetySetting, SafetyTestResult, SecurityEvent
from ...safety.limits import LIMIT_SPECS, clamp, effective_limits, public
from ...safety.manager import CATEGORY_LABELS, DATA_SCOPES
from ...safety.policy import PROHIBITED_ACTIONS
from ...safety.risks import KNOWN_RISKS
from ...tools.catalog import TOOL_SCOPES
from ..deps import CurrentUser, audit, current_user, get_db, get_settings_dep, require

router = APIRouter(prefix="/api/safety", tags=["safety"])


def _overrides(db: Session, org: int) -> dict:
    return {r.key: r.value for r in db.scalars(select(SafetySetting).where(SafetySetting.organization_id == org))}


@router.get("/limits")
def get_limits(cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db), settings: Settings = Depends(get_settings_dep)) -> dict:
    limits = effective_limits(settings, _overrides(db, cu.organization_id))
    return {"limits": public(limits), "editable": Permission.MANAGE_USERS in cu.permissions,
            "note": "Limits apply to every new workflow. Hard caps can only be changed in code; agents cannot change any limit."}


class LimitsIn(BaseModel):
    limits: dict[str, float]


@router.put("/limits")
def set_limits(body: LimitsIn, cu: CurrentUser = Depends(require(Permission.MANAGE_USERS)), db: Session = Depends(get_db),
               settings: Settings = Depends(get_settings_dep)) -> dict:
    unknown = [k for k in body.limits if k not in LIMIT_SPECS]
    if unknown:
        raise HTTPException(422, f"Unknown limit: {', '.join(unknown)}")
    before = effective_limits(settings, _overrides(db, cu.organization_id)).as_dict()
    changes = {}
    for key, value in body.limits.items():
        v = clamp(key, value)
        row = db.scalar(select(SafetySetting).where(SafetySetting.organization_id == cu.organization_id, SafetySetting.key == key))
        if row is None:
            db.add(SafetySetting(organization_id=cu.organization_id, key=key, value=v, updated_by=cu.user.id))
        else:
            row.value, row.updated_by, row.updated_at = v, cu.user.id, datetime.now(timezone.utc)
        if before[key] != v:
            changes[key] = {"from": before[key], "to": v, "requested": value}
    audit(db, cu, "safety_limits_changed", **{k: f"{c['from']} -> {c['to']}" for k, c in changes.items()})
    if changes:
        db.add(SecurityEvent(organization_id=cu.organization_id, user_id=cu.user.id, category="limit_changed", severity="info",
                             defense="Board-controlled limits within hard caps",
                             detail="; ".join(f"{LIMIT_SPECS[k][0]}: {c['from']} → {c['to']}" + (" (clamped to the hard cap)" if c["to"] != c["requested"] else "")
                                              for k, c in changes.items())))
    db.commit()
    return {"limits": public(effective_limits(settings, _overrides(db, cu.organization_id))), "changed": changes}


def permission_matrix() -> dict:
    agents = []
    for spec in AGENT_SPECS:
        agents.append({"agent": spec.name.value, "name": spec.display_name, "purpose": spec.purpose,
                       "data_scopes": sorted(DATA_SCOPES[spec.name.value]),
                       "tools": [{"tool": t, "data_scope": TOOL_SCOPES.get(t, "general")} for t in spec.allowed_tools]})
    return {"agents": agents, "prohibited": [{"name": k, "label": v} for k, v in PROHIBITED_ACTIONS.items()],
            "notes": ["Only the Orchestrator delegates, in code; no agent has a delegation tool.",
                      "No agent has a shell, filesystem, general database, mail, payment, booking, or publishing tool.",
                      "A tool outside an agent's allow-list or data scope is refused in code and logged as a security event."]}


@router.get("/overview")
def overview(cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db), settings: Settings = Depends(get_settings_dep)) -> dict:
    admin = Permission.MANAGE_USERS in cu.permissions
    since = datetime.now(timezone.utc) - timedelta(days=30)
    rows = db.scalars(select(SecurityEvent).where(SecurityEvent.organization_id == cu.organization_id, SecurityEvent.created_at >= since)
                      .order_by(SecurityEvent.created_at.desc()).limit(500)).all()
    counts = Counter(r.category for r in rows)

    def ev(r: SecurityEvent) -> dict:
        out = {"id": r.id, "category": r.category, "label": CATEGORY_LABELS.get(r.category, r.category), "severity": r.severity,
               "agent": r.agent, "run_id": r.run_id, "defense": r.defense, "created_at": r.created_at.isoformat()}
        out["detail"] = r.detail if admin else "Details are visible to the chair."
        return out

    tests = db.scalars(select(SafetyTestResult).order_by(SafetyTestResult.ran_at.desc()).limit(200)).all()
    latest: dict[tuple, SafetyTestResult] = {}
    for t in tests:
        latest.setdefault((t.test_id or t.name, t.mode or "mocked"), t)
    def order(t: SafetyTestResult) -> tuple:  # TEST A, A2, B … then the regression checks; LIVE-A, LIVE-B … then LIVE-LEGIT
        label = t.name.split(":", 1)[0]
        return (t.mode or "", label in ("LEGIT", "MATRIX", "LIVE-LEGIT"), label)

    test_rows = sorted(latest.values(), key=order)
    return {
        "admin": admin,
        "limits": public(effective_limits(settings, _overrides(db, cu.organization_id))),
        "matrix": permission_matrix(),
        "tests": [{"name": t.name, "category": t.category, "mode": t.mode or "mocked", "passed": t.passed, "observed": t.observed,
                   "expected": t.expected, "defense": t.defense, "run_id": t.run_id, "ran_at": t.ran_at.isoformat()} for t in test_rows],
        "events": {"counts": {k: {"label": CATEGORY_LABELS.get(k, k), "count": v} for k, v in counts.most_common()},
                   "total_30_days": len(rows),
                   "blocked_actions": [ev(r) for r in rows if r.category in ("tool_denied", "prohibited_action", "url_blocked")][:15],
                   "budget": [ev(r) for r in rows if r.category in ("budget_limit", "budget_stepdown", "loop_limit", "time_limit", "tool_limit")][:15],
                   "injections": [ev(r) for r in rows if r.category == "injection_detected"][:15],
                   "data_access": [ev(r) for r in rows if r.category in ("permission_denied", "cross_workspace")][:15],
                   "other": [ev(r) for r in rows if r.category in ("upload_rejected", "output_rejected", "model_restricted", "limit_changed")][:15]},
        "risks": KNOWN_RISKS,
    }
