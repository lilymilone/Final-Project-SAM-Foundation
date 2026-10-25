"""Multi-agent behavior: routing, permissions, structured output, revisions, loop limits."""

from __future__ import annotations

import time

import pytest
from sqlalchemy import select

from backend.app.agents.contracts import AgentName, AgentResult, AgentTask
from backend.app.agents.orchestrator import INTENT_AGENTS, Orchestrator, keyword_analysis
from backend.app.agents.outputs import BoardRecommendation, RequestAnalysis
from backend.app.agents.registry import AGENT_SPECS, AGENTS_BY_NAME
from backend.app.agents.verification import verify_workflow
from backend.app.ai.providers import AIProvider
from backend.app.core.permissions import permissions_for
from backend.app.db.models import AgentHandoff, AgentRun, AgentToolCall, EventPlan, HistoricalLesson, ModelUsage, OutreachDraft
from backend.app.safety.policy import PROHIBITED_ACTIONS
from backend.app.services import calculators as calc
from backend.app.tools.registry import ToolPermissionError
from backend.app.tools.web import UnsafeURLError, check_url

from .conftest import MEMBER, login
from .fakes import ScriptedClient

GALA = "Plan a 150-person Manhattan fundraising gala, using lessons from our previous events and checking whether we can afford it."


def gala_plan_id(app) -> int:
    with app.state.db.session() as s:
        return s.scalar(select(EventPlan.id).where(EventPlan.name.like("Manhattan Spring Gala%")))


def run_sync(client, request=GALA, intent=None, mode="synthetic", role="chair", plan=True, script=None):
    """Create a run row and execute the workflow synchronously with the scripted model."""
    app = client.app
    fake = script or ScriptedClient()
    app.state.provider = AIProvider("openai", fake)
    db = app.state.db
    with db.transaction() as s:
        run = AgentRun(organization_id=1, user_id=1 if role == "chair" else 2, workflow_type=intent or "auto", request_text=request,
                       status="queued", strategy="auto", provider="openai", budget_usd=app.state.settings.workflow_budget_usd,
                       research_mode=mode)
        s.add(run)
        s.flush()
        run_id = run.id
    app.state.workflows.start(run_id, user_id=1, organization_id=1, permissions=permissions_for(role), strategy="auto",
                              research_mode=mode, request=request, intent_hint=intent,
                              event_plan_id=gala_plan_id(app) if plan else None, synchronous=True)
    with db.session() as s:
        run = s.get(AgentRun, run_id)
        steps = s.scalars(select(AgentHandoff).where(AgentHandoff.run_id == run_id).order_by(AgentHandoff.id)).all()
    return run, steps, fake


# ── Routing ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("text,intent", [
    (GALA, "plan_event"),
    ("Find eating disorder research initiatives we could support", "mission_discovery"),
    ("Draft sponsor outreach to local wellness businesses", "partnership_outreach"),
    ("Review our finances and reserve", "financial_review"),
    ("Which donations still need acknowledgment letters?", "donations_review"),
    ("What lessons can we learn from our previous events?", "event_learning"),
    ("What's the weather tomorrow?", "unsupported"),
])
def test_keyword_routing(text, intent):
    assert keyword_analysis(text).intent == intent


def test_routing_extracts_event_details():
    a = keyword_analysis(GALA)
    assert (a.attendance, a.city, a.event_type) == (150, "Manhattan, New York, NY", "gala")


def test_each_intent_uses_its_own_specialists():
    assert INTENT_AGENTS["plan_event"] == [AgentName.EVENT_INTELLIGENCE, AgentName.FUNDRAISING_EVENTS,
                                           AgentName.FINANCIAL_ANALYSIS, AgentName.PARTNERSHIPS_OUTREACH]
    assert INTENT_AGENTS["donations_review"] == [AgentName.DONATIONS_COMPLIANCE]
    assert INTENT_AGENTS["unsupported"] == []


def test_model_routing_is_used_and_recorded(client):
    run, steps, fake = run_sync(client)
    intake = steps[0]
    assert intake.to_agent == "orchestrator" and intake.from_agent == "board"
    assert intake.result["data"]["routing"] == "model"
    assert len(fake.schema_calls("RequestAnalysis")) == 1


def test_invalid_model_classification_falls_back_to_keywords(client):
    run, steps, fake = run_sync(client, script=ScriptedClient({"RequestAnalysis": lambda p, kw: "not json"}))
    assert steps[0].result["data"]["routing"] == "keyword"
    assert len(fake.schema_calls("RequestAnalysis")) == 3  # 1 try + 2 bounded retries
    assert run.status in ("completed", "completed_with_warnings")


# ── Structured output validation ─────────────────────────────────────────────────


def test_structured_output_retries_then_succeeds(client):
    state = {"n": 0}

    def flaky(p, kw):
        state["n"] += 1
        return '{"summary": "missing fields"}' if state["n"] == 1 else ScriptedClient().handlers["LessonsOutput"](p, kw)

    run, steps, fake = run_sync(client, script=ScriptedClient({"LessonsOutput": flaky}))
    lessons = next(s for s in steps if s.step_key == "lessons")
    assert lessons.status == "completed"
    assert "REJECTED" in fake.schema_calls("LessonsOutput")[1]["input"]
    with client.app.state.db.session() as s:
        attempts = s.scalars(select(ModelUsage.attempt).where(ModelUsage.handoff_id == lessons.id)).all()
    assert attempts == [1, 2]


def test_agent_fails_cleanly_after_bounded_retries(client):
    run, steps, _ = run_sync(client, script=ScriptedClient({"LessonsOutput": lambda p, kw: "{}"}))
    lessons = next(s for s in steps if s.step_key == "lessons")
    assert lessons.status == "failed" and "after 3 attempt" in lessons.error
    assert any(s.step_key == "venues" for s in steps)  # the workflow carries on without lessons


def test_results_are_valid_contract_models(client):
    run, steps, _ = run_sync(client)
    for s in steps:
        AgentResult.model_validate(s.result)
    BoardRecommendation.model_validate(run.result["recommendation"])
    RequestAnalysis.model_validate(run.result["analysis"])


def test_template_validator_requires_merge_fields(client):
    bad = {"summary": "x", "subject": "Thanks", "body": "Dear friend, thank you.", "review_items": []}
    run, steps, fake = run_sync(client, request="Review donations and draft acknowledgments", intent="donations_review", plan=False,
                                script=ScriptedClient({"AcknowledgmentTemplate": lambda p, kw: bad}))
    step = next(s for s in steps if s.to_agent == "donations_compliance")
    assert step.status == "failed"
    assert "merge fields" in fake.schema_calls("AcknowledgmentTemplate")[1]["input"]


# ── The controlled synthetic example: revision after Finance + history feedback ──


def test_gala_collaboration_and_revision(client):
    run, steps, _ = run_sync(client)
    assert run.status == "completed", run.error
    keys = [s.step_key for s in steps]
    assert keys == ["intake", "lessons", "venues", "finance", "evaluate", "venues_revision_1", "finance_revision_1",
                    "evaluate_revision_1", "outreach_decision", "outreach", "recommendation", "verification"]

    first_finance = steps[keys.index("finance")]
    assert first_finance.status == "needs_revision"
    conflict_types = {c["type"] for c in first_finance.result["data"]["conflicts"]}
    assert {"over_budget_limit", "upfront_cash_exceeds_available"} <= conflict_types

    revision = steps[keys.index("venues_revision_1")]
    assert revision.kind == "revision" and revision.revision_round == 1 and revision.from_agent == "orchestrator"
    constraints = {c["name"]: c.get("value") for c in revision.payload["constraints"]}
    assert constraints["max_total_usd"] == 18000
    assert constraints["max_upfront_usd"] == pytest.approx(9938.0)
    assert constraints["min_contingency_pct"] == 0.15  # historical feedback from Event Intelligence
    assert "history:lock_guest_count" in constraints

    second = steps[keys.index("finance_revision_1")]
    assert second.status == "completed" and second.result["data"]["conflicts"] == []
    assert second.result["data"]["verdict"] == "affordable_with_conditions"  # below the $40,000 target: a warning, not a conflict
    assert second.result["data"]["option_id"] == "chelsea-atelier:reception"
    assert steps[keys.index("evaluate")].status == "needs_revision" and steps[keys.index("evaluate_revision_1")].status == "completed"

    history = run.result["revision_history"]
    assert [h["verdict"] for h in history] == ["not_affordable_as_planned", "affordable_with_conditions"]
    assert run.result["original_plan"]["venue"] != run.result["revised_plan"]["venue"]
    assert {r["source"] for r in run.result["revision_reasons"]} >= {"finance"}
    assert run.result["verification"]["passed"] is True
    assert any("synthetic" in c.lower() for c in run.result["recommendation"]["caveats"])


def test_finance_numbers_are_deterministic(client):
    run, steps, _ = run_sync(client)
    model = run.result["finance"]["model"]
    assert model["total_cost_usd"] == 16100.0  # (1,800 + 150×58 + 1,500 + 600 + 900 + 500) × 1.15
    assert model["upfront_cash_usd"] == 4250.0  # 0.3 × (1,800 + 8,700) + 600 marketing + 500 insurance
    assert run.result["finance"]["position"]["available_planning_budget_usd"] == 9938.0
    assert model["break_even_attendance"] == 6
    assert model["scenarios"]["base"]["net_usd"] == 30742.5


def test_outputs_saved_lessons_with_evidence_and_unsent_drafts(client):
    run, steps, _ = run_sync(client)
    with client.app.state.db.session() as s:
        lessons = s.scalars(select(HistoricalLesson).where(HistoricalLesson.run_id == run.id)).all()
        drafts = s.scalars(select(OutreachDraft).where(OutreachDraft.run_id == run.id)).all()
    assert lessons and all(l.evidence for l in lessons)
    assert drafts and {d.status for d in drafts} == {"draft"}
    assert {d.draft_type for d in drafts} >= {"venue_inquiry"}


def test_invented_lesson_evidence_is_dropped(client):
    def fake_lessons(p, kw):
        out = ScriptedClient().handlers["LessonsOutput"](p, kw)
        out["lessons"].append({"kind": "recommendation", "theme": "invented", "text": "Invented lesson.", "evidence_event_ids": [999],
                               "evidence_reflection_ids": [888], "confidence": "high"})
        return out

    run, steps, _ = run_sync(client, script=ScriptedClient({"LessonsOutput": fake_lessons}))
    lessons = next(s for s in steps if s.step_key == "lessons")
    assert all(l["text"] != "Invented lesson." for l in lessons.result["data"]["lessons"])
    assert any("no valid evidence" in w for w in lessons.result["warnings"])


# ── Permissions ──────────────────────────────────────────────────────────────────


def test_allow_lists_are_narrow_and_distinct():
    finance = set(AGENTS_BY_NAME[AgentName.FINANCIAL_ANALYSIS].allowed_tools)
    donations = set(AGENTS_BY_NAME[AgentName.DONATIONS_COMPLIANCE].allowed_tools)
    outreach = set(AGENTS_BY_NAME[AgentName.PARTNERSHIPS_OUTREACH].allowed_tools)
    assert not finance & donations and "read_donations" not in outreach and "read_financial_records" not in outreach
    for spec in AGENT_SPECS:
        assert not set(spec.allowed_tools) & set(PROHIBITED_ACTIONS)
        assert not any("send" in t or "email" in t or "delegate" in t for t in spec.allowed_tools), spec.name


def test_specialists_cannot_delegate():
    orch = Orchestrator()
    for name, agent in orch.agents.items():
        assert not hasattr(agent, "dispatch"), name
    assert hasattr(orch, "dispatch")


def test_agent_cannot_use_another_agents_tool(client):
    run, steps, fake = run_sync(client)
    from backend.app.agents.runtime import RunContext
    from backend.app.agents.specialists.financial_analysis import FinancialAnalysisAgent
    from backend.app.ai.budget import WorkflowBudget
    from backend.app.ai.router import ModelRouter
    from backend.app.tools.catalog import build_tool_registry

    app = client.app
    ctx = RunContext(run_id=run.id, organization_id=1, user_id=1, user_permissions=permissions_for("chair"), strategy="auto",
                     research_mode="synthetic", db=app.state.db, router=ModelRouter("openai"), budget=WorkflowBudget(1, 5),
                     settings=app.state.settings, llm=None)
    ctx.tools = build_tool_registry(ctx)
    with pytest.raises(ToolPermissionError):
        FinancialAnalysisAgent().tool(ctx, "read_donations")
    with app.state.db.session() as s:
        denied = s.scalars(select(AgentToolCall).where(AgentToolCall.allowed.is_(False))).all()
    assert any(d.agent == "financial_analysis" and d.tool_name == "read_donations" for d in denied)


def test_member_workflow_skips_finance_by_permission(client):
    run, steps, _ = run_sync(client, role="member")
    finance_steps = [s for s in steps if s.to_agent == "financial_analysis"]
    assert finance_steps and all(s.status == "refused" and "view_financials" in s.error for s in finance_steps)
    assert run.result["finance"] is None  # no ledger figures reach a member's result
    assert any("Skipped for your role" in c for c in run.result["recommendation"]["caveats"])


# ── Loop prevention ──────────────────────────────────────────────────────────────


def test_revision_rounds_are_capped(make_client):
    stubborn = ScriptedClient({"EventStrategyOutput": lambda p, kw: {
        **ScriptedClient().handlers["EventStrategyOutput"]({**p, "constraints": []}, kw)}})
    client = make_client(max_revisions=1)
    # Make every option unaffordable so the conflict can't be resolved.
    client.app.state.db  # noqa: B018
    with client.app.state.db.transaction() as s:
        s.get(EventPlan, gala_plan_id(client.app)).budget_limit_usd = 5000
    run, steps, _ = run_sync(client, script=stubborn)
    revisions = [s for s in steps if s.step_key.startswith("venues_revision")]
    assert len(revisions) == 1
    assert run.result["unresolved_conflicts"]
    assert any("loop limit" in c for c in run.result["recommendation"]["caveats"])


def test_zero_revisions_allowed(make_client):
    run, steps, _ = run_sync(make_client(max_revisions=0))
    assert not any(s.kind == "revision" and s.step_key.startswith("venues") for s in steps)


def test_handoff_cap_stops_runaway_runs(make_client):
    run, steps, _ = run_sync(make_client(max_handoffs_per_run=3))
    assert run.status == "stopped" and "limit of 3 handoffs" in run.error
    assert len(steps) == 3


def test_model_call_cap_stops_run(make_client):
    run, steps, _ = run_sync(make_client(max_model_calls_per_workflow=2))
    assert run.status == "stopped"
    assert run.model_calls <= 2


# ── Verification ─────────────────────────────────────────────────────────────────


def test_verification_catches_invented_figures_and_action_claims(client):
    rec = BoardRecommendation(headline="Go", recommendation="We have booked the venue for $99,999.", rationale=[], options=[],
                              risks=[], decisions_for_board=[], next_steps=[], lessons_applied=[], caveats=[])
    report = verify_workflow(client.app.state.db, 0, {}, rec, {15525.0}, set())
    by_name = {c["name"]: c for c in report["checks"]}
    assert by_name["Every dollar figure traces to a calculation"]["passed"] is False
    assert by_name["No claims that anything was sent, booked, or paid"]["passed"] is False
    assert report["passed"] is False


def test_recommendation_is_corrected_once_after_failed_verification(client):
    state = {"n": 0}

    def sloppy(p, kw):
        state["n"] += 1
        out = ScriptedClient().handlers["BoardRecommendation"](p, kw)
        if state["n"] == 1:
            out["recommendation"] = "Budget $123,456 for the evening."
        return out

    run, steps, _ = run_sync(client, script=ScriptedClient({"BoardRecommendation": sloppy}))
    assert [s.step_key for s in steps][-3:] == ["recommendation", "recommendation_fix", "verification"]
    assert run.result["verification"]["passed"] is True


# ── Privacy, research safety, calculators ─────────────────────────────────────────


def test_donor_names_never_reach_the_model(client):
    run, steps, fake = run_sync(client, request="Review donations", intent="donations_review", plan=False)
    sent = " ".join(c["input"] for c in fake.calls)
    assert "Sample Donor" not in sent and "donor0" not in sent
    with client.app.state.db.session() as s:
        drafts = s.scalars(select(OutreachDraft).where(OutreachDraft.draft_type.in_(("donor_thank_you", "contribution_acknowledgment")))).all()
    assert drafts and all("Sample Donor" in d.body and "{{" not in d.body for d in drafts)
    tool_logs = [s for s in steps if s.to_agent == "donations_compliance"]
    with client.app.state.db.session() as s:
        summaries = s.scalars(select(AgentToolCall.result_summary).where(AgentToolCall.handoff_id == tool_logs[0].id)).all()
    assert not any("Sample Donor" in (x or "") for x in summaries)


def test_mission_discovery_labels_synthetic_sources(client):
    run, steps, _ = run_sync(client, request="Find eating disorder research initiatives", intent="mission_discovery", plan=False)
    research = next(s for s in steps if s.to_agent == "mission_discovery")
    assert research.status == "completed"
    assert {src["verification"] for src in research.result["sources"]} == {"synthetic"}
    assert all(f["verification"] == "synthetic" for f in run.result["findings"])


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://127.0.0.1:8000/api/health", "http://localhost/admin",
                                 "http://169.254.169.254/latest/meta-data", "http://10.0.0.7/", "ftp://example.org/x"])
def test_web_fetch_refuses_unsafe_urls(url):
    with pytest.raises(UnsafeURLError):
        check_url(url)


def test_calculators():
    b = calc.event_budget(venue_key="v", venue_name="V", event_format="reception", attendance=100, rental_usd=1000,
                          fnb_per_guest_usd=50, deposit_pct=0.5, production_usd=1000, contingency_pct=0.1)
    assert (b.subtotal_usd, b.total_usd, b.upfront_cash_usd) == (7000, 7700, 4000)
    pos = calc.financial_position([{"period": "2026-01", "kind": "expense", "amount_usd": 100},
                                   {"period": "2026-01", "kind": "reserve", "amount_usd": 1000}])
    assert pos["available_planning_budget_usd"] is None and "Not supported" in pos["available_planning_budget_basis"]


# ── API ─────────────────────────────────────────────────────────────────────────


def test_run_api_end_to_end_and_member_redaction(client):
    client.app.state.provider = AIProvider("openai", ScriptedClient())
    login(client)
    r = client.post("/api/runs", json={"request": GALA, "research_mode": "synthetic", "event_plan_id": gala_plan_id(client.app)})
    assert r.status_code == 202
    run_id = r.json()["run"]["id"]
    for _ in range(100):
        detail = client.get(f"/api/runs/{run_id}").json()
        if detail["run"]["status"] not in ("queued", "running"):
            break
        time.sleep(0.05)
    assert detail["run"]["status"] == "completed"
    assert detail["totals"]["revisions"] >= 2 and detail["totals"]["model_calls"] > 0
    text = str(detail)
    assert "Ground rules" not in text and "Use only the data" not in text  # no prompts in activity logs
    assert "fake-openai-key" not in text

    client.post("/api/auth/logout")
    login(client, email=MEMBER)
    member_view = client.get(f"/api/runs/{run_id}").json()
    fin = [s for s in member_view["steps"] if s["to_agent"] == "financial_analysis"]
    assert fin and all(s["redacted"] and s["result"] is None for s in fin)
    assert "finance" not in (member_view["result"] or {})


def test_only_one_active_run_and_permissions(client):
    client.app.state.provider = AIProvider("openai", ScriptedClient())
    login(client, email=MEMBER)
    assert client.post("/api/runs", json={"request": "Review our finances", "intent": "financial_review"}).status_code == 403
    with client.app.state.db.transaction() as s:
        s.add(AgentRun(organization_id=1, user_id=1, workflow_type="auto", request_text="x", status="running", strategy="auto"))
    assert client.post("/api/runs", json={"request": "Find research partners", "intent": "mission_discovery"}).status_code == 409


def test_member_cannot_run_without_provider(make_client):
    client = make_client("none")
    login(client)
    assert client.post("/api/runs", json={"request": "Find research partners"}).status_code == 400


def test_agent_task_contract_rejects_unknown_agent():
    with pytest.raises(Exception):
        AgentTask(run_id=1, step_key="x", agent="email_bot", objective="send")


def test_negated_action_statements_are_not_flagged():
    from backend.app.agents.verification import action_claims
    assert action_claims("Nothing has been sent, booked, or paid.") == []
    assert action_claims("No venue has been booked yet.") == []
    assert action_claims("The deposit has been paid.") == ["has been paid"]
    assert action_claims("We have booked Chelsea Atelier.") == ["We have booked"]


def test_event_type_is_canonicalized_for_format_and_history():
    from backend.app.agents.orchestrator import canonical_event_type
    assert canonical_event_type("Fundraising Gala") == "gala"
    assert canonical_event_type("benefit dinner") == "dinner"
    assert canonical_event_type(None) is None
