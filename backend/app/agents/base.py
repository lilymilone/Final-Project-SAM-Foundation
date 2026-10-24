"""Shared interfaces for every SAM SPACE agent.

Agents talk only through typed handoffs: a HandoffRequest goes in and an
AgentResult comes out. Both are stored in agent_handoffs, so a run can be
replayed and audited. Each fact is tagged as a verified fact, an estimate, or
an opinion, so the UI can show which is which.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..ai.budget import WorkflowBudget
from ..ai.llm import LLMService
from ..ai.router import ModelRouter
from ..core.permissions import Permission
from ..tools.registry import ToolRegistry


class AgentName(str, Enum):
    ORCHESTRATOR = "orchestrator"
    MISSION_DISCOVERY = "mission_discovery"
    FUNDRAISING_EVENTS = "fundraising_events"
    FINANCIAL_ANALYSIS = "financial_analysis"
    DONATIONS_COMPLIANCE = "donations_compliance"
    PARTNERSHIPS_OUTREACH = "partnerships_outreach"
    EVENT_INTELLIGENCE = "event_intelligence"


class Finding(BaseModel):
    claim: str
    kind: Literal["verified_fact", "estimate", "opinion"]
    source_url: str | None = None
    source_title: str | None = None


class HandoffRequest(BaseModel):
    run_id: int
    from_agent: AgentName
    to_agent: AgentName
    objective: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)


class AgentResult(BaseModel):
    agent: AgentName
    status: Literal["completed", "needs_revision", "refused", "failed"]
    summary: str
    findings: list[Finding] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    usage_ids: list[int] = Field(default_factory=list)


@dataclass
class AgentContext:
    run_id: int
    organization_id: int
    user_id: int
    user_permissions: frozenset[Permission]
    strategy: str
    router: ModelRouter
    budget: WorkflowBudget
    tools: ToolRegistry
    llm: LLMService | None = None
    max_iterations: int = 8
    notes: list[str] = field(default_factory=list)


class BaseAgent(ABC):
    name: AgentName

    @abstractmethod
    def run(self, request: HandoffRequest, ctx: AgentContext) -> AgentResult:
        """Do one handoff's work and return a typed result."""
