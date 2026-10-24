"""Financial Intelligence and Donations & Compliance (role-restricted)."""

from __future__ import annotations

import csv
import io
import math
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
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


class LedgerImport(BaseModel):
    csv_text: str = Field(min_length=1, max_length=200_000)
    replace_demo: bool = False


LEDGER_COLUMNS = ("period", "kind", "category", "amount_usd")
LEDGER_KINDS = {"income", "expense", "reserve"}
PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
MAX_ROWS = 2000


@router.post("/finance/import")
def import_ledger(body: LedgerImport, cu: CurrentUser = Depends(require(Permission.VIEW_FINANCIALS)),
                  db: Session = Depends(get_db)) -> dict:
    """Validated CSV upload: period (YYYY-MM), kind (income|expense|reserve), category, amount_usd.
    Every row is checked. Nothing is saved unless the whole file is valid."""
    reader = csv.DictReader(io.StringIO(body.csv_text.lstrip("﻿")))
    headers = {(h or "").strip().lower() for h in (reader.fieldnames or [])}
    if not set(LEDGER_COLUMNS) <= headers:
        raise HTTPException(422, f"The CSV needs these columns: {', '.join(LEDGER_COLUMNS)}.")
    rows, errors = [], []
    for line, raw in enumerate(reader, start=2):
        if len(rows) >= MAX_ROWS:
            errors.append(f"More than {MAX_ROWS} rows; split the file.")
            break
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        if not any(r.values()):
            continue
        category = r["category"].lstrip("=+-@\t")[:80]  # neutralize spreadsheet formulas
        try:
            amount = float(r["amount_usd"].replace(",", "").replace("$", ""))
        except ValueError:
            amount = None
        problems = []
        if not PERIOD.match(r["period"]):
            problems.append("period must look like 2026-09")
        if r["kind"].lower() not in LEDGER_KINDS:
            problems.append("kind must be income, expense, or reserve")
        if not category:
            problems.append("category is empty")
        if amount is None or not math.isfinite(amount) or not 0 <= amount <= 10_000_000:
            problems.append("amount_usd must be a number between 0 and 10,000,000")
        if problems:
            errors.append(f"Line {line}: {'; '.join(problems)}")
            continue
        rows.append(FinancialRecord(organization_id=cu.organization_id, period=r["period"], kind=r["kind"].lower(), category=category,
                                    amount_usd=round(amount, 2), description="Imported from CSV", source="upload", is_demo=False))
    if errors:
        raise HTTPException(422, "Nothing was imported. " + " | ".join(errors[:6]) + (" | …" if len(errors) > 6 else ""))
    if not rows:
        raise HTTPException(422, "The CSV has no data rows.")
    replaced = 0
    if body.replace_demo:
        replaced = db.execute(delete(FinancialRecord).where(FinancialRecord.organization_id == cu.organization_id,
                                                            FinancialRecord.is_demo.is_(True))).rowcount or 0
    db.add_all(rows)
    audit(db, cu, "ledger_imported", rows=len(rows), replaced_demo_rows=replaced)
    db.commit()
    return {"imported": len(rows), "replaced_demo_rows": replaced}


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
