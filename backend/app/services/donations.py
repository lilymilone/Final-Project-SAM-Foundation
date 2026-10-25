"""Donation records: flags, summaries, CSV import/export, and compliance checks (all deterministic).

Rules that hold everywhere:
  * pledges are not received money: they are totaled separately and never counted as revenue
  * in-kind gifts carry a description, not a value assigned by the foundation
  * SAM SPACE never decides whether a gift is tax-deductible
  * donation records are reconciled against the ledger, never added to it (no double counting)
  * nothing here contacts a donor
"""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from datetime import date

from ..compliance import reference
from .documents import parse_amount

ACK_THRESHOLD_USD = 250.0
QUID_PRO_QUO_USD = 75.0
STALE_ACK_DAYS = 14
CONTRIBUTION_TYPES = ("monetary", "in_kind", "event_ticket", "sponsorship", "matching_gift")
PAYMENT_STATUSES = ("received", "pledged", "pending", "returned")
ACK_STATUSES = ("not_started", "prepared", "completed", "not_needed")
RESTRICTIONS = ("unrestricted", "temporarily_restricted", "permanently_restricted")
METHODS = ("check", "online", "wire", "cash", "card", "stock", "other")
EVENT_TYPES = ("event_ticket", "sponsorship")
MAX_IMPORT_ROWS = 2000


def donation_code(donation_id: int) -> str:
    return f"DON-{donation_id:05d}"


def duplicate_key(donor_name: str, received_on: str, amount: float) -> tuple:
    return (re.sub(r"\s+", " ", donor_name.strip().lower()), received_on, round(float(amount), 2))


def is_received(d: dict) -> bool:
    return (d.get("payment_status") or "received") == "received"


def counts_as_money(d: dict) -> bool:
    return is_received(d) and (d.get("contribution_type") or "monetary") != "in_kind"


def flags_for(d: dict, duplicates: dict[tuple, list[int]], today: date) -> list[dict]:
    """Recordkeeping and compliance flags for one gift. Each flag: {code, severity, text, ref}."""
    out = []
    ack = d.get("ack_status") or ("completed" if d.get("acknowledged") else "not_started")
    ctype = d.get("contribution_type") or "monetary"
    received = is_received(d)

    def add(code: str, severity: str, text: str, ref: str | None = None) -> None:
        out.append({"code": code, "severity": severity, "text": text, "ref": ref})

    if received and ctype != "in_kind" and d["amount_usd"] >= ACK_THRESHOLD_USD and ack not in ("completed", "not_needed"):
        add("ack_250", "high", "Gift of $250 or more without a completed written acknowledgment.", "irs-written-ack")
    gsv = d.get("goods_services_value_usd")
    if gsv and d["amount_usd"] > QUID_PRO_QUO_USD and ack != "completed":
        add("quid_pro_quo", "high", "The donor received goods or services (e.g. a dinner) for a payment over $75: a written "
                                    "disclosure statement with a good-faith estimate of their value is needed.", "irs-quid-pro-quo")
    if ctype == "in_kind":
        add("in_kind", "medium", "In-kind gift: the acknowledgment should describe the item without assigning it a value.", "irs-written-ack")
        if not d.get("in_kind_description"):
            add("in_kind_description", "medium", "In-kind gift without a description of what was given.")
    if received and ctype != "in_kind" and not d.get("method"):
        add("missing_method", "medium", "Payment method is not recorded.")
    if d.get("restriction") is None and ctype != "in_kind":
        add("restriction_undocumented", "low", "Whether the donor restricted this gift is not documented.")
    if (d.get("payment_status") or "received") == "pledged":
        add("pledge", "low", "Pledged, not received: it is not counted as money received.")
    if (d.get("payment_status") or "") == "returned":
        add("returned", "medium", "Payment was returned; confirm the record and any acknowledgment.")
    if not d.get("has_email"):
        add("no_email", "low", "No contact email (only needed if the acknowledgment goes by email).")
    if received and ack == "not_started" and d["amount_usd"] < ACK_THRESHOLD_USD:
        days = (today - date.fromisoformat(d["received_on"])).days
        if days > STALE_ACK_DAYS:
            add("ack_overdue", "low", f"Not yet thanked after {days} days.")
    others = [i for i in duplicates.get(duplicate_key(d["donor_name"], d["received_on"], d["amount_usd"]), []) if i != d["id"]]
    if others:
        add("possible_duplicate", "high", "Possible duplicate of " + ", ".join(donation_code(i) for i in others)
            + " (same donor, date, and amount). Only one should count.")
    if not d.get("campaign_id"):
        add("no_campaign", "low", "Not associated with a campaign or event.")
    return out


def duplicate_index(donations: list[dict]) -> dict[tuple, list[int]]:
    idx: dict[tuple, list[int]] = defaultdict(list)
    for d in donations:
        idx[duplicate_key(d["donor_name"], d["received_on"], d["amount_usd"])].append(d["id"])
    return idx


def summarize(donations: list[dict], campaigns: list[dict], ledger: list[dict], today: date | None = None) -> dict:
    """Totals and breakdowns. Duplicates are counted once; pledges and in-kind gifts are separate."""
    seen_keys: set[tuple] = set()
    counted = []
    for d in sorted(donations, key=lambda x: x["id"]):
        key = duplicate_key(d["donor_name"], d["received_on"], d["amount_usd"])
        if key in seen_keys:
            continue  # a possible duplicate never counts twice
        seen_keys.add(key)
        counted.append(d)
    money = [d for d in counted if counts_as_money(d)]
    pledged = [d for d in counted if d.get("payment_status") == "pledged"]
    in_kind = [d for d in counted if d.get("contribution_type") == "in_kind"]
    by_month: dict[str, float] = defaultdict(float)
    for d in money:
        by_month[d["received_on"][:7]] += d["amount_usd"]
    camp_rows = []
    for c in campaigns:
        rec = sum(d["amount_usd"] for d in money if d.get("campaign_id") == c["id"])
        pl = sum(d["amount_usd"] for d in pledged if d.get("campaign_id") == c["id"])
        camp_rows.append({**c, "received_usd": round(rec, 2), "pledged_usd": round(pl, 2),
                          "gifts": sum(1 for d in counted if d.get("campaign_id") == c["id"]),
                          "progress": round(rec / c["goal_usd"], 3) if c.get("goal_usd") else None})
    unassigned = sum(d["amount_usd"] for d in money if not d.get("campaign_id"))
    event_ids = {c["id"] for c in campaigns if c.get("kind") == "event"}
    event_related = [d for d in money if d.get("campaign_id") in event_ids or d.get("contribution_type") in EVENT_TYPES]
    ack = defaultdict(int)
    for d in counted:
        if is_received(d):
            ack[d.get("ack_status") or "not_started"] += 1
    restr = defaultdict(float)
    for d in money:
        restr[d.get("restriction") or "not_documented"] += d["amount_usd"]
    donor_ids = {d.get("donor_id") or d["donor_name"] for d in money}
    # Reconciliation: donation records vs the ledger's donation income, month by month. Shown, never added together.
    ledger_gifts: dict[str, float] = defaultdict(float)
    for r in ledger:
        if r["kind"] == "income" and re.search(r"donation|gift|contribution|individual", r["category"], re.IGNORECASE):
            ledger_gifts[r["period"]] += r["amount_usd"]
    months = sorted(set(by_month) & set(ledger_gifts))
    reconciliation = [{"period": m, "donation_records_usd": round(by_month[m], 2), "ledger_donations_usd": round(ledger_gifts[m], 2),
                       "difference_usd": round(by_month[m] - ledger_gifts[m], 2)} for m in months]
    total = sum(d["amount_usd"] for d in money)
    return {
        "received_usd": round(total, 2), "gifts_received": len(money), "donors": len(donor_ids),
        "average_gift_usd": round(total / len(money), 2) if money else None,
        "pledged_outstanding_usd": round(sum(d["amount_usd"] for d in pledged), 2), "pledges": len(pledged),
        "in_kind_gifts": len(in_kind), "event_related_usd": round(sum(d["amount_usd"] for d in event_related), 2),
        "unassigned_usd": round(unassigned, 2), "by_month": [{"period": p, "amount_usd": round(v, 2)} for p, v in sorted(by_month.items())],
        "by_campaign": camp_rows, "ack_status": dict(ack), "by_restriction": {k: round(v, 2) for k, v in restr.items()},
        "duplicates_excluded": len(donations) - len(counted), "reconciliation": reconciliation,
        "notes": ["Pledges are listed separately and never counted as received.",
                  "In-kind gifts are counted, not valued: the foundation does not assign them a dollar value.",
                  "Possible duplicates count once.",
                  "Donation records are reconciled against the financial ledger, never added to it."],
    }


# ── Compliance review (deterministic; each item cites a reference or goes to a professional) ──


def compliance_items(donations: list[dict], ledger: list[dict], locations: list[str], today: date | None = None) -> list[dict]:
    today = today or date.today()
    dupes = duplicate_index(donations)
    by_code: dict[str, list[dict]] = defaultdict(list)
    for d in donations:
        for f in flags_for(d, dupes, today):
            by_code[f["code"]].append(d)

    def item(key, title, detail, kind, refs, ids=(), professional=None):
        return {"key": key, "title": title, "detail": detail, "kind": kind, "professional": professional,
                "donation_ids": list(ids), "references": [r for r in (reference(x, today) for x in refs) if r]}

    items = []
    if by_code["ack_250"]:
        items.append(item("ack_250", "Written acknowledgments for gifts of $250 or more",
                          f"{len(by_code['ack_250'])} gift(s) of $250 or more have no completed acknowledgment. A donor needs one to "
                          "deduct the gift. SAM SPACE prepares drafts; a person sends them.", "verified_requirement",
                          ["irs-written-ack"], [d["id"] for d in by_code["ack_250"]]))
    if by_code["quid_pro_quo"]:
        items.append(item("quid_pro_quo", "Disclosure for gifts where the donor received something (over $75)",
                          f"{len(by_code['quid_pro_quo'])} payment(s), such as gala tickets, include goods or services. A disclosure "
                          "statement with a good-faith estimate of their value is required. The estimate itself should be "
                          "confirmed by your accountant.", "verified_requirement", ["irs-quid-pro-quo"],
                          [d["id"] for d in by_code["quid_pro_quo"]], "accountant"))
    if by_code["in_kind"]:
        items.append(item("in_kind", "In-kind gifts", f"{len(by_code['in_kind'])} in-kind gift(s). Acknowledge them by describing the "
                          "item, without stating a value. Valuing the gift is the donor's responsibility; ask your accountant about "
                          "any appraisal or reporting questions.", "verified_requirement", ["irs-written-ack"],
                          [d["id"] for d in by_code["in_kind"]], "accountant"))
    restricted = [d for d in donations if d.get("restriction") in ("temporarily_restricted", "permanently_restricted")]
    if restricted:
        items.append(item("restricted", "Donor-restricted gifts", f"{len(restricted)} gift(s) are restricted by the donor. They must be "
                          "used only for the stated purpose. How to track and report restricted funds is an accounting question.",
                          "needs_professional_review", [], [d["id"] for d in restricted], "accountant"))
    if by_code["pledge"]:
        items.append(item("pledges", "Pledges", f"{len(by_code['pledge'])} pledge(s) are recorded but not received. SAM SPACE never counts "
                          "them as revenue; how pledges are recorded in your books is a question for your accountant.",
                          "needs_professional_review", [], [d["id"] for d in by_code["pledge"]], "accountant"))
    income = sum(r["amount_usd"] for r in ledger if r["kind"] == "income" and (r.get("period_months") or 1) == 1)
    months = len({r["period"] for r in ledger if r["kind"] == "income" and (r.get("period_months") or 1) == 1})
    items.append(item("form_990", "Annual information return (Form 990 series)",
                      f"Which return the foundation files depends on its gross receipts and total assets for the tax year. SAM SPACE "
                      f"holds ${income:,.0f} of recorded income over {months} month(s), which is not a full tax year and not a "
                      "determination. Confirm the right form and deadline with your accountant.", "verified_requirement",
                      ["irs-990-series"], [], "accountant"))
    states = sorted({s for s in locations if s})
    refs = (["ny-charities-registration"] if "New York" in states else []) + (["ct-charities-registration"] if "Connecticut" in states else [])
    if states:
        items.append(item("state_registration", "State charitable solicitation registration",
                          f"The foundation's events and plans are in {', '.join(states)}. States where a charity solicits may require "
                          "registration and annual filings. Whether that applies, and whether the foundation is registered or exempt, "
                          "needs counsel.", "general_guidance", refs, [], "attorney"))
    incomplete = {d["id"] for code in ("missing_method", "in_kind_description", "restriction_undocumented") for d in by_code[code]}
    if incomplete or by_code["possible_duplicate"]:
        items.append(item("recordkeeping", "Recordkeeping", f"{len(incomplete)} record(s) are incomplete and "
                          f"{len(by_code['possible_duplicate'])} look like duplicates. Complete records make acknowledgments and "
                          "annual reporting easier.", "general_guidance", [], sorted(incomplete | {d["id"] for d in by_code["possible_duplicate"]})))
    return items


def state_of(location: str | None) -> str | None:
    low = (location or "").lower()
    if any(w in low for w in ("new york", "manhattan", "brooklyn", "queens", "nyc", ", ny")):
        return "New York"
    if any(w in low for w in ("connecticut", ", ct", "new haven", "greenwich", "hartford", "stamford")):
        return "Connecticut"
    return None


# ── CSV import and export ─────────────────────────────────────────────────────────

IMPORT_COLUMNS = ("donor_name", "donation_date", "amount_usd")


def _clean(text: str | None, limit: int) -> str:
    return (text or "").strip().lstrip("=+-@\t")[:limit]


def parse_donation_csv(text: str, campaigns_by_name: dict[str, int]) -> tuple[list[dict], list[str]]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    headers = {(h or "").strip().lower() for h in (reader.fieldnames or [])}
    if not set(IMPORT_COLUMNS) <= headers:
        return [], [f"The CSV needs these columns: {', '.join(IMPORT_COLUMNS)}."]
    rows, errors, seen = [], [], set()
    for line, raw in enumerate(reader, start=2):
        if len(rows) >= MAX_IMPORT_ROWS:
            errors.append(f"More than {MAX_IMPORT_ROWS} rows; split the file.")
            break
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items() if k is not None}
        if not any(r.values()):
            continue
        problems = []
        name = _clean(r.get("donor_name"), 200)
        amount = parse_amount(r.get("amount_usd"))
        try:
            received = date.fromisoformat(r.get("donation_date", ""))
        except ValueError:
            received = None
        ctype = (r.get("contribution_type") or "monetary").lower()
        payment = (r.get("payment_status") or "received").lower()
        ack = (r.get("ack_status") or "not_started").lower()
        restriction = (r.get("restriction") or "").lower().replace(" ", "_") or None
        method = (r.get("method") or "").lower() or None
        currency = (r.get("currency") or "USD").upper()
        campaign = r.get("campaign") or ""
        email = (r.get("donor_email") or "").strip() or None
        gsv = parse_amount(r.get("goods_services_value_usd")) if r.get("goods_services_value_usd") else None
        if not name:
            problems.append("donor_name is empty")
        if received is None:
            problems.append("donation_date must look like 2026-10-14")
        if amount is None or amount < 0:
            problems.append("amount_usd must be a positive number")
        if ctype not in CONTRIBUTION_TYPES:
            problems.append(f"contribution_type must be one of {', '.join(CONTRIBUTION_TYPES)}")
        if payment not in PAYMENT_STATUSES:
            problems.append(f"payment_status must be one of {', '.join(PAYMENT_STATUSES)}")
        if ack not in ACK_STATUSES:
            problems.append(f"ack_status must be one of {', '.join(ACK_STATUSES)}")
        if restriction and restriction not in RESTRICTIONS:
            problems.append(f"restriction must be one of {', '.join(RESTRICTIONS)} (or blank)")
        if method and method not in METHODS:
            problems.append(f"method must be one of {', '.join(METHODS)} (or blank)")
        if currency != "USD":
            problems.append("only USD is supported")
        if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            problems.append("donor_email is not a valid address")
        if campaign and campaign.lower() not in campaigns_by_name:
            problems.append(f"campaign “{campaign[:60]}” does not exist; create it first or leave it blank")
        if not problems:
            key = duplicate_key(name, received.isoformat(), amount)
            if key in seen:
                problems.append("the same donor, date, and amount appear earlier in this file")
            seen.add(key)
        if problems:
            errors.append(f"Row {line}: {'; '.join(problems)}")
            continue
        rows.append({"donor_name": name, "donor_email": email, "received_on": received, "amount_usd": round(amount, 2),
                     "currency": "USD", "contribution_type": ctype, "payment_status": payment, "ack_status": ack,
                     "restriction": restriction, "method": method, "campaign_id": campaigns_by_name.get(campaign.lower()) if campaign else None,
                     "notes": _clean(r.get("notes"), 500), "in_kind_description": _clean(r.get("in_kind_description"), 300) or None,
                     "goods_services_value_usd": gsv, "designation": _clean(r.get("designation"), 120) or "General fund", "row": line})
    if not rows and not errors:
        errors.append("The CSV has no data rows.")
    return rows, errors


EXPORT_COLUMNS = ("donation_id", "donor_id", "donor_name", "donation_date", "amount_usd", "currency", "contribution_type", "campaign",
                  "restriction", "designation", "payment_status", "ack_status", "method", "in_kind_description",
                  "goods_services_value_usd", "notes", "source", "is_demo", "created_at", "updated_at")


def _cell(value) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t") else text  # never export a spreadsheet formula


def export_csv(rows: list[dict]) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(EXPORT_COLUMNS)
    for r in rows:
        w.writerow([_cell(r.get(c)) for c in EXPORT_COLUMNS])
    return out.getvalue()
