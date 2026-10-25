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
from typing import Any, TypeVar

from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select

from ..db.database import Database
from ..db.models import ModelUsage
from ..safety.redact import configured_secrets, redact
from .budget import DAILY_GUARD, WorkflowBudget
from .pricing import PriceTable, get_price_table
from .providers import AIProvider, ProviderPolicyError
from .router import BudgetExceededError, RoutingDecision


T = TypeVar("T", bound=BaseModel)


class SafeProviderError(RuntimeError):
    """A provider failure whose message has been redacted (no keys or tokens)."""


class StructuredOutputError(RuntimeError):
    """The model never produced output that passed Pydantic validation."""


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
    web_search_calls: int = 0
    status: str = "completed"
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
        handoff_id: int | None = None,
        attempt: int | None = None,
        max_output_tokens: int = 1200,
        **kwargs: Any,
    ) -> LLMResult:
        # Reserve a conservatively bounded cost before calling: worst-case input plus the full output allowance.
        worst = self.worst_case_cost(decision.model, instructions, input, max_output_tokens, kwargs.get("max_tool_calls"),
                                     bool(kwargs.get("tools")))
        try:
            token = budget.reserve(worst)
        except BudgetExceededError as exc:
            self._record(decision, run_id, handoff_id=handoff_id, attempt=attempt, status="refused", error=str(exc))
            raise
        spent_today = self.spent_today_usd()
        try:
            day_token = DAILY_GUARD.reserve(spent_today, self.daily_budget_usd, worst or 0.0)
        except BudgetExceededError as exc:
            budget.release(token)  # nothing was called
            self._record(decision, run_id, handoff_id=handoff_id, status="refused", error=str(exc))
            raise

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
        except ProviderPolicyError:
            budget.release(token)  # blocked before any API call
            DAILY_GUARD.release(day_token)
            self._record(decision, run_id, handoff_id=handoff_id, attempt=attempt, status="refused",
                         error=f"Blocked by provider policy: {decision.model} is not allowed with this key.")
            raise
        except Exception as exc:
            latency = int((time.perf_counter() - started) * 1000)
            self._record(decision, run_id, handoff_id=handoff_id, attempt=attempt, status="error",
                         error=redact(f"{type(exc).__name__}: {str(exc)[:300]}", configured_secrets()), latency_ms=latency)
            budget.settle(token, None)
            DAILY_GUARD.release(day_token)
            raise SafeProviderError(redact(f"{type(exc).__name__}: {str(exc)[:200]}", configured_secrets())) from None
        DAILY_GUARD.release(day_token)
        latency = int((time.perf_counter() - started) * 1000)

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
        details = getattr(usage, "input_tokens_details", None)
        cached = getattr(details, "cached_tokens", None)
        cache_write = getattr(details, "cache_write_tokens", None)
        searches = sum(1 for item in (getattr(response, "output", None) or []) if getattr(item, "type", "") == "web_search_call")
        cost = None
        if input_tokens is not None and output_tokens is not None:
            cost = self.prices.cost_usd(decision.model, input_tokens, output_tokens, cached or 0, cache_write or 0)
            if cost is not None:
                cost = round(cost + searches * self.prices.web_search_per_call, 8)
        budget.settle(token, cost if cost is not None else worst)  # unknown price: count the reserved worst case
        status = getattr(response, "status", "completed") or "completed"
        usage_id = self._record(
            decision,
            run_id,
            handoff_id=handoff_id,
            attempt=attempt,
            status="ok" if status == "completed" else status,
            web_search_calls=searches,
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
            web_search_calls=searches,
            status=status,
            raw=response,
        )

    def worst_case_cost(self, model: str, instructions: str, input: Any, max_output_tokens: int, max_tool_calls: int | None,
                        uses_tools: bool) -> float | None:
        """Upper bound for one call: input at ~3 characters per token (generous), the full output allowance,
        and, for hosted web search, extra context and the per-search fee for every allowed search."""
        chars = len(instructions or "") + len(input if isinstance(input, str) else str(input))
        in_tokens = chars // 3 + 200
        searches = (max_tool_calls or 2) if uses_tools else 0
        in_tokens += searches * 12000  # search results enter the context
        cost = self.prices.cost_usd(model, in_tokens, max_output_tokens)
        if cost is None:
            return None
        return round(cost + searches * self.prices.web_search_per_call, 6)

    def structured(
        self,
        *,
        decision: RoutingDecision,
        instructions: str,
        input: str,
        output_model: type[T],
        budget: WorkflowBudget,
        run_id: int | None = None,
        handoff_id: int | None = None,
        max_retries: int = 2,
        max_output_tokens: int = 6000,
        reasoning_effort: str = "low",
        tools: list[dict] | None = None,
        max_tool_calls: int | None = None,
    ) -> tuple[T, list[LLMResult]]:
        """Ask for JSON matching output_model (OpenAI strict JSON schema), then
        validate with Pydantic. Bounded retries: an invalid, cut-off, or
        unparsable reply is retried at most max_retries times, with the
        validation error fed back. Every attempt is recorded in model_usage."""
        fmt = {"type": "json_schema", "name": output_model.__name__, "schema": to_strict_json_schema(output_model), "strict": True}
        extra: dict[str, Any] = {"text": {"format": fmt}, "reasoning": {"effort": reasoning_effort}}
        if tools:
            extra["tools"] = tools
            if max_tool_calls is not None:
                extra["max_tool_calls"] = max_tool_calls
        attempts: list[LLMResult] = []
        feedback: str | None = None
        for attempt in range(1, max_retries + 2):
            prompt = input if feedback is None else (
                f"{input}\n\nYOUR PREVIOUS REPLY WAS REJECTED: {feedback}\nReply again with JSON that matches the schema exactly."
            )
            result = self.call(decision=decision, instructions=instructions, input=prompt, budget=budget, run_id=run_id,
                               handoff_id=handoff_id, attempt=attempt, max_output_tokens=max_output_tokens, **extra)
            attempts.append(result)
            if result.status != "completed":
                feedback = f"the reply was {result.status} (likely cut off). Be more concise."
                continue
            try:
                return output_model.model_validate_json(result.text), attempts
            except ValidationError as exc:
                problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:3])
                feedback = f"schema validation failed ({problems})"
        raise StructuredOutputError(
            f"{output_model.__name__}: no valid output after {len(attempts)} attempt(s). Last problem: {feedback}"
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
