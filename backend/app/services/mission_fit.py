"""Deterministic mission-fit rubric (see mission.FIT_RUBRIC).

The model gives qualitative evidence levels (strong / partial / unclear /
none) with an explanation for each, and code turns them into a fit label.
There is no numeric score, and philosophy criteria never lower a clinical
research opportunity: charitable alignment alone can earn "Strong fit".
"""

from __future__ import annotations

ORDER = {"strong": 3, "partial": 2, "unclear": 1, "none": 0}


def best_charitable_level(charitable: dict) -> str:
    levels = [v.get("level", "unclear") for v in charitable.values() if isinstance(v, dict)]
    return max(levels, key=lambda lv: ORDER.get(lv, 0)) if levels else "unclear"


def fit_label(*, charitable: dict, verification: str, blockers: list[str], purpose_known: bool) -> tuple[str, str]:
    """Return (label, reason). verification: verified | unverified | unreachable | synthetic."""
    best = best_charitable_level(charitable)
    if verification == "unreachable" or not purpose_known:
        return "Needs research", "The source could not be reached or the organization's purpose is unclear."
    if best == "strong" and verification in ("verified", "synthetic") and not blockers:
        return "Strong fit", "Strong alignment with a purpose area, a checked source, and no blocking feasibility issue."
    if best in ("strong", "partial"):
        why = []
        if best == "partial":
            why.append("alignment is partial")
        if verification not in ("verified", "synthetic"):
            why.append("the source is not verified")
        if blockers:
            why.append("feasibility issues: " + "; ".join(blockers[:2]))
        return "Possible fit", "Aligned, but " + ", ".join(why) + "."
    return "Weak fit", "The sources show no more than an unclear connection to the foundation's purpose areas."
