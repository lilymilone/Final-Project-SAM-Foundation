"""Partnership Opportunity Packet: assembled deterministically from a stored
partnership run (Mission Discovery -> selection -> Partnerships & Outreach).

Nothing here calls a model. It brings together the board recommendation,
every opportunity researched (selected and not selected, with reasons), the
four-part alignment for each, the unsent drafts, the sources with the dates
they were checked, the handoff trace, and token usage.
"""

from __future__ import annotations

from sqlalchemy import select

from ..db.models import AgentHandoff, AgentRun, ModelUsage, OutreachDraft, ResearchFinding, SourceRecordRow
from ..mission import PHILOSOPHY
from .opportunities import opportunity_out
from .packet import _money, _usage


def build_partnership_packet(db, run_id: int, organization_id: int) -> dict | None:
    with db.session() as s:
        run = s.get(AgentRun, run_id)
        if run is None or run.organization_id != organization_id or (run.result or {}).get("intent") != "partnership_outreach":
            return None
        steps = s.scalars(select(AgentHandoff).where(AgentHandoff.run_id == run_id).order_by(AgentHandoff.id)).all()
        calls = s.scalars(select(ModelUsage).where(ModelUsage.run_id == run_id).order_by(ModelUsage.id)).all()
        drafts = s.scalars(select(OutreachDraft).where(OutreachDraft.run_id == run_id).order_by(OutreachDraft.id)).all()
        source_rows = s.scalars(select(SourceRecordRow).where(SourceRecordRow.run_id == run_id).order_by(SourceRecordRow.id)).all()
        r = run.result or {}
        selection = r.get("selection") or {}
        ids = {o["id"] for o in selection.get("selected") or []} | {o["id"] for o in selection.get("excluded") or []}
        rows = {f.id: f for f in s.scalars(select(ResearchFinding).where(ResearchFinding.id.in_(ids),
                                                                        ResearchFinding.organization_id == organization_id)).all()}
        cards = {i: opportunity_out(f, include_notes=False) for i, f in rows.items()}

    selected = [{**cards.get(o["id"], o), "selection_reason": o.get("selection_reason")} for o in selection.get("selected") or []]
    excluded = [{**cards.get(o["id"], {}), "id": o["id"], "name": o["name"], "reason": o["reason"]} for o in selection.get("excluded") or []]
    trace = []
    for i, st in enumerate(steps, start=1):
        st_calls = [c for c in calls if c.handoff_id == st.id]
        trace.append({
            "n": i, "step_key": st.step_key, "from_agent": st.from_agent, "to_agent": st.to_agent, "kind": st.kind,
            "status": st.status, "objective": st.objective, "duration_ms": st.duration_ms, "summary": (st.result or {}).get("summary"),
            "constraints": (st.payload or {}).get("constraints", []), "models": sorted({c.selected_model for c in st_calls}),
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
    return {
        "run": {"id": run.id, "status": run.status, "research_mode": run.research_mode, "strategy": run.strategy,
                "started_at": run.started_at.isoformat(), "duration_ms": run.duration_ms, "error": run.error,
                "options": (run.plan or {}).get("options")},
        "request": run.request_text, "philosophy": PHILOSOPHY,
        "recommendation": r.get("recommendation"),
        "selected": selected, "excluded": excluded, "selection_warnings": selection.get("warnings") or [],
        "count_requested": selection.get("count_requested"),
        "unresolved": r.get("unresolved_conflicts") or [],
        "drafts": [{"id": d.id, "recipient": d.recipient_org, "draft_type": d.draft_type, "subject": d.subject, "purpose": d.purpose,
                    "foundation_background": d.foundation_background, "opportunity": d.opportunity, "body": d.body,
                    "next_step": d.next_step, "sources": d.sources or [], "review_notes": d.review_notes or [], "status": d.status,
                    "finding_id": d.finding_id, "is_synthetic_target": d.is_synthetic_target} for d in drafts],
        "sources": sources, "trace": trace, "usage": _usage(calls), "verification": r.get("verification"),
    }


def partnership_markdown(p: dict) -> str:
    rec = p.get("recommendation") or {}
    L = [f"# Partnership Opportunity Packet (workflow #{p['run']['id']})", "",
         f"> {p['philosophy']}", "",
         f"_Request:_ {p['request']}  ", f"_Research:_ {'live web' if p['run']['research_mode'] == 'live' else 'synthetic demo fixtures (not real organizations)'}  ",
         "_Nothing in this packet has been sent. Every draft waits for a person to review it and send it outside SAM SPACE._", "",
         "## 1. Board recommendation", "", f"**{rec.get('headline', '—')}**", "", rec.get("recommendation", "")]
    L += [f"- {x}" for x in rec.get("rationale") or []]
    L += ["", "**Decisions for the board**", ""] + [f"- {x}" for x in rec.get("decisions_for_board") or ["—"]]
    L += ["", "**Risks**", ""] + [f"- {x}" for x in rec.get("risks") or ["—"]]
    L += ["", "## 2. Selected opportunities", ""]
    for o in p["selected"]:
        a = o.get("alignment_detail") or {}
        L += [f"### {o['name']} ({o.get('fit') or '—'})", "",
              f"- Category: {o.get('category')} · Geography: {o.get('geography') or 'not stated'}",
              f"- Website: {o.get('website') or '—'} ({o.get('verification')}; last checked {(o.get('last_checked') or '—')[:10]})",
              f"- Purpose: {o.get('purpose') or '—'}",
              f"- Dates: {o.get('dates_text') or 'not stated'} ({o.get('date_status') or 'none'})",
              f"- Known costs: {o.get('known_costs') or 'not stated on the source'}",
              f"- Why selected: {o.get('selection_reason')}", f"- Fit: {o.get('fit_reason')}"]
        for part, label in (("charitable", "A. Charitable"), ("philosophical", "B. Philosophical")):
            for k, v in (a.get(part) or {}).items():
                L.append(f"- {label} · {k.replace('_', ' ')}: **{v['level']}**. {v['explanation']}")
        prac = a.get("practical") or {}
        if prac:
            L.append("- C. Practical: " + "; ".join(f"{k}: {prac[k]}" for k in ("geography", "cost", "volunteers", "timing", "operations") if prac.get(k)))
        ev = a.get("evidence") or {}
        if ev:
            L.append(f"- D. Evidence ({ev.get('reliability')}): verified {', '.join(ev.get('verified_items') or []) or '—'}; "
                     f"unconfirmed {', '.join(ev.get('unconfirmed_claims') or []) or '—'}")
        L += [f"- Missing: {m}" for m in o.get("missing_info") or []] + [f"- Warning: {w}" for w in o.get("warnings") or []]
        L += [f"- Next step: {o.get('next_step') or '—'}", ""]
    L += ["## 3. Considered but not selected", ""] + ([f"- {x['name']}: {x['reason']}" for x in p["excluded"]] or ["- None."])
    L += [f"- Note: {w}" for w in p["selection_warnings"]]
    L += ["", "## 4. Unsent outreach drafts", ""]
    for d in p["drafts"]:
        L += [f"### {d['draft_type'].replace('_', ' ').title()} to {d['recipient']} ({d['status']})", "", f"**Subject:** {d['subject']}  ",
              f"**Purpose:** {d.get('purpose') or '—'}  ", f"**Opportunity:** {d.get('opportunity') or '—'}  ",
              f"**Next step:** {d.get('next_step') or '—'}", "", d["body"], ""]
        L += ["Sources: " + "; ".join(f"{x.get('title')} ({x.get('url')}, {x.get('verification')})" for x in d["sources"]) if d["sources"] else "Sources: —"]
        L += [f"- Confirm before sending: {n}" for n in d["review_notes"]] + [""]
    L += ["## 5. Supporting sources", ""] + [f"- {x['title']}: {x['url'] or '—'} ({x['verification']}{', checked ' + x['retrieved_at'][:10] if x.get('retrieved_at') else ''})"
                                              for x in p["sources"]] + ["", "## 6. Agent handoff trace", "",
          "| # | From → To | Step | Status | Models | Tokens in/out | Cost |", "|---|---|---|---|---|---|---|"]
    for t in p["trace"]:
        L.append(f"| {t['n']} | {t['from_agent']} → {t['to_agent']} | {t['step_key']} | {t['status']} | {', '.join(t['models']) or 'code'} | "
                 f"{t['input_tokens']:,}/{t['output_tokens']:,} | ${t['cost_usd']:.4f} |")
    u = p["usage"]
    L += ["", "## 7. Token usage and cost", "", f"- Model calls: {u['model_calls']} · web searches: {u['web_search_calls']}",
          f"- Tokens: {u['input_tokens']:,} in ({u['cached_input_tokens']:,} cached) / {u['output_tokens']:,} out",
          f"- Estimated cost: {_money(u['cost_usd']) if u['cost_usd'] >= 1 else '$' + format(u['cost_usd'], '.4f')}", ""]
    if p.get("verification"):
        L += ["## Verification", ""] + [f"- [{'pass' if c['passed'] else 'FAIL' if c['passed'] is False else 'note'}] {c['name']}: {c['detail']}"
                                        for c in p["verification"]["checks"]]
    return "\n".join(L) + "\n"
