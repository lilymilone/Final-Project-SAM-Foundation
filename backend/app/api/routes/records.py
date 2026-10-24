"""Financial Intelligence and Donations & Compliance (role-restricted)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.permissions import Permission
from ...db.models import Donation, EventPlan, FinancialRecord
from ...services.finance import donation_flags, finance_summary
from ..deps import CurrentUser, audit, get_db, require

router = APIRouter(prefix="/api", tags=["records"])


@router.get("/finance/summary")
def finance(cu: CurrentUser = Depends(require(Permission.VIEW_FINANCIALS)), db: Session = Depends(get_db)) -> dict:
    org = cu.organization_id
    records = db.scalars(select(FinancialRecord).where(FinancialRecord.organization_id == org)).all()
    plans = db.scalars(select(EventPlan).where(EventPlan.organization_id == org)).all()
    audit(db, cu, "financials_viewed")
    db.commit()
    return finance_summary(records, plans)


@router.get("/donations")
def donations(cu: CurrentUser = Depends(require(Permission.VIEW_DONOR_DATA)), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(Donation).where(Donation.organization_id == cu.organization_id).order_by(Donation.received_on.desc())
    ).all()
    items = [
        {
            "id": d.id, "donor_name": d.donor_name, "has_email": bool(d.donor_email), "amount_usd": d.amount_usd,
            "received_on": d.received_on.isoformat(), "method": d.method, "designation": d.designation,
            "acknowledged": d.acknowledged, "is_demo": d.is_demo, "flags": donation_flags(d),
        }
        for d in rows
    ]
    audit(db, cu, "donor_data_viewed")
    db.commit()
    return {
        "donations": items,
        "totals": {
            "count": len(items),
            "amount_usd": round(sum(d["amount_usd"] for d in items), 2),
            "needs_attention": sum(1 for d in items if d["flags"]),
            "unacknowledged": sum(1 for d in items if not d["acknowledged"]),
        },
        "is_demo": any(d["is_demo"] for d in items),
        "note": "Flags are for review by a person or a professional. SAM SPACE never contacts donors.",
    }
