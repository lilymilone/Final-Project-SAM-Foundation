"""Financial Intelligence: dashboard, document uploads, the review queue, and manual entry.

Viewing needs view_financials (chair, treasurer). Uploading, entering, and
approving figures needs manage_financials. Every change is audited (counts and
IDs only, never amounts or file contents).

Uploaded CSVs are parsed in code and imported only if every row is valid.
Uploaded PDFs are read for text only; the Financial Analysis agent then
organizes figures, which wait in the review queue until a board member
approves, corrects, or rejects each one. Nothing extracted by AI counts in any
total before that.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.permissions import Permission
from ...db.models import Donation, EventPlan, ExtractedFigure, FinancialDocument, FinancialRecord, HistoricalEvent
from ...services import documents as docs
from ...services.finance_dashboard import build_dashboard
from ..deps import CurrentUser, audit, get_db, is_foreign_or_missing, require, security_event

router = APIRouter(prefix="/api/finance", tags=["finance"])


def _uploads(request: Request):
    return request.app.state.settings.database_path.parent / "uploads"


def _row(r) -> dict:
    return {c.name: getattr(r, c.name) for c in r.__table__.columns}


@router.get("/dashboard")
def dashboard(cu: CurrentUser = Depends(require(Permission.VIEW_FINANCIALS)), db: Session = Depends(get_db)) -> dict:
    org = cu.organization_id
    records = [_row(r) for r in db.scalars(select(FinancialRecord).where(FinancialRecord.organization_id == org))]
    past = [_row(e) for e in db.scalars(select(HistoricalEvent).where(HistoricalEvent.organization_id == org))]
    for e in past:
        e["event_date"] = e["event_date"].isoformat() if e.get("event_date") else None
    plans = [{"name": p.name, "budget_limit_usd": p.budget_limit_usd, "status": p.status}
             for p in db.scalars(select(EventPlan).where(EventPlan.organization_id == org))]
    donations = None
    if Permission.VIEW_DONOR_DATA in cu.permissions:  # aggregates only; no names leave this function
        donations = [{"received_on": d.received_on.isoformat(), "amount_usd": d.amount_usd}
                     for d in db.scalars(select(Donation).where(Donation.organization_id == org))]
    pending = db.scalar(select(func.count(ExtractedFigure.id)).where(ExtractedFigure.organization_id == org,
                                                                     ExtractedFigure.status == "pending")) or 0
    audit(db, cu, "financials_viewed")
    db.commit()
    return build_dashboard(records, plans, past, donations, pending_review=pending)


# ── Documents ────────────────────────────────────────────────────────────────────


def doc_out(d: FinancialDocument, counts: dict | None = None) -> dict:
    return {"id": d.id, "filename": d.filename, "file_type": d.file_type, "doc_type": d.doc_type,
            "doc_type_label": docs.DOC_TYPES.get(d.doc_type, d.doc_type), "size_bytes": d.size_bytes, "status": d.status,
            "page_count": d.page_count, "notes": d.notes or [], "period_label": d.period_label, "run_id": d.run_id,
            "is_demo": d.is_demo, "created_at": d.created_at.isoformat(), "figures": counts or {}}


@router.get("/documents")
def list_documents(cu: CurrentUser = Depends(require(Permission.VIEW_FINANCIALS)), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(FinancialDocument).where(FinancialDocument.organization_id == cu.organization_id)
                      .order_by(FinancialDocument.created_at.desc()).limit(50)).all()
    counts: dict[int, dict] = {}
    for doc_id, st, n in db.execute(select(ExtractedFigure.document_id, ExtractedFigure.status, func.count())
                                    .where(ExtractedFigure.organization_id == cu.organization_id)
                                    .group_by(ExtractedFigure.document_id, ExtractedFigure.status)):
        counts.setdefault(doc_id, {})[st] = n
    for doc_id, n in db.execute(select(FinancialRecord.document_id, func.count()).where(
            FinancialRecord.organization_id == cu.organization_id, FinancialRecord.document_id.is_not(None))
            .group_by(FinancialRecord.document_id)):
        counts.setdefault(doc_id, {})["records"] = n
    return {"documents": [doc_out(d, counts.get(d.id)) for d in rows], "doc_types": docs.DOC_TYPES}


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def upload_document(request: Request, file: UploadFile = File(...), doc_type: str = Form(default="other"),
                          allow_duplicate_rows: bool = Form(default=False),
                          cu: CurrentUser = Depends(require(Permission.MANAGE_FINANCIALS)), db: Session = Depends(get_db)) -> dict:
    if doc_type not in docs.DOC_TYPES:
        raise HTTPException(422, "Unknown document type.")
    data = await file.read(docs.MAX_PDF_BYTES + 1)
    if not data:
        raise HTTPException(422, "The file is empty.")
    name = docs.sanitize_filename(file.filename)
    try:
        file_type = docs.detect_type(data, name)
    except docs.DocumentError as exc:
        security_event(db, cu, "upload_rejected", f"Financial upload “{name}” rejected: {exc}", severity="low",
                       defense="File type and size checks")
        raise HTTPException(422, str(exc)) from exc
    digest = docs.sha256(data)
    existing = db.scalar(select(FinancialDocument).where(FinancialDocument.organization_id == cu.organization_id,
                                                         FinancialDocument.sha256 == digest))
    if existing is not None:
        raise HTTPException(409, f"This exact file was already uploaded as “{existing.filename}” on "
                                 f"{existing.created_at:%b %d, %Y}. Nothing was added twice.")

    if file_type == "csv":
        rows, errors = docs.parse_ledger_csv(data.decode("utf-8-sig"))
        if errors:
            security_event(db, cu, "upload_rejected", f"CSV “{name}” rejected: {len(errors)} invalid row(s); nothing imported.",
                           severity="low", defense="Row-by-row CSV validation")
            raise HTTPException(422, "Nothing was imported. " + " | ".join(errors[:6]) + (" | …" if len(errors) > 6 else ""))
        have = {docs.duplicate_key({"period": r.period, "kind": r.kind, "category": r.category, "amount_usd": r.amount_usd})
                for r in db.scalars(select(FinancialRecord).where(FinancialRecord.organization_id == cu.organization_id,
                                                                   FinancialRecord.is_demo.is_(False)))}
        duplicates = [r for r in rows if docs.duplicate_key(r) in have]
        if duplicates and not allow_duplicate_rows:
            raise HTTPException(409, f"{len(duplicates)} row(s) match figures already recorded (same month, kind, category, and amount), "
                                     f"for example row {duplicates[0]['row']}. Nothing was imported. If they are genuinely separate "
                                     "entries, upload again and confirm.")
    stored = docs.store(data, _uploads(request), cu.organization_id, digest, file_type)
    doc = FinancialDocument(organization_id=cu.organization_id, uploaded_by=cu.user.id, filename=name, file_type=file_type,
                            doc_type=doc_type if file_type == "pdf" or doc_type != "other" else "ledger", size_bytes=len(data),
                            sha256=digest, stored_name=stored, status="imported", notes=[])
    db.add(doc)
    db.flush()
    if file_type == "csv":
        for r in rows:
            db.add(FinancialRecord(organization_id=cu.organization_id, period=r["period"], kind=r["kind"], category=r["category"],
                                   amount_usd=r["amount_usd"], description=r["description"] or f"Imported from {name}",
                                   source="document", is_demo=False, restriction=r["restriction"], purpose=r["purpose"],
                                   currency="USD", original_amount=r["original_amount"], document_id=doc.id, source_row=r["row"],
                                   verification="parsed_csv", entered_by=cu.user.id, period_months=r["period_months"],
                                   period_label=r["period_label"]))
        doc.notes = [f"{len(rows)} row(s) parsed in code and imported."] + (
            [f"{len(duplicates)} row(s) matched existing figures and were imported after confirmation."] if duplicates else [])
        audit(db, cu, "financial_document_uploaded", f"financial_document:{doc.id}", file_type="csv", rows=len(rows))
    else:
        parsed = docs.read_pdf_isolated(data)
        doc.page_count = parsed["page_count"]
        doc.text_chars = sum(len(p) for p in parsed["pages"])
        doc.notes = parsed["notes"]
        doc.status = "ready_for_extraction" if parsed["status"] == "readable" else "unreadable"
        risky = [n for n in parsed["notes"] if "none of it was run" in n or "took longer" in n or "could not be read" in n]
        if risky:
            security_event(db, cu, "upload_rejected" if doc.status == "unreadable" else "injection_detected",
                           f"PDF “{name}”: " + " ".join(risky), severity="medium", defense="Text-only PDF parsing in an isolated process",
                           commit=False)
        audit(db, cu, "financial_document_uploaded", f"financial_document:{doc.id}", file_type="pdf", status=doc.status)
    db.commit()
    return {"document": doc_out(doc)}


@router.get("/documents/{doc_id}/figures")
def document_figures(doc_id: int, cu: CurrentUser = Depends(require(Permission.VIEW_FINANCIALS)), db: Session = Depends(get_db)) -> dict:
    doc = db.get(FinancialDocument, doc_id)
    if is_foreign_or_missing(db, cu, doc, "doc"):
        raise HTTPException(404, "Document not found.")
    figures = db.scalars(select(ExtractedFigure).where(ExtractedFigure.document_id == doc_id).order_by(ExtractedFigure.page, ExtractedFigure.id)).all()
    records = db.scalars(select(FinancialRecord).where(FinancialRecord.document_id == doc_id).order_by(FinancialRecord.source_row)).all()
    return {"document": doc_out(doc), "figures": [_row(f) | {"reviewed_at": f.reviewed_at.isoformat() if f.reviewed_at else None,
                                                            "created_at": f.created_at.isoformat()} for f in figures],
            "records": [record_out(r) for r in records]}


class FigureReview(BaseModel):
    model_config = {"extra": "forbid"}
    action: Literal["approve", "reject"]
    kind: Literal["income", "expense", "reserve", "cash", "budget_income", "budget_expense"] | None = None
    category: str | None = Field(default=None, max_length=80)
    amount_usd: float | None = Field(default=None, ge=0, le=docs.MAX_AMOUNT)
    period: str | None = None
    period_months: int | None = Field(default=None, ge=1, le=12)
    restriction: Literal["unrestricted", "temporarily_restricted", "permanently_restricted"] | None = None
    purpose: Literal["operations", "program", "event", "fundraising"] | None = None

    @field_validator("period")
    @classmethod
    def _period(cls, v: str | None) -> str | None:
        if v is not None and not docs.PERIOD.match(v):
            raise ValueError("period must look like 2026-09")
        return v


@router.post("/figures/{figure_id}/review")
def review_figure(figure_id: int, body: FigureReview, cu: CurrentUser = Depends(require(Permission.MANAGE_FINANCIALS)),
                  db: Session = Depends(get_db)) -> dict:
    f = db.get(ExtractedFigure, figure_id)
    if is_foreign_or_missing(db, cu, f, "f"):
        raise HTTPException(404, "Figure not found.")
    if f.status != "pending":
        raise HTTPException(409, f"This figure is already {f.status}.")
    f.reviewed_by, f.reviewed_at = cu.user.id, datetime.now(timezone.utc)
    if body.action == "reject":
        f.status = "rejected"
        audit(db, cu, "extracted_figure_rejected", f"extracted_figure:{f.id}")
        db.commit()
        return {"figure": _row(f) | {"reviewed_at": f.reviewed_at.isoformat(), "created_at": f.created_at.isoformat()}}
    edits = body.model_dump(exclude_none=True, exclude={"action"})
    changed = sorted(k for k, v in edits.items() if getattr(f, k) != v)
    for k, v in edits.items():
        setattr(f, k, v)
    if f.amount_usd is None or f.period is None:
        raise HTTPException(422, "Set the amount and the reporting month before approving.")
    if f.currency != "USD":
        raise HTTPException(422, "Only USD figures can be approved. Convert the amount and enter it manually.")
    rec = FinancialRecord(organization_id=cu.organization_id, period=f.period, kind=f.kind, category=f.category, amount_usd=round(f.amount_usd, 2),
                          description=f"{f.label} (from the uploaded document, reviewed by a board member)", source="document",
                          is_demo=False, restriction=f.restriction, purpose=f.purpose, currency="USD", original_amount=f.original_amount,
                          document_id=f.document_id, source_page=f.page, verification="board_reviewed", entered_by=cu.user.id,
                          period_months=f.period_months or 1, period_label=f.period_label)
    db.add(rec)
    db.flush()
    f.status, f.record_id = "approved", rec.id
    f.check_notes = (f.check_notes or []) + ([f"Corrected by the reviewer: {', '.join(changed)}."] if changed else [])
    doc = db.get(FinancialDocument, f.document_id)
    if not db.scalar(select(func.count(ExtractedFigure.id)).where(ExtractedFigure.document_id == f.document_id,
                                                                  ExtractedFigure.status == "pending", ExtractedFigure.id != f.id)):
        doc.status = "reviewed"
    audit(db, cu, "extracted_figure_approved", f"extracted_figure:{f.id}", record_id=rec.id, corrected=changed)
    db.commit()
    return {"figure": _row(f) | {"reviewed_at": f.reviewed_at.isoformat(), "created_at": f.created_at.isoformat()},
            "record": record_out(rec)}


# ── Records (manual entry and listing) ─────────────────────────────────────────────


def record_out(r: FinancialRecord) -> dict:
    return {"id": r.id, "period": r.period, "kind": r.kind, "category": r.category, "amount_usd": r.amount_usd,
            "restriction": r.restriction, "purpose": r.purpose, "description": r.description, "source": r.source,
            "verification": r.verification or ("demo" if r.is_demo else r.source), "original_amount": r.original_amount,
            "document_id": r.document_id, "source_page": r.source_page, "source_row": r.source_row, "is_demo": r.is_demo,
            "period_months": r.period_months or 1, "period_label": r.period_label, "currency": r.currency or "USD",
            "updated_at": r.updated_at.isoformat() if r.updated_at else None}


@router.get("/records")
def list_records(cu: CurrentUser = Depends(require(Permission.VIEW_FINANCIALS)), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(FinancialRecord).where(FinancialRecord.organization_id == cu.organization_id)
                      .order_by(FinancialRecord.period.desc(), FinancialRecord.kind, FinancialRecord.id).limit(500)).all()
    return {"records": [record_out(r) for r in rows]}


class ManualRecord(BaseModel):
    model_config = {"extra": "forbid"}
    period: str
    kind: Literal["income", "expense", "reserve", "cash", "budget_income", "budget_expense"]
    category: str = Field(min_length=1, max_length=80)
    amount_usd: float = Field(ge=0, le=docs.MAX_AMOUNT)
    restriction: Literal["unrestricted", "temporarily_restricted", "permanently_restricted"] | None = None
    purpose: Literal["operations", "program", "event", "fundraising"] | None = None
    description: str = Field(default="", max_length=500)
    period_months: int = Field(default=1, ge=1, le=12)
    period_label: str | None = Field(default=None, max_length=80)
    confirm_duplicate: bool = False

    @field_validator("period")
    @classmethod
    def _period(cls, v: str) -> str:
        if not docs.PERIOD.match(v):
            raise ValueError("period must look like 2026-09")
        return v

    @field_validator("category", "description")
    @classmethod
    def _clean(cls, v: str) -> str:
        return v.strip().lstrip("=+-@\t")


@router.post("/records", status_code=status.HTTP_201_CREATED)
def add_record(body: ManualRecord, cu: CurrentUser = Depends(require(Permission.MANAGE_FINANCIALS)), db: Session = Depends(get_db)) -> dict:
    if not body.category:
        raise HTTPException(422, "category: enter a category.")
    key = docs.duplicate_key(body.model_dump())
    dupe = next((r for r in db.scalars(select(FinancialRecord).where(FinancialRecord.organization_id == cu.organization_id,
                                                                    FinancialRecord.period == body.period, FinancialRecord.kind == body.kind))
                 if docs.duplicate_key({"period": r.period, "kind": r.kind, "category": r.category, "amount_usd": r.amount_usd}) == key), None)
    if dupe is not None and not body.confirm_duplicate:
        raise HTTPException(409, f"A matching figure is already recorded ({dupe.category}, {dupe.period}, ${dupe.amount_usd:,.2f}). "
                                 "Confirm if this is a separate entry.")
    rec = FinancialRecord(organization_id=cu.organization_id, period=body.period, kind=body.kind, category=body.category,
                          amount_usd=round(body.amount_usd, 2), description=body.description or "Entered manually by a board member",
                          source="manual", is_demo=False, restriction=body.restriction, purpose=body.purpose, currency="USD",
                          verification="entered_by_board", entered_by=cu.user.id, period_months=body.period_months,
                          period_label=body.period_label)
    db.add(rec)
    db.flush()
    audit(db, cu, "financial_record_entered", f"financial_record:{rec.id}")
    db.commit()
    return {"record": record_out(rec)}


class RecordEdit(BaseModel):
    model_config = {"extra": "forbid"}
    period: str | None = None
    kind: Literal["income", "expense", "reserve", "cash", "budget_income", "budget_expense"] | None = None
    category: str | None = Field(default=None, min_length=1, max_length=80)
    amount_usd: float | None = Field(default=None, ge=0, le=docs.MAX_AMOUNT)
    restriction: Literal["unrestricted", "temporarily_restricted", "permanently_restricted", "not_documented"] | None = None
    purpose: Literal["operations", "program", "event", "fundraising", "not_stated"] | None = None
    description: str | None = Field(default=None, max_length=500)
    period_months: int | None = Field(default=None, ge=1, le=12)

    @field_validator("period")
    @classmethod
    def _period(cls, v: str | None) -> str | None:
        if v is not None and not docs.PERIOD.match(v):
            raise ValueError("period must look like 2026-09")
        return v


@router.put("/records/{record_id}")
def edit_record(record_id: int, body: RecordEdit, cu: CurrentUser = Depends(require(Permission.MANAGE_FINANCIALS)),
                db: Session = Depends(get_db)) -> dict:
    r = db.get(FinancialRecord, record_id)
    if is_foreign_or_missing(db, cu, r, "r"):
        raise HTTPException(404, "Record not found.")
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        if k in ("category", "description") and isinstance(v, str):
            v = v.strip().lstrip("=+-@\t")
        if k == "restriction" and v == "not_documented":
            v = None
        if k == "purpose" and v == "not_stated":
            v = None
        setattr(r, k, round(v, 2) if k == "amount_usd" and v is not None else v)
    if {"amount_usd", "kind", "period"} & set(changes) and r.verification in ("parsed_csv", "board_reviewed"):
        r.verification = "edited_by_board"  # the source document no longer matches this figure exactly
    r.updated_at, r.updated_by = datetime.now(timezone.utc), cu.user.id
    audit(db, cu, "financial_record_edited", f"financial_record:{r.id}", fields=sorted(changes))
    db.commit()
    return {"record": record_out(r)}
