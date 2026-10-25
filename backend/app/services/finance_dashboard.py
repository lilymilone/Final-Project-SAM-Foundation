"""The Financial Intelligence dashboard, computed in code from stored records.

Every metric carries a plain-English explanation, the basis it was computed
on, and a status: recorded, calculated, partial, or not documented. Three rules
hold everywhere:
  * revenue is never presented as cash; only a recorded cash or reserve balance is
  * restricted money is never counted as spendable, and undocumented restrictions are not assumed unrestricted
  * figures waiting for board review never count in any total
Monthly ledger rows and multi-month statements are kept apart, so an annual
statement is never added on top of the months it already covers.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from . import fin_calc as fc
from .calculators import financial_position
from .finance import EVENT_BUDGET_RESERVE_SHARE, RESERVE_GUIDELINE_MONTHS

STALE_DAYS = 120


def _usd(x: float | None) -> str:
    if x is None:
        return "Not recorded"
    return f"−${abs(x):,.0f}" if x < 0 else f"${x:,.0f}"


def _months_between(start: str, end: str) -> int:
    (y1, m1), (y2, m2) = map(int, start.split("-")), map(int, end.split("-"))
    return (y2 - y1) * 12 + (m2 - m1) + 1


def _covered(period: str, months: int) -> list[str]:
    y, m = map(int, period.split("-"))
    out = []
    for _ in range(months):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def _month_label(p: str) -> str:
    return date(int(p[:4]), int(p[5:7]), 1).strftime("%b %Y")


def metric(key: str, label: str, value, display: str, status: str, explanation: str, basis: str) -> dict:
    return {"key": key, "label": label, "value": value, "display": display, "status": status, "explanation": explanation, "basis": basis}


def build_dashboard(records: list[dict], plans: list[dict], past_events: list[dict], donations: list[dict] | None,
                    pending_review: int = 0, today: date | None = None) -> dict:
    today = today or date.today()
    monthly = [r for r in records if (r.get("period_months") or 1) == 1]
    multi = [r for r in records if (r.get("period_months") or 1) > 1]
    ledger = [r for r in monthly if r["kind"] in ("income", "expense")]
    periods = sorted({r["period"] for r in ledger})
    basis = (f"Monthly ledger, {_month_label(periods[0])} to {_month_label(periods[-1])} ({len(periods)} month"
             f"{'s' if len(periods) != 1 else ''})") if periods else "No monthly ledger recorded"
    is_demo = any(r.get("is_demo") for r in records)

    result = fc.operating_result(ledger)
    position = financial_position([r for r in records if (r.get("period_months") or 1) == 1 or r["kind"] in ("reserve", "cash")])
    restr = fc.restriction_summary(ledger)
    cash = position.get("cash")
    ratios = fc.expense_ratios(ledger)
    program_usd = ratios["by_purpose"].get("program")
    event_ledger_usd = ratios["by_purpose"].get("event")
    reserve_cover = fc.reserve_months(position.get("reserve_usd"), position.get("average_monthly_expense_usd"))
    past_cost = sum(e["total_cost_usd"] for e in past_events if e.get("total_cost_usd") is not None)
    past_directed = [e for e in past_events if e.get("funds_directed_usd") is not None]

    metrics = [
        metric("revenue", "Total recorded revenue", result["revenue_usd"], _usd(result["revenue_usd"]) if ledger else "Not recorded",
               "recorded" if ledger else "not_documented",
               "Money the books show as received in these months. This is not cash in the bank: some has already been "
               "spent, and some may be restricted to a purpose.", basis),
        metric("expenses", "Total recorded expenses", result["expenses_usd"], _usd(result["expenses_usd"]) if ledger else "Not recorded",
               "recorded" if ledger else "not_documented", "Money the books show as spent in the same months.", basis),
        metric("net", f"Net operating result ({result['result']})", result["net_usd"], _usd(result["net_usd"]) if ledger else "Not recorded",
               "calculated" if ledger else "not_documented",
               "Revenue minus expenses for the same months. A surplus means more came in than went out; it is not a "
               "savings account and does not mean that money is still available.", f"Calculated in code from the {basis.lower()}."),
        metric("cash", f"Cash on hand{' (as of ' + _month_label(cash['as_of']) + ')' if cash else ''}",
               cash["cash_usd"] if cash else None, _usd(cash["cash_usd"]) if cash else "Not supplied",
               "recorded" if cash else "not_documented",
               "The latest bank balance the board recorded. It is the only figure here that describes money actually "
               "on hand." if cash else "No cash balance has been recorded. Revenue totals cannot stand in for it.",
               "Recorded cash balance." if cash else "Add a cash balance (kind “cash”) from a bank statement or statement of financial position."),
        metric("restricted", "Restricted vs. unrestricted funds", restr["restricted_usd"],
               (f"{_usd(restr['restricted_usd'])} restricted · {_usd(restr['unrestricted_usd'])} unrestricted"
                + (f" · {_usd(restr['not_documented_usd'])} not documented" if restr["not_documented_usd"] else "")) if ledger else "Not recorded",
               "recorded" if ledger and not restr["not_documented_usd"] else "partial" if ledger else "not_documented",
               "Restricted money was given for a specific purpose (for example, a grant for research programs). It "
               "cannot pay for events or general costs. Income with no documented restriction is listed separately, "
               "never assumed to be free to spend.", f"Income in the {basis.lower()}, by the restriction recorded on each row."),
        metric("program_funds", "Funds allocated to charitable programs", program_usd,
               _usd(program_usd) + (f" ({ratios['ratios']['program']:.0%} of expenses)" if program_usd and ratios["ratios"] else "")
               if program_usd is not None else "Not separately recorded",
               "recorded" if program_usd is not None else "not_documented",
               "Spending recorded for the foundation's programs: mental-health awareness, eating-disorder support and "
               "research, and community programs.", f"Expenses tagged or named as program spending in the {basis.lower()}."),
        metric("event_spending", "Event-related expenditures", event_ledger_usd,
               _usd(event_ledger_usd) if event_ledger_usd is not None else
               (f"Not in the ledger · {_usd(past_cost)} across {len(past_events)} past events" if past_events else "Not recorded"),
               "recorded" if event_ledger_usd is not None else "partial" if past_events else "not_documented",
               "What events cost. The ledger shows event spending only when it is categorized; past-event costs come "
               "from Our Legacy records.", "Ledger expenses tagged as event spending; Our Legacy event records."),
        metric("capacity", "Preliminary event budget capacity", position.get("available_planning_budget_usd"),
               _usd(position["available_planning_budget_usd"]) if position.get("available_planning_budget_usd") is not None else "Not supported",
               "calculated" if position.get("available_planning_budget_usd") is not None else "not_documented",
               f"Unrestricted money above a {RESERVE_GUIDELINE_MONTHS:g}-month safety floor of expenses. It is a starting "
               "point for a board conversation about deposits and upfront costs, not approval to spend.",
               position.get("available_planning_budget_basis") or ""),
        metric("reserve_months", "Months of expenses the reserve covers", reserve_cover,
               f"{reserve_cover} months" if reserve_cover is not None else "Not supported",
               "calculated" if reserve_cover is not None else "not_documented",
               f"How long the operating reserve would cover average monthly expenses. The board guideline is "
               f"{RESERVE_GUIDELINE_MONTHS:g} months.", "Reserve balance ÷ average monthly expense, calculated in code."),
    ]

    # Trends (ledger only, so annual statements never inflate a month).
    trend: dict[str, dict[str, float]] = defaultdict(lambda: {"donations": 0.0, "events": 0.0, "grants": 0.0, "other": 0.0})
    for r in ledger:
        if r["kind"] == "income":
            trend[r["period"]][fc.income_source(r)] += r["amount_usd"]
    donation_trend = [{"period": p, **{k: fc.r2(v) for k, v in trend[p].items()}} for p in periods]
    gifts_by_month: list[dict] | None = None
    if donations is not None:
        g: dict[str, list[float]] = defaultdict(list)
        for d in donations:
            g[d["received_on"][:7]].append(d["amount_usd"])
        gifts_by_month = [{"period": p, "gifts": len(v), "amount_usd": fc.r2(sum(v))} for p, v in sorted(g.items())]

    # Budget vs actual over the months each budget covers.
    variances = []
    for kind, actual_kind in (("budget_income", "income"), ("budget_expense", "expense")):
        groups: dict[tuple, list[dict]] = defaultdict(list)
        for r in records:
            if r["kind"] == kind:
                groups[(r["period"], r.get("period_months") or 1, r.get("period_label"))].append(r)
        for (period, months, label), rows in groups.items():
            window = set(_covered(period, months))
            actual = defaultdict(float)
            for r in ledger:
                if r["kind"] == actual_kind and r["period"] in window:
                    actual[r["category"]] += r["amount_usd"]
            budget = defaultdict(float)
            for r in rows:
                budget[r["category"]] += r["amount_usd"]
            covered = sorted(window & set(periods))
            variances.append({"label": label or f"Budget ending {period}", "kind": actual_kind, "months": months,
                              "months_with_actuals": len(covered),
                              "rows": fc.budget_variance(dict(budget), dict(actual), kind="expense" if actual_kind == "expense" else "revenue")})

    # Three-month outlook scenarios (estimates from recorded averages, not forecasts of real gifts).
    scenarios = None
    if periods:
        n = len(periods)
        avg_rev, avg_exp = result["revenue_usd"] / n, result["expenses_usd"] / n
        scenarios = {
            "label": "Next 3 months if recent averages continue (estimate)",
            "rows": fc.compare_scenarios({
                "Recent averages": {"revenue_usd": avg_rev * 3, "cost_usd": avg_exp * 3},
                "Revenue 20% lower": {"revenue_usd": avg_rev * 3 * 0.8, "cost_usd": avg_exp * 3},
                "Expenses 10% higher": {"revenue_usd": avg_rev * 3, "cost_usd": avg_exp * 3 * 1.1},
                "Both": {"revenue_usd": avg_rev * 3 * 0.8, "cost_usd": avg_exp * 3 * 1.1},
            }),
            "revenue_sensitivity": fc.revenue_sensitivity(avg_rev * 3, avg_exp * 3),
            "expense_sensitivity": fc.expense_sensitivity(avg_rev * 3, avg_exp * 3),
            "basis": f"Average monthly revenue {_usd(avg_rev)} and expenses {_usd(avg_exp)} over {n} recorded months, times 3.",
        }

    statements = defaultdict(lambda: {"revenue_usd": 0.0, "expenses_usd": 0.0})
    for r in multi:
        if r["kind"] in ("income", "expense"):
            key = r.get("period_label") or f"{r['period_months']} months ending {r['period']}"
            statements[key]["revenue_usd" if r["kind"] == "income" else "expenses_usd"] += r["amount_usd"]
    statement_rows = [{"period_label": k, "revenue_usd": fc.r2(v["revenue_usd"]), "expenses_usd": fc.r2(v["expenses_usd"]),
                       "net_usd": fc.r2(v["revenue_usd"] - v["expenses_usd"])} for k, v in statements.items()]

    # Warnings and missing information, each in plain words.
    warnings, missing = [], []
    if reserve_cover is not None and reserve_cover < RESERVE_GUIDELINE_MONTHS:
        warnings.append({"severity": "high", "title": "Reserve below guideline",
                         "detail": f"The reserve covers {reserve_cover} months of average expenses (guideline {RESERVE_GUIDELINE_MONTHS:g})."})
    deficits = [m for m in fc.monthly_results(ledger) if m["net"] < 0]
    if deficits:
        warnings.append({"severity": "medium", "title": "Months with a deficit",
                         "detail": "Expenses exceeded revenue in " + ", ".join(_month_label(m["period"]) for m in deficits) + "."})
    if restr["restricted_usd"]:
        warnings.append({"severity": "low", "title": "Restricted funds are excluded from spending capacity",
                         "detail": f"{_usd(restr['restricted_usd'])} was given for a specific purpose and is not counted as available for events."})
    if ledger and restr["not_documented_usd"]:
        warnings.append({"severity": "medium", "title": "Restrictions not documented",
                         "detail": f"{_usd(restr['not_documented_usd'])} of income has no restriction recorded. Until it is "
                                   "documented, it is not treated as freely spendable in this dashboard's restricted figures."})
    for p in plans:
        reserve = position.get("reserve_usd")
        if p.get("budget_limit_usd") and reserve and p.get("status") not in ("completed", "cancelled"):
            share = p["budget_limit_usd"] / reserve
            if share > EVENT_BUDGET_RESERVE_SHARE:
                warnings.append({"severity": "medium", "title": f"{p['name']}: large budget",
                                 "detail": f"The ${p['budget_limit_usd']:,.0f} budget limit is {share:.0%} of the operating reserve."})
    overlap = sorted({r.get("period_label") or r["period"] for r in multi if r["kind"] in ("income", "expense")
                      and set(_covered(r["period"], r["period_months"])) & set(periods)})
    if overlap:
        warnings.append({"severity": "medium", "title": "Statements overlap the monthly ledger",
                         "detail": f"{', '.join(overlap)} covers months that are also in the monthly ledger. They are shown "
                                   "separately and never added together."})
    keys = defaultdict(int)
    for r in records:
        keys[(r["period"], r["kind"], r["category"].lower(), round(r["amount_usd"], 2))] += 1
    dupes = sum(1 for n in keys.values() if n > 1)
    if dupes:
        warnings.append({"severity": "medium", "title": "Possible duplicate entries",
                         "detail": f"{dupes} figure(s) appear more than once with the same month, category, and amount."})
    if pending_review:
        warnings.append({"severity": "low", "title": "Figures waiting for review",
                         "detail": f"{pending_review} figure(s) read from uploaded documents are not counted until a board member approves them."})
    if periods:
        last = date(int(periods[-1][:4]), int(periods[-1][5:7]), 28)
        if (today - last).days > STALE_DAYS:
            warnings.append({"severity": "low", "title": "Records may be out of date",
                             "detail": f"The latest month recorded is {_month_label(periods[-1])}."})
    if not ledger:
        missing.append("No income or expense records. Upload a CSV ledger or statement, or enter figures manually.")
    if cash is None:
        missing.append("No cash balance. Without one, the dashboard can't say how much money is actually on hand.")
    if position.get("reserve_usd") is None:
        missing.append("No operating reserve balance.")
    if ledger and restr["not_documented_usd"]:
        missing.append("Restriction status for some income.")
    if program_usd is None and ledger:
        missing.append("Program spending is not tagged, so funds directed to programs can't be shown.")
    if event_ledger_usd is None and ledger:
        missing.append("Event spending is not tagged in the ledger.")
    if not any(r["kind"].startswith("budget_") for r in records):
        missing.append("No budget recorded, so budget-vs-actual variance can't be explained.")

    return {
        "is_demo": is_demo, "basis": basis, "metrics": metrics,
        "monthly": fc.monthly_results(ledger), "income_by_category": fc.breakdown(ledger, "income"),
        "expense_by_category": fc.breakdown(ledger, "expense"), "expense_ratios": ratios, "restrictions": restr,
        "position": position, "donation_trend": donation_trend, "gifts_by_month": gifts_by_month,
        "past_events": [{k: e.get(k) for k in ("id", "name", "event_date", "fundraising_goal_usd", "funds_raised_usd", "total_cost_usd",
                                              "funds_directed_usd", "is_demo")}
                        | {"net_usd": fc.event_net_proceeds(e["funds_raised_usd"], e["total_cost_usd"])
                           if e.get("funds_raised_usd") is not None and e.get("total_cost_usd") is not None else None}
                        for e in past_events],
        "legacy_funds_directed_usd": fc.r2(sum(e["funds_directed_usd"] for e in past_directed)) if past_directed else None,
        "variances": variances, "statements": statement_rows, "scenarios": scenarios, "warnings": warnings, "missing": missing,
        "pending_review": pending_review,
        "method": "Every figure is computed in Python from stored records. No AI is involved in this dashboard.",
    }
