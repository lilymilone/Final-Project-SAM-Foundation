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
from ..ai.router import BudgetExceededError
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
        if task.step_key.startswith("evaluate"):
            return self._evaluate(task, ctx)
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
        if hint and not task.inputs.get("interpret"):
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
            except (BudgetExceededError, RunStopped):
                raise
            except Exception as exc:  # network or provider outage: interpreting the request has a safe fallback
                analysis, routing = keywords, "keyword"
                warnings.append(f"The model could not be reached ({type(exc).__name__}); used keyword routing.")
            if hint:  # Event Studio fixes the workflow; the model only interprets the details
                analysis = analysis.model_copy(update={"intent": hint})
                routing = f"{routing}, workflow set by Event Studio"
        agents = INTENT_AGENTS[analysis.intent]
        return self.result(task, "completed",
                           f"Intent: {analysis.intent.replace('_', ' ')} ({routing} routing). "
                           f"Specialists: {', '.join(a.value.replace('_', ' ') for a in agents) or 'none'}.",
                           warnings=warnings, data={"analysis": analysis.model_dump(), "routing": routing,
                                                    "agents": [a.value for a in agents]})

    def _evaluate(self, task: AgentTask, ctx: RunContext) -> AgentResult:
        """Step 5: combine Finance's conflicts with checks on neglected history lessons (deterministic)."""
        res = self.tool(ctx, "evaluate_constraints", finance_conflicts=task.inputs["finance_conflicts"],
                        lessons=task.inputs["lessons"], assumptions=task.inputs["assumptions"], venue_name=task.inputs["venue_name"])
        conflicts, checks = res.data["conflicts"], res.data["history_checks"]
        findings = [Finding(claim=f"{c['source'].upper()} CONFLICT: {c['detail']}", kind="computed") for c in conflicts]
        findings += [Finding(claim=f"{'PASS' if h['passed'] else 'FAIL'}: {h['name']}. {h['detail']}", kind="computed",
                             source_ids=[f"event:{i}" for i in h["event_ids"]] + [f"reflection:{i}" for i in h["reflection_ids"]])
                     for h in checks]
        summary = ("No conflicts: the plan fits the budget and respects the lessons checked." if not conflicts else
                   f"{len(conflicts)} conflict(s) to resolve: " + "; ".join(sorted({c['source'] for c in conflicts})) + ".")
        return self.result(task, "needs_revision" if conflicts else "completed", summary, findings=findings, data=res.data)

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

    def run(self, ctx: RunContext, request: str, intent_hint: str | None = None, event_plan_id: int | None = None,
            options: dict | None = None) -> dict:
        options = options or {}
        use_history = options.get("use_history", True)
        intake = self.dispatch(ctx, self._task(ctx, "intake", A.ORCHESTRATOR, "Understand the request and choose specialists",
                                               inputs={"request": request, "intent_hint": intent_hint,
                                                       "interpret": bool(options.get("interpret"))}), from_agent="board")
        if intake.status != "completed":
            raise RuntimeError(intake.summary)
        analysis = RequestAnalysis.model_validate(intake.data["analysis"])
        intent = analysis.intent
        results: dict[str, AgentResult] = {}
        extra: dict[str, Any] = {"revision_history": []}

        if intent == "plan_event":
            self._plan_event(ctx, analysis, request, event_plan_id, results, extra, use_history=use_history)
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
            focus_id = options.get("historical_event_id")
            focus_name = options.get("historical_event_name")
            results["lessons"] = self.dispatch(ctx, self._task(
                ctx, "lessons", A.EVENT_INTELLIGENCE,
                f"Analyze {focus_name} and generate lessons" if focus_name else "Learn from past events and reflections",
                inputs={"focus": focus_name or request, "focus_event_id": focus_id, "mode": "event_analysis"}))
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
            "options": {"use_history": use_history, "historical_event_id": options.get("historical_event_id")},
            "history_constraints": extra.get("history_constraints", []),
            "events_strategy": {k: results["venues"].data.get(k) for k in ("fundraising_strategy", "logistics_notes", "changes_from_previous")}
            if "venues" in results and results["venues"].status == "completed" else None,
            "themes": results["lessons"].data.get("themes") if "lessons" in results and results["lessons"].status == "completed" else [],
            "comparison": results["lessons"].data.get("comparison") if "lessons" in results and results["lessons"].status == "completed" else None,
            "recommendation": rec.model_dump() if rec else None,
            "verification": report,
            "figures": figures,
            "revision_history": extra["revision_history"],
            "unresolved_conflicts": extra.get("unresolved_conflicts", []),
            "event_plan_id": extra.get("event_plan_id"),
            "specialists": {k: {"agent": r.agent.value, "status": r.status, "summary": r.summary} for k, r in results.items()},
            "finance": {k: results["finance"].data.get(k) for k in ("verdict", "affordability", "model", "position", "venue", "event_format", "option_id")}
            if "finance" in results and results["finance"].status in ("completed", "needs_revision") else None,
            "event": extra.get("event"),
            "venues": extra.get("venues", []),
            "shortlist": [{"option_id": s["option_id"], "venue": s["venue"]["name"], "event_format": s["event_format"], "rank": s["rank"],
                           "total_usd": s["model"]["total_cost_usd"], "upfront_cash_usd": s["model"]["upfront_cash_usd"],
                           "pricing_status": s["venue"].get("pricing_status"), "rationale": s["rationale"],
                           "lessons_applied": s.get("lessons_applied", []), "verification": s["venue"].get("verification"),
                           "website": s["venue"].get("website"), "source_url": s["venue"].get("source_url")}
                          for s in (results["venues"].data.get("shortlist") or [])] if "venues" in results and results["venues"].status == "completed" else [],
            "original_plan": extra["revision_history"][0] if extra["revision_history"] else None,
            "revised_plan": extra["revision_history"][-1] if len(extra["revision_history"]) > 1 else None,
            "revision_reasons": extra.get("revision_reasons", []),
            "evaluation": extra.get("evaluation"),
            "drafts": (results["outreach"].data.get("drafts") if "outreach" in results else []) or [],
            "lessons": results["lessons"].data.get("lessons") if "lessons" in results else [],
            "disagreements": results["lessons"].data.get("disagreements") if "lessons" in results else [],
            "findings": results["research"].data.get("findings") if "research" in results else [],
            "donations": results["donations"].data if "donations" in results else None,
        }

    def _plan_event(self, ctx: RunContext, analysis: RequestAnalysis, request: str, event_plan_id: int | None,
                    results: dict[str, AgentResult], extra: dict, use_history: bool = True) -> None:
        plan: dict = {}
        if event_plan_id:
            got = self.me.tool(ctx, "read_event_plan", event_plan_id=event_plan_id)
            plan = got.data or {}

        def pick(plan_key: str, analysis_value, default=None):
            return plan.get(plan_key) if plan.get(plan_key) not in (None, "") else (analysis_value if analysis_value not in (None, "") else default)

        event = {
            "name": plan.get("name") or "Fundraising event",
            "city": pick("city", analysis.city, "Manhattan, New York, NY"),
            "attendance": int(pick("attendance", analysis.attendance, 100)),
            "event_type": canonical_event_type(pick("event_type", analysis.event_type, "gala")) or "gala",
            "event_format": pick("event_format", analysis.event_format),
            "budget_limit_usd": pick("budget_limit_usd", analysis.budget_limit_usd),
            "fundraising_goal_usd": plan.get("fundraising_goal_usd"),
            "ticket_price_usd": plan.get("ticket_price_usd"),
            "target_date": plan.get("target_date"), "date_end": plan.get("date_end"),
            "instructions": plan.get("instructions"),
        }
        overrides = plan.get("assumptions") or {}
        if not event_plan_id:
            try:
                made = self.me.tool(ctx, "create_event_plan", name=f"{event['attendance']}-guest {event['event_type']} in {event['city']}",
                                    city=event["city"], attendance=event["attendance"], event_type=event["event_type"],
                                    budget_limit_usd=event["budget_limit_usd"])
                event_plan_id = made.data["id"] if made.ok else None
            except PermissionError:
                event_plan_id = None  # the plan still runs; venue candidates just aren't saved
        extra["event_plan_id"] = event_plan_id
        extra["event"] = event
        focus = f"{event['attendance']}-guest {event['event_type']} in {event['city']}"

        contingency, lesson_constraints, lesson_list = None, [], []
        if use_history:  # step 2: Event Intelligence retrieves relevant lessons
            lessons = self.dispatch(ctx, self._task(ctx, "lessons", A.EVENT_INTELLIGENCE, f"Retrieve lessons from past events for a {focus}",
                                                    inputs={"focus": focus, "mode": "planning"}))
            results["lessons"] = lessons
            if lessons.status == "completed":
                contingency = lessons.data.get("recommended_contingency_pct")
                lesson_constraints = [Constraint(**c) for c in lessons.data.get("constraints", [])]
                lesson_list = lessons.data.get("lessons", [])
        extra["history_constraints"] = [c.model_dump(mode="json") for c in lesson_constraints]

        # Step 3: Events researches venues. An empty lesson list (not None) means "no lessons provided".
        base_inputs = {"event": event, "event_plan_id": event_plan_id, "contingency_pct": contingency, "lessons": lesson_list,
                       "assumption_overrides": overrides}
        venues = self.dispatch(ctx, self._task(ctx, "venues", A.FUNDRAISING_EVENTS, f"Research venues and a fundraising strategy for a {focus}",
                                               inputs=base_inputs, constraints=lesson_constraints,
                                               depends_on=["lessons"] if use_history else []))
        results["venues"] = venues
        extra["venues"] = venues.data.get("venues", []) if venues.status == "completed" else []
        top = venues.data.get("top_choice") if venues.status == "completed" else None
        if top is None:
            extra["unresolved_conflicts"] = [{"type": "no_venue", "detail": venues.summary, "source": "events"}]
            return

        finance_inputs = {"budget_limit_usd": event["budget_limit_usd"], "fundraising_goal_usd": event["fundraising_goal_usd"],
                          "min_contingency_pct": contingency}
        round_no = 0
        while True:
            suffix = "" if round_no == 0 else f"_revision_{round_no}"
            # Step 4: Finance assesses affordability (it recomputes the model itself).
            finance = self.dispatch(ctx, self._task(
                ctx, f"finance{suffix}", A.FINANCIAL_ANALYSIS,
                f"{'Re-check' if round_no else 'Check'} whether we can afford {top['venue']['name']} ({top['event_format'].replace('_', ' ')})",
                kind="revision" if round_no else "task", revision_round=round_no, inputs={**finance_inputs, "top_choice": top},
                depends_on=[venues.step_key]))
            results["finance"] = finance
            # Step 5: the Orchestrator evaluates budget and history constraints together (in code).
            evaluation = self.dispatch(ctx, self._task(
                ctx, f"evaluate{suffix}", A.ORCHESTRATOR, "Evaluate cost, history, and plan constraints",
                kind="revision" if round_no else "task", revision_round=round_no,
                inputs={"finance_conflicts": finance.data.get("conflicts", []) if finance.status in ("completed", "needs_revision") else [],
                        "lessons": lesson_list, "assumptions": top["model"]["assumptions"], "venue_name": top["venue"]["name"]},
                depends_on=[finance.step_key]))
            conflicts = evaluation.data.get("conflicts", [])
            extra["evaluation"] = evaluation.data
            extra["revision_history"].append(self._history_entry(round_no, top, finance, conflicts, venues))
            if round_no == 0 and conflicts:
                extra["revision_reasons"] = conflicts
            if not conflicts or round_no >= ctx.settings.max_revisions:
                break
            # Step 6: request a revised, lower-cost or lesson-compliant strategy from the Events agent.
            round_no += 1
            constraints = self._revision_constraints(conflicts, lesson_constraints, contingency)
            previous = [{"option_id": s["option_id"], "venue": s["venue"]["name"], "total_usd": s["model"]["total_cost_usd"]}
                        for s in venues.data.get("shortlist", [])]
            venues = self.dispatch(ctx, self._task(
                ctx, f"venues_revision_{round_no}", A.FUNDRAISING_EVENTS,
                "Revise the plan to resolve: " + "; ".join(c["detail"] for c in conflicts),
                kind="revision", revision_round=round_no,
                inputs={**base_inputs, "previous_shortlist": previous, "candidates": extra["venues"]},
                constraints=constraints, depends_on=[evaluation.step_key]))
            results["venues"] = venues
            top = venues.data.get("top_choice") if venues.status == "completed" else None
            if top is None:
                break

        if conflicts:
            extra["unresolved_conflicts"] = conflicts
            if round_no >= ctx.settings.max_revisions:
                extra["revision_limit_reached"] = True

        if venues.status == "completed" and venues.data.get("shortlist"):  # step 7: unsent venue inquiries
            results["outreach"] = self.dispatch(ctx, self._task(
                ctx, "outreach", A.PARTNERSHIPS_OUTREACH, "Prepare unsent inquiry drafts for the shortlisted venues",
                inputs={"event": event, "shortlist": venues.data["shortlist"][:3], "find_partners": False}, depends_on=[venues.step_key]))

    @staticmethod
    def _history_entry(round_no: int, top: dict, finance: AgentResult, conflicts: list[dict], venues: AgentResult) -> dict:
        m = top["model"]
        return {"round": round_no, "option_id": top["option_id"], "venue": top["venue"]["name"], "event_format": top["event_format"],
                "pricing_status": top["venue"].get("pricing_status"), "total_usd": m["total_cost_usd"], "upfront_cash_usd": m["upfront_cash_usd"],
                "base_net_usd": m["scenarios"]["base"]["net_usd"], "contingency_pct": m["contingency_pct"],
                "finance_status": finance.status, "verdict": finance.data.get("verdict"),
                "conflicts": [c["detail"] for c in conflicts], "conflict_sources": sorted({c["source"] for c in conflicts}),
                "changes_from_previous": venues.data.get("changes_from_previous") if round_no else None,
                "rationale": top.get("rationale")}

    @staticmethod
    def _revision_constraints(conflicts: list[dict], lesson_constraints: list[Constraint], contingency: float | None) -> list[Constraint]:
        out = [Constraint(name="allow_format_change", detail="You may switch between seated dinner and reception to meet the constraints.",
                          source_agent=A.ORCHESTRATOR)]
        for c in conflicts:
            if c["type"] == "over_budget_limit":
                out.append(Constraint(name="max_total_usd", value=c["max_total_usd"], detail=c["detail"], source_agent=A.FINANCIAL_ANALYSIS))
            elif c["type"] == "upfront_cash_exceeds_available":
                out.append(Constraint(name="max_upfront_usd", value=c["max_upfront_usd"], detail=c["detail"], source_agent=A.FINANCIAL_ANALYSIS))
            elif c["type"] == "history_catering_minimum":
                out.append(Constraint(name="avoid_catering_minimum_risk", value=c.get("conservative_share"), detail=c["detail"],
                                      source_agent=A.ORCHESTRATOR))
            else:
                out.append(Constraint(name=c["type"], detail=c["detail"],
                                      source_agent=A.FINANCIAL_ANALYSIS if c.get("source") == "finance" else A.ORCHESTRATOR))
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
            m = fin.data.get("model") or {}
            for k in ("total_cost_usd", "upfront_cash_usd", "contingency_usd", "subtotal_usd", "max_budget_usd", "target_usd"):
                if m.get(k) is not None:
                    f[f"top_option_{k}"] = m[k]
            for line in m.get("lines", []):
                f[f"cost_{line['category'].lower()}_usd"] = line["amount_usd"]
            for name, sc in (m.get("scenarios") or {}).items():
                for k in ("ticket_revenue_usd", "sponsorship_revenue_usd", "donations_usd", "total_revenue_usd", "net_usd", "vs_target_usd"):
                    if sc.get(k) is not None:
                        f[f"{name}_{k}"] = sc[k]
            for k, a in (m.get("assumptions") or {}).items():
                if isinstance(a.get("value"), (int, float)) and not isinstance(a.get("value"), bool):
                    f[f"assumption_{k}"] = a["value"]
        ven = results.get("venues")
        if ven and ven.status == "completed":
            for o in ven.data.get("options", []):
                f[f"{o['option_id']}_total_usd"] = o["total_usd"]
                f[f"{o['option_id']}_upfront_usd"] = o["upfront_cash_usd"]
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
                model = r.data.get("model") or {}
                item["scenarios"] = model.get("scenarios")
                item["break_even_attendance"] = model.get("break_even_attendance")
                item["missing_inputs"] = model.get("missing_inputs")
            if key == "lessons":
                item["lessons"] = r.data.get("lessons")
                item["disagreements"] = r.data.get("disagreements")
            specialists[key] = item
        return {"request": request, "intent": intent, "research_mode": ctx.research_mode, "specialists": specialists,
                "revision_history": extra.get("revision_history"), "unresolved_conflicts": extra.get("unresolved_conflicts", []),
                "revision_reasons": extra.get("revision_reasons", []), "event": extra.get("event"),
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

