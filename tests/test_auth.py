from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.app.core.security import hash_password, verify_password
from backend.app.db.models import AuthSession
from backend.app.db.seed import DEMO_PASSWORD_DEFAULT

from .conftest import CHAIR, login


def test_health_is_public(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["database"] == "ok"


def test_password_hashing():
    h1, h2 = hash_password("correct horse battery"), hash_password("correct horse battery")
    assert h1 != h2  # random salt
    assert "correct horse battery" not in h1
    assert verify_password("correct horse battery", h1)
    assert not verify_password("wrong", h1)
    assert not verify_password("anything", "garbage")


def test_protected_routes_need_login(client):
    for path in ("/api/overview", "/api/auth/me", "/api/finance/summary", "/api/donations", "/api/system/status"):
        assert client.get(path).status_code == 401, path


def test_login_sets_httponly_cookie_and_personalizes(client):
    r = login(client)
    assert r.status_code == 200
    assert r.json()["user"]["first_name"] == "Avery"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/api/overview").json()["first_name"] == "Avery"


def test_wrong_password_rejected(client):
    r = login(client, password="not-the-password")
    assert r.status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_session_token_is_stored_hashed(client):
    login(client)
    token = client.cookies.get("samspace_session")
    db = client.app.state.db
    with db.session() as s:
        stored = s.scalars(select(AuthSession.token_hash)).all()
    assert token and token not in stored


def test_logout_revokes_session(client):
    login(client)
    assert client.get("/api/auth/session").json()["user"]["first_name"] == "Avery"
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/session").json() == {"user": None}


def test_expired_session_rejected(client):
    login(client)
    with client.app.state.db.transaction() as s:
        for sess in s.scalars(select(AuthSession)):
            sess.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    r = client.get("/api/auth/me")
    assert r.status_code == 401 and "expired" in r.json()["detail"]


def test_login_rate_limited_after_five_failures(client):
    for _ in range(5):
        assert login(client, password="wrong-password").status_code == 401
    assert login(client, password=DEMO_PASSWORD_DEFAULT).status_code == 429


def test_state_changing_request_needs_same_origin_header(client):
    login(client)
    r = client.post("/api/events", json={"name": "Test"}, headers={"x-sam-request": ""})
    assert r.status_code == 403


def test_unknown_email_and_wrong_password_look_the_same(client):
    a = login(client, email="nobody@example.org", password="x")
    b = login(client, email=CHAIR, password="x")
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()
