"""Event Strategy Packet: assembled deterministically from a stored planning run.

Nothing here calls a model. The packet pulls the run's validated results,
handoffs, tool and model usage, sources, and drafts together into one
board-ready document. Finance sections are removed for roles without
financial access.
"""

from __future__ import annotations

from sqlalchemy import select

from ..db.models import AgentHandoff, AgentRun, HistoricalEvent, ModelUsage, OutreachDraft, SourceRecordRow

FINANCE_AGENT = "financial_analysis"


def _usage(calls: list[ModelUsage]) -> dict:
    by_agent: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    for c in calls:
        for bucket, key in ((by_agent, c.agent), (by_model, c.selected_model)):
            b = bucket.setdefault(key, {"calls": 0, "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
            b["calls"] += 1
            b["input_tokens"] += c.input_tokens or 0
            b["cached_input_tokens"] += c.cached_input_tokens or 0
            b["output_tokens"] += c.output_tokens or 0
            b["cost_usd"] = round(b["cost_usd"] + (c.estimated_cost_usd or 0), 6)
    return {
        "model_calls": len(calls),
        "input_tokens": sum(c.input_tokens or 0 for c in calls),
        "cached_input_tokens": sum(c.cached_input_tokens or 0 for c in calls),
        "output_tokens": sum(c.output_tokens or 0 for c in calls),
        "web_search_calls": sum(c.web_search_calls or 0 for c in calls),
        "cost_usd": round(sum(c.estimated_cost_usd or 0 for c in calls), 6),
        "by_agent": by_agent, "by_model": by_model,
    }


def build_packet(db, run_id: int, organization_id: int, can_see_finance: bool) -> dict | None:
    with db.session() as s:
        run = s.get(AgentRun, run_id)
        if run is None or run.organization_id != organization_id:
            return None
        steps = s.scalars(select(AgentHandoff).where(AgentHandoff.run_id == run_id).order_by(AgentHandoff.id)).all()
        calls = s.scalars(select(ModelUsage).where(ModelUsage.run_id == run_id).order_by(ModelUsage.id)).all()
        drafts = s.scalars(select(OutreachDraft).where(OutreachDraft.run_id == run_id).order_by(OutreachDraft.id)).all()
        source_rows = s.scalars(select(SourceRecordRow).where(SourceRecordRow.run_id == run_id).order_by(SourceRecordRow.id)).all()
        event_names = dict(s.execute(select(HistoricalEvent.id, HistoricalEvent.name).where(HistoricalEvent.organization_id == organization_id)).all())
    r = run.result or {}
    shortlist_rank = {x["option_id"].split(":")[0]: x["rank"] for x in r.get("shortlist") or []}

    venues = []
    for v in r.get("venues") or []:
        caps = v.get("capacity") or {}
        venues.append({
            "name": v.get("name"), "location": v.get("address") or v.get("neighborhood"), "website": v.get("website"),
            "website_status": v.get("website_status") or v.get("verification"), "verified_at": v.get("verified_at"),
            "source_url": v.get("source_url"), "verification": v.get("verification"),
            "capacity": caps, "capacity_status": v.get("capacity_status"), "capacity_quote": v.get("capacity_quote"),
            "pricing_status": v.get("pricing_status"),
            "pricing": v.get("pricing_quote") if v.get("pricing_status") == "published" else "Quote required",
            "amenities": v.get("amenities") or [], "restrictions": v.get("restrictions") or [], "notes": v.get("notes"),
            "shortlist_rank": shortlist_rank.get(v.get("venue_key")),
        })

    lessons = []
    lesson_step = next((st for st in steps if st.step_key == "lessons" and st.result), None)
    for l in ((lesson_step.result or {}).get("data") or {}).get("lessons", []) if lesson_step else []:
        lessons.append({**l, "events": [{"id": i, "name": event_names.get(i, f"Event #{i}")} for i in l.get("event_ids", [])]})
    evaluation = r.get("evaluation") or {}
    history_checks = [{**h, "events": [{"id": i, "name": event_names.get(i, f"Event #{i}")} for i in h.get("event_ids", [])]}
                      for h in evaluation.get("history_checks", [])]

    finance = r.get("finance") or None
    warnings = []
    if finance and can_see_finance:
        for c in (finance.get("affordability") or {}).get("checks", []):
            if c["passed"] is not True:
                warnings.append({"level": "conflict" if c["passed"] is False and c["kind"] in
                                 ("over_budget_limit", "upfront_cash_exceeds_available", "negative_net", "contingency_below_lesson") else
                                 ("warning" if c["passed"] is False else "unknown"), "text": f"{c['name']}: {c['detail']}"})
        for m in (finance.get("model") or {}).get("missing_inputs", []):
            warnings.append({"level": "unknown", "text": f"Missing input: {m}. Revenue and break-even stay incomplete until it is provided."})
    for c in r.get("unresolved_conflicts") or []:
        if c.get("source") != "finance" or can_see_finance:
            warnings.append({"level": "conflict", "text": f"Unresolved after the revision limit: {c['detail']}"})
    for v in venues:
        if v["pricing_status"] != "published":
            warnings.append({"level": "warning", "text": f"{v['name']}: Quote required. Any venue figure in the model is a hypothetical estimate."})

    trace = []
    for i, st in enumerate(steps, start=1):
        st_calls = [c for c in calls if c.handoff_id == st.id]
        hidden = st.to_agent == FINANCE_AGENT and not can_see_finance
        trace.append({
            "n": i, "step_key": st.step_key, "from_agent": st.from_agent, "to_agent": st.to_agent, "kind": st.kind,
            "revision_round": st.revision_round, "status": st.status, "objective": st.objective, "duration_ms": st.duration_ms,
            "summary": None if hidden else (st.result or {}).get("summary"),
            "models": sorted({c.selected_model for c in st_calls}),
            "input_tokens": sum(c.input_tokens or 0 for c in st_calls), "output_tokens": sum(c.output_tokens or 0 for c in st_calls),
            "cost_usd": round(sum(c.estimated_cost_usd or 0 for c in st_calls), 6),
        })

    seen, sources = set(), []
    for src in source_rows:
        key = src.url or src.source_key
        if key in seen or src.verification == "internal":
            continue
        seen.add(key)
        sources.append({"title": src.title, "url": src.url, "verification": src.verification, "http_status": src.http_status,
                        "retrieved_at": src.retrieved_at, "note": src.note})

    packet = {
        "run": {"id": run.id, "status": run.status, "research_mode": run.research_mode, "strategy": run.strategy,
                "started_at": run.started_at.isoformat(), "duration_ms": run.duration_ms, "event_plan_id": run.event_plan_id,
                "options": (run.plan or {}).get("options"), "error": run.error},
        "overview": {"event": r.get("event"), "request": run.request_text, "interpreted": r.get("analysis"), "routing": r.get("routing")},
        "recommendation": r.get("recommendation"),
        "venues": venues,
        "shortlist": r.get("shortlist") or [],
        "sources": sources,
        "lessons": lessons,
        "history_checks": history_checks,
        "revision": {"original": r.get("original_plan"), "revised": r.get("revised_plan"), "reasons": r.get("revision_reasons") or [],
                     "history": r.get("revision_history") or []},
        "budget_warnings": warnings,
        "drafts": [{"id": d.id, "recipient": d.recipient_org or d.recipient_name, "subject": d.subject, "body": d.body, "status": d.status,
                    "draft_type": d.draft_type, "is_synthetic_target": d.is_synthetic_target} for d in drafts if d.draft_type != "donor_acknowledgment"],
        "trace": trace,
        "usage": _usage(calls),
        "verification": r.get("verification"),
        "finance_visible": can_see_finance,
    }
    if can_see_finance and finance:
        packet["financial_model"] = finance.get("model")
        packet["affordability"] = finance.get("affordability")
        packet["position"] = finance.get("position")
    elif not can_see_finance:
        for key in ("original", "revised"):
            if packet["revision"][key]:
                packet["revision"][key] = {k: v for k, v in packet["revision"][key].items()
                                           if k in ("round", "venue", "event_format", "pricing_status", "changes_from_previous", "rationale", "conflict_sources")}
        packet["revision"]["history"] = []
        packet["revision"]["reasons"] = [x for x in packet["revision"]["reasons"] if x.get("source") != "finance"]
    return packet


def _money(x) -> str:
    return "—" if x is None else f"${x:,.0f}"


def packet_markdown(p: dict) -> str:
    ev = (p["overview"].get("event") or {})
    rec = p.get("recommendation") or {}
    L = [f"# Event Strategy Packet: {ev.get('name', 'Event')}", "",
         f"_Workflow #{p['run']['id']} · {p['run']['status']} · research: {p['run']['research_mode']} · {p['run']['started_at'][:10]}_", "",
         "## 1. Event overview", "",
         f"- **Event:** {ev.get('event_type')} · {ev.get('attendance')} guests · {ev.get('city')}",
         f"- **Date:** {ev.get('target_date') or 'not set'}{(' to ' + ev['date_end']) if ev.get('date_end') else ''}",
         f"- **Ticket price:** {_money(ev.get('ticket_price_usd'))} · **Fundraising target:** {_money(ev.get('fundraising_goal_usd'))} · "
         f"**Maximum planning budget:** {_money(ev.get('budget_limit_usd'))}",
         f"- **Board instructions:** {ev.get('instructions') or '—'}", "",
         "## 2. Board recommendation", "", f"**{rec.get('headline', '—')}**", "", rec.get("recommendation", ""), ""]
    for title, key in (("Decisions for the board", "decisions_for_board"), ("Risks", "risks"), ("Next steps", "next_steps"), ("Caveats", "caveats")):
        if rec.get(key):
            L += [f"**{title}**", ""] + [f"- {x}" for x in rec[key]] + [""]
    rv = p["revision"]
    L += ["## 3. Original and revised strategy", ""]
    if rv.get("original"):
        o = rv["original"]
        L.append(f"- **Original:** {o['venue']} ({o['event_format'].replace('_', ' ')})"
                 + (f": projected {_money(o.get('total_usd'))}, verdict {o.get('verdict')}" if "total_usd" in o else ""))
    if rv.get("revised"):
        n = rv["revised"]
        L.append(f"- **Revised:** {n['venue']} ({n['event_format'].replace('_', ' ')})"
                 + (f": projected {_money(n.get('total_usd'))}, verdict {n.get('verdict')}" if "total_usd" in n else ""))
        if n.get("changes_from_previous"):
            L.append(f"- **What changed:** {n['changes_from_previous']}")
    else:
        L.append("- No revision was needed.")
    if rv.get("reasons"):
        L += ["", "**Why the plan was revised**", ""] + [f"- ({x['source']}) {x['detail']}" for x in rv["reasons"]]
    L += ["", "## 4. Venue shortlist and research", "", "| Venue | Location | Capacity | Pricing | Website | Checked |", "|---|---|---|---|---|---|"]
    for v in p["venues"]:
        cap = ", ".join(f"{k.replace('_', ' ')} {n}" for k, n in (v["capacity"] or {}).items()) or "not published"
        if v["capacity_status"] not in ("published", None):
            cap += f" ({v['capacity_status']})"
        rank = f" (#{v['shortlist_rank']})" if v.get("shortlist_rank") else ""
        L.append(f"| {v['name']}{rank} | {v['location'] or '—'} | {cap} | {v['pricing']} | {v['website'] or '—'} ({v['website_status']}) | {(v['verified_at'] or '—')[:10]} |")
    if p.get("financial_model"):
        m = p["financial_model"]
        L += ["", "## 5. Preliminary financial model", "", "| Cost | Amount | Basis |", "|---|---|---|"]
        L += [f"| {x['category']} | {_money(x['amount_usd'])} | {x['basis']} |" for x in m["lines"]]
        L += [f"| Contingency ({m['contingency_pct']:.0%}) | {_money(m['contingency_usd'])} | |", f"| **Total** | **{_money(m['total_cost_usd'])}** | |",
              "", f"Upfront cash before the event: {_money(m['upfront_cash_usd'])}. Break-even attendance: {m['break_even_attendance'] if m['break_even_attendance'] is not None else (m.get('break_even_note') or '—')}.",
              "", "| Scenario | Attendance | Tickets | Sponsorship | Donations | Revenue | Net | vs target |", "|---|---|---|---|---|---|---|---|"]
        for name, sc in m["scenarios"].items():
            L.append(f"| {name} | {sc['attendance']} | {_money(sc['ticket_revenue_usd'])} | {_money(sc['sponsorship_revenue_usd'])} | "
                     f"{_money(sc['donations_usd'])} | {_money(sc['total_revenue_usd'])} | {_money(sc['net_usd'])} | {_money(sc['vs_target_usd'])} |")
        L += ["", "**Assumptions**", ""] + [f"- {k.replace('_', ' ')}: {a['value'] if a['value'] is not None else 'missing'} ({a['kind']}: {a['basis']})"
                                            for k, a in m["assumptions"].items()]
        if p.get("affordability"):
            L += ["", f"_{p['affordability']['cash_note']}_"]
    L += ["", "## 6. Budget warnings", ""] + ([f"- **{w['level']}:** {w['text']}" for w in p["budget_warnings"]] or ["- None."])
    L += ["", "## 7. Lessons from past events", ""]
    for l in p["lessons"]:
        L.append(f"- ({l['kind'].replace('_', ' ')}) {l['text']} [evidence: {', '.join(e['name'] for e in l['events']) or 'board reflections'}]")
    for h in p["history_checks"]:
        L.append(f"- **History check, {'passed' if h['passed'] else 'failed'}:** {h['name']}. {h['detail']}")
    if not p["lessons"]:
        L.append("- Historical lessons were not used in this run.")
    L += ["", "## 8. Unsent outreach drafts", ""]
    for d in p["drafts"]:
        L += [f"### To {d['recipient']}: {d['subject']}", "", d["body"], ""]
    L += ["## 9. Supporting sources", ""] + [f"- {s['title']}: {s['url'] or '—'} ({s['verification']}{', checked ' + s['retrieved_at'][:10] if s.get('retrieved_at') else ''})"
                                           for s in p["sources"]]
    L += ["", "## 10. Agent handoff trace", "", "| # | From → To | Step | Status | Models | Tokens in/out | Cost |", "|---|---|---|---|---|---|---|"]
    L += [f"| {t['n']} | {t['from_agent']} → {t['to_agent']} | {t['step_key']} | {t['status']} | {', '.join(t['models']) or '—'} | "
          f"{t['input_tokens']:,}/{t['output_tokens']:,} | ${t['cost_usd']:.4f} |" for t in p["trace"]]
    u = p["usage"]
    L += ["", "## 11. Token usage and cost", "", f"- Model calls: {u['model_calls']} · web searches: {u['web_search_calls']}",
          f"- Tokens: {u['input_tokens']:,} in ({u['cached_input_tokens']:,} cached) · {u['output_tokens']:,} out",
          f"- Cost at official list prices: ${u['cost_usd']:.4f}", ""]
    if p.get("verification"):
        L += ["## Verification", ""] + [f"- [{'pass' if c['passed'] else 'FAIL' if c['passed'] is False else 'note'}] {c['name']}: {c['detail']}"
                                        for c in p["verification"]["checks"]]
    return "\n".join(L) + "\n"
