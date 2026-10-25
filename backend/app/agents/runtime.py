"""Per-run context and the step log (handoffs, sources, usage).

The log stores what each agent was asked to do (objective, constraints), what
it returned (the validated AgentResult), how long it took, and any errors. It
never stores prompts, model instructions, or keys.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from ..ai.budget import WorkflowBudget
from ..ai.llm import LLMService
from ..ai.router import ModelRouter
from ..core.config import Settings
from ..core.permissions import Permission
from ..db.database import Database, as_utc
from ..db.models import AgentHandoff as HandoffRow
from ..db.models import ModelUsage, SourceRecordRow
from .contracts import AgentResult, AgentTask, SourceRecord, UsageSummary

if TYPE_CHECKING:
    from ..tools.registry import ToolRegistry


class RunStopped(RuntimeError):
    """The board stopped the run, or a loop/handoff limit was reached."""


@dataclass
class RunContext:
    run_id: int
    organization_id: int
    user_id: int
    user_permissions: frozenset[Permission]
    strategy: str
    research_mode: str  # "live" | "synthetic"
    db: Database
    router: ModelRouter
    budget: WorkflowBudget
    settings: Settings
    llm: LLMService | None
    tools: ToolRegistry | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    current_handoff_id: int | None = None
    counters: dict[str, int] = field(default_factory=lambda: {"handoffs": 0, "web_searches": 0, "page_fetches": 0})
    safety: Any = None  # SafetyManager (safety/manager.py)
    fixtures: dict | None = None  # research_mode "fixture": server-side test fixtures (venues and page HTML); never set from the API

    def check_cancelled(self) -> None:
        if self.cancel.is_set():
            raise RunStopped("Stopped by a board member.")
        if self.safety is not None:
            self.safety.check_duration()

    @property
    def max_web_searches(self) -> int:
        return self.safety.limits.max_web_searches if self.safety else self.settings.max_web_searches_per_run

    @property
    def max_page_fetches(self) -> int:
        return self.safety.limits.max_page_fetches if self.safety else self.settings.max_page_fetches_per_run

    @property
    def max_revisions(self) -> int:
        return self.safety.limits.max_revisions if self.safety else self.settings.max_revisions


def _now() -> datetime:
    return datetime.now(timezone.utc)


def open_handoff(ctx: RunContext, task: AgentTask, from_agent: str) -> int:
    payload = {
        "objective": task.objective,
        "kind": task.kind,
        "revision_round": task.revision_round,
        "constraints": [c.model_dump(mode="json") for c in task.constraints],
        "inputs_provided": sorted(task.inputs.keys()),
        "depends_on": task.depends_on,
    }
    history = {}  # organizational learning is traceable: which past events and lessons went into this step
    if task.inputs.get("relevant_events"):
        history["relevant_events"] = [{"id": r.get("id"), "name": r.get("name"), "reasons": r.get("reasons")}
                                      for r in task.inputs["relevant_events"]][:10]
    if task.inputs.get("lessons"):
        history["lessons"] = [{"id": l.get("id"), "text": str(l.get("text", ""))[:200], "event_ids": l.get("event_ids"),
                               "reflection_ids": l.get("reflection_ids")} for l in task.inputs["lessons"] if isinstance(l, dict)][:12]
    if task.inputs.get("contingency_pct") is not None:
        history["contingency_pct"] = task.inputs["contingency_pct"]
    if history:
        payload["history_passed"] = history
    with ctx.db.transaction() as s:
        row = HandoffRow(
            run_id=ctx.run_id, step_key=task.step_key, kind=task.kind, revision_round=task.revision_round,
            from_agent=from_agent, to_agent=task.agent.value, objective=task.objective, payload=payload,
            status="running", started_at=_now(),
        )
        s.add(row)
        s.flush()
        return row.id


def close_handoff(ctx: RunContext, handoff_id: int, result: AgentResult) -> None:
    with ctx.db.transaction() as s:
        row = s.get(HandoffRow, handoff_id)
        now = _now()
        row.status = result.status
        row.result = result.model_dump(mode="json")
        row.completed_at = now
        row.duration_ms = int((now - as_utc(row.started_at)).total_seconds() * 1000) if row.started_at else None
        row.error = result.summary if result.status in ("failed", "refused", "stopped") else None
        for src in result.sources:
            s.add(SourceRecordRow(
                run_id=ctx.run_id, handoff_id=handoff_id, source_key=src.id, url=src.url, title=src.title[:400],
                publisher=src.publisher, published=src.published, retrieved_at=src.retrieved_at,
                verification=src.verification, http_status=src.http_status, note=src.note,
            ))


def usage_for_handoff(db: Database, handoff_id: int) -> UsageSummary:
    with db.session() as s:
        row = s.execute(
            select(
                func.count(ModelUsage.id),
                func.coalesce(func.sum(ModelUsage.input_tokens), 0),
                func.coalesce(func.sum(ModelUsage.cached_input_tokens), 0),
                func.coalesce(func.sum(ModelUsage.output_tokens), 0),
                func.coalesce(func.sum(ModelUsage.web_search_calls), 0),
                func.coalesce(func.sum(ModelUsage.estimated_cost_usd), 0.0),
            ).where(ModelUsage.handoff_id == handoff_id)
        ).one()
        models = s.scalars(select(ModelUsage.selected_model).where(ModelUsage.handoff_id == handoff_id).distinct()).all()
    return UsageSummary(
        model_calls=row[0], input_tokens=row[1], cached_input_tokens=row[2], output_tokens=row[3],
        web_search_calls=row[4], cost_usd=round(float(row[5]), 6), models=list(models),
    )


def dedupe_sources(sources: list[SourceRecord]) -> list[SourceRecord]:
    seen: dict[str, SourceRecord] = {}
    for s in sources:
        seen.setdefault(s.id, s)
    return list(seen.values())


def compact(value: Any, limit: int = 60) -> Any:
    """Trim long lists before they go into a prompt (keeps token use bounded)."""
    if isinstance(value, list):
        return [compact(v, limit) for v in value[:limit]]
    if isinstance(value, dict):
        return {k: compact(v, limit) for k, v in value.items()}
    if isinstance(value, str) and len(value) > 1500:
        return value[:1500] + "…"
    return value
