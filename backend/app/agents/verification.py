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


# Outreach may never invent a relationship or commit the foundation to anything.
RELATIONSHIP_CLAIMS = re.compile(
    r"\b(?:our|the)\s+(?:long[- ]?standing|longtime|ongoing|existing|continued|past|previous)\s+(?:partnership|relationship|collaboration|support)\b"
    r"|\b(?:as|like)\s+(?:we|i)\s+(?:discussed|mentioned|agreed)\b|\bfollowing (?:up on )?our (?:conversation|call|meeting)\b"
    r"|\b(?:we|i)\s+(?:have|'ve)\s+(?:long\s+)?(?:worked|partnered|collaborated)\s+with\b"
    r"|\bthank you (?:again )?for your (?:continued|ongoing|past|generous) support\b"
    r"|\b(?:we|i)\s+(?:recently\s+)?(?:met|spoke)\s+(?:with\s+)?(?:you|your team)\b"
    r"|\byour (?:past|previous|continued) (?:gift|donation|support|sponsorship) (?:to|of) (?:us|our)\b",
    re.IGNORECASE,
)
COMMITMENT_CLAIMS = re.compile(
    r"\b(?:we|the foundation)\s+(?:will|commit to|pledge to|guarantee to|promise to|are committing to|have committed to)\s+"
    r"(?:donate|fund|sponsor|pay|provide|contribute|give|cover|underwrite|grant)\b"
    r"|\b(?:we|the foundation)\s+(?:pledge|guarantee|promise)\b"
    r"|\b(?:we are|we're) pleased to confirm\b|\bthis (?:letter|email|message) confirms\b",
    re.IGNORECASE,
)


def outreach_violations(text: str, allowed_amounts: set[float] | None = None) -> list[str]:
    """Reasons a draft must not be saved: claims of actions taken, invented
    relationships, commitments, or dollar amounts that are not in the research."""
    problems = [f"claims an action was taken (“{c}”)" for c in action_claims(text)]
    problems += [f"implies a relationship that does not exist (“{m.group(0)}”)" for m in RELATIONSHIP_CLAIMS.finditer(text)]
    problems += [f"commits the foundation (“{m.group(0)}”)" for m in COMMITMENT_CLAIMS.finditer(text)]
    if allowed_amounts is not None:
        stray = [a for a in dollar_amounts(text) if a not in allowed_amounts]
        if stray:
            problems.append("mentions dollar amounts that are not in the research (" + ", ".join(f"${a:,.0f}" for a in stray) + ")")
    return problems


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


def collect_amounts(obj: Any, out: set[float] | None = None) -> set[float]:
    """Numbers, plus dollar amounts written inside strings (e.g. a published "$150 table fee")."""
    out = collect_numbers(obj, out)
    if isinstance(obj, str):
        out.update(dollar_amounts(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_amounts(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            collect_amounts(v, out)
    return out


def is_supported(amount: float, allowed: set[float]) -> bool:
    """Quoted amounts carry no sign ("a deficit of $1,870" quotes a computed -1,870), so compare magnitudes."""
    amount = abs(amount)
    for f in {abs(x) for x in allowed}:
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
        drafts = s.execute(select(OutreachDraft.status, OutreachDraft.finding_id, OutreachDraft.sources)
                           .where(OutreachDraft.run_id == run_id)).all()
    statuses = [d[0] for d in drafts]
    add("All outreach drafts remain unsent", all(st in ("draft", "reviewed", "archived") for st in statuses),
        f"{len(statuses)} draft(s) saved; none sent (SAM SPACE has no sending tool).")
    research_drafts = [d for d in drafts if d[1] is not None]
    if research_drafts:
        uncited = [d for d in research_drafts if not d[2]]
        add("Every partnership draft carries the sources it was written from", not uncited,
            f"{len(research_drafts) - len(uncited)} of {len(research_drafts)} drafts link to their research sources.")
    selection = results.get("select")
    if selection is not None and selection.status == "completed":
        chosen = selection.data.get("selected", [])
        bad = [c["name"] for c in chosen if c.get("verification") not in ("verified", "synthetic")]
        add("Selected opportunities have checked sources", not bad,
            f"{len(chosen)} selected, all with checked sources." if not bad else "Unchecked: " + ", ".join(bad))

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
