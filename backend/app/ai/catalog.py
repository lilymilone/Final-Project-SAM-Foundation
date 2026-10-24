"""Model tiers: the preferred model for each tier, plus an explicit fallback.

Every model here was checked on 2026-10-24: it appeared in the OpenAI key's
model list and answered a test call through the Responses API. A fallback is
used only when the preferred model is missing from the verified list, and the
substitution is always recorded. Override any model in .env (see .env.example).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

TIERS: tuple[str, ...] = ("fast", "intermediate", "advanced")
TIER_NAMES = {"fast": "Luna", "intermediate": "Sol", "advanced": "Astra"}

# The course PORTKEY_API_KEY may only ever be used with this model.
PORTKEY_ALLOWED_MODEL = "gpt-6-luna"


@dataclass(frozen=True)
class TierConfig:
    tier: str
    preferred: str
    fallback: str | None


def _env(name: str, default: str | None) -> str | None:
    value = os.getenv(name, "").strip()
    return value or default


def tier_configs() -> dict[str, TierConfig]:
    return {
        "fast": TierConfig("fast", _env("MODEL_FAST", "gpt-6-luna"), _env("MODEL_FAST_FALLBACK", None)),
        "intermediate": TierConfig(
            "intermediate", _env("MODEL_INTERMEDIATE", "gpt-6.1-sol"), _env("MODEL_INTERMEDIATE_FALLBACK", "gpt-6-sol")
        ),
        "advanced": TierConfig(
            "advanced", _env("MODEL_ADVANCED", "gpt-6-astra"), _env("MODEL_ADVANCED_FALLBACK", "gpt-6.1-sol")
        ),
    }
