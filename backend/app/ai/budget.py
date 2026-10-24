"""Spending guards: a per-workflow budget plus a cap on model calls.

Checked before every model call. Agents cannot raise their own limits.
"""

from __future__ import annotations

from dataclasses import dataclass

from .router import BudgetExceededError


@dataclass
class WorkflowBudget:
    limit_usd: float
    max_calls: int
    spent_usd: float = 0.0
    calls: int = 0

    @property
    def remaining_usd(self) -> float:
        return max(0.0, round(self.limit_usd - self.spent_usd, 8))

    def check_call(self, estimated_cost_usd: float | None) -> None:
        if self.calls >= self.max_calls:
            raise BudgetExceededError(f"Stopped: this workflow reached its limit of {self.max_calls} model calls.")
        if estimated_cost_usd is not None and estimated_cost_usd > self.remaining_usd:
            raise BudgetExceededError(
                f"Stopped: the next call (est. ${estimated_cost_usd:.4f}) exceeds the remaining "
                f"workflow budget (${self.remaining_usd:.4f})."
            )

    def record(self, actual_cost_usd: float | None) -> None:
        self.calls += 1
        self.spent_usd = round(self.spent_usd + (actual_cost_usd or 0.0), 8)
