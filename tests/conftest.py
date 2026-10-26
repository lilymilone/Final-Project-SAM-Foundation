from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.db.seed import DEMO_PASSWORD_DEFAULT
from backend.app.main import create_app

FAKE_OPENAI_KEY = "fake-openai-key-for-tests-111"
FAKE_PORTKEY_KEY = "fake-portkey-key-for-tests-222"
CHAIR = "chair@demo.samspace"
MEMBER = "member@demo.samspace"


@pytest.fixture(autouse=True)
def clean_model_env(monkeypatch):
    for name in ("MODEL_FAST", "MODEL_FAST_FALLBACK", "MODEL_INTERMEDIATE", "MODEL_INTERMEDIATE_FALLBACK",
                 "MODEL_ADVANCED", "MODEL_ADVANCED_FALLBACK", "DEMO_PASSWORD"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def make_client(tmp_path):
    def _make(provider: str = "openai", **overrides) -> TestClient:
        keys = {
            "openai": {"openai_api_key": FAKE_OPENAI_KEY},
            "portkey": {"portkey_api_key": FAKE_PORTKEY_KEY},
            "none": {},
        }[provider]
        settings = Settings(database_path=tmp_path / "test.db", **keys, **overrides)
        app = create_app(settings, verify_models=False)
        return TestClient(app, headers={"x-sam-request": "1"})

    return _make


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


def login(client: TestClient, email: str = CHAIR, password: str = DEMO_PASSWORD_DEFAULT):
    return client.post("/api/auth/login", json={"email": email, "password": password})


@pytest.fixture
def member_without_finance(monkeypatch):
    """Board members can read the finances. Tests of the guard for a role WITHOUT financial access (redaction, refused
    Finance steps, 403s) use this fixture, which takes that permission away from the member role for one test."""
    from backend.app.core.permissions import ROLE_PERMISSIONS, Permission, Role
    monkeypatch.setitem(ROLE_PERMISSIONS, Role.MEMBER, ROLE_PERMISSIONS[Role.MEMBER] - {Permission.VIEW_FINANCIALS})
