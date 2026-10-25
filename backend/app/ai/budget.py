"""Spending guards: a per-workflow budget, a model-call cap, and a daily cap.

Before every paid call the caller reserves a conservatively bounded cost (the
worst case: estimated input tokens plus the full output-token allowance at
list price). The reservation is checked against what is spent AND what is
already reserved by calls in flight, under a lock, so concurrent calls cannot
slip past the limit together. After the call the reservation is settled with
the actual cost. Agents cannot raise their own limits.
"""

from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field

from .router import BudgetExceededError

_ids = itertools.count(1)


@dataclass
class WorkflowBudget:
    limit_usd: float
    max_calls: int
    spent_usd: float = 0.0
    calls: int = 0
    reserved_usd: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)
    _open: dict = field(default_factory=dict, repr=False, compare=False)
    refusals: int = 0

    @property
    def remaining_usd(self) -> float:
        """What a new call may still reserve: limit − spent − already reserved."""
        return max(0.0, round(self.limit_usd - self.spent_usd - self.reserved_usd, 8))

    def reserve(self, estimated_cost_usd: float | None) -> int:
        est = float(estimated_cost_usd or 0.0)
        with self._lock:
            if self.calls + len(self._open) >= self.max_calls:
                self.refusals += 1
                raise BudgetExceededError(f"Stopped: this workflow reached its limit of {self.max_calls} model calls.")
            available = round(self.limit_usd - self.spent_usd - self.reserved_usd, 8)
            if est > available:
                self.refusals += 1
                raise BudgetExceededError(
                    f"Stopped: the next call could cost up to ${est:.4f}, more than the ${max(0.0, available):.4f} left "
                    f"in this workflow's ${self.limit_usd:.2f} budget.")
            token = next(_ids)
            self._open[token] = est
            self.reserved_usd = round(self.reserved_usd + est, 8)
            return token

    def settle(self, token: int, actual_cost_usd: float | None) -> None:
        with self._lock:
            est = self._open.pop(token, 0.0)
            self.reserved_usd = max(0.0, round(self.reserved_usd - est, 8))
            self.calls += 1
            self.spent_usd = round(self.spent_usd + (actual_cost_usd or 0.0), 8)

    def release(self, token: int) -> None:
        """Drop a reservation for a call that never happened (nothing spent, no call counted)."""
        with self._lock:
            self.reserved_usd = max(0.0, round(self.reserved_usd - self._open.pop(token, 0.0), 8))

    # Older call sites (and tests) use check/record directly.
    def check_call(self, estimated_cost_usd: float | None) -> None:
        token = self.reserve(estimated_cost_usd)
        with self._lock:
            self.reserved_usd = max(0.0, round(self.reserved_usd - self._open.pop(token, 0.0), 8))

    def record(self, actual_cost_usd: float | None) -> None:
        with self._lock:
            self.calls += 1
            self.spent_usd = round(self.spent_usd + (actual_cost_usd or 0.0), 8)


class DailyGuard:
    """Process-wide daily cap that also counts calls in flight in every workflow."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._open: dict[int, float] = {}

    def reserve(self, spent_today_usd: float, daily_limit_usd: float, est: float) -> int:
        with self._lock:
            in_flight = sum(self._open.values())
            if spent_today_usd + in_flight + est > daily_limit_usd:
                raise BudgetExceededError(f"Stopped: the daily AI budget of ${daily_limit_usd:.2f} would be exceeded "
                                          f"(spent ${spent_today_usd:.4f}, in flight ${in_flight:.4f}).")
            token = next(_ids)
            self._open[token] = est
            return token

    def release(self, token: int) -> None:
        with self._lock:
            self._open.pop(token, None)


DAILY_GUARD = DailyGuard()
