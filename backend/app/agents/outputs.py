"""Pydantic schemas for model-generated output, one per agent step.

These are sent to OpenAI as strict JSON schemas, and every reply is checked
against them before anything uses it. Fields have no defaults (strict mode
requires every field), and optional values are nullable. Validators enforce
the rules a schema alone cannot express.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

Intent = Literal[
    "plan_event", "mission_discovery", "partnership_outreach", "financial_review", "donations_review",
    "event_learning", "unsupported",
]
EventFormat = Literal["seated_dinner", "reception"]
Confidence = Literal["low", "medium", "high"]


class RequestAnalysis(BaseModel):
    intent: Intent
    city: str | None
    attendance: int | None
    event_type: str | None
    event_format: EventFormat | None
    budget_limit_usd: float | None
    research_topic: str | None
    rationale: str

    @field_validator("attendance")
    @classmethod
    def _attendance(cls, v: int | None) -> int | None:
        if v is not None and not 1 <= v <= 5000:
            raise ValueError("attendance must be between 1 and 5000")
        return v


# --- Event Intelligence -----------------------------------------------------------


class Lesson(BaseModel):
    kind: Literal["what_worked", "recurring_problem", "recommendation"]
    text: str
    evidence_event_ids: list[int]
    evidence_reflection_ids: list[int]
    confidence: Confidence


class Disagreement(BaseModel):
    topic: str
    positions: list[str]
    evidence_reflection_ids: list[int]


class PlanningConstraint(BaseModel):
    name: str
    detail: str
    evidence_reflection_ids: list[int]


class LessonsOutput(BaseModel):
    summary: str
    lessons: list[Lesson]
    disagreements: list[Disagreement]
    planning_constraints: list[PlanningConstraint]
    recommended_contingency_pct: float | None
    contingency_evidence_reflection_ids: list[int]
    uncertainties: list[str]

    @field_validator("recommended_contingency_pct")
    @classmethod
    def _contingency(cls, v: float | None) -> float | None:
        if v is not None and not 0 <= v <= 0.5:
            raise ValueError("recommended_contingency_pct must be a fraction between 0 and 0.5 (e.g. 0.15)")
        return v


# --- Fundraising & Events ---------------------------------------------------------


class VenueChoice(BaseModel):
    option_id: str
    rank: int
    rationale: str
    lessons_applied: list[str]


class EventStrategyOutput(BaseModel):
    summary: str
    shortlist: list[VenueChoice]
    fundraising_strategy: list[str]
    logistics_notes: list[str]
    changes_from_previous: str | None
    risks: list[str]
    uncertainties: list[str]

    @field_validator("shortlist")
    @classmethod
    def _shortlist(cls, v: list[VenueChoice]) -> list[VenueChoice]:
        if not v:
            raise ValueError("shortlist must contain at least one option_id from the options provided")
        return v


# --- Financial Analysis -----------------------------------------------------------


class FinanceNarrative(BaseModel):
    summary: str
    explanation: str
    conditions: list[str]
    risks: list[str]
    questions_for_board: list[str]


# --- Donations & Compliance -------------------------------------------------------

MERGE_FIELDS = ("{{donor_name}}", "{{amount}}", "{{date}}")


class ReviewItem(BaseModel):
    issue: str
    why_professional_review: str
    related_flag: str


class AcknowledgmentTemplate(BaseModel):
    summary: str
    subject: str
    body: str
    review_items: list[ReviewItem]

    @field_validator("body")
    @classmethod
    def _merge_fields(cls, v: str) -> str:
        missing = [f for f in MERGE_FIELDS if f not in v]
        if missing:
            raise ValueError(f"body must contain the merge fields {', '.join(missing)} (names and amounts are filled in locally)")
        return v


# --- Mission Discovery ------------------------------------------------------------


class MissionFinding(BaseModel):
    source_id: str
    category: Literal["organization", "research", "event", "partnership", "cause"]
    alignment: Literal["high", "medium", "low", "none"]
    summary: str
    date_text: str | None
    uncertainty: str
    why_relevant: str


class MissionOutput(BaseModel):
    summary: str
    findings: list[MissionFinding]
    gaps: list[str]


class SearchHit(BaseModel):
    title: str
    url: str
    publisher: str | None
    published: str | None
    snippet: str


class SearchHits(BaseModel):
    hits: list[SearchHit]
    search_notes: str


class VenueHit(BaseModel):
    name: str
    neighborhood: str | None
    url: str
    formats: list[EventFormat]
    capacity_seated: int | None
    capacity_reception: int | None
    rental_usd: float | None
    fnb_per_guest_usd: float | None
    pricing_quote: str | None
    notes: str


class VenueHits(BaseModel):
    venues: list[VenueHit]
    search_notes: str


# --- Partnerships & Outreach ------------------------------------------------------


class DraftOut(BaseModel):
    target_id: str
    draft_type: Literal["venue_inquiry", "partnership", "sponsor"]
    subject: str
    body: str
    personalization_basis: str


class DraftsOutput(BaseModel):
    summary: str
    drafts: list[DraftOut]


# --- Orchestrator -----------------------------------------------------------------


class BoardOption(BaseModel):
    title: str
    option_id: str | None
    summary: str


class BoardRecommendation(BaseModel):
    headline: str
    recommendation: str
    rationale: list[str]
    options: list[BoardOption]
    risks: list[str]
    decisions_for_board: list[str]
    next_steps: list[str]
    lessons_applied: list[str]
    caveats: list[str]
