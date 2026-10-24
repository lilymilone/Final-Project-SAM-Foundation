"""Health check, configuration status, model routing, and safety policy.

These routes report which keys were found (true/false) and which .env files
were loaded ("repo", "parent"). They never return a key value.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ...agents.registry import AGENT_SPECS
from ...ai.catalog import PORTKEY_ALLOWED_MODEL, TIER_NAMES
from ...ai.pricing import get_price_table
from ...ai.router import STRATEGY_DESCRIPTIONS, ModelRouter, Strategy
from ...core.config import Settings
from ...db.models import SafetyTestResult
from ...safety.policy import ALLOWED_CAPABILITIES, PROHIBITED_ACTIONS
from ..deps import CurrentUser, current_user, get_db, get_settings_dep

VERSION = "0.1.0"
router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "error"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "app": "SAM SPACE",
        "version": VERSION,
        "database": database,
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def portkey_policy(settings: Settings) -> dict:
    return {
        "active": settings.provider == "portkey",
        "allowed_model": PORTKEY_ALLOWED_MODEL,
        "rule": "The course PORTKEY_API_KEY may only call gpt-6-luna. Sol and Astra are never attempted, "
                "escalation is disabled, and users cannot override it.",
    }


@router.get("/system/status")
def system_status(
    request: Request,
    _: CurrentUser = Depends(current_user),
    settings: Settings = Depends(get_settings_dep),
) -> dict:
    return {
        "provider": settings.provider,
        "provider_setting": settings.ai_provider_setting,
        "keys_detected": {"OPENAI_API_KEY": settings.has_openai_key, "PORTKEY_API_KEY": settings.has_portkey_key},
        "env_files_loaded": list(settings.env_files_loaded),
        "portkey_policy": portkey_policy(settings),
        "model_availability": request.app.state.availability.public(),
        "demo_mode": settings.demo_mode,
        "version": VERSION,
    }


@router.get("/models")
def models_overview(
    request: Request,
    strategy: str | None = Query(default=None),
    cu: CurrentUser = Depends(current_user),
    settings: Settings = Depends(get_settings_dep),
) -> dict:
    """Shows, without calling any model, which model each agent task would get."""
    chosen = strategy or cu.user.model_strategy
    availability = request.app.state.availability
    router_ = ModelRouter(settings.provider, availability.available)
    preview = []
    for spec in AGENT_SPECS:
        for profile in spec.typical_tasks:
            try:
                d = router_.select(profile, chosen, budget_remaining_usd=settings.workflow_budget_usd)
                preview.append({"agent": spec.display_name, **d.as_dict()})
            except Exception as exc:
                preview.append({"agent": spec.display_name, "task": profile.task, "error": str(exc)})
    return {
        "provider": settings.provider,
        "strategy": chosen,
        "strategies": [
            {"value": s.value, "label": s.value.title(), "description": STRATEGY_DESCRIPTIONS[s]} for s in Strategy
        ],
        "tier_names": TIER_NAMES,
        "tiers": availability.public()["tiers"],
        "availability_status": availability.status,
        "pricing": get_price_table().public_summary(),
        "portkey_policy": portkey_policy(settings),
        "routing_preview": preview,
        "routing_rule": "score = complexity (0-2) + 1 if multi-step reasoning + 1 if high risk; "
                        "the strategy maps the score to a tier; budget can step it down.",
    }


@router.get("/safety/policy")
def safety_policy(
    _: CurrentUser = Depends(current_user),
    settings: Settings = Depends(get_settings_dep),
    db: Session = Depends(get_db),
) -> dict:
    tests = db.scalars(select(SafetyTestResult).order_by(SafetyTestResult.ran_at.desc()).limit(50)).all()
    return {
        "prohibited_actions": [{"name": k, "label": v} for k, v in PROHIBITED_ACTIONS.items()],
        "allowed_capabilities": list(ALLOWED_CAPABILITIES),
        "limits": {
            "workflow_budget_usd": settings.workflow_budget_usd,
            "daily_budget_usd": settings.daily_budget_usd,
            "max_model_calls_per_workflow": settings.max_model_calls_per_workflow,
            "max_agent_iterations": settings.max_agent_iterations,
            "session_hours": settings.session_hours,
            "login_attempts": "5 failures per 15 minutes",
        },
        "portkey_policy": portkey_policy(settings),
        "safety_tests": [
            {"name": t.name, "category": t.category, "passed": t.passed, "observed": t.observed, "ran_at": t.ran_at.isoformat()}
            for t in tests
        ],
        "safety_tests_recorded": db.scalar(select(func.count(SafetyTestResult.id))) or 0,
    }
