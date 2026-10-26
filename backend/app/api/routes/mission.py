"""Foundation mission, Mission Discovery opportunities, partnership packets, and impact.

Opportunity actions are board bookkeeping inside SAM SPACE: save, dismiss,
categorize, and private notes. Private notes never reach a model or a
website. "Request more research" and "Generate outreach draft" start an
ordinary agent run (POST /api/runs with follow_up_finding_id / finding_ids).
Nothing here contacts any organization.
"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.permissions import Permission
from ...db.models import OutreachDraft, ResearchFinding
from ...mission import public_config
from ...services.impact import impact_metrics
from ...services.opportunities import opportunity_out
from ...services.partnership_packet import build_partnership_packet, partnership_markdown
from ..deps import CurrentUser, audit, current_user, get_db, require, is_foreign_or_missing

router = APIRouter(prefix="/api", tags=["mission"])
BOARD_CATEGORIES = ("Partnership prospect", "Research to support", "Event to join", "Sponsor prospect", "Watch list")


@router.get("/mission")
def mission_config(_: CurrentUser = Depends(current_user)) -> dict:
    return {**public_config(), "board_categories": list(BOARD_CATEGORIES)}


def _stats(rows: list[ResearchFinding]) -> dict:
    cards = [opportunity_out(r, include_notes=False) for r in rows]
    checked = [c["last_checked"] for c in cards if c["last_checked"]]
    return {
        "total": len(cards),
        "by_status": dict(Counter(c["status"] for c in cards)),
        "by_fit": dict(Counter(c["fit"] or "Not assessed" for c in cards)),
        "by_verification": dict(Counter(c["verification"] for c in cards)),
        "with_warnings": sum(1 for c in cards if c["warnings"]),
        "injection_flagged": sum(1 for c in cards if c["injection_flagged"]),
        "synthetic": sum(1 for c in cards if c["is_synthetic"]),
        "last_checked": max(checked) if checked else None,
    }


@router.get("/opportunities")
def list_opportunities(status: Literal["new", "saved", "dismissed", "all", "active"] = "active", cu: CurrentUser = Depends(current_user),
                       db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(ResearchFinding).where(ResearchFinding.organization_id == cu.organization_id)
                      .order_by(ResearchFinding.last_checked.desc().nulls_last(), ResearchFinding.created_at.desc()).limit(200)).all()
    cards = [opportunity_out(r) for r in rows]
    # Contact details come only from an outreach draft for that finding, where they were looked up on the organization's
    # own website (never guessed). Newest draft wins.
    contacts: dict[int, dict] = {}
    for d in db.scalars(select(OutreachDraft).where(OutreachDraft.organization_id == cu.organization_id, OutreachDraft.finding_id.is_not(None))
                        .order_by(OutreachDraft.created_at)):
        if d.contact:
            contacts[d.finding_id] = {k: d.contact.get(k) for k in ("email", "contact_page_url", "source_url", "status", "display", "verified_at")}
            contacts[d.finding_id]["draft_id"] = d.id
    for c in cards:
        c["contact"] = contacts.get(c["id"])
    if status == "active":
        cards = [c for c in cards if c["status"] != "dismissed"]
    elif status != "all":
        cards = [c for c in cards if c["status"] == status]
    return {"opportunities": cards, "stats": _stats(rows), "board_categories": list(BOARD_CATEGORIES)}


def _owned(db: Session, cu: CurrentUser, finding_id: int) -> ResearchFinding:
    f = db.get(ResearchFinding, finding_id)
    if is_foreign_or_missing(db, cu, f, "f"):
        raise HTTPException(404, "Opportunity not found.")
    return f


class StatusIn(BaseModel):
    status: Literal["new", "saved", "dismissed"]


@router.post("/opportunities/{finding_id}/status")
def set_status(finding_id: int, body: StatusIn, cu: CurrentUser = Depends(require(Permission.RUN_AGENTS)),
               db: Session = Depends(get_db)) -> dict:
    f = _owned(db, cu, finding_id)
    f.status = body.status
    f.saved = body.status == "saved"
    audit(db, cu, f"opportunity_{body.status}", f"finding:{f.id}")
    db.commit()
    return {"opportunity": opportunity_out(f)}


class OpportunityEdit(BaseModel):
    board_category: str | None = Field(default=None, max_length=60)
    notes: str | None = Field(default=None, max_length=4000)


@router.put("/opportunities/{finding_id}")
def edit_opportunity(finding_id: int, body: OpportunityEdit, cu: CurrentUser = Depends(require(Permission.RUN_AGENTS)),
                     db: Session = Depends(get_db)) -> dict:
    f = _owned(db, cu, finding_id)
    changed = body.model_dump(exclude_unset=True)
    for k, v in changed.items():
        setattr(f, k, (v or "").strip() or None)
    audit(db, cu, "opportunity_updated", f"finding:{f.id}", fields=sorted(changed))  # field names only, never note text
    db.commit()
    return {"opportunity": opportunity_out(f)}


@router.get("/impact")
def impact(request: Request, cu: CurrentUser = Depends(current_user)) -> dict:
    return impact_metrics(request.app.state.db, cu.organization_id)


@router.get("/runs/{run_id}/partnership-packet")
def partnership_packet(run_id: int, request: Request, cu: CurrentUser = Depends(current_user)) -> dict:
    packet = build_partnership_packet(request.app.state.db, run_id, cu.organization_id)
    if packet is None:
        raise HTTPException(404, "No partnership packet for this workflow.")
    return {"packet": packet}


@router.get("/runs/{run_id}/partnership-packet.md", response_class=PlainTextResponse)
def partnership_packet_md(run_id: int, request: Request, cu: CurrentUser = Depends(current_user)) -> PlainTextResponse:
    packet = build_partnership_packet(request.app.state.db, run_id, cu.organization_id)
    if packet is None:
        raise HTTPException(404, "No partnership packet for this workflow.")
    return PlainTextResponse(partnership_markdown(packet), media_type="text/markdown",
                             headers={"Content-Disposition": f'attachment; filename="partnership-packet-{run_id}.md"'})
