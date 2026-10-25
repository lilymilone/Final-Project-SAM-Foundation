"""Reusable, deterministic financial calculations for a small nonprofit.

Every number on the Financial Intelligence dashboard and in the Financial
Analysis agent's work comes from these functions. Models never do arithmetic.

Records are plain dicts with at least: period (YYYY-MM), kind, category,
amount_usd, and optionally restriction and purpose. Kinds:
  income   money recorded as received (not the same as cash on hand)
  expense  money recorded as spent
  reserve  the operating reserve balance at a period end (treated as unrestricted)
  cash     a cash balance at a period end; restriction says if part of it is restricted
  budget_income / budget_expense   planned amounts, used only for budget-vs-actual variance

An empty restriction means "not documented". It is never assumed to be unrestricted.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Iterable

RESTRICTED = ("temporarily_restricted", "permanently_restricted")
RESTRICTIONS = ("unrestricted",) + RESTRICTED
PURPOSES = ("operations", "program", "event", "fundraising")


def r2(x: float) -> float:
    return round(x + 0.0, 2)


# ── Classification (explicit field first, then category wording) ─────────────────

_EXPENSE_RULES = (
    ("program", r"program|grant(s)? (to|awarded)|scholarship|research grant|charitable|direct services?|support groups?"),
    ("event", r"event|gala|venue|catering|walk|dinner|ticketing|auction"),
    ("fundraising", r"fundrais|donor (outreach|relations)|appeal|marketing"),
    ("operations", r"operat|admin|insurance|software|accounting|legal|office|bank fee|management|general"),
)
_INCOME_RULES = (
    ("donations", r"donation|gift|contribution|individual"),
    ("events", r"event|ticket|sponsor|gala|walk|auction"),
    ("grants", r"grant|foundation award"),
)


def expense_purpose(record: dict) -> str | None:
    if record.get("purpose") in PURPOSES:
        return record["purpose"]
    low = (record.get("category") or "").lower()
    return next((p for p, rx in _EXPENSE_RULES if re.search(rx, low)), None)


def income_source(record: dict) -> str:
    low = (record.get("category") or "").lower()
    return next((p for p, rx in _INCOME_RULES if re.search(rx, low)), "other")


# ── Totals and operating results ──────────────────────────────────────────────────


def _of(records: Iterable[dict], kind: str) -> list[dict]:
    return [r for r in records if r.get("kind") == kind]


def total_revenue(records: Iterable[dict]) -> float:
    return r2(sum(r["amount_usd"] for r in _of(records, "income")))


def total_expenses(records: Iterable[dict]) -> float:
    return r2(sum(r["amount_usd"] for r in _of(records, "expense")))


def operating_result(records: Iterable[dict]) -> dict:
    records = list(records)
    revenue, expenses = total_revenue(records), total_expenses(records)
    net = r2(revenue - expenses)
    return {"revenue_usd": revenue, "expenses_usd": expenses, "net_usd": net,
            "result": "surplus" if net > 0 else "deficit" if net < 0 else "break-even"}


def monthly_results(records: Iterable[dict]) -> list[dict]:
    by: dict[str, dict[str, float]] = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    for r in records:
        if r.get("kind") in ("income", "expense"):
            by[r["period"]][r["kind"]] += r["amount_usd"]
    return [{"period": p, "income": r2(v["income"]), "expense": r2(v["expense"]), "net": r2(v["income"] - v["expense"])}
            for p, v in sorted(by.items())]


def breakdown(records: Iterable[dict], kind: str) -> list[dict]:
    """Totals by category, largest first, with each category's share of the total."""
    by: dict[str, float] = defaultdict(float)
    for r in _of(records, kind):
        by[r["category"]] += r["amount_usd"]
    total = sum(by.values())
    return [{"category": c, "amount_usd": r2(v), "share": r2(v / total) if total else None}
            for c, v in sorted(by.items(), key=lambda kv: -kv[1])]


def expense_ratios(records: Iterable[dict]) -> dict:
    """Share of expenses by purpose: program, event, fundraising, operations, unclassified."""
    records = list(records)
    by: dict[str, float] = defaultdict(float)
    for r in _of(records, "expense"):
        by[expense_purpose(r) or "unclassified"] += r["amount_usd"]
    total = sum(by.values())
    return {"total_usd": r2(total), "by_purpose": {k: r2(v) for k, v in by.items()},
            "ratios": {k: r2(v / total) for k, v in by.items()} if total else {}}


def fundraising_efficiency(fundraising_costs: float, funds_raised: float) -> float | None:
    """Cost to raise one dollar (lower is better). None when nothing was raised."""
    return r2(fundraising_costs / funds_raised) if funds_raised else None


# ── Balances, restrictions, and capacity ──────────────────────────────────────────


def latest_balance(records: Iterable[dict], kind: str) -> dict | None:
    """The latest period's balance of a kind (summing rows in that period), split by restriction."""
    rows = _of(records, kind)
    if not rows:
        return None
    period = max(r["period"] for r in rows)
    current = [r for r in rows if r["period"] == period]
    restricted = sum(r["amount_usd"] for r in current if r.get("restriction") in RESTRICTED)
    return {"period": period, "total_usd": r2(sum(r["amount_usd"] for r in current)), "restricted_usd": r2(restricted)}


def restriction_summary(records: Iterable[dict]) -> dict:
    """Income by documented restriction. Undocumented income is reported separately, not assumed unrestricted."""
    out = {"unrestricted_usd": 0.0, "temporarily_restricted_usd": 0.0, "permanently_restricted_usd": 0.0, "not_documented_usd": 0.0}
    for r in _of(records, "income"):
        key = f"{r['restriction']}_usd" if r.get("restriction") in RESTRICTIONS else "not_documented_usd"
        out[key] += r["amount_usd"]
    out = {k: r2(v) for k, v in out.items()}
    out["restricted_usd"] = r2(out["temporarily_restricted_usd"] + out["permanently_restricted_usd"])
    total = out["unrestricted_usd"] + out["restricted_usd"] + out["not_documented_usd"]
    out["share_documented"] = r2((total - out["not_documented_usd"]) / total) if total else None
    return out


def reserve_months(balance_usd: float | None, avg_monthly_expense_usd: float | None) -> float | None:
    if balance_usd is None or not avg_monthly_expense_usd:
        return None
    return round(balance_usd / avg_monthly_expense_usd, 1)


def spendable_cash(cash: dict | None, restricted_income_usd: float) -> dict | None:
    """Cash minus restricted money. If no restricted balance was recorded, every restricted gift on
    record is assumed still unspent (the conservative reading)."""
    if cash is None:
        return None
    restricted = cash["restricted_usd"] if cash["restricted_usd"] else restricted_income_usd
    basis = ("restricted balance recorded with the cash balance" if cash["restricted_usd"] else
             "no restricted balance recorded, so all restricted gifts on record are assumed unspent" if restricted_income_usd else
             "no restricted funds documented")
    return {"as_of": cash["period"], "cash_usd": cash["total_usd"], "restricted_usd": r2(restricted),
            "unrestricted_usd": r2(max(0.0, cash["total_usd"] - restricted)), "basis": basis}


# ── Events ────────────────────────────────────────────────────────────────────────


def contribution_margin(revenue_per_attendee: float, variable_cost_per_attendee: float) -> dict:
    margin = revenue_per_attendee - variable_cost_per_attendee
    return {"margin_per_attendee_usd": r2(margin),
            "margin_ratio": r2(margin / revenue_per_attendee) if revenue_per_attendee else None}


def event_net_proceeds(revenue_usd: float, total_cost_usd: float) -> float:
    return r2(revenue_usd - total_cost_usd)


def break_even_attendance(fixed_costs_usd: float, revenue_per_attendee: float, variable_cost_per_attendee: float) -> int | None:
    """Guests needed for revenue to cover costs. None if each guest costs more than they bring in."""
    margin = revenue_per_attendee - variable_cost_per_attendee
    if margin <= 0:
        return None
    return math.ceil(fixed_costs_usd / margin)


def revenue_sensitivity(base_revenue_usd: float, total_cost_usd: float, shocks=(-0.30, -0.20, -0.10, 0.0, 0.10)) -> list[dict]:
    return [{"change": s, "revenue_usd": r2(base_revenue_usd * (1 + s)), "net_usd": r2(base_revenue_usd * (1 + s) - total_cost_usd)}
            for s in shocks]


def expense_sensitivity(revenue_usd: float, base_cost_usd: float, shocks=(-0.10, 0.0, 0.10, 0.20, 0.30)) -> list[dict]:
    return [{"change": s, "cost_usd": r2(base_cost_usd * (1 + s)), "net_usd": r2(revenue_usd - base_cost_usd * (1 + s))}
            for s in shocks]


def budget_variance(budget: dict[str, float], actual: dict[str, float], kind: str = "expense") -> list[dict]:
    """Budget vs actual by category. For expenses, spending less than budget is favorable; for revenue, more is."""
    rows = []
    for cat in sorted(set(budget) | set(actual)):
        b, a = budget.get(cat), actual.get(cat)
        if b is None or a is None:
            rows.append({"category": cat, "budget_usd": b, "actual_usd": a, "variance_usd": None, "variance_pct": None,
                         "direction": "missing " + ("actual" if a is None else "budget")})
            continue
        var = a - b
        favorable = var <= 0 if kind == "expense" else var >= 0
        rows.append({"category": cat, "budget_usd": r2(b), "actual_usd": r2(a), "variance_usd": r2(var),
                     "variance_pct": r2(var / b) if b else None, "direction": "favorable" if favorable else "unfavorable"})
    return rows


def compare_scenarios(scenarios: dict[str, dict]) -> list[dict]:
    """Each scenario: {revenue_usd, cost_usd}. Returns net and the difference from the first scenario."""
    rows, base = [], None
    for name, s in scenarios.items():
        net = r2(s["revenue_usd"] - s["cost_usd"])
        base = net if base is None else base
        rows.append({"scenario": name, "revenue_usd": r2(s["revenue_usd"]), "cost_usd": r2(s["cost_usd"]), "net_usd": net,
                     "vs_first_usd": r2(net - base)})
    return rows


# ── Conservative / base / optimistic ───────────────────────────────────────────────

SCENARIO_FACTORS = {
    "conservative": {"attendance": 0.80, "sponsorship": None, "donations": 0.50},  # sponsorship: confirmed amount only
    "base": {"attendance": 1.00, "sponsorship": 1.00, "donations": 1.00},
    "optimistic": {"attendance": 1.00, "sponsorship": 1.50, "donations": 1.30},
}


def event_scenarios(*, attendance: int, ticket_price: float | None, donations_per_attendee: float | None,
                    sponsorship_expected: float | None, sponsorship_confirmed: float = 0.0, other_revenue: float = 0.0,
                    total_cost: float, target: float | None = None) -> dict[str, dict]:
    """The three standard event scenarios. Costs are fixed (catering is guaranteed on the expected headcount);
    revenue drivers vary. Pledged sponsorship never counts in the conservative case."""
    if sponsorship_expected is not None:
        sponsorship_expected = max(float(sponsorship_expected), float(sponsorship_confirmed))
    out = {}
    for name, f in SCENARIO_FACTORS.items():
        att = max(0, round(attendance * f["attendance"]))
        t = r2(att * ticket_price) if ticket_price is not None else None
        if sponsorship_expected is None:
            s = None
        else:
            s = r2(sponsorship_confirmed) if f["sponsorship"] is None else r2(sponsorship_expected * f["sponsorship"])
        d = r2(att * donations_per_attendee * f["donations"]) if donations_per_attendee is not None else None
        revenue = r2(t + s + d + other_revenue) if None not in (t, s, d) else None
        net = r2(revenue - total_cost) if revenue is not None else None
        out[name] = {"attendance": att, "ticket_revenue_usd": t, "sponsorship_revenue_usd": s, "donations_usd": d,
                     "other_revenue_usd": r2(other_revenue), "total_revenue_usd": revenue, "total_cost_usd": r2(total_cost),
                     "net_usd": net, "vs_target_usd": r2(net - target) if net is not None and target is not None else None}
    return out
