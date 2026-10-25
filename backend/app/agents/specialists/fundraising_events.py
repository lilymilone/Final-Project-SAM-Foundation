"""Agent 3: Fundraising & Events.

Finds venues (labeled synthetic fixtures, or live web search with links
verified by fetching them). Prices every venue-and-format option with the
deterministic budget calculator, and pulls revenue scenarios from past
events. The model then ranks the options and writes the fundraising strategy,
but it can only choose option IDs the tools produced. On a revision it must
respect the constraints the Orchestrator passes back from Finance and
Event Intelligence.
"""

from __future__ import annotations

from ..base import BaseAgent
from ..contracts import AgentName, AgentResult, AgentTask, Finding, SourceRecord
from ..outputs import EventStrategyOutput
from ..registry import VENUE_STRATEGY
from ..runtime import RunContext, dedupe_sources

INSTRUCTIONS = """Rank the venue options and write a fundraising strategy for the event.
- Choose only option_id values that appear in "options". Rank 1 = your top recommendation. Shortlist 1 to 3 options.
- Use the computed budgets as given; do not recompute or invent costs.
- Apply the lessons from past events and say which lesson each choice applies. Lessons are ADVISORY: they shape your
  ranking, strategy, and questions, but they never override the computed costs, Finance's limits, or verified source data.
  If a lesson conflicts with current numbers, say so in risks rather than ignoring the numbers.
- If no lessons are provided, plan from the current data alone and do not invent historical claims.
- If "constraints" are present (this is a revision), every shortlisted option must satisfy them; explain what changed in
  changes_from_previous. If no option satisfies them, rank the closest one and say so plainly in risks.
- fundraising_strategy: practical ideas (ticket tiers, sponsorship asks, paddle raise, in-kind support).
- logistics_notes: timing, guest-count lock, accessibility, volunteers.
- uncertainties: anything unconfirmed (availability, real quotes, synthetic data)."""

GALA_TYPES = {"gala", "dinner", "benefit"}


class FundraisingEventsAgent(BaseAgent):
    name = AgentName.FUNDRAISING_EVENTS

    def execute(self, task: AgentTask, ctx: RunContext) -> AgentResult:
        event = task.inputs["event"]
        attendance = int(event.get("attendance") or 100)
        city = event.get("city") or "Manhattan, New York, NY"
        event_type = (event.get("event_type") or "gala").lower()
        revision = task.kind == "revision"
        # Hard spending limits are taken only from Financial Analysis; history is advisory.
        constraint_map = {c.name: c for c in task.constraints if c.source_agent == AgentName.FINANCIAL_ANALYSIS}
        contingency = task.inputs.get("contingency_pct")

        if revision:
            formats = ["seated_dinner", "reception"]  # a revision may change the format to meet constraints
        elif event.get("event_format"):
            formats = [event["event_format"]]
        else:
            formats = ["seated_dinner"] if any(t in event_type for t in GALA_TYPES) else ["reception"]

        lessons = task.inputs.get("lessons")
        if lessons is None:
            lessons = self.tool(ctx, "get_historical_lessons").data

        found = self.tool(ctx, "search_venues", city=city, attendance=attendance, formats=formats)
        venues = found.data or []
        sources: list[SourceRecord] = list(found.sources)
        warnings = list(found.warnings)
        if not found.ok:
            warnings.append(found.error or "Venue search failed.")

        # Live results: verify each link by fetching it.
        for v in venues:
            if v.get("verification") == "unverified" and v.get("source_url"):
                check = self.tool(ctx, "fetch_source", url=v["source_url"], source_id=v["source_id"])
                if check.sources:
                    sources = [s for s in sources if s.id != v["source_id"]] + check.sources
                    v["verification"] = check.sources[0].verification

        options = []
        for v in venues:
            for fmt in v["formats"]:
                budget = self.tool(ctx, "compute_event_budget", venue=v, event_format=fmt, attendance=attendance,
                                   contingency_pct=contingency).data
                options.append({"option_id": f"{v['venue_key']}:{fmt}", "venue": v, "event_format": fmt, "budget": budget})
        if not options:
            return self.result(task, "completed", f"No venues found in {city} for {attendance} guests ({', '.join(formats)}).",
                               sources=dedupe_sources(sources), warnings=warnings,
                               next_steps=["Try live web research or a different format, city, or guest count."],
                               data={"options": [], "shortlist": [], "top_choice": None})

        revenue = self.tool(ctx, "compute_revenue_scenarios", attendance=attendance, event_type=event_type)
        prompt_options = [{
            "option_id": o["option_id"], "venue": o["venue"]["name"], "neighborhood": o["venue"].get("neighborhood"),
            "format": o["event_format"], "capacity": o["venue"].get("capacity"), "notes": o["venue"].get("notes"),
            "catering_terms": o["venue"].get("catering"),
            "source": o["venue"].get("verification"), "total_usd": o["budget"]["total_usd"],
            "upfront_cash_usd": o["budget"]["upfront_cash_usd"], "cost_per_guest_usd": o["budget"]["cost_per_guest_usd"],
            "assumptions": o["budget"]["assumptions"],
        } for o in options]
        out = self.think(ctx, VENUE_STRATEGY, INSTRUCTIONS, {
            "event": event, "options": prompt_options, "revenue_scenarios": revenue.data, "lessons": lessons,
            "constraints": [c.model_dump(mode="json") for c in task.constraints],
            "previous_shortlist": task.inputs.get("previous_shortlist"),
        }, EventStrategyOutput)

        by_id = {o["option_id"]: o for o in options}
        shortlist = []
        for choice in sorted(out.shortlist, key=lambda c: c.rank):
            if choice.option_id not in by_id:
                warnings.append(f"Ignored an option the model invented: {choice.option_id}")
                continue
            o = by_id[choice.option_id]
            shortlist.append({**o, "rank": choice.rank, "rationale": choice.rationale, "lessons_applied": choice.lessons_applied})
        if not shortlist:  # model chose nothing valid: fall back to the cheapest option, and say so
            cheapest = min(options, key=lambda o: o["budget"]["total_usd"])
            shortlist = [{**cheapest, "rank": 1, "rationale": "Fallback: lowest projected total (the model's choices were invalid).",
                          "lessons_applied": []}]
            warnings.append("The model's shortlist was invalid; fell back to the lowest-cost option.")

        # Deterministic guard on a revision: if the model's top pick still breaks
        # Finance's hard limits but another option meets them, re-rank in code.
        if revision:
            max_total = constraint_map.get("max_total_usd")
            max_upfront = constraint_map.get("max_upfront_usd")

            def fits(o: dict) -> bool:
                return ((not max_total or o["budget"]["total_usd"] <= float(max_total.value)) and
                        (not max_upfront or o["budget"]["upfront_cash_usd"] <= float(max_upfront.value)))

            if not fits(shortlist[0]):
                fitting = [s for s in shortlist if fits(s)] or sorted((o for o in options if fits(o)), key=lambda o: o["budget"]["total_usd"])
                if fitting:
                    best = fitting[0]
                    best = best if "rank" in best else {**best, "rationale": "Lowest-cost option that meets Finance's limits.",
                                                        "lessons_applied": []}
                    shortlist = [best] + [s for s in shortlist if s["option_id"] != best["option_id"]]
                    for i, s in enumerate(shortlist, start=1):
                        s["rank"] = i
                    warnings.append(f"Re-ranked by code: the model's top choice broke Finance's limits; "
                                    f"{best['venue']['name']} ({best['event_format'].replace('_', ' ')}) meets them.")
                else:
                    warnings.append("No researched option meets Finance's limits; the closest option is shown for the board.")
        top = shortlist[0]

        plan_id = task.inputs.get("event_plan_id")
        if plan_id:
            for item in shortlist:
                self.tool(ctx, "save_venue_candidate", event_plan_id=plan_id, venue=item["venue"],
                          event_format=item["event_format"], budget_total_usd=item["budget"]["total_usd"])

        findings = [Finding(claim=f"#{s['rank']} {s['venue']['name']} ({s['event_format'].replace('_', ' ')}): "
                                  f"projected ${s['budget']['total_usd']:,.0f}. {s['rationale']}",
                            kind="recommendation", source_ids=[s["venue"]["source_id"]]) for s in shortlist]
        assumptions = sorted({a for s in shortlist for a in s["budget"]["assumptions"]})
        if revenue.data and revenue.data.get("assumptions"):
            assumptions += revenue.data["assumptions"]
        return self.result(
            task, "completed", out.summary, findings=findings, sources=dedupe_sources(sources + revenue.sources),
            assumptions=assumptions, warnings=warnings + out.uncertainties + out.risks,
            next_steps=["Finance checks affordability of the top option."] if not revision else ["Finance re-checks the revised option."],
            data={"options": [{"option_id": o["option_id"], "venue": o["venue"]["name"], "event_format": o["event_format"],
                               "total_usd": o["budget"]["total_usd"], "upfront_cash_usd": o["budget"]["upfront_cash_usd"]} for o in options],
                  "shortlist": shortlist, "top_choice": top, "revenue": revenue.data,
                  "fundraising_strategy": out.fundraising_strategy, "logistics_notes": out.logistics_notes,
                  "changes_from_previous": out.changes_from_previous, "research_mode": ctx.research_mode},
        )
