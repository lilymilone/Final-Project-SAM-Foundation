"""Role-based access: board members never see donor or financial records."""

from __future__ import annotations

from sqlalchemy import select

from backend.app.db.models import AuditLog

from .conftest import MEMBER, login


def test_member_blocked_from_financial_and_donor_data(client):
    assert login(client, email=MEMBER).status_code == 200
    assert client.get("/api/finance/summary").status_code == 403
    assert client.get("/api/donations").status_code == 403
    overview = client.get("/api/overview").json()
    assert overview["financial"]["restricted"] is True and overview["financial"]["flags"] == []


def test_denied_access_is_audited(client):
    login(client, email=MEMBER)
    client.get("/api/donations")
    with client.app.state.db.session() as s:
        actions = s.scalars(select(AuditLog.action)).all()
    assert "access_denied" in actions


def test_chair_sees_financials_with_computed_flags(client):
    login(client)
    body = client.get("/api/finance/summary").json()
    assert body["is_demo"] is True
    assert body["reserve_usd"] == 21500
    titles = [f["title"] for f in body["flags"]]
    assert "Months with a deficit" in titles


def test_donations_are_flagged_for_review_not_contacted(client):
    login(client)
    body = client.get("/api/donations").json()
    assert body["totals"]["count"] == 6
    assert all("donor_email" not in d for d in body["donations"])  # emails never leave the server
    flagged = [d for d in body["donations"] if d["flags"]]
    assert flagged, "demo data includes records that need attention"


def test_member_can_plan_events_and_write_reflections(client):
    login(client, email=MEMBER)
    r = client.post("/api/events", json={"name": "Autumn Walk", "city": "New Haven, CT", "status": "idea"})
    assert r.status_code == 201
    history = client.get("/api/legacy/events").json()["events"]
    r = client.post(f"/api/legacy/events/{history[0]['id']}/reflections", json={"went_well": "Great turnout", "rating": 5})
    assert r.status_code == 201
    assert r.json()["reflection"]["author"] == "Sam Rivera"


def test_event_validation(client):
    login(client)
    assert client.post("/api/events", json={"name": ""}).status_code == 422
    assert client.post("/api/events", json={"name": "Gala", "budget_limit_usd": -5}).status_code == 422
