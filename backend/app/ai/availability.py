"""Checks which models the configured API key can actually use.

OpenAI: the key's model list (GET /v1/models, which costs no tokens).
Portkey: gpt-6-luna only, by course policy. Nothing else is ever allowed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .catalog import PORTKEY_ALLOWED_MODEL, TIERS, tier_configs
from .providers import AIProvider


@dataclass
class ModelAvailability:
    provider: str | None
    status: str = "unverified"  # unverified | verified | policy | error | no_provider
    available: set[str] | None = None
    checked_at: str | None = None
    error: str | None = None
    tier_models: dict[str, dict] = field(default_factory=dict)

    def public(self) -> dict:
        return {
            "provider": self.provider,
            "status": self.status,
            "checked_at": self.checked_at,
            "error": self.error,
            "tiers": self.tier_models,
        }


def check_availability(provider: AIProvider | None) -> ModelAvailability:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if provider is None:
        return ModelAvailability(provider=None, status="no_provider", checked_at=now)
    if provider.name == "portkey":
        result = ModelAvailability(provider="portkey", status="policy", available={PORTKEY_ALLOWED_MODEL}, checked_at=now)
    else:
        try:
            ids = provider.list_model_ids()
            result = ModelAvailability(provider="openai", status="verified", available=ids, checked_at=now)
        except Exception as exc:  # network down, bad key, etc.
            return ModelAvailability(
                provider="openai", status="error", checked_at=now, error=f"{type(exc).__name__}: {str(exc)[:200]}"
            )
    result.tier_models = describe_tiers(result.provider, result.available)
    return result


def describe_tiers(provider: str | None, available: set[str] | None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for tier, config in tier_configs().items():
        if provider == "portkey":
            out[tier] = {
                "preferred": config.preferred,
                "effective": PORTKEY_ALLOWED_MODEL,
                "preferred_available": config.preferred == PORTKEY_ALLOWED_MODEL,
                "note": None if tier == TIERS[0] else "Not attempted: course Portkey key is gpt-6-luna only.",
            }
            continue
        preferred_ok = available is None or config.preferred in available
        fallback_ok = bool(config.fallback) and available is not None and config.fallback in available
        out[tier] = {
            "preferred": config.preferred,
            "fallback": config.fallback,
            "preferred_available": preferred_ok if available is not None else None,
            "effective": config.preferred if preferred_ok else (config.fallback if fallback_ok else None),
            "note": None
            if preferred_ok
            else (f"Using configured fallback {config.fallback}." if fallback_ok else "Unavailable: no fallback."),
        }
    return out
