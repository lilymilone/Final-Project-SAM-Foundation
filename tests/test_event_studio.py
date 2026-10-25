"""Event Studio: the five required scenarios, plus recalculation, packets, and live-venue honesty."""

from __future__ import annotations

from sqlalchemy import delete, select

from backend.app.agents.runtime import RunContext
from backend.app.agents.specialists.fundraising_events import FundraisingEventsAgent, _verify_live_venue
from backend.app.ai.budget import WorkflowBudget
from backend.app.ai.providers import AIProvider
from backend.app.ai.router import ModelRouter
from backend.app.core.permissions import permissions_for
from backend.app.db.models import AgentHandoff, AgentRun, FinancialRecord, OutreachDraft
from backend.app.services import event_model as em
from backend.app.services.packet import build_packet, packet_markdown
from backend.app.tools import web
from backend.app.tools.catalog import build_tool_registry

from .conftest import MEMBER, login
from .fakes import ScriptedClient
from .test_agents import gala_plan_id


def make_plan(client, **fields) -> int:
    login(client)
    body = {"name": "Test fundraiser", "event_type": "gala", "city": "Manhattan, New York, NY", "expected_attendance": 150,
            "ticket_price_usd": 250, "fundraising_goal_usd": 40000, "budget_limit_usd": 18000, "status": "planning", **fields}
    r = client.post("/api/events", json=body)
    assert r.status_code == 201, r.text
    return r.json()["event"]["id"]


def run_plan(client, plan_id: int, *, script=None, use_history=True, role="chair"):
    app = client.app
    fake = script or ScriptedClient()
    app.state.provider = AIProvider("openai", fake)
    with app.state.db.transaction() as s:
        run = AgentRun(organization_id=1, user_id=1, workflow_type="plan_event", request_text="Generate an event strategy",
                       status="queued", strategy="auto", provider="openai", budget_usd=0.5, research_mode="synthetic", event_plan_id=plan_id,
                       plan={"options": {"use_history": use_history, "interpret": True}})
        s.add(run)
        s.flush()
        run_id = run.id
    app.state.workflows.start(run_id, user_id=1, organization_id=1, permissions=permissions_for(role), strategy="auto",
                              research_mode="synthetic", request="Generate an event strategy for this plan", intent_hint="plan_event",
                              event_plan_id=plan_id, synchronous=True, options={"use_history": use_history, "interpret": True})
    with app.state.db.session() as s:
        run = s.get(AgentRun, run_id)
        steps = s.scalars(select(AgentHandoff).where(AgentHandoff.run_id == run_id).order_by(AgentHandoff.id)).all()
    return run, steps, fake


def pick(first: str, revision_rule: str = "cheapest_fitting"):
    """Scripted Events model: choose a specific venue first; on revision choose by rule."""
    base = ScriptedClient().handlers["EventStrategyOutput"]

    def handler(p, kw):
        out = base(p, kw)
        if not p.get("constraints") or not any(c["name"] in ("max_total_usd", "avoid_catering_minimum_risk") for c in p["constraints"]):
            chosen = next(o for o in p["options"] if first in o["option_id"])
            out["shortlist"] = [{"option_id": chosen["option_id"], "rank": 1, "rationale": "Scripted choice.", "lessons_applied": []}]
        return out
    return handler


# 1 ─ An affordable event ──────────────────────────────────────────────────────────


def test_affordable_event_needs_no_revision(client):
    pid = make_plan(client, name="Spring reception", event_type="reception", event_format="reception", expected_attendance=100,
                    ticket_price_usd=150, fundraising_goal_usd=3000, budget_limit_usd=25000)
    # Pledged sponsorship is never guaranteed: without any confirmed sponsorship the conservative case loses money.
    run0, _, _ = run_plan(client, pid, script=ScriptedClient({"EventStrategyOutput": pick("chelsea")}))
    m0 = run0.result["finance"]["model"]
    assert run0.result["finance"]["verdict"] == "affordable_with_conditions"
    assert m0["scenarios"]["conservative"]["sponsorship_revenue_usd"] == 0 and m0["scenarios"]["conservative"]["net_usd"] < 0
    assert m0["sponsorship_confirmed_usd"] == 0 and m0["break_even_confirmed_only"] >= m0["break_even_attendance"]
    # Once the board records $3,000 of signed sponsorship, the conservative case covers its costs.
    assert client.put(f"/api/events/{pid}/assumptions", json={"assumptions": {"sponsorship_confirmed_usd": 3000}}).status_code == 200
    run, steps, _ = run_plan(client, pid, script=ScriptedClient({"EventStrategyOutput": pick("chelsea")}))
    keys = [s.step_key for s in steps]
    assert run.status == "completed", run.error
    assert keys == ["intake", "lessons", "venues", "finance", "evaluate", "outreach_decision", "outreach", "recommendation", "verification"]
    assert run.result["finance"]["verdict"] == "affordable"
    assert run.result["revised_plan"] is None and run.result["revision_reasons"] == []
    model = run.result["finance"]["model"]
    assert model["total_cost_usd"] == 12765.0 and model["scenarios"]["conservative"]["net_usd"] > 0
    # No past reception exists, so history falls back to all events, and donations above the ticket price come to $0.
    assert model["assumptions"]["donations_per_attendee_usd"]["value"] == 0.0


# 2 ─ An over-budget event that requires a revision ─────────────────────────────────


def test_over_budget_event_is_revised_and_packet_explains_why(client):
    login(client)
    run, steps, _ = run_plan(client, gala_plan_id(client.app))
    assert run.result["original_plan"]["verdict"] == "not_affordable_as_planned"
    assert run.result["revised_plan"]["venue"] == "Chelsea Atelier (synthetic)"
    reasons = {r["type"] for r in run.result["revision_reasons"]}
    assert {"over_budget_limit", "upfront_cash_exceeds_available"} <= reasons
    packet = client.get(f"/api/runs/{run.id}/packet").json()["packet"]
    assert packet["revision"]["original"]["total_usd"] > 18000 >= packet["revision"]["revised"]["total_usd"]
    assert packet["drafts"] and all(d["status"] == "draft" for d in packet["drafts"])
    assert {d["recipient"] for d in packet["drafts"]} <= {v["name"] for v in packet["venues"]}
    md = client.get(f"/api/runs/{run.id}/packet.md").text
    for heading in ("Event overview", "Original and revised strategy", "Venue shortlist", "Preliminary financial model", "Budget warnings",
                    "What We Learned", "Unsent outreach drafts", "Supporting sources", "Agent handoff trace", "Token usage and cost"):
        assert heading in md, heading


# 3 ─ An event with missing venue pricing ──────────────────────────────────────────


def test_missing_venue_pricing_shows_quote_required_and_hypothetical_estimate(client):
    pid = make_plan(client, name="Ballroom gala", budget_limit_usd=60000)
    run, steps, _ = run_plan(client, pid, script=ScriptedClient({"EventStrategyOutput": pick("gramercy")}))
    first = next(s for s in steps if s.step_key == "finance")
    assert first.result["data"]["venue"] == "Gramercy Hall (synthetic)" and run.result["original_plan"]["pricing_status"] == "quote_required"
    a = first.result["data"]["model"]["assumptions"]
    assert a["venue_rental_usd"]["kind"] == "hypothetical" and "Quote required" in a["venue_rental_usd"]["basis"]
    assert a["catering_per_guest_usd"]["kind"] == "placeholder"
    packet = client.get(f"/api/runs/{run.id}/packet").json()["packet"]
    gramercy = next(v for v in packet["venues"] if v["name"].startswith("Gramercy"))
    assert gramercy["pricing"] == "Quote required" and gramercy["pricing_status"] == "quote_required"
    assert any("Gramercy Hall" in w["text"] and "Quote required" in w["text"] for w in packet["budget_warnings"])


# 4 ─ An event with incomplete financial information ────────────────────────────────


def test_incomplete_financial_information_is_reported_not_guessed(client):
    pid = make_plan(client, name="Unpriced reception", event_type="reception", event_format="reception", ticket_price_usd=None,
                    budget_limit_usd=100000)
    with client.app.state.db.transaction() as s:
        s.execute(delete(FinancialRecord).where(FinancialRecord.kind.in_(("reserve", "cash"))))  # no balance of any kind
    run, steps, _ = run_plan(client, pid, script=ScriptedClient({"EventStrategyOutput": pick("chelsea")}))
    fin = run.result["finance"]
    assert fin["verdict"] == "insufficient_data"
    assert fin["position"]["available_planning_budget_usd"] is None and "no reserve" in fin["position"]["available_planning_budget_basis"]
    m = fin["model"]
    assert m["scenarios"]["base"]["net_usd"] is None and m["break_even_attendance"] is None
    assert "Ticket price" in m["missing_inputs"]
    assert not any(s.kind == "revision" for s in steps)  # unknowns never trigger revisions
    packet = client.get(f"/api/runs/{run.id}/packet").json()["packet"]
    assert any(w["level"] == "unknown" and "Ticket price" in w["text"] for w in packet["budget_warnings"])


# 5 ─ An event affected by historical lessons ─────────────────────────────────────


def test_history_lesson_alone_triggers_a_revision(client):
    pid = make_plan(client, name="Seated gala", budget_limit_usd=40000)
    run, steps, _ = run_plan(client, pid, script=ScriptedClient({"EventStrategyOutput": pick("hudson")}))
    first_finance = next(s for s in steps if s.step_key == "finance")
    assert first_finance.result["data"]["conflicts"] == []  # affordable on budget...
    assert run.result["original_plan"]["venue"].startswith("Hudson")
    reasons = run.result["revision_reasons"]
    assert [r["source"] for r in reasons] == ["history"] and "catering minimum" in reasons[0]["detail"]  # ...but neglects a lesson
    assert run.result["revised_plan"]["venue"] == "Chelsea Atelier (synthetic)"
    packet = client.get(f"/api/runs/{run.id}/packet").json()["packet"]
    assert packet["history_checks"] and packet["history_checks"][-1]["passed"] is True
    assert packet["lessons"] and all(l["events"] or l["reflection_ids"] for l in packet["lessons"])


def test_same_plan_without_history_keeps_the_original_choice(client):
    pid = make_plan(client, name="Seated gala", budget_limit_usd=40000)
    run, steps, _ = run_plan(client, pid, script=ScriptedClient({"EventStrategyOutput": pick("hudson")}), use_history=False)
    assert "lessons" not in [s.step_key for s in steps] and not any(s.kind == "revision" for s in steps)
    assert run.result["finance"]["venue"].startswith("Hudson")


# ── Recalculation, saved assumptions, packet permissions ─────────────────────────


def test_board_can_recalculate_assumptions_deterministically(client):
    login(client)
    run, _, _ = run_plan(client, gala_plan_id(client.app))
    assumptions = run.result["finance"]["model"]["assumptions"]
    edited = {**assumptions, "attendance": {**assumptions["attendance"], "value": 120},
              "ticket_price_usd": {**assumptions["ticket_price_usd"], "value": 300}}
    r = client.post("/api/event-model/calculate", json={"assumptions": edited, "max_budget_usd": 18000, "target_usd": 40000})
    assert r.status_code == 200
    m = r.json()["model"]
    assert m["attendance"] == 120 and m["scenarios"]["base"]["ticket_revenue_usd"] == 36000
    assert r.json()["affordability"]["cash_note"].startswith("Recorded income is not treated as cash")
    bad = client.post("/api/event-model/calculate", json={"assumptions": {**edited, "contingency_pct": 5}})
    assert bad.status_code == 422
    client.post("/api/auth/logout")
    login(client, email=MEMBER)
    assert client.post("/api/event-model/calculate", json={"assumptions": edited}).status_code == 403


def test_saved_board_assumptions_feed_the_next_strategy(client):
    login(client)
    pid = gala_plan_id(client.app)
    assert client.put(f"/api/events/{pid}/assumptions", json={"assumptions": {"entertainment_usd": 400, "marketing_usd": 0}}).status_code == 200
    run, _, _ = run_plan(client, pid)
    a = run.result["finance"]["model"]["assumptions"]
    assert a["entertainment_usd"] == {"value": 400.0, "kind": "board", "basis": "Edited by the board"}
    assert a["marketing_usd"]["value"] == 0.0


def test_member_packet_hides_finance_but_shows_plan(client):
    login(client)
    run, _, _ = run_plan(client, gala_plan_id(client.app))
    client.post("/api/auth/logout")
    login(client, email=MEMBER)
    p = client.get(f"/api/runs/{run.id}/packet").json()["packet"]
    assert "financial_model" not in p and "position" not in p and p["finance_visible"] is False
    assert "total_usd" not in (p["revision"]["original"] or {})
    assert p["venues"] and p["trace"] and p["drafts"]
    assert all(t["summary"] is None for t in p["trace"] if t["to_agent"] == "financial_analysis")
    assert "Preliminary financial model" not in client.get(f"/api/runs/{run.id}/packet.md").text


def test_update_plan_validates_date_range(client):
    pid = make_plan(client)
    ok = client.put(f"/api/events/{pid}", json={"name": "Test fundraiser", "target_date": "2027-04-17", "date_end": "2027-04-24"})
    assert ok.status_code == 200 and ok.json()["event"]["date_end"] == "2027-04-24"
    assert client.put(f"/api/events/{pid}", json={"name": "Test", "target_date": "2027-04-17", "date_end": "2027-04-01"}).status_code == 422


# ── Live venue research honesty (no network: the fetch is simulated) ────────────────


def live_ctx(client, run_id: int = 1):
    app = client.app
    ctx = RunContext(run_id=run_id, organization_id=1, user_id=1, user_permissions=permissions_for("chair"), strategy="auto",
                     research_mode="live", db=app.state.db, router=ModelRouter("openai"), budget=WorkflowBudget(1, 5),
                     settings=app.state.settings, llm=None)
    ctx.tools = build_tool_registry(ctx)
    return ctx


def test_live_prices_are_used_only_if_they_appear_on_the_fetched_page(client, monkeypatch):
    with client.app.state.db.transaction() as s:
        s.add(AgentRun(id=1, organization_id=1, user_id=1, workflow_type="plan_event", request_text="x", status="running", strategy="auto"))
    pages = {"https://venue.example/": {"ok": True, "http_status": 200, "title": "The Venue", "retrieved_at": "2026-10-25T00:00:00+00:00",
                                         "text": "Our ballroom seats 180 guests for dinner. Dinner packages from $165 per person."}}
    monkeypatch.setattr(web, "fetch_page", lambda url, **_: {"url": url, "final_url": url, **pages.get(url, {"ok": False, "http_status": 404, "text": ""})})
    v = {"venue_key": "live-1", "name": "The Venue", "website": "https://venue.example/", "source_url": "https://venue.example/",
         "capacity": {"seated_dinner": 180}, "reported_rental_usd": 12000.0, "reported_fnb_per_guest_usd": 165.0,
         "reported_fnb_minimum_usd": None, "source_id": "web:venue:1", "verification": "unverified", "notes": ""}
    sources = _verify_live_venue(FundraisingEventsAgent(), live_ctx(client), v)
    assert v["fnb_per_guest_usd"] == 165.0 and v["rental_usd"] is None  # $12,000 rental was not on the page
    assert v["pricing_status"] == "published" and v["capacity_status"] == "published" and v["website_status"] == "verified"
    assert "Not confirmed on the fetched page" in v["notes"] and "rental" in v["notes"] and sources[0].verification == "verified"
    a = em.build_assumptions(venue=v, event_format="seated_dinner", event={"attendance": 150, "ticket_price_usd": 200},
                             history={}, contingency_pct=None)
    assert a["venue_rental_usd"]["kind"] == "hypothetical" and a["catering_per_guest_usd"]["kind"] == "published"


def test_unreachable_live_venue_is_not_presented_as_researched(client, monkeypatch):
    with client.app.state.db.transaction() as s:
        s.add(AgentRun(id=1, organization_id=1, user_id=1, workflow_type="plan_event", request_text="x", status="running", strategy="auto"))
    monkeypatch.setattr(web, "fetch_page", lambda url, **_: {"url": url, "ok": False, "http_status": None, "error": "ConnectError", "text": ""})
    v = {"venue_key": "live-2", "name": "Ghost Hall", "website": "https://ghost.example/", "source_url": "https://ghost.example/",
         "capacity": {"reception": 200}, "reported_rental_usd": 5000.0, "reported_fnb_per_guest_usd": None, "reported_fnb_minimum_usd": None,
         "source_id": "web:venue:2", "verification": "unverified", "notes": ""}
    _verify_live_venue(FundraisingEventsAgent(), live_ctx(client), v)
    assert v["verification"] == "unverified" and v["website_status"] == "unreachable"
    assert v["pricing_status"] == "quote_required" and v["capacity_status"] == "unconfirmed" and v["rental_usd"] is None


def test_figures_on_page_matches_whole_numbers_only():
    found = web.figures_on_page("Seats 150 guests. Rental $1,500 per evening.", [150.0, 1500.0, 15.0])
    assert found == {"150.0": True, "1500.0": True, "15.0": False}


def test_outreach_drafts_target_only_shortlisted_venues_and_stay_unsent(client):
    login(client)
    run, _, _ = run_plan(client, gala_plan_id(client.app))
    with client.app.state.db.session() as s:
        drafts = s.scalars(select(OutreachDraft).where(OutreachDraft.run_id == run.id)).all()
    shortlisted = {x["venue"] for x in run.result["shortlist"]}
    assert drafts and {d.recipient_org for d in drafts} <= shortlisted and {d.status for d in drafts} == {"draft"}
    assert {d.draft_type for d in drafts} == {"venue_inquiry"}


def test_packet_builder_and_markdown_are_deterministic(client):
    login(client)
    run, _, _ = run_plan(client, gala_plan_id(client.app))
    a = build_packet(client.app.state.db, run.id, 1, True)
    b = build_packet(client.app.state.db, run.id, 1, True)
    assert a == b and packet_markdown(a) == packet_markdown(b)
    assert a["usage"]["model_calls"] == sum(1 for t in a["trace"] for _ in t["models"]) or a["usage"]["model_calls"] > 0


def test_intake_survives_a_provider_outage(client):
    """If the model can't be reached, the Orchestrator still interprets the request (keyword fallback)."""
    def down(p, kw):
        raise ConnectionError("network down")

    login(client)
    run, steps, _ = run_plan(client, gala_plan_id(client.app), script=ScriptedClient({"RequestAnalysis": down}))
    intake = steps[0]
    assert intake.status == "completed" and intake.result["data"]["routing"].startswith("keyword")
    assert any("could not be reached" in w for w in intake.result["warnings"])
    assert run.status in ("completed", "completed_with_warnings")
