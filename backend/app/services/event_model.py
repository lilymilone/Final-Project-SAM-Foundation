"""Deterministic financial model for Event Studio.

Every number here is computed in Python. Each assumption carries a "basis"
saying where it came from:

  published     the venue states it (on a page we fetched, or in a labeled synthetic fixture)
  board         entered by a board member (Event Studio form or edited assumptions)
  history       derived from the foundation's recorded past events
  lesson        recommended by Event Intelligence from board reflections
  placeholder   a generic planning figure, to be replaced with a real quote
  hypothetical  an estimate used where the venue publishes no price ("Quote required")
  missing       not provided and not derivable, so it stays empty and is never guessed

Three scenarios vary only the revenue drivers. Costs are the same in all
three, because catering is guaranteed on the expected headcount:

  conservative  80% attendance · confirmed sponsorship only · 50% donations
  base          expected attendance · expected sponsorship · historical giving
  optimistic    full attendance · 150% of expected sponsorship · 130% donations

Pledged or prospective sponsorship is never treated as guaranteed: only
sponsorship the board marks as confirmed (signed or received) counts in the
conservative case, and a second break-even shows the headcount needed if no
unconfirmed sponsorship arrives.
"""

from __future__ import annotations

from typing import Any

from .fin_calc import SCENARIO_FACTORS, event_scenarios

PLACEHOLDERS: dict[str, Any] = {
    "catering_per_guest_usd": {"seated_dinner": 150.0, "reception": 85.0},
    "venue_rental_estimate_usd": 6000.0,
    "entertainment_usd": 1500.0,
    "marketing_usd": 600.0,
    "staffing_usd": 900.0,
    "insurance_usd": 500.0,
    "misc_usd": 0.0,
    "contingency_pct": 0.10,
    "deposit_pct": 0.50,
}

SCENARIOS = SCENARIO_FACTORS  # one definition, in services/fin_calc.py

# Order and labels for the editable assumptions table.
ASSUMPTION_LABELS = {
    "attendance": "Expected attendees",
    "ticket_price_usd": "Ticket price",
    "venue_rental_usd": "Venue rental",
    "catering_per_guest_usd": "Catering per guest",
    "catering_minimum_usd": "Catering minimum",
    "entertainment_usd": "Entertainment",
    "marketing_usd": "Marketing",
    "staffing_usd": "Staffing",
    "insurance_usd": "Insurance and permits",
    "misc_usd": "Miscellaneous",
    "contingency_pct": "Contingency",
    "sponsorship_usd": "Sponsorship expected (pledged or prospective)",
    "sponsorship_confirmed_usd": "Sponsorship confirmed (signed or received)",
    "donations_per_attendee_usd": "Donations per attendee",
    "other_revenue_usd": "Other documented revenue",
    "deposit_pct": "Deposit due before the event",
}
REVENUE_INPUTS = ("ticket_price_usd", "sponsorship_usd", "donations_per_attendee_usd")
GALA_TYPES = ("gala", "dinner", "benefit")


def r2(x: float) -> float:
    return round(x + 0.0, 2)


def A(value: Any, kind: str, basis: str) -> dict:
    return {"value": value, "kind": kind, "basis": basis}


def history_basis(events: list[dict], event_type: str) -> dict:
    """Guest giving and sponsorship from comparable recorded events (gala ~ dinner)."""
    t = (event_type or "").lower()
    similar = {"gala", "dinner", "benefit"} if any(g in t for g in GALA_TYPES) else {t}
    usable = [e for e in events if e.get("funds_raised_usd") and e.get("attendance")]
    comparable = [e for e in usable if any(s in (e.get("event_type") or "").lower() for s in similar)] or usable
    if not comparable:
        return {"guest_giving_per_attendee_usd": None, "sponsorship_usd": None, "event_ids": [], "names": []}
    giving = [(e["funds_raised_usd"] - (e.get("sponsorship_usd") or 0)) / e["attendance"] for e in comparable]
    sponsors = [e["sponsorship_usd"] for e in comparable if e.get("sponsorship_usd") is not None]
    return {
        "guest_giving_per_attendee_usd": r2(sum(giving) / len(giving)),
        "sponsorship_usd": r2(sum(sponsors) / len(sponsors)) if sponsors else None,
        "event_ids": [e["id"] for e in comparable],
        "names": [e["name"] for e in comparable],
    }


def build_assumptions(*, venue: dict | None, event_format: str, event: dict, history: dict, contingency_pct: float | None,
                      overrides: dict | None = None) -> dict:
    """Assemble labeled assumptions for one venue option. Never invents a price:
    an unpublished rental becomes a clearly labeled hypothetical estimate."""
    venue = venue or {}
    synthetic = venue.get("verification") == "synthetic"
    src = "synthetic fixture" if synthetic else "venue's published information (page verified)"
    out: dict[str, dict] = {}
    out["attendance"] = A(int(event.get("attendance") or 0) or None, "board" if event.get("attendance") else "missing",
                          "Entered in Event Studio" if event.get("attendance") else "Not provided")
    ticket = event.get("ticket_price_usd")
    out["ticket_price_usd"] = A(ticket, "board", "Entered in Event Studio") if ticket is not None else A(None, "missing", "Not provided")

    if venue.get("rental_usd") is not None and venue.get("pricing_status") == "published":
        out["venue_rental_usd"] = A(float(venue["rental_usd"]), "published", f"Rental fee from the {src}")
    else:
        out["venue_rental_usd"] = A(PLACEHOLDERS["venue_rental_estimate_usd"], "hypothetical",
                                    "Quote required: the venue publishes no rental price. Hypothetical planning estimate, not a quote.")
    fnb = venue.get("fnb_per_guest_usd")
    fnb_value = fnb.get(event_format) if isinstance(fnb, dict) else fnb
    if fnb_value is not None and venue.get("pricing_status") == "published":
        out["catering_per_guest_usd"] = A(float(fnb_value), "published", f"Per-guest catering from the {src}")
    else:
        out["catering_per_guest_usd"] = A(PLACEHOLDERS["catering_per_guest_usd"].get(event_format, 150.0), "placeholder",
                                          "Placeholder planning figure; request a catering quote")
    minimum = venue.get("fnb_minimum_usd")
    out["catering_minimum_usd"] = (A(float(minimum), "published", f"Food-and-beverage minimum from the {src}")
                                   if minimum is not None and venue.get("pricing_status") == "published"
                                   else A(None, "missing", "No published minimum (confirm with the venue)"))
    for key in ("entertainment_usd", "marketing_usd", "staffing_usd", "insurance_usd"):
        out[key] = A(PLACEHOLDERS[key], "placeholder", "Placeholder planning figure; replace with quotes")
    out["misc_usd"] = A(PLACEHOLDERS["misc_usd"], "placeholder", "Not estimated (contingency covers small items); enter known costs such as printing or permits")
    out["contingency_pct"] = (A(contingency_pct, "lesson", "Recommended by Event Intelligence from past cost overruns")
                              if contingency_pct is not None else A(PLACEHOLDERS["contingency_pct"], "placeholder", "Default planning contingency"))
    names = ", ".join(history.get("names") or [])
    if history.get("sponsorship_usd") is not None:
        out["sponsorship_usd"] = A(history["sponsorship_usd"], "history", f"Average sponsorship at comparable past events: {names}")
    else:
        out["sponsorship_usd"] = A(None, "missing", "No sponsorship history; enter an expected amount")
    out["sponsorship_confirmed_usd"] = A(0.0, "board", "No sponsorship confirmed yet; pledges are not counted as guaranteed")
    out["other_revenue_usd"] = A(0.0, "board", "No other documented revenue; enter only documented amounts (e.g. a confirmed auction donation)")
    giving = history.get("guest_giving_per_attendee_usd")
    if giving is not None and ticket is not None:
        out["donations_per_attendee_usd"] = A(r2(max(0.0, giving - ticket)), "history",
                                              f"Past guest giving per attendee ({names}, ${giving:,.2f}) minus the ticket price")
    else:
        out["donations_per_attendee_usd"] = A(None, "missing", "Needs a ticket price and past giving data to separate donations from tickets"
                                              if giving is not None else "No past giving data")
    out["deposit_pct"] = (A(venue["deposit_pct"], "published", f"Deposit terms from the {src}")
                          if venue.get("deposit_pct") is not None and venue.get("pricing_status") == "published"
                          else A(PLACEHOLDERS["deposit_pct"], "placeholder", "Placeholder deposit assumption"))
    for key, value in (overrides or {}).items():
        if key in ASSUMPTION_LABELS and value is not None:
            out[key] = A(value, "board", "Edited by the board")
    return out


def _catering(per_guest: float, guests: int, minimum: float | None) -> tuple[float, bool]:
    base = per_guest * guests
    if minimum is not None and minimum > base:
        return minimum, True
    return base, False


def compute(assumptions: dict, *, max_budget_usd: float | None = None, target_usd: float | None = None) -> dict:
    v = {k: (a["value"] if isinstance(a, dict) else a) for k, a in assumptions.items()}
    n = int(v.get("attendance") or 0)
    if n <= 0:
        raise ValueError("Expected attendees must be a positive number.")
    pct = float(v.get("contingency_pct") or 0.0)
    venue = float(v["venue_rental_usd"])
    catering, minimum_applies = _catering(float(v["catering_per_guest_usd"]), n, v.get("catering_minimum_usd"))
    v.setdefault("misc_usd", 0.0)  # models saved before these lines existed
    v.setdefault("sponsorship_confirmed_usd", 0.0)
    v.setdefault("other_revenue_usd", 0.0)
    fixed_keys = ("entertainment_usd", "marketing_usd", "staffing_usd", "insurance_usd", "misc_usd")
    fixed_other = sum(float(v[k] or 0) for k in fixed_keys)
    lines = [
        {"category": "Venue", "amount_usd": r2(venue), "basis": assumptions["venue_rental_usd"].get("basis") if isinstance(assumptions["venue_rental_usd"], dict) else ""},
        {"category": "Catering", "amount_usd": r2(catering),
         "basis": f"Venue minimum applies (${v['catering_minimum_usd']:,.0f} > {n} × ${v['catering_per_guest_usd']:,.2f})" if minimum_applies
         else f"{n} guests × ${float(v['catering_per_guest_usd']):,.2f}"},
    ] + [{"category": ASSUMPTION_LABELS[k], "amount_usd": r2(float(v[k] or 0)),
          "basis": (assumptions.get(k) or {}).get("basis", "") if isinstance(assumptions.get(k), dict) else ""}
         for k in fixed_keys]
    subtotal = venue + catering + fixed_other
    contingency = subtotal * pct
    total = subtotal + contingency
    upfront = float(v.get("deposit_pct") or 0) * (venue + catering) + float(v["marketing_usd"]) + float(v["insurance_usd"])

    missing = [k for k in REVENUE_INPUTS if v.get(k) is None]
    ticket, sponsorship, donations = v.get("ticket_price_usd"), v.get("sponsorship_usd"), v.get("donations_per_attendee_usd")
    confirmed = float(v.get("sponsorship_confirmed_usd") or 0.0)
    other = float(v.get("other_revenue_usd") or 0.0)
    if sponsorship is not None:
        sponsorship = max(float(sponsorship), confirmed)  # expected can never be less than what is already confirmed
    scenarios = event_scenarios(attendance=n, ticket_price=ticket, donations_per_attendee=donations, sponsorship_expected=sponsorship,
                                sponsorship_confirmed=confirmed, other_revenue=other, total_cost=total, target=target_usd)

    # Break-even: the smallest headcount whose revenue covers its cost (catering minimum and contingency included).
    def _break_even(sponsor: float) -> int | None:
        for guests in range(0, max(3 * n, 1000) + 1):
            cat, _ = _catering(float(v["catering_per_guest_usd"]), guests, v.get("catering_minimum_usd"))
            cost = (venue + cat + fixed_other) * (1 + pct)
            if sponsor + other + guests * (ticket + donations) >= cost:
                return guests
        return None

    break_even, be_note, break_even_confirmed = None, None, None
    if ticket is None or donations is None or sponsorship is None:
        be_note = "Needs ticket price, sponsorship, and donations per attendee."
    else:
        break_even = _break_even(sponsorship)
        break_even_confirmed = _break_even(confirmed)
        if break_even is None:
            be_note = "Revenue per guest never covers costs within three times the expected attendance."
        elif break_even == 0:
            be_note = "Expected sponsorship alone covers the fixed costs."

    checks = []

    def check(name: str, passed: bool | None, detail: str, kind: str) -> None:
        checks.append({"name": name, "passed": passed, "detail": detail, "kind": kind})

    if max_budget_usd:
        check("Within the maximum planning budget", total <= max_budget_usd, f"Projected cost ${total:,.0f} vs maximum ${max_budget_usd:,.0f}.", "over_budget_limit")
    else:
        check("Within the maximum planning budget", None, "No maximum planning budget entered.", "over_budget_limit")
    base_net = scenarios["base"]["net_usd"]
    check("Base case covers its costs", None if base_net is None else base_net >= 0,
          "Revenue incomplete: " + ", ".join(ASSUMPTION_LABELS[m].lower() for m in missing) if base_net is None else f"Base-case net ${base_net:,.0f}.",
          "negative_net")
    cons = scenarios["conservative"]["net_usd"]
    check("Conservative case avoids a loss", None if cons is None else cons >= 0,
          "Revenue incomplete." if cons is None else f"Conservative net ${cons:,.0f}.", "conservative_loss")
    check("Break-even below expected attendance", None if break_even is None else break_even <= n,
          be_note or f"Break-even at {break_even} guests vs {n} expected.", "break_even_too_high")
    if target_usd:
        check("Base case meets the fundraising target", None if base_net is None else base_net >= target_usd,
              "Revenue incomplete." if base_net is None else f"Base-case net ${base_net:,.0f} vs target ${target_usd:,.0f}.", "below_target")

    return {
        "lines": lines, "subtotal_usd": r2(subtotal), "contingency_pct": pct, "contingency_usd": r2(contingency),
        "total_cost_usd": r2(total), "upfront_cash_usd": r2(upfront), "catering_minimum_applies": minimum_applies,
        "scenarios": scenarios, "break_even_attendance": break_even, "break_even_note": be_note,
        "break_even_confirmed_only": break_even_confirmed,
        "sponsorship_confirmed_usd": r2(confirmed), "sponsorship_unconfirmed_usd": r2(max(0.0, (sponsorship or 0) - confirmed)),
        "missing_inputs": [ASSUMPTION_LABELS[m] for m in missing], "complete": not missing, "checks": checks,
        "assumptions": assumptions, "attendance": n, "max_budget_usd": max_budget_usd, "target_usd": target_usd,
        "scenario_definitions": {k: f"attendance {int(f['attendance'] * 100)}%, "
                                    + ("confirmed sponsorship only" if f["sponsorship"] is None else f"sponsorship {int(f['sponsorship'] * 100)}% of expected")
                                    + f", donations {int(f['donations'] * 100)}%" for k, f in SCENARIOS.items()},
    }


def catering_minimum_risk(assumptions: dict, share: float = SCENARIOS["conservative"]["attendance"]) -> dict | None:
    """If attendance falls to the conservative level, would a venue minimum still be charged in full?"""
    v = {k: (a["value"] if isinstance(a, dict) else a) for k, a in assumptions.items()}
    minimum = v.get("catering_minimum_usd")
    if not minimum or not v.get("attendance"):
        return None
    guests = round(v["attendance"] * share)
    by_head = v["catering_per_guest_usd"] * guests
    if minimum > by_head:
        return {"minimum_usd": minimum, "guests": guests, "by_head_usd": r2(by_head), "overpay_usd": r2(minimum - by_head)}
    return None


def affordability(model: dict, position: dict, min_contingency_pct: float | None) -> dict:
    """Add the organization's cash position to the event model's own checks.

    Recorded income is never treated as cash. Only the recorded reserve balance
    above the reserve floor counts as available for upfront event costs."""
    checks = [dict(c) for c in model["checks"]]
    available = position.get("available_planning_budget_usd")
    upfront = model["upfront_cash_usd"]
    if available is not None:
        checks.append({"name": "Upfront cash fits the available planning budget", "passed": upfront <= available,
                       "detail": f"Deposits and prepaid costs ${upfront:,.0f} vs ${available:,.0f} available above the reserve floor "
                                 "(event revenue arrives after deposits are due, so it is not counted).",
                       "kind": "upfront_cash_exceeds_available"})
    else:
        checks.append({"name": "Upfront cash fits the available planning budget", "passed": None,
                       "detail": position.get("available_planning_budget_basis") or "Not supported by the records.",
                       "kind": "upfront_cash_exceeds_available"})
    if min_contingency_pct is not None:
        checks.append({"name": "Contingency meets the lesson from past events", "passed": model["contingency_pct"] >= min_contingency_pct - 1e-9,
                       "detail": f"Contingency {model['contingency_pct']:.0%} vs {min_contingency_pct:.0%} recommended from history.",
                       "kind": "contingency_below_lesson"})
    revision_triggers = {"over_budget_limit", "upfront_cash_exceeds_available", "negative_net", "contingency_below_lesson"}
    conflicts = []
    for c in checks:
        if c["passed"] is False and c["kind"] in revision_triggers:
            conflict = {"type": c["kind"], "detail": c["detail"], "source": "finance"}
            if c["kind"] == "over_budget_limit":
                conflict["max_total_usd"] = model["max_budget_usd"]
            if c["kind"] == "upfront_cash_exceeds_available":
                conflict["max_upfront_usd"] = available
            if c["kind"] == "contingency_below_lesson":
                conflict["min_contingency_pct"] = min_contingency_pct
            conflicts.append(conflict)
    warnings = [c["detail"] for c in checks if c["passed"] is False and c["kind"] not in revision_triggers]
    unknown = [c for c in checks if c["passed"] is None]
    if any(c["type"] in ("over_budget_limit", "negative_net") for c in conflicts):
        verdict = "not_affordable_as_planned"
    elif conflicts:
        verdict = "affordable_with_conditions"
    elif not model["complete"]:
        verdict = "insufficient_data"
    elif warnings or unknown:
        verdict = "affordable_with_conditions"
    else:
        verdict = "affordable"
    return {"verdict": verdict, "checks": checks, "conflicts": conflicts, "warnings": warnings,
            "cash_note": "Recorded income is not treated as cash on hand, restricted gifts are never counted as spendable, and "
                         "pledged sponsorship is not guaranteed. Only unrestricted money above the board's reserve floor is counted "
                         "as available for deposits. Financial feasibility is not board authorization."}
