"""Our Legacy imports: check the AI's candidate extraction against its sources, then apply the board's decision.

validate_extraction() is deterministic. A value survives only if the words it cites really appear in the cited source
(a board member's description or an uploaded file) and, for figures and dates, the number itself appears in those
words. Photos are never a source. When two sources give different figures for the same field, the field is left
empty and the conflict goes to the board. Lessons are labeled AI interpretations; everything else that survives is a
source fact (with its quote). Missing information is listed, never filled in.

apply_decision() writes an approved preview to historical_events. It refuses to overwrite a value that is already
recorded unless the board member confirmed that field, and it refuses to save while a conflict is unresolved.
"""

from __future__ import annotations

import re
from datetime import date

FIGURE_LABELS = {
    "attendance": "Attendance", "fundraising_goal_usd": "Fundraising goal", "funds_raised_usd": "Revenue (funds raised)",
    "total_cost_usd": "Expenses", "net_proceeds_usd": "Net proceeds (as reported)", "sponsorship_usd": "Sponsorship",
    "volunteers_count": "Volunteers", "planned_budget_usd": "Planned budget",
}
TEXT_LABELS = {"name": "Event title", "event_date": "Date", "event_year": "Year", "location": "Location", "venue": "Venue",
               "event_type": "Type", "summary": "Description", "sponsorship_info": "Sponsors"}
LIST_LABELS = {"positive_outcomes": "What worked", "problems_encountered": "What did not work", "lessons_learned": "Lessons learned"}
STORED_FIGURES = ("attendance", "fundraising_goal_usd", "funds_raised_usd", "total_cost_usd", "sponsorship_usd", "volunteers_count",
                  "planned_budget_usd")
INT_FIELDS = ("attendance", "volunteers_count")
KEY_FIELDS = (("name", "Event title"), ("event_date", "Date or year"), ("location", "Location"), ("attendance", "Attendance"),
              ("fundraising_goal_usd", "Fundraising goal"), ("funds_raised_usd", "Revenue (funds raised)"), ("total_cost_usd", "Expenses"))
MONTHS = {m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august", "september",
                                      "october", "november", "december"), 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
_NUM = re.compile(r"\$?\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?\s*([kK]\b|[mM]\b|thousand\b|million\b)?")


def norm(text: str | None) -> str:
    t = str(text or "").lower()
    for a, b in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'), ("–", "-"), ("—", "-"), ("|", " "), ("…", " ... ")):
        t = t.replace(a, b)
    return " ".join(t.split())


def quote_in(quote: str | None, source: str) -> bool:
    """Every part of the quote (split on ellipses) appears in the source, after normalizing spacing and punctuation marks."""
    q = norm(quote).strip(' ."\'')
    if len(q) < 3:
        return False
    src = norm(source)
    parts = [p.strip(' ."\'') for p in q.split("...") if p.strip(' ."\'')]
    return bool(parts) and all(p in src for p in parts)


def numbers_in(text: str) -> list[float]:
    out = []
    for m in _NUM.finditer(text or ""):
        whole, frac, scale = m.group(1).replace(",", ""), m.group(2), (m.group(3) or "").lower()
        v = float(whole + ("." + frac if frac else ""))
        v *= 1000 if scale in ("k", "thousand") else 1_000_000 if scale in ("m", "million") else 1
        out.append(v)
    return out


def parse_date(text: str | None) -> tuple[date | None, int | None, str | None]:
    """(full date, year, note). Only what the words say: a month and year give a year plus a note, never a guessed day."""
    t = norm(text)
    if not t:
        return None, None, None
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3])), int(m[1]), None
        except ValueError:
            pass
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", t)
    if m:
        try:
            return date(int(m[3]), int(m[1]), int(m[2])), int(m[3]), None
        except ValueError:
            pass
    month = next((MONTHS[w] for w in re.findall(r"[a-z]+", t) if w in MONTHS), None)
    year_m = re.search(r"\b(19[5-9]\d|20\d{2})\b", t)
    year = int(year_m[1]) if year_m else None
    if month and year:
        day = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b(?!\d)", t.replace(str(year), " "))
        if day and 1 <= int(day[1]) <= 31:
            try:
                return date(year, month, int(day[1])), year, None
            except ValueError:
                pass
        return None, year, f"Month given ({t}), but not the day."
    if year:
        return None, year, None
    return None, None, None


def _label(source_id: str, sources: dict) -> str:
    return sources.get(source_id, {}).get("label", source_id)


def validate_extraction(out, sources: dict[str, dict]) -> dict:
    """out: EventExtraction. sources: {source_id: {"text", "label", "kind"}} with the same (screened) text the model saw."""
    dropped: list[str] = []
    fields: dict[str, dict] = {}

    def check(source_id: str | None, quote: str | None, what: str) -> bool:
        src = sources.get(source_id or "")
        if src is None:
            dropped.append(f"{what}: cited a source that does not exist, so it was left out.")
            return False
        if src["kind"] == "image":
            dropped.append(f"{what}: photos are never used as a source, so it was left out.")
            return False
        if not quote_in(quote, src["text"]):
            dropped.append(f"{what}: the quoted words are not in {src['label']}, so it was left out.")
            return False
        return True

    def text_field(key: str, sv, origin: str = "source_fact", must_contain: bool = True) -> None:
        label = TEXT_LABELS[key]
        if sv is None or not (sv.value or "").strip():
            return
        if not check(sv.source_id, sv.quote, f"{label} “{sv.value[:60]}”"):
            return
        if must_contain and norm(sv.value) not in norm(sv.quote):
            if key in ("name", "location", "venue"):  # a name or place must be the source's own words, never a guess
                dropped.append(f"{label} “{sv.value[:60]}”: those words are not in the quote, so it was left out.")
                return
            origin = "ai_interpretation"  # a reworded type is an interpretation, shown as one
        fields[key] = {"value": sv.value.strip()[:200 if key != "summary" else 2000], "origin": origin, "source_id": sv.source_id,
                       "source_label": _label(sv.source_id, sources), "quote": (sv.quote or "").strip()[:400]}

    text_field("name", out.title)
    text_field("location", out.location)
    text_field("venue", out.venue)
    text_field("event_type", out.event_type)
    text_field("summary", out.description, origin="ai_interpretation", must_contain=False)

    if out.date and (out.date.value or "").strip() and check(out.date.source_id, out.date.quote, f"Date “{out.date.value[:40]}”"):
        d, year, note = parse_date(out.date.value)
        if year is None or str(year) not in (out.date.quote or ""):
            dropped.append(f"Date “{out.date.value[:40]}”: the year is not in the quoted words, so it was left out.")
        else:
            base = {"origin": "source_fact", "source_id": out.date.source_id, "source_label": _label(out.date.source_id, sources),
                    "quote": out.date.quote.strip()[:400]}
            if d is not None:
                fields["event_date"] = {**base, "value": d.isoformat()}
            fields["event_year"] = {**base, "value": year, "note": note}

    # Figures: keep only numbers that are in their quote; group by field; disagreement -> conflict for the board.
    by_field: dict[str, list[dict]] = {}
    for f in out.figures:
        what = f"{FIGURE_LABELS[f.field]} {f.value:,.0f}"
        if f.value < 0 or f.value > 100_000_000:
            dropped.append(f"{what}: outside any plausible range, so it was left out.")
            continue
        if not check(f.source_id, f.quote, what):
            continue
        if not any(abs(n - f.value) < 0.5 for n in numbers_in(f.quote)):
            dropped.append(f"{what}: that number is not in the quoted words, so it was left out.")
            continue
        by_field.setdefault(f.field, []).append({"value": float(f.value), "source_id": f.source_id, "source_label": _label(f.source_id, sources),
                                                 "quote": f.quote.strip()[:400]})
    conflicts, warnings = [], []
    for key, items in by_field.items():
        distinct = sorted({round(i["value"], 2) for i in items})
        if len(distinct) == 1:
            v = distinct[0]
            fields[key] = {"value": int(v) if key in INT_FIELDS else v, "origin": "source_fact", "source_id": items[0]["source_id"],
                           "source_label": items[0]["source_label"], "quote": items[0]["quote"],
                           "also_in": [i["source_label"] for i in items[1:] if i["source_id"] != items[0]["source_id"]]}
        else:
            conflicts.append({"field": key, "label": FIGURE_LABELS[key], "values": items,
                              "detail": f"The sources give different {FIGURE_LABELS[key].lower()} figures: "
                                        + "; ".join(f"{i['value']:,.0f} ({i['source_label']})" for i in items) + ". Choose one or leave it blank."})
    net = fields.pop("net_proceeds_usd", None)
    raised, cost = fields.get("funds_raised_usd"), fields.get("total_cost_usd")
    if net and raised and cost and abs(net["value"] - (raised["value"] - cost["value"])) > 1:
        warnings.append(f"The reported net proceeds (${net['value']:,.0f}, {net['source_label']}) do not equal revenue minus expenses "
                        f"(${raised['value'] - cost['value']:,.0f}). SAM SPACE always computes net from revenue and expenses; check both figures.")
    elif net and not (raised and cost):
        warnings.append(f"Net proceeds of ${net['value']:,.0f} are reported ({net['source_label']}), but SAM SPACE stores revenue and expenses "
                        "and computes net from them. Add both if you know them.")
    if any(c["field"] == "net_proceeds_usd" for c in conflicts):
        conflicts = [c for c in conflicts if c["field"] != "net_proceeds_usd"]
        warnings.append("The sources report different net proceeds. Net is computed from revenue and expenses, so check those figures.")

    def points(items, origin: str, label: str) -> list[dict]:
        kept = []
        for p in items or []:
            if p.text.strip() and check(p.source_id, p.quote, f"{label} “{p.text[:50]}”"):
                kept.append({"text": p.text.strip()[:400], "origin": origin, "source_id": p.source_id,
                             "source_label": _label(p.source_id, sources), "quote": p.quote.strip()[:400]})
        return kept

    lists = {"positive_outcomes": points(out.what_worked, "source_fact", "What worked"),
             "problems_encountered": points(out.what_did_not_work, "source_fact", "What did not work"),
             "lessons_learned": points(out.lessons_learned, "ai_interpretation", "Lesson")}
    sponsors = points(out.sponsors, "source_fact", "Sponsor")
    if sponsors:
        fields["sponsorship_info"] = {"value": "; ".join(s["text"] for s in sponsors)[:2000], "origin": "source_fact",
                                      "source_id": sponsors[0]["source_id"], "source_label": sponsors[0]["source_label"],
                                      "quote": " / ".join(s["quote"] for s in sponsors)[:400]}
    conflict_fields = {c["field"] for c in conflicts}
    missing = [label for key, label in KEY_FIELDS
               if key not in fields and key not in conflict_fields and not (key == "event_date" and "event_year" in fields)]
    return {"summary": out.summary, "fields": fields, "lists": lists, "conflicts": conflicts, "warnings": warnings,
            "missing": missing, "ai_noted_missing": [m for m in out.missing_information if m.strip()][:10], "dropped": dropped}


# ── Applying the board's decision ───────────────────────────────────────────────────────

EDITABLE = ("name", "event_date", "event_year", "location", "venue", "event_type", "summary", "attendance", "fundraising_goal_usd",
            "funds_raised_usd", "total_cost_usd", "sponsorship_usd", "sponsorship_info", "volunteers_count", "planned_budget_usd",
            "positive_outcomes", "problems_encountered", "lessons_learned")


def candidate_values(extraction: dict) -> dict:
    """The preview's starting values (what the board sees before editing)."""
    vals = {k: v["value"] for k, v in (extraction.get("fields") or {}).items() if k in EDITABLE}
    for key, items in (extraction.get("lists") or {}).items():
        if items:
            vals[key] = "\n".join(f"- {i['text']}" for i in items)
    return vals


def _same(a, b) -> bool:
    if a in (None, "") and b in (None, ""):
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 0.005
    return norm(str(a)) == norm(str(b))


class DecisionError(ValueError):
    def __init__(self, status: int, message: str, details: list | None = None):
        super().__init__(message)
        self.status, self.details = status, details or []


def plan_decision(extraction: dict, final: dict, existing: dict | None, resolved: set[str], confirmed: set[str]) -> dict:
    """Check the board's decision and work out provenance. Raises DecisionError(409) when a conflict is unresolved or a
    recorded value would be overwritten without confirmation."""
    unresolved = [c for c in extraction.get("conflicts") or [] if c["field"] not in resolved]
    if unresolved:
        raise DecisionError(409, "Some sources disagree. Choose a value (or leave it blank) for each conflict before saving.",
                            [{"field": c["field"], "label": c["label"], "values": [v["value"] for v in c["values"]]} for c in unresolved])
    if existing is not None:
        overwrites = [{"field": k, "label": {**TEXT_LABELS, **FIGURE_LABELS, **LIST_LABELS}.get(k, k), "current": existing.get(k), "proposed": v}
                      for k, v in final.items() if existing.get(k) not in (None, "") and not _same(existing.get(k), v) and k not in confirmed]
        if overwrites:
            raise DecisionError(409, "This would change values already recorded for the event. Confirm each change to continue.", overwrites)
    cand = candidate_values(extraction)
    fields = extraction.get("fields") or {}
    lists = extraction.get("lists") or {}
    provenance, edits = {}, {}
    for key, value in final.items():
        if value in (None, ""):
            continue
        if key in cand and _same(cand[key], value):
            if key in lists:
                origins = {i["origin"] for i in lists[key]}
                provenance[key] = {"origin": "ai_interpretation" if "ai_interpretation" in origins else "source_fact",
                                   "sources": sorted({i["source_label"] for i in lists[key]}),
                                   "source_ids": sorted({i["source_id"] for i in lists[key]}),
                                   "quotes": [i["quote"] for i in lists[key]][:6]}
            else:
                f = fields[key]
                provenance[key] = {"origin": f["origin"], "sources": [f["source_label"]] + list(f.get("also_in") or []),
                                   "source_ids": [f["source_id"]], "quotes": [f["quote"]]}
        else:
            conflict = next((c for c in extraction.get("conflicts") or [] if c["field"] == key), None)
            chosen = next((v for v in (conflict or {}).get("values", []) if _same(v["value"], value)), None) if conflict else None
            if chosen:
                provenance[key] = {"origin": "board_choice", "sources": [chosen["source_label"]], "source_ids": [chosen["source_id"]],
                                   "quotes": [chosen["quote"]], "note": "Chosen by the board between conflicting sources."}
            else:
                provenance[key] = {"origin": "board_entered" if key not in cand else "board_edited", "sources": [], "source_ids": [],
                                   "quotes": []}
            if key in cand:
                edits[key] = {"candidate": cand[key], "final": value}
    return {"provenance": provenance, "edits": edits}
