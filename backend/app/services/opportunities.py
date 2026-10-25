"""Opportunities found by Mission Discovery: serialization, de-duplication, and
the Orchestrator's deterministic candidate selection.

Selection is code, not a model: it ranks by the explicit fit rubric
(mission.FIT_RUBRIC), then by how well the source was checked, and it never
selects an opportunity the board dismissed. Every choice and every exclusion
gets a stated reason that appears in the partnership packet.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from ..db.models import ResearchFinding

FIT_ORDER = {"Strong fit": 0, "Possible fit": 1, "Needs research": 2, "Weak fit": 3}
SELECTABLE = ("Strong fit", "Possible fit")
VERIFICATION_ORDER = {"verified": 0, "synthetic": 0, "unverified": 1, "unreachable": 2}
COUNT_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "a couple": 2, "a few": 3, "several": 4}
MAX_SELECT = 5


def domain(url: str | None) -> str | None:
    if not url:
        return None
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host or None


def norm_name(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def requested_count(text: str, default: int = 3) -> int:
    """'Find three organizations…' -> 3. Bounded to MAX_SELECT."""
    low = text.lower()
    m = re.search(r"\b(\d{1,2})\s+(?:organi[sz]ations|orgs|partners|groups|nonprofits|opportunities|candidates|sponsors)", low)
    if m:
        return max(1, min(MAX_SELECT, int(m.group(1))))
    for word, n in COUNT_WORDS.items():
        if re.search(rf"\b{word}\b\s+(?:\w+\s+){{0,2}}(?:organi[sz]ations|orgs|partners|groups|nonprofits|opportunities|candidates|sponsors)", low):
            return n
    return default


def opportunity_out(f: ResearchFinding, include_notes: bool = True) -> dict:
    status = f.status or ("saved" if f.saved else "new")
    out = {
        "id": f.id, "run_id": f.run_id, "name": f.name or f.title, "title": f.title, "category": f.category,
        "geography": f.geography, "purpose": f.purpose or f.summary, "summary": f.summary, "activities": f.activities or [],
        "website": f.website or f.source_url, "source_url": f.source_url, "source_title": f.source_title,
        "verification": f.verification_status, "dates_text": f.dates_text or f.published, "date_status": f.date_status,
        "partnership_types": f.partnership_types or [], "contribution_ways": f.contribution_ways or [],
        "known_costs": f.known_costs, "missing_info": f.missing_info or [], "next_step": f.next_step,
        "alignment": f.alignment, "alignment_detail": f.alignment_detail, "fit": f.fit, "fit_reason": f.fit_reason,
        "warnings": f.warnings or [], "injection_flagged": bool(f.injection_flags), "uncertainty": f.uncertainty,
        "is_synthetic": bool(f.is_synthetic), "status": status, "saved": status == "saved", "board_category": f.board_category,
        "research_requested": bool(f.research_requested),
        "last_checked": f.last_checked.isoformat() if f.last_checked else None,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }
    if include_notes:
        out["notes"] = f.notes
    return out


def select_candidates(findings: list[dict], count: int) -> dict:
    """Pick up to `count` opportunities for outreach, with a reason for every decision."""
    def rank(f: dict) -> tuple:
        return (FIT_ORDER.get(f.get("fit") or "", 9), VERIFICATION_ORDER.get(f.get("verification") or "", 3),
                1 if f.get("date_status") == "conflicting" else 0, 1 if f.get("injection_flagged") else 0,
                len(f.get("missing_info") or []))

    selected, excluded = [], []
    for f in sorted(findings, key=rank):
        name = f.get("name") or f.get("title")
        if f.get("status") == "dismissed":
            excluded.append({"id": f["id"], "name": name, "reason": "Dismissed by the board."})
        elif f.get("fit") not in SELECTABLE:
            excluded.append({"id": f["id"], "name": name, "reason": f"{f.get('fit') or 'No fit'}: {f.get('fit_reason') or 'not enough evidence'}"})
        elif f.get("verification") in ("unverified", "unreachable"):
            excluded.append({"id": f["id"], "name": name, "reason": "Its source could not be verified, so there is nothing reliable to draft from."})
        elif len(selected) >= count:
            excluded.append({"id": f["id"], "name": name,
                             "reason": f"Ranked below the {count} requested. {f.get('fit')}: {f.get('fit_reason') or ''}".strip()})
        else:
            why = [f.get("fit") or ""]
            why.append("source checked" if f.get("verification") == "verified" else "synthetic demo source")
            if f.get("date_status") == "conflicting":
                why.append("dates conflict, so the draft asks to confirm them")
            if f.get("injection_flagged"):
                why.append("its page contained instruction-like text that was removed; review with care")
            selected.append({**f, "selection_reason": "; ".join(w for w in why if w)})
    warnings = []
    if len(selected) < count:
        warnings.append(f"Only {len(selected)} of the {count} requested opportunities met the selection bar "
                        "(Strong or Possible fit, with a checked source). Nothing was padded or invented.")
    return {"selected": selected, "excluded": excluded, "warnings": warnings, "count_requested": count}
