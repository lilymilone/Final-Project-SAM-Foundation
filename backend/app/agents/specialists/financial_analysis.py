"""Agent 4: Financial Analysis.

Reads the ledger (chair/treasurer only) and computes the foundation's position
in Python. It recomputes the event model itself from the option's labeled
assumptions, so it never trusts another agent's arithmetic. Then it checks
affordability:

  * cost vs the board's maximum planning budget
  * upfront cash vs the available planning budget
  * base-case and conservative net
  * break-even attendance and the fundraising target
  * contingency vs the history lesson

Recorded income is never treated as cash: only the reserve above the board's
floor counts toward deposits. If information is missing, the checks say
"unknown" instead of guessing. The verdict and the conflicts come from code,
and the model only explains them.
"""

from __future__ import annotations

from ..base import BaseAgent
from ..contracts import AgentName, AgentResult, AgentTask, Finding, SourceRecord
from ..outputs import FinanceNarrative
from ..registry import FINANCE_NARRATIVE
from ..runtime import RunContext

INSTRUCTIONS = """Explain the computed financial results to a volunteer board.
- The model, verdict, checks, and conflicts were computed by code. Explain them; never change or contradict them.
- Quote only dollar figures that appear in the data. Recorded income is not cash on hand; say so if relevant.
- If inputs are missing, say exactly which ones and what the board must provide. Never fill gaps with guesses.
- conditions: what must be true to proceed (e.g. sponsorship commitments before deposits).
- questions_for_board: decisions only the board can make."""


def _position_findings(position: dict) -> list[Finding]:
    out = []
    if position.get("months_of_data"):
        out.append(Finding(claim=f"Recorded income ${position['total_income_usd']:,.0f} and expenses ${position['total_expense_usd']:,.0f} "
                                 f"({position['period_start']} to {position['period_end']}). Recorded income is not cash on hand.",
                           kind="computed", source_ids=["ledger"]))
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
        if not choice:  # a financial review without an event
            narrative = self.think(ctx, FINANCE_NARRATIVE, INSTRUCTIONS, {"position": position}, FinanceNarrative)
            return self.result(task, "completed", narrative.summary, findings=_position_findings(position), sources=sources,
                               assumptions=assumptions, warnings=narrative.risks, next_steps=narrative.questions_for_board,
                               data={"position": position, "narrative": narrative.model_dump()})

        model = self.tool(ctx, "recompute_event_model", assumptions=choice["model"]["assumptions"],
                          max_budget_usd=task.inputs.get("budget_limit_usd"), target_usd=task.inputs.get("fundraising_goal_usd")).data
        aff = self.tool(ctx, "check_event_affordability", model=model, position=position,
                        min_contingency_pct=task.inputs.get("min_contingency_pct")).data
        narrative = self.think(ctx, FINANCE_NARRATIVE, INSTRUCTIONS, {
            "option": {"venue": choice["venue"]["name"], "format": choice["event_format"], "pricing_status": choice["venue"].get("pricing_status")},
            "model": {k: model[k] for k in ("lines", "subtotal_usd", "contingency_pct", "contingency_usd", "total_cost_usd", "upfront_cash_usd",
                                            "scenarios", "break_even_attendance", "break_even_note", "missing_inputs", "scenario_definitions")},
            "position": position, "affordability": aff,
        }, FinanceNarrative)

        findings = _position_findings(position) + [
            Finding(claim=f"{choice['venue']['name']}: projected cost ${model['total_cost_usd']:,.0f}, upfront cash ${model['upfront_cash_usd']:,.0f}.",
                    kind="computed", source_ids=[f"{choice['venue']['source_id']}:website"]),
        ] + [Finding(claim=f"{'PASS' if c['passed'] else 'FAIL' if c['passed'] is False else 'UNKNOWN'}: {c['name']}. {c['detail']}",
                     kind="computed", source_ids=["ledger"]) for c in aff["checks"]]
        model_assumptions = sorted({a["basis"] for a in model["assumptions"].values() if a["kind"] in ("placeholder", "hypothetical", "missing")})
        warnings = narrative.risks + aff["warnings"] + ([f"Missing inputs: {', '.join(model['missing_inputs'])}."] if model["missing_inputs"] else [])
        return self.result(
            task, "needs_revision" if aff["conflicts"] else "completed", narrative.summary, findings=findings, sources=sources,
            assumptions=assumptions + model_assumptions + [aff["cash_note"]], warnings=warnings,
            next_steps=narrative.conditions + narrative.questions_for_board,
            data={"position": position, "model": model, "option_id": choice["option_id"], "venue": choice["venue"]["name"],
                  "event_format": choice["event_format"], "affordability": aff, "verdict": aff["verdict"],
                  "conflicts": aff["conflicts"], "narrative": narrative.model_dump()},
        )
