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
    report: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)  # the specialist's structured AgentReport
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
    # Mission Discovery dashboard (Prompt 5). Every field comes from a source or is left empty.
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)  # organization or initiative
    website: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    geography: Mapped[str | None] = mapped_column(String(200), nullable=True)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    activities: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    dates_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    date_status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # confirmed|unconfirmed|conflicting|none
    partnership_types: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    contribution_ways: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    known_costs: Mapped[str | None] = mapped_column(Text, nullable=True)  # only costs stated on a checked source
    missing_info: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    next_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    alignment_detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)  # A charitable, B philosophical, C practical, D evidence
    fit: Mapped[str | None] = mapped_column(String(30), nullable=True)  # Strong fit|Possible fit|Weak fit|Needs research
    fit_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    injection_flags: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # new|saved|dismissed
    board_category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # private board notes; never sent to a model or website
    research_requested: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
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
    source: Mapped[str] = mapped_column(String(40), default="manual")  # manual | upload | demo | document
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    # Provenance and fund status (Prompt 6). Empty restriction means "not documented", never "unrestricted".
    restriction: Mapped[str | None] = mapped_column(String(30), nullable=True)  # unrestricted|temporarily_restricted|permanently_restricted
    purpose: Mapped[str | None] = mapped_column(String(30), nullable=True)  # operations|program|event|fundraising
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    original_amount: Mapped[str | None] = mapped_column(String(60), nullable=True)  # exactly as written in the source
    document_id: Mapped[int | None] = mapped_column(ForeignKey("financial_documents.id", ondelete="SET NULL"), nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verification: Mapped[str | None] = mapped_column(String(30), nullable=True)  # parsed_csv|entered_by_board|board_reviewed|demo
    period_months: Mapped[int | None] = mapped_column(Integer, nullable=True)  # months the figure covers (12 for an annual statement)
    period_label: Mapped[str | None] = mapped_column(String(80), nullable=True)  # e.g. "Year ended Dec 31, 2025"
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    entered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = _created()


class FinancialDocument(Base):
    """An uploaded statement or ledger. The file is stored privately, scoped to the
    organization, under a content-hash name; the original filename is kept only as sanitized text."""

    __tablename__ = "financial_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    filename: Mapped[str] = mapped_column(String(200))  # sanitized display name
    file_type: Mapped[str] = mapped_column(String(10))  # csv | pdf
    doc_type: Mapped[str] = mapped_column(String(40), default="other")
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    stored_name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30))  # imported|needs_review|reviewed|unreadable|rejected
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text_chars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)  # what the parser found (scripts ignored, scanned pages…)
    period_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()


class ExtractedFigure(Base):
    """A figure read from an uploaded document, waiting for a board member's review.
    It never counts in any total until a person approves it into financial_records."""

    __tablename__ = "extracted_figures"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("financial_documents.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(200))  # the line item as written
    kind: Mapped[str] = mapped_column(String(20))
    category: Mapped[str] = mapped_column(String(80))
    restriction: Mapped[str | None] = mapped_column(String(30), nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(30), nullable=True)
    amount_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    original_amount: Mapped[str] = mapped_column(String(60))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    period: Mapped[str | None] = mapped_column(String(7), nullable=True)
    period_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    period_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    found_on_page: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|approved|rejected
    check_notes: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    record_id: Mapped[int | None] = mapped_column(ForeignKey("financial_records.id", ondelete="SET NULL"), nullable=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = _created()


class Donor(Base):
    """Only what acknowledgments need: a name and, optionally, an email. No addresses, phone numbers, or IDs."""

    __tablename__ = "donors"
    __table_args__ = (UniqueConstraint("organization_id", "donor_code", name="uq_donor_code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    donor_code: Mapped[str] = mapped_column(String(20))  # e.g. DNR-0007, the donor identifier shown in tables and exports
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()


class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(20), default="campaign")  # campaign | event
    goal_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    historical_event_id: Mapped[int | None] = mapped_column(ForeignKey("historical_events.id", ondelete="SET NULL"), nullable=True)
    event_plan_id: Mapped[int | None] = mapped_column(ForeignKey("event_plans.id", ondelete="SET NULL"), nullable=True)
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
    # Prompt 6: the full record structure. Tax deductibility is never determined by SAM SPACE.
    donor_id: Mapped[int | None] = mapped_column(ForeignKey("donors.id", ondelete="SET NULL"), nullable=True, index=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    contribution_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # monetary|in_kind|event_ticket|sponsorship|matching_gift
    restriction: Mapped[str | None] = mapped_column(String(30), nullable=True)  # unrestricted|temporarily_restricted|permanently_restricted
    payment_status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # received|pledged|pending|returned
    ack_status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # not_started|prepared|completed|not_needed
    in_kind_description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    goods_services_value_usd: Mapped[float | None] = mapped_column(Float, nullable=True)  # what the donor received (e.g. dinner), if any
    source: Mapped[str | None] = mapped_column(String(20), nullable=True)  # manual | csv_import | demo
    import_document_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


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
    # Partnership drafts (Prompt 5): what the board needs to review a draft before anyone sends it.
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    opportunity: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    foundation_background: Mapped[str | None] = mapped_column(Text, nullable=True)
    sources: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)  # [{title, url, verification}]
    finding_id: Mapped[int | None] = mapped_column(ForeignKey("research_findings.id", ondelete="SET NULL"), nullable=True)
    donation_id: Mapped[int | None] = mapped_column(ForeignKey("donations.id", ondelete="SET NULL"), nullable=True)
    review_notes: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)  # uncertainty carried over from research
    # Board review and traceability (Prompt 10). Statuses: draft (AI draft) | needs_review | reviewed | archived. Never "sent".
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)  # venue | charity | sponsor | research | partner
    contact: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # public contact record with its source and verification
    found_by_agent: Mapped[str | None] = mapped_column(String(40), nullable=True)
    recommendation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)  # why the Orchestrator recommended outreach
    related_findings: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    financial_considerations: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(60), nullable=True)
    handoff_id: Mapped[int | None] = mapped_column(ForeignKey("agent_handoffs.id", ondelete="SET NULL"), nullable=True)
    edited_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
    # Community impact (Prompt 5). Board-recorded counts; empty means "not recorded", never zero.
    volunteers_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    repeat_participants: Mapped[int | None] = mapped_column(Integer, nullable=True)
    partnerships_formed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    funds_directed_usd: Mapped[float | None] = mapped_column(Float, nullable=True)  # to charitable programs
    community_outcomes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Organizational memory (Prompt 8). All optional: unknown stays empty, never zero.
    event_year: Mapped[int | None] = mapped_column(Integer, nullable=True)  # when only the year is known
    planned_budget_usd: Mapped[float | None] = mapped_column(Float, nullable=True)  # for cost-overrun checks
    positive_outcomes: Mapped[str | None] = mapped_column(Text, nullable=True)
    problems_encountered: Mapped[str | None] = mapped_column(Text, nullable=True)
    lessons_learned: Mapped[str | None] = mapped_column(Text, nullable=True)  # the board's own words (AI lessons are separate)
    # board_reported | document_extracted (AI-extracted, board-approved, not verified accounting) | verified (treasurer)
    verification_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    field_sources: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # field -> {origin, import_id, source_id, quote}
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()

    reflections: Mapped[list[BoardReflection]] = relationship(back_populates="event", cascade="all, delete-orphan")
    photos: Mapped[list[EventPhoto]] = relationship(back_populates="event", cascade="all, delete-orphan")
    documents: Mapped[list[LegacyDocument]] = relationship(back_populates="event")


class LegacyImport(Base):
    """A draft import: a board member's description or uploaded files, the AI's candidate extraction, and the board's
    decision. Nothing reaches historical_events until a board member approves the preview."""

    __tablename__ = "legacy_imports"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    method: Mapped[str] = mapped_column(String(20))  # upload | conversation
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # the description, exactly as written
    target_event_id: Mapped[int | None] = mapped_column(ForeignKey("historical_events.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|extracting|ready|failed|approved|discarded
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    extraction: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # validated candidate (see services/legacy_import.py)
    approved_event_id: Mapped[int | None] = mapped_column(ForeignKey("historical_events.id", ondelete="SET NULL"), nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # what the board changed, chose, and confirmed
    created_at: Mapped[datetime] = _created()

    documents: Mapped[list[LegacyDocument]] = relationship(back_populates="legacy_import")


class LegacyDocument(Base):
    """An original source file (PDF, CSV, XLSX, text notes, or a photo), kept for authorized review."""

    __tablename__ = "legacy_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    import_id: Mapped[int | None] = mapped_column(ForeignKey("legacy_imports.id", ondelete="SET NULL"), nullable=True, index=True)
    historical_event_id: Mapped[int | None] = mapped_column(ForeignKey("historical_events.id", ondelete="SET NULL"), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(160))  # sanitized display name
    file_type: Mapped[str] = mapped_column(String(10))  # pdf | csv | xlsx | text | image
    content_type: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    stored_name: Mapped[str] = mapped_column(String(120))  # hash-named, inside the workspace folder
    status: Mapped[str] = mapped_column(String(20), default="stored")  # readable | unreadable | photo
    text: Mapped[str | None] = mapped_column(Text, nullable=True)  # extracted text (untrusted; screened whenever used)
    parse_notes: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = _created()

    legacy_import: Mapped[LegacyImport | None] = relationship(back_populates="documents")
    event: Mapped[HistoricalEvent | None] = relationship(back_populates="documents")


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
    # Community questions (Prompt 5). Board observations, not verified outcomes.
    welcome_inclusion: Mapped[str | None] = mapped_column(Text, nullable=True)  # Did attendees seem welcomed and included?
    connection_moments: Mapped[str | None] = mapped_column(Text, nullable=True)  # Which activities created connection?
    volunteer_appreciation: Mapped[str | None] = mapped_column(Text, nullable=True)  # Did volunteers feel appreciated?
    accessibility_issues: Mapped[str | None] = mapped_column(Text, nullable=True)  # Accessibility or inclusion problems?
    inclusion_improvements: Mapped[str | None] = mapped_column(Text, nullable=True)  # What could have made people feel more welcomed?
    # Authorized attribution: a board member may record another member's reflection (e.g. given by phone). Both are kept.
    recorded_by_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
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


# --- Impact & Evaluation (real-user pilot) ----------------------------------------


class ImpactEvaluation(Base):
    """One participant's evaluation of the fixed planning task: a manual baseline, a SAM SPACE-assisted attempt linked to
    a real agent run, rubric scores, and feedback. Practice and test records are flagged is_synthetic and never counted."""

    __tablename__ = "impact_evaluations"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    participant_code: Mapped[str] = mapped_column(String(20))  # "P1": what reports show unless naming is permitted
    participant_role: Mapped[str] = mapped_column(String(60), default="")
    show_name_in_reports: Mapped[bool] = mapped_column(Boolean, default=False)
    attribution_permission: Mapped[bool] = mapped_column(Boolean, default=False)  # may identifiable comments be quoted publicly?
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)  # practice runs and automated fixtures
    scenario_key: Mapped[str] = mapped_column(String(40), default="gala_150_manhattan")
    task_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | submitted
    # Manual baseline (the participant's usual way of working).
    manual_status: Mapped[str] = mapped_column(String(20), default="not_started")  # not_started|in_progress|completed|unavailable
    manual_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    manual_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    manual_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    manual_tools: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    manual_venues: Mapped[int | None] = mapped_column(Integer, nullable=True)
    manual_verified_sources: Mapped[int | None] = mapped_column(Integer, nullable=True)
    manual_financial_model: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    manual_history_used: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    manual_outreach_draft: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    manual_difficulties: Mapped[str | None] = mapped_column(Text, nullable=True)
    manual_comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    # SAM SPACE-assisted attempt. Human time (start to finish, including review) is separate from model execution time.
    assisted_status: Mapped[str] = mapped_column(String(20), default="not_started")
    assisted_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assisted_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assisted_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)  # part spent reviewing and correcting AI output
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    run_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # read from the run's logs when linked
    calculations_correct: Mapped[str | None] = mapped_column(String(10), nullable=True)  # yes | no | unsure
    outreach_usefulness: Mapped[str | None] = mapped_column(String(20), nullable=True)  # usable | needs_editing | not_usable
    errors_encountered: Mapped[str | None] = mapped_column(Text, nullable=True)
    unsupported_claims_found: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unsupported_claims_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    assisted_observations: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    feedback_saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mission: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EvaluationScore(Base):
    """A human evaluator's rubric score for one proposal (manual, SAM SPACE-assisted, or a history-comparison run)."""

    __tablename__ = "evaluation_scores"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    evaluation_id: Mapped[int | None] = mapped_column(ForeignKey("impact_evaluations.id", ondelete="CASCADE"), nullable=True, index=True)
    experiment_id: Mapped[int | None] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), nullable=True, index=True)
    condition: Mapped[str] = mapped_column(String(20))  # manual | assisted | without_history | with_history
    dimension: Mapped[str] = mapped_column(String(40))
    score: Mapped[int] = mapped_column(Integer)  # 0-4
    scorer_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    scorer_kind: Mapped[str] = mapped_column(String(10), default="human")  # human (no AI scoring is used)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created()


class ImpactAssumption(Base):
    """Administrator-entered assumptions for projections (e.g. similar tasks per year). Always labeled as assumptions."""

    __tablename__ = "impact_assumptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    key: Mapped[str] = mapped_column(String(60))
    value: Mapped[float] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = _created()


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
    mode: Mapped[str | None] = mapped_column(String(20), nullable=True)  # mocked | live
    defense: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_id: Mapped[str | None] = mapped_column(String(200), nullable=True)


class SecurityEvent(Base):
    """A safety control acting: a blocked tool, a denied record, an injection screened out, a budget or loop
    stop, a restricted model, a rejected upload or URL, a rejected output. Details are redacted before saving."""

    __tablename__ = "security_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str] = mapped_column(String(10), default="medium")  # info | low | medium | high
    agent: Mapped[str | None] = mapped_column(String(40), nullable=True)
    defense: Mapped[str] = mapped_column(String(80), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _created()


class SafetySetting(Base):
    """A board-configured safety limit. Always clamped to the hard caps in safety/limits.py."""

    __tablename__ = "safety_settings"
    __table_args__ = (UniqueConstraint("organization_id", "key", name="uq_safety_setting"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    key: Mapped[str] = mapped_column(String(40))
    value: Mapped[float] = mapped_column(Float)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = _created()


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    target: Mapped[str] = mapped_column(String(200), default="")
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = _created()


class KnowledgeEntry(Base):
    """One fact in the Foundation Knowledge Base: who the foundation is, its signature events, vendors, relationships,
    community, board, priorities, finance guidelines, and communication preferences. Every fact keeps its source,
    contributor, dates, and verification status. Real entries live only in the local database; the repository ships
    a blank template and a few labeled samples (services/knowledge.py)."""

    __tablename__ = "knowledge_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    section: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")  # short narrative
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)  # the section's structured fields
    aliases: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)  # other names, used to recognize an organization or vendor
    historical_event_id: Mapped[int | None] = mapped_column(ForeignKey("historical_events.id", ondelete="SET NULL"), nullable=True)
    source: Mapped[str] = mapped_column(String(300), default="")
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    contributor: Mapped[str] = mapped_column(String(120), default="")
    verification: Mapped[str] = mapped_column(String(30), default="needs_confirmation")  # verified|board_reported|estimate|needs_confirmation|demo
    verified_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    share_externally: Mapped[bool] = mapped_column(Boolean, default=False)  # may appear in an outreach draft
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | removed
    removed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    recorded_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _created()
    updated_by: Mapped[str] = mapped_column(String(120), default="")
