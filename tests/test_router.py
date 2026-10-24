"""ModelRouter rules, the Portkey restriction, fallbacks, and budget limits."""

from __future__ import annotations

import pytest

from backend.app.ai.catalog import TierConfig
from backend.app.ai.providers import AIProvider, ProviderPolicyError
from backend.app.ai.router import (
    BudgetExceededError,
    ModelRouter,
    ModelUnavailableError,
    RoutingPolicyError,
    Strategy,
    TaskProfile,
)

ALL_MODELS = {"gpt-6-luna", "gpt-6.1-sol", "gpt-6-sol", "gpt-6-astra"}
SIMPLE = TaskProfile("partnerships_outreach", "Short draft", "low", False, "low", 1000, 300)
MEDIUM = TaskProfile("event_intelligence", "Synthesize feedback", "medium", True, "low", 4000, 800)
HARD = TaskProfile("orchestrator", "Board recommendation", "high", True, "high", 8000, 1500)
PROFILES = [SIMPLE, MEDIUM, HARD, TaskProfile("x", "y", "high", False, "medium")]


# --- Portkey: gpt-6-luna only, always -----------------------------------------


@pytest.mark.parametrize("strategy", list(Strategy))
@pytest.mark.parametrize("profile", PROFILES)
def test_portkey_always_uses_luna(strategy, profile):
    d = ModelRouter("portkey", ALL_MODELS).select(profile, strategy)
    assert d.model == "gpt-6-luna"
    assert d.provider == "portkey"
    assert d.escalation_allowed is False


def test_portkey_substitution_is_recorded_not_silent():
    d = ModelRouter("portkey").select(HARD, Strategy.ADVANCED)
    assert d.requested_model == "gpt-6-astra"
    assert d.substituted is True
    assert "not attempted" in d.substitution_note


def test_portkey_escalation_refused():
    router = ModelRouter("portkey")
    d = router.select(SIMPLE)
    with pytest.raises(RoutingPolicyError):
        router.escalate(d, SIMPLE, "draft was weak")


def test_portkey_client_blocks_other_models_even_without_router():
    class ExplodingClient:
        class responses:  # noqa: N801
            @staticmethod
            def create(**_):
                raise AssertionError("must not reach the network")

    provider = AIProvider("portkey", ExplodingClient())
    for model in ("gpt-6.1-sol", "gpt-6-astra", "gpt-6-sol"):
        with pytest.raises(ProviderPolicyError):
            provider.create_response(model=model, input="hi")


def test_portkey_env_override_cannot_unlock_other_models(monkeypatch):
    monkeypatch.setenv("MODEL_FAST", "gpt-6-astra")
    d = ModelRouter("portkey").select(SIMPLE)
    assert d.model == "gpt-6-luna"


# --- OpenAI routing table -------------------------------------------------------


def test_simple_task_uses_luna():
    assert ModelRouter("openai", ALL_MODELS).select(SIMPLE, "auto").model == "gpt-6-luna"


def test_medium_reasoning_task_uses_sol():
    assert ModelRouter("openai", ALL_MODELS).select(MEDIUM, "auto").model == "gpt-6.1-sol"


def test_hard_high_risk_task_uses_astra_under_auto():
    d = ModelRouter("openai", ALL_MODELS).select(HARD, "auto")
    assert d.model == "gpt-6-astra" and d.score == 4
    assert "Score 4" in d.reason


def test_economy_never_uses_astra():
    router = ModelRouter("openai", ALL_MODELS)
    for profile in PROFILES:
        assert router.select(profile, "economy").model != "gpt-6-astra"


def test_strategies_are_ordered_by_spend():
    router = ModelRouter("openai", ALL_MODELS)
    order = ["gpt-6-luna", "gpt-6.1-sol", "gpt-6-astra"]
    for profile in PROFILES:
        ranks = [order.index(router.select(profile, s).model) for s in ("economy", "balanced", "auto", "advanced")]
        assert ranks == sorted(ranks), profile


def test_escalation_moves_up_one_tier_with_reason():
    router = ModelRouter("openai", ALL_MODELS)
    d = router.select(SIMPLE, "auto")
    up = router.escalate(d, SIMPLE, "missing sources")
    assert up.model == "gpt-6.1-sol" and "missing sources" in up.reason


def test_unknown_strategy_and_missing_provider_rejected():
    with pytest.raises(RoutingPolicyError):
        ModelRouter("openai", ALL_MODELS).select(SIMPLE, "turbo")
    with pytest.raises(RoutingPolicyError):
        ModelRouter(None).select(SIMPLE)


# --- Availability + fallbacks ----------------------------------------------------


def test_unavailable_model_uses_configured_fallback_and_says_so():
    d = ModelRouter("openai", {"gpt-6-luna", "gpt-6-sol"}).select(MEDIUM, "auto")
    assert d.model == "gpt-6-sol" and d.requested_model == "gpt-6.1-sol"
    assert d.substituted and "fallback" in d.substitution_note


def test_unavailable_model_without_fallback_raises():
    tiers = {
        "fast": TierConfig("fast", "gpt-6-luna", None),
        "intermediate": TierConfig("intermediate", "gpt-6.1-sol", None),
        "advanced": TierConfig("advanced", "gpt-6-astra", None),
    }
    with pytest.raises(ModelUnavailableError):
        ModelRouter("openai", {"gpt-6-luna"}, tiers=tiers).select(HARD, "auto")


# --- Budget ---------------------------------------------------------------------


def test_budget_steps_down_tier_when_needed():
    router = ModelRouter("openai", ALL_MODELS)
    astra_cost = router.estimate_cost("gpt-6-astra", HARD)
    d = router.select(HARD, "auto", budget_remaining_usd=astra_cost / 2)
    assert d.model in ("gpt-6.1-sol", "gpt-6-luna")
    assert "stepped down" in d.reason and d.substituted


def test_budget_exhausted_raises():
    with pytest.raises(BudgetExceededError):
        ModelRouter("openai", ALL_MODELS).select(HARD, "auto", budget_remaining_usd=0.0000001)


def test_unpriced_model_refused_when_budget_enforced(monkeypatch):
    monkeypatch.setenv("MODEL_FAST", "some-unpriced-model")
    with pytest.raises(RoutingPolicyError):
        ModelRouter("openai", None).select(SIMPLE, "auto", budget_remaining_usd=1.0)
