"""Backend-only AI provider clients (official OpenAI Python SDK).

  openai  - api.openai.com with OPENAI_API_KEY. Any model the router picks.
  portkey - the course gateway, https://api.portkey.ai/v1, with PORTKEY_API_KEY
            as the bearer key and the header x-portkey-provider: openai.
            The client refuses every model except gpt-6-luna, so the course
            restriction holds even if a caller skips the router.

Checked on 2026-10-24: both configurations answered a Responses API call for
gpt-6-luna. Portkey reported the model as "gpt-6-luna-global".
"""

from __future__ import annotations

from typing import Any

from openai import OpenAI

from ..core.config import Settings
from .catalog import PORTKEY_ALLOWED_MODEL


class ProviderPolicyError(RuntimeError):
    """A call that the provider policy forbids (e.g. a non-Luna model on Portkey)."""


class AIProvider:
    def __init__(self, name: str, client: Any):
        if name not in ("openai", "portkey"):
            raise ValueError(f"Unknown provider {name!r}")
        self.name = name
        self._client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> AIProvider | None:
        provider = settings.provider
        if provider == "openai":
            return cls("openai", OpenAI(api_key=settings.openai_api_key, timeout=90, max_retries=2))
        if provider == "portkey":
            client = OpenAI(
                api_key=settings.portkey_api_key,
                base_url=settings.portkey_base_url,
                default_headers={"x-portkey-provider": "openai"},
                timeout=90,
                max_retries=2,
            )
            return cls("portkey", client)
        return None

    def check_model_allowed(self, model: str) -> None:
        if self.name == "portkey" and model != PORTKEY_ALLOWED_MODEL:
            raise ProviderPolicyError(
                f"Blocked: the course PORTKEY_API_KEY may only call {PORTKEY_ALLOWED_MODEL}, not {model}."
            )

    def create_response(self, *, model: str, **kwargs: Any) -> Any:
        self.check_model_allowed(model)
        return self._client.responses.create(model=model, **kwargs)

    def list_model_ids(self) -> set[str]:
        return {m.id for m in self._client.models.list()}
