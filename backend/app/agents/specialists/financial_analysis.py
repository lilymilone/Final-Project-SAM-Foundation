"""Agent 4: Financial Analysis.

Reads the ledger (chair/treasurer only). Then computes, entirely in Python:
revenue, expenses, reserve, the available planning budget (only when the
records support one), projected event cost, break-even, sensitivity, and
pass/fail affordability checks. The verdict and the conflicts come from code.
The model only explains them in plain language and lists questions for the
board. If any check fails, the result is "needs_revision" so the Orchestrator
can send the plan back to the Events agent.
"""

from __future__ import annotations

from ..base import BaseAgent
from ..contracts import AgentName, AgentResult, AgentTask, Finding, SourceRecord
from ..outputs import FinanceNarrative
from ..registry import FINANCE_NARRATIVE
from ..runtime import RunContext

INSTRUCTIONS = """Explain the computed financial results to a volunteer board.
- The verdict, checks, and conflicts were computed by code. Explain them; never change or contradict them.
- Quote only dollar figures that appear in the data.
- conditions: what must be true to proceed (e.g. sponsorship commitments before deposits).
- questions_for_board: decisions only the board can make."""


def _money_findings(position: dict) -> list[Finding]:
    out = []
    if position.get("total_income_usd") is not None:
        out.append(Finding(claim=f"Recorded income ${position['total_income_usd']:,.0f} and expenses ${position['total_expense_usd']:,.0f} "
                                 f"from {position['period_start']} to {position['period_end']}.", kind="computed", source_ids=["ledger"]))
    if position.get("available_planning_budget_usd") is not None:
        out.append(Finding(claim=f"Available planning budget ${position['available_planning_budget_usd']:,.0f}. "
                                 f"{position['available_planning_budget_basis']}", kind="computed", source_ids=["ledger"]))
    elif position.get("available_planning_budget_basis"):
        out.append(Finding(claim=position["available_planning_budget_basis"], kind="computed", source_ids=["ledger"]))
    return out


class FinancialAnalysisAgent(BaseAgent):
    name = AgentName.FINANCIAL_ANALYSIS

    def execute(self, task: AgentTask, ctx: RunContext) -> AgentResult:
        records = self.tool(ctx, "read_financial_records")
        position = self.tool(ctx, "compute_financial_position", records=records.data).data
        sources: list[SourceRecord] = list(records.sources)
        assumptions = [f"Reserve guideline: keep {position['reserve_guideline_months']:g} months of average expenses (board guideline)."]
        if any(r.get("is_demo") for r in records.data):
            assumptions.append("Figures come from the synthetic demo ledger.")

        choice = task.inputs.get("top_choice")
        if not choice:  # financial review without an event
            narrative = self.think(ctx, FINANCE_NARRATIVE, INSTRUCTIONS, {"position": position}, FinanceNarrative)
            return self.result(task, "completed", narrative.summary, findings=_money_findings(position), sources=sources,
                               assumptions=assumptions, warnings=narrative.risks, next_steps=narrative.questions_for_board,
                               data={"position": position, "narrative": narrative.model_dump()})

        budget = choice["budget"]
        revenue = task.inputs.get("revenue") or {}
        per_attendee = revenue.get("per_attendee_usd")
        be = self.tool(ctx, "compute_break_even", budget=budget, per_attendee_usd=per_attendee).data
        sens = self.tool(ctx, "compute_sensitivity", budget=budget, per_attendee_usd=per_attendee).data
        aff = self.tool(ctx, "check_event_affordability", budget=budget, position=position,
                        budget_limit_usd=task.inputs.get("budget_limit_usd"), break_even_result=be,
                        revenue=revenue if per_attendee else None,
                        min_contingency_pct=task.inputs.get("min_contingency_pct")).data
        narrative = self.think(ctx, FINANCE_NARRATIVE, INSTRUCTIONS, {
            "option": {"venue": choice["venue"]["name"], "format": choice["event_format"]},
            "budget": budget, "position": position, "revenue_scenarios": revenue, "break_even": be,
            "sensitivity": sens, "affordability": aff,
        }, FinanceNarrative)

        findings = _money_findings(position) + [
            Finding(claim=f"{choice['venue']['name']}: projected total ${budget['total_usd']:,.0f}, upfront cash ${budget['upfront_cash_usd']:,.0f}.",
                    kind="computed", source_ids=[choice["venue"]["source_id"]]),
        ] + [Finding(claim=f"{'PASS' if c['passed'] else 'FAIL' if c['passed'] is False else 'UNKNOWN'}: {c['name']}. {c['detail']}",
                     kind="computed", source_ids=["ledger"]) for c in aff["checks"]]
        status = "needs_revision" if aff["conflicts"] else "completed"
        return self.result(
            task, status, narrative.summary, findings=findings, sources=sources,
            assumptions=assumptions + budget["assumptions"] + revenue.get("assumptions", []),
            warnings=narrative.risks, next_steps=narrative.conditions + narrative.questions_for_board,
            data={"position": position, "budget": budget, "option_id": choice["option_id"], "venue": choice["venue"]["name"],
                  "event_format": choice["event_format"], "break_even": be, "sensitivity": sens, "affordability": aff,
                  "verdict": aff["verdict"], "conflicts": aff["conflicts"], "narrative": narrative.model_dump()},
        )
