"""What the agents produced: drafts, research findings, lessons, venue candidates.

Drafts can be edited, marked reviewed, or archived. They can never be sent:
no route, tool, or integration in SAM SPACE sends mail.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.permissions import Permission
from ...db.models import EventPlan, OutreachDraft, ResearchFinding, VenueCandidate
from ..deps import CurrentUser, audit, current_user, get_db, require

router = APIRouter(prefix="/api", tags=["outputs"])
DONOR_DRAFTS = ("donor_acknowledgment", "donor_thank_you", "contribution_acknowledgment")


def draft_out(d: OutreachDraft) -> dict:
    return {"id": d.id, "run_id": d.run_id, "agent": d.agent, "draft_type": d.draft_type, "recipient_name": d.recipient_name,
            "recipient_org": d.recipient_org, "subject": d.subject, "body": d.body, "status": d.status,
            "personalization_basis": d.personalization_basis, "is_synthetic_target": d.is_synthetic_target,
            "purpose": d.purpose, "opportunity": d.opportunity, "next_step": d.next_step,
            "foundation_background": d.foundation_background, "sources": d.sources or [], "finding_id": d.finding_id,
            "review_notes": d.review_notes or [], "donation_id": d.donation_id,
            "created_at": d.created_at.isoformat(), "updated_at": d.updated_at.isoformat() if d.updated_at else None}


@router.get("/drafts")
def list_drafts(kind: Literal["outreach", "donor", "all"] = "outreach", archived: bool = False, cu: CurrentUser = Depends(current_user),
                db: Session = Depends(get_db)) -> dict:
    q = select(OutreachDraft).where(OutreachDraft.organization_id == cu.organization_id,
                                    OutreachDraft.status == "archived" if archived else OutreachDraft.status != "archived")
    if kind == "donor" or (kind == "all" and Permission.VIEW_DONOR_DATA in cu.permissions):
        if Permission.VIEW_DONOR_DATA not in cu.permissions:
            raise HTTPException(403, "Donor acknowledgments are limited to the chair and treasurer.")
        if kind == "donor":
            q = q.where(OutreachDraft.draft_type.in_(DONOR_DRAFTS))
    else:
        q = q.where(OutreachDraft.draft_type.not_in(DONOR_DRAFTS))
    rows = db.scalars(q.order_by(OutreachDraft.created_at.desc()).limit(60)).all()
    return {"drafts": [draft_out(d) for d in rows]}


class DraftUpdate(BaseModel):
    """Edits a person makes to a draft. There is deliberately no "sent" status: SAM SPACE cannot send."""

    model_config = {"extra": "forbid"}
    subject: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, max_length=8000)
    purpose: str | None = Field(default=None, max_length=1000)
    opportunity: str | None = Field(default=None, max_length=2000)
    next_step: str | None = Field(default=None, max_length=1000)
    recipient_name: str | None = Field(default=None, max_length=200)
    status: Literal["draft", "reviewed", "archived"] | None = None


@router.put("/drafts/{draft_id}")
def update_draft(draft_id: int, body: DraftUpdate, cu: CurrentUser = Depends(require(Permission.RUN_AGENTS)),
                 db: Session = Depends(get_db)) -> dict:
    d = db.get(OutreachDraft, draft_id)
    if d is None or d.organization_id != cu.organization_id:
        raise HTTPException(404, "Draft not found.")
    if d.draft_type in DONOR_DRAFTS and Permission.VIEW_DONOR_DATA not in cu.permissions:
        raise HTTPException(403, "Donor acknowledgments are limited to the chair and treasurer.")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(d, k, v)
    audit(db, cu, "draft_updated", f"draft:{d.id}", status=d.status)
    db.commit()
    return {"draft": draft_out(d)}


@router.get("/findings")
def list_findings(cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(ResearchFinding).where(ResearchFinding.organization_id == cu.organization_id)
                      .order_by(ResearchFinding.saved.desc(), ResearchFinding.created_at.desc()).limit(60)).all()
    return {"findings": [{
        "id": f.id, "run_id": f.run_id, "title": f.title, "summary": f.summary, "category": f.category, "alignment": f.alignment,
        "source_url": f.source_url, "verification": f.verification_status, "uncertainty": f.uncertainty, "published": f.published,
        "is_synthetic": f.is_synthetic, "saved": f.saved, "created_at": f.created_at.isoformat(),
    } for f in rows]}


class SaveFinding(BaseModel):
    saved: bool


@router.post("/findings/{finding_id}/save")
def save_finding(finding_id: int, body: SaveFinding, cu: CurrentUser = Depends(require(Permission.RUN_AGENTS)),
                 db: Session = Depends(get_db)) -> dict:
    f = db.get(ResearchFinding, finding_id)
    if f is None or f.organization_id != cu.organization_id:
        raise HTTPException(404, "Finding not found.")
    f.saved = body.saved
    f.status = "saved" if body.saved else "new"
    audit(db, cu, "finding_saved" if body.saved else "finding_unsaved", f"finding:{f.id}")
    db.commit()
    return {"id": f.id, "saved": f.saved}


@router.get("/events/{event_id}/venues")
def venue_candidates(event_id: int, cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    plan = db.get(EventPlan, event_id)
    if plan is None or plan.organization_id != cu.organization_id:
        raise HTTPException(404, "Event plan not found.")
    rows = db.scalars(select(VenueCandidate).where(VenueCandidate.event_plan_id == event_id).order_by(VenueCandidate.estimated_cost_usd)).all()
    return {"venues": [{
        "id": v.id, "name": v.name, "neighborhood": v.address, "capacity": v.capacity, "estimated_total_usd": v.estimated_cost_usd,
        "fnb_per_guest_usd": v.fnb_per_guest_usd, "formats": v.formats, "verification": v.verification, "is_synthetic": v.is_synthetic,
        "source_url": v.source_url, "notes": v.notes, "run_id": v.run_id,
    } for v in rows]}
