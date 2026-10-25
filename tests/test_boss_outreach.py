"""Boss Agent coordination, structured reports, proactive outreach drafting, verified contacts, and the Review Center.

Deterministic: the model is scripted (tests/fakes.py) and research uses the labeled synthetic fixtures, whose contact
details live on example.org. Nothing here touches the network or the app's real database.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import func, select

from backend.app.agents.contracts import AgentName
from backend.app.agents.registry import AGENTS_BY_NAME
from backend.app.db.models import AgentHandoff, AgentToolCall, AuditLog, FinancialRecord, ModelUsage, OutreachDraft
from backend.app.research import fixtures
from backend.app.safety.policy import PROHIBITED_ACTIONS
from backend.app.services import contacts as ct
from backend.app.tools.registry import ProhibitedActionError, ToolKind, ToolRegistry, ToolSpec

from .conftest import login
from .fakes import ScriptedClient, drafts as fake_drafts
from .test_mission import run_flow

GALA = "Plan a 150-person Manhattan fundraising gala and check whether we can afford it."
CHARITY = "Research eating disorder and mental health organizations in New York the foundation could learn about supporting."
SPONSOR_REQUEST = "Find possible local sponsors in Manhattan for our spring gala."
REPORT_KEYS = {"task_id", "workflow_id", "agent", "objective", "work_completed", "key_findings", "sources", "assumptions",
               "risks_uncertainties", "financial_considerations", "recommended_next_actions", "outreach", "additional_agents", "approval"}


def drafts_for(client, run_id):
    with client.app.state.db.session() as s:
        return s.scalars(select(OutreachDraft).where(OutreachDraft.run_id == run_id).order_by(OutreachDraft.id)).all()


def sponsor_plan(p, kw):
    return {"search_query": p["request"][:120], "geography": "New York, NY", "count_requested": None,
            "opportunity_types": ["sponsor"], "focus_criteria": ["community"]}


# 1, 3, 4, 15: the venue workflow


def test_venue_workflow_delegates_reports_and_drafts_automatically(client):
    login(client)
    run, steps, fake = run_flow(client, GALA, intent="plan_event", plan_id=1)  # the request never asks for an email
    assert run.status in ("completed", "completed_with_warnings"), run.error
    route = [(s.from_agent, s.to_agent, s.step_key) for s in steps]
    for agent, key in (("event_intelligence", "lessons"), ("fundraising_events", "venues"), ("financial_analysis", "finance"),
                       ("orchestrator", "outreach_decision"), ("partnerships_outreach", "outreach")):
        assert ("orchestrator", agent, key) in route  # 1. every task is delegated by the Orchestrator
    keys = [k for _, _, k in route]
    assert keys.index("outreach_decision") < keys.index("outreach") and keys.index("finance") < keys.index("outreach_decision")
    # 3. information flows through the Orchestrator: Finance's verdict and history reach the outreach decision and drafts.
    decision = next(s for s in steps if s.step_key == "outreach_decision")
    assert any("OUTREACH RECOMMENDED" in f["claim"] for f in decision.result["findings"])
    venues_step = next(s for s in steps if s.step_key == "venues")
    assert venues_step.payload["history_passed"]["lessons"]
    outreach_step = next(s for s in steps if s.step_key == "outreach")
    assert outreach_step.payload["depends_on"] == ["outreach_decision"]
    # 4. drafts were prepared without being asked, with the Orchestrator's reasons and Finance's considerations.
    ds = drafts_for(client, run.id)
    assert ds and all(d.status == "draft" and d.category == "venue" and d.found_by_agent == "fundraising_events" for d in ds)
    assert all(d.recommendation_reason and "shortlisted" in d.recommendation_reason for d in ds)
    assert any(any("Financial Analysis verdict" in x for x in d.financial_considerations) for d in ds)
    assert all(any("budget" in x for x in d.financial_considerations) for d in ds)
    assert run.result["boss_decisions"] and run.result["outreach_drafts"]
    # 15. Agent Activity shows the reports, the decision, and the contact lookups.
    detail = client.get(f"/api/runs/{run.id}").json()
    by_key = {s["step_key"]: s for s in detail["steps"]}
    assert by_key["venues"]["report"]["outreach"]["appropriate"] is True
    assert "lookup_inquiry_details" in [t["tool"] for t in by_key["outreach"]["tool_calls"]]
    assert by_key["outreach_decision"]["report"] is None  # the Boss Agent decides; it does not report to itself


# 2: structured reports


def test_every_specialist_returns_a_structured_report(client):
    login(client)
    run, steps, _ = run_flow(client, GALA, intent="plan_event", plan_id=1)
    specialists = [s for s in steps if s.to_agent != "orchestrator"]
    assert specialists and all(s.report and REPORT_KEYS <= set(s.report) for s in specialists)
    reports = {s.step_key: s.report for s in specialists}
    assert reports["venues"]["outreach"]["candidates"] and {"financial_analysis", "partnerships_outreach"} <= \
        {x["agent"] for x in reports["venues"]["additional_agents"]}
    assert reports["finance"]["financial_considerations"] and reports["finance"]["approval"]["board_review"]
    assert reports["finance"]["outreach"]["appropriate"] is False
    assert reports["outreach"]["approval"]["board_review"] and "nothing is sent" in reports["outreach"]["outreach"]["reason"].lower()
    assert all(r["workflow_id"] == run.id and r["task_id"] for r in reports.values())
    assert reports["lessons"]["additional_agents"][0]["agent"] == "fundraising_events"


# 5, 6: charities, research initiatives, and sponsors


def test_charity_and_research_discovery_trigger_drafts_without_promising_money(client):
    login(client)
    run, steps, _ = run_flow(client, CHARITY, intent="mission_discovery")
    keys = [s.step_key for s in steps]
    assert keys[:2] == ["intake", "research"] and "outreach_decision" in keys and "outreach" in keys
    assert "finance" in keys  # the chair has financial access, so Finance states the available budget; no amount is proposed
    ds = drafts_for(client, run.id)
    assert ds and {d.category for d in ds} <= {"charity", "research", "partner"} and all(d.found_by_agent == "mission_discovery" for d in ds)
    assert all(any("not approval to give or spend" in x or "No support amount" in x or "proposes no support amount" in x
                   for x in d.financial_considerations) for d in ds)
    assert not [d for d in ds if re.search(r"\bwe (will|would like to) (donate|give|fund)\b", d.body, re.I)]


def test_finance_is_consulted_only_with_financial_access():
    """Finance states available funds only for a board member whose role allows financial access; nobody proposes an amount."""
    from backend.app.agents.orchestrator import Orchestrator
    from backend.app.core.permissions import permissions_for

    class Ctx:  # the helper reads only the permission set before deciding whether to consult Finance
        user_permissions = permissions_for("member")

    notes = Orchestrator()._support_capacity(Ctx(), {}, [{"category": "organization"}])
    assert notes == ["Finance was not consulted: your board role has no financial access. No support amount is proposed."]
    assert Orchestrator()._support_capacity(Ctx(), {}, [{"category": "sponsor"}]) == []  # sponsorship needs no support budget


def test_sponsor_discovery_triggers_a_sponsorship_draft(client):
    login(client)
    run, steps, _ = run_flow(client, SPONSOR_REQUEST, intent="mission_discovery", script=ScriptedClient({"ResearchPlan": sponsor_plan}))
    ds = drafts_for(client, run.id)
    assert ds and all(d.category == "sponsor" and d.draft_type == "corporate_sponsorship" and d.found_by_agent == "mission_discovery"
                      for d in ds)
    assert all(any("prospective income" in x for x in d.financial_considerations) for d in ds)
    # The search also surfaced charities and events: on-mission, but not what the board asked for, so they get no draft.
    decision = next(s for s in steps if s.step_key == "outreach_decision")
    skipped = decision.result["data"]["skipped"]
    assert any("the board asked for sponsors" in x["reason"] for x in skipped)
    assert any("NO DRAFT" in f["claim"] and "asked for sponsors" in f["claim"] for f in decision.result["findings"])
    assert "finance" not in [s.step_key for s in steps]  # no support budget is relevant to a sponsor search


def test_past_events_and_off_request_findings_get_no_draft():
    from datetime import date

    from backend.app.agents.contracts import AgentResult
    from backend.app.agents.orchestrator import Orchestrator, _requested_categories
    base = {"verification": "verified", "fit": "Strong fit", "fit_reason": "Aligned."}
    found = [{**base, "id": 1, "name": "Last spring's gala", "category": "event", "dates_text": "Monday, May 11, 2026, 6:00pm–10:00pm"},
             {**base, "id": 2, "name": "Next spring's gala", "category": "event", "dates_text": "Saturday, May 15, 2027, 5:30 PM"},
             {**base, "id": 3, "name": "Weekly peer group", "category": "organization", "dates_text": "Every Monday evening"},
             {**base, "id": 4, "name": "Corner bakery (test)", "category": "sponsor", "dates_text": None}]
    today = date(2026, 10, 25)
    c = {x["name"]: x for x in Orchestrator()._opportunity_candidates(found, "mission_discovery", [], "Rated", today=today)}
    assert not c["Last spring's gala"]["eligible"] and c["Last spring's gala"]["skip_reason"] == "its date (May 11, 2026) has already passed"
    assert c["Next spring's gala"]["eligible"] and c["Weekly peer group"]["eligible"] and c["Corner bakery (test)"]["eligible"]
    s = {x["name"]: x for x in Orchestrator()._opportunity_candidates(found, "mission_discovery", [], "Rated", wanted={"sponsor"}, today=today)}
    assert [n for n, x in s.items() if x["eligible"]] == ["Corner bakery (test)"]
    assert s["Next spring's gala"]["skip_reason"] == "not a sponsor (listed as an event); the board asked for sponsors"
    plan = lambda types: AgentResult.model_construct(data={"plan": {"opportunity_types": types}})  # noqa: E731
    assert _requested_categories(plan(["sponsor"])) == {"sponsor"}
    assert _requested_categories(plan(["sponsor", "organization"])) is None and _requested_categories(None) is None


def test_contact_research_has_its_own_page_allowance(client, monkeypatch):
    """Research cannot use up contact research: it has its own allowance per draft (default 2 pages) and per run."""
    from backend.app.agents.runtime import RunContext
    from backend.app.agents.specialists.partnerships_outreach import PartnershipsOutreachAgent
    from backend.app.ai.budget import WorkflowBudget
    from backend.app.ai.router import ModelRouter
    from backend.app.core.permissions import permissions_for
    from backend.app.db.models import AgentRun
    from backend.app.tools import web
    from backend.app.tools.catalog import CONTACT_DRAFTS_PER_RUN, build_tool_registry

    app = client.app
    with app.state.db.session() as s:
        row = AgentRun(organization_id=1, user_id=1, workflow_type="auto", request_text="x", status="running", strategy="auto")
        s.add(row)
        s.commit()
        run_id = row.id
    ctx = RunContext(run_id=run_id, organization_id=1, user_id=1, user_permissions=permissions_for("chair"), strategy="auto",
                     research_mode="live", db=app.state.db, router=ModelRouter("openai"), budget=WorkflowBudget(1, 5),
                     settings=app.state.settings, llm=None)
    ctx.tools = build_tool_registry(ctx)
    ctx.counters["page_fetches"] = ctx.max_page_fetches  # venue or mission research already used every research page
    pages = {
        "https://venue.example.com/": {"ok": True, "url": "https://venue.example.com/", "text": "Welcome", "mailtos": [],
                                       "links": [{"href": "https://venue.example.com/contact", "text": "Contact"},
                                                 {"href": "https://venue.example.com/about", "text": "About"}]},
        "https://venue.example.com/contact": {"ok": True, "url": "https://venue.example.com/contact", "text": "events@venue.example.com",
                                              "links": [], "mailtos": []},
        "https://venue.example.com/about": {"ok": True, "url": "https://venue.example.com/about", "text": "about@venue.example.com",
                                            "links": [], "mailtos": []},
    }
    fetched = []

    def fake_fetch(url):
        fetched.append(url)
        return pages.get(url, {"url": url, "ok": False, "error": "HTTP 404"})

    monkeypatch.setattr(web, "fetch_page", fake_fetch)
    monkeypatch.setattr(web, "robots_allowed", lambda url, client=None: True)
    lookup = lambda name: PartnershipsOutreachAgent().tool(ctx, "lookup_inquiry_details", name=name,  # noqa: E731
                                                           website="https://venue.example.com/", kind="venue")
    out = lookup("Venue (test)")
    assert ctx.max_contact_pages == 2 and fetched == ["https://venue.example.com/", "https://venue.example.com/contact"]
    assert out.ok and out.data["email"] == "events@venue.example.com" and ctx.counters["contact_pages"] == 2
    assert ctx.counters["page_fetches"] == ctx.max_page_fetches  # research's limit is untouched
    # Per run: after three drafts' worth of pages, nothing more is read, and the draft says so.
    ctx.counters["contact_pages"] = ctx.max_contact_pages * CONTACT_DRAFTS_PER_RUN
    fetched.clear()
    out = lookup("Second venue (test)")
    assert fetched == [] and out.data["email"] is None and any("contact-page limit" in n for n in out.data["notes"])


# 7, 8, 14: contacts and attribution


def test_verified_contacts_are_attached_and_missing_ones_are_flagged(client):
    login(client)
    run, steps, _ = run_flow(client, GALA, intent="plan_event", plan_id=1)
    ds = drafts_for(client, run.id)
    outreach = next(s for s in steps if s.step_key == "outreach")
    with client.app.state.db.session() as s:
        model = s.scalar(select(ModelUsage.selected_model).where(ModelUsage.handoff_id == outreach.id).order_by(ModelUsage.id.desc()))
    for d in ds:
        fixture = next(v for v in fixtures.VENUES if v["name"] == d.recipient_org)
        expected = fixture["contact"]["email"]
        assert d.contact["email"] == expected  # 7. exactly the listed address, or none
        assert d.contact["source_url"] == fixture["contact"]["contact_page"] and d.contact["status"].startswith("synthetic")
        if expected is None:  # 8. no verified email: the board is told to use the official contact page
            assert d.contact["display"] == ct.NOT_VERIFIED and ct.NOT_VERIFIED in (d.review_notes or [])
        # 14. attribution: where the opportunity came from, which model wrote it, which handoff produced it
        assert d.found_by_agent == "fundraising_events" and d.model_used == model and d.handoff_id == outreach.id
        assert d.sources and all(src.get("verification") == "synthetic" for src in d.sources)
    with_email = [d for d in ds if d.contact["email"]]
    without = [d for d in ds if not d.contact["email"]]
    assert with_email or without


def test_a_draft_cannot_contain_an_invented_email_or_phone(client):
    login(client)

    def sneaky(p, kw):
        out = fake_drafts(p, kw)
        for d in out["drafts"]:
            d["body"] += "\nWrite to director@lavender-events.example.com or call 212-555-0199."
        return out

    run, steps, fake = run_flow(client, GALA, intent="plan_event", plan_id=1, script=ScriptedClient({"DraftsOutput": sneaky}))
    ds = drafts_for(client, run.id)
    assert not ds  # every draft was rejected twice (one bounded rewrite), so none was saved
    outreach = next(s for s in steps if s.step_key == "outreach")
    assert any("not verified on the organization's website" in w for w in outreach.result["warnings"])
    assert any("phone number" in w for w in outreach.result["warnings"])


def test_live_contact_research_only_accepts_addresses_on_the_official_site():
    pages = {
        "https://venue.example.com/events": {"ok": True, "url": "https://venue.example.com/events", "retrieved_at": "2026-10-25T20:00:00+00:00",
                                             "text": "Book your gala with us. Questions? partner@othersite.example.net",
                                             "links": [{"href": "https://venue.example.com/contact", "text": "Contact"},
                                                       {"href": "https://evil.example.org/contact", "text": "Contact"}], "mailtos": []},
        "https://venue.example.com/": {"ok": True, "url": "https://venue.example.com/", "retrieved_at": "x", "text": "Welcome", "links": [], "mailtos": []},
        "https://venue.example.com/contact": {"ok": True, "url": "https://venue.example.com/contact", "retrieved_at": "2026-10-25T20:01:00+00:00",
                                              "text": "Private events: events@venue.example.com", "links": [], "mailtos": ["noreply@venue.example.com"],
                                              "has_form": True},
    }
    fetched = []

    def fetch(url):
        fetched.append(url)
        return pages.get(url, {"ok": False, "error": "HTTP 404"})

    rec = ct.find_contact_live("Venue (test)", "https://venue.example.com/events", "venue", fetch=fetch, robots_ok=lambda u: True)
    assert rec["email"] == "events@venue.example.com" and rec["status"] == "verified_email"  # on the venue's own contact page
    assert rec["source_url"] == "https://venue.example.com/contact" and rec["contact_page_url"] == "https://venue.example.com/contact"
    assert "evil.example.org/contact" not in " ".join(fetched)  # never leaves the official site
    # No address on the site: nothing is guessed (no info@ pattern), and the board is pointed to the official page.
    pages["https://venue.example.com/contact"]["text"] = "Use the form below."
    pages["https://venue.example.com/contact"]["mailtos"] = []
    rec = ct.find_contact_live("Venue (test)", "https://venue.example.com/events", "venue", fetch=fetch, robots_ok=lambda u: True)
    assert rec["email"] is None and rec["status"] == "contact_page_only" and rec["display"] == ct.NOT_VERIFIED
    # robots.txt disallows: the page is not fetched at all.
    fetched.clear()
    rec = ct.find_contact_live("Venue (test)", "https://venue.example.com/events", "venue", fetch=fetch, robots_ok=lambda u: False)
    assert fetched == [] and rec["email"] is None and any("robots.txt" in n for n in rec["notes"])
    assert ct.find_contact_live("No site", None, "default", fetch=fetch, robots_ok=lambda u: True)["status"] == "not_found"
    # The run's page-fetch limit stops the search with one note; tracking parameters are not followed.
    pages["https://venue.example.com/events"]["links"] = [{"href": "https://venue.example.com/contact?_ga=1.2.3", "text": "Contact"}]
    fetched.clear()
    limited = lambda u: fetch(u) if len(fetched) < 1 else {"url": u, "ok": False, "error": "page-fetch limit for this run reached"}
    rec = ct.find_contact_live("Venue (test)", "https://venue.example.com/events", "venue", fetch=limited, robots_ok=lambda u: True)
    assert fetched == ["https://venue.example.com/events"] and sum("limit" in n for n in rec["notes"]) == 1
    assert rec["status"] == "website_only" and rec["email"] is None
    fetched.clear()
    ct.find_contact_live("Venue (test)", "https://venue.example.com/events", "venue", fetch=fetch, robots_ok=lambda u: True)
    assert "https://venue.example.com/contact" in fetched and not any("_ga" in u for u in fetched)


def test_reasons_end_on_whole_sentences():
    from backend.app.agents.orchestrator import _clip_sentences
    text = "First sentence is here. Second sentence runs on and on. " * 10
    out = _clip_sentences(text, 120)
    assert out.endswith(".") and len(out) <= 120
    assert _clip_sentences("word " * 100, 50).endswith("…")
    assert _clip_sentences("Short.", 50) == "Short."


# 9, 10, 11: no fabricated contacts, no sending, no spending


def test_no_sending_and_no_spending_capability_exists(client):
    login(client)
    for name in ("send_email", "reply_email", "forward_message", "submit_contact_form", "schedule_outbound_communication", "send_message",
                 "make_payment", "transfer_funds", "allocate_funds", "approve_donation", "purchase_service", "book_venue", "sign_contract",
                 "commit_foundation_resources"):
        assert name in PROHIBITED_ACTIONS
        with pytest.raises(ProhibitedActionError):
            ToolRegistry(client.app.state.db).register(ToolSpec(name, "x", ToolKind.DRAFT, lambda: None))
    for spec in AGENTS_BY_NAME.values():
        assert not set(spec.allowed_tools) & set(PROHIBITED_ACTIONS)
    assert not [r.path for r in client.app.routes if re.search(r"send|deliver|dispatch|schedule|publish|pay|transfer|book|purchase|donate",
                                                               getattr(r, "path", ""))]
    assert set(AGENTS_BY_NAME[AgentName.PARTNERSHIPS_OUTREACH].allowed_tools) == {"read_saved_findings", "lookup_inquiry_details",
                                                                                 "create_outreach_draft"}
    run, _, _ = run_flow(client, GALA, intent="plan_event", plan_id=1)
    d = drafts_for(client, run.id)[0]
    for bad in ("sent", "approved", "scheduled"):
        assert client.put(f"/api/drafts/{d.id}", json={"status": bad}).status_code == 422
    with client.app.state.db.session() as s:
        ledger_before = s.scalar(select(func.count(FinancialRecord.id)))
    assert client.put(f"/api/drafts/{d.id}", json={"status": "reviewed"}).status_code == 200
    with client.app.state.db.session() as s:
        assert s.scalar(select(func.count(FinancialRecord.id))) == ledger_before  # a review status never triggers a transaction


# 12, 13: review statuses and edits


def test_review_statuses_and_edits_persist(client):
    login(client)
    run, _, _ = run_flow(client, GALA, intent="plan_event", plan_id=1)
    d = drafts_for(client, run.id)[0]
    listed = client.get("/api/drafts?kind=outreach").json()["drafts"]
    item = next(x for x in listed if x["id"] == d.id)
    assert item["status_label"] == "AI Draft" and item["notice"] == "AI-prepared draft. Review all details before contacting this organization."
    assert item["contact"] and item["recommendation_reason"] and item["model_used"]
    r = client.put(f"/api/drafts/{d.id}", json={"subject": "Gala inquiry (edited)", "body": "Hello,\nAn edited message.\n[Board member name]"})
    assert r.status_code == 200 and r.json()["draft"]["edited_at"] and r.json()["draft"]["status"] == "draft"  # never auto-approved
    assert client.put(f"/api/drafts/{d.id}", json={"status": "needs_review"}).json()["draft"]["status_label"] == "Needs Review"
    reviewed = client.put(f"/api/drafts/{d.id}", json={"status": "reviewed"}).json()["draft"]
    assert reviewed["status_label"] == "Reviewed" and reviewed["reviewed_at"] and reviewed["reviewed_by"] == 1
    assert client.put(f"/api/drafts/{d.id}", json={"status": "archived"}).json()["draft"]["status_label"] == "Archived"
    again = next(x for x in client.get("/api/drafts?kind=outreach&archived=true").json()["drafts"] if x["id"] == d.id)
    assert again["subject"] == "Gala inquiry (edited)" and again["body"].startswith("Hello,\nAn edited message.")
    with client.app.state.db.session() as s:
        logs = s.scalars(select(AuditLog).where(AuditLog.action == "draft_updated")).all()
    assert any(l.detail.get("edited") == ["subject", "body"] or set(l.detail.get("edited") or []) == {"subject", "body"} for l in logs)
    client.post("/api/auth/logout")
    from .test_adversarial import _second_workspace
    _second_workspace(client)
    client.post("/api/auth/login", json={"email": "chair@other.example", "password": "other-pass-123"})
    assert client.put(f"/api/drafts/{d.id}", json={"status": "reviewed"}).status_code == 404


# 16: spending limits and model routing


def test_routing_and_spending_limits_apply_to_outreach(client, make_client):
    login(client)
    run, steps, fake = run_flow(client, GALA, intent="plan_event", plan_id=1)
    with client.app.state.db.session() as s:
        calls = s.scalars(select(ModelUsage).where(ModelUsage.run_id == run.id)).all()
    outreach = next(s for s in steps if s.step_key == "outreach")
    assert {c.selected_model for c in calls if c.handoff_id == outreach.id} == {"gpt-6-luna"}  # basic venue drafts: the economical tier
    rec = next(s for s in steps if s.step_key == "recommendation")
    assert {c.selected_model for c in calls if c.handoff_id == rec.id} - {"gpt-6-luna"}  # cross-department synthesis: a stronger tier
    assert all(c.estimated_cost_usd is not None and c.input_tokens for c in calls if c.status == "ok")
    # A tiny budget stops the workflow before any outreach is drafted.
    from .test_adversarial import set_limit
    set_limit(client, "workflow_budget_usd", 0.01)
    from .test_adversarial import WorstCaseClient
    stopped, steps2, _ = run_flow(client, GALA, intent="plan_event", plan_id=1, script=WorstCaseClient())
    assert stopped.status == "stopped" and not drafts_for(client, stopped.id)
    assert not any(s.step_key == "outreach_decision" for s in steps2)
    unfinished = [s.report for s in steps2 if s.report and s.report["status"] != "completed"]
    assert unfinished and all("did not finish" in r["outreach"]["reason"] and not r["outreach"]["appropriate"] for r in unfinished)
    # The course Portkey key keeps every agent, including Outreach, on gpt-6-luna.
    pk = make_client("portkey")
    login(pk)
    prun, _, _ = run_flow(pk, GALA, intent="plan_event", plan_id=1)
    with pk.app.state.db.session() as s:
        models = set(s.scalars(select(ModelUsage.selected_model).where(ModelUsage.run_id == prun.id, ModelUsage.status == "ok")))
        made = s.scalar(select(func.count(OutreachDraft.id)).where(OutreachDraft.run_id == prun.id))
    assert models == {"gpt-6-luna"} and made


def test_tool_calls_and_reports_are_logged_for_the_whole_run(client):
    login(client)
    run, steps, _ = run_flow(client, CHARITY, intent="mission_discovery")
    with client.app.state.db.session() as s:
        tools = s.scalars(select(AgentToolCall).where(AgentToolCall.run_id == run.id)).all()
        handoffs = s.scalars(select(AgentHandoff).where(AgentHandoff.run_id == run.id)).all()
    names = [t.tool_name for t in tools]
    assert "lookup_inquiry_details" in names and "create_outreach_draft" in names
    assert all(h.report for h in handoffs if h.to_agent != "orchestrator")


def test_published_costs_and_fit_reasons_stay_readable():
    """A finding's published costs are one quoted string; they must reach the draft and the report as written."""
    from backend.app.agents.orchestrator import Orchestrator
    from backend.app.agents.reports import _mission
    from backend.app.agents.contracts import AgentResult
    from backend.app.services.mission_fit import fit_label
    f = {"id": 1, "name": "Gala (test)", "category": "event", "verification": "verified", "fit": "Possible fit", "fit_reason": "Aligned.",
         "known_costs": 'The page lists "Price $1,500 - $50,000".'}
    notes = Orchestrator()._opportunity_candidates([f], "mission_discovery", [], "Mission Discovery rated it")[0]["financial_considerations"]
    assert notes == ['Published costs: The page lists "Price $1,500 - $50,000".']
    _, _, money = _mission(AgentResult.model_construct(data={"findings": [f]}))
    assert money == ['Gala (test): known costs The page lists "Price $1,500 - $50,000".']
    label, why = fit_label(charitable={"belonging": {"level": "partial"}}, verification="verified",
                           blockers=["The event is outside the requested geography."], purpose_known=True)
    assert label == "Possible fit" and ".." not in why
