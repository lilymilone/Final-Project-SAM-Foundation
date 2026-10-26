"""Foundation Knowledge Base: storage, permissions, task-relevant retrieval, and whether the knowledge changes what the
agents do (tests A-F).

Every fact here is invented for the test and labeled "(test)"; none is a real foundation record. The model is scripted
(tests/fakes.py) and research uses the labeled synthetic fixtures, so nothing touches the network.
"""

from __future__ import annotations

from sqlalchemy import select

from backend.app.agents.base import KNOWLEDGE_RULES
from backend.app.agents.verification import outreach_violations
from backend.app.db.models import AgentToolCall, KnowledgeEntry
from backend.app.services import knowledge as kb

from .conftest import MEMBER, login
from .fakes import ScriptedClient, drafts as fake_drafts, strategy as fake_strategy
from .test_mission import run_flow

GALA = "Plan a 150-person Manhattan fundraising gala and check whether we can afford it."
SPIN = "Plan a spin class fundraiser in Manhattan for 120 riders and check what it would cost."
RESEARCH = "Find eating disorder research initiatives"

FACTS = [
    {"section": "signature_events", "title": "Lantern Night Gala (test)", "body": "The foundation's annual seated gala in Manhattan.",
     "details": {"venue": "Juniper Hall (test)", "catering": "An outside caterer from the hometown",
                 "entertainment": "Live band, about $4,000", "expenses": "About $28,000 in total",
                 "what_should_change": "Book the band earlier"},
     "verification": "estimate", "source": "Board member (test)"},
    {"section": "signature_events", "title": "Pedal for Hope (test)", "body": "Spin class fundraiser held each November.",
     "details": {"venue": "Cadence Studio (test)", "ticket_pricing": "$45 including a shirt",
                 "extras": "Donations by mobile payment", "what_worked": "Riders brought friends"},
     "verification": "board_reported", "source": "Board member (test)", "share_externally": True},
    {"section": "vendors_venues", "title": "Juniper Hall (test)", "body": "Event venue used for the gala.",
     "details": {"category": "Event venue", "events": "Lantern Night Gala (test)",
                 "relationship_status": "Past venue; no current agreement"}, "verification": "board_reported"},
    {"section": "community_audience", "title": "Hometown families (test)",
     "details": {"connection": "Most guests at community events are families and friends from the hometown"},
     "verification": "board_reported"},
    {"section": "communication", "title": "Introductions (test)",
     "details": {"preference": "Open with the founding story in one sentence; quote the philosophy at most once"},
     "verification": "board_reported", "share_externally": True},
    {"section": "board", "title": "Jordan Example (test)",
     "details": {"role": "Treasurer", "reviews": "finance and budgets", "contact": "jordan.example@example.org"},
     "verification": "board_reported"},
]


def add_facts(client, facts=FACTS) -> dict[str, int]:
    login(client)
    ids = {}
    for f in facts:
        r = client.post("/api/knowledge", json=f)
        assert r.status_code == 201, r.text
        ids[f["title"]] = r.json()["id"]
    return ids


def calls_for(fake: ScriptedClient, schema: str) -> str:
    return "\n".join(str(c.get("input", "")) + str(c.get("instructions", "")) for c in fake.schema_calls(schema))


def tool_calls(client, run_id: int, tool: str = "read_foundation_knowledge") -> list[AgentToolCall]:
    with client.app.state.db.session() as s:
        return s.scalars(select(AgentToolCall).where(AgentToolCall.run_id == run_id, AgentToolCall.tool_name == tool)).all()


# ── Storage, provenance, and permissions ─────────────────────────────────────────


def test_every_fact_keeps_source_contributor_dates_and_status(client):
    ids = add_facts(client)
    body = client.get("/api/knowledge").json()
    gala = next(e for e in body["entries"] if e["id"] == ids["Lantern Night Gala (test)"])
    assert gala["source"] == "Board member (test)" and gala["contributor"] == "Tauhid Zaman"
    assert gala["recorded_at"] and gala["updated_at"] and gala["verification"] == "estimate"
    assert {s["key"] for s in body["sections"]} == set(kb.SECTION_KEYS) and len(body["sections"]) == 10
    # The identity from the repository's mission configuration is seeded; a fresh clone has no real records.
    titles = {e["title"] for e in body["entries"]}
    assert {"Foundation identity", "Guiding philosophy", "Mission areas"} <= titles
    assert body["can_edit"] and body["can_verify"]


def test_members_add_and_correct_but_only_the_chair_or_treasurer_verifies_or_removes(client):
    ids = add_facts(client)
    client.post("/api/auth/logout")
    login(client, MEMBER)
    made = client.post("/api/knowledge", json={"section": "community_audience", "title": "Volunteers (test)",
                                               "body": "Friends staff check-in.", "verification": "verified"}).json()
    assert made["verification"] == "board_reported"  # a member cannot mark a fact verified
    assert client.post(f"/api/knowledge/{made['id']}/verify", json={"verification": "verified"}).status_code == 403
    assert client.post(f"/api/knowledge/{made['id']}/remove", json={"reason": "wrong"}).status_code == 403
    board = next(e for e in client.get("/api/knowledge").json()["entries"] if e["title"] == "Jordan Example (test)")
    assert board["details"]["contact"] == "(visible to the chair)"  # contacts only for the chair
    client.post("/api/auth/logout")
    login(client)
    ok = client.post(f"/api/knowledge/{made['id']}/verify", json={"verification": "verified"}).json()
    assert ok["verification"] == "verified" and ok["verified_by"] == "Tauhid Zaman" and ok["verified_at"]
    gone = client.post(f"/api/knowledge/{ids['Juniper Hall (test)']}/remove", json={"reason": "Inaccurate (test)"}).json()
    assert gone["status"] == "removed" and gone["removed_reason"] == "Inaccurate (test)"
    with client.app.state.db.session() as s:  # a removed fact never reaches an agent
        pack = kb.retrieve(s, 1, agent="fundraising_events", query="gala venue Juniper Hall")
    assert "Juniper Hall (test)" not in {f["title"] for f in pack["facts"]}
    with client.app.state.db.session() as s:
        assert s.get(KnowledgeEntry, ids["Juniper Hall (test)"]) is not None  # kept for the record, with the reason


def test_past_fundraisers_link_to_our_legacy_instead_of_duplicating(client):
    login(client)
    events = client.get("/api/knowledge").json()["legacy_events"]
    dinner = next(e for e in events if e["name"].startswith("Butterfly Benefit Dinner"))
    made = client.post(f"/api/knowledge/from-legacy/{dinner['id']}")
    assert made.status_code == 201 and made.json()["historical_event_id"] == dinner["id"]
    assert made.json()["source"] == f"Our Legacy record #{dinner['id']}" and made.json()["is_demo"]
    assert client.post(f"/api/knowledge/from-legacy/{dinner['id']}").status_code == 409


def test_blank_template_and_import(client):
    login(client)
    t = client.get("/api/knowledge/template").json()
    assert set(t["sections"]) == set(kb.SECTION_KEYS)
    assert all(v == "" for v in t["entries"][0]["details"].values()) and t["entries"][0]["title"] == ""
    got = client.post("/api/knowledge/import", json={"entries": [
        {"section": "relationships", "title": "Example Helpline (test)", "body": "Featured at a past event.", "verification": "estimate"},
        {"section": "not_a_section", "title": "ignored"}]}).json()
    assert got == {"added": 1, "updated": 0}


def test_samples_give_way_to_real_knowledge_in_the_same_section(client):
    add_facts(client)
    with client.app.state.db.session() as s:
        titles = {e.title for e in kb.active_entries(s, 1)}
    assert "Butterfly Benefit Dinner (sample)" not in titles and "Lantern Night Gala (test)" in titles  # real gala replaces the sample
    assert "Nourish NY Eating Disorder Research Network (synthetic)" in titles  # no real relationship yet, so the sample stays


def test_retrieval_is_task_relevant_and_limited_to_the_agents_sections(client):
    add_facts(client)
    with client.app.state.db.session() as s:
        events = kb.retrieve(s, 1, agent="fundraising_events", query=SPIN)
        finance = kb.retrieve(s, 1, agent="financial_analysis", query=GALA)
        outreach = kb.retrieve(s, 1, agent="partnerships_outreach", query="venue inquiry Juniper Hall (test) gala")
    assert events["facts"][0]["title"] == "Pedal for Hope (test)"  # TEST B: the cycling history, not the gala, comes first
    assert all(f["section_key"] in kb.AGENT_SECTIONS["financial_analysis"] for f in finance["facts"])
    assert "Jordan Example (test)" not in {f["title"] for f in events["facts"] + finance["facts"] + outreach["facts"]}
    assert events["est_tokens"] > 0 and events["returned"] <= 6 and events["considered"] > events["returned"]
    assert {"Foundation identity", "Juniper Hall (test)"} <= {f["title"] for f in outreach["facts"]}
    preview = client.get("/api/knowledge/preview", params={"agent": "fundraising_events", "query": SPIN}).json()
    assert preview["facts"][0]["title"] == "Pedal for Hope (test)"


# ── Test A: gala planning recognizes the foundation's own gala and its lessons ─────


def test_A_gala_plan_uses_the_foundations_gala_history(client):
    ids = add_facts(client)
    gala_id = f"KB-{ids['Lantern Night Gala (test)']}"

    def cites(p, kw):
        out = fake_strategy(p, kw)
        given = [f["id"] for f in (p.get("foundation_knowledge") or {}).get("facts", [])]
        return {**out, "knowledge_used": [gala_id, "KB-99999"] if gala_id in given else [],
                "prior_vendors_considered": ["Juniper Hall (test): not among the options; ask about availability first."]}

    fake = ScriptedClient({"EventStrategyOutput": cites})
    run, steps, _ = run_flow(client, GALA, intent="plan_event", plan_id=1, script=fake)
    assert run.status in ("completed", "completed_with_warnings"), run.error
    events_prompt = calls_for(fake, "EventStrategyOutput")
    assert "Lantern Night Gala (test)" in events_prompt and "Book the band earlier" in events_prompt
    assert KNOWLEDGE_RULES.splitlines()[0] in events_prompt
    venues = next(s for s in steps if s.step_key == "venues")
    assert gala_id in venues.payload["foundation_passed"]  # the Orchestrator passed the gala fact to Events
    assert venues.result["data"]["knowledge_used"] == [gala_id]  # an id it was never given is dropped
    assert venues.result["data"]["prior_vendors_considered"]
    assert any("Lantern Night Gala (test)" in t.result_summary for t in tool_calls(client, run.id))
    assert "Lantern Night Gala (test)" in calls_for(fake, "BoardRecommendation")  # the final answer can draw on it too


def test_A_without_the_knowledge_base_the_same_plan_gets_none_of_it(client):
    add_facts(client)
    fake = ScriptedClient()
    run, steps, _ = run_flow(client, GALA, intent="plan_event", plan_id=1, script=fake, options={"use_knowledge": False})
    assert run.status in ("completed", "completed_with_warnings"), run.error
    assert "Lantern Night Gala (test)" not in "\n".join(str(c.get("input", "")) for c in fake.calls)
    assert run.result["foundation_context"]["facts"] == []
    assert run.result["recommendation"]["knowledge_used"] == []  # nothing supplied, so nothing can be cited
    assert all("switched off" in t.result_summary.lower() for t in tool_calls(client, run.id))


# ── Test B: a cycling fundraiser retrieves the cycling history ───────────────────


def test_B_cycling_fundraiser_retrieves_the_cycling_event(client):
    ids = add_facts(client)
    fake = ScriptedClient()
    run, steps, _ = run_flow(client, SPIN, intent="plan_event", script=fake)
    assert run.status in ("completed", "completed_with_warnings"), run.error
    spin_id = f"KB-{ids['Pedal for Hope (test)']}"
    intake = next(s for s in steps if s.step_key == "intake")
    found = [f["id"] for f in intake.result["data"]["foundation_context"]["facts"]]
    assert spin_id in found and found.index(spin_id) < found.index(f"KB-{ids['Lantern Night Gala (test)']}")
    venues = next(s for s in steps if s.step_key == "venues")
    assert spin_id in venues.payload["foundation_passed"]
    assert "Pedal for Hope (test)" in calls_for(fake, "EventStrategyOutput") and "$45 including a shirt" in calls_for(fake, "EventStrategyOutput")


def test_B_a_spin_class_is_not_planned_as_a_gala():
    from backend.app.agents.orchestrator import canonical_event_type, keyword_analysis
    a = keyword_analysis("Plan a spin class fundraiser in Manhattan this November for 50 riders.")
    assert (a.intent, a.attendance, a.event_type) == ("plan_event", 50, "spin class")
    assert canonical_event_type("cycling fundraiser") == "spin class" and canonical_event_type("fundraising gala") == "gala"


# ── Test C: a known eating-disorder organization is not presented as a new discovery ─


def test_C_research_recognizes_a_recorded_relationship(client):
    login(client)
    fake = ScriptedClient()
    run, steps, _ = run_flow(client, RESEARCH, intent="mission_discovery", script=fake)
    assert run.status in ("completed", "completed_with_warnings"), run.error
    research = next(s for s in steps if s.step_key == "research")
    assert research.result["data"]["already_known"] == ["Nourish NY Eating Disorder Research Network (synthetic)"]
    nourish = next(f for f in run.result["findings"] if f["name"].startswith("Nourish NY"))
    assert nourish["known_relationship"]["relationship_type"] == "historical collaboration"
    assert not nourish["known_relationship"]["formal_partnership"]
    others = [f for f in run.result["findings"] if not f["name"].startswith("Nourish NY")]
    assert others and all(f["known_relationship"] is None for f in others)  # unfamiliar organizations are still recommended
    assert any("Already known to the foundation" in f["claim"] for f in research.result["findings"])
    assert "Nourish NY Eating Disorder Research Network (synthetic)" in calls_for(fake, "MissionAnalysis")
    cards = client.get("/api/opportunities").json()["opportunities"]
    known = [o for o in cards if (o.get("known_relationship") or {}).get("organization", "").startswith("Nourish NY")]
    assert known, "the opportunity card shows the recorded relationship"


def test_C_drafts_acknowledge_a_known_organization_and_never_invent_one():
    known = {"formal_partnership": False, "summary": "Already known"}
    assert outreach_violations("We valued our past collaboration at the spring dinner.", None, known) == []
    assert outreach_violations("We valued our past collaboration at the spring dinner.", None, None)  # unknown: rejected
    assert outreach_violations("Building on our ongoing partnership, we...", None, known)  # not a formal partnership
    assert outreach_violations("Following our conversation last week, ...", None, known)  # no recorded conversation


# ── Test D: outreach describes the foundation from its facts, and keeps internal facts out ─


def test_D_outreach_uses_foundation_facts_and_keeps_internal_costs_out(client):
    add_facts(client)

    def leaky(p, kw):
        out = fake_drafts(p, kw)
        for d in out["drafts"]:
            d["body"] = d["body"].replace("Hello", "Our last gala cost about $28,000. Hello")
        return out

    fake = ScriptedClient({"DraftsOutput": leaky})
    run, steps, _ = run_flow(client, GALA, intent="plan_event", plan_id=1, script=fake)
    outreach = next(s for s in steps if s.step_key == "outreach")
    prompt = calls_for(fake, "DraftsOutput")
    assert "Foundation identity" in prompt and "shareable_in_outreach" in prompt
    assert "Adapt the introduction to the recipient" in prompt
    assert outreach.result["data"]["drafts"] == []  # every draft quoting the internal $28,000 cost was dropped
    assert any("$28,000" in w for w in outreach.result["warnings"])


ATELIER = {"section": "vendors_venues", "title": "Chelsea Atelier (synthetic)", "body": "Hosted a past spring reception (test).",
           "details": {"category": "Event venue", "relationship_status": "Past venue; no current agreement"},
           "verification": "board_reported"}


def test_D_a_venue_the_foundation_used_before_is_recognized_in_the_inquiry(client):
    add_facts(client, FACTS + [ATELIER])

    def acknowledging(p, kw):
        out = fake_drafts(p, kw)
        known = {t["target_id"] for t in p["targets"] if t.get("known_relationship")}
        for d in out["drafts"]:
            if d["target_id"] in known:
                d["body"] = d["body"].replace("We are writing", "We were glad to hold our spring reception with you before, and we are writing")
        return out

    fake = ScriptedClient({"DraftsOutput": acknowledging})
    run, steps, _ = run_flow(client, GALA, intent="plan_event", plan_id=1, script=fake)
    outreach = next(s for s in steps if s.step_key == "outreach")
    atelier = [d for d in outreach.result["data"]["drafts"] if d["recipient"] == "Chelsea Atelier (synthetic)"]
    assert atelier and atelier[0]["known_relationship"].lower().startswith("already known to the foundation (past venue")
    assert '"known_relationship"' in calls_for(fake, "DraftsOutput")


def test_D_a_known_organization_never_gets_a_first_introduction(client):
    add_facts(client, FACTS + [ATELIER])
    def generic(p, kw):  # ignores known_relationship: every draft reads as a first introduction
        return fake_drafts({**p, "targets": [{**t, "known_relationship": None} for t in p["targets"]]}, kw)

    run, steps, _ = run_flow(client, GALA, intent="plan_event", plan_id=1, script=ScriptedClient({"DraftsOutput": generic}))
    outreach = next(s for s in steps if s.step_key == "outreach")
    assert "Chelsea Atelier (synthetic)" not in {d["recipient"] for d in outreach.result["data"]["drafts"]}
    assert any("reads as a first introduction" in w for w in outreach.result["warnings"])


# ── Test E: Finance keeps demo books apart from real finances ────────────────────


def test_E_finance_labels_demo_books_and_never_uses_history_as_funds(client):
    add_facts(client)
    fake = ScriptedClient()
    run, steps, _ = run_flow(client, GALA, intent="plan_event", plan_id=1, script=fake)
    finance = next(s for s in steps if s.step_key == "finance")
    sources = finance.result["data"]["data_sources"]
    assert sources["ledger"]["kind"] == "demo" and sources["ledger"]["demo_rows"] == 22
    assert any("Lantern Night Gala (test)" in x for x in sources["board_estimates"])  # an estimate, never a verified figure
    assert sources["verified_history"] == [] and "Never infer" in sources["rule"]
    assert any("synthetic demonstration data" in f["claim"] for f in finance.result["findings"])
    assert finance.result["data"]["position"]["available_planning_budget_usd"] == 34640.0  # the $28,000 estimate is not money
    prompt = calls_for(fake, "FinanceNarrative")
    assert "data_sources" in prompt and "Keep four kinds apart" in prompt
    review_run, review_steps, _ = run_flow(client, "Review our finances", intent="financial_review", script=ScriptedClient())
    review = next(s for s in review_steps if s.step_key == "finance")
    assert review.result["data"]["data_sources"]["ledger"]["kind"] == "demo"


# ── Test F: the Boss Agent passes each specialist only its share and integrates the results ─


def test_F_orchestrator_passes_context_by_section_and_suggests_a_reviewer(client):
    ids = add_facts(client)
    fake = ScriptedClient()
    run, steps, _ = run_flow(client, GALA, intent="plan_event", plan_id=1, script=fake)
    by_key = {s.step_key: s for s in steps}
    titles = {f"KB-{v}": k for k, v in ids.items()}
    for key, agent in (("lessons", "event_intelligence"), ("venues", "fundraising_events"), ("finance", "financial_analysis"),
                       ("outreach", "partnerships_outreach")):
        passed = by_key[key].payload.get("foundation_passed", [])
        with client.app.state.db.session() as s:
            sections = {s.get(KnowledgeEntry, int(i.removeprefix("KB-"))).section for i in passed}
        assert sections <= set(kb.AGENT_SECTIONS[agent]), (key, sections)
    assert f"KB-{ids['Jordan Example (test)']}" not in str([s.payload for s in steps])  # the board entry stays with the Boss Agent
    ctx = run.result["foundation_context"]
    assert {"lessons", "venues", "finance", "outreach"} <= set(ctx["supplied_to"])
    assert ctx["est_tokens"] > 0 and ctx["facts"]
    assert "foundation_knowledge" in calls_for(fake, "BoardRecommendation")
    # Privacy: the board member's contact never reaches any model.
    assert "jordan.example@example.org" not in "\n".join(str(c.get("input", "")) for c in fake.calls)
    review, _, _ = run_flow(client, "Review our finances", intent="financial_review", script=ScriptedClient())
    assert review.result["review_by"]["reviewers"][0]["name"] == "Jordan Example (test)"
    assert "nothing has been assigned" in review.result["review_by"]["note"].lower()
    assert titles  # ids map back to the test facts


def test_board_names_never_leave_in_a_web_search(client):
    add_facts(client)
    with client.app.state.db.session() as s:
        terms = kb.private_terms(s, 1)
    assert "Jordan Example (test)" in terms and "jordan.example@example.org" in terms


def test_research_pages_can_be_opened_from_the_trace_but_fixtures_cannot():
    from types import SimpleNamespace as NS

    from backend.app.api.routes.runs import public_page
    live = NS(tool_name="fetch_source", arguments={"url": "https://www.example-charity.test/donate", "source_id": "web:1"})
    fixture = NS(tool_name="fetch_source", arguments={"url": "https://example.org/synthetic/organizations/x"})
    other = NS(tool_name="search_web", arguments={"query": "eating disorder research"})
    contact = NS(tool_name="lookup_inquiry_details", arguments={"name": "A venue", "website": "https://venue.test/"})
    assert public_page(live) == "https://www.example-charity.test/donate" and public_page(contact) == "https://venue.test/"
    assert public_page(fixture) is None and public_page(other) is None
