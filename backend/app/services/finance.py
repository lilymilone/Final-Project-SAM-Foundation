"""Deterministic financial checks. All arithmetic happens here in Python, never in a model."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date

from ..db.models import Donation, EventPlan, FinancialRecord

RESERVE_GUIDELINE_MONTHS = 3.0  # board guideline: keep 3 months of expenses in reserve
EVENT_BUDGET_RESERVE_SHARE = 0.5  # flag an event budget above 50% of the reserve
IRS_ACK_THRESHOLD_USD = 250.0  # single gifts of $250+ need a written acknowledgment


def finance_summary(records: Iterable[FinancialRecord], plans: Iterable[EventPlan] = ()) -> dict:
    by_month: dict[str, dict[str, float]] = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    reserve: tuple[str, float] | None = None
    is_demo = False
    for r in records:
        is_demo = is_demo or r.is_demo
        if r.kind in ("income", "expense"):
            by_month[r.period][r.kind] += r.amount_usd
        elif r.kind == "reserve" and (reserve is None or r.period >= reserve[0]):
            reserve = (r.period, r.amount_usd)

    months = [
        {"period": p, "income": round(v["income"], 2), "expense": round(v["expense"], 2), "net": round(v["income"] - v["expense"], 2)}
        for p, v in sorted(by_month.items())
    ]
    avg_expense = round(sum(m["expense"] for m in months) / len(months), 2) if months else None
    reserve_usd = reserve[1] if reserve else None
    months_covered = round(reserve_usd / avg_expense, 1) if reserve_usd is not None and avg_expense else None

    flags: list[dict] = []
    if months_covered is not None and months_covered < RESERVE_GUIDELINE_MONTHS:
        flags.append({
            "severity": "high",
            "title": "Reserve below guideline",
            "detail": f"The operating reserve covers {months_covered} months of average expenses "
                      f"(guideline: {RESERVE_GUIDELINE_MONTHS:g}).",
        })
    deficits = [m["period"] for m in months if m["net"] < 0]
    if deficits:
        flags.append({
            "severity": "medium",
            "title": "Months with a deficit",
            "detail": f"Expenses exceeded income in {', '.join(deficits)}.",
        })
    for plan in plans:
        if plan.budget_limit_usd and reserve_usd and plan.status not in ("completed", "cancelled"):
            share = plan.budget_limit_usd / reserve_usd
            if share > EVENT_BUDGET_RESERVE_SHARE:
                flags.append({
                    "severity": "medium",
                    "title": f"{plan.name}: large budget",
                    "detail": f"Budget limit ${plan.budget_limit_usd:,.0f} is {share:.0%} of the operating reserve "
                              f"(${reserve_usd:,.0f}). Plan deposits and cash flow carefully.",
                })
    return {
        "is_demo": is_demo,
        "months": months,
        "average_monthly_expense": avg_expense,
        "reserve_usd": reserve_usd,
        "reserve_period": reserve[0] if reserve else None,
        "reserve_months_covered": months_covered,
        "flags": flags,
        "method": "Computed in Python from financial_records. No AI involved.",
    }


def donation_flags(donation: Donation, today: date | None = None) -> list[str]:
    today = today or date.today()
    flags: list[str] = []
    if not donation.donor_email:
        flags.append("Missing donor contact email")
    if not donation.method:
        flags.append("Missing payment method")
    if not donation.acknowledged and donation.amount_usd >= IRS_ACK_THRESHOLD_USD:
        flags.append("Gift of $250+ without a written acknowledgment. Confirm requirements with your accountant.")
    elif not donation.acknowledged:
        days = (today - donation.received_on).days
        if days > 14:
            flags.append(f"Not acknowledged after {days} days")
    return flags
