"""Every tool the agents can use, bound to one run.

Each tool does one narrow thing and returns a ToolResult. The allow-lists in
agents/registry.py decide which agent may call which tool. The permission
column decides which board roles may trigger it. Sensitive tools log counts,
never contents.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

from sqlalchemy import or_, select

from ..agents.contracts import SourceRecord, ToolResult
from ..core.permissions import Permission
from ..db.models import (
    BoardReflection,
    Campaign,
    Donation,
    EventPlan,
    ExtractedFigure,
    FinancialDocument,
    FinancialRecord,
    HistoricalEvent,
    HistoricalLesson,
    OutreachDraft,
    ResearchFinding,
    User,
    VenueCandidate,
)
from ..research import fixtures
from ..safety.policy import sanitize_untrusted, scrub_outbound_query
from ..services import opportunities as opp
from ..services import calculators as calc
from ..services import documents as docs
from ..services.finance_dashboard import build_dashboard
from ..services import event_model as em
from . import web
from .registry import ToolKind, ToolRegistry, ToolSpec

MISSION_TERMS = {
    "eating_disorders": ("eating disorder", "anorexia", "bulimia", "binge", "arfid", "body image", "recovery", "neda", "anad"),
    "mental_health": ("mental health", "suicide", "anxiety", "depression", "wellbeing", "well-being", "counsel", "therapy", "nami", "crisis"),
    "community": ("community", "peer support", "families", "campus", "student", "volunteer", "walk", "awareness"),
}
NYC_ALIASES = ("manhattan", "new york", "nyc")
FOOD_LESSON = re.compile(r"food|cater|f&b|menu|meal|minimum", re.IGNORECASE)


def _norm_city(city: str | None) -> str:
    return (city or "").strip().lower()


def build_tool_registry(ctx) -> ToolRegistry:  # ctx: RunContext (import avoided to prevent a cycle)
    reg = ToolRegistry(ctx.db)
    org = ctx.organization_id
    db = ctx.db
    synthetic = ctx.research_mode == "synthetic"

    def add(name, description, kind, func, permission=None, sensitive=False):
        reg.register(ToolSpec(name, description, kind, func, permission, sensitive))

    # ── Event Intelligence ─────────────────────────────────────────────────────────

    def read_historical_events() -> ToolResult:
        with db.session() as s:
            rows = s.scalars(select(HistoricalEvent).where(HistoricalEvent.organization_id == org).order_by(HistoricalEvent.event_date)).all()
        data = [{
            "id": e.id, "name": e.name, "event_date": e.event_date.isoformat() if e.event_date else None,
            "location": e.location, "event_type": e.event_type, "attendance": e.attendance,
            "funds_raised_usd": e.funds_raised_usd, "total_cost_usd": e.total_cost_usd, "summary": e.summary,
            "venue": e.venue, "fundraising_goal_usd": e.fundraising_goal_usd, "sponsorship_usd": e.sponsorship_usd,
            "volunteers_count": e.volunteers_count, "repeat_participants": e.repeat_participants,
            "partnerships_formed": e.partnerships_formed, "funds_directed_usd": e.funds_directed_usd,
            "community_outcomes": e.community_outcomes, "is_demo": e.is_demo,
        } for e in rows]
        sources = [SourceRecord(id=f"event:{e['id']}", title=e["name"], verification="internal",
                                note="synthetic demo record" if e["is_demo"] else "board record") for e in data]
        return ToolResult(tool="read_historical_events", ok=True, summary=f"{len(data)} past events", data=data, sources=sources)

    def read_board_reflections() -> ToolResult:
        with db.session() as s:
            rows = s.execute(
                select(BoardReflection, HistoricalEvent.name)
                .join(HistoricalEvent, HistoricalEvent.id == BoardReflection.historical_event_id)
                .where(HistoricalEvent.organization_id == org)
                .order_by(BoardReflection.id)
            ).all()
        data = [{
            "id": r.id, "event_id": r.historical_event_id, "event_name": name, "author": r.author_label or "Board member",
            "submitted": r.created_at.date().isoformat(), "what_worked": r.went_well, "did_not_go_as_planned": r.challenges,
            "unexpected_costs_or_complications": r.unexpected_costs, "attendee_feedback": r.attendee_feedback,
            "repeat": r.should_repeat, "change": r.do_differently, "advice_for_next_board": r.advice, "rating": r.rating,
            "welcome_inclusion": r.welcome_inclusion, "connection_moments": r.connection_moments,
            "volunteer_appreciation": r.volunteer_appreciation, "accessibility_issues": r.accessibility_issues,
        } for r, name in rows]
        sources = [SourceRecord(id=f"reflection:{r['id']}", title=f"Reflection on {r['event_name']} ({r['author']})",
                                verification="internal") for r in data]
        return ToolResult(tool="read_board_reflections", ok=True, summary=f"{len(data)} reflections", data=data, sources=sources)

    def compare_event_outcomes(events: list) -> ToolResult:
        rows = calc.compare_events(events)
        complete = [r for r in rows if r["net_usd"] is not None]
        sufficient = len(complete) >= 2
        return ToolResult(tool="compare_event_outcomes", ok=True, data={"rows": rows, "sufficient": sufficient,
                          "note": None if sufficient else "Fewer than two events have both funds raised and expenses; numeric comparison is not meaningful."},
                          summary=f"compared {len(rows)} events ({'sufficient' if sufficient else 'insufficient'} data)")

    superseded_scopes: set[str] = set()

    def save_historical_lesson(lesson: str, kind: str, theme: str, confidence: str, applies_to: str, evidence: list,
                               based_on_demo_data: bool, scope: str, focus_event_id: int | None) -> ToolResult:
        with db.transaction() as s:
            if scope not in superseded_scopes:  # a newer analysis replaces unreviewed lessons from older runs
                superseded_scopes.add(scope)
                for old in s.scalars(select(HistoricalLesson).where(HistoricalLesson.organization_id == org, HistoricalLesson.scope == scope,
                                                                    HistoricalLesson.run_id != ctx.run_id)):
                    if (old.status or "new") == "new":
                        old.status = "superseded"
            row = HistoricalLesson(organization_id=org, run_id=ctx.run_id, lesson=lesson[:1500], kind=kind, theme=theme[:80],
                                   confidence=confidence, applies_to=applies_to[:120], evidence=evidence, scope=scope[:160],
                                   focus_event_id=focus_event_id, status="new", based_on_demo_data=based_on_demo_data)
            s.add(row)
            s.flush()
            return ToolResult(tool="save_historical_lesson", ok=True, summary=f"lesson #{row.id} saved", data={"id": row.id})

    def get_historical_lessons(limit: int = 12, statuses: list | None = None) -> ToolResult:
        wanted = statuses or ["new", "reviewed", "adopted"]
        with db.session() as s:
            rows = [l for l in s.scalars(select(HistoricalLesson).where(HistoricalLesson.organization_id == org)
                                         .order_by(HistoricalLesson.created_at.desc()).limit(200)) if (l.status or "new") in wanted][:limit]
        data = [{"id": l.id, "lesson": l.lesson, "kind": l.kind, "theme": l.theme, "status": l.status or "new",
                 "confidence": l.confidence, "evidence": l.evidence} for l in rows]
        return ToolResult(tool="get_historical_lessons", ok=True, summary=f"{len(data)} saved lessons", data=data)

    add("read_historical_events", "Past events with attendance, funds raised, and costs.", ToolKind.READ, read_historical_events, Permission.VIEW_DASHBOARD)
    add("read_board_reflections", "Board reflections on past events.", ToolKind.READ, read_board_reflections, Permission.VIEW_DASHBOARD)
    add("compare_event_outcomes", "Net, ROI, and per-attendee metrics for past events.", ToolKind.COMPUTE, compare_event_outcomes)
    add("save_historical_lesson", "Save an evidence-backed lesson.", ToolKind.SAVE, save_historical_lesson, Permission.RUN_AGENTS)
    add("get_historical_lessons", "Read saved lessons.", ToolKind.READ, get_historical_lessons, Permission.VIEW_DASHBOARD)

    # ── Fundraising & Events ───────────────────────────────────────────────────────

    def read_event_plan(event_plan_id: int) -> ToolResult:
        with db.session() as s:
            p = s.get(EventPlan, event_plan_id)
        if p is None or p.organization_id != org:
            return ToolResult(tool="read_event_plan", ok=False, error="Event plan not found.")
        data = {"id": p.id, "name": p.name, "event_type": p.event_type, "city": p.city,
                "target_date": p.target_date.isoformat() if p.target_date else None,
                "date_end": p.date_end.isoformat() if p.date_end else None,
                "attendance": p.expected_attendance, "fundraising_goal_usd": p.fundraising_goal_usd,
                "budget_limit_usd": p.budget_limit_usd, "ticket_price_usd": p.ticket_price_usd, "event_format": p.event_format,
                "instructions": p.instructions, "assumptions": p.assumptions, "notes": p.notes, "is_demo": p.is_demo}
        return ToolResult(tool="read_event_plan", ok=True, summary=p.name, data=data,
                          sources=[SourceRecord(id=f"event_plan:{p.id}", title=p.name, verification="internal")])

    def create_event_plan(name: str, city: str, attendance: int | None, event_type: str, budget_limit_usd: float | None) -> ToolResult:
        with db.transaction() as s:
            p = EventPlan(organization_id=org, created_by=ctx.user_id, name=name[:200], city=city[:120], event_type=event_type[:60],
                          expected_attendance=attendance, budget_limit_usd=budget_limit_usd, status="planning",
                          notes="Created by the Orchestrator from a board request.")
            s.add(p)
            s.flush()
            return ToolResult(tool="create_event_plan", ok=True, summary=f"event plan #{p.id}", data={"id": p.id})

    def search_venues(city: str, attendance: int, formats: list) -> ToolResult:
        if synthetic:
            if not any(a in _norm_city(city) for a in NYC_ALIASES):
                return ToolResult(tool="search_venues", ok=True, data=[], summary="no synthetic venues for this city",
                                  warnings=[f"The synthetic demo only has Manhattan venues. Use live research for {city}."])
            out, sources = [], []
            for v in fixtures.VENUES:
                fits = {f: cap for f, cap in v["capacity"].items() if f in formats and cap >= attendance}
                if not fits:
                    continue
                src_id = f"synthetic:venue:{v['key']}"
                url = fixtures.fixture_url("venues", v["key"])
                out.append({
                    "venue_key": v["key"], "name": v["name"], "address": v["address"], "neighborhood": v["neighborhood"],
                    "website": url, "website_status": "synthetic", "source_url": url, "verified_at": None,
                    "formats": list(fits), "capacity": v["capacity"], "capacity_quote": v["capacity_quote"], "capacity_status": "published",
                    "pricing_status": v["pricing_status"], "pricing_quote": v["pricing_quote"], "rental_usd": v["rental_usd"],
                    "fnb_per_guest_usd": v["fnb_per_guest_usd"], "fnb_minimum_usd": v["fnb_minimum_usd"], "deposit_pct": v["deposit_pct"],
                    "catering": v["catering"], "amenities": v["amenities"], "restrictions": v["restrictions"], "notes": v["notes"],
                    "source_id": src_id, "verification": "synthetic",
                })
                sources.append(SourceRecord(id=src_id, title=v["name"], url=url, verification="synthetic", note=fixtures.SYNTHETIC_NOTE))
            return ToolResult(tool="search_venues", ok=True, data=out, sources=sources,
                              summary=f"{len(out)} synthetic venues fit {attendance} guests ({', '.join(formats)})",
                              warnings=["Synthetic venue fixtures, not live web research."])
        from ..research.live import live_venue_search
        return live_venue_search(ctx, city, attendance, formats)

    def save_venue_candidate(event_plan_id: int, venue: dict, event_format: str, budget_total_usd: float) -> ToolResult:
        with db.transaction() as s:
            existing = s.scalar(select(VenueCandidate).where(VenueCandidate.event_plan_id == event_plan_id,
                                                              VenueCandidate.name == venue["name"]))
            row = existing or VenueCandidate(event_plan_id=event_plan_id, name=venue["name"])
            row.run_id = ctx.run_id
            row.address = venue.get("neighborhood") or ""
            caps = venue.get("capacity") or {}
            row.capacity = caps.get(event_format) if isinstance(caps, dict) else None
            row.estimated_cost_usd = budget_total_usd
            row.cost_is_estimate = True
            fnb = venue.get("fnb_per_guest_usd")
            row.fnb_per_guest_usd = fnb.get(event_format) if isinstance(fnb, dict) else fnb
            row.deposit_pct = venue.get("deposit_pct")
            row.formats = venue.get("formats")
            row.verification = venue.get("verification")
            row.is_synthetic = venue.get("verification") == "synthetic"
            row.website = venue.get("website")
            row.pricing_status = venue.get("pricing_status")
            row.amenities = venue.get("amenities")
            row.restrictions = venue.get("restrictions")
            row.verified_at = venue.get("verified_at")
            row.source_url = venue.get("source_url")
            row.notes = (venue.get("notes") or "")[:1000]
            s.add(row)
            s.flush()
            return ToolResult(tool="save_venue_candidate", ok=True, summary=f"venue candidate #{row.id}", data={"id": row.id})

    def compute_event_model(venue: dict, event_format: str, event: dict, contingency_pct: float | None, overrides: dict | None) -> ToolResult:
        history = em.history_basis(read_historical_events().data, event.get("event_type") or "")
        assumptions = em.build_assumptions(venue=venue, event_format=event_format, event=event, history=history,
                                           contingency_pct=contingency_pct, overrides=overrides)
        model = em.compute(assumptions, max_budget_usd=event.get("budget_limit_usd"), target_usd=event.get("fundraising_goal_usd"))
        model["catering_minimum_risk"] = em.catering_minimum_risk(assumptions)
        model["history_basis"] = history
        return ToolResult(tool="compute_event_model", ok=True, data=model,
                          summary=f"{venue['name']} {event_format}: cost ${model['total_cost_usd']:,.0f}, upfront ${model['upfront_cash_usd']:,.0f}")

    add("read_event_plan", "Read one event plan.", ToolKind.READ, read_event_plan, Permission.VIEW_DASHBOARD)
    add("create_event_plan", "Create an event plan from a request.", ToolKind.SAVE, create_event_plan, Permission.MANAGE_EVENTS)
    add("search_venues", "Find venues (live web search, or labeled synthetic fixtures).", ToolKind.RESEARCH, search_venues)
    add("save_venue_candidate", "Save a venue candidate to an event plan.", ToolKind.SAVE, save_venue_candidate, Permission.MANAGE_EVENTS)
    add("compute_event_model", "Deterministic cost/revenue model with labeled assumptions and three scenarios.", ToolKind.COMPUTE,
        compute_event_model, Permission.VIEW_DASHBOARD)

    # ── Financial Analysis ─────────────────────────────────────────────────────────

    def read_financial_records() -> ToolResult:
        with db.session() as s:
            rows = s.scalars(select(FinancialRecord).where(FinancialRecord.organization_id == org)).all()
        data = [{"period": r.period, "kind": r.kind, "category": r.category, "amount_usd": r.amount_usd, "is_demo": r.is_demo,
                 "restriction": r.restriction, "purpose": r.purpose} for r in rows]
        demo = any(r["is_demo"] for r in data)
        return ToolResult(tool="read_financial_records", ok=True, summary=f"{len(data)} ledger rows | contents redacted", data=data,
                          sources=[SourceRecord(id="ledger", title="Financial records (synthetic demo books)" if demo else "Financial records",
                                                verification="internal")])

    def compute_financial_analysis() -> ToolResult:
        """The full dashboard analysis (totals, restrictions, cash, ratios, variance, warnings), computed in code."""
        with db.session() as s:
            rows = s.scalars(select(FinancialRecord).where(FinancialRecord.organization_id == org)).all()
            records = [{c.name: getattr(r, c.name) for c in FinancialRecord.__table__.columns} for r in rows]
            past = [{c.name: getattr(e, c.name) for c in HistoricalEvent.__table__.columns}
                    for e in s.scalars(select(HistoricalEvent).where(HistoricalEvent.organization_id == org))]
            plans = [{"name": p.name, "budget_limit_usd": p.budget_limit_usd, "status": p.status}
                     for p in s.scalars(select(EventPlan).where(EventPlan.organization_id == org))]
            pending = len(s.scalars(select(ExtractedFigure.id).where(ExtractedFigure.organization_id == org,
                                                                      ExtractedFigure.status == "pending")).all())
        for e in past:
            e["event_date"] = e["event_date"].isoformat() if e.get("event_date") else None
        data = build_dashboard(records, plans, past, None, pending_review=pending)
        return ToolResult(tool="compute_financial_analysis", ok=True, data=data, summary=f"{len(data['metrics'])} metrics | contents redacted")

    def read_document_text(document_id: int) -> ToolResult:
        """Page text of an uploaded PDF, screened for instructions aimed at AI. The file itself is never executed."""
        with db.session() as s:
            d = s.get(FinancialDocument, int(document_id))
            if d is None or d.organization_id != org:
                return ToolResult(tool="read_document_text", ok=False, error="Document not found.")
            meta = {"id": d.id, "filename": d.filename, "doc_type": d.doc_type, "file_type": d.file_type, "is_demo": d.is_demo}
            path = ctx.settings.database_path.parent / "uploads" / "finance" / str(org) / d.stored_name
        if meta["file_type"] != "pdf":
            return ToolResult(tool="read_document_text", ok=False, error="Only PDFs are read this way; CSV files are parsed in code.")
        parsed = docs.read_pdf(path.read_bytes())
        pages, flags = [], []
        for text in parsed["pages"]:
            clean, found = sanitize_untrusted(text)
            pages.append(clean)
            flags += found
        return ToolResult(tool="read_document_text", ok=True, summary=f"{len(pages)} page(s), status {parsed['status']} | text not logged",
                          data={**meta, "pages": pages, "status": parsed["status"], "notes": parsed["notes"], "injection_flags": flags},
                          sources=[SourceRecord(id=f"document:{meta['id']}", title=meta["filename"], verification="internal",
                                                note="uploaded financial document")])

    def save_extracted_figures(document_id: int, figures: list, period_label: str | None, status: str) -> ToolResult:
        """Stage figures for board review. They do not count anywhere until a person approves them."""
        with db.transaction() as s:
            d = s.get(FinancialDocument, int(document_id))
            if d is None or d.organization_id != org:
                return ToolResult(tool="save_extracted_figures", ok=False, error="Document not found.")
            for old in s.scalars(select(ExtractedFigure).where(ExtractedFigure.document_id == d.id, ExtractedFigure.status == "pending")):
                s.delete(old)  # a re-extraction replaces figures nobody has reviewed yet
            for f in figures:
                s.add(ExtractedFigure(organization_id=org, document_id=d.id, run_id=ctx.run_id, **f))
            d.status, d.period_label, d.run_id = status, period_label, ctx.run_id
            return ToolResult(tool="save_extracted_figures", ok=True, data={"saved": len(figures)},
                              summary=f"{len(figures)} figure(s) staged for board review")

    def compute_financial_position(records: list) -> ToolResult:
        pos = calc.financial_position(records)
        return ToolResult(tool="compute_financial_position", ok=True, data=pos,
                          summary=f"{pos['months_of_data']} months; available planning budget: "
                                  f"{'$' + format(pos['available_planning_budget_usd'], ',.0f') if pos['available_planning_budget_usd'] is not None else 'not supported'}")

    def recompute_event_model(assumptions: dict, max_budget_usd: float | None, target_usd: float | None) -> ToolResult:
        model = em.compute(assumptions, max_budget_usd=max_budget_usd, target_usd=target_usd)
        model["catering_minimum_risk"] = em.catering_minimum_risk(assumptions)
        return ToolResult(tool="recompute_event_model", ok=True, data=model, summary=f"recomputed: cost ${model['total_cost_usd']:,.0f}")

    def check_event_affordability(model: dict, position: dict, min_contingency_pct: float | None) -> ToolResult:
        aff = em.affordability(model, position, min_contingency_pct)
        return ToolResult(tool="check_event_affordability", ok=True, data=aff,
                          summary=f"verdict {aff['verdict']}; {len(aff['conflicts'])} conflict(s)")

    add("read_financial_records", "Read the ledger.", ToolKind.READ, read_financial_records, Permission.VIEW_FINANCIALS, sensitive=True)
    add("compute_financial_position", "Revenue, expenses, reserve, planning budget.", ToolKind.COMPUTE, compute_financial_position, Permission.VIEW_FINANCIALS)
    add("recompute_event_model", "Recompute the event model from the given assumptions.", ToolKind.COMPUTE, recompute_event_model)
    add("check_event_affordability", "Pass/fail affordability checks and conflicts.", ToolKind.COMPUTE, check_event_affordability, Permission.VIEW_FINANCIALS)

    # ── Donations & Compliance ──────────────────────────────────────────────────────

    def _donation_items() -> tuple[list[dict], list[dict]]:
        from ..services import donations as dsvc
        from ..db.models import Campaign, Donor
        with db.session() as s:
            donors = {x.id: x.donor_code for x in s.scalars(select(Donor).where(Donor.organization_id == org))}
            camps = {c.id: c for c in s.scalars(select(Campaign).where(Campaign.organization_id == org))}
            rows = s.scalars(select(Donation).where(Donation.organization_id == org).order_by(Donation.received_on)).all()
            items = [{"id": d.id, "donation_id": dsvc.donation_code(d.id), "donor_id": donors.get(d.donor_id), "donor_name": d.donor_name,
                      "has_email": bool(d.donor_email), "amount_usd": d.amount_usd, "received_on": d.received_on.isoformat(),
                      "method": d.method, "designation": d.designation, "acknowledged": d.acknowledged,
                      "ack_status": d.ack_status or ("completed" if d.acknowledged else "not_started"),
                      "contribution_type": d.contribution_type or "monetary", "restriction": d.restriction,
                      "payment_status": d.payment_status or "received", "campaign_id": d.campaign_id,
                      "campaign": camps[d.campaign_id].name if d.campaign_id in camps else None,
                      "in_kind_description": d.in_kind_description, "goods_services_value_usd": d.goods_services_value_usd,
                      "is_demo": d.is_demo} for d in rows]
            campaigns = [{"id": c.id, "name": c.name, "kind": c.kind, "goal_usd": c.goal_usd} for c in camps.values()]
        dupes = dsvc.duplicate_index(items)
        for it in items:
            it["flags"] = dsvc.flags_for(it, dupes, date.today())
        return items, campaigns

    def read_donations() -> ToolResult:
        items, campaigns = _donation_items()
        return ToolResult(tool="read_donations", ok=True, summary=f"{len(items)} gifts | contents redacted",
                          data={"donations": items, "campaigns": campaigns})

    def flag_donation_issues(donations: list) -> ToolResult:
        """Counts by flag and campaign, with no names or per-donor amounts (this is what a model may see)."""
        from ..services import donations as dsvc
        items, campaigns = _donation_items()
        wanted = {d["id"] for d in donations}
        items = [d for d in items if d["id"] in wanted]
        counts: dict[str, int] = {}
        for d in items:
            for f in d["flags"]:
                counts[f["code"]] = counts.get(f["code"], 0) + 1
        ledger = [{"period": r.period, "kind": r.kind, "category": r.category, "amount_usd": r.amount_usd, "period_months": r.period_months}
                  for r in _ledger_rows()]
        summary = dsvc.summarize(items, campaigns, ledger)
        aggregate = {"gifts_recorded": len(items), "gifts_needing_attention": sum(1 for d in items if any(f["severity"] != "low" for f in d["flags"])),
                     "flag_counts": counts, "ack_status": summary["ack_status"], "pledges": summary["pledges"],
                     "in_kind_gifts": summary["in_kind_gifts"], "duplicates_excluded": summary["duplicates_excluded"],
                     "by_campaign": [{k: c[k] for k in ("name", "kind", "goal_usd", "received_usd", "pledged_usd", "gifts")} for c in summary["by_campaign"]],
                     "received_total_usd": summary["received_usd"], "reconciliation_months": len(summary["reconciliation"])}
        per_gift = [{"id": d["id"], "flags": [f["code"] for f in d["flags"]], "acknowledged": d["acknowledged"], "ack_status": d["ack_status"],
                     "amount_band": "250_plus" if d["amount_usd"] >= 250 else "under_250", "payment_status": d["payment_status"],
                     "contribution_type": d["contribution_type"]} for d in items]
        return ToolResult(tool="flag_donation_issues", ok=True, data={"per_gift": per_gift, "flag_counts": counts, "aggregate": aggregate},
                          summary=f"{aggregate['gifts_needing_attention']} gifts need attention")

    def read_compliance_items() -> ToolResult:
        from ..services import donations as dsvc
        from ..compliance import public_references
        items, _ = _donation_items()
        with db.session() as s:
            places = [p.city for p in s.scalars(select(EventPlan).where(EventPlan.organization_id == org))] + \
                     [e.location for e in s.scalars(select(HistoricalEvent).where(HistoricalEvent.organization_id == org))]
        ledger = [{"period": r.period, "kind": r.kind, "category": r.category, "amount_usd": r.amount_usd, "period_months": r.period_months}
                  for r in _ledger_rows()]
        found = dsvc.compliance_items(items, ledger, [x for x in map(dsvc.state_of, places) if x])
        refs = [{k: r[k] for k in ("id", "title", "authority", "jurisdiction", "kind", "url", "checked_on", "stale", "points")}
                for r in public_references()]
        return ToolResult(tool="read_compliance_items", ok=True, summary=f"{len(found)} compliance items",
                          data={"items": [{k: i[k] for k in ("key", "title", "detail", "kind", "professional")} | {"ref_ids": [r["id"] for r in i["references"]],
                                           "count": len(i["donation_ids"])} for i in found], "references": refs})

    def _ledger_rows():
        with db.session() as s:
            return s.scalars(select(FinancialRecord).where(FinancialRecord.organization_id == org)).all()

    def _gift_text(d: Donation) -> str:
        """The gift itself, as recorded: an amount, or a description for in-kind gifts (never a value we assign)."""
        if (d.contribution_type or "monetary") == "in_kind":
            text = d.in_kind_description or "in-kind support"
            return text[:1].lower() + text[1:] if not text[:2].isupper() else text
        return f"${d.amount_usd:,.2f}"

    def create_acknowledgment_drafts(subject: str, body: str, donation_ids: list) -> ToolResult:
        """Merge the template locally with verified record fields. Drafts are never sent, and records are not changed."""
        made, ids = 0, []
        with db.transaction() as s:
            camps = {c.id: c.name for c in s.scalars(select(Campaign).where(Campaign.organization_id == org))}
            for d in s.scalars(select(Donation).where(Donation.organization_id == org, Donation.id.in_(donation_ids))):
                fill = {"{{donor_name}}": d.donor_name, "{{gift}}": _gift_text(d), "{{amount}}": _gift_text(d),
                        "{{date}}": f"{d.received_on:%B} {d.received_on.day}, {d.received_on.year}", "{{designation}}": d.designation or "",
                        "{{campaign}}": camps.get(d.campaign_id, "the foundation's work")}
                text_body, text_subject = body, subject
                for k, v in fill.items():
                    text_body, text_subject = text_body.replace(k, v), text_subject.replace(k, v)
                text_body = re.sub(r"\b(your (gift|donation|contribution) of )\1", r"\1", text_body, flags=re.IGNORECASE)
                notes = ["General thank-you letter, not a tax acknowledgment. SAM SPACE does not decide whether a gift is deductible."]
                if d.amount_usd >= 250 and (d.contribution_type or "monetary") != "in_kind":
                    notes.append("This gift is $250 or more: the donor also needs a written contribution acknowledgment (see the "
                                 "separate draft for accountant review).")
                draft = OutreachDraft(organization_id=org, run_id=ctx.run_id, agent="donations_compliance", draft_type="donor_thank_you",
                                      recipient_name=d.donor_name, recipient_org="", subject=text_subject[:300], body=text_body, status="draft",
                                      created_by=ctx.user_id, donation_id=d.id, review_notes=notes,
                                      personalization_basis="Merged locally from the donation record; the AI saw only a template.",
                                      is_synthetic_target=d.is_demo)
                s.add(draft)
                s.flush()
                ids.append(draft.id)
                made += 1
        return ToolResult(tool="create_acknowledgment_drafts", ok=True, data={"drafts_created": made, "draft_ids": ids},
                          summary=f"{made} thank-you drafts")

    def create_contribution_acknowledgments(donation_ids: list) -> ToolResult:
        """Deterministic drafts of the elements a written contribution acknowledgment needs (IRS, US federal), marked for
        accountant review. No model writes these, and nothing is sent."""
        from ..compliance import reference
        ref, qpq = reference("irs-written-ack"), reference("irs-quid-pro-quo")
        made, ids = 0, []
        with db.transaction() as s:
            for d in s.scalars(select(Donation).where(Donation.organization_id == org, Donation.id.in_(donation_ids))):
                in_kind = (d.contribution_type or "monetary") == "in_kind"
                lines = ["[DRAFT FOR ACCOUNTANT REVIEW. Not sent. Not a final acknowledgment until a qualified person reviews it.]", "",
                         "Sabrina Audrey Milone Foundation", "Contribution acknowledgment", "",
                         f"Donor: {d.donor_name}", f"Date received: {d.received_on:%B} {d.received_on.day}, {d.received_on.year}",
                         (f"Contribution: {d.in_kind_description or '[describe the item]'} (description only; the foundation does not state a value)"
                          if in_kind else f"Contribution: ${d.amount_usd:,.2f}")]
                if d.goods_services_value_usd:
                    lines += [f"Goods or services provided in return: [describe, e.g. dinner at the event]. Good-faith estimate of their value: "
                              f"${d.goods_services_value_usd:,.2f} [confirm with accountant].",
                              "The amount deductible for federal income tax purposes is limited to the excess of the payment over the value "
                              "of the goods or services provided. [Confirm wording with accountant.]"]
                else:
                    lines.append("[Confirm before use] No goods or services were provided in exchange for this contribution.")
                lines += ["", f"Source: {ref['authority']}, “{ref['title']}” ({ref['jurisdiction']}), {ref['url']}, checked {ref['checked_on']}."]
                if d.goods_services_value_usd:
                    lines.append(f"Source: {qpq['authority']}, “{qpq['title']}” ({qpq['jurisdiction']}), {qpq['url']}, checked {qpq['checked_on']}.")
                draft = OutreachDraft(organization_id=org, run_id=ctx.run_id, agent="donations_compliance", draft_type="contribution_acknowledgment",
                                      recipient_name=d.donor_name, recipient_org="", subject="Contribution acknowledgment (draft for accountant review)",
                                      body="\n".join(lines), status="draft", created_by=ctx.user_id, donation_id=d.id, is_synthetic_target=d.is_demo,
                                      review_notes=["Contains only fields from the donation record. Review with an accountant before anyone sends it."],
                                      personalization_basis="Built in code from the donation record (no AI).",
                                      sources=[{"title": ref["title"], "url": ref["url"], "verification": "verified"}] +
                                              ([{"title": qpq["title"], "url": qpq["url"], "verification": "verified"}] if d.goods_services_value_usd else []))
                s.add(draft)
                s.flush()
                ids.append(draft.id)
                made += 1
        return ToolResult(tool="create_contribution_acknowledgments", ok=True, data={"drafts_created": made, "draft_ids": ids},
                          summary=f"{made} contribution acknowledgment drafts (for accountant review)")

    add("read_donations", "Read contribution records.", ToolKind.READ, read_donations, Permission.VIEW_DONOR_DATA, sensitive=True)
    add("read_compliance_items", "Deterministic compliance checklist with cited sources.", ToolKind.COMPUTE, read_compliance_items,
        Permission.VIEW_DONOR_DATA)
    add("create_contribution_acknowledgments", "Draft contribution acknowledgments for accountant review (code, unsent).", ToolKind.DRAFT,
        create_contribution_acknowledgments, Permission.MANAGE_DONATIONS, sensitive=True)
    add("flag_donation_issues", "Missing-information and acknowledgment flags.", ToolKind.COMPUTE, flag_donation_issues, Permission.VIEW_DONOR_DATA)
    add("create_acknowledgment_drafts", "Merge a template into unsent acknowledgment drafts.", ToolKind.DRAFT, create_acknowledgment_drafts,
        Permission.VIEW_DONOR_DATA, sensitive=True)

    # ── Mission Discovery + Partnerships ─────────────────────────────────────────────

    def private_terms() -> list[str]:
        """Names that must never leave SAM SPACE in a search query (donors, board members)."""
        with db.session() as s:
            donors = s.scalars(select(Donation.donor_name).where(Donation.organization_id == org)).all()
            users = s.execute(select(User.first_name, User.last_name)).all()
        return [d for d in donors if d] + [f"{a} {b}".strip() for a, b in users if b]

    def search_web(query: str, purpose: str) -> ToolResult:
        clean, removed = scrub_outbound_query(query, private_terms())
        notes = [f"Removed private details from the search query before it left SAM SPACE ({', '.join(removed)})."] if removed else []
        if synthetic:
            pool = fixtures.SPONSORS + fixtures.ORGANIZATIONS if purpose == "sponsors" else fixtures.ORGANIZATIONS
            data = [{"source_id": f"synthetic:{'sponsors' if o in fixtures.SPONSORS else 'organizations'}:{o['key']}", "title": o["title"],
                     "url": fixtures.fixture_url("sponsors" if o in fixtures.SPONSORS else "organizations", o["key"]),
                     "publisher": None, "published": o["published"], "date_claim": o.get("date_claim"), "snippet": o["summary"],
                     "category_hint": o["category"], "geography": o.get("geography")} for o in pool][:6]
            return ToolResult(tool="search_web", ok=True, data=data, summary=f"{len(data)} synthetic results",
                              warnings=["Synthetic research fixtures, not live web research."] + notes)
        from ..research.live import live_web_search
        result = live_web_search(ctx, clean, purpose)
        result.warnings = notes + result.warnings
        return result

    def _page_checks(text: str, data: dict, check_terms: list | None, check_dates: list | None) -> None:
        """Screen untrusted page text, then record what it does and does not say. The raw text is never returned."""
        clean, flags = sanitize_untrusted(text)
        low = clean.lower()
        data["injection_flags"] = flags
        data["excerpt"] = clean[:2200]
        data["dates_on_page"] = web.dates_in_text(clean)
        data["money_on_page"] = web.money_in_text(clean)
        data["terms_found"] = [t for t in (check_terms or []) if t and t.lower() in low]
        data["date_checks"] = {c: web.date_status(c, data["dates_on_page"]) for c in (check_dates or []) if c}

    def fetch_source(url: str, source_id: str, check_values: list | None = None, check_terms: list | None = None,
                     check_dates: list | None = None, screen: bool = False) -> ToolResult:
        if url.startswith("https://example.org/synthetic/"):
            fixture = fixtures.FIXTURE_PAGES.get(url.split("/synthetic/", 1)[1])
            src = SourceRecord(id=source_id, title=fixture["title"] if fixture else url.rsplit("/", 1)[-1], url=url,
                               verification="synthetic", note=fixtures.SYNTHETIC_NOTE,
                               retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
            data = {"verified": False, "synthetic": True, "retrieved_at": src.retrieved_at}
            if screen:
                _page_checks((fixture or {}).get("page_text", ""), data, check_terms, check_dates)
            flagged = f" · {len(data.get('injection_flags') or [])} instruction-like fragment(s) removed" if data.get("injection_flags") else ""
            return ToolResult(tool="fetch_source", ok=True, data=data, sources=[src], summary=f"synthetic fixture (not fetched){flagged}")
        if ctx.counters["page_fetches"] >= ctx.settings.max_page_fetches_per_run:
            return ToolResult(tool="fetch_source", ok=False, error="Page-fetch limit for this run reached.",
                              sources=[SourceRecord(id=source_id, title=url, url=url, verification="unverified", note="not fetched: limit")])
        ctx.counters["page_fetches"] += 1
        page = web.fetch_page(url)
        text = page.pop("text", "")
        page["figures_found"] = web.figures_on_page(text, [float(x) for x in (check_values or [])])
        if screen:
            _page_checks(" ".join(x for x in (page.get("description"), text) if x), page, check_terms, check_dates)
        src = SourceRecord(id=source_id, title=page.get("title") or url, url=url, published=page.get("published"),
                           retrieved_at=page.get("retrieved_at"), verification="verified" if page["ok"] else "unverified",
                           http_status=page.get("http_status"), note=None if page["ok"] else page.get("error"))
        flagged = f" · {len(page.get('injection_flags') or [])} instruction-like fragment(s) removed" if page.get("injection_flags") else ""
        return ToolResult(tool="fetch_source", ok=page["ok"], data=page, sources=[src], error=None if page["ok"] else page.get("error"),
                          summary=f"HTTP {page.get('http_status')} {(page.get('title') or '')[:80]}{flagged}")

    def classify_mission_alignment(text: str) -> ToolResult:
        low = text.lower()
        hits = {area: [t for t in terms if t in low] for area, terms in MISSION_TERMS.items()}
        score = 2 * len(hits["eating_disorders"]) + 2 * len(hits["mental_health"]) + len(hits["community"])
        label = "high" if hits["eating_disorders"] or score >= 4 else "medium" if score >= 2 else "low" if score else "none"
        return ToolResult(tool="classify_mission_alignment", ok=True, data={"keyword_label": label, "score": score, "matches": hits},
                          summary=f"keyword alignment {label}")

    RESEARCH_FIELDS = ("category", "title", "summary", "source_url", "source_title", "verification_status", "alignment",
                       "uncertainty", "published", "name", "website", "geography", "purpose", "activities", "dates_text",
                       "date_status", "partnership_types", "contribution_ways", "known_costs", "missing_info", "next_step",
                       "alignment_detail", "fit", "fit_reason", "warnings", "injection_flags")

    def save_research_finding(agent: str, finding: dict) -> ToolResult:
        """Save an opportunity, or refresh the existing card for the same organization.
        Board fields (status, category, private notes) are never overwritten by research."""
        fields = {k: finding.get(k) for k in RESEARCH_FIELDS if k in finding}
        fields["title"] = (fields.get("title") or fields.get("name") or "Untitled")[:300]
        site = opp.domain(fields.get("website") or fields.get("source_url"))
        with db.transaction() as s:
            candidates = s.scalars(select(ResearchFinding).where(
                ResearchFinding.organization_id == org,
                or_(ResearchFinding.name.is_not(None), ResearchFinding.website.is_not(None)))).all()
            row = next((r for r in candidates if (site and not site.startswith("example.org") and opp.domain(r.website) == site)
                        or (fields.get("name") and opp.norm_name(r.name) == opp.norm_name(fields["name"]))), None)
            refreshed = row is not None
            if row is None:
                row = ResearchFinding(organization_id=org, agent=agent, status="new", saved=False)
                s.add(row)
            for k, v in fields.items():
                setattr(row, k, v)
            row.run_id = ctx.run_id
            row.is_synthetic = fields.get("verification_status") == "synthetic"
            row.last_checked = datetime.now(timezone.utc)
            row.research_requested = False
            s.flush()
            return ToolResult(tool="save_research_finding", ok=True, data={"id": row.id, "refreshed": refreshed},
                              summary=f"{'refreshed' if refreshed else 'new'} opportunity #{row.id}")

    def read_saved_findings(categories: list) -> ToolResult:
        with db.session() as s:
            rows = s.scalars(select(ResearchFinding).where(ResearchFinding.organization_id == org, ResearchFinding.category.in_(categories))
                             .order_by(ResearchFinding.saved.desc(), ResearchFinding.created_at.desc()).limit(8)).all()
        data = [{"id": f.id, "title": f.title, "category": f.category, "summary": f.summary, "source_url": f.source_url,
                 "verification": f.verification_status, "saved": f.saved} for f in rows]
        return ToolResult(tool="read_saved_findings", ok=True, data=data, summary=f"{len(data)} findings")

    def read_opportunities(ids: list | None = None, status: str | None = None) -> ToolResult:
        """Opportunities as the board sees them, without private notes (notes never reach a model)."""
        with db.session() as s:
            q = select(ResearchFinding).where(ResearchFinding.organization_id == org)
            if ids:
                q = q.where(ResearchFinding.id.in_([int(i) for i in ids]))
            rows = s.scalars(q.order_by(ResearchFinding.created_at.desc()).limit(40)).all()
            data = [opp.opportunity_out(r, include_notes=False) for r in rows]
        if status:
            data = [d for d in data if d["status"] == status]
        return ToolResult(tool="read_opportunities", ok=True, data=data, summary=f"{len(data)} opportunities")

    def select_opportunities(findings: list, count: int) -> ToolResult:
        picked = opp.select_candidates(findings, int(count))
        return ToolResult(tool="select_opportunities", ok=True, data=picked, warnings=picked["warnings"],
                          summary=f"selected {len(picked['selected'])} of {len(findings)} (requested {count})")

    def create_outreach_draft(draft_type: str, recipient_org: str, subject: str, body: str, personalization_basis: str,
                              is_synthetic_target: bool, purpose: str | None = None, opportunity: str | None = None,
                              next_step: str | None = None, foundation_background: str | None = None, sources: list | None = None,
                              finding_id: int | None = None, review_notes: list | None = None) -> ToolResult:
        """Save an UNSENT draft. There is no 'sent' status and no tool anywhere that sends it."""
        with db.transaction() as s:
            row = OutreachDraft(organization_id=org, run_id=ctx.run_id, agent="partnerships_outreach", draft_type=draft_type,
                                recipient_org=recipient_org[:200], subject=subject[:300], body=body[:6000], status="draft",
                                personalization_basis=personalization_basis[:1000], is_synthetic_target=is_synthetic_target,
                                purpose=purpose, opportunity=opportunity, next_step=next_step, foundation_background=foundation_background,
                                sources=sources or [], finding_id=finding_id, review_notes=review_notes or [], created_by=ctx.user_id)
            s.add(row)
            s.flush()
            return ToolResult(tool="create_outreach_draft", ok=True, summary=f"draft #{row.id} (unsent)", data={"id": row.id})

    add("search_web", "Bounded web search (or labeled synthetic fixtures).", ToolKind.RESEARCH, search_web)
    add("fetch_source", "Fetch one public page to verify a link (SSRF-guarded).", ToolKind.RESEARCH, fetch_source)
    add("classify_mission_alignment", "Keyword cross-check of mission alignment.", ToolKind.COMPUTE, classify_mission_alignment)
    add("save_research_finding", "Save (or refresh) an opportunity with its sources and alignment.", ToolKind.SAVE, save_research_finding,
        Permission.RUN_AGENTS)
    add("compute_financial_analysis", "Full financial analysis in code (totals, restrictions, cash, variance).", ToolKind.COMPUTE,
        compute_financial_analysis, Permission.VIEW_FINANCIALS, sensitive=True)
    add("read_document_text", "Read an uploaded PDF's text (screened, never executed).", ToolKind.READ, read_document_text,
        Permission.VIEW_FINANCIALS, sensitive=True)
    add("save_extracted_figures", "Stage extracted figures for board review.", ToolKind.SAVE, save_extracted_figures,
        Permission.MANAGE_FINANCIALS, sensitive=True)
    add("read_saved_findings", "Read saved research findings.", ToolKind.READ, read_saved_findings, Permission.VIEW_DASHBOARD)
    add("read_opportunities", "Read Mission Discovery opportunities (no private notes).", ToolKind.READ, read_opportunities,
        Permission.VIEW_DASHBOARD)
    add("select_opportunities", "Deterministically pick outreach candidates by the fit rubric.", ToolKind.COMPUTE, select_opportunities)
    add("create_outreach_draft", "Save an unsent outreach draft.", ToolKind.DRAFT, create_outreach_draft, Permission.RUN_AGENTS)

    # ── Orchestrator ─────────────────────────────────────────────────────────────

    def verify_final_result(report: dict) -> ToolResult:
        failed = [c for c in report.get("checks", []) if c.get("passed") is False]
        return ToolResult(tool="verify_final_result", ok=not failed, data=report,
                          summary=f"{len(report.get('checks', [])) - len(failed)}/{len(report.get('checks', []))} checks passed")

    add("verify_final_result", "Record the deterministic verification report.", ToolKind.COMPUTE, verify_final_result)

    def evaluate_constraints(finance_conflicts: list, lessons: list, assumptions: dict, venue_name: str) -> ToolResult:
        """Budget conflicts from Finance plus history checks the plan may have neglected."""
        conflicts = [dict(c) for c in finance_conflicts]
        history_checks = []
        food = [l for l in lessons if FOOD_LESSON.search(f"{l.get('theme') or ''} {l.get('text') or ''}")]
        risk = em.catering_minimum_risk(assumptions)
        if food:
            ok = risk is None
            detail = (f"{venue_name}'s ${risk['minimum_usd']:,.0f} catering minimum would still be charged if only {risk['guests']} guests "
                      f"come (${risk['overpay_usd']:,.0f} above per-head cost), the food-cost exposure past events warned about."
                      if risk else "No binding catering minimum at conservative attendance.")
            history_checks.append({"name": "Food-cost lesson respected (no binding catering minimum)", "passed": ok, "detail": detail,
                                   "lessons": [l.get("text") for l in food][:3],
                                   "event_ids": sorted({i for l in food for i in l.get("event_ids", [])}),
                                   "reflection_ids": sorted({i for l in food for i in l.get("reflection_ids", [])})})
            if not ok:
                conflicts.append({"type": "history_catering_minimum", "source": "history", "detail": detail,
                                  "conservative_share": em.SCENARIOS["conservative"]["attendance"]})
        return ToolResult(tool="evaluate_constraints", ok=True, data={"conflicts": conflicts, "history_checks": history_checks},
                          summary=f"{len(conflicts)} conflict(s): " + ", ".join(sorted({c['source'] for c in conflicts})) if conflicts else "no conflicts")

    add("evaluate_constraints", "Combine Finance conflicts with history checks.", ToolKind.COMPUTE, evaluate_constraints)

    return reg


def today_iso() -> str:
    return date.today().isoformat()
