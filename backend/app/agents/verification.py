"""Deterministic verification of a workflow's final result.

These checks run in code after the specialists finish and after the board
recommendation is drafted:

  * every dollar figure in the recommendation traces to a computed figure
  * no text claims that anything was sent, booked, paid, or submitted
  * every option the recommendation names was produced by the Events agent
  * every outreach draft from the run is still unsent
  * every saved lesson cites real event/reflection records
  * source provenance is labeled (verified / unverified / synthetic / internal)
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select

from ..db.models import OutreachDraft
from .contracts import AgentResult
from .outputs import BoardRecommendation

# A trailing sentence period is fine ("…total of $14,850.00."); a decimal continuation is not.
MONEY = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(k|K|thousand|million|M)?(?!\w)(?!\.\d)")
ACTION_CLAIMS = re.compile(
    r"\b(?:we|i|sam space|the agents?)\s+(?:have\s+|has\s+)?(?:already\s+)?(?:sent|emailed|booked|reserved|paid|submitted|signed|approved)\b"
    r"|\b(?:has|have)\s+been\s+(?:sent|booked|paid|submitted|approved|reserved)\b",
    re.IGNORECASE,
)


NEGATION = re.compile(r"\b(?:no|not|nothing|never|none|neither|nor|without|n't|cannot|can't|won't)\b|n't\b", re.IGNORECASE)


def action_claims(text: str) -> list[str]:
    """Claims that something was sent/booked/paid, ignoring negated ones
    ("nothing has been sent", "no venue has been booked")."""
    found = []
    for m in ACTION_CLAIMS.finditer(text):
        start = max(0, text.rfind(".", 0, m.start()) + 1, text.rfind("\n", 0, m.start()) + 1, m.start() - 60)
        if not NEGATION.search(text[start:m.start()]):
            found.append(m.group(0))
    return found


def dollar_amounts(text: str) -> list[float]:
    out = []
    for number, suffix in MONEY.findall(text):
        value = float(number.replace(",", ""))
        if suffix in ("k", "K", "thousand"):
            value *= 1_000
        elif suffix in ("million", "M"):
            value *= 1_000_000
        out.append(value)
    return out


def collect_numbers(obj: Any, out: set[float] | None = None) -> set[float]:
    out = set() if out is None else out
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            collect_numbers(v, out)
    return out


def is_supported(amount: float, allowed: set[float]) -> bool:
    for f in allowed:
        if abs(amount - f) <= max(1.0, 0.005 * abs(f)):
            return True
        for step in (100, 1000):  # "$17,500" or "$18K" quoting a computed $17,537.50 / $18,000
            if abs(f) >= step and abs(amount - round(f / step) * step) < 0.5:
                return True
    return False


def recommendation_text(rec: BoardRecommendation) -> str:
    parts = [rec.headline, rec.recommendation, *rec.rationale, *rec.risks, *rec.decisions_for_board, *rec.next_steps,
             *rec.lessons_applied, *rec.caveats]
    parts += [f"{o.title} {o.summary}" for o in rec.options]
    return "\n".join(parts)


def verify_workflow(db, run_id: int, results: dict[str, AgentResult], rec: BoardRecommendation | None,
                    allowed_figures: set[float], known_option_ids: set[str]) -> dict:
    checks: list[dict] = []

    def add(name: str, passed: bool | None, detail: str) -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})

    unsupported: list[float] = []
    if rec is not None:
        text = recommendation_text(rec)
        unsupported = sorted({a for a in dollar_amounts(text) if not is_supported(a, allowed_figures)})
        add("Every dollar figure traces to a calculation", not unsupported,
            "All figures match computed results." if not unsupported else
            "Not found in any calculation: " + ", ".join(f"${a:,.0f}" for a in unsupported))
        claims = action_claims(text)
        add("No claims that anything was sent, booked, or paid", not claims,
            "None found." if not claims else "Found: " + "; ".join(f"“{c}”" for c in claims[:3]))
        named = [o.option_id for o in rec.options if o.option_id]
        if named or known_option_ids:
            bad = [o for o in named if o not in known_option_ids]
            add("Options come from the Events agent's research", not bad,
                "All options are real candidates." if not bad else f"Unknown options: {', '.join(bad)}")

    with db.session() as s:
        statuses = s.scalars(select(OutreachDraft.status).where(OutreachDraft.run_id == run_id)).all()
    add("All outreach drafts remain unsent", all(st in ("draft", "reviewed", "archived") for st in statuses),
        f"{len(statuses)} draft(s) saved; none sent (SAM SPACE has no sending tool).")

    lessons = results.get("lessons")
    if lessons is not None and lessons.status == "completed":
        items = lessons.data.get("lessons", [])
        ok = all(l.get("event_ids") or l.get("reflection_ids") for l in items)
        add("Every lesson cites real events or reflections", ok, f"{len(items)} lesson(s) checked against the database.")

    counts: dict[str, int] = {}
    for r in results.values():
        for src in r.sources:
            counts[src.verification] = counts.get(src.verification, 0) + 1
    add("Sources are labeled by provenance", True,
        ", ".join(f"{n} {k}" for k, n in sorted(counts.items())) or "No external sources used.")

    failed = [r.agent.value for r in results.values() if r.status in ("failed", "stopped")]
    refused = [r.agent.value for r in results.values() if r.status == "refused"]
    add("Specialists finished", None if (failed or refused) else True,
        "All specialists completed." if not (failed or refused) else
        f"Failed: {', '.join(failed) or 'none'}; refused (permissions): {', '.join(refused) or 'none'}.")

    return {"passed": all(c["passed"] is not False for c in checks), "checks": checks, "unsupported_figures": unsupported}
