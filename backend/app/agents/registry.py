"""The seven SAM SPACE agents: purpose, tool allow-list, and typical tasks.

The allow-lists are enforced by the ToolRegistry. No agent has a tool that
sends, pays, books, publishes, or submits anything.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..ai.router import TaskProfile
from .base import AgentName


@dataclass(frozen=True)
class AgentSpec:
    name: AgentName
    display_name: str
    purpose: str
    allowed_tools: tuple[str, ...]
    typical_tasks: tuple[TaskProfile, ...]
    status: str = "planned"  # planned | active


def _t(agent: AgentName, task: str, complexity: str, reasoning: bool, risk: str, tin: int, tout: int) -> TaskProfile:
    return TaskProfile(agent.value, task, complexity, reasoning, risk, tin, tout)  # type: ignore[arg-type]


A = AgentName
AGENT_SPECS: tuple[AgentSpec, ...] = (
    AgentSpec(
        A.ORCHESTRATOR, "Orchestrator",
        "Coordinates the specialists, manages task dependencies, checks their results, and writes the board-ready recommendation.",
        ("delegate_to_agent", "read_event_plans", "read_historical_lessons"),
        (
            _t(A.ORCHESTRATOR, "Classify the board's request", "low", False, "low", 800, 200),
            _t(A.ORCHESTRATOR, "Board-ready recommendation with trade-offs", "high", True, "high", 9000, 1800),
        ),
    ),
    AgentSpec(
        A.MISSION_DISCOVERY, "Mission Discovery",
        "Researches mental-health and eating-disorder organizations, awareness events, research initiatives, and partnerships.",
        ("web_search", "fetch_web_page", "save_research_finding"),
        (
            _t(A.MISSION_DISCOVERY, "Organize search results into opportunities", "low", False, "low", 4000, 800),
            _t(A.MISSION_DISCOVERY, "Compare competing research findings", "medium", True, "medium", 7000, 1200),
        ),
    ),
    AgentSpec(
        A.FUNDRAISING_EVENTS, "Fundraising & Events",
        "Researches venues, develops fundraising strategies, evaluates logistics, and drafts preliminary event budgets.",
        ("web_search", "fetch_web_page", "read_event_plans", "save_venue_candidate", "compute_event_budget"),
        (
            _t(A.FUNDRAISING_EVENTS, "Extract venue details from a page", "low", False, "low", 3000, 500),
            _t(A.FUNDRAISING_EVENTS, "Revise event strategy after a conflict", "high", True, "medium", 8000, 1500),
        ),
    ),
    AgentSpec(
        A.FINANCIAL_ANALYSIS, "Financial Analysis",
        "Reads financial records, computes budget constraints in Python, and judges whether an event is affordable.",
        ("read_financial_records", "compute_budget_constraints", "compute_event_affordability"),
        (_t(A.FINANCIAL_ANALYSIS, "Interpret computed financial results", "medium", True, "high", 5000, 900),),
    ),
    AgentSpec(
        A.DONATIONS_COMPLIANCE, "Donations & Compliance",
        "Organizes donation records, finds missing information, drafts acknowledgments, and flags issues for professional review.",
        ("read_donations", "flag_missing_donation_info", "draft_acknowledgment"),
        (_t(A.DONATIONS_COMPLIANCE, "Draft a donor acknowledgment", "low", False, "medium", 1500, 500),),
    ),
    AgentSpec(
        A.PARTNERSHIPS_OUTREACH, "Partnerships & Outreach",
        "Researches potential sponsors and writes editable, unsent partnership and venue-inquiry drafts.",
        ("web_search", "fetch_web_page", "create_outreach_draft"),
        (_t(A.PARTNERSHIPS_OUTREACH, "Write a partnership inquiry draft", "low", False, "low", 2000, 600),),
    ),
    AgentSpec(
        A.EVENT_INTELLIGENCE, "Event Intelligence & Learning",
        "Reviews past events and board reflections to find what worked, what failed, and lessons for future fundraisers.",
        ("read_historical_events", "read_board_reflections", "save_historical_lesson"),
        (
            _t(A.EVENT_INTELLIGENCE, "Synthesize board reflections", "medium", True, "low", 6000, 1000),
            _t(A.EVENT_INTELLIGENCE, "Weigh conflicting historical evidence", "high", True, "medium", 9000, 1400),
        ),
    ),
)

AGENTS_BY_NAME: dict[AgentName, AgentSpec] = {spec.name: spec for spec in AGENT_SPECS}
