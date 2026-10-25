"""Runs workflows in the background so the board can watch progress live.

One active run per workspace at a time (a simple guard against accidental
double-spending). Each run has its own budget, call cap, handoff cap, and a
Stop button. Whatever happens, the run row ends with a final status,
duration, spend, and call count.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from sqlalchemy import select, update

from ..ai.llm import LLMService
from ..ai.router import BudgetExceededError, ModelRouter
from ..core.permissions import Permission
from ..db.models import AgentRun, Experiment
from ..safety.limits import effective_limits, load_overrides
from ..safety.manager import SafetyManager
from ..tools.catalog import build_tool_registry
from .orchestrator import Orchestrator
from .runtime import RunContext, RunStopped

ACTIVE = ("queued", "running")


class WorkflowManager:
    def __init__(self, app_state) -> None:
        self.state = app_state
        self._cancel: dict[int, threading.Event] = {}
        self._lock = threading.Lock()

    def mark_interrupted(self) -> None:
        """Runs left 'running' by a previous server process can never finish."""
        with self.state.db.transaction() as s:
            s.execute(update(AgentRun).where(AgentRun.status.in_(ACTIVE))
                      .values(status="failed", error="Interrupted: the server restarted.", finished_at=datetime.now(timezone.utc)))
            s.execute(update(Experiment).where(Experiment.status.in_(("queued", "running")))
                      .values(status="failed", error="Interrupted: the server restarted.", finished_at=datetime.now(timezone.utc)))

    def active_run(self, organization_id: int) -> int | None:
        with self.state.db.session() as s:
            return s.scalar(select(AgentRun.id).where(AgentRun.organization_id == organization_id, AgentRun.status.in_(ACTIVE)).limit(1))

    def start(self, run_id: int, *, user_id: int, organization_id: int, permissions: frozenset[Permission], strategy: str,
              research_mode: str, request: str, intent_hint: str | None, event_plan_id: int | None, synchronous: bool = False,
              options: dict | None = None) -> None:
        cancel = threading.Event()
        with self._lock:
            self._cancel[run_id] = cancel
        args = (run_id, user_id, organization_id, permissions, strategy, research_mode, request, intent_hint, event_plan_id, cancel,
                options or {})
        if synchronous:
            self._execute(*args)
        else:
            threading.Thread(target=self._execute, args=args, name=f"run-{run_id}", daemon=True).start()

    def stop(self, run_id: int) -> bool:
        with self._lock:
            event = self._cancel.get(run_id)
        if event:
            event.set()
        return event is not None

    def _execute(self, run_id, user_id, organization_id, permissions, strategy, research_mode, request, intent_hint, event_plan_id, cancel,
                 options) -> None:
        st = self.state
        settings = st.settings
        started = time.perf_counter()
        options = dict(options or {})
        fixtures = options.pop("_fixtures", None)  # server-side test fixtures only (research_mode "fixture"); never from the API
        # The central safety layer: limits from configuration and the board's settings, clamped to hard caps.
        limits = effective_limits(settings, load_overrides(st.db, organization_id))
        safety = SafetyManager(st.db, limits, organization_id=organization_id, user_id=user_id, run_id=run_id, cancel=cancel)
        budget = safety.new_budget()
        llm = LLMService(st.provider, st.db, limits.daily_budget_usd) if st.provider is not None else None
        ctx = RunContext(
            run_id=run_id, organization_id=organization_id, user_id=user_id, user_permissions=permissions, strategy=strategy,
            research_mode=research_mode, db=st.db, router=ModelRouter(settings.provider, st.availability.available),
            budget=budget, settings=settings, llm=llm, cancel=cancel, safety=safety, fixtures=fixtures,
        )
        ctx.tools = build_tool_registry(ctx)
        with st.db.transaction() as s:
            run = s.get(AgentRun, run_id)
            run.status = "running"
            run.budget_usd = limits.workflow_budget_usd

        status, error, result = "completed", None, None
        orchestrator = Orchestrator()
        try:
            result = orchestrator.run(ctx, request, intent_hint, event_plan_id, options)
            if result.get("verification") and not result["verification"]["passed"]:
                status = "completed_with_warnings"
        except (RunStopped, BudgetExceededError) as exc:
            status, error = "stopped", safety.redact(str(exc))
            safety.on_stop(error)
            result = orchestrator.partial_result(error)  # keep what was verified before the stop; never a fake success
        except Exception as exc:
            status, error = "failed", safety.redact(f"{type(exc).__name__}: {str(exc)[:400]}")
            result = orchestrator.partial_result(error)
        finally:
            with st.db.transaction() as s:
                run = s.get(AgentRun, run_id)
                run.status = status
                run.error = error
                run.result = result
                run.finished_at = datetime.now(timezone.utc)
                run.duration_ms = int((time.perf_counter() - started) * 1000)
                run.spent_usd = budget.spent_usd
                run.model_calls = budget.calls
            with self._lock:
                self._cancel.pop(run_id, None)
