"""Prompt 5: Mission Discovery, Partnerships & Outreach, and the foundation's philosophy.

The nine required scenarios, run offline with the scripted model so results
are identical every time:
  1. source-backed retrieval            6. a malicious page is treated as untrusted
  2. alignment uses the philosophy      7. missing / conflicting info produces warnings
  3. saving and organizing an opportunity 8. history (community feedback) shapes an event plan
  4. Mission Discovery -> Outreach handoff 9. model routing and usage logging
  5. drafts saved, never sent
"""

from __future__ import annotations

import pathlib
import re

import pytest
from sqlalchemy import select

from backend.app.agents.registry import AGENTS_BY_NAME
from backend.app.agents.contracts import AgentName
from backend.app.agents.verification import outreach_violations
from backend.app.ai.providers import AIProvider
from backend.app.core.permissions import permissions_for
from backend.app.db.models import (AgentHandoff, AgentRun, AgentToolCall, AuditLog, BoardReflection, Donation, HistoricalLesson, ModelUsage,
                                   OutreachDraft, ResearchFinding)
from backend.app.mission import CRITERIA, PHILOSOPHY
from backend.app.safety.policy import PROHIBITED_ACTIONS
from backend.app.services.mission_fit import fit_label
from backend.app.tools import web
from backend.app.tools.registry import ProhibitedActionError, ToolKind, ToolRegistry, ToolSpec

from .conftest import login
from .fakes import ScriptedClient
from .test_agents import gala_plan_id

NY_REQUEST = ("Find three organizations in New York that support mental health awareness and community belonging, "
              "and draft partnership inquiries.")
BACKEND = pathlib.Path(__file__).resolve().parents[1] / "backend"


def run_flow(client, request: str, intent: str | None = None, mode: str = "synthetic", script: ScriptedClient | None = None,
             options: dict | None = None, plan_id: int | None = None):
    app = client.app
    fake = script or ScriptedClient()
    app.state.provider = AIProvider(app.state.settings.provider or "openai", fake)
    with app.state.db.transaction() as s:
        run = AgentRun(organization_id=1, user_id=1, workflow_type=intent or "auto", request_text=request, status="queued",
                       strategy="auto", provider=app.state.settings.provider, budget_usd=app.state.settings.workflow_budget_usd,
                       research_mode=mode)
        s.add(run)
        s.flush()
        run_id = run.id
    app.state.workflows.start(run_id, user_id=1, organization_id=1, permissions=permissions_for("chair"), strategy="auto",
                              research_mode=mode, request=request, intent_hint=intent, event_plan_id=plan_id, synchronous=True,
                              options=options or {})
    with app.state.db.session() as s:
        run = s.get(AgentRun, run_id)
        steps = s.scalars(select(AgentHandoff).where(AgentHandoff.run_id == run_id).order_by(AgentHandoff.id)).all()
    return run, steps, fake


def model_inputs(fake: ScriptedClient) -> str:
    return "\n".join(str(c.get("input", "")) + str(c.get("instructions", "")) for c in fake.calls)


def findings_by_name(client) -> dict[str, ResearchFinding]:
    with client.app.state.db.session() as s:
        return {re.sub(r" \(synthetic\)$", "", f.name or f.title): f for f in s.scalars(select(ResearchFinding)).all()}


# ── 1. Real, source-backed retrieval ─────────────────────────────────────────────


def test_live_retrieval_is_source_backed(client, monkeypatch):
    """Live mode: every saved opportunity carries the URL the search returned and the result of fetching it.
    Unknown sources, unreachable pages, and costs missing from the page are never presented as facts."""
    hits = [
        {"title": "Real Peer Support NYC", "url": "https://peer.example.net/", "publisher": None, "published": None,
         "date_claim": None, "snippet": "Peer-led mental health support groups in Brooklyn."},
        {"title": "Gone Collective", "url": "https://gone.example.net/", "publisher": None, "published": None,
         "date_claim": "June 6, 2027", "snippet": "A community wellness collective."},
    ]
    pages = {"https://peer.example.net/": {"ok": True, "http_status": 200, "title": "Real Peer Support NYC",
                                            "text": "We run free peer-led mental health support circles in Brooklyn community centers. "
                                                    "Community partners can sponsor a circle for $150 a month."}}
    monkeypatch.setattr(web, "fetch_page", lambda url, **_: {"url": url, "final_url": url, "retrieved_at": "2026-10-24T12:00:00+00:00",
                                                            **pages.get(url, {"ok": False, "http_status": None, "error": "ConnectError", "text": ""})})

    def analysis(p, kw):
        out = ScriptedClient().handlers["MissionAnalysis"](p, kw)
        for o in out["opportunities"]:
            if o["source_id"] == "web:1":
                o["known_costs"] = "Sponsor a circle for $9,999 per year"  # not on the page: must be dropped
        out["opportunities"].append({**out["opportunities"][0], "source_id": "web:99", "name": "Invented Org"})
        return out

    fake = ScriptedClient({"SearchHits": lambda p, kw: {"hits": hits, "search_notes": ""}, "MissionAnalysis": analysis})
    run, steps, _ = run_flow(client, "Find peer support organizations in New York", intent="mission_discovery", mode="live", script=fake)
    assert run.status == "completed", run.error
    research = next(s for s in steps if s.to_agent == "mission_discovery")
    cards = {f.website: f for f in findings_by_name(client).values()}
    assert set(cards) == {"https://peer.example.net/", "https://gone.example.net/"}  # only URLs the search returned
    assert "Invented Org" not in {f.name for f in cards.values()}
    assert any("unknown source (web:99)" in w for w in research.result["warnings"])
    ok, gone = cards["https://peer.example.net/"], cards["https://gone.example.net/"]
    assert ok.verification_status == "verified" and ok.last_checked is not None
    assert ok.known_costs is None and any("not found on the checked page" in w for w in ok.warnings)
    assert gone.verification_status == "unverified" and gone.fit == "Needs research"
    assert any("could not be verified" in w for w in gone.warnings) and gone.date_status == "unconfirmed"
    sources = {src["url"]: src["verification"] for src in research.result["sources"]}
    assert sources == {"https://peer.example.net/": "verified", "https://gone.example.net/": "unverified"}


# ── 2. Alignment uses the foundation's philosophy ─────────────────────────────────


def test_alignment_uses_the_philosophy_and_an_explicit_rubric(client):
    run, steps, fake = run_flow(client, "Find mental health and eating disorder organizations in New York", intent="mission_discovery")
    instructions = fake.schema_calls("MissionAnalysis")[0]["instructions"]
    assert PHILOSOPHY in instructions and all(c["label"] in instructions for c in CRITERIA)
    assert "never assume" in instructions.lower() and "clinical" in instructions.lower()
    cards = findings_by_name(client)
    detail = cards["Harbor Minds Collective"].alignment_detail
    assert set(detail) >= {"charitable", "philosophical", "practical", "evidence"}  # A, B, C, D
    assert set(detail["philosophical"]) == {"compassion", "belonging_inclusion", "human_connection", "seen_heard_valued"}
    # Clinical research is a Strong fit even though its effect on belonging is not visible.
    nourish = cards["Nourish NY Eating Disorder Research Network"]
    assert nourish.alignment_detail["philosophical"]["seen_heard_valued"]["level"] == "unclear" and nourish.fit == "Strong fit"
    # Outside the requested geography: a stated blocker keeps it from Strong fit.
    assert cards["Campus Minds Collective"].fit == "Possible fit"
    # The rubric is code, not the model: same inputs, same label.
    strong = {"mental_health": {"level": "unclear"}, "eating_disorders": {"level": "strong"}, "community_wellbeing": {"level": "none"}}
    assert fit_label(charitable=strong, verification="verified", blockers=[], purpose_known=True)[0] == "Strong fit"
    assert fit_label(charitable=strong, verification="unverified", blockers=[], purpose_known=True)[0] == "Possible fit"
    weak = {k: {"level": "unclear"} for k in strong}
    assert fit_label(charitable=weak, verification="verified", blockers=[], purpose_known=True)[0] == "Weak fit"
    assert fit_label(charitable=strong, verification="unreachable", blockers=[], purpose_known=True)[0] == "Needs research"


# ── 3. Saving and organizing opportunities ────────────────────────────────────────


def test_board_can_save_dismiss_categorize_and_annotate(client):
    login(client)
    run_flow(client, "Find organizations in New York", intent="mission_discovery")
    cards = findings_by_name(client)
    harbor, walk = cards["Harbor Minds Collective"].id, cards["Belonging Walk NYC"].id
    assert client.post(f"/api/opportunities/{harbor}/status", json={"status": "saved"}).json()["opportunity"]["saved"] is True
    assert client.post(f"/api/opportunities/{walk}/status", json={"status": "dismissed"}).status_code == 200
    r = client.put(f"/api/opportunities/{harbor}", json={"board_category": "Partnership prospect", "notes": "Ask Dana privately first."})
    assert r.json()["opportunity"]["board_category"] == "Partnership prospect"
    body = client.get("/api/opportunities").json()
    ids = {o["id"] for o in body["opportunities"]}
    assert harbor in ids and walk not in ids  # dismissed are hidden from the active view
    assert walk in {o["id"] for o in client.get("/api/opportunities?status=dismissed").json()["opportunities"]}
    stats = body["stats"]  # computed from stored records only
    assert stats["by_status"]["saved"] == 1 and stats["by_status"]["dismissed"] == 1 and stats["total"] == 6
    assert stats["synthetic"] == 6 and stats["injection_flagged"] == 1
    saved = next(o for o in body["opportunities"] if o["id"] == harbor)
    assert saved["notes"] == "Ask Dana privately first." and saved["status"] == "saved"
    # Private notes never reach a model, and the audit log records field names only.
    _, _, fake = run_flow(client, "Draft partnership inquiries", intent="partnership_outreach", options={"finding_ids": [harbor]})
    assert "Ask Dana" not in model_inputs(fake)
    with client.app.state.db.session() as s:
        logged = [a.detail for a in s.scalars(select(AuditLog).where(AuditLog.action == "opportunity_updated")).all()]
    assert logged and "Ask Dana" not in str(logged)
    client.post("/api/auth/logout")
    assert client.post(f"/api/opportunities/{harbor}/status", json={"status": "dismissed"}).status_code == 401


# ── 4. Mission Discovery -> Outreach handoff ──────────────────────────────────────


def test_mission_discovery_hands_verified_findings_to_outreach(client):
    run, steps, fake = run_flow(client, NY_REQUEST)
    assert run.status == "completed", run.error
    assert run.result["intent"] == "partnership_outreach"
    assert [(s.from_agent, s.to_agent, s.step_key) for s in steps] == [
        ("board", "orchestrator", "intake"), ("orchestrator", "mission_discovery", "research"), ("orchestrator", "orchestrator", "select"),
        # Prompt 10: Finance states the available budget (the chair has financial access), then the Boss Agent decides on drafts.
        ("orchestrator", "financial_analysis", "finance"), ("orchestrator", "orchestrator", "outreach_decision"),
        ("orchestrator", "partnerships_outreach", "outreach"), ("orchestrator", "orchestrator", "recommendation"),
        ("orchestrator", "orchestrator", "verification")]
    select_step = next(s for s in steps if s.step_key == "select")
    selected = select_step.result["data"]["selected"]
    assert len(selected) == 3 and all(o["fit"] == "Strong fit" for o in selected)
    excluded = {x["name"]: x["reason"] for x in select_step.result["data"]["excluded"]}
    assert "Belonging Walk NYC (synthetic)" in excluded and "Open Table Queens (synthetic)" in excluded
    # Sources and uncertainty travel with the findings into the Outreach handoff (logged in Agent Activity).
    outreach = next(s for s in steps if s.step_key == "outreach")
    constraints = {c["name"]: c["detail"] for c in outreach.payload["constraints"]}
    assert "drafts_only" in constraints and sum(k.startswith("confirm:") for k in constraints) == 3
    targets = fake.schema_calls("DraftsOutput")[0]
    sent = re.search(r"DATA \(JSON\):\n(.*)", targets["input"], re.S).group(1)
    assert "source_ids" in sent and "missing_or_unconfirmed" in sent
    with client.app.state.db.session() as s:
        drafts = s.scalars(select(OutreachDraft).where(OutreachDraft.run_id == run.id)).all()
    assert {d.finding_id for d in drafts} == {o["id"] for o in selected}
    assert all(d.sources and d.sources[0]["url"].startswith("https://example.org/synthetic/") for d in drafts)
    assert all(d.review_notes for d in drafts) and {d.draft_type for d in drafts} <= {
        "nonprofit_collaboration", "research_support", "partnership_inquiry", "community_program"}
    login(client)
    packet = client.get(f"/api/runs/{run.id}/partnership-packet").json()["packet"]
    assert len(packet["selected"]) == 3 and len(packet["drafts"]) == 3 and packet["excluded"]
    md = client.get(f"/api/runs/{run.id}/partnership-packet.md").text
    assert "Nothing in this packet has been sent" in md and "## 3. Considered but not selected" in md
    assert all(c["passed"] is not False for c in run.result["verification"]["checks"])
    names = {c["name"] for c in run.result["verification"]["checks"]}
    assert {"Every partnership draft carries the sources it was written from", "Selected opportunities have checked sources"} <= names


# ── 5. Drafts are saved and editable, never sent ──────────────────────────────────


def test_drafts_are_saved_editable_and_never_sent(client):
    run, _, _ = run_flow(client, NY_REQUEST)
    login(client)
    drafts = client.get("/api/drafts").json()["drafts"]
    assert drafts and all(d["status"] == "draft" for d in drafts)
    d = drafts[0]
    r = client.put(f"/api/drafts/{d['id']}", json={"subject": "Edited subject", "body": "Edited body", "next_step": "A short call."})
    assert r.status_code == 200
    again = next(x for x in client.get("/api/drafts").json()["drafts"] if x["id"] == d["id"])
    assert (again["subject"], again["body"], again["next_step"]) == ("Edited subject", "Edited body", "A short call.")
    assert client.put(f"/api/drafts/{d['id']}", json={"status": "sent"}).status_code == 422
    assert client.put(f"/api/drafts/{d['id']}", json={"send": True}).status_code == 422
    assert client.put(f"/api/drafts/{d['id']}", json={"status": "archived"}).status_code == 200
    assert d["id"] in {x["id"] for x in client.get("/api/drafts?archived=true").json()["drafts"]}
    # No route, tool, or library in SAM SPACE can send anything.
    assert not [r.path for r in client.app.routes if re.search(r"send|deliver|dispatch|schedule|publish", getattr(r, "path", ""))]
    for name in ("send_email", "send_message", "send_direct_message", "contact_organization", "schedule_outreach",
                 "publish_message", "make_commitment"):
        assert name in PROHIBITED_ACTIONS
        with pytest.raises(ProhibitedActionError):
            ToolRegistry(client.app.state.db).register(ToolSpec(name, "x", ToolKind.DRAFT, lambda: None))
    # Drafts only. lookup_inquiry_details only READS official pages for a public inquiry address; it cannot send anything.
    assert set(AGENTS_BY_NAME[AgentName.PARTNERSHIPS_OUTREACH].allowed_tools) == {"read_saved_findings", "lookup_inquiry_details",
                                                                                 "create_outreach_draft"}
    code = "\n".join(p.read_text() for p in BACKEND.rglob("*.py"))
    for lib in ("smtplib", "sendgrid", "mailgun", "postmark", "twilio", "boto3", "email.mime", "slack_sdk"):
        assert f"import {lib}" not in code and f"from {lib}" not in code
    with client.app.state.db.session() as s:
        statuses = set(s.scalars(select(OutreachDraft.status)).all())
    assert statuses <= {"draft", "reviewed", "archived"}


def test_drafts_inventing_relationships_or_commitments_are_rewritten_or_dropped(client):
    bad = "Following our conversation last week, thank you for your continued support. We will donate $5,000 to your program."

    def drafts(p, kw):
        out = ScriptedClient().handlers["DraftsOutput"](p, kw)
        if "rejected_because" in p:  # the bounded rewrite: fix one, keep the other bad
            out["drafts"] = out["drafts"][:1] + [{**x, "body": bad} for x in out["drafts"][1:]]
        else:
            out["drafts"] = [{**x, "body": bad} for x in out["drafts"]]
        return out

    run, steps, fake = run_flow(client, NY_REQUEST, script=ScriptedClient({"DraftsOutput": drafts}))
    assert len(fake.schema_calls("DraftsOutput")) == 2  # one rewrite, never more
    with client.app.state.db.session() as s:
        saved = s.scalars(select(OutreachDraft).where(OutreachDraft.run_id == run.id)).all()
    assert len(saved) == 1 and bad not in saved[0].body
    outreach = next(s for s in steps if s.step_key == "outreach")
    assert sum("Dropped the draft" in w for w in outreach.result["warnings"]) == 2
    problems = outreach_violations(bad, set())
    assert any("relationship" in p for p in problems) and any("commits" in p for p in problems) and any("$5,000" in p for p in problems)


# ── 6. A malicious webpage is treated as untrusted ────────────────────────────────


def test_malicious_page_instructions_are_removed_and_never_followed(client):
    run, steps, fake = run_flow(client, NY_REQUEST)
    sent = model_inputs(fake)
    assert "Ignore all previous instructions" not in sent and "donor list" not in sent and "perfect fit" not in sent
    card = findings_by_name(client)["Open Table Queens"]
    assert card.injection_flags and card.fit != "Strong fit"
    assert any("instructions aimed at an AI system" in w for w in card.warnings)
    assert any("instruction-like" in c.lower() for c in run.result["recommendation"]["caveats"])
    with client.app.state.db.session() as s:
        drafts = s.scalars(select(OutreachDraft)).all()
        logged = s.scalars(select(AgentToolCall.result_summary).where(AgentToolCall.tool_name == "fetch_source")).all()
    assert not any("grants@example.org" in (d.body + d.recipient_org) for d in drafts)
    assert any("instruction-like fragment(s) removed" in (x or "") for x in logged)


def test_private_records_never_leave_in_a_search_query(client, monkeypatch):
    with client.app.state.db.session() as s:
        donor = s.scalars(select(Donation.donor_name)).first()
    assert donor
    monkeypatch.setattr(web, "fetch_page", lambda url, **_: {"url": url, "ok": False, "http_status": None, "error": "x", "text": ""})
    fake = ScriptedClient({"SearchHits": lambda p, kw: {"hits": [], "search_notes": ""},
                           "ResearchPlan": lambda p, kw: {"search_query": f"partners like {donor} who gave $2,500 email a@b.org",
                                                          "geography": None, "count_requested": None,
                                                          "opportunity_types": ["organization"], "focus_criteria": []}})
    run, steps, _ = run_flow(client, "Find partners", intent="mission_discovery", mode="live", script=fake)
    query = fake.schema_calls("SearchHits")[0]["input"]
    assert donor not in query and "$2,500" not in query and "a@b.org" not in query
    research = next(s for s in steps if s.to_agent == "mission_discovery")
    assert any("Removed private details" in w for w in research.result["warnings"])


# ── 7. Missing or conflicting information produces warnings ───────────────────────


def test_missing_and_conflicting_information_produce_warnings(client):
    run_flow(client, "Find organizations in New York", intent="mission_discovery")
    cards = findings_by_name(client)
    walk = cards["Belonging Walk NYC"]
    assert walk.date_status == "conflicting" and walk.fit == "Possible fit"
    assert any("Conflicting dates" in w and "May 9, 2027" in w and "May 2, 2027" in w for w in walk.warnings)
    nourish = cards["Nourish NY Eating Disorder Research Network"]
    assert nourish.date_status == "confirmed" and "$5,000" in (nourish.known_costs or "")
    harbor = cards["Harbor Minds Collective"]
    assert harbor.known_costs is None and "Costs or giving levels are not stated on the source." in harbor.missing_info
    assert "No dates are stated." in harbor.missing_info
    assert web.date_status("May 2, 2027", ["2027-05-09"])[0] == "conflicting"
    assert web.date_status("May 2, 2027", ["2026-01-01"])[0] == "unconfirmed"


# ── 8. History shapes an event recommendation ─────────────────────────────────────


def _with_insights(real_quote: str):
    def lessons(p, kw):
        out = ScriptedClient().handlers["LessonsOutput"](p, kw)
        refl = next(r for r in p["reflections"] if real_quote in (r.get("welcome_inclusion") or ""))
        out["community_insights"] = [
            {"lens": "welcomed", "observation": "Ticket price made some first-time guests feel out of place.", "quote": real_quote,
             "evidence_reflection_ids": [refl["id"]], "evidence_event_ids": [], "evidence_type": "verified_outcome"},
            {"lens": "connection", "observation": "Guests loved everything.", "quote": "Everyone said it was the best night of their lives.",
             "evidence_reflection_ids": [refl["id"]], "evidence_event_ids": [], "evidence_type": "attendee_feedback_reported"},
        ]
        return out

    def strategy(p, kw):
        out = ScriptedClient().handlers["EventStrategyOutput"](p, kw)
        applied = [f"{c['observation']} (reflection {c['reflection_ids'][0]})" for c in p.get("community_insights") or []]
        out["mission_contribution"] = {"inclusion": "Offer a lower-priced community ticket." if applied else "Not assessed.",
                                       "connection": "Seat first-time guests with board members.", "accessibility": "Ask about step-free entry.",
                                       "recognition": "Thank volunteers by name.", "charitable_alignment": "Recovery speaker.",
                                       "community_lessons_applied": applied or ["Invented lesson"], "open_questions": ["Is entry step-free?"]}
        return out

    return ScriptedClient({"LessonsOutput": lessons, "EventStrategyOutput": strategy})


def test_community_feedback_from_history_shapes_the_event_plan(client):
    quote = "Some first-time guests told me they felt out of place at a $250 dinner."
    gala = "Plan a 150-person Manhattan fundraising gala, using lessons from our previous events and checking whether we can afford it."
    run, steps, fake = run_flow(client, gala, intent="plan_event", script=_with_insights(quote), plan_id=gala_plan_id(client.app),
                                options={"use_history": True})
    assert run.status == "completed", run.error
    lessons = next(s for s in steps if s.step_key == "lessons")
    kept = lessons.result["data"]["community_insights"]
    assert [c["quote"] for c in kept] == [quote]  # the fabricated quote was dropped
    assert kept[0]["evidence_type"] == "board_observation"  # an opinion is never promoted to an outcome
    assert any("not in the cited records" in w for w in lessons.result["warnings"])
    strategy_input = fake.schema_calls("EventStrategyOutput")[0]["input"]
    assert quote.replace("$", "") in strategy_input.replace("$", "")
    mc = run.result["mission_contribution"]
    assert mc["community_lessons_applied"] and "reflection" in mc["community_lessons_applied"][0]
    assert run.result["finance"]["verdict"]  # mission contribution sits alongside the financial checks, not instead of them
    with client.app.state.db.session() as s:
        saved = s.scalars(select(HistoricalLesson).where(HistoricalLesson.kind == "community_insight")).all()
    assert len(saved) == 1 and quote in saved[0].lesson
    login(client)
    packet = client.get(f"/api/runs/{run.id}/packet").json()["packet"]
    assert packet["mission_contribution"]["inclusion"] and packet["community_insights"][0]["quote"] == quote
    # Without history, nothing can be "applied": the claimed lesson is removed by code.
    run2, steps2, _ = run_flow(client, gala, intent="plan_event", script=_with_insights(quote), plan_id=gala_plan_id(client.app),
                               options={"use_history": False})
    assert run2.result["mission_contribution"]["community_lessons_applied"] == []


def test_impact_metrics_are_labeled_and_never_invented(client):
    login(client)
    body = client.get("/api/impact").json()
    m = {x["key"]: x for x in body["metrics"]}
    assert m["participants"]["type"] == "Actual observation" and m["participants"]["value"] == 425
    assert m["volunteers"]["value"] == 42 and m["repeat_participants"]["coverage"] == "1 of 3 events recorded"
    assert m["reported_belonging"]["type"] == "Self-reported" and m["reported_belonging"]["examples"]
    assert m["community_insights"]["type"] == "AI interpretation" and m["community_insights"]["display"] == "Not generated yet"
    assert m["directed_per_participant"]["type"] == "Estimate"
    with client.app.state.db.transaction() as s:  # a new event with nothing recorded stays "Not recorded"
        for r in s.scalars(select(BoardReflection)).all():
            s.delete(r)
    body = client.get("/api/impact").json()
    assert {x["key"]: x for x in body["metrics"]}["reported_belonging"]["display"] == "Not recorded"


# ── 9. Model routing and usage logging ────────────────────────────────────────────


def test_partnership_workflow_routes_models_by_task_and_logs_usage(client):
    run, steps, fake = run_flow(client, NY_REQUEST)
    by_schema = {c["text"]["format"]["name"]: c["model"] for c in fake.calls}
    assert by_schema["ResearchPlan"] == "gpt-6-luna"  # simple extraction
    assert by_schema["RequestAnalysis"] == "gpt-6-luna"  # classification
    assert by_schema["MissionAnalysis"] == "gpt-6.1-sol"  # comparing findings, mission-alignment synthesis
    assert by_schema["DraftsOutput"] == "gpt-6.1-sol"  # personalized outreach from research
    assert by_schema["BoardRecommendation"] == "gpt-6-astra"  # multi-agent partnership strategy
    with client.app.state.db.session() as s:
        usage = s.scalars(select(ModelUsage).where(ModelUsage.run_id == run.id)).all()
    assert len(usage) == len(fake.calls)
    for u in usage:
        assert u.selected_model and u.selection_reason and u.handoff_id
        assert u.input_tokens and u.output_tokens is not None and u.cached_input_tokens is not None
        assert u.estimated_cost_usd and u.estimated_cost_usd > 0 and u.latency_ms is not None
    assert run.spent_usd == pytest.approx(sum(u.estimated_cost_usd for u in usage))
    assert run.spent_usd <= run.budget_usd


def test_event_venue_drafts_stay_on_luna(client):
    gala = "Plan a 150-person Manhattan fundraising gala, using lessons from our previous events and checking whether we can afford it."
    _, _, fake = run_flow(client, gala, intent="plan_event", plan_id=gala_plan_id(client.app))
    assert {c["model"] for c in fake.schema_calls("DraftsOutput")} == {"gpt-6-luna"}  # short venue inquiries


def test_portkey_runs_the_partnership_workflow_on_luna_only(make_client):
    client = make_client("portkey")
    run, _, fake = run_flow(client, NY_REQUEST)
    assert run.status == "completed", run.error
    assert {c["model"] for c in fake.calls} == {"gpt-6-luna"}
    with client.app.state.db.session() as s:
        usage = s.scalars(select(ModelUsage).where(ModelUsage.run_id == run.id)).all()
    assert {u.selected_model for u in usage} == {"gpt-6-luna"} and {u.provider for u in usage} == {"portkey"}
    assert any(u.substitution_note for u in usage)  # Sol/Astra requests are recorded as substitutions, never attempted


def test_request_more_research_refreshes_the_same_card(client):
    """'Request more research' re-checks one opportunity and refreshes its card; board fields are kept, nothing is duplicated."""
    login(client)
    run_flow(client, "Find organizations in New York", intent="mission_discovery")
    harbor = findings_by_name(client)["Harbor Minds Collective"]
    client.put(f"/api/opportunities/{harbor.id}", json={"board_category": "Watch list", "notes": "Keep."})
    run, steps, fake = run_flow(client, "Research more about Harbor Minds Collective", intent="mission_discovery",
                                options={"follow_up_finding_id": harbor.id})
    research = next(s for s in steps if s.to_agent == "mission_discovery")
    assert research.objective.startswith("Research more about Harbor Minds Collective (synthetic)")
    with client.app.state.db.session() as s:
        rows = s.scalars(select(ResearchFinding).where(ResearchFinding.name == harbor.name)).all()
    assert len(rows) == 1 and rows[0].id == harbor.id and rows[0].run_id == run.id
    assert rows[0].board_category == "Watch list" and rows[0].notes == "Keep." and rows[0].last_checked >= harbor.last_checked
    assert "Keep." not in model_inputs(fake)
