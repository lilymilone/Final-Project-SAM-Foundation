"""Role-based access: board members never see donor or financial records."""

from __future__ import annotations

from sqlalchemy import select

from backend.app.db.models import AuditLog

from .conftest import MEMBER, login


def test_member_blocked_from_financial_and_donor_data(client, member_without_finance):
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
    assert body["totals"]["count"] == 11  # fictional demo gifts, including a pledge, an in-kind gift, and a duplicate
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
    assert r.json()["reflection"]["author"] == "Ava Milone"


def test_event_validation(client):
    login(client)
    assert client.post("/api/events", json={"name": ""}).status_code == 422
    assert client.post("/api/events", json={"name": "Gala", "budget_limit_usd": -5}).status_code == 422


def test_ledger_csv_import_validates_and_feeds_finance(client):
    login(client)
    bad = "period,kind,category,amount_usd\n2026-13,income,Gifts,100\n2026-10,profit,X,abc\n"
    r = client.post("/api/finance/import", json={"csv_text": bad})
    assert r.status_code == 422 and "Line 2" in r.json()["detail"] and "Line 3" in r.json()["detail"]
    good = ("period,kind,category,amount_usd\n2026-10,income,=SUM(A1),4000\n2026-10,expense,Programs,\"3,000\"\n"
            "2026-11,income,Gifts,5000\n2026-11,expense,Programs,3500\n2026-12,income,Gifts,4500\n2026-12,expense,Programs,3200\n"
            "2026-12,reserve,Operating reserve,30000\n")
    r = client.post("/api/finance/import", json={"csv_text": good, "replace_demo": True})
    assert r.status_code == 200 and r.json()["imported"] == 7 and r.json()["replaced_demo_rows"] > 0
    summary = client.get("/api/finance/summary").json()
    assert summary["is_demo"] is False and summary["reserve_usd"] == 30000
    assert [m["period"] for m in summary["months"]] == ["2026-10", "2026-11", "2026-12"]


def test_member_cannot_import_ledger(client):
    login(client, email=MEMBER)
    assert client.post("/api/finance/import", json={"csv_text": "period,kind,category,amount_usd\n"}).status_code == 403


def test_overview_never_lists_donor_drafts(client):
    """Donor acknowledgment drafts carry donor names: the dashboard lists outreach drafts only, for every role."""
    from backend.app.api.routes.outputs import DONOR_DRAFTS
    from backend.app.db.models import OutreachDraft
    with client.app.state.db.session() as s:
        s.add(OutreachDraft(organization_id=1, draft_type="donor_thank_you", recipient_name="Private Donor (fictional)", recipient_org="",
                            subject="Thank you, Private Donor", body="x", status="draft"))
        s.commit()
    for email in (None, MEMBER):
        if email:
            client.post("/api/auth/logout")
        assert login(client, **({"email": email} if email else {})).status_code == 200
        overview = client.get("/api/overview").json()
        assert all(d["draft_type"] not in DONOR_DRAFTS for d in overview["drafts_awaiting_review"])
        assert "Private Donor" not in str(overview)


def test_members_can_read_finances_but_not_change_them_or_see_donors(client):
    """Board members see the finances, so Financial Analysis can check affordability for them. Uploading or editing
    financial records stays with the chair and treasurer, and donor records stay private."""
    assert login(client, email=MEMBER).status_code == 200
    assert client.get("/api/finance/dashboard").status_code == 200
    assert client.get("/api/finance/summary").status_code == 200
    overview = client.get("/api/overview").json()
    assert overview["financial"]["restricted"] is False
    assert client.post("/api/finance/records", json={"period": "2026-01", "kind": "expense", "category": "test", "amount_usd": 1}).status_code == 403
    assert client.get("/api/donations").status_code == 403
    me = client.get("/api/auth/me").json()
    assert "view_financials" in me["user"]["permissions"] and "manage_financials" not in me["user"]["permissions"]
    assert "view_donor_data" not in me["user"]["permissions"]
