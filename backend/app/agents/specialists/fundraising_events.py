"""Agent 3: Fundraising & Events.

Venue research is bounded and honest:
  * Live mode: one web search. Then each venue's website (and source page) is
    fetched, and every reported price and capacity figure is checked against
    the page text. Figures not found on a fetched page are dropped, so the
    venue shows "Quote required" or "capacity unconfirmed".
  * Synthetic mode: labeled fixtures (example.org), never presented as live.

Every venue-and-format option is priced with the deterministic event model
(services/event_model.py). The model ranks options and writes the strategy,
but it can choose only option IDs the tools produced. On a revision, the
venues already researched are reused (no new search), and a code guard
enforces Finance's limits and the history constraints.
"""

from __future__ import annotations

from ...mission import EVENT_CONSIDERATIONS, PHILOSOPHY
from ...safety.policy import wrap_untrusted
from ..base import BaseAgent
from ..contracts import AgentName, AgentResult, AgentTask, Finding, SourceRecord
from ..outputs import EventStrategyOutput
from ..registry import VENUE_STRATEGY
from ..runtime import RunContext, dedupe_sources

INSTRUCTIONS = """Rank the venue options and write a fundraising strategy for the event.
- Choose only option_id values that appear in "options". Rank 1 = your top recommendation. Shortlist 1 to 3 options.
- Use the computed figures as given; never recompute, adjust, or invent costs, prices, capacity, or availability.
  If pricing_status is "quote_required", say the price must be quoted; the model's venue figure is a hypothetical estimate.
- Respect the board's instructions and the venue restrictions.
- Apply the lessons from past events and say which lesson each choice applies. Lessons are ADVISORY: they shape your
  ranking, strategy, and questions, but they never override computed costs, Finance's limits, or verified source data.
  If a lesson conflicts with current numbers, say so in risks rather than ignoring the numbers.
- If no lessons are provided, plan from the current data alone and do not invent historical claims.
- If "constraints" are present (this is a revision), every shortlisted option must satisfy them; explain what changed and
  why in changes_from_previous, referring to "finance_feedback" (the issues, limits, amounts over, and the cost drivers). If no option satisfies them, rank the closest one and say so plainly in risks.
- fundraising_strategy: practical ideas (ticket tiers, sponsorship asks, paddle raise, in-kind support).
- logistics_notes: timing, guest-count lock, accessibility, volunteers, questions to ask venues.
- uncertainties: anything unconfirmed (availability, quotes, synthetic data).
- mission_contribution: how the shortlisted plan serves the foundation's mission, alongside (never instead of) the
  financial checks: inclusion (price points, format, who might feel left out), connection (moments for guests to meet),
  accessibility (only what the venue data states; otherwise list it as an open question), recognition (volunteers,
  sponsors, participants), and charitable_alignment (mental health, eating disorders, community). Practical, not sentimental.
  community_lessons_applied: which "community_insights" from past events you used, naming the event; [] if none were given.
  Never invent feedback or claim the event will create belonging; describe what the plan makes possible.
  open_questions: what to ask the venue or board to make the event more welcoming."""

GALA_TYPES = ("gala", "dinner", "benefit")
ALL_FORMATS = ["seated_dinner", "reception"]


def _verify_live_venue(agent: BaseAgent, ctx: RunContext, v: dict) -> list[SourceRecord]:
    """Fetch the venue's pages and keep only figures that actually appear on them."""
    reported = {
        "rental_usd": v.get("reported_rental_usd"),
        "fnb_per_guest_usd": v.get("reported_fnb_per_guest_usd"),
        "fnb_minimum_usd": v.get("reported_fnb_minimum_usd"),
        **{f"capacity_{f}": c for f, c in (v.get("capacity") or {}).items()},
    }
    check = [float(x) for x in reported.values() if x is not None]
    found: dict[str, bool] = {}
    sources: list[SourceRecord] = []
    pages = [("website", v.get("website"))]
    if v.get("source_url") and v.get("source_url") != v.get("website"):
        pages.append(("source", v["source_url"]))
    for label, url in pages:
        if not url:
            continue
        res = agent.tool(ctx, "fetch_source", url=url, source_id=f"{v['source_id']}:{label}", check_values=check)
        sources += res.sources
        page = res.data or {}
        if label == "website":
            v["website_status"] = "verified" if res.ok else "unreachable"
            v["verified_at"] = page.get("retrieved_at")
        for key, ok in (page.get("figures_found") or {}).items():
            found[key] = found.get(key, False) or ok
    confirmed = {k: (val is not None and found.get(str(float(val)), False)) for k, val in reported.items()}
    for k in ("rental_usd", "fnb_per_guest_usd", "fnb_minimum_usd"):
        v[k] = v.get(f"reported_{k}") if confirmed[k] else None
    unconfirmed = [k for k, val in reported.items() if val is not None and not confirmed[k]]
    v["pricing_status"] = "published" if (v["rental_usd"] is not None or v["fnb_per_guest_usd"] is not None) else "quote_required"
    caps_ok = [k for k in confirmed if k.startswith("capacity_") and confirmed[k]]
    v["capacity_status"] = "published" if caps_ok else ("unconfirmed" if v.get("capacity") else "not_published")
    v["verification"] = "verified" if v.get("website_status") == "verified" else "unverified"
    if unconfirmed:
        names = ", ".join(k.replace("_usd", "").replace("capacity_", "capacity (").replace("fnb", "catering").replace("_", " ")
                          + (")" if k.startswith("capacity_") else "") for k in unconfirmed)
        v["notes"] = (v.get("notes") or "") + f" Not confirmed on the fetched page, so not used as published: {names}."
    return sources


VENUE_TEXT_FIELDS = ("name", "address", "neighborhood", "notes", "capacity_quote", "pricing_quote", "catering")


def _screen_venue(ctx: RunContext, v: dict, warnings: list[str]) -> None:
    """Venue names, descriptions, amenities, and quotes come from outside sources: screen every text field once.
    Instruction-like sentences are removed and recorded; the rest only ever reaches a model as labeled data."""
    if v.get("screened") or ctx.safety is None:
        return
    found = []
    for k in VENUE_TEXT_FIELDS:
        if isinstance(v.get(k), str) and v[k]:
            v[k], flags = ctx.safety.ingest_untrusted(v[k], f"the description of venue {v.get('venue_key')}", agent="fundraising_events",
                                                       max_chars=1500)
            found += flags
    for k in ("amenities", "restrictions"):
        cleaned = []
        for item in v.get(k) or []:
            text, flags = ctx.safety.ingest_untrusted(str(item), f"venue {v.get('venue_key')} {k}", agent="fundraising_events", max_chars=200)
            found += flags
            if not flags:
                cleaned.append(text)
        v[k] = cleaned
    v["screened"] = True
    if found:
        v["injection_flagged"] = True
        warnings.append(f"{v.get('name') or v.get('venue_key')}: its listing contained instructions aimed at AI systems. They were removed and "
                        "not followed; only the venue facts were used.")


class FundraisingEventsAgent(BaseAgent):
    name = AgentName.FUNDRAISING_EVENTS

    def execute(self, task: AgentTask, ctx: RunContext) -> AgentResult:
        event = task.inputs["event"]
        attendance = int(event.get("attendance") or 100)
        city = event.get("city") or "Manhattan, New York, NY"
        event_type = (event.get("event_type") or "gala").lower()
        revision = task.kind == "revision"
        contingency = task.inputs.get("contingency_pct")
        overrides = task.inputs.get("assumption_overrides") or {}
        finance_limits = {c.name: c for c in task.constraints if c.source_agent == AgentName.FINANCIAL_ANALYSIS}
        avoid_minimum = any(c.name == "avoid_catering_minimum_risk" for c in task.constraints)

        if revision:
            formats = ALL_FORMATS  # a revision may change the format to meet constraints
        elif event.get("event_format"):
            formats = [event["event_format"]]
        else:
            formats = ["seated_dinner"] if any(t in event_type for t in GALA_TYPES) else ["reception"]

        lessons = task.inputs.get("lessons")
        if lessons is None:
            lessons = self.tool(ctx, "get_historical_lessons").data

        warnings: list[str] = []
        sources: list[SourceRecord] = []
        venues = task.inputs.get("candidates")
        if venues is None:  # research once; revisions reuse these candidates
            found = self.tool(ctx, "search_venues", city=city, attendance=attendance, formats=ALL_FORMATS)
            venues = found.data or []
            sources += found.sources
            warnings += found.warnings
            if not found.ok:
                warnings.append(found.error or "Venue search failed.")
            for v in venues:
                if v.get("verification") == "unverified":
                    sources += _verify_live_venue(self, ctx, v)
                _screen_venue(ctx, v, warnings)
        else:
            sources += [SourceRecord(id=f"{v['source_id']}:website", title=v["name"], url=v.get("website"),
                                     verification=v.get("verification") or "unverified", retrieved_at=v.get("verified_at"))
                        for v in venues if v.get("website")]

        options = []
        for v in venues:
            for fmt in [f for f in v.get("formats", []) if f in formats]:
                model = self.tool(ctx, "compute_event_model", venue=v, event_format=fmt, event=event,
                                  contingency_pct=contingency, overrides=overrides).data
                options.append({"option_id": f"{v['venue_key']}:{fmt}", "venue": v, "event_format": fmt, "model": model})
        if not options:
            return self.result(task, "completed", f"No venues found in {city} for {attendance} guests ({', '.join(formats)}).",
                               sources=dedupe_sources(sources), warnings=warnings,
                               next_steps=["Try a different format, city, or guest count, or switch research mode."],
                               data={"venues": venues, "options": [], "shortlist": [], "top_choice": None, "research_mode": ctx.research_mode})

        prompt_options = [{
            "option_id": o["option_id"], "venue": o["venue"]["name"], "neighborhood": o["venue"].get("neighborhood"),
            "format": o["event_format"], "capacity": o["venue"].get("capacity"), "capacity_status": o["venue"].get("capacity_status"),
            "pricing_status": o["venue"].get("pricing_status"), "amenities": o["venue"].get("amenities"),
            "description": wrap_untrusted(o["venue"].get("notes") or "", f"venue listing {o['venue'].get('venue_key')}", max_chars=600),
            "restrictions": o["venue"].get("restrictions"), "catering_terms": o["venue"].get("catering"),
            "total_cost_usd": o["model"]["total_cost_usd"], "total_usd": o["model"]["total_cost_usd"],
            "upfront_cash_usd": o["model"]["upfront_cash_usd"], "base_net_usd": o["model"]["scenarios"]["base"]["net_usd"],
            "conservative_net_usd": o["model"]["scenarios"]["conservative"]["net_usd"],
            "catering_minimum_risk": o["model"].get("catering_minimum_risk"), "missing_inputs": o["model"]["missing_inputs"],
            "assumption_kinds": {k: a["kind"] for k, a in o["model"]["assumptions"].items()},
        } for o in options]
        out = self.think(ctx, VENUE_STRATEGY, INSTRUCTIONS, {
            "event": {k: event.get(k) for k in ("name", "event_type", "city", "attendance", "target_date", "date_end", "ticket_price_usd",
                                                "fundraising_goal_usd", "budget_limit_usd", "instructions")},
            "options": prompt_options, "lessons": lessons,
            "mission": {"philosophy": PHILOSOPHY, "event_considerations": EVENT_CONSIDERATIONS},
            "community_insights": [{k: c.get(k) for k in ("lens_label", "event_names", "observation", "quote", "evidence_label", "reflection_ids")}
                                   for c in task.inputs.get("community_insights") or []],
            "constraints": [c.model_dump(mode="json") for c in task.constraints],
            "previous_shortlist": task.inputs.get("previous_shortlist"),
            "finance_feedback": task.inputs.get("finance_feedback"),
        }, EventStrategyOutput)

        by_id = {o["option_id"]: o for o in options}
        shortlist = []
        for choice in sorted(out.shortlist, key=lambda c: c.rank):
            if choice.option_id not in by_id:
                warnings.append(f"Ignored an option the model invented: {choice.option_id}")
                continue
            shortlist.append({**by_id[choice.option_id], "rank": choice.rank, "rationale": choice.rationale,
                              "lessons_applied": choice.lessons_applied})
        if not shortlist:
            cheapest = min(options, key=lambda o: o["model"]["total_cost_usd"])
            shortlist = [{**cheapest, "rank": 1, "rationale": "Fallback: lowest projected cost (the model's choices were invalid).", "lessons_applied": []}]
            warnings.append("The model's shortlist was invalid; fell back to the lowest-cost option.")

        if revision:  # code guard: the top option must meet Finance's limits and the history constraints if any option can
            max_total = finance_limits.get("max_total_usd")
            max_upfront = finance_limits.get("max_upfront_usd")

            def fits(o: dict) -> bool:
                m = o["model"]
                return ((not max_total or m["total_cost_usd"] <= float(max_total.value)) and
                        (not max_upfront or m["upfront_cash_usd"] <= float(max_upfront.value)) and
                        (not avoid_minimum or not m.get("catering_minimum_risk")))

            if not fits(shortlist[0]):
                fitting = [s for s in shortlist if fits(s)] or sorted((o for o in options if fits(o)), key=lambda o: o["model"]["total_cost_usd"])
                if fitting:
                    best = fitting[0] if "rank" in fitting[0] else {**fitting[0], "rationale": "Lowest-cost option that meets Finance's limits and the history constraints.", "lessons_applied": []}
                    shortlist = [best] + [s for s in shortlist if s["option_id"] != best["option_id"]]
                    for i, s in enumerate(shortlist, start=1):
                        s["rank"] = i
                    warnings.append(f"Re-ranked by code: the model's top choice broke a constraint; {best['venue']['name']} "
                                    f"({best['event_format'].replace('_', ' ')}) meets them.")
                else:
                    warnings.append("No researched option meets every constraint; the closest option is shown for the board.")
        top = shortlist[0]
        contribution = out.mission_contribution.model_dump() if out.mission_contribution else None
        if contribution is not None and not task.inputs.get("community_insights") and contribution["community_lessons_applied"]:
            contribution["community_lessons_applied"] = []  # nothing was provided, so nothing could have been applied
            warnings.append("Removed community lessons the plan claimed to apply: no community insights were provided.")

        plan_id = task.inputs.get("event_plan_id")
        if plan_id:
            for item in shortlist:
                self.tool(ctx, "save_venue_candidate", event_plan_id=plan_id, venue=item["venue"], event_format=item["event_format"],
                          budget_total_usd=item["model"]["total_cost_usd"])

        findings = []
        for s in shortlist:
            price = "published pricing" if s["venue"].get("pricing_status") == "published" else "Quote required (hypothetical estimate used)"
            findings.append(Finding(claim=f"#{s['rank']} {s['venue']['name']} ({s['event_format'].replace('_', ' ')}): projected "
                                          f"${s['model']['total_cost_usd']:,.0f}; {price}. {s['rationale']}",
                                    kind="recommendation", source_ids=[f"{s['venue']['source_id']}:website"]))
        assumptions = sorted({f"{a['basis']}" for s in shortlist for k, a in s["model"]["assumptions"].items()
                              if a["kind"] in ("placeholder", "hypothetical")})
        return self.result(
            task, "completed", out.summary, findings=findings, sources=dedupe_sources(sources), assumptions=assumptions,
            warnings=warnings + out.uncertainties + out.risks,
            next_steps=["Finance re-checks the revised option."] if revision else ["Finance checks affordability of the top option."],
            data={"venues": venues,
                  "options": [{"option_id": o["option_id"], "venue": o["venue"]["name"], "event_format": o["event_format"],
                               "total_usd": o["model"]["total_cost_usd"], "upfront_cash_usd": o["model"]["upfront_cash_usd"],
                               "pricing_status": o["venue"].get("pricing_status")} for o in options],
                  "shortlist": shortlist, "top_choice": top,
                  "fundraising_strategy": out.fundraising_strategy, "logistics_notes": out.logistics_notes,
                  "changes_from_previous": out.changes_from_previous, "research_mode": ctx.research_mode,
                  "mission_contribution": contribution},
        )
