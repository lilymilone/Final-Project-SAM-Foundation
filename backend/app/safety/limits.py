"""Workflow safety limits: defaults from configuration, board-adjustable, always clamped to hard caps.

The chair can tighten or loosen a limit in Analytics & Safety, but never past
HARD_CAPS, which only a code change can move. Agents have no way to change a
limit: there is no tool for it, and the values are read once per workflow.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# key: (label, minimum, hard cap, kind)
LIMIT_SPECS: dict[str, tuple[str, float, float, str]] = {
    "workflow_budget_usd": ("Spending limit per workflow (USD)", 0.01, 2.00, "usd"),
    "daily_budget_usd": ("Daily AI spending limit (USD)", 0.05, 20.00, "usd"),
    "max_model_calls": ("Model calls per workflow", 1, 40, "int"),
    "max_handoffs": ("Orchestrator steps (handoffs) per workflow", 2, 20, "int"),
    "max_tool_calls": ("Tool calls per workflow", 5, 200, "int"),
    "max_retries": ("Retries per model step", 0, 3, "int"),
    "max_output_tokens": ("Output tokens per model call", 500, 16000, "int"),
    "max_workflow_seconds": ("Workflow duration (seconds)", 30, 900, "int"),
    "max_revisions": ("Revision rounds per plan", 0, 2, "int"),
    "max_web_searches": ("Web searches per workflow", 0, 10, "int"),
    "max_page_fetches": ("Page fetches per workflow", 0, 25, "int"),
    "max_contact_pages": ("Contact pages read per outreach draft", 0, 3, "int"),  # separate, so research cannot use them up
}


@dataclass(frozen=True)
class SafetyLimits:
    workflow_budget_usd: float
    daily_budget_usd: float
    max_model_calls: int
    max_handoffs: int
    max_tool_calls: int
    max_retries: int
    max_output_tokens: int
    max_workflow_seconds: int
    max_revisions: int
    max_web_searches: int
    max_page_fetches: int
    max_contact_pages: int

    def as_dict(self) -> dict:
        return asdict(self)


def clamp(key: str, value: float) -> float:
    _, lo, hi, kind = LIMIT_SPECS[key]
    v = min(max(float(value), lo), hi)
    return int(round(v)) if kind == "int" else round(v, 2)


def defaults(settings) -> dict:
    return {
        "workflow_budget_usd": settings.workflow_budget_usd, "daily_budget_usd": settings.daily_budget_usd,
        "max_model_calls": settings.max_model_calls_per_workflow, "max_handoffs": settings.max_handoffs_per_run,
        "max_tool_calls": getattr(settings, "max_tool_calls_per_run", 120), "max_retries": 2, "max_output_tokens": 12000,
        "max_workflow_seconds": getattr(settings, "max_workflow_seconds", 480), "max_revisions": settings.max_revisions,
        "max_web_searches": settings.max_web_searches_per_run, "max_page_fetches": settings.max_page_fetches_per_run,
        "max_contact_pages": getattr(settings, "max_contact_pages_per_draft", 2),
    }


def effective_limits(settings, overrides: dict | None = None) -> SafetyLimits:
    """Configured defaults, replaced by board overrides, every value clamped to its hard cap."""
    values = defaults(settings)
    for k, v in (overrides or {}).items():
        if k in LIMIT_SPECS and v is not None:
            values[k] = v
    return SafetyLimits(**{k: clamp(k, v) for k, v in values.items()})


def load_overrides(db, organization_id: int) -> dict:
    from sqlalchemy import select
    from ..db.models import SafetySetting
    with db.session() as s:
        return {r.key: r.value for r in s.scalars(select(SafetySetting).where(SafetySetting.organization_id == organization_id))}


def public(limits: SafetyLimits) -> list[dict]:
    return [{"key": k, "label": LIMIT_SPECS[k][0], "value": v, "minimum": LIMIT_SPECS[k][1], "hard_cap": LIMIT_SPECS[k][2],
             "kind": LIMIT_SPECS[k][3]} for k, v in limits.as_dict().items()]
