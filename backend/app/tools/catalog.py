"""Every tool the agents can use, bound to one run.

Each tool does one narrow thing and returns a ToolResult. The allow-lists in
agents/registry.py decide which agent may call which tool. The permission
column decides which board roles may trigger it. Sensitive tools log counts,
never contents.
"""

from __future__ import annotations

import re
from datetime import date

from sqlalchemy import select

from ..agents.contracts import SourceRecord, ToolResult
from ..core.permissions import Permission
from ..db.models import (
    BoardReflection,
    Donation,
    EventPlan,
    FinancialRecord,
    HistoricalEvent,
    HistoricalLesson,
    OutreachDraft,
    ResearchFinding,
    VenueCandidate,
)
from ..research import fixtures
from ..services import calculators as calc
from ..services import event_model as em
from ..services.finance import donation_flags
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
            "is_demo": e.is_demo,
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
        data = [{"period": r.period, "kind": r.kind, "category": r.category, "amount_usd": r.amount_usd, "is_demo": r.is_demo} for r in rows]
        demo = any(r["is_demo"] for r in data)
        return ToolResult(tool="read_financial_records", ok=True, summary=f"{len(data)} ledger rows | contents redacted", data=data,
                          sources=[SourceRecord(id="ledger", title="Financial records (synthetic demo books)" if demo else "Financial records",
                                                verification="internal")])

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

    def read_donations() -> ToolResult:
        with db.session() as s:
            rows = s.scalars(select(Donation).where(Donation.organization_id == org).order_by(Donation.received_on)).all()
        data = [{"id": d.id, "donor_name": d.donor_name, "has_email": bool(d.donor_email), "amount_usd": d.amount_usd,
                 "received_on": d.received_on.isoformat(), "method": d.method, "designation": d.designation,
                 "acknowledged": d.acknowledged, "is_demo": d.is_demo} for d in rows]
        return ToolResult(tool="read_donations", ok=True, summary=f"{len(data)} gifts | contents redacted", data=data)

    def flag_donation_issues(donations: list) -> ToolResult:
        with db.session() as s:
            rows = {d.id: d for d in s.scalars(select(Donation).where(Donation.organization_id == org))}
        flagged = []
        for d in donations:
            flags = donation_flags(rows[d["id"]]) if d["id"] in rows else []
            flagged.append({"id": d["id"], "flags": flags, "acknowledged": d["acknowledged"], "amount_band": "250_plus" if d["amount_usd"] >= 250 else "under_250"})
        counts: dict[str, int] = {}
        for f in flagged:
            for flag in f["flags"]:
                key = re.sub(r"\d+ days", "N days", flag)
                counts[key] = counts.get(key, 0) + 1
        return ToolResult(tool="flag_donation_issues", ok=True, data={"per_gift": flagged, "flag_counts": counts},
                          summary=f"{sum(1 for f in flagged if f['flags'])} gifts need attention")

    def create_acknowledgment_drafts(subject: str, body: str, donation_ids: list) -> ToolResult:
        made = 0
        with db.transaction() as s:
            for d in s.scalars(select(Donation).where(Donation.organization_id == org, Donation.id.in_(donation_ids))):
                fill = {"{{donor_name}}": d.donor_name, "{{amount}}": f"${d.amount_usd:,.2f}",
                        "{{date}}": f"{d.received_on:%B} {d.received_on.day}, {d.received_on.year}", "{{designation}}": d.designation}
                text_body, text_subject = body, subject
                for k, v in fill.items():
                    text_body, text_subject = text_body.replace(k, v), text_subject.replace(k, v)
                s.add(OutreachDraft(organization_id=org, run_id=ctx.run_id, agent="donations_compliance",
                                    draft_type="donor_acknowledgment", recipient_name=d.donor_name, recipient_org="",
                                    subject=text_subject[:300], body=text_body, status="draft", created_by=ctx.user_id,
                                    personalization_basis="Merged locally from the donation record; the AI saw only a template.",
                                    is_synthetic_target=d.is_demo))
                made += 1
        return ToolResult(tool="create_acknowledgment_drafts", ok=True, data={"drafts_created": made}, summary=f"{made} acknowledgment drafts")

    add("read_donations", "Read contribution records.", ToolKind.READ, read_donations, Permission.VIEW_DONOR_DATA, sensitive=True)
    add("flag_donation_issues", "Missing-information and acknowledgment flags.", ToolKind.COMPUTE, flag_donation_issues, Permission.VIEW_DONOR_DATA)
    add("create_acknowledgment_drafts", "Merge a template into unsent acknowledgment drafts.", ToolKind.DRAFT, create_acknowledgment_drafts,
        Permission.VIEW_DONOR_DATA, sensitive=True)

    # ── Mission Discovery + Partnerships ─────────────────────────────────────────────

    def search_web(query: str, purpose: str) -> ToolResult:
        if synthetic:
            pool = fixtures.SPONSORS if purpose == "sponsors" else fixtures.ORGANIZATIONS
            kind = "sponsors" if purpose == "sponsors" else "organizations"
            data = [{"source_id": f"synthetic:{kind}:{o['key']}", "title": o["title"], "url": fixtures.fixture_url(kind, o["key"]),
                     "publisher": None, "published": o["published"], "snippet": o["summary"], "category_hint": o["category"]} for o in pool]
            return ToolResult(tool="search_web", ok=True, data=data, summary=f"{len(data)} synthetic results",
                              warnings=["Synthetic research fixtures, not live web research."])
        from ..research.live import live_web_search
        return live_web_search(ctx, query, purpose)

    def fetch_source(url: str, source_id: str, check_values: list | None = None) -> ToolResult:
        if url.startswith("https://example.org/synthetic/"):
            src = SourceRecord(id=source_id, title=url.rsplit("/", 1)[-1], url=url, verification="synthetic", note=fixtures.SYNTHETIC_NOTE)
            return ToolResult(tool="fetch_source", ok=True, data={"verified": False, "synthetic": True}, sources=[src],
                              summary="synthetic fixture (not fetched)")
        if ctx.counters["page_fetches"] >= ctx.settings.max_page_fetches_per_run:
            return ToolResult(tool="fetch_source", ok=False, error="Page-fetch limit for this run reached.",
                              sources=[SourceRecord(id=source_id, title=url, url=url, verification="unverified", note="not fetched: limit")])
        ctx.counters["page_fetches"] += 1
        page = web.fetch_page(url)
        page["figures_found"] = web.figures_on_page(page.pop("text", ""), [float(x) for x in (check_values or [])])
        src = SourceRecord(id=source_id, title=page.get("title") or url, url=url, published=page.get("published"),
                           retrieved_at=page.get("retrieved_at"), verification="verified" if page["ok"] else "unverified",
                           http_status=page.get("http_status"), note=None if page["ok"] else page.get("error"))
        return ToolResult(tool="fetch_source", ok=page["ok"], data=page, sources=[src], error=None if page["ok"] else page.get("error"),
                          summary=f"HTTP {page.get('http_status')} {(page.get('title') or '')[:80]}")

    def classify_mission_alignment(text: str) -> ToolResult:
        low = text.lower()
        hits = {area: [t for t in terms if t in low] for area, terms in MISSION_TERMS.items()}
        score = 2 * len(hits["eating_disorders"]) + 2 * len(hits["mental_health"]) + len(hits["community"])
        label = "high" if hits["eating_disorders"] or score >= 4 else "medium" if score >= 2 else "low" if score else "none"
        return ToolResult(tool="classify_mission_alignment", ok=True, data={"keyword_label": label, "score": score, "matches": hits},
                          summary=f"keyword alignment {label}")

    def save_research_finding(agent: str, category: str, title: str, summary: str, source_url: str | None, source_title: str | None,
                              verification_status: str, alignment: str, uncertainty: str, published: str | None) -> ToolResult:
        with db.transaction() as s:
            row = ResearchFinding(organization_id=org, run_id=ctx.run_id, agent=agent, category=category, title=title[:300],
                                  summary=summary, source_url=source_url, source_title=source_title, verification_status=verification_status,
                                  alignment=alignment, uncertainty=uncertainty, published=published, is_synthetic=verification_status == "synthetic",
                                  retrieved_at=None, saved=False)
            s.add(row)
            s.flush()
            return ToolResult(tool="save_research_finding", ok=True, summary=f"finding #{row.id}", data={"id": row.id})

    def read_saved_findings(categories: list) -> ToolResult:
        with db.session() as s:
            rows = s.scalars(select(ResearchFinding).where(ResearchFinding.organization_id == org, ResearchFinding.category.in_(categories))
                             .order_by(ResearchFinding.saved.desc(), ResearchFinding.created_at.desc()).limit(8)).all()
        data = [{"id": f.id, "title": f.title, "category": f.category, "summary": f.summary, "source_url": f.source_url,
                 "verification": f.verification_status, "saved": f.saved} for f in rows]
        return ToolResult(tool="read_saved_findings", ok=True, data=data, summary=f"{len(data)} findings")

    def create_outreach_draft(draft_type: str, recipient_org: str, subject: str, body: str, personalization_basis: str,
                              is_synthetic_target: bool) -> ToolResult:
        with db.transaction() as s:
            row = OutreachDraft(organization_id=org, run_id=ctx.run_id, agent="partnerships_outreach", draft_type=draft_type,
                                recipient_org=recipient_org[:200], subject=subject[:300], body=body[:6000], status="draft",
                                personalization_basis=personalization_basis[:1000], is_synthetic_target=is_synthetic_target,
                                created_by=ctx.user_id)
            s.add(row)
            s.flush()
            return ToolResult(tool="create_outreach_draft", ok=True, summary=f"draft #{row.id} (unsent)", data={"id": row.id})

    add("search_web", "Bounded web search (or labeled synthetic fixtures).", ToolKind.RESEARCH, search_web)
    add("fetch_source", "Fetch one public page to verify a link (SSRF-guarded).", ToolKind.RESEARCH, fetch_source)
    add("classify_mission_alignment", "Keyword cross-check of mission alignment.", ToolKind.COMPUTE, classify_mission_alignment)
    add("save_research_finding", "Save a research finding with its source.", ToolKind.SAVE, save_research_finding, Permission.RUN_AGENTS)
    add("read_saved_findings", "Read saved research findings.", ToolKind.READ, read_saved_findings, Permission.VIEW_DASHBOARD)
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
