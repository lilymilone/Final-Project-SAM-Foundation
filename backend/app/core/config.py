"""Runtime settings, read from the environment after the .env files are loaded.

API keys live only here, on the backend. They are excluded from repr() and are
never returned by any route, logged, or sent to the browser.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .env import REPO_ROOT, load_environment

VALID_PROVIDER_SETTINGS = ("auto", "openai", "portkey")


def _str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    env_files_loaded: tuple[str, ...] = ()
    ai_provider_setting: str = "auto"
    openai_api_key: str = field(default="", repr=False)
    portkey_api_key: str = field(default="", repr=False)
    portkey_base_url: str = "https://api.portkey.ai/v1"
    database_path: Path = REPO_ROOT / "backend" / "data" / "sam_space.db"
    session_hours: float = 8.0
    workflow_budget_usd: float = 0.50
    daily_budget_usd: float = 5.00
    max_model_calls_per_workflow: int = 20
    max_agent_iterations: int = 8
    demo_mode: bool = True
    cookie_secure: bool = False
    verify_models_on_startup: bool = True

    @property
    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def has_portkey_key(self) -> bool:
        return bool(self.portkey_api_key)

    @property
    def provider(self) -> str | None:
        """The provider actually used: 'openai', 'portkey', or None if no key."""
        setting = self.ai_provider_setting
        if setting == "openai":
            return "openai" if self.has_openai_key else None
        if setting == "portkey":
            return "portkey" if self.has_portkey_key else None
        if self.has_openai_key:
            return "openai"
        if self.has_portkey_key:
            return "portkey"
        return None


def settings_from_env(load_files: bool = True) -> Settings:
    loaded = load_environment() if load_files else ()
    provider = _str("AI_PROVIDER", "auto").lower()
    if provider not in VALID_PROVIDER_SETTINGS:
        provider = "auto"
    db_path = _str("DATABASE_PATH")
    return Settings(
        env_files_loaded=loaded,
        ai_provider_setting=provider,
        openai_api_key=_str("OPENAI_API_KEY"),
        portkey_api_key=_str("PORTKEY_API_KEY"),
        portkey_base_url=_str("PORTKEY_BASE_URL", "https://api.portkey.ai/v1").rstrip("/"),
        database_path=Path(db_path) if db_path else Settings.database_path,
        session_hours=_float("SESSION_HOURS", 8.0),
        workflow_budget_usd=_float("WORKFLOW_BUDGET_USD", 0.50),
        daily_budget_usd=_float("DAILY_BUDGET_USD", 5.00),
        max_model_calls_per_workflow=_int("MAX_MODEL_CALLS_PER_WORKFLOW", 20),
        max_agent_iterations=_int("MAX_AGENT_ITERATIONS", 8),
        demo_mode=_bool("SAM_DEMO_MODE", True),
        cookie_secure=_bool("COOKIE_SECURE", False),
        verify_models_on_startup=_bool("VERIFY_MODELS_ON_STARTUP", True),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return settings_from_env()
