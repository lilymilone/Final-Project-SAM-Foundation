"""Per-user settings: butterfly animations and the AI Model Strategy."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...ai.router import STRATEGY_DESCRIPTIONS, Strategy
from ...core.config import Settings
from ..deps import CurrentUser, audit, current_user, get_db, get_settings_dep

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsIn(BaseModel):
    animations_enabled: bool | None = None
    model_strategy: Literal["auto", "economy", "balanced", "advanced"] | None = None


def settings_out(cu: CurrentUser, settings: Settings) -> dict:
    return {
        "animations_enabled": cu.user.animations_enabled,
        "model_strategy": cu.user.model_strategy,
        "strategies": [
            {"value": s.value, "label": s.value.title(), "description": STRATEGY_DESCRIPTIONS[s]} for s in Strategy
        ],
        "provider": settings.provider,
        "strategy_note": "The course Portkey key is active, so every strategy uses gpt-6-luna."
        if settings.provider == "portkey"
        else None,
    }


@router.get("")
def get_user_settings(cu: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings_dep)) -> dict:
    return settings_out(cu, settings)


@router.put("")
def update_user_settings(
    body: SettingsIn,
    cu: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> dict:
    user = cu.user
    changes = body.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(user, key, value)
    db.add(user)
    audit(db, cu, "settings_updated", **changes)
    db.commit()
    return settings_out(cu, settings)
