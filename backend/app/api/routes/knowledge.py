"""Foundation Knowledge Base: read, add, correct, verify, and remove what SAM SPACE knows about the foundation.

Any board member can read the base and add or correct facts (as board-reported). Only the chair or treasurer can mark a
fact verified, remove one, or import a whole profile. Board contact details are shown to the chair only and are never
sent to a model. Every change is audited.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.permissions import Permission
from ...db.models import HistoricalEvent, KnowledgeEntry
from ...services import knowledge as kb
from ..deps import CurrentUser, audit, current_user, get_db, is_foreign_or_missing, require

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

Section = Literal["mission_history", "signature_events", "past_fundraisers", "vendors_venues", "relationships", "community_audience",
                  "board", "fundraising_priorities", "financial_guidelines", "communication"]
Verification = Literal["verified", "board_reported", "estimate", "needs_confirmation"]


class EntryIn(BaseModel):
    section: Section
    title: str = Field(min_length=2, max_length=200)
    body: str = Field(default="", max_length=4000)
    details: dict[str, Any] = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list, max_length=12)
    source: str = Field(default="", max_length=300)
    source_url: str | None = Field(default=None, max_length=500)
    verification: Verification = "board_reported"
    share_externally: bool = False
    historical_event_id: int | None = None


class VerifyIn(BaseModel):
    verification: Verification


class RemoveIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ImportIn(BaseModel):
    entries: list[dict[str, Any]] = Field(max_length=200)


def _name(cu: CurrentUser) -> str:
    return f"{cu.user.first_name} {cu.user.last_name}".strip()


def _out(e: KnowledgeEntry, cu: CurrentUser, events: dict[int, str]) -> dict:
    details = dict(e.details or {})
    if Permission.MANAGE_USERS not in cu.permissions:
        for hidden in kb.HIDDEN_FIELDS.get(e.section, ()):
            if details.get(hidden):
                details[hidden] = "(visible to the chair)"
    return {"id": e.id, "code": f"KB-{e.id}", "section": e.section, "section_label": kb.SECTION_LABELS.get(e.section, e.section),
            "title": e.title, "body": e.body, "details": details, "aliases": e.aliases or [],
            "historical_event_id": e.historical_event_id, "historical_event_name": events.get(e.historical_event_id or 0),
            "source": e.source, "source_url": e.source_url, "contributor": e.contributor, "verification": e.verification,
            "verification_label": kb.VERIFICATION.get(e.verification, e.verification), "verified_by": e.verified_by,
            "verified_at": e.verified_at.isoformat() if e.verified_at else None, "share_externally": e.share_externally,
            "status": e.status, "removed_reason": e.removed_reason, "is_demo": e.is_demo,
            "recorded_at": e.recorded_at.isoformat() if e.recorded_at else None,
            "updated_at": e.updated_at.isoformat() if e.updated_at else None, "updated_by": e.updated_by}


def _event_names(db: Session, org_id: int) -> dict[int, str]:
    return dict(db.execute(select(HistoricalEvent.id, HistoricalEvent.name).where(HistoricalEvent.organization_id == org_id)).all())


def _get(db: Session, cu: CurrentUser, entry_id: int) -> KnowledgeEntry:
    row = db.get(KnowledgeEntry, entry_id)
    if is_foreign_or_missing(db, cu, row, "knowledge entry"):
        raise HTTPException(404, "Fact not found.")
    return row


def _check_event(db: Session, cu: CurrentUser, event_id: int | None) -> None:
    if event_id is not None and is_foreign_or_missing(db, cu, db.get(HistoricalEvent, event_id), "past event"):
        raise HTTPException(404, "Past event not found.")


@router.get("")
def list_knowledge(include_removed: bool = False, cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    q = select(KnowledgeEntry).where(KnowledgeEntry.organization_id == cu.organization_id)
    if not include_removed:
        q = q.where(KnowledgeEntry.status == "active")
    rows = db.scalars(q.order_by(KnowledgeEntry.section, KnowledgeEntry.id)).all()
    events = _event_names(db, cu.organization_id)
    in_use = {e.id for e in kb.active_entries(db, cu.organization_id)}
    entries = [_out(e, cu, events) | {"used_by_agents": e.id in in_use} for e in rows]
    counts: dict[str, int] = {}
    for e in rows:
        if e.status == "active":
            counts[e.verification] = counts.get(e.verification, 0) + 1
    return {
        "sections": [{"key": s["key"], "label": s["label"], "hint": s["hint"],
                      "fields": [{"key": k, "label": label} for k, label in s["fields"]]} for s in kb.SECTIONS],
        "verification_labels": {k: v for k, v in kb.VERIFICATION.items()},
        "datasets": kb.DATASETS,
        "entries": entries,
        "counts": counts,
        "gaps": kb.gaps(db, cu.organization_id),
        "financial_sources": kb.financial_sources(db, cu.organization_id) if Permission.VIEW_FINANCIALS in cu.permissions else None,
        "legacy_events": [{"id": i, "name": n} for i, n in sorted(events.items(), key=lambda p: p[1])],
        "agents": sorted(kb.AGENT_SECTIONS),
        "can_edit": Permission.MANAGE_EVENTS in cu.permissions,
        "can_verify": Permission.MANAGE_KNOWLEDGE in cu.permissions,
    }


@router.get("/template")
def blank_template(_cu: CurrentUser = Depends(current_user)) -> dict:
    return kb.template()


@router.get("/preview")
def preview_retrieval(agent: str = Query(..., max_length=40), query: str = Query(..., min_length=3, max_length=500),
                      cu: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Exactly what the shared retrieval service would hand this agent for this task (no model call, no cost)."""
    if agent not in kb.AGENT_SECTIONS:
        raise HTTPException(422, "Unknown agent.")
    return kb.retrieve(db, cu.organization_id, agent=agent, query=query)


@router.post("", status_code=201)
def add_entry(body: EntryIn, cu: CurrentUser = Depends(require(Permission.MANAGE_EVENTS)), db: Session = Depends(get_db)) -> dict:
    _check_event(db, cu, body.historical_event_id)
    verification = body.verification
    if verification == "verified" and Permission.MANAGE_KNOWLEDGE not in cu.permissions:
        verification = "board_reported"  # only the chair or treasurer can verify
    now = datetime.now(timezone.utc)
    row = KnowledgeEntry(organization_id=cu.organization_id, section=body.section, title=body.title.strip(), body=body.body.strip(),
                         details={k: v for k, v in body.details.items() if v not in (None, "", [])} or None,
                         aliases=[a.strip() for a in body.aliases if a.strip()] or None, source=body.source.strip(),
                         source_url=body.source_url, contributor=_name(cu), verification=verification,
                         share_externally=body.share_externally, historical_event_id=body.historical_event_id,
                         recorded_at=now, updated_at=now, updated_by=_name(cu))
    if verification == "verified":
        row.verified_by, row.verified_at = _name(cu), now
    db.add(row)
    db.flush()
    audit(db, cu, "knowledge_added", f"knowledge:{row.id}", section=body.section, verification=verification)
    db.commit()
    return _out(row, cu, _event_names(db, cu.organization_id))


@router.put("/{entry_id}")
def correct_entry(entry_id: int, body: EntryIn, cu: CurrentUser = Depends(require(Permission.MANAGE_EVENTS)),
                  db: Session = Depends(get_db)) -> dict:
    row = _get(db, cu, entry_id)
    _check_event(db, cu, body.historical_event_id)
    can_verify = Permission.MANAGE_KNOWLEDGE in cu.permissions
    details = {k: v for k, v in body.details.items() if v not in (None, "", [])}
    for hidden in kb.HIDDEN_FIELDS.get(row.section, ()):  # a masked contact stays as it was unless the chair edits it
        if details.get(hidden) == "(visible to the chair)" or Permission.MANAGE_USERS not in cu.permissions:
            if (row.details or {}).get(hidden):
                details[hidden] = row.details[hidden]
            else:
                details.pop(hidden, None)
    verification = body.verification if (body.verification != "verified" or can_verify) else "board_reported"
    row.section, row.title, row.body = body.section, body.title.strip(), body.body.strip()
    row.details, row.aliases = details or None, [a.strip() for a in body.aliases if a.strip()] or None
    row.source, row.source_url, row.share_externally = body.source.strip(), body.source_url, body.share_externally
    row.historical_event_id = body.historical_event_id
    if verification != row.verification or verification != "verified":
        row.verified_by, row.verified_at = (_name(cu), datetime.now(timezone.utc)) if verification == "verified" else (None, None)
    row.verification = verification
    row.updated_at, row.updated_by = datetime.now(timezone.utc), _name(cu)
    audit(db, cu, "knowledge_corrected", f"knowledge:{row.id}", verification=verification)
    db.commit()
    return _out(row, cu, _event_names(db, cu.organization_id))


@router.post("/{entry_id}/verify")
def set_verification(entry_id: int, body: VerifyIn, cu: CurrentUser = Depends(require(Permission.MANAGE_KNOWLEDGE)),
                     db: Session = Depends(get_db)) -> dict:
    row = _get(db, cu, entry_id)
    if row.is_demo:
        raise HTTPException(422, "Samples stay labeled as samples. Add the real fact instead.")
    row.verification = body.verification
    row.verified_by, row.verified_at = (_name(cu), datetime.now(timezone.utc)) if body.verification == "verified" else (None, None)
    row.updated_at, row.updated_by = datetime.now(timezone.utc), _name(cu)
    audit(db, cu, "knowledge_verification", f"knowledge:{row.id}", verification=body.verification)
    db.commit()
    return _out(row, cu, _event_names(db, cu.organization_id))


@router.post("/{entry_id}/remove")
def remove_entry(entry_id: int, body: RemoveIn, cu: CurrentUser = Depends(require(Permission.MANAGE_KNOWLEDGE)),
                 db: Session = Depends(get_db)) -> dict:
    """Retire an inaccurate fact. It stops reaching the agents at once and stays visible (with the reason) for the record."""
    row = _get(db, cu, entry_id)
    row.status, row.removed_reason = "removed", body.reason.strip()
    row.updated_at, row.updated_by = datetime.now(timezone.utc), _name(cu)
    audit(db, cu, "knowledge_removed", f"knowledge:{row.id}", reason=body.reason[:200])
    db.commit()
    return _out(row, cu, _event_names(db, cu.organization_id))


@router.post("/{entry_id}/restore")
def restore_entry(entry_id: int, cu: CurrentUser = Depends(require(Permission.MANAGE_KNOWLEDGE)), db: Session = Depends(get_db)) -> dict:
    row = _get(db, cu, entry_id)
    row.status, row.removed_reason = "active", None
    row.updated_at, row.updated_by = datetime.now(timezone.utc), _name(cu)
    audit(db, cu, "knowledge_restored", f"knowledge:{row.id}")
    db.commit()
    return _out(row, cu, _event_names(db, cu.organization_id))


@router.post("/from-legacy/{event_id}", status_code=201)
def add_from_legacy(event_id: int, cu: CurrentUser = Depends(require(Permission.MANAGE_EVENTS)), db: Session = Depends(get_db)) -> dict:
    """Bring an approved Our Legacy record into the base as a past fundraiser, linked rather than copied twice."""
    ev = db.get(HistoricalEvent, event_id)
    if is_foreign_or_missing(db, cu, ev, "past event"):
        raise HTTPException(404, "Past event not found.")
    existing = db.scalar(select(KnowledgeEntry).where(KnowledgeEntry.organization_id == cu.organization_id,
                                                      KnowledgeEntry.section == "past_fundraisers",
                                                      KnowledgeEntry.historical_event_id == ev.id, KnowledgeEntry.status == "active"))
    if existing is not None:
        raise HTTPException(409, f"{ev.name} is already in the knowledge base as KB-{existing.id}.")
    money = [f"{label} ${v:,.0f}" for label, v in (("raised", ev.funds_raised_usd), ("cost", ev.total_cost_usd),
                                                    ("sponsorship", ev.sponsorship_usd)) if v is not None]
    when = ev.event_date.isoformat() if ev.event_date else (str(ev.event_year) if ev.event_year else None)
    details = {"date": when, "location": ", ".join(x for x in (ev.venue, ev.location) if x) or None,
               "highlights": ev.summary or ev.positive_outcomes, "figures": "; ".join(money) or None}
    now = datetime.now(timezone.utc)
    verification = "demo" if ev.is_demo else ("verified" if ev.verification_status == "verified" else "board_reported")
    row = KnowledgeEntry(organization_id=cu.organization_id, section="past_fundraisers", title=ev.name, body="",
                         details={k: v for k, v in details.items() if v} or None, source=f"Our Legacy record #{ev.id}",
                         contributor=_name(cu), verification=verification, is_demo=ev.is_demo, historical_event_id=ev.id,
                         recorded_at=now, updated_at=now, updated_by=_name(cu))
    db.add(row)
    db.flush()
    audit(db, cu, "knowledge_added", f"knowledge:{row.id}", section="past_fundraisers", from_event=ev.id)
    db.commit()
    return _out(row, cu, _event_names(db, cu.organization_id))


@router.post("/import")
def import_profile(body: ImportIn, cu: CurrentUser = Depends(require(Permission.MANAGE_KNOWLEDGE)), db: Session = Depends(get_db)) -> dict:
    counts = kb.import_entries(db, cu.organization_id, body.entries, contributor=_name(cu), can_verify=True)
    audit(db, cu, "knowledge_imported", "knowledge", **counts)
    db.commit()
    return counts
