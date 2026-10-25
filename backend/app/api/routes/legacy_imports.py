"""Our Legacy imports: file uploads and "Tell us about an event", reviewed and approved by a board member.

  1. A board member uploads files (PDF, CSV, XLSX, JPG/PNG, .txt/.md notes) and/or describes an event in plain words.
     Each file is checked by its contents and size, stored privately under a hash name, and read in an isolated
     process. Photos are kept but never read.
  2. The Event Intelligence agent extracts a candidate (a recorded workflow). Code keeps only values whose quoted words
     are in the cited source, leaves disagreeing figures as conflicts, and lists what is missing.
  3. The board member edits the preview, resolves each conflict, confirms any change to an already-recorded value,
     and approves. Only then is the event written, with each field's source kept alongside it.

Original files and the original description are retained. Nothing is deleted.
"""

from __future__ import annotations

import shutil
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.permissions import Permission
from ...db.models import AgentRun, EventPhoto, HistoricalEvent, LegacyDocument, LegacyImport
from ...services import legacy_sources as ls
from ...services.documents import DocumentError, sanitize_filename
from ...services.legacy import document_out, event_out
from ...services.legacy_import import EDITABLE, DecisionError, candidate_values, plan_decision
from ..deps import CurrentUser, audit, current_user, get_db, is_foreign_or_missing, require, security_event

router = APIRouter(prefix="/api/legacy", tags=["legacy-imports"])

MAX_DESCRIPTION = 6000


def _root(request: Request):
    return request.app.state.settings.database_path.parent / "uploads"


def _get_import(db: Session, cu: CurrentUser, import_id: int) -> LegacyImport:
    imp = db.get(LegacyImport, import_id)
    if is_foreign_or_missing(db, cu, imp, "import"):
        raise HTTPException(404, "Import not found.")
    return imp


def _event_values(e: HistoricalEvent) -> dict:
    return {k: (getattr(e, k).isoformat() if isinstance(getattr(e, k), date) else getattr(e, k)) for k in EDITABLE}


def import_out(db: Session, imp: LegacyImport) -> dict:
    run = db.get(AgentRun, imp.run_id) if imp.run_id else None
    target = db.get(HistoricalEvent, imp.target_event_id) if imp.target_event_id else None
    return {
        "id": imp.id, "method": imp.method, "status": imp.status, "raw_text": imp.raw_text, "created_at": imp.created_at.isoformat(),
        "run": {"id": run.id, "status": run.status, "spent_usd": run.spent_usd, "error": run.error} if run else None,
        "extraction": imp.extraction, "candidate": candidate_values(imp.extraction or {}),
        "documents": [document_out(d) for d in sorted(imp.documents, key=lambda d: d.id)],
        "target_event": {"id": target.id, "name": target.name, "values": _event_values(target)} if target else None,
        "approved_event_id": imp.approved_event_id, "decision": imp.decision,
    }


# ── Create an import (Method A: files; Method B: a description) ────────────────────────────────


@router.post("/imports", status_code=status.HTTP_201_CREATED)
async def create_import(request: Request, method: str = Form(...), description: str = Form(default=""),
                        target_event_id: int | None = Form(default=None), files: list[UploadFile] = File(default=[]),
                        cu: CurrentUser = Depends(require(Permission.MANAGE_EVENTS)), db: Session = Depends(get_db)) -> dict:
    if Permission.RUN_AGENTS not in cu.permissions:
        raise HTTPException(403, "Your board role cannot start agent workflows.")
    if method not in ("upload", "conversation"):
        raise HTTPException(422, "method must be 'upload' or 'conversation'.")
    description = (description or "").strip()
    if len(description) > MAX_DESCRIPTION:
        raise HTTPException(422, f"Please keep the description under {MAX_DESCRIPTION:,} characters.")
    if method == "conversation" and len(description) < 20:
        raise HTTPException(422, "Tell us a little more about the event (at least a sentence).")
    if method == "upload" and not files:
        raise HTTPException(422, "Choose at least one file.")
    if len(files) > ls.MAX_FILES_PER_IMPORT:
        raise HTTPException(422, f"Upload at most {ls.MAX_FILES_PER_IMPORT} files at a time.")
    target = None
    if target_event_id is not None:
        target = db.get(HistoricalEvent, target_event_id)
        if is_foreign_or_missing(db, cu, target, "event"):
            raise HTTPException(404, "Event not found.")

    accepted = []
    for f in files:  # check every file before storing any (all or nothing)
        name = sanitize_filename(f.filename, "upload")
        data = await f.read(max(ls.MAX_BYTES.values()) + 1)
        try:
            kind, ctype = ls.detect(data, name)
        except DocumentError as exc:
            security_event(db, cu, "upload_rejected", f"Our Legacy upload rejected ({name}): {exc}", severity="low",
                           defense="File type and size checks")
            raise HTTPException(422, f"{name}: {exc}") from exc
        accepted.append((name, kind, ctype, data))

    imp = LegacyImport(organization_id=cu.organization_id, created_by=cu.user.id, method=method, raw_text=description or None,
                       target_event_id=target.id if target else None, status="extracting")
    db.add(imp)
    db.flush()
    root = _root(request)
    for name, kind, ctype, data in accepted:
        stored, digest = ls.store(data, root, cu.organization_id, kind)
        parsed = ls.read_source(data, kind)
        db.add(LegacyDocument(organization_id=cu.organization_id, import_id=imp.id, filename=name, file_type=kind, content_type=ctype,
                              size_bytes=len(data), sha256=digest, stored_name=stored, status=parsed["status"],
                              text=parsed["text"] or None, parse_notes=parsed["notes"], uploaded_by=cu.user.id))
    settings = request.app.state.settings
    label = "a description" if method == "conversation" and not accepted else f"{len(accepted)} file(s)" + (" and a description" if description else "")
    run = AgentRun(organization_id=cu.organization_id, user_id=cu.user.id, workflow_type="legacy_import",
                   request_text=f"Import a past event from {label} (Our Legacy import #{imp.id})"
                                + (f" into “{target.name}”" if target else ""),
                   status="queued", strategy=cu.user.model_strategy, provider=settings.provider, budget_usd=settings.workflow_budget_usd,
                   research_mode="records", plan={"options": {"import_id": imp.id}})
    db.add(run)
    db.flush()
    imp.run_id = run.id
    audit(db, cu, "legacy_import_created", f"legacy_import:{imp.id}", method=method, files=[n for n, *_ in accepted],
          target_event_id=imp.target_event_id)
    db.commit()
    request.app.state.workflows.start(run.id, user_id=cu.user.id, organization_id=cu.organization_id, permissions=cu.permissions,
                                      strategy=cu.user.model_strategy, research_mode="records", request=run.request_text,
                                      intent_hint="legacy_import", event_plan_id=None, options={"import_id": imp.id})
    db.refresh(imp)
    return {"import": import_out(db, imp)}


@router.get("/imports")
def list_imports(cu: CurrentUser = Depends(require(Permission.MANAGE_EVENTS)), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(LegacyImport).where(LegacyImport.organization_id == cu.organization_id)
                      .order_by(LegacyImport.created_at.desc()).limit(30)).all()
    return {"imports": [{"id": i.id, "method": i.method, "status": i.status, "created_at": i.created_at.isoformat(),
                         "title": ((i.extraction or {}).get("fields") or {}).get("name", {}).get("value"),
                         "approved_event_id": i.approved_event_id, "files": len(i.documents)} for i in rows]}


@router.get("/imports/{import_id}")
def get_import(import_id: int, cu: CurrentUser = Depends(require(Permission.MANAGE_EVENTS)), db: Session = Depends(get_db)) -> dict:
    imp = _get_import(db, cu, import_id)
    run = db.get(AgentRun, imp.run_id) if imp.run_id else None
    if imp.status == "extracting" and run and run.status not in ("queued", "running"):  # the run ended without staging
        imp.status = "ready" if imp.extraction else "failed"
        db.commit()
    return {"import": import_out(db, imp)}


# ── Approve or discard ────────────────────────────────────────────────────────────────


class ApprovedFields(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    event_date: date | None = None
    event_year: int | None = Field(default=None, ge=1950, le=2100)
    location: str | None = Field(default=None, max_length=200)
    venue: str | None = Field(default=None, max_length=200)
    event_type: str | None = Field(default=None, max_length=60)
    summary: str | None = Field(default=None, max_length=4000)
    attendance: int | None = Field(default=None, ge=0, le=1_000_000)
    volunteers_count: int | None = Field(default=None, ge=0, le=1_000_000)
    fundraising_goal_usd: float | None = Field(default=None, ge=0, le=100_000_000)
    funds_raised_usd: float | None = Field(default=None, ge=0, le=100_000_000)
    total_cost_usd: float | None = Field(default=None, ge=0, le=100_000_000)
    sponsorship_usd: float | None = Field(default=None, ge=0, le=100_000_000)
    planned_budget_usd: float | None = Field(default=None, ge=0, le=100_000_000)
    sponsorship_info: str | None = Field(default=None, max_length=2000)
    positive_outcomes: str | None = Field(default=None, max_length=4000)
    problems_encountered: str | None = Field(default=None, max_length=4000)
    lessons_learned: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _date_and_year(self):
        if self.event_date and self.event_year and self.event_date.year != self.event_year:
            raise ValueError("The year does not match the date.")
        if self.event_date and not self.event_year:
            self.event_year = self.event_date.year
        return self


class ApproveIn(BaseModel):
    fields: ApprovedFields
    target_event_id: int | None = None  # None: create a new historical event
    resolved_conflicts: list[str] = Field(default_factory=list)
    confirm_overwrite: list[str] = Field(default_factory=list)
    mark_as_sample: bool = False  # a test or sample record, not a real foundation event


@router.post("/imports/{import_id}/approve")
def approve_import(import_id: int, body: ApproveIn, request: Request, cu: CurrentUser = Depends(require(Permission.MANAGE_EVENTS)),
                   db: Session = Depends(get_db)) -> dict:
    imp = _get_import(db, cu, import_id)
    if imp.status in ("approved", "discarded"):
        raise HTTPException(409, f"This import was already {imp.status}.")
    if imp.status == "extracting":
        raise HTTPException(409, "The agents are still reading the sources.")
    final = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in body.fields.model_dump().items()}
    final = {k: (v.strip() if isinstance(v, str) else v) for k, v in final.items()}
    event = None
    if body.target_event_id is not None:
        event = db.get(HistoricalEvent, body.target_event_id)
        if is_foreign_or_missing(db, cu, event, "event"):
            raise HTTPException(404, "Event not found.")
        final = {k: v for k, v in final.items() if v not in (None, "")}  # blank means "leave as recorded"
    elif not (final.get("name") or "").strip() or len(final["name"]) < 2:
        raise HTTPException(422, "Give the event a title before saving.")
    try:
        plan = plan_decision(imp.extraction or {}, final, _event_values(event) if event else None,
                             set(body.resolved_conflicts), set(body.confirm_overwrite))
    except DecisionError as exc:
        raise HTTPException(exc.status, {"message": str(exc), "items": exc.details}) from exc

    creating = event is None
    before = _event_values(event) if event else {}
    if creating:
        event = HistoricalEvent(organization_id=cu.organization_id, created_by=cu.user.id, name=final["name"],
                                location=final.get("location") or "", event_type=final.get("event_type") or "fundraiser",
                                summary=final.get("summary") or "", is_demo=body.mark_as_sample)
        db.add(event)
    for key, value in final.items():
        if key in ("location", "summary") and value is None:
            value = ""
        if key == "event_type" and not value:
            continue
        if key == "event_date" and value:
            value = date.fromisoformat(value)
        if creating or value not in (None, ""):
            setattr(event, key, value)
    sources = dict(event.field_sources or {})
    for key, prov in plan["provenance"].items():
        sources[key] = {**prov, "import_id": imp.id, "approved_by": cu.user.id, "approved_at": datetime.now(timezone.utc).isoformat()}
    event.field_sources = sources
    figures_changed = any(k in final and not creating and before.get(k) != final[k]
                          for k in ("attendance", "fundraising_goal_usd", "funds_raised_usd", "total_cost_usd", "sponsorship_usd"))
    from_docs = any(p["origin"] in ("source_fact", "board_choice") and any(i.startswith("doc:") for i in p.get("source_ids", []))
                    for p in plan["provenance"].values())
    if creating or figures_changed or event.verification_status != "verified":
        event.verification_status = "document_extracted" if from_docs else "board_reported"
        event.verified_by, event.verified_at = None, None
    event.updated_by, event.updated_at = cu.user.id, datetime.now(timezone.utc)
    db.flush()

    photo_root = request.app.state.settings.database_path.parent / "uploads" / "photos"
    for d in imp.documents:  # keep every original with the event; photos also join the gallery
        d.historical_event_id = event.id
        if d.file_type == "image":
            src = ls.stored_path(_root(request), cu.organization_id, d.stored_name)
            if src is not None:
                folder = photo_root / str(int(cu.organization_id))
                folder.mkdir(parents=True, exist_ok=True)
                ext = "png" if d.content_type == "image/png" else "jpg"
                name = f"{int(cu.organization_id)}/{uuid.uuid4().hex}.{ext}"
                shutil.copyfile(src, photo_root / name)
                db.add(EventPhoto(historical_event_id=event.id, file_path=name, caption=d.filename[:300], uploaded_by=cu.user.id,
                                  content_type=d.content_type, size_bytes=d.size_bytes, is_demo=body.mark_as_sample))
    imp.status, imp.approved_event_id, imp.approved_by, imp.approved_at = "approved", event.id, cu.user.id, datetime.now(timezone.utc)
    imp.decision = {"target": "existing" if not creating else "new", "edits": plan["edits"], "resolved_conflicts": body.resolved_conflicts,
                    "confirmed_overwrites": body.confirm_overwrite, "mark_as_sample": body.mark_as_sample}
    changes = {k: {"before": before.get(k), "after": final[k]} for k in final if not creating and before.get(k) != final[k]}
    audit(db, cu, "legacy_import_approved", f"historical_event:{event.id}", import_id=imp.id, created=creating, changes=changes,
          edits=plan["edits"], resolved_conflicts=body.resolved_conflicts)
    db.commit()
    db.refresh(event)
    return {"event": event_out(event, detail=True), "created": creating}


@router.post("/imports/{import_id}/discard")
def discard_import(import_id: int, cu: CurrentUser = Depends(require(Permission.MANAGE_EVENTS)), db: Session = Depends(get_db)) -> dict:
    imp = _get_import(db, cu, import_id)
    if imp.status == "approved":
        raise HTTPException(409, "An approved import cannot be discarded; edit the event instead.")
    imp.status = "discarded"
    audit(db, cu, "legacy_import_discarded", f"legacy_import:{imp.id}")
    db.commit()
    return {"id": imp.id, "status": imp.status, "note": "The original files and description are kept; nothing was added to Our Legacy."}


# ── Original files ──────────────────────────────────────────────────────────────────


@router.get("/documents/{doc_id}")
def get_document(doc_id: int, request: Request, cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> FileResponse:
    doc = db.get(LegacyDocument, doc_id)
    if is_foreign_or_missing(db, cu, doc, "document"):
        raise HTTPException(404, "Document not found.")
    if doc.file_type != "image" and Permission.VIEW_FINANCIALS not in cu.permissions and doc.uploaded_by != cu.user.id:
        security_event(db, cu, "permission_denied", f"Source document #{doc.id} requested without financial access.", severity="low",
                       defense="Role-based access to source documents")
        raise HTTPException(403, "Source documents may contain financial details. The treasurer, the chair, or the person who "
                                 "uploaded it can open the original.")
    path = ls.stored_path(_root(request), cu.organization_id, doc.stored_name)
    if path is None:
        raise HTTPException(404, "The original file is missing.")
    inline = doc.file_type == "image"
    return FileResponse(path, media_type=doc.content_type, filename=sanitize_filename(doc.filename),
                        content_disposition_type="inline" if inline else "attachment",
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                                 "Content-Security-Policy": "default-src 'none'; img-src 'self'; sandbox"})
