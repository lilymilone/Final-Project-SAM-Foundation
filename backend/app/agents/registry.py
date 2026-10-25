"""The seven SAM SPACE agents: purpose, tool allow-list, and typical tasks.

The allow-lists are enforced by the ToolRegistry, so each agent can touch only
its own tools. No agent has a tool that sends, pays, books, publishes, or
submits anything. Only the Orchestrator delegates, and it does so in code
(recorded as handoffs), not through a tool a specialist could call.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..ai.router import TaskProfile
from .contracts import AgentName


@dataclass(frozen=True)
class AgentSpec:
    name: AgentName
    display_name: str
    purpose: str
    allowed_tools: tuple[str, ...]
    typical_tasks: tuple[TaskProfile, ...]
    status: str = "active"


def _t(agent: AgentName, task: str, complexity: str, reasoning: bool, risk: str, tin: int, tout: int) -> TaskProfile:
    return TaskProfile(agent.value, task, complexity, reasoning, risk, tin, tout)  # type: ignore[arg-type]


A = AgentName

# Task profiles drive model routing (see ai/router.py). They are module-level so
# agents and the routing preview use exactly the same numbers.
CLASSIFY = _t(A.ORCHESTRATOR, "Classify the board's request", "low", False, "low", 900, 300)
BOARD_RECOMMENDATION = _t(A.ORCHESTRATOR, "Board-ready recommendation with trade-offs", "high", True, "high", 9000, 2500)
SUMMARY_REPORT = _t(A.ORCHESTRATOR, "Summarize specialist results for the board", "medium", False, "medium", 5000, 1500)
LESSONS = _t(A.EVENT_INTELLIGENCE, "Synthesize lessons from events and reflections", "medium", True, "low", 4000, 2000)
VENUE_STRATEGY = _t(A.FUNDRAISING_EVENTS, "Shortlist venues and fundraising strategy", "medium", True, "medium", 5000, 2000)
VENUE_SEARCH = _t(A.FUNDRAISING_EVENTS, "Web search: venue candidates", "low", False, "low", 9000, 1500)
FINANCE_NARRATIVE = _t(A.FINANCIAL_ANALYSIS, "Explain computed financial results", "medium", False, "high", 4000, 1200)
ACK_TEMPLATE = _t(A.DONATIONS_COMPLIANCE, "Draft acknowledgment template and review items", "low", False, "medium", 1500, 1200)
MISSION_SEARCH = _t(A.MISSION_DISCOVERY, "Web search: mission-aligned opportunities", "low", False, "low", 9000, 1500)
MISSION_CLASSIFY = _t(A.MISSION_DISCOVERY, "Classify and summarize sources", "medium", False, "low", 4000, 1800)
PARTNER_SEARCH = _t(A.PARTNERSHIPS_OUTREACH, "Web search: prospective partners", "low", False, "low", 9000, 1500)
OUTREACH_DRAFTS = _t(A.PARTNERSHIPS_OUTREACH, "Write personalized outreach drafts", "low", False, "low", 2500, 1800)

AGENT_SPECS: tuple[AgentSpec, ...] = (
    AgentSpec(
        A.ORCHESTRATOR, "Orchestrator",
        "Reads the board's request, picks the specialists, manages dependencies and revisions, and writes the board-ready recommendation.",
        ("read_event_plan", "create_event_plan", "evaluate_constraints", "verify_final_result"),
        (CLASSIFY, BOARD_RECOMMENDATION, SUMMARY_REPORT),
    ),
    AgentSpec(
        A.MISSION_DISCOVERY, "Mission Discovery",
        "Researches mental-health and eating-disorder organizations, research initiatives, awareness events, and partnership opportunities.",
        ("search_web", "fetch_source", "classify_mission_alignment", "save_research_finding"),
        (MISSION_SEARCH, MISSION_CLASSIFY),
    ),
    AgentSpec(
        A.FUNDRAISING_EVENTS, "Fundraising & Events",
        "Researches venues (Manhattan first), builds fundraising strategy, and prices every option with the budget calculator.",
        ("search_venues", "fetch_source", "save_venue_candidate", "compute_event_model", "get_historical_lessons", "read_event_plan"),
        (VENUE_SEARCH, VENUE_STRATEGY),
    ),
    AgentSpec(
        A.FINANCIAL_ANALYSIS, "Financial Analysis",
        "Analyzes recorded financial data and checks event affordability. All arithmetic is deterministic Python.",
        ("read_financial_records", "compute_financial_position", "recompute_event_model", "check_event_affordability"),
        (FINANCE_NARRATIVE,),
    ),
    AgentSpec(
        A.DONATIONS_COMPLIANCE, "Donations & Compliance",
        "Organizes contribution records, flags missing information, drafts acknowledgments, and lists issues for professional review.",
        ("read_donations", "flag_donation_issues", "create_acknowledgment_drafts"),
        (ACK_TEMPLATE,),
    ),
    AgentSpec(
        A.PARTNERSHIPS_OUTREACH, "Partnerships & Outreach",
        "Identifies prospective partners and writes personalized, unsent outreach drafts.",
        ("search_web", "fetch_source", "read_saved_findings", "create_outreach_draft"),
        (PARTNER_SEARCH, OUTREACH_DRAFTS),
    ),
    AgentSpec(
        A.EVENT_INTELLIGENCE, "Event Intelligence & Learning",
        "Compares past events and board reflections, surfaces disagreements, and shares evidence-backed lessons with the Events agent.",
        ("read_historical_events", "read_board_reflections", "compare_event_outcomes", "get_historical_lessons", "save_historical_lesson"),
        (LESSONS,),
    ),
)

AGENTS_BY_NAME: dict[AgentName, AgentSpec] = {spec.name: spec for spec in AGENT_SPECS}
