"""LLMService: the only path from agents to a model.

Each call:
  1. checks the workflow budget, call cap, and daily spend cap,
  2. calls the provider (backend only, Responses API, store=False),
  3. reads the token usage the API reports (input, cached input, output),
  4. prices it from pricing.json,
  5. writes one model_usage row (agent, models, reason, tokens, cost, time).

Token counts and costs are never made up: if the API omits usage, the fields
stay empty.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select

from ..db.database import Database
from ..db.models import ModelUsage
from .budget import WorkflowBudget
from .pricing import PriceTable, get_price_table
from .providers import AIProvider
from .router import BudgetExceededError, RoutingDecision


@dataclass(frozen=True)
class LLMResult:
    text: str
    decision: RoutingDecision
    model_used: str | None
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    latency_ms: int
    usage_id: int
    raw: Any = None


class LLMService:
    def __init__(self, provider: AIProvider, db: Database, daily_budget_usd: float, prices: PriceTable | None = None):
        self.provider = provider
        self.db = db
        self.daily_budget_usd = daily_budget_usd
        self.prices = prices or get_price_table()

    def spent_today_usd(self) -> float:
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        with self.db.session() as session:
            total = session.scalar(
                select(func.coalesce(func.sum(ModelUsage.estimated_cost_usd), 0.0)).where(ModelUsage.created_at >= start)
            )
        return float(total or 0.0)

    def call(
        self,
        *,
        decision: RoutingDecision,
        instructions: str,
        input: str | list[dict[str, Any]],
        budget: WorkflowBudget,
        run_id: int | None = None,
        max_output_tokens: int = 1200,
        **kwargs: Any,
    ) -> LLMResult:
        budget.check_call(decision.estimated_cost_usd)
        spent_today = self.spent_today_usd()
        if spent_today >= self.daily_budget_usd:
            self._record(decision, run_id, status="refused", error=f"Daily budget ${self.daily_budget_usd:.2f} reached.")
            raise BudgetExceededError(f"Stopped: the daily AI budget of ${self.daily_budget_usd:.2f} is used up.")

        started = time.perf_counter()
        try:
            response = self.provider.create_response(
                model=decision.model,
                instructions=instructions,
                input=input,
                max_output_tokens=max_output_tokens,
                store=False,
                **kwargs,
            )
        except Exception as exc:
            latency = int((time.perf_counter() - started) * 1000)
            self._record(decision, run_id, status="error", error=f"{type(exc).__name__}: {str(exc)[:300]}", latency_ms=latency)
            budget.record(None)
            raise
        latency = int((time.perf_counter() - started) * 1000)

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
        details = getattr(usage, "input_tokens_details", None)
        cached = getattr(details, "cached_tokens", None)
        cache_write = getattr(details, "cache_write_tokens", None)
        cost = None
        if input_tokens is not None and output_tokens is not None:
            cost = self.prices.cost_usd(decision.model, input_tokens, output_tokens, cached or 0, cache_write or 0)
        budget.record(cost)
        usage_id = self._record(
            decision,
            run_id,
            model_used=getattr(response, "model", None),
            input_tokens=input_tokens,
            cached_input_tokens=cached,
            cache_write_tokens=cache_write,
            output_tokens=output_tokens,
            estimated_cost_usd=cost,
            latency_ms=latency,
        )
        return LLMResult(
            text=getattr(response, "output_text", "") or "",
            decision=decision,
            model_used=getattr(response, "model", None),
            input_tokens=input_tokens,
            cached_input_tokens=cached,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=latency,
            usage_id=usage_id,
            raw=response,
        )

    def _record(self, decision: RoutingDecision, run_id: int | None, *, status: str = "ok", **fields: Any) -> int:
        row = ModelUsage(
            run_id=run_id,
            agent=decision.agent,
            task=decision.task,
            strategy=decision.strategy,
            provider=decision.provider,
            requested_tier=decision.requested_tier,
            selected_model=decision.model,
            selection_reason=decision.reason,
            substitution_note=decision.substitution_note,
            price_source=self.prices.source if self.prices.has_price(decision.model) else None,
            status=status,
            **fields,
        )
        with self.db.transaction() as session:
            session.add(row)
            session.flush()
            return row.id
