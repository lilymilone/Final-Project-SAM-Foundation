"""Agent 1: Orchestrator.

1. Intake: classify the request (model, or keyword fallback) and extract event details.
2. Plan: pick the specialists for that intent from a fixed template. The model
   cannot invent agents or loops.
3. Dispatch: hand each specialist a typed AgentTask, and log it as a handoff.
4. Revise: if Finance reports conflicts, send constraints back to the Events
   agent. At most settings.max_revisions rounds (hard cap 2), then stop and
   report what is unresolved.
5. Recommend and verify: draft the board recommendation, check it in code,
   and fix it once if needed.

Only the Orchestrator can delegate. Specialists never receive a dispatcher,
so there is no recursive delegation. A cap on total handoffs per run, the
model-call cap, and the spending budget guard against runaway loops.
"""

from __future__ import annotations

import re
from typing import Any

from ..ai.llm import StructuredOutputError
from .base import BaseAgent
from .contracts import AgentName, AgentResult, AgentTask, Constraint, Finding
from .outputs import BoardRecommendation, RequestAnalysis
from .registry import BOARD_RECOMMENDATION, CLASSIFY, SUMMARY_REPORT
from .runtime import RunContext, RunStopped, close_handoff, open_handoff
from .specialists.donations_compliance import DonationsComplianceAgent
from .specialists.event_intelligence import EventIntelligenceAgent
from .specialists.financial_analysis import FinancialAnalysisAgent
from .specialists.fundraising_events import FundraisingEventsAgent
from .specialists.mission_discovery import MissionDiscoveryAgent
from .specialists.partnerships_outreach import PartnershipsOutreachAgent
from .verification import collect_numbers, verify_workflow

A = AgentName

INTENT_AGENTS: dict[str, list[AgentName]] = {
    "plan_event": [A.EVENT_INTELLIGENCE, A.FUNDRAISING_EVENTS, A.FINANCIAL_ANALYSIS, A.PARTNERSHIPS_OUTREACH],
    "mission_discovery": [A.MISSION_DISCOVERY],
    "partnership_outreach": [A.PARTNERSHIPS_OUTREACH],
    "financial_review": [A.FINANCIAL_ANALYSIS],
    "donations_review": [A.DONATIONS_COMPLIANCE],
    "event_learning": [A.EVENT_INTELLIGENCE],
    "unsupported": [],
}
INTENT_DESCRIPTIONS = {
    "plan_event": "Plan a fundraising event: venues, budget, affordability, outreach.",
    "mission_discovery": "Research mission-aligned organizations, research initiatives, awareness events, causes.",
    "partnership_outreach": "Find prospective partners or sponsors and draft outreach.",
    "financial_review": "Review the foundation's finances and planning budget.",
    "donations_review": "Organize donation records, acknowledgments, compliance flags.",
    "event_learning": "Learn from past events and board reflections.",
    "unsupported": "Anything else.",
}

KEYWORDS = [
    ("donations_review", ("donation", "donor", "acknowledg", "thank-you", "thank you", "gift", "receipt", "compliance")),
    ("event_learning", ("lesson", "learn from", "past event", "previous event", "reflection", "what worked", "went wrong")),
    ("partnership_outreach", ("sponsor", "outreach", "partner with", "partnership", "reach out", "draft an email", "inquiry")),
    ("financial_review", ("budget review", "finances", "financial", "cash", "reserve", "afford", "income", "expenses")),
    ("plan_event", ("gala", "fundraiser", "fundraising event", "plan a", "plan an", "dinner", "walk", "benefit", "venue", "event")),
    ("mission_discovery", ("research", "organization", "nonprofit", "awareness", "initiative", "cause", "discover", "find")),
]
PLAN_EVENT = re.compile(r"\b(plan|organi[sz]e|host|throw|put on)\b.*\b(gala|fundraiser|event|dinner|walk|benefit|brunch|concert|auction|reception)\b")
CITY_PATTERNS = [
    (r"\bmanhattan\b|\bnyc\b|\bnew york\b", "Manhattan, New York, NY"),
    (r"\bnew haven\b", "New Haven, CT"),
    (r"\bgreenwich\b", "Greenwich, CT"),
    (r"\bboston\b", "Boston, MA"),
    (r"\bbrooklyn\b", "Brooklyn, NY"),
]

INTAKE_INSTRUCTIONS = """Classify the board's request into exactly one intent from "supported_intents" and extract details.
- attendance, city, event_type (e.g. gala, dinner, walk), event_format (seated_dinner or reception, only if stated),
  budget_limit_usd (only if a number is stated), research_topic (for research or outreach requests).
- Use null for anything not stated. Do not guess numbers.
- If the request asks to plan an event AND to check affordability or use past lessons, the intent is plan_event."""

SYNTHESIS_INSTRUCTIONS = """Write a board-ready recommendation from the specialists' validated results.
- Lead with a clear recommendation. Be honest about trade-offs and anything unresolved.
- Quote dollar figures ONLY from "figures" (exact values or rounded to the nearest $100 or $1,000).
- options: the realistic choices, using option_id values from "option_ids" (or null for non-venue options).
- lessons_applied: which past-event lessons shaped the plan, naming the event.
- decisions_for_board: the specific decisions only the board can make.
- caveats: synthetic data, unverified links, placeholder assumptions, missing permissions.
- Never claim that anything was sent, booked, reserved, paid, or approved."""


CANONICAL_TYPES = ("gala", "dinner", "walk", "panel", "concert", "auction", "brunch", "reception", "run")


def canonical_event_type(value: str | None) -> str | None:
    """'fundraising gala' -> 'gala'. Keeps unknown types as given."""
    if not value:
        return None
    low = value.lower()
    return next((t for t in CANONICAL_TYPES if t in low), low.strip())


def keyword_analysis(request: str) -> RequestAnalysis:
    text = request.lower()
    intent = "unsupported"
    if PLAN_EVENT.search(text):  # "plan a gala using lessons…" is still event planning
        intent = "plan_event"
    else:
        for name, words in KEYWORDS:
            if any(w in text for w in words):
                intent = name
                break
    attendance = None
    m = re.search(r"(\d{2,4})\s*[- ]?\s*(?:person|people|guest|attendee|seat)", text)
    if m:
        attendance = int(m.group(1))
    city = next((label for pattern, label in CITY_PATTERNS if re.search(pattern, text)), None)
    event_type = next((t for t in ("gala", "dinner", "walk", "panel", "concert", "auction", "brunch") if t in text), None)
    fmt = "reception" if "reception" in text or "cocktail" in text else "seated_dinner" if "seated" in text else None
    budget = None
    b = re.search(r"budget[^$\d]{0,20}\$?\s?(\d[\d,]*)\s*(k)?", text)
    if b:
        budget = float(b.group(1).replace(",", "")) * (1000 if b.group(2) else 1)
    return RequestAnalysis(intent=intent, city=city, attendance=attendance, event_type=event_type, event_format=fmt,
                           budget_limit_usd=budget, research_topic=request if intent in ("mission_discovery", "partnership_outreach") else None,
                           rationale="Keyword routing.")


class _OrchestratorSelf(BaseAgent):
    """The Orchestrator's own model-backed steps (intake and the recommendation)."""

    name = A.ORCHESTRATOR

    def execute(self, task: AgentTask, ctx: RunContext) -> AgentResult:
        if task.step_key == "intake":
            return self._intake(task, ctx)
        if task.step_key.startswith("recommendation"):
            return self._recommend(task, ctx)
        if task.step_key == "verification":
            report = task.inputs["report"]
            self.tool(ctx, "verify_final_result", report=report)
            failed = [c for c in report["checks"] if c["passed"] is False]
            return self.result(task, "completed" if not failed else "needs_revision",
                               "All checks passed." if not failed else f"{len(failed)} check(s) failed: " + "; ".join(c["name"] for c in failed),
                               findings=[Finding(claim=f"{'PASS' if c['passed'] else 'FAIL' if c['passed'] is False else 'NOTE'}: {c['name']}. {c['detail']}",
                                                 kind="computed") for c in report["checks"]],
                               data=report)
        raise ValueError(f"Unknown orchestrator step {task.step_key}")

    def _intake(self, task: AgentTask, ctx: RunContext) -> AgentResult:
        request = task.inputs["request"]
        hint = task.inputs.get("intent_hint")
        keywords = keyword_analysis(request)
        warnings: list[str] = []
        if hint:
            analysis = keywords.model_copy(update={"intent": hint, "rationale": "Intent chosen by the board member."})
            routing = "board"
        else:
            try:
                analysis = self.think(ctx, CLASSIFY, INTAKE_INSTRUCTIONS,
                                      {"request": request, "supported_intents": INTENT_DESCRIPTIONS}, RequestAnalysis)
                routing = "model"
                # Fill details the model left empty with what the text plainly states.
                analysis = analysis.model_copy(update={k: v for k, v in keywords.model_dump().items()
                                                       if k in ("attendance", "city", "budget_limit_usd") and getattr(analysis, k) is None and v is not None})
                # Format only when the request states it (no model guesses), and a canonical event type.
                analysis = analysis.model_copy(update={"event_format": keywords.event_format,
                                                       "event_type": canonical_event_type(analysis.event_type) or keywords.event_type})
            except StructuredOutputError as exc:
                analysis, routing = keywords, "keyword"
                warnings.append(f"Model classification failed validation; used keyword routing. ({exc})")
        agents = INTENT_AGENTS[analysis.intent]
        return self.result(task, "completed",
                           f"Intent: {analysis.intent.replace('_', ' ')} ({routing} routing). "
                           f"Specialists: {', '.join(a.value.replace('_', ' ') for a in agents) or 'none'}.",
                           warnings=warnings, data={"analysis": analysis.model_dump(), "routing": routing,
                                                    "agents": [a.value for a in agents]})

    def _recommend(self, task: AgentTask, ctx: RunContext) -> AgentResult:
        profile = BOARD_RECOMMENDATION if task.inputs["intent"] == "plan_event" else SUMMARY_REPORT
        rec = self.think(ctx, profile, SYNTHESIS_INSTRUCTIONS, task.inputs["payload"], BoardRecommendation,
                         reasoning="medium" if profile is BOARD_RECOMMENDATION else "low", max_output_tokens=8000)
        return self.result(task, "completed", rec.headline, data={"recommendation": rec.model_dump()},
                           findings=[Finding(claim=rec.recommendation, kind="recommendation")])


class Orchestrator:
    def __init__(self) -> None:
        self.me = _OrchestratorSelf()
        self.agents: dict[AgentName, BaseAgent] = {
            A.ORCHESTRATOR: self.me,
            A.EVENT_INTELLIGENCE: EventIntelligenceAgent(),
            A.FUNDRAISING_EVENTS: FundraisingEventsAgent(),
            A.FINANCIAL_ANALYSIS: FinancialAnalysisAgent(),
            A.DONATIONS_COMPLIANCE: DonationsComplianceAgent(),
            A.PARTNERSHIPS_OUTREACH: PartnershipsOutreachAgent(),
            A.MISSION_DISCOVERY: MissionDiscoveryAgent(),
        }

    # -- delegation (the only place handoffs happen) -----------------------------------

    def dispatch(self, ctx: RunContext, task: AgentTask, from_agent: str = "orchestrator") -> AgentResult:
        ctx.check_cancelled()
        if ctx.counters["handoffs"] >= ctx.settings.max_handoffs_per_run:
            raise RunStopped(f"Stopped: reached the limit of {ctx.settings.max_handoffs_per_run} handoffs for one run.")
        ctx.counters["handoffs"] += 1
        handoff_id = open_handoff(ctx, task, from_agent)
        ctx.current_handoff_id = handoff_id
        try:
            result = self.agents[task.agent].run(task, ctx)
        finally:
            ctx.current_handoff_id = None
        close_handoff(ctx, handoff_id, result)
        if result.status == "stopped":
            raise RunStopped(result.summary)
        return result

    def _task(self, ctx: RunContext, step: str, agent: AgentName, objective: str, **kw: Any) -> AgentTask:
        return AgentTask(run_id=ctx.run_id, step_key=step, agent=agent, objective=objective, **kw)

    # -- workflow ---------------------------------------------------------------------

    def run(self, ctx: RunContext, request: str, intent_hint: str | None = None, event_plan_id: int | None = None) -> dict:
        intake = self.dispatch(ctx, self._task(ctx, "intake", A.ORCHESTRATOR, "Understand the request and choose specialists",
                                               inputs={"request": request, "intent_hint": intent_hint}), from_agent="board")
        if intake.status != "completed":
            raise RuntimeError(intake.summary)
        analysis = RequestAnalysis.model_validate(intake.data["analysis"])
        intent = analysis.intent
        results: dict[str, AgentResult] = {}
        extra: dict[str, Any] = {"revision_history": []}

        if intent == "plan_event":
            self._plan_event(ctx, analysis, request, event_plan_id, results, extra)
        elif intent == "mission_discovery":
            results["research"] = self.dispatch(ctx, self._task(ctx, "research", A.MISSION_DISCOVERY, "Research mission-aligned opportunities",
                                                                inputs={"topic": analysis.research_topic or request}))
        elif intent == "partnership_outreach":
            results["outreach"] = self.dispatch(ctx, self._task(ctx, "outreach", A.PARTNERSHIPS_OUTREACH, "Find prospective partners and draft outreach",
                                                                inputs={"find_partners": True, "topic": analysis.research_topic or request}))
        elif intent == "financial_review":
            results["finance"] = self.dispatch(ctx, self._task(ctx, "finance", A.FINANCIAL_ANALYSIS, "Review the foundation's financial position"))
        elif intent == "donations_review":
            results["donations"] = self.dispatch(ctx, self._task(ctx, "donations", A.DONATIONS_COMPLIANCE, "Review donations and draft acknowledgments"))
        elif intent == "event_learning":
            results["lessons"] = self.dispatch(ctx, self._task(ctx, "lessons", A.EVENT_INTELLIGENCE, "Learn from past events and reflections",
                                                               inputs={"focus": request}))
        else:
            return {"intent": intent, "routing": intake.data["routing"], "analysis": analysis.model_dump(), "recommendation": None,
                    "message": "SAM SPACE can plan events, research mission partners, draft outreach, review finances, "
                               "organize donations, and learn from past events. Try rephrasing your request.",
                    "verification": None, "research_mode": ctx.research_mode}

        figures = self._figures(results)
        option_ids = {o["option_id"] for r in results.values() for o in (r.data.get("options") or []) if isinstance(o, dict) and "option_id" in o}
        payload = self._synthesis_payload(intent, request, results, extra, figures, option_ids, ctx)
        rec_result = self.dispatch(ctx, self._task(ctx, "recommendation", A.ORCHESTRATOR, "Write the board-ready recommendation",
                                                   inputs={"intent": intent, "payload": payload}))
        rec = BoardRecommendation.model_validate(rec_result.data["recommendation"]) if rec_result.status == "completed" else None
        allowed = collect_numbers(figures) | collect_numbers({k: r.data for k, r in results.items()})
        report = verify_workflow(ctx.db, ctx.run_id, results, rec, allowed, option_ids)

        if rec is not None and not report["passed"]:  # one bounded correction, then accept and flag
            failed = "; ".join(f"{c['name']}: {c['detail']}" for c in report["checks"] if c["passed"] is False)
            payload["verification_feedback"] = f"Your previous draft failed verification ({failed}). Fix only those problems."
            retry = self.dispatch(ctx, self._task(ctx, "recommendation_fix", A.ORCHESTRATOR, "Correct the recommendation after verification",
                                                  kind="revision", revision_round=1, inputs={"intent": intent, "payload": payload}))
            if retry.status == "completed":
                rec = BoardRecommendation.model_validate(retry.data["recommendation"])
                report = verify_workflow(ctx.db, ctx.run_id, results, rec, allowed, option_ids)
        self.dispatch(ctx, self._task(ctx, "verification", A.ORCHESTRATOR, "Verify the final result in code", inputs={"report": report}))

        caveats = self._deterministic_caveats(ctx, results, extra)
        if rec is not None:
            rec = rec.model_copy(update={"caveats": caveats + [c for c in rec.caveats if c not in caveats]})
        return {
            "intent": intent,
            "routing": intake.data["routing"],
            "analysis": analysis.model_dump(),
            "research_mode": ctx.research_mode,
            "recommendation": rec.model_dump() if rec else None,
            "verification": report,
            "figures": figures,
            "revision_history": extra["revision_history"],
            "unresolved_conflicts": extra.get("unresolved_conflicts", []),
            "event_plan_id": extra.get("event_plan_id"),
            "specialists": {k: {"agent": r.agent.value, "status": r.status, "summary": r.summary} for k, r in results.items()},
            "finance": {k: results["finance"].data.get(k) for k in ("verdict", "affordability", "budget", "position", "break_even", "sensitivity", "venue", "event_format")}
            if "finance" in results and results["finance"].status in ("completed", "needs_revision") else None,
            "shortlist": [{"option_id": s["option_id"], "venue": s["venue"]["name"], "event_format": s["event_format"],
                           "total_usd": s["budget"]["total_usd"], "upfront_cash_usd": s["budget"]["upfront_cash_usd"],
                           "rationale": s["rationale"], "verification": s["venue"].get("verification"), "source_url": s["venue"].get("source_url")}
                          for s in (results["venues"].data.get("shortlist") or [])] if "venues" in results else [],
            "drafts": (results["outreach"].data.get("drafts") if "outreach" in results else []) or [],
            "lessons": results["lessons"].data.get("lessons") if "lessons" in results else [],
            "disagreements": results["lessons"].data.get("disagreements") if "lessons" in results else [],
            "findings": results["research"].data.get("findings") if "research" in results else [],
            "donations": results["donations"].data if "donations" in results else None,
        }

    def _plan_event(self, ctx: RunContext, analysis: RequestAnalysis, request: str, event_plan_id: int | None,
                    results: dict[str, AgentResult], extra: dict) -> None:
        plan: dict = {}
        if event_plan_id:
            got = self.me.tool(ctx, "read_event_plan", event_plan_id=event_plan_id)
            plan = got.data or {}
        event = {
            "name": plan.get("name") or "Fundraising event",
            "city": analysis.city or plan.get("city") or "Manhattan, New York, NY",
            "attendance": analysis.attendance or plan.get("attendance") or 100,
            "event_type": canonical_event_type(analysis.event_type or plan.get("event_type")) or "gala",
            "event_format": analysis.event_format,
            "budget_limit_usd": analysis.budget_limit_usd or plan.get("budget_limit_usd"),
            "target_date": plan.get("target_date"),
        }
        if not event_plan_id:
            try:
                made = self.me.tool(ctx, "create_event_plan", name=f"{event['attendance']}-guest {event['event_type']} in {event['city']}",
                                    city=event["city"], attendance=event["attendance"], event_type=event["event_type"],
                                    budget_limit_usd=event["budget_limit_usd"])
                event_plan_id = made.data["id"] if made.ok else None
            except PermissionError:
                event_plan_id = None  # the plan still runs; venue candidates just aren't saved
        extra["event_plan_id"] = event_plan_id
        focus = f"{event['attendance']}-guest {event['event_type']} in {event['city']}"

        lessons = self.dispatch(ctx, self._task(ctx, "lessons", A.EVENT_INTELLIGENCE, f"Retrieve lessons from past events for a {focus}",
                                                inputs={"focus": focus}))
        results["lessons"] = lessons
        contingency = lessons.data.get("recommended_contingency_pct") if lessons.status == "completed" else None
        lesson_constraints = [Constraint(**c) for c in lessons.data.get("constraints", [])] if lessons.status == "completed" else []

        base_inputs = {"event": event, "event_plan_id": event_plan_id, "contingency_pct": contingency,
                       "lessons": lessons.data.get("lessons", []) if lessons.status == "completed" else []}
        venues = self.dispatch(ctx, self._task(ctx, "venues", A.FUNDRAISING_EVENTS, f"Research venues and a fundraising strategy for a {focus}",
                                               inputs=base_inputs, constraints=lesson_constraints, depends_on=["lessons"]))
        results["venues"] = venues
        top = venues.data.get("top_choice") if venues.status == "completed" else None
        if top is None:
            extra["unresolved_conflicts"] = [{"type": "no_venue", "detail": venues.summary}]
            return

        finance_inputs = {"budget_limit_usd": event["budget_limit_usd"], "min_contingency_pct": contingency}
        finance = self.dispatch(ctx, self._task(ctx, "finance", A.FINANCIAL_ANALYSIS, f"Check whether we can afford {top['venue']['name']}",
                                                inputs={**finance_inputs, "top_choice": top, "revenue": venues.data.get("revenue")},
                                                depends_on=["venues"]))
        results["finance"] = finance
        extra["revision_history"].append(self._history_entry(0, top, finance))

        round_no = 0
        while finance.status == "needs_revision" and finance.data.get("conflicts") and round_no < ctx.settings.max_revisions:
            round_no += 1
            constraints = self._revision_constraints(finance, lesson_constraints, contingency)
            previous = [{"option_id": s["option_id"], "venue": s["venue"]["name"], "total_usd": s["budget"]["total_usd"]}
                        for s in venues.data.get("shortlist", [])]
            venues = self.dispatch(ctx, self._task(
                ctx, f"venues_revision_{round_no}", A.FUNDRAISING_EVENTS,
                "Revise the venue plan to resolve Finance's conflicts: " + "; ".join(c["detail"] for c in finance.data["conflicts"]),
                kind="revision", revision_round=round_no, inputs={**base_inputs, "previous_shortlist": previous},
                constraints=constraints, depends_on=["finance"]))
            results["venues"] = venues
            top = venues.data.get("top_choice") if venues.status == "completed" else None
            if top is None:
                break
            finance = self.dispatch(ctx, self._task(
                ctx, f"finance_revision_{round_no}", A.FINANCIAL_ANALYSIS, f"Re-check affordability of the revised plan ({top['venue']['name']})",
                kind="revision", revision_round=round_no, inputs={**finance_inputs, "top_choice": top, "revenue": venues.data.get("revenue")},
                depends_on=[f"venues_revision_{round_no}"]))
            results["finance"] = finance
            extra["revision_history"].append(self._history_entry(round_no, top, finance))

        if finance.status == "needs_revision":
            extra["unresolved_conflicts"] = finance.data.get("conflicts", [])
            if round_no >= ctx.settings.max_revisions:
                extra["revision_limit_reached"] = True

        if venues.status == "completed" and venues.data.get("shortlist"):
            results["outreach"] = self.dispatch(ctx, self._task(
                ctx, "outreach", A.PARTNERSHIPS_OUTREACH, "Prepare unsent venue and sponsor inquiry drafts",
                inputs={"event": event, "shortlist": venues.data["shortlist"], "find_partners": True,
                        "topic": f"Local sponsors for a mental-health fundraising {event['event_type']} in {event['city']}"},
                depends_on=[venues.step_key]))

    @staticmethod
    def _history_entry(round_no: int, top: dict, finance: AgentResult) -> dict:
        return {"round": round_no, "option_id": top["option_id"], "venue": top["venue"]["name"], "event_format": top["event_format"],
                "total_usd": top["budget"]["total_usd"], "upfront_cash_usd": top["budget"]["upfront_cash_usd"],
                "finance_status": finance.status, "verdict": finance.data.get("verdict"),
                "conflicts": [c["detail"] for c in finance.data.get("conflicts", [])]}

    @staticmethod
    def _revision_constraints(finance: AgentResult, lesson_constraints: list[Constraint], contingency: float | None) -> list[Constraint]:
        out = [Constraint(name="allow_format_change", detail="You may switch between seated dinner and reception to meet the budget.",
                          source_agent=A.ORCHESTRATOR)]
        for c in finance.data.get("conflicts", []):
            if c["type"] == "over_budget_limit":
                out.append(Constraint(name="max_total_usd", value=c["max_total_usd"], detail=c["detail"], source_agent=A.FINANCIAL_ANALYSIS))
            elif c["type"] == "upfront_cash_exceeds_available":
                out.append(Constraint(name="max_upfront_usd", value=c["max_upfront_usd"], detail=c["detail"], source_agent=A.FINANCIAL_ANALYSIS))
            else:
                out.append(Constraint(name=c["type"], detail=c["detail"], source_agent=A.FINANCIAL_ANALYSIS))
        out += [c for c in lesson_constraints if c.name != "min_contingency_pct"]
        if contingency is not None:
            out.append(Constraint(name="min_contingency_pct", value=contingency, detail=f"Keep at least {contingency:.0%} contingency (past overruns).",
                                  source_agent=A.EVENT_INTELLIGENCE))
        return out

    @staticmethod
    def _figures(results: dict[str, AgentResult]) -> dict[str, float]:
        f: dict[str, float] = {}
        fin = results.get("finance")
        if fin and fin.status in ("completed", "needs_revision"):
            pos = fin.data.get("position") or {}
            for k in ("total_income_usd", "total_expense_usd", "net_usd", "average_monthly_expense_usd", "reserve_usd",
                      "reserve_floor_usd", "available_planning_budget_usd"):
                if pos.get(k) is not None:
                    f[k] = pos[k]
            b = fin.data.get("budget") or {}
            for k in ("total_usd", "upfront_cash_usd", "cost_per_guest_usd", "contingency_usd", "subtotal_usd"):
                if b.get(k) is not None:
                    f[f"top_option_{k}"] = b[k]
            be = fin.data.get("break_even") or {}
            if be.get("break_even_revenue_per_attendee_usd") is not None:
                f["break_even_revenue_per_attendee_usd"] = be["break_even_revenue_per_attendee_usd"]
        ven = results.get("venues")
        if ven and ven.status == "completed":
            for o in ven.data.get("options", []):
                f[f"{o['option_id']}_total_usd"] = o["total_usd"]
                f[f"{o['option_id']}_upfront_usd"] = o["upfront_cash_usd"]
            rev = ven.data.get("revenue") or {}
            for k in ("low", "base", "high", "per_attendee_usd"):
                if rev.get(k) is not None:
                    f[f"revenue_{k}_usd" if k != "per_attendee_usd" else "revenue_per_attendee_usd"] = rev[k]
        return f

    @staticmethod
    def _synthesis_payload(intent, request, results, extra, figures, option_ids, ctx) -> dict:
        specialists = {}
        for key, r in results.items():
            item = {"agent": r.agent.value, "status": r.status, "summary": r.summary,
                    "findings": [f.claim for f in r.findings][:12], "warnings": r.warnings[:8], "assumptions": r.assumptions[:8],
                    "next_steps": r.next_steps[:6]}
            if key == "venues":
                item["shortlist"] = [{"option_id": s["option_id"], "venue": s["venue"]["name"], "format": s["event_format"],
                                      "rationale": s["rationale"]} for s in r.data.get("shortlist", [])]
                item["fundraising_strategy"] = r.data.get("fundraising_strategy")
                item["changes_from_previous"] = r.data.get("changes_from_previous")
            if key == "finance":
                item["verdict"] = r.data.get("verdict")
                item["checks"] = (r.data.get("affordability") or {}).get("checks")
            if key == "lessons":
                item["lessons"] = r.data.get("lessons")
                item["disagreements"] = r.data.get("disagreements")
            specialists[key] = item
        return {"request": request, "intent": intent, "research_mode": ctx.research_mode, "specialists": specialists,
                "revision_history": extra.get("revision_history"), "unresolved_conflicts": extra.get("unresolved_conflicts", []),
                "figures": figures, "option_ids": sorted(option_ids)}

    @staticmethod
    def _deterministic_caveats(ctx: RunContext, results: dict[str, AgentResult], extra: dict) -> list[str]:
        caveats = []
        if any(src.verification == "synthetic" for r in results.values() for src in r.sources):
            caveats.append("Research used labeled synthetic fixtures, not live web research. Venue names, prices, and partners are not real.")
        if any("synthetic demo" in a.lower() or "demo ledger" in a.lower() or "demo records" in a.lower()
               for r in results.values() for a in r.assumptions):
            caveats.append("Past events, books, and donations are the synthetic demo dataset.")
        if extra.get("revision_limit_reached"):
            caveats.append(f"Stopped after {ctx.settings.max_revisions} revision round(s) (loop limit). Remaining conflicts need a board decision.")
        refused = [r.agent.value.replace("_", " ") for r in results.values() if r.status == "refused"]
        if refused:
            caveats.append(f"Skipped for your role: {', '.join(refused)}.")
        return caveats

