"""Donations & Compliance: records, campaigns, import/export, acknowledgment tracking, compliance review.

Viewing needs view_donor_data (chair, treasurer); changing records needs
manage_donations. Donor emails never leave the server (only "has email").
Every change and export is audited with IDs and field names, never donor
details. Nothing here sends anything: "completed" acknowledgment status means
a person sent it outside SAM SPACE.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...compliance import public_references
from ...core.permissions import Permission
from ...db.models import Campaign, Donation, Donor, EventPlan, FinancialRecord, HistoricalEvent
from ...services import documents as docs
from ...services import donations as dsvc
from ..deps import CurrentUser, audit, current_user, get_db, is_foreign_or_missing, require, security_event

router = APIRouter(prefix="/api", tags=["donations"])

ContributionType = Literal["monetary", "in_kind", "event_ticket", "sponsorship", "matching_gift"]
PaymentStatus = Literal["received", "pledged", "pending", "returned"]
AckStatus = Literal["not_started", "prepared", "completed", "not_needed"]
Restriction = Literal["unrestricted", "temporarily_restricted", "permanently_restricted"]


def _plain(d: Donation, donor: Donor | None, campaign: Campaign | None) -> dict:
    return {
        "id": d.id, "donation_id": dsvc.donation_code(d.id), "donor_id": donor.donor_code if donor else None, "donor_ref": d.donor_id,
        "donor_name": d.donor_name, "has_email": bool(d.donor_email), "amount_usd": d.amount_usd, "currency": d.currency or "USD",
        "received_on": d.received_on.isoformat(), "method": d.method, "designation": d.designation,
        "contribution_type": d.contribution_type or "monetary", "restriction": d.restriction, "payment_status": d.payment_status or "received",
        "ack_status": d.ack_status or ("completed" if d.acknowledged else "not_started"), "acknowledged": d.acknowledged,
        "campaign_id": d.campaign_id, "campaign": campaign.name if campaign else None, "in_kind_description": d.in_kind_description,
        "goods_services_value_usd": d.goods_services_value_usd, "notes": d.notes, "source": d.source or ("demo" if d.is_demo else "manual"),
        "is_demo": d.is_demo, "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        "tax_treatment": "Not determined by SAM SPACE",
    }


def _load(db: Session, org: int) -> tuple[list[dict], list[dict]]:
    donors = {x.id: x for x in db.scalars(select(Donor).where(Donor.organization_id == org))}
    camps = {c.id: c for c in db.scalars(select(Campaign).where(Campaign.organization_id == org))}
    rows = db.scalars(select(Donation).where(Donation.organization_id == org).order_by(Donation.received_on.desc(), Donation.id.desc())).all()
    items = [_plain(d, donors.get(d.donor_id), camps.get(d.campaign_id)) for d in rows]
    dupes = dsvc.duplicate_index(items)
    today = date.today()
    for it in items:
        it["flags"] = dsvc.flags_for(it, dupes, today)
    campaigns = [{"id": c.id, "name": c.name, "kind": c.kind, "goal_usd": c.goal_usd, "is_demo": c.is_demo,
                  "starts_on": c.starts_on.isoformat() if c.starts_on else None, "ends_on": c.ends_on.isoformat() if c.ends_on else None,
                  "event_plan_id": c.event_plan_id, "historical_event_id": c.historical_event_id} for c in camps.values()]
    return items, campaigns


def _ledger(db: Session, org: int) -> list[dict]:
    return [{"period": r.period, "kind": r.kind, "category": r.category, "amount_usd": r.amount_usd, "period_months": r.period_months}
            for r in db.scalars(select(FinancialRecord).where(FinancialRecord.organization_id == org))]


@router.get("/donations")
def list_donations(search: str | None = Query(default=None, max_length=100), campaign_id: int | None = None,
                   payment_status: PaymentStatus | None = None, ack_status: AckStatus | None = None,
                   contribution_type: ContributionType | None = None, restriction: Restriction | Literal["not_documented"] | None = None,
                   date_from: date | None = None, date_to: date | None = None, flagged: bool = False,
                   cu: CurrentUser = Depends(require(Permission.VIEW_DONOR_DATA)), db: Session = Depends(get_db)) -> dict:
    items, campaigns = _load(db, cu.organization_id)
    summary = dsvc.summarize(items, campaigns, _ledger(db, cu.organization_id))
    shown = items
    if search:
        q = search.lower().strip()
        shown = [d for d in shown if q in d["donor_name"].lower() or q in (d["donor_id"] or "").lower() or q in d["donation_id"].lower()
                 or q in (d["campaign"] or "").lower() or q in (d["notes"] or "").lower()]
    for key, value in (("campaign_id", campaign_id), ("payment_status", payment_status), ("ack_status", ack_status),
                       ("contribution_type", contribution_type)):
        if value is not None:
            shown = [d for d in shown if d[key] == value]
    if restriction is not None:
        shown = [d for d in shown if (d["restriction"] or "not_documented") == restriction]
    if date_from:
        shown = [d for d in shown if d["received_on"] >= date_from.isoformat()]
    if date_to:
        shown = [d for d in shown if d["received_on"] <= date_to.isoformat()]
    if flagged:
        shown = [d for d in shown if any(f["severity"] in ("high", "medium") for f in d["flags"])]
    audit(db, cu, "donor_data_viewed")
    db.commit()
    return {
        "donations": shown, "summary": summary, "campaigns": campaigns,
        "totals": {"count": len(items), "amount_usd": summary["received_usd"],
                   "needs_attention": sum(1 for d in items if any(f["severity"] in ("high", "medium") for f in d["flags"])),
                   "unacknowledged": sum(1 for d in items if d["payment_status"] == "received" and d["ack_status"] in ("not_started", "prepared"))},
        "is_demo": any(d["is_demo"] for d in items),
        "note": "Flags are for review by a person or a professional. SAM SPACE never contacts donors or decides tax treatment.",
    }


class DonationIn(BaseModel):
    model_config = {"extra": "forbid"}
    donor_name: str = Field(min_length=1, max_length=200)
    donor_email: str | None = Field(default=None, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    received_on: date
    amount_usd: float = Field(ge=0, le=docs.MAX_AMOUNT)
    contribution_type: ContributionType = "monetary"
    payment_status: PaymentStatus = "received"
    ack_status: AckStatus = "not_started"
    restriction: Restriction | None = None
    designation: str = Field(default="General fund", max_length=120)
    method: Literal["check", "online", "wire", "cash", "card", "stock", "other"] | None = None
    campaign_id: int | None = None
    in_kind_description: str | None = Field(default=None, max_length=300)
    goods_services_value_usd: float | None = Field(default=None, ge=0, le=docs.MAX_AMOUNT)
    notes: str = Field(default="", max_length=1000)
    confirm_duplicate: bool = False

    @field_validator("donor_name", "designation", "notes", "in_kind_description")
    @classmethod
    def _clean(cls, v: str | None) -> str | None:
        return v.strip().lstrip("=+-@\t") if isinstance(v, str) else v


def _donor(db: Session, org: int, name: str, email: str | None) -> Donor:
    existing = db.scalar(select(Donor).where(Donor.organization_id == org, func.lower(Donor.name) == name.lower()))
    if existing:
        if email and not existing.email:
            existing.email = email
        return existing
    n = (db.scalar(select(func.count(Donor.id)).where(Donor.organization_id == org)) or 0) + 1
    code = f"DNR-{n:04d}"
    while db.scalar(select(Donor.id).where(Donor.organization_id == org, Donor.donor_code == code)):
        n += 1
        code = f"DNR-{n:04d}"
    donor = Donor(organization_id=org, donor_code=code, name=name, email=email)
    db.add(donor)
    db.flush()
    return donor


def _check_campaign(db: Session, org: int, campaign_id: int | None) -> None:
    if campaign_id is not None:
        c = db.get(Campaign, campaign_id)
        if c is None or c.organization_id != org:
            raise HTTPException(404, "Campaign not found.")


def _duplicate_of(db: Session, org: int, name: str, received_on: date, amount: float, exclude: int | None = None) -> Donation | None:
    key = dsvc.duplicate_key(name, received_on.isoformat(), amount)
    for d in db.scalars(select(Donation).where(Donation.organization_id == org, Donation.received_on == received_on)):
        if d.id != exclude and dsvc.duplicate_key(d.donor_name, d.received_on.isoformat(), d.amount_usd) == key:
            return d
    return None


def _apply(d: Donation, body: dict) -> None:
    for k in ("donor_name", "received_on", "amount_usd", "contribution_type", "payment_status", "restriction", "designation", "method",
              "campaign_id", "in_kind_description", "goods_services_value_usd", "notes"):
        if k in body:
            setattr(d, k, body[k])
    if "ack_status" in body:
        d.ack_status = body["ack_status"]
        d.acknowledged = body["ack_status"] == "completed"
        d.acknowledged_on = date.today() if d.acknowledged and not d.acknowledged_on else (d.acknowledged_on if d.acknowledged else None)


@router.post("/donations", status_code=status.HTTP_201_CREATED)
def create_donation(body: DonationIn, cu: CurrentUser = Depends(require(Permission.MANAGE_DONATIONS)), db: Session = Depends(get_db)) -> dict:
    org = cu.organization_id
    _check_campaign(db, org, body.campaign_id)
    dupe = _duplicate_of(db, org, body.donor_name, body.received_on, body.amount_usd)
    if dupe and not body.confirm_duplicate:
        raise HTTPException(409, f"A gift with the same donor, date, and amount already exists ({dsvc.donation_code(dupe.id)}). "
                                 "Confirm if this is a separate gift.")
    donor = _donor(db, org, body.donor_name, body.donor_email)
    d = Donation(organization_id=org, donor_name=body.donor_name, donor_email=body.donor_email or donor.email, amount_usd=body.amount_usd,
                 received_on=body.received_on, donor_id=donor.id, currency="USD", source="manual", is_demo=False)
    _apply(d, body.model_dump(exclude={"confirm_duplicate", "donor_email"}))
    db.add(d)
    db.flush()
    audit(db, cu, "donation_created", f"donation:{d.id}")
    db.commit()
    items, _ = _load(db, org)
    return {"donation": next(x for x in items if x["id"] == d.id)}


class DonationEdit(BaseModel):
    model_config = {"extra": "forbid"}
    received_on: date | None = None
    amount_usd: float | None = Field(default=None, ge=0, le=docs.MAX_AMOUNT)
    contribution_type: ContributionType | None = None
    payment_status: PaymentStatus | None = None
    ack_status: AckStatus | None = None
    restriction: Restriction | Literal["not_documented"] | None = None
    designation: str | None = Field(default=None, max_length=120)
    method: Literal["check", "online", "wire", "cash", "card", "stock", "other"] | None = None
    campaign_id: int | None = None
    in_kind_description: str | None = Field(default=None, max_length=300)
    goods_services_value_usd: float | None = Field(default=None, ge=0, le=docs.MAX_AMOUNT)
    notes: str | None = Field(default=None, max_length=1000)


@router.put("/donations/{donation_id}")
def edit_donation(donation_id: int, body: DonationEdit, cu: CurrentUser = Depends(require(Permission.MANAGE_DONATIONS)),
                  db: Session = Depends(get_db)) -> dict:
    d = db.get(Donation, donation_id)
    if is_foreign_or_missing(db, cu, d, "d"):
        raise HTTPException(404, "Donation not found.")
    changes = body.model_dump(exclude_unset=True)
    if "campaign_id" in changes:
        _check_campaign(db, cu.organization_id, changes["campaign_id"])
    if changes.get("restriction") == "not_documented":
        changes["restriction"] = None
    for k in ("designation", "notes", "in_kind_description"):
        if isinstance(changes.get(k), str):
            changes[k] = changes[k].strip().lstrip("=+-@\t")
    _apply(d, changes)
    d.updated_at, d.updated_by = datetime.now(timezone.utc), cu.user.id
    audit(db, cu, "donation_updated", f"donation:{d.id}", fields=sorted(changes))
    db.commit()
    items, _ = _load(db, cu.organization_id)
    return {"donation": next(x for x in items if x["id"] == d.id)}


class AckIn(BaseModel):
    status: AckStatus


@router.post("/donations/{donation_id}/acknowledgment")
def set_acknowledgment(donation_id: int, body: AckIn, cu: CurrentUser = Depends(require(Permission.MANAGE_DONATIONS)),
                       db: Session = Depends(get_db)) -> dict:
    """Bookkeeping only: 'completed' records that a person sent the acknowledgment outside SAM SPACE."""
    d = db.get(Donation, donation_id)
    if is_foreign_or_missing(db, cu, d, "d"):
        raise HTTPException(404, "Donation not found.")
    _apply(d, {"ack_status": body.status})
    d.updated_at, d.updated_by = datetime.now(timezone.utc), cu.user.id
    audit(db, cu, "acknowledgment_status_set", f"donation:{d.id}", status=body.status)
    db.commit()
    return {"id": d.id, "ack_status": d.ack_status, "acknowledged": d.acknowledged,
            "note": "Recorded. SAM SPACE did not send anything; this marks work a person did."}


@router.post("/donations/import", status_code=status.HTTP_201_CREATED)
async def import_donations(request: Request, file: UploadFile = File(...), allow_duplicates: bool = Form(default=False),
                           cu: CurrentUser = Depends(require(Permission.MANAGE_DONATIONS)), db: Session = Depends(get_db)) -> dict:
    data = await file.read(docs.MAX_CSV_BYTES + 1)
    name = docs.sanitize_filename(file.filename)
    try:
        if docs.detect_type(data, name) != "csv":
            raise docs.DocumentError("Donation imports must be CSV files.")
    except docs.DocumentError as exc:
        security_event(db, cu, "upload_rejected", f"Donation import “{name}” rejected: {exc}", severity="low",
                       defense="File type and size checks")
        raise HTTPException(422, str(exc)) from exc
    org = cu.organization_id
    digest = docs.sha256(data)
    if db.scalar(select(Donation.id).where(Donation.organization_id == org, Donation.import_document_sha == digest).limit(1)):
        raise HTTPException(409, "This exact file was already imported. Nothing was added twice.")
    campaigns = {c.name.lower(): c.id for c in db.scalars(select(Campaign).where(Campaign.organization_id == org))}
    rows, errors = dsvc.parse_donation_csv(data.decode("utf-8-sig"), campaigns)
    if errors:
        raise HTTPException(422, "Nothing was imported. " + " | ".join(errors[:6]) + (" | …" if len(errors) > 6 else ""))
    dupes = [r for r in rows if _duplicate_of(db, org, r["donor_name"], r["received_on"], r["amount_usd"])]
    if dupes and not allow_duplicates:
        raise HTTPException(409, f"{len(dupes)} row(s) match gifts already recorded (same donor, date, and amount), for example row "
                                 f"{dupes[0]['row']}. Nothing was imported. If they are genuinely separate gifts, import again and confirm.")
    for r in rows:
        donor = _donor(db, org, r["donor_name"], r["donor_email"])
        d = Donation(organization_id=org, donor_name=r["donor_name"], donor_email=r["donor_email"] or donor.email, amount_usd=r["amount_usd"],
                     received_on=r["received_on"], donor_id=donor.id, currency="USD", source="csv_import", import_document_sha=digest, is_demo=False)
        _apply(d, {k: v for k, v in r.items() if k not in ("row", "donor_email", "currency")})
        db.add(d)
    audit(db, cu, "donations_imported", rows=len(rows), confirmed_duplicates=len(dupes))
    db.commit()
    return {"imported": len(rows), "confirmed_duplicates": len(dupes), "filename": name}


@router.get("/donations/export.csv", response_class=PlainTextResponse)
def export_donations(cu: CurrentUser = Depends(require(Permission.VIEW_DONOR_DATA)), db: Session = Depends(get_db)) -> PlainTextResponse:
    items, _ = _load(db, cu.organization_id)
    rows = [{**d, "donation_date": d["received_on"], "donor_id": d["donor_id"]} for d in items]
    audit(db, cu, "donations_exported", rows=len(rows))
    db.commit()
    return PlainTextResponse(dsvc.export_csv(rows), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="donations-export.csv"', "Cache-Control": "no-store"})


# ── Campaigns ─────────────────────────────────────────────────────────────────────


@router.get("/campaigns")
def list_campaigns(cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(Campaign).where(Campaign.organization_id == cu.organization_id).order_by(Campaign.name)).all()
    return {"campaigns": [{"id": c.id, "name": c.name, "kind": c.kind, "goal_usd": c.goal_usd, "is_demo": c.is_demo} for c in rows]}


class CampaignIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    kind: Literal["campaign", "event"] = "campaign"
    goal_usd: float | None = Field(default=None, ge=0, le=docs.MAX_AMOUNT)
    starts_on: date | None = None
    ends_on: date | None = None
    event_plan_id: int | None = None
    historical_event_id: int | None = None


@router.post("/campaigns", status_code=status.HTTP_201_CREATED)
def create_campaign(body: CampaignIn, cu: CurrentUser = Depends(require(Permission.MANAGE_DONATIONS)), db: Session = Depends(get_db)) -> dict:
    org = cu.organization_id
    name = body.name.strip().lstrip("=+-@\t")
    if db.scalar(select(Campaign.id).where(Campaign.organization_id == org, func.lower(Campaign.name) == name.lower())):
        raise HTTPException(409, "A campaign with this name already exists.")
    for model, value in ((EventPlan, body.event_plan_id), (HistoricalEvent, body.historical_event_id)):
        if value is not None:
            row = db.get(model, value)
            if row is None or row.organization_id != org:
                raise HTTPException(404, "Linked event not found.")
    c = Campaign(organization_id=org, name=name, kind=body.kind, goal_usd=body.goal_usd, starts_on=body.starts_on, ends_on=body.ends_on,
                 event_plan_id=body.event_plan_id, historical_event_id=body.historical_event_id)
    db.add(c)
    db.flush()
    audit(db, cu, "campaign_created", f"campaign:{c.id}")
    db.commit()
    return {"campaign": {"id": c.id, "name": c.name, "kind": c.kind, "goal_usd": c.goal_usd}}


# ── Compliance review ─────────────────────────────────────────────────────────────


@router.get("/compliance")
def compliance(cu: CurrentUser = Depends(require(Permission.VIEW_DONOR_DATA)), db: Session = Depends(get_db)) -> dict:
    org = cu.organization_id
    items, _ = _load(db, org)
    locations = [dsvc.state_of(x) for x in
                 [p.city for p in db.scalars(select(EventPlan).where(EventPlan.organization_id == org))] +
                 [e.location for e in db.scalars(select(HistoricalEvent).where(HistoricalEvent.organization_id == org))]]
    return {"items": dsvc.compliance_items(items, _ledger(db, org), [x for x in locations if x]), "references": public_references(),
            "disclaimer": "General information for a volunteer board, not legal or tax advice. SAM SPACE does not file returns, submit "
                          "documents, decide whether gifts are deductible, or contact anyone. Confirm with your accountant or attorney."}
