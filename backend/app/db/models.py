"""SQLite schema for SAM SPACE (SQLAlchemy 2.0 ORM).

Every row that comes from the synthetic demo dataset has is_demo=True, and the
UI labels it. Tables that hold AI output (runs, findings, drafts, lessons) start
empty and are filled only by real agent runs.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# --- Workspace + people -------------------------------------------------------


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    mission: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    animations_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    model_strategy: Mapped[str] = mapped_column(String(20), default="auto")
    created_at: Mapped[datetime] = _created()
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    memberships: Mapped[list[BoardMembership]] = relationship(back_populates="user")


class BoardMembership(Base):
    """A user's board role inside one organization (role drives permissions)."""

    __tablename__ = "board_memberships"
    __table_args__ = (UniqueConstraint("user_id", "organization_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20))  # chair | treasurer | member
    title: Mapped[str] = mapped_column(String(80), default="Board Member")
    created_at: Mapped[datetime] = _created()

    user: Mapped[User] = relationship(back_populates="memberships")
    organization: Mapped[Organization] = relationship()


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- Agent runs, handoffs, tool calls, model usage ------------------------------


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    workflow_type: Mapped[str] = mapped_column(String(60))
    request_text: Mapped[str] = mapped_column(Text, default="")
    research_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)  # live | synthetic
    event_plan_id: Mapped[int | None] = mapped_column(ForeignKey("event_plans.id", ondelete="SET NULL"), nullable=True)
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|completed|failed|stopped
    strategy: Mapped[str] = mapped_column(String(20), default="auto")
    provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    budget_usd: Mapped[float] = mapped_column(Float, default=0.0)
    spent_usd: Mapped[float] = mapped_column(Float, default=0.0)
    model_calls: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = _created()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentHandoff(Base):
    __tablename__ = "agent_handoffs"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    step_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    kind: Mapped[str | None] = mapped_column(String(20), nullable=True)  # task | revision | verification
    revision_round: Mapped[int | None] = mapped_column(Integer, nullable=True)
    from_agent: Mapped[str] = mapped_column(String(40))
    to_agent: Mapped[str] = mapped_column(String(40))
    objective: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="requested")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = _created()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentToolCall(Base):
    __tablename__ = "agent_tool_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True, index=True)
    handoff_id: Mapped[int | None] = mapped_column(ForeignKey("agent_handoffs.id", ondelete="CASCADE"), nullable=True)
    agent: Mapped[str] = mapped_column(String(40))
    tool_name: Mapped[str] = mapped_column(String(80))
    ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    arguments: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result_summary: Mapped[str] = mapped_column(Text, default="")
    allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    denial_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created()


class ModelUsage(Base):
    """One row per model call: which model, why, tokens, cost, time."""

    __tablename__ = "model_usage"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True, index=True)
    handoff_id: Mapped[int | None] = mapped_column(ForeignKey("agent_handoffs.id", ondelete="CASCADE"), nullable=True)
    agent: Mapped[str] = mapped_column(String(40))
    task: Mapped[str] = mapped_column(String(120), default="")
    web_search_calls: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    strategy: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(20))
    requested_tier: Mapped[str] = mapped_column(String(20))
    selected_model: Mapped[str] = mapped_column(String(60))
    model_used: Mapped[str | None] = mapped_column(String(80), nullable=True)  # as reported by the API
    selection_reason: Mapped[str] = mapped_column(Text)
    substitution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_write_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ok")  # ok | error | refused
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created()


# --- Research, events, venues -------------------------------------------------


class SourceRecordRow(Base):
    """Every source an agent relied on: a fetched web page, a synthetic fixture, or an internal record."""

    __tablename__ = "source_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True, index=True)
    handoff_id: Mapped[int | None] = mapped_column(ForeignKey("agent_handoffs.id", ondelete="CASCADE"), nullable=True)
    source_key: Mapped[str] = mapped_column(String(60))
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    title: Mapped[str] = mapped_column(String(400), default="")
    publisher: Mapped[str | None] = mapped_column(String(200), nullable=True)
    published: Mapped[str | None] = mapped_column(String(60), nullable=True)
    retrieved_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    verification: Mapped[str] = mapped_column(String(20))  # verified | unverified | synthetic | internal
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created()


class ResearchFinding(Base):
    __tablename__ = "research_findings"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    agent: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(40))  # organization|event|research|partnership|venue
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(20), default="unverified")  # verified|unverified|synthetic
    alignment: Mapped[str | None] = mapped_column(String(20), nullable=True)  # high|medium|low|none
    uncertainty: Mapped[str | None] = mapped_column(Text, nullable=True)
    published: Mapped[str | None] = mapped_column(String(60), nullable=True)
    is_synthetic: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    saved: Mapped[bool] = mapped_column(Boolean, default=False)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()


class EventPlan(Base):
    __tablename__ = "event_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    event_type: Mapped[str] = mapped_column(String(60), default="fundraiser")
    city: Mapped[str] = mapped_column(String(120), default="")
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_attendance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fundraising_goal_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    budget_limit_usd: Mapped[float | None] = mapped_column(Float, nullable=True)  # maximum planning budget
    date_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    ticket_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    event_format: Mapped[str | None] = mapped_column(String(20), nullable=True)  # seated_dinner | reception
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    assumptions: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)  # board-edited model assumptions
    status: Mapped[str] = mapped_column(String(30), default="idea")  # idea|planning|board_review|completed|cancelled
    notes: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class VenueCandidate(Base):
    __tablename__ = "venue_candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_plan_id: Mapped[int] = mapped_column(ForeignKey("event_plans.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(String(300), default="")
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_is_estimate: Mapped[bool] = mapped_column(Boolean, default=True)
    fnb_per_guest_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    deposit_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    formats: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    verification: Mapped[str | None] = mapped_column(String(20), nullable=True)  # verified|unverified|synthetic
    is_synthetic: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    website: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    pricing_status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # published | quote_required
    amenities: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    restrictions: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    verified_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _created()


# --- Money --------------------------------------------------------------------


class FinancialRecord(Base):
    __tablename__ = "financial_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    period: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    kind: Mapped[str] = mapped_column(String(20))  # income | expense | reserve
    category: Mapped[str] = mapped_column(String(80))
    amount_usd: Mapped[float] = mapped_column(Float)
    description: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(40), default="manual")  # manual | upload | demo
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()


class Donation(Base):
    __tablename__ = "donations"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    donor_name: Mapped[str] = mapped_column(String(200))
    donor_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    amount_usd: Mapped[float] = mapped_column(Float)
    received_on: Mapped[date] = mapped_column(Date)
    method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    designation: Mapped[str] = mapped_column(String(120), default="General fund")
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()


class OutreachDraft(Base):
    """An unsent draft. There is deliberately no 'sent' status: sending happens
    outside SAM SPACE, by a person."""

    __tablename__ = "outreach_drafts"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    agent: Mapped[str | None] = mapped_column(String(40), nullable=True)
    draft_type: Mapped[str] = mapped_column(String(40))  # partnership|venue_inquiry|donor_acknowledgment|sponsor
    recipient_name: Mapped[str] = mapped_column(String(200), default="")
    recipient_org: Mapped[str] = mapped_column(String(200), default="")
    subject: Mapped[str] = mapped_column(String(300), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    personalization_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_synthetic_target: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | reviewed | archived
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# --- Legacy: past events, photos, reflections, lessons ----------------------


class HistoricalEvent(Base):
    __tablename__ = "historical_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    location: Mapped[str] = mapped_column(String(200), default="")
    event_type: Mapped[str] = mapped_column(String(60), default="fundraiser")
    attendance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    funds_raised_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)  # expenses
    summary: Mapped[str] = mapped_column(Text, default="")
    venue: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fundraising_goal_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    sponsorship_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    sponsorship_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()

    reflections: Mapped[list[BoardReflection]] = relationship(back_populates="event", cascade="all, delete-orphan")
    photos: Mapped[list[EventPhoto]] = relationship(back_populates="event", cascade="all, delete-orphan")


class EventPhoto(Base):
    __tablename__ = "event_photos"
    id: Mapped[int] = mapped_column(primary_key=True)
    historical_event_id: Mapped[int] = mapped_column(ForeignKey("historical_events.id", ondelete="CASCADE"), index=True)
    file_path: Mapped[str] = mapped_column(String(500))
    caption: Mapped[str] = mapped_column(String(300), default="")
    content_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_demo: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = _created()

    event: Mapped[HistoricalEvent] = relationship(back_populates="photos")


class BoardReflection(Base):
    __tablename__ = "board_reflections"
    id: Mapped[int] = mapped_column(primary_key=True)
    historical_event_id: Mapped[int] = mapped_column(ForeignKey("historical_events.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    author_label: Mapped[str] = mapped_column(String(120), default="")
    # The seven post-event questions. Stored exactly as written and never edited by AI.
    went_well: Mapped[str] = mapped_column(Text, default="")  # 1. What worked particularly well?
    challenges: Mapped[str] = mapped_column(Text, default="")  # 2. What did not go as planned?
    unexpected_costs: Mapped[str | None] = mapped_column(Text, nullable=True)  # 3. Unexpected expenses or complications?
    attendee_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)  # 4. What feedback did attendees provide?
    should_repeat: Mapped[str | None] = mapped_column(Text, nullable=True)  # 5. What should we repeat?
    do_differently: Mapped[str] = mapped_column(Text, default="")  # 6. What should we change?
    advice: Mapped[str | None] = mapped_column(Text, nullable=True)  # 7. Advice for the next planning board
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()

    event: Mapped[HistoricalEvent] = relationship(back_populates="reflections")


class HistoricalLesson(Base):
    """A lesson generated by the Event Intelligence agent from real records."""

    __tablename__ = "historical_lessons"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    lesson: Mapped[str] = mapped_column(Text)
    kind: Mapped[str | None] = mapped_column(String(30), nullable=True)  # what_worked|recurring_problem|recommendation
    theme: Mapped[str | None] = mapped_column(String(80), nullable=True)
    scope: Mapped[str | None] = mapped_column(String(160), nullable=True)  # "event:3" or "planning:..." (newer analyses supersede)
    focus_event_id: Mapped[int | None] = mapped_column(ForeignKey("historical_events.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # new|reviewed|adopted|dismissed|superseded
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    based_on_demo_data: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    evidence: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[str] = mapped_column(String(10), default="medium")
    applies_to: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = _created()


class Experiment(Base):
    """A controlled comparison, e.g. the same plan run without and with historical lessons."""

    __tablename__ = "experiments"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40))  # history_ab
    request_text: Mapped[str] = mapped_column(Text)
    research_mode: Mapped[str] = mapped_column(String(20), default="synthetic")
    run_a_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    run_b_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- Safety + audit -----------------------------------------------------------


class SafetyTestResult(Base):
    __tablename__ = "safety_tests"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(60))  # prompt_injection|data_leak|loop|budget|hallucination|permissions
    input_excerpt: Mapped[str] = mapped_column(Text, default="")
    expected: Mapped[str] = mapped_column(Text, default="")
    observed: Mapped[str] = mapped_column(Text, default="")
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    ran_at: Mapped[datetime] = _created()


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    target: Mapped[str] = mapped_column(String(200), default="")
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = _created()
