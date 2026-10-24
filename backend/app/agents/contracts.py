"""Typed contracts that every agent speaks.

A specialist receives an AgentTask and returns an AgentResult. Tools return
ToolResults. Anything taken from outside the database is a SourceRecord. Each
delegation is stored as an AgentHandoff. All of these are Pydantic models,
validated when created and again when read back from storage.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentName(str, Enum):
    ORCHESTRATOR = "orchestrator"
    MISSION_DISCOVERY = "mission_discovery"
    FUNDRAISING_EVENTS = "fundraising_events"
    FINANCIAL_ANALYSIS = "financial_analysis"
    DONATIONS_COMPLIANCE = "donations_compliance"
    PARTNERSHIPS_OUTREACH = "partnerships_outreach"
    EVENT_INTELLIGENCE = "event_intelligence"


Verification = Literal["verified", "unverified", "synthetic", "internal"]
FindingKind = Literal["verified_fact", "computed", "estimate", "assumption", "opinion", "recommendation"]
ResultStatus = Literal["completed", "needs_revision", "refused", "failed", "stopped"]


class SourceRecord(BaseModel):
    """Where a claim came from.

    verification:
      verified   - fetched live just now: HTTP success, and the title was read
      unverified - came from a search result, but the fetch failed or was skipped
      synthetic  - a labeled demo fixture, never presented as live research
      internal   - a SAM SPACE database record (event, reflection, ledger row)
    """

    id: str
    title: str
    url: str | None = None
    publisher: str | None = None
    published: str | None = None
    retrieved_at: str | None = None
    verification: Verification
    http_status: int | None = None
    note: str | None = None


class Finding(BaseModel):
    claim: str
    kind: FindingKind
    source_ids: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] | None = None


class ToolResult(BaseModel):
    tool: str
    ok: bool
    summary: str = ""
    data: Any = None
    sources: list[SourceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    duration_ms: int = 0


class UsageSummary(BaseModel):
    model_calls: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    web_search_calls: int = 0
    cost_usd: float = 0.0
    models: list[str] = Field(default_factory=list)


class Constraint(BaseModel):
    """A requirement passed to a specialist, e.g. from Finance or Event Intelligence."""

    name: str
    detail: str
    value: float | str | None = None
    source_agent: AgentName | None = None


class AgentTask(BaseModel):
    run_id: int
    step_key: str
    agent: AgentName
    objective: str
    kind: Literal["task", "revision"] = "task"
    revision_round: int = 0
    inputs: dict[str, Any] = Field(default_factory=dict)
    constraints: list[Constraint] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)


class AgentResult(BaseModel):
    run_id: int
    step_key: str
    agent: AgentName
    status: ResultStatus
    summary: str
    findings: list[Finding] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    usage: UsageSummary = Field(default_factory=UsageSummary)
    duration_ms: int = 0


class AgentHandoff(BaseModel):
    """One delegation as stored and shown in Agent Activity (never prompts)."""

    id: int
    run_id: int
    step_key: str | None
    kind: str | None
    revision_round: int | None
    from_agent: str
    to_agent: str
    objective: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
