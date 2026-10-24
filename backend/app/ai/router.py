"""ModelRouter: picks a model for each task by deterministic, auditable rules.

No model call is spent on choosing a model. The rule:

  score = complexity (low 0, medium 1, high 2)
        + 1 if the task needs multi-step reasoning
        + 1 if a wrong answer is high-risk (money, donors, final board advice)

  score:        0     1             2             3             4
  economy     fast  fast          fast          intermediate  intermediate
  balanced    fast  fast          intermediate  intermediate  advanced
  auto        fast  fast          intermediate  advanced      advanced
  advanced    fast  intermediate  advanced      advanced      advanced

Then:
  * Portkey (course key): always gpt-6-luna, escalation disabled. Any higher
    tier is recorded as a substitution and never attempted.
  * Unavailable preferred model: use the configured fallback and record it, or
    raise ModelUnavailableError. Never a silent swap.
  * Budget: if the estimated cost does not fit the remaining workflow budget,
    step down a tier (and say so). If even the fast tier does not fit, raise
    BudgetExceededError.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Literal

from .catalog import PORTKEY_ALLOWED_MODEL, TIER_NAMES, TIERS, TierConfig, tier_configs
from .pricing import PriceTable, get_price_table


class Strategy(str, Enum):
    AUTO = "auto"
    ECONOMY = "economy"
    BALANCED = "balanced"
    ADVANCED = "advanced"


ROUTING_TABLE: dict[Strategy, tuple[str, str, str, str, str]] = {
    Strategy.ECONOMY: ("fast", "fast", "fast", "intermediate", "intermediate"),
    Strategy.BALANCED: ("fast", "fast", "intermediate", "intermediate", "advanced"),
    Strategy.AUTO: ("fast", "fast", "intermediate", "advanced", "advanced"),
    Strategy.ADVANCED: ("fast", "intermediate", "advanced", "advanced", "advanced"),
}

STRATEGY_DESCRIPTIONS = {
    Strategy.AUTO: "Picks the right model for each task. Escalates for hard, high-stakes reasoning.",
    Strategy.ECONOMY: "Fast, low-cost models whenever possible. Never uses the advanced tier.",
    Strategy.BALANCED: "Efficient models for routine work. Advanced only for the hardest, riskiest tasks.",
    Strategy.ADVANCED: "Uses advanced reasoning more often, within the workflow budget.",
}

COMPLEXITY_POINTS = {"low": 0, "medium": 1, "high": 2}


class RoutingPolicyError(RuntimeError):
    """The request breaks a routing rule (no provider, Portkey escalation, ...)."""


class ModelUnavailableError(RuntimeError):
    """The preferred model is not available and no usable fallback is configured."""


class BudgetExceededError(RuntimeError):
    """The call would exceed the remaining workflow budget, even on the fast tier."""


@dataclass(frozen=True)
class TaskProfile:
    agent: str
    task: str
    complexity: Literal["low", "medium", "high"] = "low"
    reasoning: bool = False
    risk: Literal["low", "medium", "high"] = "low"
    expected_input_tokens: int = 1500
    expected_output_tokens: int = 500

    @property
    def score(self) -> int:
        return min(4, COMPLEXITY_POINTS[self.complexity] + int(self.reasoning) + int(self.risk == "high"))


@dataclass(frozen=True)
class RoutingDecision:
    agent: str
    task: str
    strategy: str
    provider: str
    score: int
    requested_tier: str
    requested_model: str
    tier: str
    model: str
    reason: str
    substituted: bool
    substitution_note: str | None
    estimated_cost_usd: float | None
    budget_remaining_usd: float | None
    escalation_allowed: bool
    availability_verified: bool

    def as_dict(self) -> dict:
        return asdict(self)


class ModelRouter:
    def __init__(
        self,
        provider: str | None,
        available_models: set[str] | None = None,
        tiers: dict[str, TierConfig] | None = None,
        prices: PriceTable | None = None,
    ):
        self.provider = provider
        self.available_models = available_models  # None = not verified yet
        self.tiers = tiers or tier_configs()
        self.prices = prices or get_price_table()

    # -- public ---------------------------------------------------------------

    def select(
        self,
        profile: TaskProfile,
        strategy: str | Strategy = Strategy.AUTO,
        budget_remaining_usd: float | None = None,
    ) -> RoutingDecision:
        strat = self._strategy(strategy)
        tier = ROUTING_TABLE[strat][profile.score]
        reason = (
            f"Score {profile.score} (complexity={profile.complexity}, reasoning={'yes' if profile.reasoning else 'no'}, "
            f"risk={profile.risk}) under {strat.value.title()} → {TIER_NAMES[tier]} ({tier}) tier."
        )
        return self._decide(profile, strat, tier, reason, budget_remaining_usd)

    def escalate(
        self,
        previous: RoutingDecision,
        profile: TaskProfile,
        why: str,
        budget_remaining_usd: float | None = None,
    ) -> RoutingDecision:
        """Move one tier up after a cheaper model could not do the task."""
        if not previous.escalation_allowed:
            raise RoutingPolicyError(
                f"Escalation is disabled for this call ({previous.provider}, {previous.strategy}, {previous.tier} tier)."
            )
        next_tier = TIERS[TIERS.index(previous.tier) + 1]
        strat = self._strategy(previous.strategy)
        reason = f"Escalated from {previous.model} ({previous.tier}) because: {why}"
        return self._decide(profile, strat, next_tier, reason, budget_remaining_usd)

    def estimate_cost(self, model: str, profile: TaskProfile) -> float | None:
        return self.prices.cost_usd(model, profile.expected_input_tokens, profile.expected_output_tokens)

    # -- internals ------------------------------------------------------------

    def _strategy(self, strategy: str | Strategy) -> Strategy:
        try:
            return Strategy(strategy)
        except ValueError as exc:
            raise RoutingPolicyError(f"Unknown model strategy: {strategy!r}") from exc

    def _decide(
        self, profile: TaskProfile, strat: Strategy, tier: str, reason: str, budget: float | None
    ) -> RoutingDecision:
        if self.provider is None:
            raise RoutingPolicyError("No AI provider is configured. Add OPENAI_API_KEY or PORTKEY_API_KEY to .env.")
        requested_tier = tier
        requested_model = self.tiers[tier].preferred

        if self.provider == "portkey":
            return self._portkey_decision(profile, strat, requested_tier, requested_model, reason, budget)

        reasons = [reason]
        while True:
            model, substituted, note = self._resolve(tier)
            estimate = self.estimate_cost(model, profile)
            if budget is None:
                break
            if estimate is None:
                raise RoutingPolicyError(
                    f"No verified price for {model}, so the workflow budget cannot be checked. Call refused."
                )
            if estimate <= budget:
                reasons.append(f"Estimated ${estimate:.4f} fits the remaining budget of ${budget:.4f}.")
                break
            index = TIERS.index(tier)
            if index == 0:
                raise BudgetExceededError(
                    f"Estimated ${estimate:.4f} for {model} exceeds the remaining workflow budget of ${budget:.4f}."
                )
            lower = TIERS[index - 1]
            reasons.append(
                f"Estimated ${estimate:.4f} for {model} exceeds the remaining budget of ${budget:.4f}; "
                f"stepped down to {TIER_NAMES[lower]} ({lower})."
            )
            tier = lower

        return RoutingDecision(
            agent=profile.agent,
            task=profile.task,
            strategy=strat.value,
            provider=self.provider,
            score=profile.score,
            requested_tier=requested_tier,
            requested_model=requested_model,
            tier=tier,
            model=model,
            reason=" ".join(reasons),
            substituted=substituted or model != requested_model,
            substitution_note=note
            or (None if model == requested_model else f"Budget limit: used {model} instead of {requested_model}."),
            estimated_cost_usd=estimate,
            budget_remaining_usd=budget,
            escalation_allowed=self._escalation_allowed(strat, tier),
            availability_verified=self.available_models is not None,
        )

    def _portkey_decision(
        self,
        profile: TaskProfile,
        strat: Strategy,
        requested_tier: str,
        requested_model: str,
        reason: str,
        budget: float | None,
    ) -> RoutingDecision:
        model = PORTKEY_ALLOWED_MODEL
        estimate = self.estimate_cost(model, profile)
        if budget is not None and estimate is not None and estimate > budget:
            raise BudgetExceededError(
                f"Estimated ${estimate:.4f} for {model} exceeds the remaining workflow budget of ${budget:.4f}."
            )
        substituted = requested_model != model
        note = (
            f"Course PORTKEY_API_KEY is restricted to {model}. The {TIER_NAMES[requested_tier]} tier "
            f"({requested_model}) was not attempted."
            if substituted
            else None
        )
        return RoutingDecision(
            agent=profile.agent,
            task=profile.task,
            strategy=strat.value,
            provider="portkey",
            score=profile.score,
            requested_tier=requested_tier,
            requested_model=requested_model,
            tier="fast",
            model=model,
            reason=f"{reason} Portkey course key: {model} only, escalation disabled.",
            substituted=substituted,
            substitution_note=note,
            estimated_cost_usd=estimate,
            budget_remaining_usd=budget,
            escalation_allowed=False,
            availability_verified=True,
        )

    def _resolve(self, tier: str) -> tuple[str, bool, str | None]:
        config = self.tiers[tier]
        if self.available_models is None or config.preferred in self.available_models:
            return config.preferred, False, None
        if config.fallback and config.fallback in self.available_models:
            return (
                config.fallback,
                True,
                f"{config.preferred} is not available on this API account. Using the configured fallback {config.fallback}.",
            )
        raise ModelUnavailableError(
            f"{config.preferred} ({tier} tier) is not available and no available fallback is configured."
        )

    def _escalation_allowed(self, strat: Strategy, tier: str) -> bool:
        if self.provider != "openai" or tier == TIERS[-1]:
            return False
        if strat is Strategy.ECONOMY and tier == "intermediate":
            return False  # Economy never reaches the advanced tier.
        return True
