"""Deterministic calculators for event planning and finance.

Every figure an agent or the board sees comes from here, never from a model.
Each input carries a label saying where it came from: a venue source, a
synthetic fixture, a past event, or a placeholder planning assumption the
board should replace with a real quote.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field

# Placeholder planning assumptions. Used only when no source states a figure,
# and always labeled as placeholders in results and in the UI.
PLACEHOLDER_FNB_PER_GUEST = {"seated_dinner": 150.0, "reception": 85.0}
PLACEHOLDER_PRODUCTION_USD = 3000.0  # AV, decor, printing, insurance
PLACEHOLDER_DEPOSIT_PCT = 0.50
DEFAULT_CONTINGENCY_PCT = 0.10
RESERVE_GUIDELINE_MONTHS = 3.0
MIN_MONTHS_FOR_PLANNING_BUDGET = 3


@dataclass
class LineItem:
    name: str
    amount_usd: float
    basis: str  # where the number came from


@dataclass
class EventBudget:
    venue_key: str
    venue_name: str
    event_format: str
    attendance: int
    line_items: list[LineItem]
    subtotal_usd: float
    contingency_pct: float
    contingency_usd: float
    total_usd: float
    upfront_cash_usd: float
    cost_per_guest_usd: float
    fixed_costs_usd: float
    variable_cost_per_guest_usd: float
    assumptions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def r2(x: float) -> float:
    return round(x + 0.0, 2)


def event_budget(
    *,
    venue_key: str,
    venue_name: str,
    event_format: str,
    attendance: int,
    rental_usd: float | None,
    fnb_per_guest_usd: float | None,
    deposit_pct: float | None,
    production_usd: float | None = None,
    contingency_pct: float | None = None,
    source_label: str = "venue source",
    fnb_minimum_usd: float | None = None,
) -> EventBudget:
    if attendance <= 0:
        raise ValueError("attendance must be positive")
    assumptions: list[str] = []
    if rental_usd is None:
        rental_usd = 0.0
        assumptions.append(f"{venue_name}: rental fee not published. Counted as $0; request a quote.")
        rental_basis = "not published (needs quote)"
    else:
        rental_basis = source_label
    if fnb_per_guest_usd is None:
        fnb_per_guest_usd = PLACEHOLDER_FNB_PER_GUEST.get(event_format, PLACEHOLDER_FNB_PER_GUEST["seated_dinner"])
        assumptions.append(f"Food & beverage ${fnb_per_guest_usd:,.0f}/guest is a placeholder planning assumption, not a quote.")
        fnb_basis = "placeholder planning assumption"
    else:
        fnb_basis = source_label
    if production_usd is None:
        production_usd = PLACEHOLDER_PRODUCTION_USD
        assumptions.append(f"Production (AV, decor, printing, insurance) ${production_usd:,.0f} is a placeholder planning assumption.")
    if deposit_pct is None:
        deposit_pct = PLACEHOLDER_DEPOSIT_PCT
        assumptions.append(f"Deposit of {deposit_pct:.0%} before the event is a placeholder planning assumption.")
    if contingency_pct is None:
        contingency_pct = DEFAULT_CONTINGENCY_PCT
        assumptions.append(f"Contingency {contingency_pct:.0%} (default; no lesson-based figure supplied).")

    fnb_total = fnb_per_guest_usd * attendance
    minimum_applies = fnb_minimum_usd is not None and fnb_minimum_usd > fnb_total
    if minimum_applies:
        assumptions.append(f"The venue's ${fnb_minimum_usd:,.0f} food-and-beverage minimum exceeds {attendance} × "
                           f"${fnb_per_guest_usd:,.0f}, so the minimum is charged.")
        fnb_total = fnb_minimum_usd
    subtotal = rental_usd + fnb_total + production_usd
    contingency = subtotal * contingency_pct
    total = subtotal + contingency
    upfront = deposit_pct * (rental_usd + fnb_total) + production_usd
    return EventBudget(
        venue_key=venue_key,
        venue_name=venue_name,
        event_format=event_format,
        attendance=attendance,
        line_items=[
            LineItem("Venue rental", r2(rental_usd), rental_basis),
            LineItem(f"Food & beverage (venue minimum ${fnb_minimum_usd:,.0f})" if minimum_applies
                     else f"Food & beverage ({attendance} × ${fnb_per_guest_usd:,.2f})", r2(fnb_total), fnb_basis),
            LineItem("Production", r2(production_usd), "placeholder planning assumption"),
        ],
        subtotal_usd=r2(subtotal),
        contingency_pct=contingency_pct,
        contingency_usd=r2(contingency),
        total_usd=r2(total),
        upfront_cash_usd=r2(upfront),
        cost_per_guest_usd=r2(total / attendance),
        fixed_costs_usd=r2((rental_usd + production_usd + (fnb_total if minimum_applies else 0.0)) * (1 + contingency_pct)),
        # Under a binding minimum, food is effectively a fixed cost up to the minimum.
        variable_cost_per_guest_usd=r2(0.0 if minimum_applies else fnb_per_guest_usd * (1 + contingency_pct)),
        assumptions=assumptions,
    )


def revenue_per_attendee_from_history(events: Iterable[dict], event_type: str) -> dict:
    """Revenue per attendee from the organization's own past events.

    Prefers events of a similar type (gala/dinner for a gala). Otherwise falls
    back to all events that recorded both funds raised and attendance.
    """
    usable = [e for e in events if e.get("funds_raised_usd") and e.get("attendance")]
    similar_types = {"gala": {"gala", "dinner"}, "dinner": {"gala", "dinner"}}.get(event_type, {event_type})
    comparable = [e for e in usable if (e.get("event_type") or "").lower() in similar_types] or usable
    if not comparable:
        return {"per_attendee_usd": None, "basis": "No past events with funds raised and attendance recorded.", "event_ids": []}
    per = [e["funds_raised_usd"] / e["attendance"] for e in comparable]
    value = sum(per) / len(per)
    names = ", ".join(e["name"] for e in comparable)
    return {
        "per_attendee_usd": r2(value),
        "basis": f"Average funds raised per attendee at comparable past events: {names}",
        "event_ids": [e["id"] for e in comparable],
    }


def revenue_scenarios(attendance: int, per_attendee_usd: float, low_factor: float = 0.70, high_factor: float = 1.15) -> dict:
    base = per_attendee_usd * attendance
    return {
        "low": r2(base * low_factor),
        "base": r2(base),
        "high": r2(base * high_factor),
        "per_attendee_usd": r2(per_attendee_usd),
        "assumptions": [
            f"Base = ${per_attendee_usd:,.2f} per attendee × {attendance} attendees (from past events).",
            f"Low = base × {low_factor:.2f} and high = base × {high_factor:.2f} (sensitivity assumptions).",
        ],
    }


def financial_position(records: Iterable[dict]) -> dict:
    records = list(records)
    by_month: dict[str, dict[str, float]] = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    reserve: tuple[str, float] | None = None
    for r in records:
        if r["kind"] in ("income", "expense"):
            by_month[r["period"]][r["kind"]] += r["amount_usd"]
        elif r["kind"] == "reserve" and (reserve is None or r["period"] >= reserve[0]):
            reserve = (r["period"], r["amount_usd"])
    months = sorted(by_month)
    income = sum(v["income"] for v in by_month.values())
    expense = sum(v["expense"] for v in by_month.values())
    avg_expense = expense / len(months) if months else None
    out = {
        "months_of_data": len(months),
        "period_start": months[0] if months else None,
        "period_end": months[-1] if months else None,
        "total_income_usd": r2(income),
        "total_expense_usd": r2(expense),
        "net_usd": r2(income - expense),
        "average_monthly_expense_usd": r2(avg_expense) if avg_expense is not None else None,
        "reserve_usd": reserve[1] if reserve else None,
        "reserve_guideline_months": RESERVE_GUIDELINE_MONTHS,
        "available_planning_budget_usd": None,
        "available_planning_budget_basis": None,
    }
    # Cash and restricted funds: restricted gifts are never spendable for events.
    from .fin_calc import latest_balance, restriction_summary, spendable_cash  # local import keeps this module dependency-free
    restricted_income = restriction_summary(records)["restricted_usd"]
    spend = spendable_cash(latest_balance(records, "cash"), restricted_income)
    out["restricted_income_usd"] = restricted_income
    out["cash"] = spend
    # Only report a planning budget when the records actually support it.
    if reserve is None and spend is not None and len(months) >= MIN_MONTHS_FOR_PLANNING_BUDGET:
        floor = RESERVE_GUIDELINE_MONTHS * avg_expense
        out["reserve_floor_usd"] = r2(floor)
        out["available_planning_budget_usd"] = r2(max(0.0, spend["unrestricted_usd"] - floor))
        out["available_planning_budget_basis"] = (
            f"Unrestricted cash ${spend['unrestricted_usd']:,.0f} (as of {spend['as_of']}; {spend['basis']}) minus a "
            f"{RESERVE_GUIDELINE_MONTHS:g}-month floor (${floor:,.0f}).")
    elif reserve is None:
        out["available_planning_budget_basis"] = "Not supported: no reserve balance recorded."
    elif len(months) < MIN_MONTHS_FOR_PLANNING_BUDGET:
        out["available_planning_budget_basis"] = (
            f"Not supported: only {len(months)} month(s) of income/expense data (need {MIN_MONTHS_FOR_PLANNING_BUDGET})."
        )
    else:
        floor = RESERVE_GUIDELINE_MONTHS * avg_expense
        available = max(0.0, reserve[1] - floor)
        out["reserve_floor_usd"] = r2(floor)
        out["available_planning_budget_usd"] = r2(available)
        out["available_planning_budget_basis"] = (
            f"Reserve ${reserve[1]:,.0f} minus a {RESERVE_GUIDELINE_MONTHS:g}-month floor "
            f"(${floor:,.0f} = {RESERVE_GUIDELINE_MONTHS:g} × ${avg_expense:,.0f} average monthly expense)."
        )
        if spend is not None and spend["unrestricted_usd"] - floor < available:  # cash says less is truly spendable
            out["available_planning_budget_usd"] = r2(max(0.0, spend["unrestricted_usd"] - floor))
            out["available_planning_budget_basis"] += (
                f" Capped by unrestricted cash ${spend['unrestricted_usd']:,.0f} (as of {spend['as_of']}; {spend['basis']}).")
    return out


def break_even(budget: dict, per_attendee_usd: float | None) -> dict:
    attendance = budget["attendance"]
    total = budget["total_usd"]
    out = {
        "break_even_revenue_per_attendee_usd": r2(total / attendance),
        "break_even_attendance": None,
        "basis": "Fixed costs ÷ (revenue per attendee − variable cost per guest), contingency included.",
    }
    if per_attendee_usd is None:
        out["note"] = "No revenue-per-attendee history, so break-even attendance cannot be computed."
        return out
    margin = per_attendee_usd - budget["variable_cost_per_guest_usd"]
    if margin <= 0:
        out["note"] = "Revenue per attendee does not cover the per-guest cost; the event never breaks even at this price."
        return out
    out["break_even_attendance"] = math.ceil(budget["fixed_costs_usd"] / margin)
    return out


def sensitivity(budget: dict, per_attendee_usd: float | None) -> list[dict]:
    """Net result if attendance, giving per attendee, or catering costs move."""
    if per_attendee_usd is None:
        return []
    rows = []
    base_att = budget["attendance"]
    fixed = budget["fixed_costs_usd"]
    var = budget["variable_cost_per_guest_usd"]
    for att_label, att_factor in (("attendance −20%", 0.8), ("planned attendance", 1.0), ("attendance +20%", 1.2)):
        for rev_label, rev_factor in (("giving −30%", 0.7), ("giving as in past events", 1.0)):
            att = max(1, round(base_att * att_factor))
            revenue = per_attendee_usd * rev_factor * att
            cost = fixed + var * att
            rows.append({"scenario": f"{att_label}, {rev_label}", "attendance": att, "revenue_usd": r2(revenue),
                         "cost_usd": r2(cost), "net_usd": r2(revenue - cost)})
    cost = fixed + var * 1.15 * base_att
    revenue = per_attendee_usd * base_att
    rows.append({"scenario": "catering +15% (overrun)", "attendance": base_att, "revenue_usd": r2(revenue),
                 "cost_usd": r2(cost), "net_usd": r2(revenue - cost)})
    return rows


def affordability(
    budget: dict,
    position: dict,
    budget_limit_usd: float | None,
    break_even_result: dict,
    revenue: dict | None,
    min_contingency_pct: float | None,
) -> dict:
    """Pass/fail checks plus a verdict. Conflicts are what the Orchestrator acts on."""
    checks: list[dict] = []
    conflicts: list[dict] = []

    def add(name: str, passed: bool | None, detail: str, conflict: dict | None = None) -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})
        if passed is False and conflict:
            conflicts.append(conflict)

    total = budget["total_usd"]
    if budget_limit_usd:
        add("Within the board's budget limit", total <= budget_limit_usd,
            f"Projected total ${total:,.0f} vs limit ${budget_limit_usd:,.0f}.",
            {"type": "over_budget_limit", "detail": f"Projected ${total:,.0f} exceeds the ${budget_limit_usd:,.0f} limit.",
             "max_total_usd": budget_limit_usd})
    else:
        add("Within the board's budget limit", None, "No budget limit set for this event.")

    available = position.get("available_planning_budget_usd")
    upfront = budget["upfront_cash_usd"]
    if available is not None:
        add("Upfront cash fits the available planning budget", upfront <= available,
            f"Deposits and prepaid costs ${upfront:,.0f} vs available ${available:,.0f} above the reserve floor.",
            {"type": "upfront_cash_exceeds_available", "detail": f"Upfront cash ${upfront:,.0f} exceeds the ${available:,.0f} available above the reserve floor.",
             "max_upfront_usd": available})
    else:
        add("Upfront cash fits the available planning budget", None, position.get("available_planning_budget_basis") or "Unknown.")

    be = break_even_result.get("break_even_attendance")
    if be is not None:
        add("Break-even attendance below planned attendance", be <= budget["attendance"],
            f"Break-even at {be} guests vs {budget['attendance']} planned.",
            {"type": "break_even_too_high", "detail": f"Needs {be} guests to break even; {budget['attendance']} planned."})
    else:
        add("Break-even attendance below planned attendance", None, break_even_result.get("note", "Not computable."))

    if revenue:
        net = revenue["base"] - total
        add("Base-case net is positive", net >= 0, f"Base revenue ${revenue['base']:,.0f} − cost ${total:,.0f} = ${net:,.0f}.",
            {"type": "negative_net", "detail": f"Base case loses ${-net:,.0f}."})
    if min_contingency_pct is not None:
        add("Contingency meets the lesson from past events", budget["contingency_pct"] >= min_contingency_pct,
            f"Contingency {budget['contingency_pct']:.0%} vs {min_contingency_pct:.0%} recommended from history.",
            {"type": "contingency_below_lesson", "detail": f"History recommends at least {min_contingency_pct:.0%} contingency.",
             "min_contingency_pct": min_contingency_pct})

    failed = [c for c in checks if c["passed"] is False]
    unknown = [c for c in checks if c["passed"] is None]
    if any(c["type"] in ("over_budget_limit", "negative_net") for c in conflicts):
        verdict = "not_affordable_as_planned"
    elif failed:
        verdict = "affordable_with_conditions"
    elif unknown and len(unknown) == len(checks):
        verdict = "insufficient_data"
    else:
        verdict = "affordable"
    return {"verdict": verdict, "checks": checks, "conflicts": conflicts}


def compare_events(events: Iterable[dict]) -> list[dict]:
    rows = []
    for e in events:
        raised, cost, att = e.get("funds_raised_usd"), e.get("total_cost_usd"), e.get("attendance")
        rows.append({
            "event_id": e["id"],
            "name": e["name"],
            "event_type": e.get("event_type"),
            "net_usd": r2(raised - cost) if raised is not None and cost is not None else None,
            "raised_per_dollar_spent": r2(raised / cost) if raised and cost else None,
            "raised_per_attendee_usd": r2(raised / att) if raised and att else None,
            "cost_per_attendee_usd": r2(cost / att) if cost and att else None,
            "attendance": att,
        })
    return sorted(rows, key=lambda r: (r["net_usd"] is None, -(r["net_usd"] or 0)))


def _money(x: float) -> str:
    return f"${x:,.0f}"


def quantitative_observations(events: Iterable[dict]) -> list[dict]:
    """Facts computed from recorded figures only (no model, no reflections). Each names the events it rests on.
    Nothing is reported for a measure that no event recorded."""
    events = list(events)
    out: list[dict] = []
    with_net = [e for e in events if e.get("funds_raised_usd") is not None and e.get("total_cost_usd") is not None]
    by_type: dict[str, list[dict]] = defaultdict(list)
    for e in with_net:
        by_type[(e.get("event_type") or "event").strip().lower()].append(e)
    if len(by_type) >= 2:
        parts = []
        for t, items in sorted(by_type.items(), key=lambda kv: -sum(i["funds_raised_usd"] - i["total_cost_usd"] for i in kv[1]) / len(kv[1])):
            avg = sum(i["funds_raised_usd"] - i["total_cost_usd"] for i in items) / len(items)
            parts.append(f"{t} ({len(items)} event{'s' if len(items) > 1 else ''}): average net {_money(avg)}")
        out.append({"area": "fundraising_approach", "text": "Net proceeds by event type: " + "; ".join(parts) + ".",
                    "event_ids": [e["id"] for e in with_net]})
    goals = [e for e in events if e.get("fundraising_goal_usd") and e.get("funds_raised_usd") is not None]
    if goals:
        out.append({"area": "fundraising_approach", "event_ids": [e["id"] for e in goals],
                    "text": "Goal attainment: " + "; ".join(f"{e['name']} raised {100 * e['funds_raised_usd'] / e['fundraising_goal_usd']:.0f}% "
                                                             f"of its {_money(e['fundraising_goal_usd'])} goal" for e in goals) + "."})
    planned = [e for e in events if e.get("planned_budget_usd") and e.get("total_cost_usd") is not None]
    over = [e for e in planned if e["total_cost_usd"] > e["planned_budget_usd"]]
    if over:
        out.append({"area": "costs", "event_ids": [e["id"] for e in over],
                    "text": "Cost overruns against the planned budget: " + "; ".join(
                        f"{e['name']} spent {_money(e['total_cost_usd'])} vs {_money(e['planned_budget_usd'])} planned "
                        f"(+{100 * (e['total_cost_usd'] / e['planned_budget_usd'] - 1):.0f}%)" for e in over) + "."})
    elif planned:
        out.append({"area": "costs", "event_ids": [e["id"] for e in planned],
                    "text": f"No recorded cost overrun: {len(planned)} event(s) with a planned budget stayed within it."})
    per_guest = [e for e in events if e.get("total_cost_usd") and e.get("attendance")]
    if len(per_guest) >= 2:
        hi = max(per_guest, key=lambda e: e["total_cost_usd"] / e["attendance"])
        lo = min(per_guest, key=lambda e: e["total_cost_usd"] / e["attendance"])
        out.append({"area": "costs", "event_ids": [hi["id"], lo["id"]],
                    "text": f"Cost per guest ranged from {_money(lo['total_cost_usd'] / lo['attendance'])} ({lo['name']}) to "
                            f"{_money(hi['total_cost_usd'] / hi['attendance'])} ({hi['name']})."})
    sponsored = [e for e in events if e.get("sponsorship_usd") and e.get("funds_raised_usd")]
    if sponsored:
        out.append({"area": "sponsorship", "event_ids": [e["id"] for e in sponsored],
                    "text": "Sponsorship share of revenue: " + "; ".join(
                        f"{e['name']} {100 * e['sponsorship_usd'] / e['funds_raised_usd']:.0f}% ({_money(e['sponsorship_usd'])})" for e in sponsored) + "."})
    community = [e for e in events if e.get("repeat_participants") or e.get("partnerships_formed") or e.get("volunteers_count")]
    if community:
        def bits(e):
            b = [f"{e['volunteers_count']} volunteers" if e.get("volunteers_count") else None,
                 f"{e['repeat_participants']} repeat participants" if e.get("repeat_participants") else None,
                 f"{e['partnerships_formed']} partnerships formed" if e.get("partnerships_formed") else None]
            return ", ".join(x for x in b if x)
        out.append({"area": "community", "event_ids": [e["id"] for e in community],
                    "text": "Recorded community measures: " + "; ".join(f"{e['name']}: {bits(e)}" for e in community) + "."})
    for o in out:
        o["basis"] = "computed"
        o["sample_note"] = f"Based on {len(o['event_ids'])} recorded event(s)." + (" Small sample: treat as a signal, not a trend."
                                                                                   if len(o["event_ids"]) < 3 else "")
    return out


_CITY_SYNONYMS = {"manhattan": "new york", "nyc": "new york", "new york city": "new york", "brooklyn": "new york", "queens": "new york"}


def _place_tokens(text: str | None) -> set[str]:
    t = (text or "").lower()
    toks = {w.strip() for w in t.split(",") if len(w.strip()) > 2}  # state codes ("NY") alone are too broad to count
    out = set()
    for w in toks:
        out.add(w)
        for k, v in _CITY_SYNONYMS.items():
            if k in w:
                out.add(v)
    return out


def rank_relevant_events(items: list[dict], *, event_type: str | None, city: str | None, attendance: int | None) -> list[dict]:
    """Score past events by similarity to a planned one. Deterministic; every point has a stated reason."""
    want_type = set((event_type or "").lower().replace("-", " ").split()) - {"event", "the", "a"}
    want_place = _place_tokens(city)
    years = [i["year"] for i in items if i.get("year")]
    latest = max(years) if years else None
    ranked = []
    for i in items:
        score, reasons = 0, []
        have_type = set((i.get("event_type") or "").lower().replace("-", " ").split()) - {"event", "the", "a"}
        if want_type and have_type & want_type:
            score += 3
            reasons.append(f"same type ({i['event_type']})")
        if want_place and _place_tokens(i.get("location")) & want_place:
            score += 2
            reasons.append(f"same area ({i['location']})")
        if attendance and i.get("attendance"):
            ratio = i["attendance"] / attendance
            if 0.67 <= ratio <= 1.5:
                score += 2
                reasons.append(f"similar size ({i['attendance']} guests)")
        if latest and i.get("year") and latest - i["year"] <= 2:
            score += 1
            reasons.append(f"recent ({i['year']})")
        ranked.append({**i, "score": score, "reasons": reasons or ["no close match; included for general lessons"]})
    ranked.sort(key=lambda r: (-r["score"], -(r.get("year") or 0)))
    return ranked
