"""Impact & Evaluation: records, timing, calculations, feedback, rubric, history comparison, privacy, and export.

Every evaluation created here is a test fixture. Fixtures that stand in for "real" participants exist only in this
temporary test database; the app's own database never receives them, and nothing here is reported as a real user.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from backend.app.api.routes import impact as impact_routes
from backend.app.db.models import Experiment, ImpactEvaluation
from backend.app.services import impact_eval as ie
from backend.app.services.comparison import compare_runs, run_snapshot

from .conftest import MEMBER, login
from .test_mission import run_flow

T0 = datetime(2026, 10, 25, 14, 0, tzinfo=timezone.utc)
FEEDBACK = {"ease_of_use": 4, "usefulness": 3, "source_confidence": 2, "financial_helpful": "yes", "history_useful": "unsure",
            "history_changed_strategy": "no", "outreach_usable": "needs_editing", "would_use_again": "maybe",
            "worked_well": "The budget table.", "confusing": "Too many sections; I could not find the venue sources quickly.",
            "improve_first": "Shorter packet.", "comments": "Not convinced it saves time yet."}


def clock(monkeypatch, *moments):
    """Make the server clock return the given moments in order (timers are stamped server-side)."""
    seq = iter(moments)
    monkeypatch.setattr(impact_routes, "_now", lambda: next(seq))


def new_eval(client, **body) -> dict:
    r = client.post("/api/impact/evaluations", json=body)
    assert r.status_code == 201, r.text
    return r.json()["evaluation"]


def complete(client, eid: int, manual: float | None, assisted: float, feedback: dict = FEEDBACK) -> dict:
    body = {"assisted_minutes": assisted}
    if manual is not None:
        body["manual_minutes"] = manual
    assert client.put(f"/api/impact/evaluations/{eid}", json=body).status_code == 200
    if manual is None:
        client.post(f"/api/impact/evaluations/{eid}/timer", json={"part": "manual", "action": "unavailable"})
    assert client.post(f"/api/impact/evaluations/{eid}/feedback", json={"feedback": feedback}).status_code == 200
    r = client.post(f"/api/impact/evaluations/{eid}/submit")
    assert r.status_code == 200, r.text
    return r.json()["evaluation"]


# 1–4: records and timing


def test_create_evaluation_record(client):
    login(client)
    e = new_eval(client)
    assert e["participant_code"] == "P1" and e["status"] == "draft" and not e["is_synthetic"]
    assert e["participant_role"] == "Board Chair (demo)" and e["manual"]["status"] == "not_started" and e["task_date"]
    assert e["display_name"].startswith("P1")  # not named in reports by default
    practice = new_eval(client, is_synthetic=True)
    assert practice["participant_code"] == "T1" and practice["is_synthetic"]


def test_start_and_finish_both_attempts_with_the_server_clock(client, monkeypatch):
    login(client)
    eid = new_eval(client)["id"]
    clock(monkeypatch, T0, T0 + timedelta(minutes=95), T0 + timedelta(minutes=100), T0 + timedelta(minutes=142))
    url = f"/api/impact/evaluations/{eid}/timer"
    assert client.post(url, json={"part": "manual", "action": "finish"}).status_code == 409  # finish needs a start
    e = client.post(url, json={"part": "manual", "action": "start"}).json()["evaluation"]
    assert e["manual"]["status"] == "in_progress"
    e = client.post(url, json={"part": "manual", "action": "finish"}).json()["evaluation"]
    assert e["manual"]["status"] == "completed" and e["manual"]["minutes"] == 95.0
    client.post(url, json={"part": "assisted", "action": "start"})
    e = client.post(url, json={"part": "assisted", "action": "finish"}).json()["evaluation"]
    assert e["assisted"]["minutes"] == 42.0 and e["comparison"] == {"manual_minutes": 95.0, "assisted_minutes": 42.0,
                                                                     "minutes_saved": 53.0, "pct_reduction": 55.8}


def test_manual_times_typed_by_hand_and_review_time(client):
    login(client)
    eid = new_eval(client)["id"]
    url = f"/api/impact/evaluations/{eid}"
    r = client.put(url, json={"manual_started_at": "2026-10-20T09:00:00Z", "manual_finished_at": "2026-10-20T08:30:00Z"})
    assert r.status_code == 422  # finish before start
    e = client.put(url, json={"manual_started_at": "2026-10-20T09:00:00Z", "manual_finished_at": "2026-10-20T11:15:00Z",
                              "manual_tools": ["Google", " Excel ", ""], "manual_venues": 2, "manual_verified_sources": 3,
                              "manual_financial_model": True, "manual_history_used": False, "manual_outreach_draft": False,
                              "manual_difficulties": "Venue prices are not published."}).json()["evaluation"]
    m = e["manual"]
    assert m["minutes"] == 135.0 and m["status"] == "completed" and m["tools"] == ["Google", "Excel"] and m["history_used"] is False
    e = client.put(url, json={"assisted_minutes": 40, "review_minutes": 25}).json()["evaluation"]
    assert e["assisted"]["status"] == "completed" and e["assisted"]["review_minutes"] == 25
    assert client.put(url, json={"review_minutes": 60}).status_code == 422  # review cannot exceed the whole attempt


# 5–9: calculations


@pytest.mark.parametrize("manual, assisted, saved, pct", [
    (90, 35, 55.0, 61.1),       # SAM SPACE faster
    (30, 45, -15.0, -50.0),     # SAM SPACE slower: negative, never hidden
    (0, 20, -20.0, None),       # zero-minute baseline: no percentage
    (None, 20, None, None),     # baseline unavailable
    (60, None, None, None),     # assisted attempt missing
])
def test_time_calculations(manual, assisted, saved, pct):
    assert ie.minutes_saved(manual, assisted) == saved
    assert ie.pct_reduction(manual, assisted) == pct


def test_annual_projection():
    assert ie.annual_hours(55, 12) == 11.0
    assert ie.annual_hours(-15, 12) == -3.0
    assert ie.annual_hours(None, 12) is None and ie.annual_hours(55, None) is None


# 10–11: feedback


def test_feedback_is_validated_and_stored_exactly(client):
    login(client)
    eid = new_eval(client)["id"]
    url = f"/api/impact/evaluations/{eid}/feedback"
    for bad in ({**FEEDBACK, "ease_of_use": 6}, {**FEEDBACK, "outreach_usable": "maybe"}, {k: v for k, v in FEEDBACK.items() if k != "usefulness"},
                {**FEEDBACK, "comments": "x" * 3001}):
        assert client.post(url, json={"feedback": bad}).status_code == 422
    assert client.post(url, json={"feedback": FEEDBACK, "mission": {"dimensions": {"made_up": "yes"}}}).status_code == 422
    mission = {"advances_mission": "unsure", "dimensions": {"belonging": "somewhat", "eating_disorder_research": "no"},
               "comment": "Research support is missing."}
    e = client.post(url, json={"feedback": FEEDBACK, "mission": mission}).json()["evaluation"]
    assert e["feedback"] == FEEDBACK and e["mission"] == mission  # negative answers kept word for word
    assert client.get(f"/api/impact/evaluations/{eid}").json()["evaluation"]["feedback"]["confusing"] == FEEDBACK["confusing"]


# 12: historical-learning comparison records


def test_history_comparison_shows_what_changed_and_why(client):
    login(client)
    run_a, _, _ = run_flow(client, "Plan a 150-person Manhattan fundraising gala and check whether we can afford it.", intent="plan_event",
                           options={"use_history": False}, plan_id=1)
    run_b, _, _ = run_flow(client, "Plan a 150-person Manhattan fundraising gala and check whether we can afford it.", intent="plan_event",
                           options={"use_history": True}, plan_id=1)
    db = client.app.state.db
    snap_a, snap_b = run_snapshot(db, run_a.id), run_snapshot(db, run_b.id)
    with db.transaction() as s:
        exp = Experiment(organization_id=1, created_by=1, kind="history_ab", request_text="Plan a 150-person Manhattan gala", run_a_id=run_a.id,
                         run_b_id=run_b.id, status="completed", result=compare_runs(snap_a, snap_b))
        s.add(exp)
        s.flush()
        exp_id = exp.id
    c = client.get(f"/api/impact/history-comparisons/{exp_id}").json()["comparison"]
    assert [d["key"] for d in c["dimensions"]] == ["venue_selection", "budget", "logistics", "volunteers", "sponsorship", "community", "accessibility"]
    changed = [x for d in c["dimensions"] for x in d["changed_by_history"]]
    assert all(x["supported_by"] for x in changed)  # every claimed change names its lesson
    # The scripted model writes the same recommendation text either way, so no text change is claimed...
    assert not changed and {d["verdict"] for d in c["dimensions"]} <= {"no history-attributed change", "not addressed by either"}
    # ...but the budget did change: the with-history run used the contingency a lesson recommended.
    cont = next(r for r in c["numbers"] if r["measure"] == "Contingency")
    assert cont["changed"] and cont["with_history"] == 0.15 and c["summary"]["budget_numbers_changed"]
    assert c["runs"]["with_history"]["run_id"] == run_b.id and c["runs"]["with_history"]["usage"]["model_calls"] > 0
    assert c["runs"]["without_history"]["models"] and c["lessons"] and c["inputs"]["request"]
    assert {r["measure"] for r in c["numbers"]} >= {"Projected total (USD)", "Contingency"}
    assert c["human_scores"] == {}  # nothing is scored automatically
    scores = {k: 3 for k in ie.RUBRIC_KEYS}
    assert client.post(f"/api/impact/history-comparisons/{exp_id}/scores", json={"condition": "with_history", "scores": scores}).status_code == 200
    assert client.post(f"/api/impact/history-comparisons/{exp_id}/scores", json={"condition": "with_history", "scores": {"clarity": 9}}).status_code == 422
    assert client.get(f"/api/impact/history-comparisons/{exp_id}").json()["comparison"]["human_scores"]["with_history"]["clarity"] == 3


def test_a_new_statement_without_a_matching_lesson_is_not_called_an_improvement():
    without = {"recommendation": {"headline": "Book the venue", "recommendation": "Choose the hall.", "next_steps": []}}
    with_ = {"recommendation": {"headline": "Book the venue", "recommendation": "Choose the hall.",
                                "lessons_applied": ["Spring Raffle: brief volunteers by phone a week before, with station leads.",
                                                    "Hold a rooftop fireworks show for the venue opening."],
                                "next_steps": ["Ask the venue about guest parking and the coat check."]}}
    lessons = [{"text": "Brief volunteers the week before and assign station leads.", "event_ids": [4], "reflection_ids": [9]},
               {"text": "Guests praised the speaker and stayed late.", "event_ids": [5], "reflection_ids": []}]
    dims = {d["key"]: d for d in ie.history_dimensions(without, with_, lessons, [], {4: "Spring Raffle", 5: "Benefit Dinner"})}
    vol = dims["volunteers"]["changed_by_history"][0]
    assert vol["supported_by"][0]["events"] == ["Spring Raffle"] and len(vol["supported_by"]) == 1  # the generic "guests" lesson is not support
    # Attributed to history but resting on no lesson: shown as such, never as an improvement.
    assert dims["venue_selection"]["different_without_specific_lesson"][0]["statement"].startswith("Hold a rooftop")
    # Not attributed to history at all: only counted as a possible model-variation difference.
    assert dims["venue_selection"]["other_differences"] == 1 and not dims["venue_selection"]["changed_by_history"]


# 13: linking to a real agent run


def test_linking_reads_metrics_from_the_run_logs(client):
    login(client)
    run, steps, fake = run_flow(client, "Plan a 150-person Manhattan fundraising gala and check whether we can afford it.", intent="plan_event", plan_id=1)
    eid = new_eval(client)["id"]
    m = client.post(f"/api/impact/evaluations/{eid}/link-run", json={"run_id": run.id}).json()["evaluation"]["assisted"]["run_metrics"]
    assert m["run_id"] == run.id and {"fundraising_events", "financial_analysis"} <= set(m["agents_involved"])
    assert m["venues_considered"] >= 3 and m["outreach_drafts"] >= 1 and m["drafts_unsent"] and m["recommendation_written"]
    assert m["model_calls"] == len(fake.calls) and m["sources_synthetic"] > 0 and m["sources_verified_live"] == 0
    assert m["model_execution_minutes"] >= 0 and "model_execution_minutes" in m  # model time, kept apart from human time
    learning, _, _ = run_flow(client, "What lessons can we learn from our previous events?", intent="event_learning")
    assert client.post(f"/api/impact/evaluations/{eid}/link-run", json={"run_id": learning.id}).status_code == 422
    assert client.post(f"/api/impact/evaluations/{eid}/link-run", json={"run_id": 99999}).status_code == 404


# 14, 16, 18: separation, missing data, dashboard consistency


def test_practice_records_are_never_counted_and_pilot_pending_is_shown(client):
    login(client)
    practice = new_eval(client, is_synthetic=True)["id"]
    complete(client, practice, 90, 30)
    o = client.get("/api/impact/overview").json()
    assert o["pilot_pending"] and o["pilot_message"] == "Pilot pending — no real-user evaluation data collected yet."
    assert o["real"]["completed_evaluations"] == 0 and o["real"]["time"]["minutes_saved"] is None and o["real_feedback"] == []
    assert o["synthetic"]["completed_evaluations"] == 1 and o["synthetic"]["time"]["minutes_saved"] == 60.0


def test_missing_data_is_reported_not_filled(client):
    login(client)
    eid = new_eval(client)["id"]
    r = client.post(f"/api/impact/evaluations/{eid}/submit")
    assert r.status_code == 422 and "feedback form" in r.json()["detail"]
    complete(client, eid, None, 40)  # no manual baseline
    o = client.get("/api/impact/overview").json()["real"]
    assert o["completed_evaluations"] == 1 and o["sample_note"].startswith("Small pilot (n=1)")
    assert o["time"]["manual_avg_minutes"] is None and o["time"]["minutes_saved"] is None and o["time"]["pct_reduction"] is None
    assert o["time"]["manual_unavailable"] == 1 and o["time"]["assisted_avg_minutes"] == 40.0
    assert o["projection"]["annual_hours_saved"] is None


def test_dashboard_totals_match_stored_records(client):
    login(client)
    pairs = [(120, 45), (60, 75), (90, None)]
    for manual, assisted in pairs:
        eid = new_eval(client)["id"]
        complete(client, eid, manual, assisted if assisted is not None else 50)
    assert client.put("/api/impact/assumptions", json={"tasks_per_year": 6}).status_code == 200
    o = client.get("/api/impact/overview").json()["real"]
    with client.app.state.db.session() as s:
        rows = s.scalars(select(ImpactEvaluation).where(ImpactEvaluation.is_synthetic.is_(False), ImpactEvaluation.status == "submitted")).all()
    manual = [r.manual_minutes for r in rows]
    assisted = [r.assisted_minutes for r in rows]
    assert o["completed_evaluations"] == len(rows) == 3
    assert o["time"]["manual_avg_minutes"] == round(sum(manual) / 3, 1) and o["time"]["assisted_avg_minutes"] == round(sum(assisted) / 3, 1)
    paired_m, paired_a = round(sum(manual) / 3, 1), round(sum(assisted) / 3, 1)  # all three have both times here
    assert o["time"]["minutes_saved"] == round(paired_m - paired_a, 1)
    assert o["time"]["pct_reduction"] == round(100 * (paired_m - paired_a) / paired_m, 1)
    assert o["projection"]["annual_hours_saved"] == round(o["time"]["minutes_saved"] * 6 / 60, 1)
    assert o["ratings"]["usefulness"] == 3.0 and o["answers"]["would_use_again"] == {"maybe": 3}


# 15: authorization and privacy


def test_authorization_and_privacy(client):
    login(client)
    chair_eval = new_eval(client)["id"]
    complete(client, chair_eval, 80, 40)
    assert client.put(f"/api/impact/evaluations/{chair_eval}", json={"manual_minutes": 5}).status_code == 409  # submitted: frozen
    client.post("/api/auth/logout")
    login(client, email=MEMBER)
    assert client.get(f"/api/impact/evaluations/{chair_eval}").status_code == 404  # another member's evaluation
    assert client.put(f"/api/impact/evaluations/{chair_eval}", json={"manual_minutes": 1}).status_code == 404
    assert client.put("/api/impact/assumptions", json={"tasks_per_year": 99}).status_code == 403
    mine = new_eval(client)["id"]
    assert [e["id"] for e in client.get("/api/impact/evaluations").json()["evaluations"]] == [mine]
    # Names appear in reports only with both choices made.
    o = client.get("/api/impact/overview").json()
    assert o["real_feedback"][0]["participant"].startswith("P1") and "Tauhid" not in str(o["real_feedback"])
    from .test_adversarial import _second_workspace
    _second_workspace(client)
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "chair@other.example", "password": "other-pass-123"})
    assert client.get(f"/api/impact/evaluations/{chair_eval}").status_code == 404
    assert client.get("/api/impact/overview").json()["real"]["completed_evaluations"] == 0


def test_named_attribution_needs_both_choices(client):
    login(client)
    only_name = new_eval(client, show_name_in_reports=True)["id"]
    both = new_eval(client, show_name_in_reports=True, attribution_permission=True)["id"]
    complete(client, only_name, 60, 30)
    complete(client, both, 60, 30)
    names = [f["participant"] for f in client.get("/api/impact/overview").json()["real_feedback"]]
    assert sum("Tauhid Brooks" in n for n in names) == 1 and any(n.startswith("P1") for n in names)


# 17: export


def test_export_is_anonymized_and_states_missing_data(client):
    login(client)
    md = client.get("/api/impact/export.md").text
    assert "Pilot pending — no real-user evaluation data collected yet." in md and "no time-savings" in md
    eid = new_eval(client)["id"]
    complete(client, eid, 100, 40)
    bundle = client.get("/api/impact/export").json()
    ev = bundle["real"]["evaluations"][0]
    assert ev["display_name"].startswith("P1") and "Tauhid" not in str(bundle["real"])
    assert bundle["real"]["summary"]["time"]["minutes_saved"] == 60.0 and bundle["calculations"]["pct_reduction"]
    md = client.get("/api/impact/export.md").text
    assert "Pilot pending" not in md and "| Minutes saved (paired evaluations: 1) | 60.0 min | Calculated |" in md
    assert "Not convinced it saves time yet." in md  # unfavorable feedback is exported as written
    client.post("/api/auth/logout")
    login(client, email=MEMBER)
    assert client.get("/api/impact/export").status_code == 200  # members may export; still anonymized
