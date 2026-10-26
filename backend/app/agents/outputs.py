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
    "event_learning", "document_extraction", "legacy_import", "unsupported",
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


LessonArea = Literal["fundraising_approach", "logistics", "sponsorship", "board_feedback", "costs", "community", "other"]


class Lesson(BaseModel):
    kind: Literal["what_worked", "recurring_problem", "recommendation"]
    theme: str
    text: str
    evidence_event_ids: list[int]
    evidence_reflection_ids: list[int]
    confidence: Confidence
    area: LessonArea | None = None


class Theme(BaseModel):
    name: str
    polarity: Literal["strength", "weakness", "mixed"]
    description: str
    evidence_event_ids: list[int]
    evidence_reflection_ids: list[int]


class Disagreement(BaseModel):
    topic: str
    positions: list[str]
    evidence_reflection_ids: list[int]


class PlanningConstraint(BaseModel):
    name: str
    detail: str
    evidence_reflection_ids: list[int]


class CommunityInsight(BaseModel):
    lens: Literal["welcomed", "connection", "volunteers", "community", "accessibility", "improvement"]
    observation: str
    quote: str  # copied word for word from a cited reflection or event record; code checks it
    evidence_reflection_ids: list[int]
    evidence_event_ids: list[int]
    evidence_type: Literal["board_observation", "attendee_feedback_reported", "verified_outcome"]


class SourcedValue(BaseModel):
    value: str | None  # as written in the source; null when the sources do not say
    source_id: str | None  # "description" or "doc:<id>"
    quote: str | None  # the exact words it comes from; code checks that they are in the source


FigureField = Literal["attendance", "fundraising_goal_usd", "funds_raised_usd", "total_cost_usd", "net_proceeds_usd",
                      "sponsorship_usd", "volunteers_count", "planned_budget_usd"]


class ExtractedFigure(BaseModel):
    field: FigureField
    value: float
    source_id: str
    quote: str


class SourcedPoint(BaseModel):
    text: str
    source_id: str
    quote: str


class EventExtraction(BaseModel):
    """Candidate details for one past event. Every value must come with the exact words it rests on."""
    summary: str
    title: SourcedValue
    date: SourcedValue
    location: SourcedValue
    venue: SourcedValue
    event_type: SourcedValue
    description: SourcedValue
    figures: list[ExtractedFigure]  # list every figure found, even when two sources disagree
    sponsors: list[SourcedPoint]
    what_worked: list[SourcedPoint]
    what_did_not_work: list[SourcedPoint]
    lessons_learned: list[SourcedPoint]  # interpretations; quote = the words each lesson rests on
    missing_information: list[str]


class LessonsOutput(BaseModel):
    summary: str
    themes: list[Theme]
    lessons: list[Lesson]
    disagreements: list[Disagreement]
    planning_constraints: list[PlanningConstraint]
    recommended_contingency_pct: float | None
    contingency_evidence_reflection_ids: list[int]
    numeric_comparison_note: str | None
    uncertainties: list[str]
    # None-default fields are still required in the strict schema sent to the model (None defaults are stripped).
    community_insights: list[CommunityInsight] | None = None
    knowledge_used: list[str] | None = None  # Foundation Knowledge Base ids relied on (code keeps only ids it supplied)

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


class MissionContribution(BaseModel):
    inclusion: str
    connection: str
    accessibility: str
    recognition: str
    charitable_alignment: str
    community_lessons_applied: list[str]
    open_questions: list[str]


class EventStrategyOutput(BaseModel):
    summary: str
    shortlist: list[VenueChoice]
    fundraising_strategy: list[str]
    logistics_notes: list[str]
    changes_from_previous: str | None
    risks: list[str]
    uncertainties: list[str]
    mission_contribution: MissionContribution | None = None
    knowledge_used: list[str] | None = None  # Foundation Knowledge Base ids relied on (code keeps only ids it supplied)
    prior_vendors_considered: list[str] | None = None  # recorded past venues/vendors and how they compare to the new options

    @field_validator("shortlist")
    @classmethod
    def _shortlist(cls, v: list[VenueChoice]) -> list[VenueChoice]:
        if not v:
            raise ValueError("shortlist must contain at least one option_id from the options provided")
        return v


# --- Financial Analysis -----------------------------------------------------------


class FigureOut(BaseModel):
    label: str  # the line item exactly as written
    original_amount: str  # the amount exactly as printed, e.g. "$12,400" or "(1,250)"
    page: int
    kind: Literal["income", "expense", "reserve", "cash"]
    category: str
    restriction: Literal["unrestricted", "temporarily_restricted", "permanently_restricted"] | None
    purpose: Literal["operations", "program", "event", "fundraising"] | None
    is_total: bool  # a subtotal or total line (kept only to cross-check the components)
    period_end: str | None  # YYYY-MM if this figure's period differs from the document's


class FinancialReview(BaseModel):
    summary: str
    performance: str
    significant_categories: list[str]
    variance_explanations: list[str]
    restricted_funds_note: str
    capacity_explanation: str
    scenario_comparison: str
    uncertainties: list[str]
    questions_for_board: list[str]
    knowledge_used: list[str] | None = None  # Foundation Knowledge Base ids relied on (code keeps only ids it supplied)


class ExtractedFigures(BaseModel):
    summary: str
    document_type: Literal["income_statement", "financial_position", "event_budget", "donation_summary", "expense_records",
                           "cash_flow", "ledger", "other"]
    reporting_period_label: str | None
    period_end: str | None  # YYYY-MM
    period_months: int | None
    currency: str
    figures: list[FigureOut]
    unclear: list[str]


class FinanceNarrative(BaseModel):
    summary: str
    explanation: str
    conditions: list[str]
    risks: list[str]
    questions_for_board: list[str]
    knowledge_used: list[str] | None = None  # Foundation Knowledge Base ids relied on (code keeps only ids it supplied)


# --- Donations & Compliance -------------------------------------------------------

MERGE_FIELDS = ("{{donor_name}}", "{{date}}")  # plus {{gift}} (or the older {{amount}}): filled in locally, never seen by the model


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
        missing = [f for f in MERGE_FIELDS if f not in v] + ([] if "{{gift}}" in v or "{{amount}}" in v else ["{{gift}}"])
        if missing:
            raise ValueError(f"body must contain the merge fields {', '.join(missing)} (names and amounts are filled in locally)")
        return v


class ReportingQuestion(BaseModel):
    question: str
    why: str
    ref_ids: list[str]
    kind: Literal["verified_requirement", "general_guidance", "needs_professional_review"]
    professional: Literal["accountant", "attorney", "none"]


class DonationReview(BaseModel):
    summary: str
    incomplete_records: list[str]
    campaign_notes: list[str]
    reporting_questions: list[ReportingQuestion]
    knowledge_used: list[str] | None = None  # Foundation Knowledge Base ids relied on (code keeps only ids it supplied)


# --- Mission Discovery ------------------------------------------------------------


class ResearchPlan(BaseModel):
    search_query: str
    geography: str | None
    count_requested: int | None
    opportunity_types: list[Literal["organization", "research", "event", "partnership", "sponsor"]]
    focus_criteria: list[str]


AlignmentLevel = Literal["strong", "partial", "unclear", "none"]


class Level(BaseModel):
    level: AlignmentLevel
    explanation: str


class CharitableAlignment(BaseModel):
    mental_health: Level
    eating_disorders: Level
    community_wellbeing: Level


class PhilosophicalAlignment(BaseModel):
    compassion: Level
    belonging_inclusion: Level
    human_connection: Level
    seen_heard_valued: Level


class PracticalFeasibility(BaseModel):
    geography: str
    cost: str
    volunteers: str
    timing: str
    operations: str
    blockers: list[str]


class EvidenceQuality(BaseModel):
    reliability: Literal["official_source", "third_party", "unclear"]
    verified_items: list[str]
    unconfirmed_claims: list[str]
    missing_info: list[str]


class OpportunityAnalysis(BaseModel):
    source_id: str
    name: str
    category: Literal["organization", "research", "event", "partnership", "sponsor"]
    geography: str | None
    purpose: str
    activities: list[str]
    dates_text: str | None
    partnership_types: list[str]
    known_costs: str | None
    contribution_ways: list[str]
    charitable: CharitableAlignment
    philosophical: PhilosophicalAlignment
    practical: PracticalFeasibility
    evidence: EvidenceQuality
    alignment_summary: str
    next_step: str


class MissionAnalysis(BaseModel):
    summary: str
    opportunities: list[OpportunityAnalysis]
    gaps: list[str]
    knowledge_used: list[str] | None = None  # Foundation Knowledge Base ids relied on (code keeps only ids it supplied)


class SearchHit(BaseModel):
    title: str
    url: str
    publisher: str | None
    published: str | None
    date_claim: str | None  # an upcoming event or deadline date the source states
    snippet: str


class SearchHits(BaseModel):
    hits: list[SearchHit]
    search_notes: str


class VenueHit(BaseModel):
    name: str
    address: str | None
    neighborhood: str | None
    website_url: str
    source_url: str
    formats: list[EventFormat]
    capacity_seated: int | None
    capacity_reception: int | None
    capacity_quote: str | None
    rental_usd: float | None
    fnb_per_guest_usd: float | None
    fnb_minimum_usd: float | None
    pricing_quote: str | None
    amenities: list[str]
    restrictions: list[str]
    notes: str


class VenueHits(BaseModel):
    venues: list[VenueHit]
    search_notes: str


# --- Partnerships & Outreach ------------------------------------------------------


DraftType = Literal["venue_inquiry", "partnership_inquiry", "corporate_sponsorship", "nonprofit_collaboration",
                    "research_support", "community_program"]
DRAFT_TYPES: tuple[str, ...] = DraftType.__args__  # type: ignore[attr-defined]


class DraftOut(BaseModel):
    target_id: str
    draft_type: DraftType
    subject: str
    purpose: str
    foundation_background: str
    opportunity: str
    body: str
    next_step: str
    personalization_basis: str
    source_ids: list[str]
    knowledge_used: list[str] | None = None  # Foundation Knowledge Base ids relied on (code keeps only ids it supplied)


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
    mission_impact_considerations: list[str] | None = None  # optional; never overrides financial constraints
    knowledge_used: list[str] | None = None  # Foundation Knowledge Base ids relied on (code keeps only ids it supplied)
