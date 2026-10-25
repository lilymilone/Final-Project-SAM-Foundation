"""Deterministic comparison of two workflow runs (e.g. without vs. with history).

Everything here is read from stored run results and the model_usage table.
No model is involved, so the comparison shows exactly what differed: numbers,
choices, constraints, and which recommendation lines appear in one run but
not the other.
"""

from __future__ import annotations

import re

from sqlalchemy import func, select

from ..db.models import AgentHandoff, AgentRun, ModelUsage


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s%$.]", "", text.lower())).strip()


def list_diff(a: list[str] | None, b: list[str] | None) -> dict:
    a, b = a or [], b or []
    na, nb = {_norm(x): x for x in a}, {_norm(x): x for x in b}
    return {"only_without": [na[k] for k in na if k not in nb], "only_with": [nb[k] for k in nb if k not in na],
            "in_both": [na[k] for k in na if k in nb]}


def run_snapshot(db, run_id: int) -> dict:
    with db.session() as s:
        run = s.get(AgentRun, run_id)
        usage = s.execute(select(
            func.count(ModelUsage.id), func.coalesce(func.sum(ModelUsage.input_tokens), 0),
            func.coalesce(func.sum(ModelUsage.cached_input_tokens), 0), func.coalesce(func.sum(ModelUsage.output_tokens), 0),
            func.coalesce(func.sum(ModelUsage.web_search_calls), 0), func.coalesce(func.sum(ModelUsage.estimated_cost_usd), 0.0),
        ).where(ModelUsage.run_id == run_id)).one()
        steps = s.scalars(select(AgentHandoff.step_key).where(AgentHandoff.run_id == run_id).order_by(AgentHandoff.id)).all()
        per_agent = s.execute(select(ModelUsage.agent, func.count(ModelUsage.id), func.coalesce(func.sum(ModelUsage.estimated_cost_usd), 0.0))
                              .where(ModelUsage.run_id == run_id).group_by(ModelUsage.agent)).all()
    r = run.result or {}
    finance = r.get("finance") or {}
    budget = finance.get("model") or {}
    rec = r.get("recommendation") or {}
    history = r.get("revision_history") or []
    strategy = r.get("events_strategy") or {}
    return {
        "run_id": run.id, "status": run.status, "use_history": (r.get("options") or {}).get("use_history"),
        "duration_s": round((run.duration_ms or 0) / 1000, 1),
        "usage": {"model_calls": usage[0], "input_tokens": usage[1], "cached_input_tokens": usage[2], "output_tokens": usage[3],
                  "web_search_calls": usage[4], "cost_usd": round(float(usage[5]), 6),
                  "by_agent": {a: {"calls": n, "cost_usd": round(float(c), 6)} for a, n, c in per_agent}},
        "steps": list(steps),
        "first_choice": {k: history[0].get(k) for k in ("venue", "event_format", "total_usd", "verdict")} if history else None,
        "final_choice": {"venue": finance.get("venue"), "event_format": finance.get("event_format"), "total_usd": budget.get("total_cost_usd"),
                         "upfront_cash_usd": budget.get("upfront_cash_usd"), "contingency_pct": budget.get("contingency_pct"),
                         "verdict": finance.get("verdict")},
        "revisions": max(0, len(history) - 1),
        "history_constraints": [c.get("detail") for c in r.get("history_constraints") or []],
        "lessons_used": len(r.get("lessons") or []),
        "headline": rec.get("headline"),
        "recommendation": rec.get("recommendation"),
        "lessons_applied": rec.get("lessons_applied") or [],
        "fundraising_strategy": strategy.get("fundraising_strategy") or [],
        "logistics_notes": strategy.get("logistics_notes") or [],
        "risks": rec.get("risks") or [],
        "decisions_for_board": rec.get("decisions_for_board") or [],
        "next_steps": rec.get("next_steps") or [],
        "verification_passed": (r.get("verification") or {}).get("passed"),
    }


def _delta(a, b):
    return round(b - a, 6) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None


def compare_runs(without: dict, with_: dict) -> dict:
    fa, fb = without["final_choice"], with_["final_choice"]
    numbers = {}
    for label, va, vb in [
        ("Projected total (USD)", fa.get("total_usd"), fb.get("total_usd")),
        ("Upfront cash (USD)", fa.get("upfront_cash_usd"), fb.get("upfront_cash_usd")),
        ("Contingency", fa.get("contingency_pct"), fb.get("contingency_pct")),
        ("Revision rounds", without["revisions"], with_["revisions"]),
        ("Historical constraints given to Events", len(without["history_constraints"]), len(with_["history_constraints"])),
        ("Lessons applied in the recommendation", len(without["lessons_applied"]), len(with_["lessons_applied"])),
        ("Model calls", without["usage"]["model_calls"], with_["usage"]["model_calls"]),
        ("Input tokens", without["usage"]["input_tokens"], with_["usage"]["input_tokens"]),
        ("Output tokens", without["usage"]["output_tokens"], with_["usage"]["output_tokens"]),
        ("Cost (USD)", without["usage"]["cost_usd"], with_["usage"]["cost_usd"]),
        ("Duration (s)", without["duration_s"], with_["duration_s"]),
    ]:
        numbers[label] = {"without_history": va, "with_history": vb, "delta": _delta(va, vb)}

    changes = []
    if (fa.get("venue"), fa.get("event_format")) != (fb.get("venue"), fb.get("event_format")):
        changes.append(f"Final venue changed: {fa.get('venue')} ({fa.get('event_format')}) → {fb.get('venue')} ({fb.get('event_format')}).")
    else:
        changes.append(f"Final venue unchanged: {fb.get('venue')} ({fb.get('event_format')}).")
    if fa.get("contingency_pct") != fb.get("contingency_pct") and fb.get("contingency_pct") is not None and fa.get("contingency_pct") is not None:
        changes.append(f"Contingency changed from {fa['contingency_pct']:.0%} to {fb['contingency_pct']:.0%}, "
                       f"moving the projected total from ${fa.get('total_usd') or 0:,.0f} to ${fb.get('total_usd') or 0:,.0f}.")
    if fa.get("verdict") != fb.get("verdict"):
        changes.append(f"Finance verdict changed: {fa.get('verdict')} → {fb.get('verdict')}.")
    if without.get("first_choice") and with_.get("first_choice") and without["first_choice"]["venue"] != with_["first_choice"]["venue"]:
        changes.append(f"First shortlist choice changed: {without['first_choice']['venue']} → {with_['first_choice']['venue']}.")
    if with_["history_constraints"]:
        changes.append(f"With history, Event Intelligence gave the Events agent {len(with_['history_constraints'])} evidence-backed constraint(s).")
    changes.append(f"Extra cost of consulting history: ${with_['usage']['cost_usd'] - without['usage']['cost_usd']:+.4f} "
                   f"({with_['usage']['model_calls'] - without['usage']['model_calls']:+d} model calls).")

    return {
        "summary_of_changes": changes,
        "numbers": numbers,
        "history_constraints": with_["history_constraints"],
        "lessons_applied": list_diff(without["lessons_applied"], with_["lessons_applied"]),
        "fundraising_strategy": list_diff(without["fundraising_strategy"], with_["fundraising_strategy"]),
        "logistics_notes": list_diff(without["logistics_notes"], with_["logistics_notes"]),
        "risks": list_diff(without["risks"], with_["risks"]),
        "decisions_for_board": list_diff(without["decisions_for_board"], with_["decisions_for_board"]),
        "next_steps": list_diff(without["next_steps"], with_["next_steps"]),
        "headlines": {"without_history": without["headline"], "with_history": with_["headline"]},
        "recommendations": {"without_history": without["recommendation"], "with_history": with_["recommendation"]},
        "runs": {"without_history": without, "with_history": with_},
        "note": "Both runs used the same request, event plan, research data, and model strategy. Only the Event Intelligence "
                "step differs. Model outputs vary between runs, so some text differences are wording, not substance.",
    }


def _fmt_delta(label: str, delta: float | None) -> str:
    if delta is None:
        return "—"
    if "Contingency" in label:
        return format(delta, "+.0%")
    if "Cost" in label:
        return format(delta, "+,.4f")
    return format(delta, "+,.1f")


def comparison_markdown(exp: dict) -> str:
    c = exp["comparison"]
    lines = [f"# Evidence: planning without vs. with historical insights (experiment #{exp['id']})", "",
             f"**Request:** {exp['request']}  ", f"**Research data:** {exp['research_mode']} · runs #{exp['run_a_id']} (without history) "
             f"and #{exp['run_b_id']} (with history) · {exp['created_at'][:10]}", "", "## What changed", ""]
    lines += [f"- {x}" for x in c["summary_of_changes"]]
    lines += ["", "## Side by side", "", "| Measure | Without history | With history | Change |", "|---|---|---|---|"]
    for label, v in c["numbers"].items():
        def fmt(x):
            if x is None:
                return "—"
            if "Contingency" in label:
                return f"{x:.0%}"
            if "USD" in label:
                return f"${x:,.4f}" if "Cost" in label else f"${x:,.0f}"
            return f"{x:,}" if isinstance(x, int) else f"{x}"
        lines.append(f"| {label} | {fmt(v['without_history'])} | {fmt(v['with_history'])} | {_fmt_delta(label, v['delta'])} |")
    if c["history_constraints"]:
        lines += ["", "## Constraints Event Intelligence passed to the Events agent", ""] + [f"- {x}" for x in c["history_constraints"]]
    for key, title in [("lessons_applied", "Lessons applied in the recommendation"), ("fundraising_strategy", "Fundraising strategy"),
                       ("logistics_notes", "Logistics notes"), ("risks", "Risks"), ("decisions_for_board", "Decisions for the board"),
                       ("next_steps", "Next steps")]:
        d = c[key]
        if d["only_with"] or d["only_without"]:
            lines += ["", f"## {title}", ""]
            lines += [f"- **Only with history:** {x}" for x in d["only_with"]]
            lines += [f"- **Only without history:** {x}" for x in d["only_without"]]
    lines += ["", "## Headlines", "", f"- Without history: {c['headlines']['without_history']}", f"- With history: {c['headlines']['with_history']}",
              "", "## Recommendations", "", f"**Without history.** {c['recommendations']['without_history']}", "",
              f"**With history.** {c['recommendations']['with_history']}", "", f"_{c['note']}_", ""]
    return "\n".join(lines)
