"""Impact & Evaluation: a real-user pilot of SAM SPACE against the board's usual way of working.

Every number comes from what participants recorded or from the application's own logs. Practice and test records are
flagged and reported separately. Reports show participant codes unless a participant chose to be named and allowed
their comments to be attributed. Nothing is scored by AI: rubric scores are entered by people.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.permissions import Permission
from ...db.models import AgentHandoff, AgentRun, EvaluationScore, EventPlan, Experiment, HistoricalEvent, ImpactAssumption, ImpactEvaluation, User
from ...services import impact_eval as ie
from ..deps import CurrentUser, audit, current_user, get_db, is_foreign_or_missing, require

router = APIRouter(prefix="/api/impact", tags=["impact"])

YesNoUnsure = Literal["yes", "no", "unsure"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _tasks_per_year(db: Session, org: int) -> float | None:
    row = db.scalar(select(ImpactAssumption).where(ImpactAssumption.organization_id == org, ImpactAssumption.key == "tasks_per_year"))
    return row.value if row else None


def _get(db: Session, cu: CurrentUser, eval_id: int, write: bool = False) -> ImpactEvaluation:
    e = db.get(ImpactEvaluation, eval_id)
    if is_foreign_or_missing(db, cu, e, "evaluation"):
        raise HTTPException(404, "Evaluation not found.")
    admin = Permission.MANAGE_USERS in cu.permissions
    if e.user_id != cu.user.id and not (admin and not write):
        raise HTTPException(404, "Evaluation not found.")  # other members' evaluations are private to them and the chair
    if write and e.status == "submitted":
        raise HTTPException(409, "This evaluation was submitted and can no longer be changed.")
    return e


def _name(db: Session, user_id: int | None) -> str | None:
    u = db.get(User, user_id) if user_id else None
    return f"{u.first_name} {u.last_name}".strip() if u else None


def evaluation_out(db: Session, e: ImpactEvaluation, *, for_owner: bool) -> dict:
    manual, assisted = ie.evaluation_minutes(e)
    scores = db.scalars(select(EvaluationScore).where(EvaluationScore.evaluation_id == e.id)).all()
    return {
        "id": e.id, "participant_code": e.participant_code, "participant_role": e.participant_role,
        "display_name": ie.public_name(e, _name(db, e.user_id)), "show_name_in_reports": e.show_name_in_reports,
        "attribution_permission": e.attribution_permission, "is_synthetic": e.is_synthetic, "status": e.status,
        "task_date": e.task_date.isoformat() if e.task_date else None, "is_mine": for_owner,
        "manual": {"status": e.manual_status, "started_at": _iso(e.manual_started_at), "finished_at": _iso(e.manual_finished_at),
                   "minutes": e.manual_minutes, "tools": e.manual_tools or [], "venues": e.manual_venues,
                   "verified_sources": e.manual_verified_sources, "financial_model": e.manual_financial_model,
                   "history_used": e.manual_history_used, "outreach_draft": e.manual_outreach_draft,
                   "difficulties": e.manual_difficulties, "comments": e.manual_comments},
        "assisted": {"status": e.assisted_status, "started_at": _iso(e.assisted_started_at), "finished_at": _iso(e.assisted_finished_at),
                     "minutes": e.assisted_minutes, "review_minutes": e.review_minutes, "run_id": e.run_id, "run_metrics": e.run_metrics,
                     "calculations_correct": e.calculations_correct, "outreach_usefulness": e.outreach_usefulness,
                     "errors_encountered": e.errors_encountered, "unsupported_claims_found": e.unsupported_claims_found,
                     "unsupported_claims_notes": e.unsupported_claims_notes, "observations": e.assisted_observations},
        "comparison": {"manual_minutes": manual, "assisted_minutes": assisted, "minutes_saved": ie.minutes_saved(manual, assisted),
                       "pct_reduction": ie.pct_reduction(manual, assisted)},
        "scores": [{"condition": s.condition, "dimension": s.dimension, "score": s.score, "note": s.note} for s in scores],
        "feedback": e.feedback, "mission": e.mission, "feedback_saved_at": _iso(e.feedback_saved_at),
        "created_at": e.created_at.isoformat(), "submitted_at": _iso(e.submitted_at),
    }


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


# ── The task and the instruments ─────────────────────────────────────────────────────


@router.get("/scenario")
def scenario(_: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    plan_id = db.scalar(select(EventPlan.id).where(EventPlan.name.like("Manhattan Spring Gala%")).limit(1))
    return {"scenario": ie.SCENARIO, "event_plan_id": plan_id,
            "rubric": [{"key": k, "label": l, "question": q} for k, l, q in ie.RUBRIC], "scale": ie.SCALE,
            "feedback_questions": [{"key": k, "question": q, "kind": kind} for k, q, kind in ie.FEEDBACK_QUESTIONS],
            "mission_dimensions": [{"key": k, "label": l} for k, l in ie.MISSION_DIMENSIONS],
            "scoring_note": "Scores are entered by a person using the same rubric for both proposals. No AI model scores proposals."}


# ── Evaluations ─────────────────────────────────────────────────────────────────────


class EvaluationIn(BaseModel):
    is_synthetic: bool = False  # a practice or test run: shown separately, never counted
    participant_role: str | None = Field(default=None, max_length=60)
    show_name_in_reports: bool = False
    attribution_permission: bool = False


@router.post("/evaluations", status_code=status.HTTP_201_CREATED)
def create_evaluation(body: EvaluationIn, cu: CurrentUser = Depends(require(Permission.VIEW_DASHBOARD)), db: Session = Depends(get_db)) -> dict:
    n = db.scalar(select(func.count(ImpactEvaluation.id)).where(ImpactEvaluation.organization_id == cu.organization_id,
                                                                  ImpactEvaluation.is_synthetic.is_(body.is_synthetic))) or 0
    e = ImpactEvaluation(organization_id=cu.organization_id, user_id=cu.user.id, participant_code=f"{'T' if body.is_synthetic else 'P'}{n + 1}",
                         participant_role=(body.participant_role or cu.membership.title or cu.role).strip()[:60],
                         show_name_in_reports=body.show_name_in_reports, attribution_permission=body.attribution_permission,
                         is_synthetic=body.is_synthetic, task_date=date.today(), updated_at=_now())
    db.add(e)
    db.flush()
    audit(db, cu, "evaluation_created", f"evaluation:{e.id}", synthetic=body.is_synthetic)
    db.commit()
    return {"evaluation": evaluation_out(db, e, for_owner=True)}


@router.get("/evaluations")
def list_evaluations(cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    q = select(ImpactEvaluation).where(ImpactEvaluation.organization_id == cu.organization_id)
    if Permission.MANAGE_USERS not in cu.permissions:
        q = q.where(ImpactEvaluation.user_id == cu.user.id)
    rows = db.scalars(q.order_by(ImpactEvaluation.created_at.desc())).all()
    return {"evaluations": [{"id": e.id, "participant_code": e.participant_code, "status": e.status, "is_synthetic": e.is_synthetic,
                             "task_date": e.task_date.isoformat() if e.task_date else None, "is_mine": e.user_id == cu.user.id,
                             "manual_status": e.manual_status, "assisted_status": e.assisted_status} for e in rows]}


@router.get("/evaluations/{eval_id}")
def get_evaluation(eval_id: int, cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    e = _get(db, cu, eval_id)
    return {"evaluation": evaluation_out(db, e, for_owner=e.user_id == cu.user.id)}


class EvaluationUpdate(BaseModel):
    participant_role: str | None = Field(default=None, max_length=60)
    show_name_in_reports: bool | None = None
    attribution_permission: bool | None = None
    task_date: date | None = None
    manual_minutes: float | None = Field(default=None, ge=0, le=6000)  # when the manual task was timed elsewhere
    manual_started_at: datetime | None = None
    manual_finished_at: datetime | None = None
    manual_tools: list[str] | None = Field(default=None, max_length=20)
    manual_venues: int | None = Field(default=None, ge=0, le=100)
    manual_verified_sources: int | None = Field(default=None, ge=0, le=500)
    manual_financial_model: bool | None = None
    manual_history_used: bool | None = None
    manual_outreach_draft: bool | None = None
    manual_difficulties: str | None = Field(default=None, max_length=3000)
    manual_comments: str | None = Field(default=None, max_length=3000)
    assisted_minutes: float | None = Field(default=None, ge=0, le=6000)
    review_minutes: float | None = Field(default=None, ge=0, le=6000)
    calculations_correct: YesNoUnsure | None = None
    outreach_usefulness: Literal["usable", "needs_editing", "not_usable"] | None = None
    errors_encountered: str | None = Field(default=None, max_length=3000)
    unsupported_claims_found: int | None = Field(default=None, ge=0, le=500)
    unsupported_claims_notes: str | None = Field(default=None, max_length=3000)
    assisted_observations: str | None = Field(default=None, max_length=3000)


@router.put("/evaluations/{eval_id}")
def update_evaluation(eval_id: int, body: EvaluationUpdate, cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Save progress at any time. Times typed by hand are kept as entered; minutes are computed from start and finish."""
    e = _get(db, cu, eval_id, write=True)
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        if key == "manual_tools" and value is not None:
            value = [t.strip()[:60] for t in value if t.strip()]
        setattr(e, key, value.strip() if isinstance(value, str) else value)
    if "manual_started_at" in data or "manual_finished_at" in data:
        computed = ie.minutes_between(e.manual_started_at, e.manual_finished_at)
        if e.manual_started_at and e.manual_finished_at and computed is None:
            raise HTTPException(422, "The manual finish time is before the start time.")
        if computed is not None:
            e.manual_minutes, e.manual_status = computed, "completed"
    elif "manual_minutes" in data and data["manual_minutes"] is not None:
        e.manual_status = "completed"
    if "assisted_minutes" in data and data["assisted_minutes"] is not None:
        e.assisted_status = "completed"
    if e.review_minutes is not None and e.assisted_minutes is not None and e.review_minutes > e.assisted_minutes:
        raise HTTPException(422, "Review time cannot be longer than the whole SAM SPACE attempt.")
    e.updated_at = _now()
    db.commit()
    return {"evaluation": evaluation_out(db, e, for_owner=True)}


class TimerIn(BaseModel):
    part: Literal["manual", "assisted"]
    action: Literal["start", "finish", "unavailable", "reset"]


@router.post("/evaluations/{eval_id}/timer")
def timer(eval_id: int, body: TimerIn, cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Start and finish are stamped by the server clock, so recorded minutes are observed, not estimated."""
    e = _get(db, cu, eval_id, write=True)
    p = body.part
    if body.action == "finish" and (getattr(e, f"{p}_started_at") is None or getattr(e, f"{p}_status") != "in_progress"):
        raise HTTPException(409, "Press Start first.")
    now = _now()  # one server timestamp per action
    if body.action == "start":
        setattr(e, f"{p}_started_at", now)
        setattr(e, f"{p}_finished_at", None)
        setattr(e, f"{p}_minutes", None)
        setattr(e, f"{p}_status", "in_progress")
    elif body.action == "finish":
        setattr(e, f"{p}_finished_at", now)
        setattr(e, f"{p}_minutes", ie.minutes_between(getattr(e, f"{p}_started_at"), now))
        setattr(e, f"{p}_status", "completed")
    elif body.action == "unavailable":
        for f in ("started_at", "finished_at", "minutes"):
            setattr(e, f"{p}_{f}", None)
        setattr(e, f"{p}_status", "unavailable")
    else:
        for f in ("started_at", "finished_at", "minutes"):
            setattr(e, f"{p}_{f}", None)
        setattr(e, f"{p}_status", "not_started")
    e.updated_at = now
    db.commit()
    return {"evaluation": evaluation_out(db, e, for_owner=True)}


class LinkRunIn(BaseModel):
    run_id: int


@router.post("/evaluations/{eval_id}/link-run")
def link_run(eval_id: int, body: LinkRunIn, cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    e = _get(db, cu, eval_id, write=True)
    run = db.get(AgentRun, body.run_id)
    if is_foreign_or_missing(db, cu, run, "run"):
        raise HTTPException(404, "Run not found.")
    if run.workflow_type != "plan_event" or run.status in ("queued", "running"):
        raise HTTPException(422, "Link a finished Event Studio planning run.")
    e.run_id = run.id
    e.run_metrics = ie.run_metrics(db, run.id)
    e.updated_at = _now()
    db.commit()
    return {"evaluation": evaluation_out(db, e, for_owner=True)}


class ScoresIn(BaseModel):
    condition: Literal["manual", "assisted"]
    scores: dict[str, int]
    note: str | None = Field(default=None, max_length=1000)


def _check_scores(scores: dict[str, int]) -> None:
    unknown = [k for k in scores if k not in ie.RUBRIC_KEYS]
    bad = [k for k, v in scores.items() if not isinstance(v, int) or not 0 <= v <= 4]
    if unknown or bad:
        raise HTTPException(422, f"Scores must be 0-4 for these dimensions: {', '.join(ie.RUBRIC_KEYS)}.")


@router.post("/evaluations/{eval_id}/scores")
def score_evaluation(eval_id: int, body: ScoresIn, cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    e = _get(db, cu, eval_id, write=True)
    _check_scores(body.scores)
    for old in db.scalars(select(EvaluationScore).where(EvaluationScore.evaluation_id == e.id, EvaluationScore.condition == body.condition)):
        db.delete(old)
    for dim, v in body.scores.items():
        db.add(EvaluationScore(organization_id=cu.organization_id, evaluation_id=e.id, condition=body.condition, dimension=dim, score=v,
                               scorer_user_id=cu.user.id, scorer_kind="human", note=body.note))
    e.updated_at = _now()
    db.commit()
    return {"evaluation": evaluation_out(db, e, for_owner=True)}


Scale = Field(ge=1, le=5)


class FeedbackIn(BaseModel):
    ease_of_use: int = Scale
    usefulness: int = Scale
    source_confidence: int = Scale
    financial_helpful: YesNoUnsure
    history_useful: YesNoUnsure
    history_changed_strategy: YesNoUnsure
    outreach_usable: Literal["yes", "no", "needs_editing"]
    would_use_again: Literal["yes", "no", "maybe"]
    worked_well: str = Field(default="", max_length=3000)
    confusing: str = Field(default="", max_length=3000)
    improve_first: str = Field(default="", max_length=3000)
    comments: str = Field(default="", max_length=3000)


class MissionIn(BaseModel):
    advances_mission: YesNoUnsure | None = None
    dimensions: dict[str, Literal["yes", "somewhat", "no", "not_applicable"]] = Field(default_factory=dict)
    comment: str = Field(default="", max_length=3000)


class FeedbackBody(BaseModel):
    feedback: FeedbackIn
    mission: MissionIn | None = None


@router.post("/evaluations/{eval_id}/feedback")
def save_feedback(eval_id: int, body: FeedbackBody, cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Stored exactly as given. Negative answers are kept and reported like any other."""
    e = _get(db, cu, eval_id, write=True)
    if body.mission:
        unknown = [k for k in body.mission.dimensions if k not in dict(ie.MISSION_DIMENSIONS)]
        if unknown:
            raise HTTPException(422, f"Unknown mission question: {', '.join(unknown)}")
    e.feedback = body.feedback.model_dump()
    e.mission = body.mission.model_dump() if body.mission else None
    e.feedback_saved_at = e.updated_at = _now()
    audit(db, cu, "evaluation_feedback_saved", f"evaluation:{e.id}")
    db.commit()
    return {"evaluation": evaluation_out(db, e, for_owner=True)}


@router.post("/evaluations/{eval_id}/submit")
def submit(eval_id: int, cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    e = _get(db, cu, eval_id, write=True)
    missing = []
    if not e.feedback:
        missing.append("the feedback form")
    if e.assisted_status not in ("completed", "unavailable"):
        missing.append("the SAM SPACE attempt (finish it, or mark it unavailable)")
    if e.manual_status not in ("completed", "unavailable"):
        missing.append("the manual baseline (finish it, or mark it unavailable)")
    if missing:
        raise HTTPException(422, "Before submitting, complete " + " and ".join(missing) + ".")
    e.status, e.submitted_at, e.updated_at = "submitted", _now(), _now()
    audit(db, cu, "evaluation_submitted", f"evaluation:{e.id}", synthetic=e.is_synthetic)
    db.commit()
    return {"evaluation": evaluation_out(db, e, for_owner=True)}


# ── Dashboard ───────────────────────────────────────────────────────────────────────


def _feedback_entries(db: Session, rows: list[ImpactEvaluation]) -> list[dict]:
    out = []
    for e in rows:
        if e.status != "submitted" or not e.feedback:
            continue
        out.append({"participant": ie.public_name(e, _name(db, e.user_id)), "date": e.task_date.isoformat() if e.task_date else None,
                    "role": e.participant_role, "answers": e.feedback, "mission": e.mission,
                    "comments_attributed": e.attribution_permission and e.show_name_in_reports})
    return out


@router.get("/overview")
def overview(cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(ImpactEvaluation).where(ImpactEvaluation.organization_id == cu.organization_id)).all()
    scores = db.scalars(select(EvaluationScore).where(EvaluationScore.organization_id == cu.organization_id)).all()
    real, synthetic = [e for e in rows if not e.is_synthetic], [e for e in rows if e.is_synthetic]
    tasks = _tasks_per_year(db, cu.organization_id)
    real_summary = ie.summarize(real, scores, tasks)
    exps = db.scalars(select(Experiment).where(Experiment.organization_id == cu.organization_id, Experiment.kind == "history_ab",
                                               Experiment.status == "completed").order_by(Experiment.created_at.desc())).all()
    return {
        "pilot_pending": real_summary["completed_evaluations"] == 0, "pilot_message": ie.PILOT_PENDING,
        "real": real_summary, "real_feedback": _feedback_entries(db, real),
        "synthetic": {**ie.summarize(synthetic, scores, tasks), "feedback": _feedback_entries(db, synthetic),
                      "note": "Practice and test records. Never counted in the results above."},
        "assumptions": {"tasks_per_year": tasks, "editable": Permission.MANAGE_USERS in cu.permissions},
        "history_comparisons": [{"id": x.id, "request": x.request_text, "run_a_id": x.run_a_id, "run_b_id": x.run_b_id,
                                 "date": x.created_at.isoformat()} for x in exps],
    }


class AssumptionIn(BaseModel):
    tasks_per_year: float = Field(ge=0, le=10_000)
    note: str | None = Field(default=None, max_length=500)


@router.put("/assumptions")
def set_assumptions(body: AssumptionIn, cu: CurrentUser = Depends(require(Permission.MANAGE_USERS)), db: Session = Depends(get_db)) -> dict:
    row = db.scalar(select(ImpactAssumption).where(ImpactAssumption.organization_id == cu.organization_id, ImpactAssumption.key == "tasks_per_year"))
    if row is None:
        row = ImpactAssumption(organization_id=cu.organization_id, key="tasks_per_year", value=body.tasks_per_year)
        db.add(row)
    row.value, row.note, row.updated_by, row.updated_at = body.tasks_per_year, body.note, cu.user.id, _now()
    audit(db, cu, "impact_assumption_changed", "impact:tasks_per_year", value=body.tasks_per_year)
    db.commit()
    return {"tasks_per_year": row.value}


# ── Historical-learning comparisons (A without history, B with history) ─────────────────────────


def comparison_detail(db: Session, exp: Experiment) -> dict:
    res = exp.result or {}
    run_a, run_b = db.get(AgentRun, exp.run_a_id), db.get(AgentRun, exp.run_b_id)
    lessons_step = db.scalar(select(AgentHandoff).where(AgentHandoff.run_id == exp.run_b_id, AgentHandoff.step_key == "lessons"))
    data = ((lessons_step.result or {}).get("data") or {}) if lessons_step else {}
    names = dict(db.execute(select(HistoricalEvent.id, HistoricalEvent.name).where(HistoricalEvent.organization_id == exp.organization_id)).all())
    dims = ie.history_dimensions((run_a.result or {}) if run_a else {}, (run_b.result or {}) if run_b else {}, data.get("lessons", []),
                                 (run_b.result or {}).get("history_constraints", []) if run_b else [], names)
    scores = db.scalars(select(EvaluationScore).where(EvaluationScore.experiment_id == exp.id)).all()
    by_cond: dict[str, dict[str, int]] = {}
    for s in scores:
        by_cond.setdefault(s.condition, {})[s.dimension] = s.score
    runs = (res.get("runs") or {})
    return {
        "id": exp.id, "request": exp.request_text, "research_mode": exp.research_mode, "date": exp.created_at.isoformat(),
        "inputs": {"request": exp.request_text, "event_plan_id": run_a.event_plan_id if run_a else None,
                   "same_inputs_note": res.get("note")},
        "runs": {k: {"run_id": v.get("run_id"), "usage": v.get("usage"), "duration_s": v.get("duration_s"),
                     "models": ie.run_metrics(db, v["run_id"])["models_used"] if v.get("run_id") else None,
                     "verification_passed": v.get("verification_passed"), "headline": v.get("headline")} for k, v in runs.items()},
        "numbers": ie.numeric_changes(res.get("numbers") or {}),
        "dimensions": dims,
        "events_consulted": (run_b.result or {}).get("events_consulted", []) if run_b else [],
        "lessons": [{**l, "events": [names.get(i, f"Event #{i}") for i in l.get("event_ids", [])]} for l in data.get("lessons", [])],
        "human_scores": by_cond,
        "summary": {"dimensions_changed_with_support": sum(1 for d in dims if d["changed_by_history"]),
                    "unique_statements_changed": len({x["statement"] for d in dims for x in d["changed_by_history"]}),
                    "statements_changed_with_support": sum(len(d["changed_by_history"]) for d in dims),
                    "statements_different_without_lesson": sum(len(d["different_without_specific_lesson"]) for d in dims),
                    "other_differences": sum(d["other_differences"] for d in dims),
                    "budget_numbers_changed": any(r["changed"] for r in ie.numeric_changes(res.get("numbers") or {}))},
        "method_note": ("A with-history statement counts as changed by history only if the agents themselves attributed it to past "
                        "events (the recommendation's or shortlist's 'lessons applied', or a statement naming a recorded event) AND it rests "
                        "on a specific lesson: one citing the event it names, or sharing at least three meaningful words. That lesson is "
                        "shown. Other wording differences between the two runs are counted separately as possible model variation, never as "
                        "improvements. This is a transparent keyword method, not a quality judgment; overall quality is left to human scores."),
    }


@router.get("/history-comparisons/{exp_id}")
def get_comparison(exp_id: int, cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    exp = db.get(Experiment, exp_id)
    if is_foreign_or_missing(db, cu, exp, "experiment") or exp.kind != "history_ab":
        raise HTTPException(404, "Comparison not found.")
    if exp.status != "completed":
        return {"comparison": None, "status": exp.status, "error": exp.error}
    return {"comparison": comparison_detail(db, exp), "status": exp.status}


class ComparisonScoresIn(BaseModel):
    condition: Literal["without_history", "with_history"]
    scores: dict[str, int]
    note: str | None = Field(default=None, max_length=1000)


@router.post("/history-comparisons/{exp_id}/scores")
def score_comparison(exp_id: int, body: ComparisonScoresIn, cu: CurrentUser = Depends(require(Permission.RUN_AGENTS)),
                     db: Session = Depends(get_db)) -> dict:
    exp = db.get(Experiment, exp_id)
    if is_foreign_or_missing(db, cu, exp, "experiment") or exp.kind != "history_ab":
        raise HTTPException(404, "Comparison not found.")
    _check_scores(body.scores)
    for old in db.scalars(select(EvaluationScore).where(EvaluationScore.experiment_id == exp.id, EvaluationScore.condition == body.condition,
                                                        EvaluationScore.scorer_user_id == cu.user.id)):
        db.delete(old)
    for dim, v in body.scores.items():
        db.add(EvaluationScore(organization_id=cu.organization_id, experiment_id=exp.id, condition=body.condition, dimension=dim, score=v,
                               scorer_user_id=cu.user.id, scorer_kind="human", note=body.note))
    audit(db, cu, "comparison_scored", f"experiment:{exp.id}", condition=body.condition)
    db.commit()
    return {"ok": True}


# ── Export ─────────────────────────────────────────────────────────────────────────


def export_bundle(db: Session, org: int) -> dict:
    rows = db.scalars(select(ImpactEvaluation).where(ImpactEvaluation.organization_id == org).order_by(ImpactEvaluation.id)).all()
    scores = db.scalars(select(EvaluationScore).where(EvaluationScore.organization_id == org)).all()
    tasks = _tasks_per_year(db, org)

    def anon(e):
        out = evaluation_out(db, e, for_owner=False)
        out.pop("is_mine", None)
        if not (e.show_name_in_reports and e.attribution_permission):
            out["display_name"] = f"{e.participant_code} ({e.participant_role or 'board member'})"
        return out

    exps = db.scalars(select(Experiment).where(Experiment.organization_id == org, Experiment.kind == "history_ab",
                                               Experiment.status == "completed").order_by(Experiment.id)).all()
    real = [e for e in rows if not e.is_synthetic]
    return {
        "exported_at": _now().isoformat(),
        "scenario": ie.SCENARIO, "rubric": [{"key": k, "label": l, "question": q} for k, l, q in ie.RUBRIC], "scale": ie.SCALE,
        "pilot_pending": not any(e.status == "submitted" for e in real), "pilot_message": ie.PILOT_PENDING,
        "real": {"summary": ie.summarize(real, scores, tasks), "evaluations": [anon(e) for e in real]},
        "synthetic": {"note": "Practice and test records; never counted.",
                      "summary": ie.summarize([e for e in rows if e.is_synthetic], scores, tasks),
                      "evaluations": [anon(e) for e in rows if e.is_synthetic]},
        "assumptions": {"tasks_per_year": tasks},
        "calculations": {"minutes_saved": "manual minutes − SAM SPACE minutes (negative when SAM SPACE took longer)",
                         "pct_reduction": "minutes saved ÷ manual minutes × 100, only when manual minutes > 0",
                         "annual_hours_saved": "measured minutes saved × assumed tasks per year ÷ 60 (a projection)"},
        "history_comparisons": [comparison_detail(db, x) for x in exps],
    }


@router.get("/export")
def export_json(cu: CurrentUser = Depends(require(Permission.RUN_AGENTS)), db: Session = Depends(get_db)) -> dict:
    audit(db, cu, "impact_evidence_exported", "impact:export")
    db.commit()
    return export_bundle(db, cu.organization_id)


@router.get("/export.md", response_class=PlainTextResponse)
def export_markdown(cu: CurrentUser = Depends(require(Permission.RUN_AGENTS)), db: Session = Depends(get_db)) -> str:
    return ie.bundle_markdown(export_bundle(db, cu.organization_id))
