"""Foundation Knowledge Base: what SAM SPACE knows about the Sabrina Audrey Milone Foundation itself.

Board members record facts (identity, signature events, vendors, relationships, community, board, priorities, finance
guidelines, communication preferences). Each fact keeps its source, contributor, dates, and a verification status:

  verified            confirmed by an authorized board member (chair or treasurer) or against a record
  board_reported      a board member said so; not yet checked against records
  estimate            an approximate figure from a board member
  needs_confirmation  mentioned, but uncertain or incomplete
  demo                a labeled sample shipped with the demo workspace

Agents never receive the whole base. retrieve() picks the few facts relevant to one agent's task: only the sections
that agent needs, ranked by overlap with the task text, with facts the Orchestrator already chose placed first.
Everything here is deterministic Python; no model call is made.

Real foundation facts live only in the local database. The repository ships a blank template
(docs/foundation_knowledge_template.json) and a few samples labeled "(sample)".
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import BoardMembership, FinancialRecord, HistoricalEvent, KnowledgeEntry, User
from ..mission import FOUNDATION, PHILOSOPHY

SECTIONS: list[dict[str, Any]] = [
    {"key": "mission_history", "label": "Mission and history",
     "hint": "Who the foundation is, why it exists, and how its story should be told. Only what the board confirms.",
     "fields": [("established", "Established"), ("mission_areas", "Mission areas"), ("story", "Story the board approves")]},
    {"key": "signature_events", "label": "Signature events",
     "hint": "The foundation's recurring events (for example a gala or a community fundraiser): what they are, who comes, what "
             "they cost and raise, and what to keep or change.",
     "fields": [("event_name", "Event name"), ("years_and_dates", "Years and dates"), ("location", "Location"), ("venue", "Venue"),
                ("attendance", "Attendance"), ("ticket_pricing", "Ticket or participation pricing"), ("sponsorships", "Sponsorships"),
                ("catering", "Catering"), ("entertainment", "Entertainment"), ("vendors", "Vendors"), ("volunteers", "Volunteers"),
                ("extras", "Raffles and other fundraising"), ("revenue", "Revenue"), ("expenses", "Expenses"),
                ("net_proceeds", "Net proceeds"), ("feedback", "Board or participant feedback"), ("what_worked", "What worked"),
                ("what_should_change", "What should change"), ("challenges", "Operational challenges")]},
    {"key": "past_fundraisers", "label": "Past fundraisers",
     "hint": "One occurrence of an event (for example the 2025 gala). Link it to its Our Legacy record so figures stay in one place.",
     "fields": [("date", "Date"), ("location", "Location"), ("highlights", "Highlights"), ("figures", "Figures")]},
    {"key": "vendors_venues", "label": "Vendors and venues",
     "hint": "Venues, caterers, entertainment, planners, studios, printers, photographers, sponsors, and community partners the "
             "foundation has used. Mark a vendor as used only when an event record or a board member confirms it.",
     "fields": [("category", "Category"), ("events", "Events it was used for"), ("services", "Services provided"),
                ("contact", "Contact details"), ("previous_costs", "Previous costs"), ("quality", "Quality"),
                ("reliability", "Reliability"), ("lessons", "Lessons learned"), ("relationship_status", "Current relationship status")]},
    {"key": "relationships", "label": "Charitable relationships",
     "hint": "Organizations the foundation has worked with or featured. Keep historical collaboration separate from a formal, "
             "ongoing partnership.",
     "fields": [("website", "Website"), ("organization_mission", "Organization's mission"),
                ("relationship_type", "Relationship type"), ("nature", "Nature of the relationship"),
                ("activities", "Events or activities connected to it"), ("verified_contacts", "Verified contacts"),
                ("records", "Correspondence or records"), ("date_last_confirmed", "Date last confirmed"),
                ("future_opportunities", "Possible future collaboration")]},
    {"key": "community_audience", "label": "Community and audience",
     "hint": "Hometown roots, who usually comes to events, networks, volunteers, supporters, and prospective sponsors. No "
             "statistics or assumptions about anyone's health.",
     "fields": [("group", "Group"), ("connection", "Connection to the foundation"), ("involvement", "Typical involvement")]},
    {"key": "board", "label": "Board structure",
     "hint": "Board members, roles, committees, and what each would like to review. Contact details are shown only to the chair.",
     "fields": [("role", "Role"), ("committee", "Committee or responsibilities"), ("reviews", "Reviews these kinds of work"),
                ("event_involvement", "Event involvement"), ("expertise", "Relevant expertise"), ("tasks", "Tasks assigned"),
                ("preferred_involvement", "Preferred involvement"), ("contact", "Contact (chair only)")]},
    {"key": "fundraising_priorities", "label": "Fundraising priorities",
     "hint": "Goals for the year, what the board wants events to achieve, and campaigns.",
     "fields": [("year", "Year"), ("goal", "Goal"), ("priority", "Priority")]},
    {"key": "financial_guidelines", "label": "Financial guidelines",
     "hint": "Board-approved budgets, typical event cost ranges, reserve and restricted-fund rules. Say which kind of figure each is.",
     "fields": [("dataset", "Kind of figure"), ("amount", "Amount"), ("period", "Period"), ("rule", "Guideline")]},
    {"key": "communication", "label": "Communication preferences",
     "hint": "How the foundation introduces itself, tone, and what to include or avoid in letters and outreach.",
     "fields": [("audience", "Audience"), ("preference", "Preference"), ("example_language", "Example wording")]},
]
SECTION_KEYS = [s["key"] for s in SECTIONS]
SECTION_LABELS = {s["key"]: s["label"] for s in SECTIONS}
FIELD_LABELS = {s["key"]: dict(s["fields"]) for s in SECTIONS}

VERIFICATION = {
    "verified": "Verified",
    "board_reported": "Board-reported",
    "estimate": "Approximate",
    "needs_confirmation": "Needs confirmation",
    "demo": "Sample",
}
DATASETS = {  # the four kinds of financial information the Finance agent must keep apart
    "demo": "Synthetic demonstration data",
    "verified_history": "Verified historical information",
    "board_estimate": "Approximate board-provided estimate",
    "authorized_budget": "Current authorized budget",
}

# Which sections each agent may draw on. Primary sections rank higher for that agent.
AGENT_SECTIONS: dict[str, tuple[str, ...]] = {
    "orchestrator": tuple(SECTION_KEYS),
    "mission_discovery": ("mission_history", "relationships", "fundraising_priorities", "community_audience"),
    "fundraising_events": ("signature_events", "past_fundraisers", "vendors_venues", "community_audience", "fundraising_priorities",
                           "financial_guidelines"),
    "financial_analysis": ("financial_guidelines", "fundraising_priorities", "signature_events", "past_fundraisers"),
    "donations_compliance": ("fundraising_priorities", "relationships", "communication", "financial_guidelines"),
    "partnerships_outreach": ("mission_history", "relationships", "signature_events", "communication", "community_audience",
                              "vendors_venues"),
    "event_intelligence": ("signature_events", "past_fundraisers", "vendors_venues", "relationships", "community_audience"),
}
PRIMARY: dict[str, tuple[str, ...]] = {
    "orchestrator": ("mission_history", "fundraising_priorities", "board"),
    "mission_discovery": ("relationships",),
    "fundraising_events": ("signature_events", "vendors_venues", "community_audience"),
    "financial_analysis": ("financial_guidelines",),
    "donations_compliance": ("communication", "fundraising_priorities"),
    "partnerships_outreach": ("mission_history", "communication", "relationships"),
    "event_intelligence": ("signature_events", "past_fundraisers"),
}
CORE_AGENTS = ("orchestrator", "mission_discovery", "partnerships_outreach")  # always get the foundation's identity
ALWAYS = {"financial_analysis": ("financial_guidelines",)}  # rules, not topics: Finance always sees them
HIDDEN_FIELDS = {"board": ("contact",)}  # never sent to a model; shown in the app to the chair only

STOP = set("""the and for with that this from into your our are was were will would should could have has had not but all any can
about what when where which who whom why how than then them they their there these those its it's also more most such only own
same some very just plan plans planning event events foundation board please help want need make like next year years future new
our ours ask asking find research draft drafts review using use used""".split())


# Generic event words that mean the same kind of event, so "plan a gala" also finds a recorded benefit dinner.
SYNONYMS = [
    {"gala", "benefit", "dinner", "ball"},
    {"spin", "cycling", "cycle", "ride", "bike", "studio", "class"},
    {"tournament", "field", "team", "game", "sport", "league"},
    {"walk", "run", "5k", "race"},
    {"venue", "space", "hall", "ballroom"},
    {"caterer", "catering", "food", "menu"},
    {"band", "music", "dj", "entertainment"},
    {"sponsor", "sponsorship", "underwriter"},
    {"donation", "gift", "donor", "acknowledgment"},
    {"budget", "cost", "expense", "spend", "afford"},
]


def expand(words: set[str]) -> set[str]:
    out = set(words)
    for group in SYNONYMS:
        if words & group:
            out |= group
    return out


def _now() -> datetime:
    return datetime.now(timezone.utc)


def terms(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9][a-z0-9&'-]*", (text or "").lower())
    out = set()
    for w in words:
        w = w.strip("'-")
        if len(w) < 3 or w in STOP:
            continue
        out.add(w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w)
    return out


def _norm_name(text: str) -> str:
    text = re.sub(r"\((synthetic|sample)\)", "", (text or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _domain(url: str | None) -> str | None:
    m = re.match(r"^(?:https?://)?(?:www\.)?([^/:?#]+)", (url or "").strip().lower())
    return m.group(1) if m and "." in m.group(1) else None


def entry_text(e: KnowledgeEntry, *, include_hidden: bool = False) -> str:
    """The fact as one compact line: narrative first, then the filled-in structured fields."""
    labels = FIELD_LABELS.get(e.section, {})
    hidden = () if include_hidden else HIDDEN_FIELDS.get(e.section, ())
    parts = [e.body.strip()] if (e.body or "").strip() else []
    for key, value in (e.details or {}).items():
        if key in hidden or value in (None, "", []):
            continue
        value = "; ".join(map(str, value)) if isinstance(value, list) else str(value)
        parts.append(f"{labels.get(key, key.replace('_', ' ').capitalize())}: {value}")
    return " | ".join(parts)


def active_entries(db: Session, organization_id: int) -> list[KnowledgeEntry]:
    rows = db.scalars(select(KnowledgeEntry).where(KnowledgeEntry.organization_id == organization_id,
                                                   KnowledgeEntry.status == "active").order_by(KnowledgeEntry.id)).all()
    real_sections = {e.section for e in rows if not e.is_demo}
    # Samples only stand in for a section the board has not filled yet; real knowledge always replaces them.
    return [e for e in rows if not (e.is_demo and e.section in real_sections)]


def fact_out(e: KnowledgeEntry, max_chars: int = 600) -> dict:
    text = entry_text(e)
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "…"
    return {"id": f"KB-{e.id}", "section": SECTION_LABELS.get(e.section, e.section), "section_key": e.section, "title": e.title, "fact": text,
            "verification": e.verification, "source": e.source or "not recorded",
            "updated": (e.updated_at or e.recorded_at).date().isoformat() if (e.updated_at or e.recorded_at) else None,
            "shareable_in_outreach": bool(e.share_externally), "sample": bool(e.is_demo)}


def _score(e: KnowledgeEntry, query: set[str], agent: str, raw_query: str, related: set[str] = frozenset()) -> float:
    """Word overlap with the task (title words count double); words that only mean the same kind of event count half."""
    title_terms = terms(e.title)
    body_terms = terms(entry_text(e)) | {t for a in (e.aliases or []) for t in terms(str(a))}
    score = 2.0 * len(query & title_terms) + len(query & (body_terms - title_terms))
    score += 0.5 * (2 * len(related & title_terms) + len(related & (body_terms - title_terms)))
    q = _norm_name(raw_query)
    for name in [e.title] + list(e.aliases or []):
        n = _norm_name(str(name))
        if len(n) >= 4 and re.search(rf"\b{re.escape(n)}\b", q):
            score += 4.0  # the task names this organization, vendor, or event
    if score > 0 and e.section in PRIMARY.get(agent, ()):
        score += 1.5
    if score > 0 and e.verification == "verified":
        score += 0.5
    return score


def retrieve(db: Session, organization_id: int, *, agent: str, query: str, include_ids: Iterable[int] = (), limit: int = 6) -> dict:
    """The few facts one agent needs for one task, with retrieval statistics for the trace and the tokenomics."""
    sections = AGENT_SECTIONS.get(agent, ())
    pool = [e for e in active_entries(db, organization_id) if e.section in sections]
    q = terms(query)
    related = expand(q) - q
    chosen: list[KnowledgeEntry] = []
    why: dict[int, str] = {}

    def take(e: KnowledgeEntry, reason: str) -> None:
        if e not in chosen and len(chosen) < limit:
            chosen.append(e)
            why[e.id] = reason

    if agent in CORE_AGENTS:
        for e in pool:
            if e.section == "mission_history" and (e.details or {}).get("core"):
                take(e, "the foundation's identity")
    for e in pool:
        if e.section in ALWAYS.get(agent, ()):
            take(e, "a standing guideline for this agent")
    wanted = set(include_ids)
    for e in pool:
        if e.id in wanted:
            take(e, "passed on by the Orchestrator")
    ranked = sorted(((s, e) for e in pool if (s := _score(e, q, agent, query, related)) >= 1), key=lambda p: (-p[0], p[1].id))
    for s, e in ranked:
        take(e, f"matches the task (score {s:g})")
    facts = [fact_out(e) | {"why": why[e.id]} for e in chosen]
    chars = sum(len(f["fact"]) + len(f["title"]) for f in facts)
    return {"facts": facts, "agent": agent, "considered": len(pool), "returned": len(facts),
            "sections": sorted({f["section"] for f in facts}), "chars": chars, "est_tokens": (chars + 3) // 4,
            "query_terms": sorted(q)[:20]}


def match_relationship(entries: Iterable[KnowledgeEntry], name: str | None, website: str | None = None,
                       sections: tuple[str, ...] = ("relationships",)) -> KnowledgeEntry | None:
    """The recorded relationship (or past vendor) for an organization, recognized by name, alias (e.g. an acronym), or
    website domain."""
    n, dom = _norm_name(name or ""), _domain(website)
    for e in entries:
        if e.section not in sections:
            continue
        if dom and dom == _domain((e.details or {}).get("website")):
            return e
        for cand in [e.title] + list(e.aliases or []):
            c = _norm_name(str(cand))
            if not c or not n:
                continue
            if len(c) <= 6:  # an acronym must appear as a whole word
                if re.search(rf"\b{re.escape(c)}\b", n):
                    return e
            elif c == n or (len(c) >= 8 and (c in n or n in c)):
                return e
    return None


def relationship_note(e: KnowledgeEntry) -> dict:
    d = e.details or {}
    if e.section == "vendors_venues":
        d = {**d, "relationship_type": d.get("relationship_status") or "past vendor",
             "nature": d.get("services") or e.body, "activities": d.get("events")}
    kind = (d.get("relationship_type") or "historical collaboration").replace("_", " ")
    return {"entry_id": f"KB-{e.id}", "organization": e.title, "relationship_type": kind, "nature": d.get("nature") or e.body,
            "activities": d.get("activities"), "verification": e.verification, "date_last_confirmed": d.get("date_last_confirmed"),
            "formal_partnership": "formal" in kind.lower() and "no formal" not in kind.lower() and "not a formal" not in kind.lower(),
            "summary": f"Already known to the foundation ({kind}, {VERIFICATION.get(e.verification, e.verification).lower()}): "
                       f"{(d.get('nature') or e.body or '').strip()}"[:400]}


REVIEW_TOPICS = {
    "plan_event": ("event", "gala", "fundrais", "venue"),
    "financial_review": ("financ", "treasur", "budget", "money"),
    "donations_review": ("donat", "acknowledg", "treasur", "donor"),
    "partnership_outreach": ("partner", "outreach", "mission", "program", "relationship"),
    "mission_discovery": ("mission", "program", "partner", "research"),
    "event_learning": ("event", "history", "legacy"),
}
ROLE_FOR_INTENT = {"financial_review": "treasurer", "donations_review": "treasurer"}


def suggest_reviewers(db: Session, organization_id: int, intent: str) -> dict:
    """Who should review this kind of recommendation: board-directory responsibilities first, then app roles. A suggestion only:
    nothing is assigned, and no one is committed to anything."""
    topics = REVIEW_TOPICS.get(intent, ())
    board = [e for e in active_entries(db, organization_id) if e.section == "board"]
    picks = []
    for e in board:
        d = e.details or {}
        text = " ".join(str(d.get(k) or "") for k in ("role", "committee", "reviews", "tasks", "preferred_involvement")).lower()
        if any(t in text for t in topics):
            picks.append({"name": e.title, "role": d.get("role") or "Board member", "basis": f"Board directory (KB-{e.id})",
                          "sample": e.is_demo})
    if picks:
        return {"reviewers": picks[:2], "note": "Suggested from the board directory. A suggestion only; nothing has been assigned."}
    want = ROLE_FOR_INTENT.get(intent, "chair")
    rows = db.execute(select(User.first_name, User.last_name, BoardMembership.role, BoardMembership.title)
                      .join(BoardMembership, BoardMembership.user_id == User.id)
                      .where(BoardMembership.organization_id == organization_id)).all()
    fallback = [r for r in rows if r.role == want] or [r for r in rows if r.role == "chair"]
    return {"reviewers": [{"name": f"{r.first_name} {r.last_name}".strip(), "role": r.title or r.role.title(),
                           "basis": "App board role (no responsibilities recorded in the board directory)", "sample": False}
                          for r in fallback[:1]],
            "note": "No board member's responsibilities are recorded for this kind of work yet, so this is based on app roles. "
                    "Add responsibilities in Settings → Foundation Knowledge Base."}


def private_terms(db: Session, organization_id: int) -> list[str]:
    """Board names and contact details from the directory: never sent to a web search."""
    out = []
    for e in db.scalars(select(KnowledgeEntry).where(KnowledgeEntry.organization_id == organization_id,
                                                     KnowledgeEntry.section == "board")):
        out.append(e.title)
        contact = (e.details or {}).get("contact")
        if contact:
            out += [c.strip() for c in re.split(r"[;,]", str(contact)) if c.strip()]
    return [t for t in out if len(t) >= 3]


MONEY = re.compile(r"\$\s?\d")
LEDGER_STATEMENTS = {
    "demo": "The books in SAM SPACE (cash, reserve, income, expenses) are synthetic demonstration data, not the foundation's "
            "real accounts. Any affordability figure computed from them is a practice figure.",
    "mixed": "The books mix synthetic demonstration rows with entered records; treat computed balances as provisional.",
    "real": "The books hold records entered by the board.",
    "none": "No financial records are entered, so no balance can be computed.",
}


def classify_financial_sources(records: Iterable[dict], facts: Iterable[dict], event_budget_usd: float | None = None) -> dict:
    """Sort the financial information a task can lean on into the four kinds the board must keep apart. Pure function over
    ledger rows (is_demo, verification) and knowledge facts (id, title, fact, verification, section_key)."""
    keys = {v: k for k, v in SECTION_LABELS.items()}
    records = list(records)
    facts = [{**f, "section_key": f.get("section_key") or keys.get(f.get("section"))} for f in facts]
    demo_rows = sum(1 for r in records if r.get("is_demo"))
    verified_rows = sum(1 for r in records if not r.get("is_demo") and r.get("verification") == "board_reviewed")
    other_rows = len(records) - demo_rows - verified_rows
    money = [f for f in facts if f.get("section_key") in ("financial_guidelines", "signature_events", "past_fundraisers")
             and MONEY.search(f.get("fact") or "")]
    label = lambda f: f"{f['id']} {f['title']}"  # noqa: E731
    kind = "demo" if demo_rows and not (verified_rows or other_rows) else "mixed" if demo_rows else "real" if records else "none"
    return {
        "ledger": {"kind": kind, "demo_rows": demo_rows, "verified_rows": verified_rows, "other_rows": other_rows,
                   "statement": LEDGER_STATEMENTS[kind]},
        "verified_history": [label(f) for f in money if f.get("verification") == "verified"],
        "board_estimates": [label(f) for f in money if f.get("verification") in ("estimate", "board_reported", "needs_confirmation")],
        "authorized_budgets": [label(f) for f in facts if "authorized" in (f.get("fact") or "").lower() and f.get("section_key") ==
                               "financial_guidelines"] + ([f"This event's board-set maximum: ${event_budget_usd:,.0f}"]
                                                          if event_budget_usd else []),
        "rule": "Never infer the foundation's current available funds from historical event costs or board estimates.",
    }


def financial_sources(db: Session, organization_id: int, event_budget_usd: float | None = None) -> dict:
    """The same classification over everything recorded in a workspace (for the Knowledge Base page)."""
    recs = [{"is_demo": r.is_demo, "verification": r.verification} for r in
            db.scalars(select(FinancialRecord).where(FinancialRecord.organization_id == organization_id))]
    facts = [fact_out(e, max_chars=2000) for e in active_entries(db, organization_id)]
    out = classify_financial_sources(recs, facts, event_budget_usd)
    out["verified_history"] += [f"Our Legacy: {n}" for n in db.scalars(select(HistoricalEvent.name).where(
        HistoricalEvent.organization_id == organization_id, HistoricalEvent.verification_status == "verified"))]
    return out


def gaps(db: Session, organization_id: int) -> list[dict]:
    """Missing information the board could add, computed from what is (and is not) recorded."""
    rows = active_entries(db, organization_id)
    real = [e for e in rows if not e.is_demo]
    out = []
    for s in SECTIONS:
        if not any(e.section == s["key"] for e in real):
            out.append({"section": s["label"], "detail": f"Nothing recorded yet for {s['label'].lower()}."})
    wanted = {
        "signature_events": ("attendance", "revenue", "expenses", "net_proceeds", "ticket_pricing"),
        "past_fundraisers": ("figures",),
        "vendors_venues": ("contact", "previous_costs", "relationship_status"),
        "relationships": ("organization_mission", "verified_contacts", "date_last_confirmed"),
        "board": ("role", "reviews"),
    }
    for e in real:
        missing = [FIELD_LABELS[e.section][k].lower() for k in wanted.get(e.section, ()) if not (e.details or {}).get(k)]
        if missing:
            out.append({"section": SECTION_LABELS[e.section], "entry_id": e.id,
                        "detail": f"{e.title}: {', '.join(missing)} not recorded."})
    if any(e.section == "fundraising_priorities" for e in real) and not any(
            (e.details or {}).get("goal") for e in real if e.section == "fundraising_priorities"):
        out.append({"section": SECTION_LABELS["fundraising_priorities"], "detail": "No fundraising goal for this year is recorded."})
    if any(e.section == "financial_guidelines" for e in real) and not any(
            (e.details or {}).get("dataset") == "authorized_budget" for e in real if e.section == "financial_guidelines"):
        out.append({"section": SECTION_LABELS["financial_guidelines"], "detail": "No board-approved budget or spending guideline is recorded."})
    unconfirmed = [e for e in real if e.verification != "verified"]
    if unconfirmed:
        out.append({"section": "Verification", "detail": f"{len(unconfirmed)} of {len(real)} facts are not yet verified by the chair "
                                                         "or treasurer."})
    if financial_sources(db, organization_id)["ledger"]["kind"] in ("demo", "none"):
        out.append({"section": "Financial guidelines", "detail": "The foundation's actual cash, revenue, and reserves are not in "
                                                                "SAM SPACE; the books are demo data."})
    return out


# ── Seed: the public identity (already in the repository) and a few labeled samples ───────────────────────────────────

def _entry(org_id: int, section: str, title: str, body: str, *, details: dict | None = None, aliases: list | None = None,
           source: str, verification: str, share: bool = False, demo: bool = False, event_id: int | None = None) -> KnowledgeEntry:
    return KnowledgeEntry(organization_id=org_id, section=section, title=title, body=body, details=details, aliases=aliases,
                          source=source, contributor="SAM SPACE setup", verification=verification, share_externally=share,
                          is_demo=demo, historical_event_id=event_id, updated_by="SAM SPACE setup")


def seed_knowledge(db: Session, organization_id: int) -> int:
    """Add the starting entries to a workspace that has none. Never touches an existing knowledge base."""
    if db.scalar(select(KnowledgeEntry.id).where(KnowledgeEntry.organization_id == organization_id).limit(1)) is not None:
        return 0
    cfg = "SAM SPACE mission configuration (backend/app/mission.py)"
    rows = [
        _entry(organization_id, "mission_history", "Foundation identity",
               f"The {FOUNDATION['name']} ({FOUNDATION['short_name']}). {FOUNDATION['established']}",
               details={"core": True}, source=cfg, verification="board_reported", share=True),
        _entry(organization_id, "mission_history", "Guiding philosophy", f"“{PHILOSOPHY}”", details={"core": True},
               source=cfg, verification="board_reported", share=True),
        _entry(organization_id, "mission_history", "Mission areas", "", details={"core": True,
               "mission_areas": FOUNDATION["purpose_areas"]}, source=cfg, verification="board_reported", share=True),
    ]
    dinner = db.scalar(select(HistoricalEvent).where(HistoricalEvent.organization_id == organization_id,
                                                     HistoricalEvent.name == "Butterfly Benefit Dinner (sample)"))
    sample = "Demo workspace sample (invented)"
    rows += [
        _entry(organization_id, "signature_events", "Butterfly Benefit Dinner (sample)",
               "Sample seated benefit dinner with a recovery speaker and a silent auction.",
               details={"event_name": "Butterfly Benefit Dinner (sample)", "years_and_dates": "October 2025 (sample)",
                        "location": "Greenwich, CT (sample)", "venue": "Harbor Club Dining Room (sample)", "attendance": "95 (sample)",
                        "what_worked": "A personal recovery speaker; strong auction pledges (sample).",
                        "what_should_change": "Lock the guest count two weeks out; collect pledges at the table (sample)."},
               source=sample, verification="demo", demo=True, event_id=dinner.id if dinner else None),
        _entry(organization_id, "vendors_venues", "Harbor Club Dining Room (sample)", "Sample venue for the sample benefit dinner.",
               details={"category": "Event venue", "events": "Butterfly Benefit Dinner (sample)",
                        "lessons": "The food-and-beverage minimum applied on top of a per-head price change (sample).",
                        "relationship_status": "Past venue (sample); no current agreement"},
               source=sample, verification="demo", demo=True),
        _entry(organization_id, "relationships", "Nourish NY Eating Disorder Research Network (synthetic)",
               "Sample: the foundation shared this network's research summary at the sample benefit dinner.",
               details={"relationship_type": "historical collaboration", "nature": "Featured its research at a past event (sample).",
                        "activities": "Butterfly Benefit Dinner (sample)"},
               aliases=["Nourish NY"], source=sample, verification="demo", demo=True),
    ]
    db.add_all(rows)
    return len(rows)


# ── Template import (the local loader script and the editor's import both use this) ───────────────────────────────────

def template() -> dict:
    return {
        "about": "Blank Foundation Knowledge Base template. Fill in entries and import them in Settings → Foundation Knowledge Base "
                 "(or with python -m backend.scripts.load_foundation_profile FILE). Keep the filled-in file out of git.",
        "verification_values": VERIFICATION,
        "sections": {s["key"]: {"label": s["label"], "hint": s["hint"], "fields": dict(s["fields"])} for s in SECTIONS},
        "entries": [{"section": "signature_events", "title": "", "body": "", "details": {k: "" for k, _ in SECTIONS[1]["fields"]},
                     "aliases": [], "source": "", "contributor": "", "verification": "board_reported", "share_externally": False}],
    }


def import_entries(db: Session, organization_id: int, entries: list[dict], *, contributor: str, can_verify: bool) -> dict:
    """Add or update entries by (section, title). Only the chair or treasurer may import facts as verified."""
    existing = {(e.section, e.title.lower()): e for e in db.scalars(select(KnowledgeEntry).where(
        KnowledgeEntry.organization_id == organization_id, KnowledgeEntry.is_demo.is_(False)))}
    added = updated = 0
    for item in entries:
        section, title = item.get("section"), (item.get("title") or "").strip()
        if section not in SECTION_KEYS or not title:
            continue
        verification = item.get("verification") or "board_reported"
        if verification not in VERIFICATION or verification == "demo" or (verification == "verified" and not can_verify):
            verification = "board_reported"
        row = existing.get((section, title.lower()))
        if row is None:
            row = KnowledgeEntry(organization_id=organization_id, section=section, title=title[:200], recorded_at=_now())
            db.add(row)
            existing[(section, title.lower())] = row
            added += 1
        else:
            updated += 1
        row.body = (item.get("body") or "").strip()
        row.details = {k: v for k, v in (item.get("details") or {}).items() if v not in (None, "", [])} or None
        row.aliases = [a for a in item.get("aliases") or [] if a] or None
        row.source = (item.get("source") or "")[:300]
        row.source_url = item.get("source_url") or None
        row.contributor = (item.get("contributor") or contributor)[:120]
        row.verification = verification
        row.share_externally = bool(item.get("share_externally"))
        row.historical_event_id = item.get("historical_event_id")
        row.verified_by, row.verified_at = ((item.get("verified_by") or contributor)[:120], _now()) if verification == "verified" else (None, None)
        row.status, row.updated_at, row.updated_by = "active", _now(), contributor
    return {"added": added, "updated": updated}
