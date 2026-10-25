"""Our Legacy: the foundation's institutional event history.

  * Events can be created and edited by authorized board members, and every
    edit is audited with before/after values. Events are never deleted,
    because this is institutional memory.
  * Reflections are append-only. Each keeps the contributor, the date, and
    the original words. There is no edit or delete route, and AI output is
    stored separately as lessons.
  * Photos are checked by their file signature (PNG, JPEG, WebP), limited to
    5 MB, stored outside the web root, and served only to signed-in members of
    the same workspace.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ...core.permissions import Permission
from ...db.models import AgentHandoff, AgentRun, BoardReflection, EventPhoto, HistoricalEvent, HistoricalLesson
from ...services.legacy import (
    REFLECTION_QUESTIONS,
    event_out,
    history_stats,
    legacy_metrics,
    lesson_evidence_labels,
    lesson_out,
    photo_out,
    reflection_out,
)
from ..deps import CurrentUser, audit, current_user, get_db, is_foreign_or_missing, require, security_event

router = APIRouter(prefix="/api", tags=["legacy"])

MILESTONE_FUNDS_STEP = 25_000
MAX_PHOTO_BYTES = 5 * 1024 * 1024
SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
)
EVENT_FIELDS = ("name", "event_date", "event_type", "venue", "location", "attendance", "fundraising_goal_usd",
                "funds_raised_usd", "total_cost_usd", "sponsorship_usd", "sponsorship_info", "summary", "notes",
                "volunteers_count", "repeat_participants", "partnerships_formed", "funds_directed_usd", "community_outcomes",
                "event_year", "planned_budget_usd", "positive_outcomes", "problems_encountered", "lessons_learned")
FIGURES = ("attendance", "fundraising_goal_usd", "funds_raised_usd", "total_cost_usd", "sponsorship_usd", "planned_budget_usd")


def _sniff(head: bytes) -> tuple[str, str] | None:
    for sig, ctype, ext in SIGNATURES:
        if head.startswith(sig):
            return ctype, ext
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


def _photo_dir(request: Request) -> Path:
    path = request.app.state.settings.database_path.parent / "uploads" / "photos"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _photo_path(request: Request, file_path: str) -> Path:
    """Resolve a stored photo inside the photo folder only (no path traversal, even from a bad database value)."""
    root = _photo_dir(request).resolve()
    path = (root / file_path).resolve()
    if root not in path.parents:
        raise HTTPException(404, "Photo file is missing.")
    return path


def _get_event(db: Session, cu: CurrentUser, event_id: int) -> HistoricalEvent:
    event = db.get(HistoricalEvent, event_id)
    if is_foreign_or_missing(db, cu, event, "event"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    return event


# ── Events ───────────────────────────────────────────────────────────────────────


class HistoricalEventIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    event_date: date | None = None
    event_type: str = Field(default="fundraiser", max_length=60)
    venue: str | None = Field(default=None, max_length=200)
    location: str = Field(default="", max_length=200)
    attendance: int | None = Field(default=None, ge=0, le=1_000_000)
    fundraising_goal_usd: float | None = Field(default=None, ge=0, le=100_000_000)
    funds_raised_usd: float | None = Field(default=None, ge=0, le=100_000_000)
    total_cost_usd: float | None = Field(default=None, ge=0, le=100_000_000)
    sponsorship_usd: float | None = Field(default=None, ge=0, le=100_000_000)
    sponsorship_info: str | None = Field(default=None, max_length=2000)
    summary: str = Field(default="", max_length=4000)
    notes: str | None = Field(default=None, max_length=4000)
    # Community impact: leave empty when not recorded (shown as "Not recorded", never as zero).
    volunteers_count: int | None = Field(default=None, ge=0, le=1_000_000)
    repeat_participants: int | None = Field(default=None, ge=0, le=1_000_000)
    partnerships_formed: int | None = Field(default=None, ge=0, le=10_000)
    funds_directed_usd: float | None = Field(default=None, ge=0, le=100_000_000)
    community_outcomes: str | None = Field(default=None, max_length=4000)
    # Organizational memory: optional; unknown stays empty.
    event_year: int | None = Field(default=None, ge=1950, le=2100)
    planned_budget_usd: float | None = Field(default=None, ge=0, le=100_000_000)
    positive_outcomes: str | None = Field(default=None, max_length=4000)
    problems_encountered: str | None = Field(default=None, max_length=4000)
    lessons_learned: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _year(self):
        if self.event_date and self.event_year and self.event_date.year != self.event_year:
            raise ValueError("The year does not match the date.")
        if self.event_date and not self.event_year:
            self.event_year = self.event_date.year
        return self

    @field_validator("name", "event_type", "location", "summary")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


@router.get("/legacy/events")
def list_history(cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    events = db.scalars(select(HistoricalEvent).where(HistoricalEvent.organization_id == cu.organization_id)
                        .order_by(HistoricalEvent.event_date.desc())).all()
    lessons = db.scalars(select(HistoricalLesson).where(HistoricalLesson.organization_id == cu.organization_id,
                                                        HistoricalLesson.status.is_distinct_from("superseded"),
                                                        HistoricalLesson.status.is_distinct_from("dismissed"))
                         .order_by(HistoricalLesson.created_at.desc())).all()
    by_event: dict[int, list[str]] = {}
    for l in lessons:
        ids = {e.get("id") for e in (l.evidence or []) if e.get("type") == "event"} | ({l.focus_event_id} if l.focus_event_id else set())
        for i in ids:
            by_event.setdefault(i, []).append(l.lesson)
    out = []
    for e in events:
        item = event_out(e)
        item["lesson_count"] = len(by_event.get(e.id, []))
        item["top_lesson"] = by_event.get(e.id, [None])[0]
        out.append(item)
    return {"events": out, "stats": history_stats(list(events))}


@router.get("/legacy/events/{event_id}")
def get_history(event_id: int, cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    event = _get_event(db, cu, event_id)
    lessons = [l for l in db.scalars(select(HistoricalLesson).where(HistoricalLesson.organization_id == cu.organization_id)
                                     .order_by(HistoricalLesson.created_at.desc()))
               if (l.status or "new") != "superseded" and (
                   l.focus_event_id == event_id or any(e.get("type") == "event" and e.get("id") == event_id for e in (l.evidence or []))
                   or any(e.get("type") == "reflection" and e.get("id") in {r.id for r in event.reflections} for e in (l.evidence or [])))]
    lessons.sort(key=lambda l: (l.focus_event_id != event_id, l.status != "adopted"))  # this event's own analysis first
    labels = lesson_evidence_labels(db, cu.organization_id, lessons)
    out = event_out(event, detail=True)
    for d in out["documents"]:
        d["can_open"] = d["file_type"] == "image" or Permission.VIEW_FINANCIALS in cu.permissions or \
            any(x.id == d["id"] and x.uploaded_by == cu.user.id for x in event.documents)
    return {"event": out, "lessons": [lesson_out(l, labels[l.id]) for l in lessons],
            "latest_analysis": _latest_analysis(db, cu.organization_id, event_id),
            "questions": [{"key": k, "question": q} for k, q in REFLECTION_QUESTIONS]}


def _latest_analysis(db: Session, org_id: int, event_id: int) -> dict | None:
    """The most recent completed Event Intelligence analysis of this event (persisted in the run log)."""
    runs = db.scalars(select(AgentRun).where(AgentRun.organization_id == org_id, AgentRun.workflow_type == "event_learning",
                                             AgentRun.status.in_(("completed", "completed_with_warnings")))
                      .order_by(AgentRun.started_at.desc()).limit(25)).all()
    for run in runs:
        if ((run.plan or {}).get("options") or {}).get("historical_event_id") != event_id:
            continue
        step = db.scalar(select(AgentHandoff).where(AgentHandoff.run_id == run.id, AgentHandoff.to_agent == "event_intelligence"))
        data = ((step.result or {}).get("data") or {}) if step else {}
        return {"run_id": run.id, "date": run.started_at.isoformat(), "themes": data.get("themes", []),
                "disagreements": data.get("disagreements", []), "comparison": data.get("comparison"),
                "numeric_comparison_note": data.get("numeric_comparison_note")}
    return None


@router.post("/legacy/events", status_code=status.HTTP_201_CREATED)
def create_history(body: HistoricalEventIn, cu: CurrentUser = Depends(require(Permission.MANAGE_EVENTS)),
                   db: Session = Depends(get_db)) -> dict:
    org = cu.organization_id
    raised_before = db.scalar(select(func.coalesce(func.sum(HistoricalEvent.funds_raised_usd), 0.0))
                              .where(HistoricalEvent.organization_id == org)) or 0.0
    event = HistoricalEvent(organization_id=org, created_by=cu.user.id, verification_status="board_reported",
                            field_sources={k: {"origin": "board_entered"} for k, v in body.model_dump().items() if v not in (None, "")},
                            **body.model_dump())
    db.add(event)
    db.flush()
    count = db.scalar(select(func.count(HistoricalEvent.id)).where(HistoricalEvent.organization_id == org)) or 0
    raised_after = raised_before + (body.funds_raised_usd or 0)
    milestone = None
    if raised_after // MILESTONE_FUNDS_STEP > raised_before // MILESTONE_FUNDS_STEP:
        milestone = f"Recorded lifetime funds raised passed ${int(raised_after // MILESTONE_FUNDS_STEP * MILESTONE_FUNDS_STEP):,}."
    elif count % 5 == 0:
        milestone = f"{count} events now preserved in Our Legacy."
    audit(db, cu, "historical_event_created", f"historical_event:{event.id}", name=event.name)
    db.commit()
    db.refresh(event)
    return {"event": event_out(event), "milestone": milestone}


@router.put("/legacy/events/{event_id}")
def update_history(event_id: int, body: HistoricalEventIn, cu: CurrentUser = Depends(require(Permission.MANAGE_EVENTS)),
                   db: Session = Depends(get_db)) -> dict:
    event = _get_event(db, cu, event_id)
    changes = {}
    for key, value in body.model_dump().items():
        before = getattr(event, key)
        if before != value:
            changes[key] = {"before": before.isoformat() if isinstance(before, date) else before,
                            "after": value.isoformat() if isinstance(value, date) else value}
            setattr(event, key, value)
    if changes:
        event.updated_by = cu.user.id
        event.updated_at = datetime.now(timezone.utc)
        sources = dict(event.field_sources or {})
        for key in changes:
            sources[key] = {"origin": "board_edited", "edited_by": cu.user.id, "edited_at": event.updated_at.isoformat()}
        event.field_sources = sources
        if event.verification_status == "verified" and set(changes) & set(FIGURES):  # verified figures changed: no longer verified
            event.verification_status, event.verified_by, event.verified_at = "board_reported", None, None
        audit(db, cu, "historical_event_edited", f"historical_event:{event.id}", changes=changes)
    db.commit()
    db.refresh(event)
    return {"event": event_out(event, detail=True), "changed_fields": sorted(changes)}


@router.post("/legacy/events/{event_id}/verify")
def verify_history(event_id: int, cu: CurrentUser = Depends(require(Permission.MANAGE_FINANCIALS)), db: Session = Depends(get_db)) -> dict:
    """The treasurer or chair confirms the figures against the accounting records. AI extraction never sets this."""
    event = _get_event(db, cu, event_id)
    event.verification_status, event.verified_by, event.verified_at = "verified", cu.user.id, datetime.now(timezone.utc)
    audit(db, cu, "historical_event_verified", f"historical_event:{event.id}",
          figures={k: getattr(event, k) for k in FIGURES})
    db.commit()
    db.refresh(event)
    return {"event": event_out(event, detail=True)}


# ── Reflections (append-only) ────────────────────────────────────────────────────


class ReflectionIn(BaseModel):
    went_well: str = Field(default="", max_length=4000)
    challenges: str = Field(default="", max_length=4000)
    unexpected_costs: str = Field(default="", max_length=4000)
    attendee_feedback: str = Field(default="", max_length=4000)
    should_repeat: str = Field(default="", max_length=4000)
    do_differently: str = Field(default="", max_length=4000)
    advice: str = Field(default="", max_length=4000)
    welcome_inclusion: str = Field(default="", max_length=4000)
    connection_moments: str = Field(default="", max_length=4000)
    volunteer_appreciation: str = Field(default="", max_length=4000)
    accessibility_issues: str = Field(default="", max_length=4000)
    inclusion_improvements: str = Field(default="", max_length=4000)
    rating: int | None = Field(default=None, ge=1, le=5)
    # Authorized attribution: record another board member's reflection (e.g. shared by phone). Both names are kept.
    attributed_to: str | None = Field(default=None, max_length=120)


@router.post("/legacy/events/{event_id}/reflections", status_code=status.HTTP_201_CREATED)
def add_reflection(event_id: int, body: ReflectionIn, cu: CurrentUser = Depends(require(Permission.WRITE_REFLECTIONS)),
                   db: Session = Depends(get_db)) -> dict:
    event = _get_event(db, cu, event_id)
    answers = body.model_dump(exclude={"rating", "attributed_to"})
    if not any(v.strip() for v in answers.values()):
        raise HTTPException(422, "Please answer at least one question.")
    me = f"{cu.user.first_name} {cu.user.last_name}".strip()
    on_behalf = (body.attributed_to or "").strip()
    reflection = BoardReflection(historical_event_id=event.id, user_id=cu.user.id, author_label=on_behalf or me,
                                 recorded_by_label=me if on_behalf else None,
                                 rating=body.rating, **{k: v.strip() for k, v in answers.items()})
    db.add(reflection)
    db.flush()
    audit(db, cu, "reflection_created", f"historical_event:{event.id}", reflection_id=reflection.id,
          attributed_to=on_behalf or None)
    db.commit()
    return {"reflection": reflection_out(reflection)}


# ── Photos ───────────────────────────────────────────────────────────────────────


@router.post("/legacy/events/{event_id}/photos", status_code=status.HTTP_201_CREATED)
async def upload_photo(event_id: int, request: Request, file: UploadFile = File(...), caption: str = Form(default="", max_length=300),
                       cu: CurrentUser = Depends(require(Permission.MANAGE_EVENTS)), db: Session = Depends(get_db)) -> dict:
    event = _get_event(db, cu, event_id)
    data = await file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        security_event(db, cu, "upload_rejected", "Photo rejected: larger than 5 MB.", severity="low", defense="Upload size limit")
        raise HTTPException(413, "Photos must be 5 MB or smaller.")
    kind = _sniff(data[:16])
    if kind is None:
        security_event(db, cu, "upload_rejected", "Photo rejected: not a PNG, JPEG, or WebP image by its contents.", severity="low",
                       defense="File signature check")
        raise HTTPException(422, "Only PNG, JPEG, or WebP images are accepted (checked by file contents, not name).")
    content_type, ext = kind
    folder = _photo_dir(request) / str(int(cu.organization_id))  # workspace-scoped storage; names are random, never user-supplied
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{int(cu.organization_id)}/{uuid.uuid4().hex}.{ext}"
    (_photo_dir(request) / name).write_bytes(data)
    photo = EventPhoto(historical_event_id=event.id, file_path=name, caption=caption.strip(), uploaded_by=cu.user.id,
                       content_type=content_type, size_bytes=len(data), is_demo=False)
    db.add(photo)
    db.flush()
    audit(db, cu, "photo_uploaded", f"historical_event:{event.id}", photo_id=photo.id, size=len(data))
    db.commit()
    return {"photo": photo_out(photo)}


@router.get("/legacy/photos/{photo_id}")
def get_photo(photo_id: int, request: Request, cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> FileResponse:
    photo = db.get(EventPhoto, photo_id)
    if photo is None or db.get(HistoricalEvent, photo.historical_event_id).organization_id != cu.organization_id:
        raise HTTPException(404, "Photo not found.")
    path = _photo_path(request, photo.file_path)
    if not path.is_file():
        raise HTTPException(404, "Photo file is missing.")
    return FileResponse(path, media_type=photo.content_type or "application/octet-stream",
                        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})


@router.delete("/legacy/photos/{photo_id}")
def delete_photo(photo_id: int, request: Request, cu: CurrentUser = Depends(require(Permission.MANAGE_EVENTS)),
                 db: Session = Depends(get_db)) -> dict:
    photo = db.get(EventPhoto, photo_id)
    if photo is None or db.get(HistoricalEvent, photo.historical_event_id).organization_id != cu.organization_id:
        raise HTTPException(404, "Photo not found.")
    _photo_path(request, photo.file_path).unlink(missing_ok=True)
    audit(db, cu, "photo_removed", f"historical_event:{photo.historical_event_id}", photo_id=photo.id)
    db.delete(photo)
    db.commit()
    return {"ok": True}


# ── Lessons + impact ────────────────────────────────────────────────────────────


@router.get("/lessons")
def list_lessons(include_superseded: bool = False, cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    q = select(HistoricalLesson).where(HistoricalLesson.organization_id == cu.organization_id)
    if not include_superseded:
        q = q.where(or_(HistoricalLesson.status.is_(None), HistoricalLesson.status != "superseded"))
    rows = db.scalars(q.order_by(HistoricalLesson.created_at.desc()).limit(80)).all()
    labels = lesson_evidence_labels(db, cu.organization_id, rows)
    return {"lessons": [lesson_out(l, labels[l.id]) for l in rows]}


class LessonReview(BaseModel):
    status: Literal["new", "reviewed", "adopted", "dismissed"]


@router.post("/lessons/{lesson_id}/review")
def review_lesson(lesson_id: int, body: LessonReview, cu: CurrentUser = Depends(require(Permission.RUN_AGENTS)),
                  db: Session = Depends(get_db)) -> dict:
    lesson = db.get(HistoricalLesson, lesson_id)
    if is_foreign_or_missing(db, cu, lesson, "lesson"):
        raise HTTPException(404, "Lesson not found.")
    lesson.status = body.status
    lesson.reviewed_by = cu.user.id
    lesson.reviewed_at = datetime.now(timezone.utc)
    audit(db, cu, "lesson_reviewed", f"lesson:{lesson.id}", status=body.status)
    db.commit()
    return {"id": lesson.id, "status": lesson.status}


AREA_LABELS = {"fundraising_approach": "Fundraising approaches", "logistics": "Logistics", "sponsorship": "Sponsorship",
               "board_feedback": "Board feedback", "costs": "Costs and overruns", "community": "Community building", "other": "Other"}
BASIS_LABELS = {"board_feedback": "Board feedback (subjective)", "event_records": "Interpretation of recorded event data",
                "records_and_feedback": "Recorded data and board feedback"}


@router.get("/legacy/insights")
def insights(cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Cross-event learning: facts computed now from the records (no AI), plus the latest all-events analysis by the
    Event Intelligence agent, with every lesson linked to the events and reflections behind it."""
    from ...services import calculators as calc
    events = db.scalars(select(HistoricalEvent).where(HistoricalEvent.organization_id == cu.organization_id)).all()
    rows = [{"id": e.id, "name": e.name, "event_type": e.event_type, "attendance": e.attendance, "funds_raised_usd": e.funds_raised_usd,
             "total_cost_usd": e.total_cost_usd, "fundraising_goal_usd": e.fundraising_goal_usd, "sponsorship_usd": e.sponsorship_usd,
             "planned_budget_usd": e.planned_budget_usd, "volunteers_count": e.volunteers_count,
             "repeat_participants": e.repeat_participants, "partnerships_formed": e.partnerships_formed} for e in events]
    names = {e.id: e.name for e in events}
    observations = [{**o, "events": [{"id": i, "name": names.get(i)} for i in o["event_ids"]], "area_label": AREA_LABELS.get(o["area"])}
                    for o in calc.quantitative_observations(rows)]
    latest = None
    runs = db.scalars(select(AgentRun).where(AgentRun.organization_id == cu.organization_id, AgentRun.workflow_type == "event_learning",
                                             AgentRun.status.in_(("completed", "completed_with_warnings")))
                      .order_by(AgentRun.started_at.desc()).limit(25)).all()
    for run in runs:
        if ((run.plan or {}).get("options") or {}).get("historical_event_id"):
            continue  # single-event analyses are shown on that event's page
        step = db.scalar(select(AgentHandoff).where(AgentHandoff.run_id == run.id, AgentHandoff.step_key == "lessons"))
        data = ((step.result or {}).get("data") or {}) if step else {}
        saved = db.scalars(select(HistoricalLesson).where(HistoricalLesson.run_id == run.id)).all()
        labels = lesson_evidence_labels(db, cu.organization_id, saved)
        by_text = {l.lesson: l for l in saved}
        items = []
        for l in data.get("lessons", []):
            row = by_text.get(l["text"])
            items.append({**l, "area_label": AREA_LABELS.get(l.get("area"), "Other"), "basis_label": BASIS_LABELS.get(l.get("basis"), ""),
                          "lesson_id": row.id if row else None, "status": (row.status if row else None) or "new",
                          "evidence": labels.get(row.id, []) if row else []})
        latest = {"run_id": run.id, "date": run.started_at.isoformat(), "summary": (step.result or {}).get("summary") if step else None,
                  "lessons": items, "themes": data.get("themes", []), "disagreements": data.get("disagreements", []),
                  "community_insights": data.get("community_insights", [])}
        break
    return {"quantitative_observations": observations, "latest_analysis": latest, "areas": AREA_LABELS,
            "note": "Numbers are computed from recorded figures; lessons are interpretations that cite their records. "
                    "Imported figures are AI-extracted and board-approved, not verified accounting data, unless marked verified."}


@router.get("/legacy/metrics")
def metrics(cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return legacy_metrics(db, cu.organization_id)
