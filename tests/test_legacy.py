"""Our Legacy: records, append-only reflections, photos, lessons, metrics, history A/B."""

from __future__ import annotations

import struct
import time
import zlib

from sqlalchemy import select

from backend.app.ai.providers import AIProvider
from backend.app.db.models import AuditLog, BoardReflection, HistoricalEvent, HistoricalLesson
from backend.app.services import calculators as calc
from backend.app.services.comparison import compare_runs, comparison_markdown, run_snapshot

from .conftest import MEMBER, login
from .fakes import ScriptedClient
from .test_agents import run_sync

QUESTIONS = ("went_well", "challenges", "unexpected_costs", "attendee_feedback", "should_repeat", "do_differently", "advice")


def tiny_png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"\x00\xb6\x9a\xd9"  # one lavender pixel
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def dinner_id(client) -> int:
    events = client.get("/api/legacy/events").json()["events"]
    return next(e["id"] for e in events if e["name"].startswith("Butterfly Benefit Dinner"))


# ── Event records ────────────────────────────────────────────────────────────────


def test_create_and_edit_event_with_all_fields_and_computed_net(client):
    login(client)
    body = {"name": "Autumn Lantern Walk", "event_date": "2026-09-20", "event_type": "community walk", "venue": "River Park",
            "location": "Hartford, CT", "attendance": 140, "fundraising_goal_usd": 8000, "funds_raised_usd": 9100,
            "total_cost_usd": 2400, "sponsorship_usd": 1200, "sponsorship_info": "Two cafés", "summary": "Lantern walk", "notes": "First year"}
    r = client.post("/api/legacy/events", json=body)
    assert r.status_code == 201
    e = r.json()["event"]
    assert e["net_usd"] == 6700 and e["goal_pct"] == 113.8 and e["venue"] == "River Park"
    r = client.put(f"/api/legacy/events/{e['id']}", json={**body, "funds_raised_usd": 9500, "notes": "Corrected total"})
    assert r.status_code == 200 and r.json()["changed_fields"] == ["funds_raised_usd", "notes"]
    assert r.json()["event"]["net_usd"] == 7100
    with client.app.state.db.session() as s:
        log = s.scalars(select(AuditLog).where(AuditLog.action == "historical_event_edited")).one()
    assert log.detail["changes"]["funds_raised_usd"] == {"before": 9100.0, "after": 9500.0}


def test_event_validation_and_no_delete(client):
    login(client)
    assert client.post("/api/legacy/events", json={"name": "X"}).status_code == 422
    assert client.post("/api/legacy/events", json={"name": "Gala", "total_cost_usd": -1}).status_code == 422
    assert client.delete(f"/api/legacy/events/{dinner_id(client)}").status_code in (404, 405)


def test_gallery_lists_synthetic_events_with_labels(client):
    login(client)
    events = client.get("/api/legacy/events").json()["events"]
    assert len(events) >= 2 and all(e["is_demo"] for e in events)
    assert all("(sample)" in e["name"] for e in events)


# ── Reflections ───────────────────────────────────────────────────────────────


def test_structured_reflections_from_multiple_members_preserve_identity(client):
    login(client)
    eid = dinner_id(client)
    answers = {k: f"Chair answer to {k}" for k in QUESTIONS}
    assert client.post(f"/api/legacy/events/{eid}/reflections", json={**answers, "rating": 4}).status_code == 201
    client.post("/api/auth/logout")
    login(client, email=MEMBER)
    assert client.post(f"/api/legacy/events/{eid}/reflections", json={"went_well": "Member view", "rating": 5}).status_code == 201
    detail = client.get(f"/api/legacy/events/{eid}").json()
    mine = [r for r in detail["event"]["reflections"] if r["author"] in ("Avery Brooks", "Sam Rivera")]
    assert {r["author"] for r in mine} == {"Avery Brooks", "Sam Rivera"}
    chair = next(r for r in mine if r["author"] == "Avery Brooks")
    assert [a["question"] for a in chair["answers"]][0] == "What worked particularly well?"
    assert len(chair["answers"]) == 7 and chair["answers"][6]["answer"] == "Chair answer to advice" and chair["created_at"]


def test_reflections_are_append_only(client):
    login(client)
    eid = dinner_id(client)
    rid = client.get(f"/api/legacy/events/{eid}").json()["event"]["reflections"][0]["id"]
    for method in ("put", "patch", "delete"):
        r = getattr(client, method)(f"/api/legacy/events/{eid}/reflections/{rid}")
        assert r.status_code in (404, 405), method
    assert client.post(f"/api/legacy/events/{eid}/reflections", json={}).status_code == 422


def test_ai_analysis_never_modifies_reflections(client):
    with client.app.state.db.session() as s:
        before = {r.id: tuple(getattr(r, k) for k in QUESTIONS) for r in s.scalars(select(BoardReflection))}
    run_sync(client, request="What lessons can we learn from our previous events?", intent="event_learning", plan=False)
    with client.app.state.db.session() as s:
        after = {r.id: tuple(getattr(r, k) for k in QUESTIONS) for r in s.scalars(select(BoardReflection))}
    assert before == after


# ── Photos ────────────────────────────────────────────────────────────────────


def test_photo_upload_is_validated_private_and_removable(client):
    login(client)
    eid = dinner_id(client)
    png = tiny_png()
    r = client.post(f"/api/legacy/events/{eid}/photos", files={"file": ("dinner.png", png, "image/png")}, data={"caption": "Tables"})
    assert r.status_code == 201
    photo = r.json()["photo"]
    got = client.get(photo["url"])
    assert got.status_code == 200 and got.content == png and got.headers["content-type"] == "image/png"
    fake = client.post(f"/api/legacy/events/{eid}/photos", files={"file": ("evil.png", b"<script>alert(1)</script>", "image/png")})
    assert fake.status_code == 422
    big = client.post(f"/api/legacy/events/{eid}/photos", files={"file": ("big.png", png + b"0" * (5 * 1024 * 1024), "image/png")})
    assert big.status_code == 413
    client.post("/api/auth/logout")
    assert client.get(photo["url"]).status_code == 401
    login(client)
    assert client.delete(photo["url"]).status_code == 200
    assert client.get(photo["url"]).status_code == 404


# ── Event Intelligence: analysis, evidence, supersede, review, metrics ─────────────


def analyze(client, eid: int):
    client.app.state.provider = AIProvider("openai", ScriptedClient())
    r = client.post("/api/runs", json={"request": "Analyze this event and generate lessons", "intent": "event_learning",
                                       "historical_event_id": eid})
    assert r.status_code == 202
    run_id = r.json()["run"]["id"]
    for _ in range(100):
        d = client.get(f"/api/runs/{run_id}").json()
        if d["run"]["status"] not in ("queued", "running"):
            return d
        time.sleep(0.05)
    raise AssertionError("analysis did not finish")


def test_analyze_event_generates_linked_lessons_themes_and_disagreements(client):
    login(client)
    eid = dinner_id(client)
    d = analyze(client, eid)
    assert d["run"]["status"] == "completed"
    step = next(s for s in d["steps"] if s["to_agent"] == "event_intelligence")
    data = step["result"]["data"]
    assert data["focus_event_id"] == eid and data["comparison"]["sufficient"] is True
    assert data["themes"] and data["disagreements"] and data["weaknesses"] and data["recommendations"]
    detail = client.get(f"/api/legacy/events/{eid}").json()
    assert detail["lessons"], "lessons appear on the event page"
    for lesson in detail["lessons"]:
        assert lesson["evidence"] and all(ev["label"] for ev in lesson["evidence"])


def test_reanalysis_supersedes_unreviewed_but_keeps_adopted_lessons(client):
    login(client)
    eid = dinner_id(client)
    analyze(client, eid)
    first = client.get("/api/lessons").json()["lessons"]
    adopted = first[0]["id"]
    assert client.post(f"/api/lessons/{adopted}/review", json={"status": "adopted"}).status_code == 200
    analyze(client, eid)
    with client.app.state.db.session() as s:
        statuses = {l.id: l.status for l in s.scalars(select(HistoricalLesson))}
    assert statuses[adopted] == "adopted"
    assert all(statuses[l["id"]] == "superseded" for l in first if l["id"] != adopted)
    current = client.get("/api/lessons").json()["lessons"]
    assert all(l["status"] != "superseded" for l in current)


def test_impact_metrics_count_records_and_never_claim_improvement(client):
    login(client)
    m = client.get("/api/legacy/metrics").json()
    assert m["events_recorded"] == 3 and m["reflections_collected"] == 7 and m["lessons_generated"] == 0
    analyze(client, dinner_id(client))
    lessons = client.get("/api/lessons").json()["lessons"]
    client.post(f"/api/lessons/{lessons[0]['id']}/review", json={"status": "adopted"})
    client.post(f"/api/lessons/{lessons[1]['id']}/review", json={"status": "reviewed"})
    m = client.get("/api/legacy/metrics").json()
    assert m["lessons_generated"] >= 3 and m["recommendations_adopted"] == 1 and m["recommendations_reviewed"] == 1
    assert m["recurring_issues"] and m["recurring_issues"][0]["evidence_count"] >= 2
    assert m["outcome_improvement"] == "not_measured"


# ── Planning integration: history advises, never overrides ────────────────────────


def test_planning_asks_event_intelligence_and_passes_advisory_constraints(client):
    run, steps, _ = run_sync(client)
    assert [s.step_key for s in steps][:3] == ["intake", "lessons", "venues"]
    venues = steps[2]
    names = {c["name"] for c in venues.payload["constraints"]}
    assert {"history:compare_catering_minimums", "history:lock_guest_count", "min_contingency_pct"} <= names
    assert any("catering minimums" in c["detail"] for c in run.result["history_constraints"])
    assert all(c["source_agent"] == "event_intelligence" for c in run.result["history_constraints"])


def test_without_history_skips_event_intelligence(client):
    run, steps, _ = run_sync(client, script=ScriptedClient())
    app = client.app
    from backend.app.core.permissions import permissions_for
    from backend.app.db.models import AgentRun
    with app.state.db.transaction() as s:
        r = AgentRun(organization_id=1, user_id=1, workflow_type="plan_event", request_text="Plan a 150-person Manhattan gala",
                     status="queued", strategy="auto", provider="openai", budget_usd=0.5, research_mode="synthetic")
        s.add(r)
        s.flush()
        rid = r.id
    plan_id = run.event_plan_id or steps[0].run_id and None
    app.state.workflows.start(rid, user_id=1, organization_id=1, permissions=permissions_for("chair"), strategy="auto",
                              research_mode="synthetic", request="Plan a 150-person Manhattan gala", intent_hint="plan_event",
                              event_plan_id=plan_id, synchronous=True, options={"use_history": False})
    with app.state.db.session() as s:
        r = s.get(AgentRun, rid)
    assert r.status == "completed"
    assert "lessons" not in [s for s in run_snapshot(app.state.db, rid)["steps"]]
    assert r.result["history_constraints"] == [] and r.result["finance"]["budget"]["contingency_pct"] == 0.10


def test_history_cannot_override_finance(client):
    """Lessons can raise contingency, but Finance still computes from the ledger and the board's limit."""
    def pushy(p, kw):
        out = ScriptedClient().handlers["LessonsOutput"](p, kw)
        out["planning_constraints"].append({"name": "max_total_usd", "detail": "History says spend up to $80,000.",
                                            "evidence_reflection_ids": out["contingency_evidence_reflection_ids"]})
        return out

    run, steps, _ = run_sync(client, script=ScriptedClient({"LessonsOutput": pushy}))
    first_finance = next(s for s in steps if s.step_key == "finance")
    assert first_finance.status == "needs_revision"  # the $18,000 board limit still applies
    rev = next(s for s in steps if s.step_key == "venues_revision_1")
    limits = [c for c in rev.payload["constraints"] if c["name"] == "max_total_usd"]
    assert [c["value"] for c in limits] == [18000] and limits[0]["source_agent"] == "financial_analysis"
    assert any(c["name"] == "history:max_total_usd" for c in rev.payload["constraints"])  # history kept, but namespaced
    assert run.result["finance"]["budget"]["total_usd"] <= 18000
    assert run.result["finance"]["position"]["available_planning_budget_usd"] == 9938.0


def test_dollar_figures_at_sentence_end_are_read_correctly():
    from backend.app.agents.verification import dollar_amounts
    assert dollar_amounts("The total is $14,850.00. Upfront is $6,150.") == [14850.0, 6150.0]
    assert dollar_amounts("About $18K, or $1.5 million.") == [18000.0, 1500000.0]


def test_catering_minimum_is_applied_deterministically():
    b = calc.event_budget(venue_key="v", venue_name="V", event_format="seated_dinner", attendance=100, rental_usd=1000,
                          fnb_per_guest_usd=100, deposit_pct=0.5, production_usd=0, contingency_pct=0.0, fnb_minimum_usd=18000)
    assert b.total_usd == 19000 and "minimum" in b.line_items[1].name and any("minimum" in a for a in b.assumptions)


# ── The evidence test: same plan with and without history ────────────────────────


def test_history_ab_experiment_compares_runs_and_tracks_usage(client):
    client.app.state.provider = AIProvider("openai", ScriptedClient())
    login(client)
    r = client.post("/api/experiments/history-ab", json={})
    assert r.status_code == 202
    exp_id = r.json()["experiment"]["id"]
    for _ in range(200):
        e = client.get(f"/api/experiments/{exp_id}").json()["experiment"]
        if e["status"] != "running":
            break
        time.sleep(0.05)
    assert e["status"] == "completed", e["error"]
    c = e["comparison"]
    assert c["numbers"]["Contingency"] == {"without_history": 0.10, "with_history": 0.15, "delta": 0.05}
    assert c["numbers"]["Historical constraints given to Events"]["without_history"] == 0
    assert c["numbers"]["Historical constraints given to Events"]["with_history"] >= 3
    assert c["numbers"]["Model calls"]["with_history"] > c["numbers"]["Model calls"]["without_history"]
    assert c["runs"]["without_history"]["usage"]["cost_usd"] > 0 and c["runs"]["with_history"]["usage"]["cost_usd"] > 0
    assert any("Contingency changed from 10% to 15%" in x for x in c["summary_of_changes"])
    assert "lessons" not in c["runs"]["without_history"]["steps"] and "lessons" in c["runs"]["with_history"]["steps"]
    md = client.get(f"/api/experiments/{exp_id}/report.md").text
    assert "Without history" in md and "| Contingency | 10% | 15% |" in md

    client.post("/api/auth/logout")
    login(client, email=MEMBER)
    member_view = client.get(f"/api/experiments/{exp_id}").json()["experiment"]["comparison"]
    assert "Projected total (USD)" not in member_view["numbers"] and "runs" not in member_view
    assert client.get(f"/api/experiments/{exp_id}/report.md").status_code == 403


def test_comparison_markdown_is_deterministic():
    a = {"run_id": 1, "status": "completed", "use_history": False, "duration_s": 10, "steps": ["intake"],
         "usage": {"model_calls": 7, "input_tokens": 10, "cached_input_tokens": 0, "output_tokens": 5, "web_search_calls": 0, "cost_usd": 0.1, "by_agent": {}},
         "first_choice": None, "final_choice": {"venue": "V", "event_format": "reception", "total_usd": 100.0, "upfront_cash_usd": 50.0,
                                                "contingency_pct": 0.1, "verdict": "affordable"},
         "revisions": 1, "history_constraints": [], "lessons_used": 0, "headline": "A", "recommendation": "Go.", "lessons_applied": [],
         "fundraising_strategy": ["Tickets"], "logistics_notes": [], "risks": [], "decisions_for_board": [], "next_steps": [], "verification_passed": True}
    b = {**a, "run_id": 2, "use_history": True, "history_constraints": ["Compare catering minimums."], "lessons_applied": ["Lock guest count"],
         "fundraising_strategy": ["Tickets", "Sponsor tables"], "final_choice": {**a["final_choice"], "total_usd": 110.0, "contingency_pct": 0.2},
         "usage": {**a["usage"], "model_calls": 8, "cost_usd": 0.12}}
    c = compare_runs(a, b)
    assert c["fundraising_strategy"]["only_with"] == ["Sponsor tables"] and c["lessons_applied"]["only_with"] == ["Lock guest count"]
    md = comparison_markdown({"id": 9, "request": "Plan", "research_mode": "synthetic", "run_a_id": 1, "run_b_id": 2,
                              "created_at": "2026-10-25T00:00:00", "comparison": c})
    assert "| Contingency | 10% | 20% | +10% |" in md and "Only with history:** Sponsor tables" in md


def test_upgrade_fills_demo_fields_without_touching_real_records(client):
    from backend.app.db.seed import upgrade_demo_history
    db = client.app.state.db
    with db.transaction() as s:
        real = HistoricalEvent(organization_id=1, name="Real event", is_demo=False, summary="Board's own words")
        s.add(real)
        demo = s.scalar(select(HistoricalEvent).where(HistoricalEvent.is_demo.is_(True)))
        demo.venue = None
    with db.transaction() as s:
        assert upgrade_demo_history(s) >= 1
    with db.session() as s:
        assert s.scalar(select(HistoricalEvent).where(HistoricalEvent.name == "Real event")).summary == "Board's own words"
        assert s.get(HistoricalEvent, demo.id).venue


def test_recurring_issues_need_two_records_and_merge_near_duplicate_themes():
    from types import SimpleNamespace as N

    from backend.app.services.legacy import recurring_issues
    two = [{"type": "reflection", "id": 1}, {"type": "reflection", "id": 2}]
    lessons = [N(kind="recurring_problem", theme="Late changes and rush work", status="new", evidence=two, lesson=""),
               N(kind="recurring_problem", theme="late changes", status="adopted", evidence=[{"type": "event", "id": 1}, {"type": "reflection", "id": 3}], lesson=""),
               N(kind="recurring_problem", theme="Parking", status="new", evidence=[{"type": "reflection", "id": 9}], lesson=""),
               N(kind="recurring_problem", theme="Food costs", status="dismissed", evidence=two, lesson="")]
    assert recurring_issues(lessons) == [{"theme": "late changes", "evidence_count": 4}]


def test_event_page_includes_latest_analysis(client):
    login(client)
    eid = dinner_id(client)
    assert client.get(f"/api/legacy/events/{eid}").json()["latest_analysis"] is None
    d = analyze(client, eid)
    latest = client.get(f"/api/legacy/events/{eid}").json()["latest_analysis"]
    assert latest["run_id"] == d["run"]["id"] and latest["themes"] and latest["disagreements"]
    other = [e["id"] for e in client.get("/api/legacy/events").json()["events"] if e["id"] != eid][0]
    assert client.get(f"/api/legacy/events/{other}").json()["latest_analysis"] is None
