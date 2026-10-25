"""Structured AgentReports: how every specialist reports to the Orchestrator (the Boss Agent).

A report is built in code from the specialist's validated AgentResult plus the run's own logs (tool calls, model usage),
so it is always complete and never a free-form paragraph. The Orchestrator reads these fields to decide what happens next:
whether outreach is worth drafting, which other agents should contribute, and what needs board or professional review.
Specialists never direct one another; they only recommend, and the Orchestrator decides.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .contracts import AgentResult, AgentTask

FIT_PROMISING = ("Strong fit", "Possible fit")  # services/opportunities.py rubric labels


class OutreachSignal(BaseModel):
    appropriate: bool
    reason: str
    candidates: list[str] = Field(default_factory=list)


class AgentSuggestion(BaseModel):
    agent: str
    reason: str


class ApprovalNeeds(BaseModel):
    board_review: bool
    professional_review: bool
    reasons: list[str] = Field(default_factory=list)


class AgentReport(BaseModel):
    task_id: int
    workflow_id: int
    step_key: str
    agent: str
    objective: str
    status: str
    work_completed: str
    key_findings: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    assumptions: list[str]
    risks_uncertainties: list[str]
    financial_considerations: list[str]
    recommended_next_actions: list[str]
    outreach: OutreachSignal
    additional_agents: list[AgentSuggestion]
    approval: ApprovalNeeds
    tool_calls: list[dict[str, Any]]
    model_usage: dict[str, Any]


def _money(v) -> str:
    return f"${v:,.0f}" if isinstance(v, (int, float)) else "not available"


def _events(result: AgentResult) -> tuple[OutreachSignal, list[AgentSuggestion], list[str]]:
    shortlist = result.data.get("shortlist") or []
    names = [s["venue"]["name"] for s in shortlist if s.get("venue")]
    money = [f"{s['venue']['name']} ({s.get('event_format', '').replace('_', ' ')}): projected {_money((s.get('model') or {}).get('total_cost_usd'))}, "
             f"upfront {_money((s.get('model') or {}).get('upfront_cash_usd'))}" for s in shortlist if s.get("venue")]
    outreach = OutreachSignal(appropriate=bool(names), candidates=names[:3],
                              reason=(f"{len(names)} venue(s) fit the guest count; an inquiry can confirm availability, pricing, catering, and "
                                      "nonprofit terms." if names else "No venue fits yet, so there is no one to write to."))
    more = [AgentSuggestion(agent="financial_analysis", reason="Check the shortlisted costs against the budget and cash position.")] if names else []
    if names:
        more.append(AgentSuggestion(agent="partnerships_outreach", reason="Prepare unsent inquiries to the shortlisted venues."))
    return outreach, more, money


def _mission(result: AgentResult) -> tuple[OutreachSignal, list[AgentSuggestion], list[str]]:
    found = result.data.get("findings") or []
    promising = [f for f in found if f.get("fit") in FIT_PROMISING and f.get("verification") in ("verified", "synthetic")]
    names = [f.get("name") or f.get("title") for f in promising]
    outreach = OutreachSignal(appropriate=bool(promising), candidates=names[:5],
                              reason=(f"{len(promising)} opportunity(ies) are well aligned and sourced; an introductory note could learn more."
                                      if promising else "No opportunity is both well aligned and verified, so outreach would be premature."))
    more = [AgentSuggestion(agent="partnerships_outreach", reason="Draft introductory messages to the promising opportunities.")] if promising else []
    if promising:
        more.append(AgentSuggestion(agent="financial_analysis", reason="State what the foundation could responsibly consider supporting, "
                                                                        "if the board's role allows financial access."))
    money = [f"{f.get('name')}: known costs {f.get('known_costs')}" for f in promising if f.get("known_costs")]
    return outreach, more, money


def _finance(result: AgentResult) -> tuple[OutreachSignal, list[AgentSuggestion], list[str]]:
    d = result.data
    money = []
    aff, model, pos = d.get("affordability") or {}, d.get("model") or {}, d.get("position") or {}
    if aff.get("verdict"):
        money.append(f"Affordability verdict: {aff['verdict'].replace('_', ' ')}.")
    if model.get("total_cost_usd") is not None:
        money.append(f"Projected total {_money(model['total_cost_usd'])}; upfront cash {_money(model.get('upfront_cash_usd'))}.")
    money += [c["detail"] for c in d.get("conflicts") or [] if c.get("detail")][:4]
    if pos.get("available_planning_budget_usd") is not None:
        money.append(f"Available unrestricted planning budget above the reserve floor: {_money(pos['available_planning_budget_usd'])} "
                     "(a starting point for discussion, not approval to spend).")
    more = [AgentSuggestion(agent="fundraising_events", reason="Revise the plan to resolve the financial conflicts.")] if d.get("conflicts") else []
    return OutreachSignal(appropriate=False, reason="Finance analyzes; it does not identify outreach targets."), more, money


def build_report(task: AgentTask, result: AgentResult, handoff_id: int, tool_calls: list[dict]) -> AgentReport:
    agent = task.agent.value
    outreach = OutreachSignal(appropriate=False, reason="This report does not identify an outreach opportunity.")
    more: list[AgentSuggestion] = []
    money: list[str] = []
    if agent == "fundraising_events":
        outreach, more, money = _events(result)
    elif agent == "mission_discovery":
        outreach, more, money = _mission(result)
    elif agent == "financial_analysis":
        outreach, more, money = _finance(result)
    elif agent == "event_intelligence" and result.data.get("lessons"):
        more = [AgentSuggestion(agent="fundraising_events", reason="Apply the evidence-backed lessons to the plan.")]
    elif agent == "partnerships_outreach":
        outreach = OutreachSignal(appropriate=False, reason="Drafts prepared; nothing is sent. A person reviews and sends them outside SAM SPACE.",
                                  candidates=[d.get("recipient") for d in result.data.get("drafts") or []])
    if result.status != "completed" and not outreach.candidates:
        outreach = OutreachSignal(appropriate=False, reason=f"The task did not finish ({result.status}), so it cannot support an outreach decision.")
    reasons = []
    if agent == "financial_analysis" and (result.data.get("conflicts") or (result.data.get("affordability") or {}).get("verdict")):
        reasons.append("Any spending decision belongs to the board.")
    if agent == "partnerships_outreach" and result.data.get("drafts"):
        reasons.append("Every draft needs a person's review before anyone contacts the organization.")
    if agent == "event_intelligence" and result.data.get("lessons"):
        reasons.append("Lessons become planning guidance once the board reviews or adopts them.")
    if agent == "event_intelligence" and result.data.get("candidate"):
        reasons.append("Extracted event details are saved only after a board member approves them.")
    review = (result.data.get("review") or {})
    professional = bool([q for q in review.get("reporting_questions") or [] if q.get("kind") != "verified_requirement"])
    if professional:
        reasons.append("Some reporting questions need an accountant or attorney.")
    if agent == "donations_compliance" and (result.data.get("drafts_created") or result.data.get("acknowledgments")):
        reasons.append("Acknowledgment drafts need the treasurer's review.")
    risks = list(result.warnings)
    if result.status != "completed":
        risks.insert(0, f"Task status: {result.status}. {result.summary}")
    actions = [f.claim for f in result.findings if f.kind == "recommendation"][:5] + list(result.next_steps)[:5]
    return AgentReport(
        task_id=handoff_id, workflow_id=task.run_id, step_key=task.step_key, agent=agent, objective=task.objective,
        status=result.status, work_completed=result.summary,
        key_findings=[{"claim": f.claim, "kind": f.kind, "confidence": f.confidence, "source_ids": f.source_ids} for f in result.findings][:15],
        sources=[{"id": s.id, "title": s.title, "url": s.url, "verification": s.verification} for s in result.sources][:20],
        assumptions=list(result.assumptions)[:10], risks_uncertainties=risks[:10], financial_considerations=money[:8],
        recommended_next_actions=actions[:8], outreach=outreach, additional_agents=more,
        approval=ApprovalNeeds(board_review=bool(reasons), professional_review=professional, reasons=reasons),
        tool_calls=tool_calls, model_usage=result.usage.model_dump(),
    )
