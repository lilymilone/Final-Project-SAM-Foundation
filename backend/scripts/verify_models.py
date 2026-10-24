"""Check which configured models the API key can use.

    python -m backend.scripts.verify_models           # model list only (no tokens used)
    python -m backend.scripts.verify_models --probe   # also one tiny call per tier (a fraction of a cent)

Probe calls go through LLMService, so they are recorded in model_usage with
real token counts. Keys are never printed.
"""

from __future__ import annotations

import argparse

from backend.app.ai.availability import check_availability
from backend.app.ai.budget import WorkflowBudget
from backend.app.ai.llm import LLMService
from backend.app.ai.providers import AIProvider
from backend.app.ai.router import ModelRouter, TaskProfile
from backend.app.core.config import get_settings
from backend.app.db.database import Database

PROBES = [
    TaskProfile("system", "Model check: fast tier", "low", False, "low", 20, 20),
    TaskProfile("system", "Model check: intermediate tier", "medium", True, "low", 20, 20),
    TaskProfile("system", "Model check: advanced tier", "high", True, "high", 20, 20),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    print(f".env files loaded: {', '.join(settings.env_files_loaded) or 'none'}")
    print(f"Provider: {settings.provider or 'none'}")
    provider = AIProvider.from_settings(settings)
    availability = check_availability(provider)
    print(f"Availability check: {availability.status}" + (f" ({availability.error})" if availability.error else ""))
    for tier, info in availability.tier_models.items():
        print(f"  {tier:13s} preferred={info['preferred']:14s} effective={info['effective']}  {info.get('note') or ''}")

    if args.probe and provider is not None:
        db = Database(settings.database_path)
        db.initialize()
        llm = LLMService(provider, db, settings.daily_budget_usd)
        router = ModelRouter(provider.name, availability.available)
        budget = WorkflowBudget(limit_usd=0.05, max_calls=len(PROBES))
        for profile in PROBES:
            decision = router.select(profile, "auto", budget.remaining_usd)
            try:
                result = llm.call(decision=decision, instructions="Reply with exactly: ok", input="ok?",
                                  budget=budget, max_output_tokens=200, reasoning={"effort": "low"})
                print(f"  probe {decision.tier:13s} {decision.model:14s} -> {result.model_used} "
                      f"in={result.input_tokens} cached={result.cached_input_tokens} out={result.output_tokens} "
                      f"cost=${result.cost_usd:.6f} {result.latency_ms}ms  {decision.substitution_note or ''}")
            except Exception as exc:
                print(f"  probe {decision.tier:13s} {decision.model:14s} FAILED: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
