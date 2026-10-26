"""Prompt 6: Donations & Compliance, cross-agent financial decisions, privacy, routing, and usage logging.

Mocked: every model call here goes to the ScriptedClient (tests/fakes.py), so results are deterministic and no API is
called. Real model runs are recorded separately in docs/evidence/finance_donations/.
"""

from __future__ import annotations

import re

from sqlalchemy import select

from backend.app.agents.contracts import AgentName
from backend.app.agents.registry import AGENTS_BY_NAME
from backend.app.agents.specialists.donations_compliance import template_problems
from backend.app.core.security import hash_password
from backend.app.db.models import (AuditLog, BoardMembership, Donation, FinancialRecord, ModelUsage, Organization, OutreachDraft, User)
from backend.app.services import fin_calc as fc
from backend.app.services.finance_dashboard import build_dashboard

from .conftest import MEMBER, login
from .fakes import ScriptedClient
from .test_agents import gala_plan_id
from .test_mission import model_inputs, run_flow

DONATION_CSV = (b"donor_name,donation_date,amount_usd,contribution_type,payment_status,campaign,restriction,method,donor_email\n"
                b"Jordan Ellis (fictional),2026-10-20,\"$300.00\",monetary,received,Fall Community Appeal 2026 (sample),unrestricted,check,j@example.org\n"
                b"=cmd|' /C calc'!A0,2026-10-21,40,monetary,received,,,online,\n"
                b"Riley Park (fictional),2026-10-22,1500,sponsorship,pledged,Manhattan Spring Gala 2027 (sample),unrestricted,,\n")


def donations(client, query: str = "") -> dict:
    return client.get(f"/api/donations{query}").json()


def import_csv(client, data: bytes, name: str = "gifts.csv", **form):
    return client.post("/api/donations/import", files={"file": (name, data, "text/csv")}, data={k: str(v).lower() for k, v in form.items()})


# 2 + 3 ─ CSV donation import and duplicate detection ─────────────────────────────────


def test_donation_csv_import_with_campaigns_and_safe_cells(client):
    login(client)
    before = donations(client)["totals"]["count"]
    r = import_csv(client, DONATION_CSV)
    assert r.status_code == 201, r.text
    assert r.json()["imported"] == 3
    body = donations(client, "?search=fictional")
    rows = {d["donor_name"]: d for d in body["donations"]}
    jordan = rows["Jordan Ellis (fictional)"]
    assert jordan["campaign"] == "Fall Community Appeal 2026 (sample)" and jordan["source"] == "csv_import" and jordan["donor_id"].startswith("DNR-")
    assert jordan["amount_usd"] == 300 and jordan["has_email"] and "donor_email" not in jordan
    assert any(f["code"] == "ack_250" for f in jordan["flags"])
    riley = rows["Riley Park (fictional)"]
    assert riley["payment_status"] == "pledged" and any(f["code"] == "pledge" for f in riley["flags"])
    all_rows = donations(client)
    assert all_rows["totals"]["count"] == before + 3
    assert not any(d["donor_name"].startswith("=") for d in all_rows["donations"])  # formula neutralized
    # The pledge never counts as received money.
    assert all_rows["summary"]["pledged_outstanding_usd"] == 5000 + 1500
    bad = b"donor_name,donation_date,amount_usd,campaign\nA,10/20/2026,ten,No Such Campaign\n"
    r = import_csv(client, bad, "bad.csv")
    assert r.status_code == 422 and "donation_date" in r.json()["detail"] and "does not exist" in r.json()["detail"]
    assert import_csv(client, b"%PDF-1.4 not csv", "gifts.csv").status_code == 422
    assert donations(client)["totals"]["count"] == before + 3  # nothing partial was saved


def test_duplicate_donations_are_detected_and_never_double_counted(client):
    login(client)
    assert import_csv(client, DONATION_CSV).status_code == 201
    assert import_csv(client, DONATION_CSV, "same-file-again.csv").status_code == 409  # the same file
    overlap = (b"donor_name,donation_date,amount_usd\nJordan Ellis (fictional),2026-10-20,300\n")
    r = import_csv(client, overlap, "overlap.csv")
    assert r.status_code == 409 and "Nothing was imported" in r.json()["detail"]
    within = b"donor_name,donation_date,amount_usd\nA B,2026-10-01,10\nA B,2026-10-01,10\n"
    assert "appear earlier in this file" in import_csv(client, within, "within.csv").json()["detail"]
    gift = {"donor_name": "Jordan Ellis (fictional)", "received_on": "2026-10-20", "amount_usd": 300}
    assert client.post("/api/donations", json=gift).status_code == 409
    assert client.post("/api/donations", json={**gift, "confirm_duplicate": True}).status_code == 201
    body = donations(client)
    dupes = [d for d in body["donations"] if any(f["code"] == "possible_duplicate" for f in d["flags"])]
    assert len(dupes) >= 4  # the seeded pair and the confirmed pair are both flagged
    # Totals count each duplicate once: received = unique monetary, received gifts only.
    unique = {(d["donor_name"].lower(), d["received_on"], d["amount_usd"]) for d in body["donations"]
              if d["payment_status"] == "received" and d["contribution_type"] != "in_kind"}
    assert body["summary"]["received_usd"] == round(sum(a for _, _, a in unique), 2)
    assert body["summary"]["duplicates_excluded"] == 2


# 4 / 7 / 8 ─ totals, scenarios, and missing-data warnings ─────────────────────────────


def test_three_scenarios_never_count_pledged_sponsorship_as_guaranteed():
    s = fc.event_scenarios(attendance=100, ticket_price=150, donations_per_attendee=20, sponsorship_expected=5000,
                           sponsorship_confirmed=1000, other_revenue=500, total_cost=15000, target=4000)
    assert s["conservative"]["attendance"] == 80 and s["conservative"]["sponsorship_revenue_usd"] == 1000
    assert s["base"]["sponsorship_revenue_usd"] == 5000 and s["optimistic"]["sponsorship_revenue_usd"] == 7500
    assert s["base"]["total_revenue_usd"] == 100 * 150 + 5000 + 100 * 20 + 500 and s["base"]["net_usd"] == 7500
    assert s["conservative"]["donations_usd"] == 80 * 20 * 0.5 and s["base"]["vs_target_usd"] == 3500
    incomplete = fc.event_scenarios(attendance=100, ticket_price=None, donations_per_attendee=20, sponsorship_expected=0, total_cost=15000)
    assert incomplete["base"]["total_revenue_usd"] is None and incomplete["base"]["net_usd"] is None  # never guessed


def test_missing_information_is_stated_not_guessed():
    out = build_dashboard([], [], [], None)
    keys = {m["key"]: m for m in out["metrics"]}
    assert keys["revenue"]["display"] == "Not recorded" and keys["cash"]["display"] == "Not supplied"
    assert keys["capacity"]["display"] == "Not supported" and keys["capacity"]["value"] is None
    assert any("No income or expense records" in m for m in out["missing"]) and any("No cash balance" in m for m in out["missing"])
    assert any("No budget recorded" in m for m in out["missing"])


# 9 + 10 ─ "Can the foundation afford…?" across agents, with a revision ─────────────────


def test_affordability_question_drives_finance_feedback_and_a_revision(client):
    question = "Can the foundation afford a 150-person fundraising gala in Manhattan?"
    run, steps, fake = run_flow(client, question, plan_id=gala_plan_id(client.app))
    assert run.status == "completed", run.error
    assert run.result["intent"] == "plan_event"  # an affordability question about an event is planning, not a books review
    keys = [s.step_key for s in steps]
    assert keys[:4] == ["intake", "lessons", "venues", "finance"] and "evaluate" in keys and "venues_revision_1" in keys
    finance = next(s for s in steps if s.step_key == "finance")
    assert finance.result["status"] == "needs_revision" and finance.result["data"]["conflicts"]  # Finance reports back to the Orchestrator
    revision = next(s for s in steps if s.step_key == "venues_revision_1")
    assert revision.from_agent == "orchestrator" and revision.to_agent == "fundraising_events"
    constraint_names = {c["name"] for c in revision.payload["constraints"]}
    assert "max_total_usd" in constraint_names
    feedback = run.result["finance_feedback"][0]
    over = next(i for i in feedback["issues"] if i["type"] == "over_budget_limit")
    assert over["limit_usd"] == 18000 and over["over_by_usd"] > 0 and feedback["cost_drivers"][0]["share_of_total"] > 0
    sent = next(c for c in fake.schema_calls("EventStrategyOutput") if "finance_feedback\": {" in c["input"])
    assert "cost_drivers" in sent["input"]  # the Events agent received structured feedback, not "too expensive"
    comparison = run.result["proposal_comparison"]
    assert [c["label"] for c in comparison] == ["Original proposal", "Revision 1"]
    assert comparison[1]["total_usd"] < comparison[0]["total_usd"] and comparison[1]["change_in_total_usd"] < 0
    assert run.result["original_plan"]["venue"] != run.result["revised_plan"]["venue"]
    login(client)
    packet = client.get(f"/api/runs/{run.id}/packet").json()["packet"]
    assert packet["proposal_comparison"] == comparison and packet["finance_feedback"]
    assert "Structured feedback Finance sent" in client.get(f"/api/runs/{run.id}/packet.md").text


def test_a_request_without_an_authorized_budget_says_so(client):
    run, steps, _ = run_flow(client, "Can we afford a 120-person dinner in Manhattan?")
    assert run.result["intent"] == "plan_event" and run.result["authorized_budget_usd"] is None
    assert any("No explicitly authorized planning budget" in c for c in run.result["recommendation"]["caveats"])


# 11 + 12 ─ acknowledgment drafts, never sent ─────────────────────────────────────────


def test_acknowledgment_drafts_merge_verified_details_and_change_no_records(client):
    login(client)
    rows = {d["donation_id"]: d for d in donations(client)["donations"]}
    ticket = next(d for d in rows.values() if d["contribution_type"] == "event_ticket")
    in_kind = next(d for d in rows.values() if d["contribution_type"] == "in_kind")
    run, steps, fake = run_flow(client, "Draft thank-you letters", intent="donations_review",
                                options={"donation_ids": [ticket["id"], in_kind["id"]], "drafts_only": True})
    assert run.status == "completed", run.error
    assert "Sample Donor" not in model_inputs(fake) and not fake.schema_calls("DonationReview")  # drafts only: no review call
    with client.app.state.db.session() as s:
        drafts = s.scalars(select(OutreachDraft).where(OutreachDraft.run_id == run.id)).all()
        statuses = {d.id: (d.ack_status, d.acknowledged) for d in s.scalars(select(Donation).where(Donation.id.in_([ticket["id"], in_kind["id"]])))}
    thanks = [d for d in drafts if d.draft_type == "donor_thank_you"]
    formal = [d for d in drafts if d.draft_type == "contribution_acknowledgment"]
    assert len(thanks) == 2 and all(d.status == "draft" and "{{" not in d.body for d in thanks)
    ticket_letter = next(d for d in thanks if d.donation_id == ticket["id"])
    assert ticket["donor_name"] in ticket_letter.body and "your gift of $250.00" in ticket_letter.body
    assert "General thank-you letter, not a tax acknowledgment" in ticket_letter.review_notes[0]
    assert "your gift of floral arrangements" in next(d for d in thanks if d.donation_id == in_kind["id"]).body  # described, never valued
    assert "your gift of your gift" not in ticket_letter.body
    ticket_formal = next(d for d in formal if d.donation_id == ticket["id"])
    assert "DRAFT FOR ACCOUNTANT REVIEW" in ticket_formal.body and "$95.00" in ticket_formal.body
    assert "irs.gov" in ticket_formal.body and "United States (federal)" in ticket_formal.body
    assert "does not state a value" in next(d for d in formal if d.donation_id == in_kind["id"]).body
    assert statuses == {ticket["id"]: ("not_started", False), in_kind["id"]: ("not_started", False)}  # records untouched
    # Drafts can be edited and archived, never sent.
    r = client.put(f"/api/drafts/{ticket_letter.id}", json={"body": "Edited thank-you."})
    assert r.status_code == 200 and client.put(f"/api/drafts/{ticket_letter.id}", json={"status": "sent"}).status_code == 422
    assert ticket_letter.id in {d["id"] for d in client.get("/api/drafts?kind=donor").json()["drafts"]}


def test_templates_claiming_spending_or_tax_treatment_are_rejected(client):
    bad = "Dear {{donor_name}},\nYour gift funded our new program on {{date}}. {{gift}} is tax-deductible.\n[Board member name]"
    calls = {"n": 0}

    def ack(p, kw):
        calls["n"] += 1
        return {"summary": "x", "subject": "Thank you", "body": bad, "review_items": []}

    run, steps, _ = run_flow(client, "Draft thank-you letters", intent="donations_review", script=ScriptedClient({"AcknowledgmentTemplate": ack}),
                             options={"drafts_only": True})
    step = next(s for s in steps if s.to_agent == "donations_compliance")
    assert calls["n"] == 2 and any("No thank-you drafts were saved" in w for w in step.result["warnings"])
    with client.app.state.db.session() as s:
        assert not s.scalars(select(OutreachDraft).where(OutreachDraft.run_id == run.id, OutreachDraft.draft_type == "donor_thank_you")).all()
    problems = template_problems("Thanks", bad)
    assert any("spent" in p for p in problems) and any("tax" in p for p in problems)


def test_no_automatic_donor_outreach(client):
    tools = set(AGENTS_BY_NAME[AgentName.DONATIONS_COMPLIANCE].allowed_tools)
    assert not {t for t in tools if re.search(r"send|email|mail|notify|submit|file_", t)}
    assert not [r.path for r in client.app.routes if re.search(r"donation.*(send|email|notify|mail)|/send", getattr(r, "path", ""))]
    login(client)
    gift = donations(client)["donations"][0]
    r = client.post(f"/api/donations/{gift['id']}/acknowledgment", json={"status": "completed"})
    assert r.status_code == 200 and "did not send anything" in r.json()["note"]
    assert client.post(f"/api/donations/{gift['id']}/acknowledgment", json={"status": "sent"}).status_code == 422


# 13 ─ unauthorized and cross-workspace access ─────────────────────────────────────────


def _other_workspace(client) -> None:
    with client.app.state.db.transaction() as s:
        org = Organization(name="Another Foundation (test)", mission="test", is_demo=False)
        s.add(org)
        s.flush()
        user = User(email="chair@other.example", first_name="Other", last_name="Chair", password_hash=hash_password("other-pass-123"))
        s.add(user)
        s.flush()
        s.add(BoardMembership(user_id=user.id, organization_id=org.id, role="chair", title="Chair"))


def test_members_and_other_workspaces_cannot_reach_donor_or_financial_records(client, member_without_finance):
    login(client)
    gift_id = donations(client)["donations"][0]["id"]
    record_id = client.get("/api/finance/records").json()["records"][0]["id"]
    login(client, email=MEMBER)
    for method, path, body in (("get", "/api/donations", None), ("get", "/api/donations/export.csv", None), ("get", "/api/compliance", None),
                               ("post", "/api/donations", {"donor_name": "X", "received_on": "2026-10-01", "amount_usd": 5}),
                               ("put", f"/api/donations/{gift_id}", {"notes": "x"}), ("get", "/api/finance/records", None),
                               ("put", f"/api/finance/records/{record_id}", {"amount_usd": 1}), ("get", "/api/finance/documents", None)):
        r = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
        assert r.status_code == 403, (method, path, r.status_code)
    assert import_csv(client, DONATION_CSV).status_code == 403
    _other_workspace(client)
    assert client.post("/api/auth/login", json={"email": "chair@other.example", "password": "other-pass-123"}).status_code == 200
    assert donations(client)["donations"] == []  # a separate workspace sees none of the foundation's gifts
    assert client.put(f"/api/donations/{gift_id}", json={"notes": "x"}).status_code == 404
    assert client.post(f"/api/donations/{gift_id}/acknowledgment", json={"status": "completed"}).status_code == 404
    assert client.put(f"/api/finance/records/{record_id}", json={"amount_usd": 1}).status_code == 404
    assert client.get("/api/finance/dashboard").json()["metrics"][0]["display"] == "Not recorded"
    client.post("/api/auth/logout")
    assert client.get("/api/donations/export.csv").status_code == 401


def test_export_is_authorized_audited_and_formula_safe(client):
    login(client)
    assert client.post("/api/donations", json={"donor_name": "Avery Stone (fictional)", "received_on": "2026-10-23", "amount_usd": 60,
                                                "notes": "=HYPERLINK(\"http://x\")"}).status_code == 201
    csv_text = client.get("/api/donations/export.csv").text
    header = csv_text.splitlines()[0]
    assert header.startswith("donation_id,donor_id,donor_name") and "email" not in header
    assert "Avery Stone (fictional)" in csv_text and "\n=" not in csv_text and ",=" not in csv_text
    with client.app.state.db.session() as s:
        assert s.scalars(select(AuditLog).where(AuditLog.action == "donations_exported")).first() is not None


# 15 + 16 ─ routing and usage logging for the donations workflow ────────────────────────


def test_donation_review_routing_sources_and_usage_logging(client):
    run, steps, fake = run_flow(client, "Review our donations", intent="donations_review")
    assert run.status == "completed", run.error
    models = {c["text"]["format"]["name"]: c["model"] for c in fake.calls}
    assert models["DonationReview"] == "gpt-6.1-sol" and models["AcknowledgmentTemplate"] == "gpt-6-luna"
    assert "Sample Donor" not in model_inputs(fake) and "donor01@example.org" not in model_inputs(fake)
    review = next(s for s in steps if s.to_agent == "donations_compliance").result["data"]["review"]
    questions = {q["question"]: q for q in review["reporting_questions"]}
    owed = questions["Which acknowledgments are still owed for gifts of $250 or more?"]
    assert owed["kind"] == "verified_requirement" and owed["jurisdictions"] == ["United States (federal)"]
    assert questions["Must we register to solicit in New York?"]["jurisdictions"] == ["New York State"]
    step = next(s for s in steps if s.to_agent == "donations_compliance")
    assert any("Skipped 1 likely duplicate" in w for w in step.result["warnings"])  # one letter per gift
    pledges = questions["How should pledges be booked?"]  # cited a source that does not exist
    assert pledges["ref_ids"] == [] and pledges["kind"] == "needs_professional_review" and pledges["professional"] == "accountant"
    with client.app.state.db.session() as s:
        usage = s.scalars(select(ModelUsage).where(ModelUsage.run_id == run.id)).all()
    assert len(usage) == len(fake.calls)
    for u in usage:
        assert u.agent and u.selected_model and u.input_tokens and u.output_tokens is not None and u.cached_input_tokens is not None
        assert u.estimated_cost_usd > 0 and u.latency_ms is not None and u.handoff_id and u.status == "ok"


def test_portkey_keeps_finance_and_donation_work_on_luna(make_client):
    client = make_client("portkey")
    run, _, fake = run_flow(client, "Review our donations", intent="donations_review")
    run2, _, fake2 = run_flow(client, "Review our finances", intent="financial_review")
    assert {c["model"] for c in fake.calls + fake2.calls} == {"gpt-6-luna"}


# 17 ─ edited records persist ──────────────────────────────────────────────────────────


def test_edited_donation_and_financial_records_persist(client):
    login(client)
    gift = next(d for d in donations(client)["donations"] if d["contribution_type"] == "monetary")
    camp = donations(client)["campaigns"][2]["id"]
    r = client.put(f"/api/donations/{gift['id']}", json={"method": "check", "restriction": "temporarily_restricted", "campaign_id": camp,
                                                         "notes": "Corrected by the treasurer"})
    assert r.status_code == 200
    again = next(d for d in donations(client)["donations"] if d["id"] == gift["id"])
    assert (again["method"], again["restriction"], again["campaign_id"], again["notes"]) == ("check", "temporarily_restricted", camp,
                                                                                              "Corrected by the treasurer")
    assert again["updated_at"] is not None
    assert client.put(f"/api/donations/{gift['id']}", json={"donor_email": "x@y.z"}).status_code == 422  # unknown field
    rec = next(r for r in client.get("/api/finance/records").json()["records"] if r["kind"] == "expense")
    r = client.put(f"/api/finance/records/{rec['id']}", json={"amount_usd": 3333.33, "purpose": "event"})
    assert r.status_code == 200
    saved = next(x for x in client.get("/api/finance/records").json()["records"] if x["id"] == rec["id"])
    assert (saved["amount_usd"], saved["purpose"]) == (3333.33, "event") and saved["updated_at"]
    with client.app.state.db.session() as s:
        row = s.get(FinancialRecord, rec["id"])
        logged = s.scalars(select(AuditLog).where(AuditLog.action == "financial_record_edited")).first()
    assert row.amount_usd == 3333.33 and logged.detail == {"fields": ["amount_usd", "purpose"]}


def test_re_extracting_an_organized_document_needs_confirmation(client):
    from .pdfs import text_pdf
    from .test_finance import STATEMENT, upload
    login(client)
    doc = upload(client, text_pdf(STATEMENT), "s.pdf", "income_statement").json()["document"]
    run_flow(client, "Extract", intent="document_extraction", options={"document_id": doc["id"]})
    body = {"request": "Extract again", "intent": "document_extraction", "document_id": doc["id"]}
    assert client.post("/api/runs", json=body).status_code == 409  # no repeated paid calls for the same document
