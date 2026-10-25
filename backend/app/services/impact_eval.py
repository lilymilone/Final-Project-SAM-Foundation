"""Impact & Evaluation: the fixed pilot task, the rubric, and every calculation, in plain Python.

Nothing here invents data. Time savings come only from recorded start and finish times (or minutes a participant
entered). Percentages exist only when the manual time is above zero. Annual projections multiply measured savings by
an assumption an administrator entered, and are labeled as projections. Practice and test records (is_synthetic) are
reported separately and never counted. With fewer than five real participants the result is called a small pilot.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from statistics import mean

SCENARIO = {
    "key": "gala_150_manhattan",
    "title": "Initial proposal for a 150-person Manhattan gala",
    "task": ("Prepare an initial fundraising event proposal for a 150-person gala in Manhattan, including three potential venues, "
             "a preliminary event budget, relevant lessons from past foundation events, and one draft venue inquiry email."),
    "deliverables": ["Three plausible venue options", "Venue and source research", "A preliminary financial model",
                     "Fundraising revenue and expense assumptions", "Important budget constraints", "Historical event insights",
                     "An editable outreach draft", "A final recommendation"],
    "instructions": [
        "Do the task your usual way first (web search, spreadsheets, past notes, email). Press Start when you begin and Finish when "
        "you would be comfortable sharing the draft with the board. If you can't do this part, mark it unavailable: that is fine.",
        "Then do the same task with SAM SPACE: press Start, run the plan in Event Studio (Manhattan Spring Gala), read and correct the "
        "packet as you normally would, and press Finish. Your review time counts, not only the agents' time.",
        "Link the agent run so the numbers come from the application's logs, then score both proposals with the same rubric.",
        "Answer the short feedback form. Negative answers are just as useful as positive ones and are kept exactly as written.",
    ],
    "data_note": "Use the same financial records and Our Legacy history for both attempts. Do not paste confidential donor details into notes.",
}

RUBRIC = [
    ("completeness", "Completeness of required deliverables", "Are all eight deliverables present?"),
    ("factual_accuracy", "Factual accuracy", "Are venue facts, dates, and figures correct?"),
    ("source_verification", "Source verification", "Can each venue fact be traced to a checked source?"),
    ("calculation_accuracy", "Financial calculation accuracy", "Do totals, net, and break-even add up?"),
    ("financial_feasibility", "Financial feasibility", "Does the plan respect the budget and cash limits?"),
    ("historical_integration", "Integration of historical knowledge", "Are lessons from past events used appropriately?"),
    ("actionability", "Actionability", "Could the board act on it next week?"),
    ("clarity", "Clarity", "Is it easy for a board member to read?"),
    ("mission_alignment", "Alignment with the foundation's mission", "Does it reflect kindness, belonging, and the cause?"),
]
RUBRIC_KEYS = [k for k, _, _ in RUBRIC]
SCALE = {0: "Missing", 1: "Weak", 2: "Adequate", 3: "Good", 4: "Excellent"}
CONDITIONS = ("manual", "assisted", "without_history", "with_history")

FEEDBACK_QUESTIONS = [
    ("ease_of_use", "How easy was SAM SPACE to use?", "scale"),
    ("usefulness", "How useful were its recommendations?", "scale"),
    ("source_confidence", "How confident were you in its research and sources?", "scale"),
    ("financial_helpful", "Did the financial analysis help you understand event affordability?", "yes_no_unsure"),
    ("history_useful", "Were the historical event insights useful?", "yes_no_unsure"),
    ("history_changed_strategy", "Did the historical insights change or improve the proposed event strategy?", "yes_no_unsure"),
    ("outreach_usable", "Was the generated outreach draft usable?", "yes_no_editing"),
    ("would_use_again", "Would you use SAM SPACE for future foundation activities?", "yes_no_maybe"),
    ("worked_well", "What worked particularly well?", "text"),
    ("confusing", "What was confusing or frustrating?", "text"),
    ("improve_first", "What feature should be improved first?", "text"),
    ("comments", "Any additional comments?", "text"),
]
MISSION_DIMENSIONS = [
    ("kindness", "Kindness"), ("community_connection", "Community connection"), ("belonging", "Belonging"), ("inclusion", "Inclusion"),
    ("accessibility", "Accessibility"), ("mental_health_awareness", "Mental health awareness"),
    ("eating_disorder_research", "Eating disorder research"), ("charitable_participation", "Meaningful charitable participation"),
]
PILOT_PENDING = "Pilot pending — no real-user evaluation data collected yet."


# ── Calculations ─────────────────────────────────────────────────────────────────────


def _utc(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)  # SQLite returns naive datetimes; they are stored in UTC


def minutes_between(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None or _utc(end) < _utc(start):
        return None
    return round((_utc(end) - _utc(start)).total_seconds() / 60, 1)


def minutes_saved(manual: float | None, assisted: float | None) -> float | None:
    """Manual minus assisted. Negative when SAM SPACE took longer. None when either time is missing."""
    if manual is None or assisted is None:
        return None
    return round(manual - assisted, 1)


def pct_reduction(manual: float | None, assisted: float | None) -> float | None:
    """(minutes saved / manual minutes) x 100, only when the manual time is above zero."""
    saved = minutes_saved(manual, assisted)
    if saved is None or manual is None or manual <= 0:
        return None
    return round(100 * saved / manual, 1)


def annual_hours(saved: float | None, tasks_per_year: float | None) -> float | None:
    """Measured minutes saved x assumed tasks per year / 60. A projection, not a measurement."""
    if saved is None or tasks_per_year is None or tasks_per_year < 0:
        return None
    return round(saved * tasks_per_year / 60, 1)


def evaluation_minutes(e) -> tuple[float | None, float | None]:
    """(manual, assisted) minutes for a completed attempt; anything else is missing, never zero."""
    manual = e.manual_minutes if e.manual_status == "completed" else None
    assisted = e.assisted_minutes if e.assisted_status == "completed" else None
    return manual, assisted


# ── Facts read from an agent run's logs ───────────────────────────────────────────────


def run_metrics(s, run_id: int) -> dict:
    """What the application itself recorded about a run (s: a SQLAlchemy Session): agents, venues, sources, finance,
    verification, history, drafts, model time and cost. Model execution time is reported separately from human time."""
    from sqlalchemy import select
    from ..db.models import AgentHandoff, AgentRun, ModelUsage, OutreachDraft, SourceRecordRow
    run = s.get(AgentRun, run_id)
    steps = s.scalars(select(AgentHandoff).where(AgentHandoff.run_id == run_id)).all()
    sources = s.scalars(select(SourceRecordRow).where(SourceRecordRow.run_id == run_id)).all()
    calls = s.scalars(select(ModelUsage).where(ModelUsage.run_id == run_id)).all()
    drafts = s.scalars(select(OutreachDraft).where(OutreachDraft.run_id == run_id)).all()
    r = run.result or {}
    ver = r.get("verification") or {}
    checks = {c["name"]: c["passed"] for c in ver.get("checks") or []}
    model = ((r.get("finance") or {}).get("model") or {})
    seen = {}
    for src in sources:
        if src.verification in ("verified", "unverified", "synthetic"):
            seen[src.url or src.source_key] = src.verification
    return {
        "run_id": run.id, "status": run.status, "workflow": run.workflow_type, "research_mode": run.research_mode,
        "agents_involved": sorted({st.to_agent for st in steps if st.to_agent != "orchestrator"}),
        "handoffs": len(steps),
        "venues_considered": len(r.get("venues") or []), "venues_shortlisted": len(r.get("shortlist") or []),
        "sources_verified_live": sum(1 for v in seen.values() if v == "verified"),
        "sources_synthetic": sum(1 for v in seen.values() if v == "synthetic"),
        "sources_unverified": sum(1 for v in seen.values() if v == "unverified"),
        "financial_model_complete": bool(model.get("complete")) if model else False,
        "affordability_verdict": (r.get("finance") or {}).get("verdict"),
        "figures_trace_to_calculations": checks.get("Every dollar figure traces to a calculation"),
        "unsupported_figures_flagged": len(ver.get("unsupported_figures") or []),
        "verification_passed": ver.get("passed"),
        "history_events_consulted": len(r.get("events_consulted") or []),
        "history_lessons": len(r.get("lessons") or []),
        "lessons_applied": len((r.get("recommendation") or {}).get("lessons_applied") or []),
        "outreach_drafts": len(drafts), "drafts_unsent": all(d.status == "draft" for d in drafts),
        "recommendation_written": bool(r.get("recommendation")),
        "model_execution_minutes": round((run.duration_ms or 0) / 60000, 1),
        "model_calls": len(calls), "models_used": sorted({c.selected_model for c in calls if c.selected_model}),
        "cost_usd": round(sum(c.estimated_cost_usd or 0 for c in calls), 4),
        "input_tokens": sum(c.input_tokens or 0 for c in calls), "output_tokens": sum(c.output_tokens or 0 for c in calls),
    }


# ── Dashboard ─────────────────────────────────────────────────────────────────────────


def _avg(values) -> float | None:
    vals = [v for v in values if v is not None]
    return round(mean(vals), 1) if vals else None


def summarize(evals: list, scores: list, tasks_per_year: float | None) -> dict:
    """Aggregates over submitted evaluations of one kind (real or synthetic). Every number names its basis."""
    done = [e for e in evals if e.status == "submitted"]
    pairs = [(m, a) for m, a in (evaluation_minutes(e) for e in done) if m is not None and a is not None]
    manual_avg = _avg(evaluation_minutes(e)[0] for e in done)
    assisted_avg = _avg(evaluation_minutes(e)[1] for e in done)
    paired_manual, paired_assisted = _avg(m for m, _ in pairs), _avg(a for _, a in pairs)
    saved = minutes_saved(paired_manual, paired_assisted)
    fb = [e.feedback for e in done if e.feedback]
    by_cond: dict[str, dict[str, list[int]]] = {}
    ids = {e.id for e in done}
    for sc in scores:
        if sc.evaluation_id in ids:
            by_cond.setdefault(sc.condition, {}).setdefault(sc.dimension, []).append(sc.score)
    rubric = {c: {d: _avg(v) for d, v in dims.items()} for c, dims in by_cond.items()}

    def tally(key):
        out: dict[str, int] = {}
        for f in fb:
            if f.get(key) is not None:
                out[str(f[key])] = out.get(str(f[key]), 0) + 1
        return out

    n = len(done)
    return {
        "completed_evaluations": n,
        "drafts_in_progress": sum(1 for e in evals if e.status != "submitted"),
        "sample_note": None if n == 0 else (f"Small pilot (n={n}): not statistically representative." if n < 5 else f"n={n} participants."),
        "time": {
            "manual_avg_minutes": manual_avg, "assisted_avg_minutes": assisted_avg,
            "paired_evaluations": len(pairs), "paired_manual_avg": paired_manual, "paired_assisted_avg": paired_assisted,
            "minutes_saved": saved, "pct_reduction": pct_reduction(paired_manual, paired_assisted),
            "manual_unavailable": sum(1 for e in done if e.manual_status == "unavailable"),
            "basis": "Observed: start-to-finish times recorded in the evaluation (assisted time includes reviewing and correcting the "
                     "AI's output). Minutes saved and the percentage use only evaluations with both times.",
        },
        "projection": {
            "tasks_per_year": tasks_per_year, "annual_hours_saved": annual_hours(saved, tasks_per_year),
            "basis": "Extrapolated: measured minutes saved x the administrator's assumed number of similar tasks per year / 60. "
                     "An assumption, not a measurement.",
        },
        "ratings": {k: _avg((f.get(k) for f in fb)) for k in ("ease_of_use", "usefulness", "source_confidence")},
        "answers": {k: tally(k) for k, _, kind in FEEDBACK_QUESTIONS if kind not in ("scale", "text")},
        "sources": {"manual_avg_verified": _avg(e.manual_verified_sources for e in done if e.manual_status == "completed"),
                    "assisted_avg_verified_live": _avg((e.run_metrics or {}).get("sources_verified_live") for e in done if e.run_metrics),
                    "assisted_avg_synthetic": _avg((e.run_metrics or {}).get("sources_synthetic") for e in done if e.run_metrics)},
        "financial_accuracy": {"manual_avg_score": (rubric.get("manual") or {}).get("calculation_accuracy"),
                               "assisted_avg_score": (rubric.get("assisted") or {}).get("calculation_accuracy"),
                               "assisted_participant_says_correct": sum(1 for e in done if e.calculations_correct == "yes"),
                               "assisted_runs_all_figures_traced": sum(1 for e in done if (e.run_metrics or {}).get("figures_trace_to_calculations"))},
        "rubric": rubric,
        "mission": {"advances_mission": tally_mission(done)},
    }


def tally_mission(done: list) -> dict:
    out: dict[str, int] = {}
    for e in done:
        v = (e.mission or {}).get("advances_mission")
        if v:
            out[v] = out.get(v, 0) + 1
    return out


def public_name(e, user_name: str | None) -> str:
    """Reports show the participant code unless the participant chose to be named AND allowed attribution."""
    if e.show_name_in_reports and e.attribution_permission and user_name:
        return f"{user_name} ({e.participant_role or 'board member'})"
    return f"{e.participant_code} ({e.participant_role or 'board member'})"


# ── Historical learning: what changed, dimension by dimension ─────────────────────────────

DIMENSIONS = [
    ("venue_selection", "Venue-selection criteria", ("venue", "room", "space", "capacity", "layout", "site", "floor", "hall")),
    ("budget", "Event budget recommendations", ("budget", "cost", "contingency", "price", "expense", "overrun", "deposit", "minimum", "cash")),
    ("logistics", "Logistics", ("logistic", "timeline", "schedule", "check-in", "setup", "set-up", "vendor", "printing", "deadline", "program",
                                "run-through", "draw")),
    ("volunteers", "Volunteer coordination", ("volunteer", "station", "brief", "roles", "lead ")),
    ("sponsorship", "Sponsorship strategy", ("sponsor", "in-kind", "donated", "underwrit")),
    ("community", "Community-building considerations", ("community", "welcome", "belong", "connection", "conversation", "first-time",
                                                         "neighborhood", "mission")),
    ("accessibility", "Accessibility and inclusion", ("accessib", "step-free", "entrance", "quiet", "wheelchair", "inclusi", "audib",
                                                      "microphone", "sound", "dietary")),
]
_STOP = set("that this with from have will were been their they them than then when what which while into also only more most "
            "past event events plan plans planning raffle gala lessons lesson record records board should could would about after "
            "before spring guest guests provide clarify cost costs venue venues option options budget proposed consider keep make "
            "other these those there where each such include including within without using use used based".split())


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z\-]{3,}", (text or "").lower()) if w not in _STOP}


def _clean(items) -> list[str]:
    seen, out = set(), []
    for x in items:
        x = " ".join(str(x or "").split())
        if x and x.lower() not in seen and not x.lower().startswith("no past-event lessons"):
            seen.add(x.lower())
            out.append(x)
    return out


def _statements(result: dict) -> list[str]:
    """Everything a run recommended: the recommendation, its options, the shortlist rationale, and the strategy."""
    rec = result.get("recommendation") or {}
    out = [rec.get("headline"), rec.get("recommendation")]
    for key in ("rationale", "risks", "decisions_for_board", "next_steps", "lessons_applied", "caveats"):
        out += [x for x in rec.get(key) or [] if isinstance(x, str)]
    out += [f"{o.get('title', '')}: {o.get('summary', '')}" for o in rec.get("options") or []]
    for sl in result.get("shortlist") or []:
        out += list(sl.get("lessons_applied") or []) + ([sl["rationale"]] if sl.get("rationale") else [])
    strat = result.get("events_strategy") or {}
    for key in ("fundraising_strategy", "logistics_notes"):
        v = strat.get(key)
        out += v if isinstance(v, list) else [v]
    return _clean(out)


def _attributed(result: dict, event_names: dict) -> list[str]:
    """Statements the agents themselves attribute to past events: the recommendation's and the shortlist's lessons_applied,
    plus any statement that names a recorded past event."""
    rec = result.get("recommendation") or {}
    out = list(rec.get("lessons_applied") or [])
    for sl in result.get("shortlist") or []:
        out += list(sl.get("lessons_applied") or [])
    names = [n.split(" (")[0].lower() for n in event_names.values() if n]
    out += [x for x in _statements(result) if any(n and n in x.lower() for n in names)]
    return _clean(out)


def _support(statement: str, lessons: list[dict], constraints: list[dict], event_names: dict) -> list[dict]:
    """The lessons a statement rests on: a lesson citing an event the statement names (with a shared word), or any lesson
    or history constraint sharing at least three meaningful words. Generic overlap does not count."""
    words, low = _words(statement), statement.lower()
    named = {i for i, n in event_names.items() if n and n.split(" (")[0].lower() in low}
    found = []
    for l in lessons:
        shared = words & _words(l.get("text", ""))
        cites_named = bool(named & set(l.get("event_ids", [])))
        if (cites_named and shared) or len(shared) >= 3:
            found.append({"kind": "lesson", "text": l["text"], "events": [event_names.get(i, f"Event #{i}") for i in l.get("event_ids", [])],
                          "event_ids": l.get("event_ids", []), "reflection_ids": l.get("reflection_ids", []), "shared_words": sorted(shared)[:6],
                          "_rank": len(shared) + (3 if cites_named else 0)})
    for c in constraints:
        shared = words & _words(c.get("detail", ""))
        if len(shared) >= 3:
            found.append({"kind": "history_constraint", "text": c.get("detail", ""), "name": c.get("name"), "shared_words": sorted(shared)[:6],
                          "_rank": len(shared)})
    found.sort(key=lambda f: -f.pop("_rank"))
    return found[:3]


def history_dimensions(without: dict, with_: dict, lessons: list[dict], constraints: list[dict], event_names: dict) -> list[dict]:
    """Per dimension: what each condition said, and which with-history statements the agents attributed to past events AND
    that rest on a specific lesson (shown). Other differences between the two runs are counted as possible model variation,
    never as improvements."""
    a_all, b_all = _statements(without), _statements(with_)
    b_hist = _attributed(with_, event_names)
    out = []
    for key, label, kws in DIMENSIONS:
        def hits(items):
            return [x for x in items if any(k in x.lower() for k in kws)]
        a, b = hits(a_all), hits(b_all)
        changed, unexplained = [], []
        for st in hits(b_hist):
            sup = _support(st, lessons, constraints, event_names)
            (changed if sup else unexplained).append({"statement": st, "supported_by": sup})
        hist_set = {x["statement"] for x in changed + unexplained}
        other = [x for x in b if x not in hist_set and not any(len(_words(x) & _words(y)) / max(1, len(_words(x) | _words(y))) >= 0.5 for y in a)]
        out.append({"key": key, "label": label, "without_history": a, "with_history": b,
                    "changed_by_history": changed, "different_without_specific_lesson": unexplained,
                    "other_differences": len(other),
                    "verdict": ("changed, with supporting lessons" if changed else
                                "different, but no specific lesson identified" if unexplained else
                                "no history-attributed change" if a or b else "not addressed by either")})
    return out


def numeric_changes(numbers: dict) -> list[dict]:
    """Budget figures from the experiment's own comparison (computed in code for both runs)."""
    rows = []
    for k in ("Projected total (USD)", "Upfront cash (USD)", "Contingency", "Revision rounds"):
        v = numbers.get(k) or {}
        rows.append({"measure": k, "without_history": v.get("without_history"), "with_history": v.get("with_history"),
                     "changed": v.get("without_history") != v.get("with_history")})
    return rows


def _fmt(v, unit: str = "") -> str:
    return "not available" if v is None else f"{v:,}{unit}" if isinstance(v, int) else f"{v:,.1f}{unit}" if isinstance(v, float) else str(v)


def bundle_markdown(b: dict) -> str:
    """Report-ready summary of the exported evidence. Missing data is named, never filled in."""
    r = b["real"]["summary"]
    t, pr = r["time"], r["projection"]
    L = ["# SAM SPACE impact evaluation: evidence summary", "", f"_Exported {b['exported_at'][:16]} UTC._", "",
         f"**Task:** {b['scenario']['task']}", ""]
    if b["pilot_pending"]:
        L += [f"> **{b['pilot_message']}**", ">", "> The framework below is ready; no real participant has submitted an evaluation, so there "
              "are no time-savings, rating, or feedback results to report.", ""]
    else:
        L += [f"**Completed real evaluations:** {r['completed_evaluations']}. {r['sample_note']}", "",
              "| Measure | Value | Basis |", "|---|---|---|",
              f"| Average manual time | {_fmt(t['manual_avg_minutes'], ' min')} | Observed |",
              f"| Average SAM SPACE time (incl. review) | {_fmt(t['assisted_avg_minutes'], ' min')} | Observed |",
              f"| Minutes saved (paired evaluations: {t['paired_evaluations']}) | {_fmt(t['minutes_saved'], ' min')} | Calculated |",
              f"| Percentage time reduction | {_fmt(t['pct_reduction'], '%')} | Calculated |",
              f"| Projected annual hours saved | {_fmt(pr['annual_hours_saved'], ' h')} | Extrapolated ({_fmt(pr['tasks_per_year'])} tasks/year, an assumption) |",
              f"| Average usefulness rating | {_fmt(r['ratings']['usefulness'], ' / 5')} | Participant feedback |", ""]
        L += ["## Feedback, as written", ""]
        for e in b["real"]["evaluations"]:
            f = e.get("feedback") or {}
            L.append(f"- **{e['display_name']}**, {e['task_date']}: ease {f.get('ease_of_use')}/5, usefulness {f.get('usefulness')}/5, "
                     f"sources {f.get('source_confidence')}/5; would use again: {f.get('would_use_again')}.")
            for k, label in (("worked_well", "Worked well"), ("confusing", "Confusing"), ("improve_first", "Improve first"), ("comments", "Comments")):
                if f.get(k):
                    L.append(f"  - {label}: “{f[k]}”")
        L.append("")
    L += ["## Calculations", ""] + [f"- **{k.replace('_', ' ')}:** {v}" for k, v in b["calculations"].items()] + [""]
    L += ["## Rubric (scored by people, same rubric for both proposals; 0 = missing … 4 = excellent)", ""]
    L += [f"- {x['label']}: {x['question']}" for x in b["rubric"]] + [""]
    for c in b["history_comparisons"]:
        s = c["summary"]
        ra, rb = c["runs"].get("without_history") or {}, c["runs"].get("with_history") or {}
        L += [f"## Historical-learning comparison #{c['id']}", "", f"**Request:** {c['request']}", "",
              f"Runs #{ra.get('run_id')} (without history) and #{rb.get('run_id')} (with history); models {ra.get('models')} / {rb.get('models')}; "
              f"cost ${(ra.get('usage') or {}).get('cost_usd', 0):.4f} / ${(rb.get('usage') or {}).get('cost_usd', 0):.4f}.", "",
              f"- Dimensions with a lesson-supported change: {s['dimensions_changed_with_support']} of {len(c['dimensions'])}",
              f"- History-attributed statements resting on a specific lesson: {s['unique_statements_changed']} (some touch several areas); "
              f"attributed to history but resting on no lesson: {s['statements_different_without_lesson']}; other wording differences "
              f"(possible run-to-run variation, not counted): {s['other_differences']}",
              f"- Budget numbers changed: {'yes' if s['budget_numbers_changed'] else 'no'}", "",
              "| Dimension | Verdict | Example change | Supporting lesson |", "|---|---|---|---|"]
        for d in c["dimensions"]:
            ex = d["changed_by_history"][0] if d["changed_by_history"] else None
            sup = (ex["supported_by"][0] if ex else None) or {}
            L.append(f"| {d['label']} | {d['verdict']} | {(ex['statement'][:140] if ex else '—').replace('|', '/')} | "
                     f"{(sup.get('text', '—')[:120]).replace('|', '/')}{' (' + ', '.join(sup.get('events', [])) + ')' if sup.get('events') else ''} |")
        hs = c.get("human_scores") or {}
        L += ["", "Human quality scores: " + (", ".join(f"{k}: {sum(v.values())}/{4 * len(v)}" for k, v in hs.items()) if hs else
                                              "not yet scored by a person."), "", c["method_note"], ""]
    syn = b["synthetic"]["summary"]
    L += ["## Practice and test records (not counted)", "", f"{syn['completed_evaluations']} submitted practice/test evaluation(s). "
          "They are kept apart from the results above and never appear in them.", ""]
    return "\n".join(L) + "\n"
