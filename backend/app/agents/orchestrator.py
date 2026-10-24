"""Orchestrator: turns a board request into a dependency-ordered plan of handoffs.

This stage defines the plan structure, the dependency ordering, and the
reference gala workflow. Running the specialists comes in the next build stage.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .base import AgentName


class PlannedStep(BaseModel):
    key: str
    agent: AgentName
    objective: str
    depends_on: list[str] = Field(default_factory=list)


class WorkflowPlan(BaseModel):
    request: str
    steps: list[PlannedStep]


class PlanError(ValueError):
    pass


def execution_order(plan: WorkflowPlan) -> list[PlannedStep]:
    """Topological order of steps. Raises PlanError on unknown deps or cycles."""
    steps = {s.key: s for s in plan.steps}
    for step in plan.steps:
        missing = [d for d in step.depends_on if d not in steps]
        if missing:
            raise PlanError(f"Step '{step.key}' depends on unknown step(s): {missing}")
    ordered: list[PlannedStep] = []
    state: dict[str, str] = {}

    def visit(key: str) -> None:
        if state.get(key) == "done":
            return
        if state.get(key) == "visiting":
            raise PlanError(f"Cycle detected at step '{key}'")
        state[key] = "visiting"
        for dep in steps[key].depends_on:
            visit(dep)
        state[key] = "done"
        ordered.append(steps[key])

    for step in plan.steps:
        visit(step.key)
    return ordered


def gala_plan(request: str) -> WorkflowPlan:
    """Reference plan for a fundraising gala (the workflow the board asked for)."""
    A = AgentName
    return WorkflowPlan(
        request=request,
        steps=[
            PlannedStep(key="lessons", agent=A.EVENT_INTELLIGENCE, objective="Retrieve lessons from past events."),
            PlannedStep(key="venues", agent=A.FUNDRAISING_EVENTS, objective="Research candidate venues.", depends_on=["lessons"]),
            PlannedStep(key="finance", agent=A.FINANCIAL_ANALYSIS, objective="Check affordability against the books.", depends_on=["venues"]),
            PlannedStep(key="conflicts", agent=A.ORCHESTRATOR, objective="Identify conflicts or constraints.", depends_on=["lessons", "finance"]),
            PlannedStep(key="revise", agent=A.FUNDRAISING_EVENTS, objective="Revise recommendations if needed.", depends_on=["conflicts"]),
            PlannedStep(key="outreach", agent=A.PARTNERSHIPS_OUTREACH, objective="Draft unsent venue and sponsor inquiries.", depends_on=["revise"]),
            PlannedStep(key="packet", agent=A.ORCHESTRATOR, objective="Write the board-ready recommendation.", depends_on=["revise", "outreach"]),
        ],
    )
