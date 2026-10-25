export type Strategy = "auto" | "economy" | "balanced" | "advanced";

export type User = {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  is_demo: boolean;
  role: "chair" | "treasurer" | "member";
  title: string;
  permissions: string[];
  organization: { id: number; name: string; is_demo: boolean } | null;
  settings: { animations_enabled: boolean; model_strategy: Strategy };
};

export type EventPlan = {
  id: number;
  name: string;
  event_type: string;
  city: string;
  target_date: string | null;
  expected_attendance: number | null;
  fundraising_goal_usd: number | null;
  budget_limit_usd: number | null;
  status: string;
  notes: string;
  is_demo: boolean;
  created_at: string;
  date_end: string | null;
  ticket_price_usd: number | null;
  event_format: string | null;
  instructions: string | null;
  assumptions: Record<string, number> | null;
};

export type Flag = { severity: "high" | "medium" | "low"; title: string; detail: string };

export type HistoryStats = {
  events_recorded: number;
  total_raised_usd: number;
  total_net_usd: number;
  highest_net_event: { name: string; net_usd: number } | null;
  most_efficient_event: { name: string; raised_per_dollar: number } | null;
  is_demo: boolean;
};

export type Overview = {
  first_name: string;
  recent_activity: { id: number; workflow_type: string; status: string; started_at: string; spent_usd: number }[];
  saved_opportunities: { id: number; title: string; category: string; source_url: string | null; verification_status: string }[];
  planned_events: EventPlan[];
  drafts_awaiting_review: { id: number; subject: string; recipient_org: string; draft_type: string }[];
  financial: { restricted: boolean; flags: Flag[]; is_demo?: boolean };
  history: HistoryStats;
  lessons: { id: number; lesson: string; confidence: string }[];
};

export type Reflection = {
  id: number;
  author: string;
  went_well: string;
  challenges: string;
  do_differently: string;
  rating: number | null;
  is_demo: boolean;
  created_at: string;
};

export type HistoricalEvent = {
  id: number;
  name: string;
  event_date: string | null;
  location: string;
  event_type: string;
  attendance: number | null;
  funds_raised_usd: number | null;
  total_cost_usd: number | null;
  net_usd: number | null;
  summary: string;
  is_demo: boolean;
  reflections: Reflection[];
};

export type FinanceSummary = {
  is_demo: boolean;
  months: { period: string; income: number; expense: number; net: number }[];
  average_monthly_expense: number | null;
  reserve_usd: number | null;
  reserve_period: string | null;
  reserve_months_covered: number | null;
  flags: Flag[];
  method: string;
};

export type Donations = {
  donations: {
    id: number;
    donor_name: string;
    has_email: boolean;
    amount_usd: number;
    received_on: string;
    method: string | null;
    designation: string;
    acknowledged: boolean;
    is_demo: boolean;
    flags: string[];
  }[];
  totals: { count: number; amount_usd: number; needs_attention: number; unacknowledged: number };
  is_demo: boolean;
  note: string;
};

export type AgentInfo = { name: string; display_name: string; purpose: string; allowed_tools: string[]; status: string };

export type RoutingRow = {
  agent: string;
  task: string;
  strategy?: string;
  provider?: string;
  score?: number;
  requested_tier?: string;
  requested_model?: string;
  tier?: string;
  model?: string;
  reason?: string;
  substituted?: boolean;
  substitution_note?: string | null;
  estimated_cost_usd?: number | null;
  error?: string;
};

export type TierInfo = {
  preferred: string;
  fallback?: string | null;
  effective: string | null;
  preferred_available: boolean | null;
  note: string | null;
};

export type ModelsOverview = {
  provider: string | null;
  strategy: Strategy;
  strategies: { value: Strategy; label: string; description: string }[];
  tier_names: Record<string, string>;
  tiers: Record<string, TierInfo>;
  availability_status: string;
  pricing: { source: string; retrieved_on: string; unit: string; models: Record<string, Record<string, number>> };
  portkey_policy: { active: boolean; allowed_model: string; rule: string };
  routing_preview: RoutingRow[];
  routing_rule: string;
};

export type SystemStatus = {
  provider: string | null;
  provider_setting: string;
  keys_detected: Record<string, boolean>;
  env_files_loaded: string[];
  portkey_policy: { active: boolean; allowed_model: string; rule: string };
  model_availability: { provider: string | null; status: string; checked_at: string | null; error: string | null };
  demo_mode: boolean;
  version: string;
};

export type SafetyPolicy = {
  prohibited_actions: { name: string; label: string }[];
  allowed_capabilities: string[];
  limits: Record<string, number | string>;
  portkey_policy: { active: boolean; allowed_model: string; rule: string };
  safety_tests: { name: string; category: string; passed: boolean; observed: string; ran_at: string }[];
  safety_tests_recorded: number;
};

export type Activity = {
  runs: { id: number; workflow_type: string; status: string; strategy: string; provider: string | null; spent_usd: number; model_calls: number; started_at: string; finished_at: string | null }[];
  model_calls: {
    id: number;
    run_id: number | null;
    agent: string;
    task: string;
    strategy: string;
    provider: string;
    requested_tier: string;
    selected_model: string;
    model_used: string | null;
    selection_reason: string;
    substitution_note: string | null;
    input_tokens: number | null;
    cached_input_tokens: number | null;
    output_tokens: number | null;
    estimated_cost_usd: number | null;
    latency_ms: number | null;
    status: string;
    created_at: string;
  }[];
  handoffs: { id: number; run_id: number; from_agent: string; to_agent: string; objective: string; status: string }[];
  tool_calls: { id: number; run_id: number; agent: string; tool_name: string; allowed: boolean; denial_reason: string | null; created_at: string }[];
  totals: { model_calls: number; input_tokens: number; cached_input_tokens: number; output_tokens: number; estimated_cost_usd: number };
};

export type UserSettings = {
  animations_enabled: boolean;
  model_strategy: Strategy;
  strategies: { value: Strategy; label: string; description: string }[];
  provider: string | null;
  strategy_note: string | null;
};

// ── Agent workflows ─────────────────────────────────────────────────────────────

export type Intent = "plan_event" | "mission_discovery" | "partnership_outreach" | "financial_review" | "donations_review" | "event_learning";
export type ResearchMode = "synthetic" | "live" | "fixture";  // "fixture": server-side safety tests only

export type RunSummary = {
  id: number;
  request: string;
  workflow_type: string;
  intent: string | null;
  status: "queued" | "running" | "completed" | "completed_with_warnings" | "failed" | "stopped";
  strategy: string;
  provider: string | null;
  research_mode: ResearchMode | null;
  budget_usd: number;
  spent_usd: number;
  model_calls: number;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  error: string | null;
  event_plan_id: number | null;
};

export type SourceRecord = {
  id: string;
  title: string;
  url: string | null;
  publisher: string | null;
  published: string | null;
  retrieved_at: string | null;
  verification: "verified" | "unverified" | "synthetic" | "internal";
  http_status: number | null;
  note: string | null;
};

export type AgentResultData = {
  status: string;
  summary: string;
  findings: { claim: string; kind: string; source_ids: string[]; confidence: string | null }[];
  sources: SourceRecord[];
  assumptions: string[];
  warnings: string[];
  next_steps: string[];
  data: Record<string, unknown>;
  usage: { model_calls: number; input_tokens: number; cached_input_tokens: number; output_tokens: number; web_search_calls: number; cost_usd: number; models: string[] };
  duration_ms: number;
};

export type RunStep = {
  id: number;
  step_key: string;
  kind: "task" | "revision" | null;
  revision_round: number | null;
  from_agent: string;
  to_agent: string;
  objective: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  error: string | null;
  redacted: boolean;
  constraints: { name: string; detail: string; value: number | string | null; source_agent: string | null }[];
  result: AgentResultData | null;
  tool_calls: { id: number; tool: string; allowed: boolean; ok: boolean | null; duration_ms: number | null; summary: string | null; denial: string | null; error: string | null }[];
  model_calls: {
    id: number; task: string; tier: string; model: string; model_used: string | null; reason: string; substitution: string | null;
    input_tokens: number | null; cached_input_tokens: number | null; output_tokens: number | null; web_search_calls: number | null;
    cost_usd: number | null; latency_ms: number | null; attempt: number | null; status: string; error: string | null;
  }[];
};

export type BoardRecommendation = {
  mission_impact_considerations?: string[] | null;
  headline: string;
  recommendation: string;
  rationale: string[];
  options: { title: string; option_id: string | null; summary: string }[];
  risks: string[];
  decisions_for_board: string[];
  next_steps: string[];
  lessons_applied: string[];
  caveats: string[];
};

export type Check = { name: string; passed: boolean | null; detail: string };

export type RunResult = {
  intent: string;
  routing: string;
  research_mode: ResearchMode;
  message?: string;
  recommendation: BoardRecommendation | null;
  verification: { passed: boolean; checks: Check[]; unsupported_figures: number[] } | null;
  revision_history: { round: number; venue: string; event_format: string; total_usd: number; upfront_cash_usd: number; verdict: string | null; finance_status: string; conflicts: string[] }[];
  unresolved_conflicts: { type: string; detail: string }[];
  finance?: {
    verdict: string; affordability: { checks: Check[] }; venue: string; event_format: string;
    // Runs before Event Studio stored "budget"; Event Studio runs store the deterministic event "model".
    budget?: { total_usd: number; upfront_cash_usd: number; line_items: { name: string; amount_usd: number; basis: string }[]; contingency_pct: number; contingency_usd: number; assumptions: string[] };
    model?: { lines: { category: string; amount_usd: number; basis: string }[]; contingency_pct: number; contingency_usd: number; total_cost_usd: number; upfront_cash_usd: number };
  } | null;
  // A stopped workflow keeps only what it finished (never a recommendation).
  stopped?: boolean; stop_reason?: string; verified_partial_steps?: number; missing?: string[];
  completed_steps?: { step_key: string; agent: string; status: string; summary: string; warnings: string[] }[];
  shortlist: { option_id: string; venue: string; event_format: string; total_usd: number; upfront_cash_usd: number; rationale: string; verification: string; source_url: string | null }[];
  drafts?: { id: number; recipient: string; subject: string; draft_type: string; synthetic_target: boolean }[];
  lessons: { kind: string; text: string; event_ids: number[]; reflection_ids: number[]; confidence: string }[];
  disagreements: { topic: string; positions: string[]; evidence_reflection_ids: number[] }[];
  findings?: { id: number; title: string; url: string | null; category: string; alignment: string; verification: string; summary: string; date: string | null; uncertainty: string }[];
  donations: { aggregate: Record<string, unknown>; drafts_created: number; review_items: { issue: string; why_professional_review: string }[] } | null;
  event_plan_id: number | null;
};

export type RunDetail = {
  run: RunSummary;
  steps: RunStep[];
  result: RunResult | null;
  totals: { model_calls: number; input_tokens: number; cached_input_tokens: number; output_tokens: number; web_search_calls: number; cost_usd: number; tool_calls: number; denied_tool_calls: number; handoffs: number; revisions: number };
};

export type DraftSource = { title: string | null; url: string | null; verification: string | null; retrieved_at?: string | null };

export type Draft = {
  id: number; run_id: number | null; agent: string | null; draft_type: string; recipient_name: string; recipient_org: string;
  subject: string; body: string; status: "draft" | "reviewed" | "archived"; personalization_basis: string | null;
  is_synthetic_target: boolean | null; created_at: string; updated_at?: string | null;
  purpose?: string | null; opportunity?: string | null; next_step?: string | null; foundation_background?: string | null;
  sources?: DraftSource[]; finding_id?: number | null; review_notes?: string[];
};

export type AlignmentLevel = { level: "strong" | "partial" | "unclear" | "none"; explanation: string };
export type AlignmentDetail = {
  charitable: Record<string, AlignmentLevel>;
  philosophical: Record<string, AlignmentLevel>;
  practical: { geography: string; cost: string; volunteers: string; timing: string; operations: string; blockers: string[] };
  evidence: { reliability: string; verified_items: string[]; unconfirmed_claims: string[]; missing_info: string[] };
  summary: string;
};

export type Opportunity = {
  id: number; run_id: number | null; name: string; title: string; category: string; geography: string | null; purpose: string | null;
  summary: string; activities: string[]; website: string | null; source_url: string | null; source_title: string | null;
  verification: string; dates_text: string | null; date_status: string | null; partnership_types: string[]; contribution_ways: string[];
  known_costs: string | null; missing_info: string[]; next_step: string | null; alignment: string | null;
  alignment_detail: AlignmentDetail | null; fit: string | null; fit_reason: string | null; warnings: string[]; injection_flagged: boolean;
  uncertainty: string | null; is_synthetic: boolean; status: "new" | "saved" | "dismissed"; saved: boolean; board_category: string | null;
  research_requested: boolean; last_checked: string | null; created_at: string | null; notes?: string | null;
  selection_reason?: string; reason?: string;
};

export type OpportunityStats = {
  total: number; by_status: Record<string, number>; by_fit: Record<string, number>; by_verification: Record<string, number>;
  with_warnings: number; injection_flagged: number; synthetic: number; last_checked: string | null;
};

export type MissionConfig = {
  philosophy: string; foundation: { name: string; short_name: string; established: string; purpose_areas: string[] };
  criteria: { key: string; label: string; question: string }[]; evidence_rules: string[];
  fit_rubric: { label: string; rule: string }[]; event_considerations: string[]; reflection_lenses: string[]; board_categories: string[];
};

export type ImpactMetric = {
  key: string; label: string; value: number | null; display: string; type: string; basis: string; coverage: string;
  examples: { text: string; source: string }[];
};
export type Impact = { metrics: ImpactMetric[]; events_recorded: number; is_demo: boolean; labels: Record<string, string> };

export type TraceStep = {
  n: number; step_key: string; from_agent: string; to_agent: string; kind: string; status: string; objective: string;
  duration_ms: number | null; summary: string | null; models: string[]; input_tokens: number; output_tokens: number; cost_usd: number;
  constraints?: { name: string; detail: string; source_agent: string }[];
};

export type PartnershipDraft = {
  id: number; recipient: string; draft_type: string; subject: string; purpose: string | null; foundation_background: string | null;
  opportunity: string | null; body: string; next_step: string | null; sources: DraftSource[]; review_notes: string[];
  status: "draft" | "reviewed" | "archived"; finding_id: number | null; is_synthetic_target: boolean | null;
};

export type PartnershipPacket = {
  run: { id: number; status: string; research_mode: string; strategy: string; started_at: string; duration_ms: number | null; error: string | null };
  request: string; philosophy: string;
  recommendation: { headline: string; recommendation: string; rationale: string[]; options: { title: string; summary: string }[]; risks: string[];
    decisions_for_board: string[]; next_steps: string[]; lessons_applied: string[]; caveats: string[] } | null;
  selected: Opportunity[]; excluded: (Partial<Opportunity> & { id: number; name: string; reason: string })[];
  selection_warnings: string[]; count_requested: number | null; unresolved: { detail: string }[];
  drafts: PartnershipDraft[];
  sources: { title: string; url: string | null; verification: string; http_status: number | null; retrieved_at: string | null; note: string | null }[];
  trace: TraceStep[];
  usage: { model_calls: number; input_tokens: number; cached_input_tokens: number; output_tokens: number; web_search_calls: number; cost_usd: number;
    by_model: Record<string, { calls: number; input_tokens: number; cached_input_tokens: number; output_tokens: number; cost_usd: number }> };
  verification: { passed: boolean; checks: { name: string; passed: boolean | null; detail: string }[] } | null;
};

export type ResearchFindingRow = {
  id: number; run_id: number | null; title: string; summary: string; category: string; alignment: string | null; source_url: string | null;
  verification: string; uncertainty: string | null; published: string | null; is_synthetic: boolean | null; saved: boolean; created_at: string;
};

export type LessonRow = {
  id: number; run_id: number | null; lesson: string; kind: string | null; confidence: string; applies_to: string;
  based_on_demo_data: boolean | null; evidence: { type: string; id: number; label: string }[]; created_at: string;
};

export type VenueCandidateRow = {
  id: number; name: string; neighborhood: string; capacity: number | null; estimated_total_usd: number | null; fnb_per_guest_usd: number | null;
  formats: string[] | null; verification: string | null; is_synthetic: boolean | null; source_url: string | null; notes: string; run_id: number | null;
};

// ── Our Legacy ──────────────────────────────────────────────────────────────────

export type LegacyPhoto = { id: number; caption: string; url: string; is_demo: boolean; created_at: string };

export type LegacyEvent = {
  id: number; name: string; event_date: string | null; location: string; event_type: string; venue: string | null;
  attendance: number | null; fundraising_goal_usd: number | null; funds_raised_usd: number | null; total_cost_usd: number | null;
  net_usd: number | null; goal_pct: number | null; sponsorship_usd: number | null; sponsorship_info: string | null;
  summary: string; notes: string | null; is_demo: boolean; reflection_count: number; photos: LegacyPhoto[];
  updated_at: string | null; lesson_count?: number; top_lesson?: string | null;
  volunteers_count?: number | null; repeat_participants?: number | null; partnerships_formed?: number | null;
  funds_directed_usd?: number | null; community_outcomes?: string | null;
  event_year?: number | null; planned_budget_usd?: number | null; positive_outcomes?: string | null; problems_encountered?: string | null;
  lessons_learned?: string | null; verification_status?: "board_reported" | "document_extracted" | "verified"; verification_label?: string;
  verified_at?: string | null; field_sources?: Record<string, FieldSource>; documents?: LegacyDocument[];
};

export type FieldSource = { origin: "source_fact" | "ai_interpretation" | "board_choice" | "board_edited" | "board_entered"; sources?: string[];
  source_ids?: string[]; quotes?: string[]; note?: string; import_id?: number };
export type LegacyDocument = { id: number; filename: string; file_type: "pdf" | "csv" | "xlsx" | "text" | "image"; size_bytes: number;
  status: "readable" | "unreadable" | "photo"; notes: string[]; import_id: number | null; event_id: number | null; url: string;
  created_at: string; can_open?: boolean };
export type SourcedField = { value: string | number; origin: "source_fact" | "ai_interpretation"; source_id: string; source_label: string;
  quote: string; also_in?: string[]; note?: string | null };
export type SourcedItem = { text: string; origin: "source_fact" | "ai_interpretation"; source_id: string; source_label: string; quote: string };
export type ImportConflict = { field: string; label: string; detail: string;
  values: { value: number; source_id: string; source_label: string; quote: string }[] };
export type ImportExtraction = {
  summary: string; fields: Record<string, SourcedField>; lists: Record<"positive_outcomes" | "problems_encountered" | "lessons_learned", SourcedItem[]>;
  conflicts: ImportConflict[]; warnings: string[]; missing: string[]; ai_noted_missing: string[]; dropped: string[];
  sources?: { source_id: string; label: string; kind: string; note: string | null }[]; injection_flags?: number; run_id?: number;
};
export type LegacyImport = {
  id: number; method: "upload" | "conversation"; status: "draft" | "extracting" | "ready" | "failed" | "approved" | "discarded";
  raw_text: string | null; created_at: string; run: { id: number; status: string; spent_usd: number; error: string | null } | null;
  extraction: ImportExtraction | null; candidate: Record<string, string | number | null>; documents: LegacyDocument[];
  target_event: { id: number; name: string; values: Record<string, string | number | null> } | null;
  approved_event_id: number | null; decision: Record<string, unknown> | null;
};
export type QuantObservation = { area: string; area_label?: string; text: string; event_ids: number[]; basis: "computed"; sample_note: string;
  events?: { id: number; name: string | null }[] | string[] };
export type InsightLesson = { kind: string; theme: string; text: string; event_ids: number[]; reflection_ids: number[]; confidence: string;
  area: string; basis: string; area_label?: string; basis_label?: string; lesson_id?: number | null; status?: string;
  evidence?: { type: string; id: number; event_id: number; label: string }[] };
export type LegacyInsights = {
  quantitative_observations: QuantObservation[]; areas: Record<string, string>; note: string;
  latest_analysis: { run_id: number; date: string; summary: string | null; lessons: InsightLesson[];
    themes: { name: string; polarity: string; description: string }[]; disagreements: { topic: string; positions: string[] }[] } | null;
};

export type ReflectionAnswer = { key: string; question: string; answer: string };
export type LegacyReflection = { id: number; event_id: number; author: string; user_id: number | null; recorded_by?: string | null; answers: ReflectionAnswer[]; rating: number | null; is_demo: boolean; created_at: string };

export type LessonItem = {
  id: number; run_id: number | null; lesson: string; kind: string | null; theme: string | null; confidence: string; applies_to: string;
  scope: string | null; focus_event_id: number | null; status: "new" | "reviewed" | "adopted" | "dismissed" | "superseded";
  reviewed_at: string | null; based_on_demo_data: boolean | null; evidence: { type: string; id: number; event_id: number; label: string }[];
  created_at: string;
};

export type LegacyAnalysis = {
  run_id: number; date: string;
  themes: { name: string; polarity: string; description: string }[];
  disagreements: { topic: string; positions: string[] }[];
  comparison: { sufficient: boolean; note: string | null } | null;
  numeric_comparison_note: string | null;
};

export type LegacyEventDetail = {
  event: LegacyEvent & { reflections: LegacyReflection[] };
  lessons: LessonItem[];
  latest_analysis: LegacyAnalysis | null;
  questions: { key: string; question: string }[];
};

export type LegacyMetrics = {
  events_recorded: number; events_demo: number; reflections_collected: number; reflections_demo: number; contributors: number;
  photos: number; lessons_generated: number; lessons_current: number; recurring_issues: { theme: string; evidence_count: number }[];
  recommendations_reviewed: number; recommendations_adopted: number; recommendations_dismissed: number;
  outcome_improvement: string; outcome_note: string;
};

export type ListDiff = { only_without: string[]; only_with: string[]; in_both: string[] };
export type ExperimentComparison = {
  summary_of_changes: string[];
  numbers: Record<string, { without_history: number | null; with_history: number | null; delta: number | null }>;
  history_constraints: string[];
  lessons_applied: ListDiff; fundraising_strategy: ListDiff; logistics_notes: ListDiff; risks: ListDiff; decisions_for_board: ListDiff; next_steps: ListDiff;
  headlines: { without_history: string | null; with_history: string | null };
  recommendations: { without_history: string | null; with_history: string | null };
  note: string;
};
export type Experiment = {
  id: number; kind: string; request: string; research_mode: string; run_a_id: number | null; run_b_id: number | null;
  status: "queued" | "running" | "completed" | "failed"; error: string | null; created_at: string; finished_at: string | null;
  comparison: ExperimentComparison | null;
};

// ── Event Studio ────────────────────────────────────────────────────────────────

export type Assumption = { value: number | null; kind: "published" | "board" | "history" | "lesson" | "placeholder" | "hypothetical" | "missing"; basis: string };
export type Scenario = { attendance: number; ticket_revenue_usd: number | null; sponsorship_revenue_usd: number | null; donations_usd: number | null; other_revenue_usd?: number | null; total_revenue_usd: number | null; total_cost_usd: number; net_usd: number | null; vs_target_usd: number | null };
export type ModelCheck = { name: string; passed: boolean | null; detail: string; kind: string };
export type EventModel = {
  lines: { category: string; amount_usd: number; basis: string }[];
  subtotal_usd: number; contingency_pct: number; contingency_usd: number; total_cost_usd: number; upfront_cash_usd: number;
  catering_minimum_applies: boolean; scenarios: Record<"conservative" | "base" | "optimistic", Scenario>;
  break_even_attendance: number | null; break_even_note: string | null; missing_inputs: string[]; complete: boolean;
  break_even_confirmed_only?: number | null; sponsorship_confirmed_usd?: number; sponsorship_unconfirmed_usd?: number;
  checks: ModelCheck[]; assumptions: Record<string, Assumption>; attendance: number; max_budget_usd: number | null; target_usd: number | null;
  scenario_definitions: Record<string, string>; catering_minimum_risk?: { minimum_usd: number; guests: number; overpay_usd: number } | null;
};
export type Affordability = { verdict: string; checks: ModelCheck[]; conflicts: { type: string; detail: string; source: string }[]; warnings: string[]; cash_note: string };
export type PlanSnapshot = {
  round: number; option_id?: string; venue: string; event_format: string; pricing_status?: string; total_usd?: number; upfront_cash_usd?: number;
  base_net_usd?: number | null; contingency_pct?: number; verdict?: string | null; finance_status?: string; conflicts?: string[];
  conflict_sources?: string[]; changes_from_previous?: string | null; rationale?: string | null;
};
export type PacketVenue = {
  name: string; location: string | null; website: string | null; website_status: string | null; verified_at: string | null; source_url: string | null;
  verification: string | null; capacity: Record<string, number>; capacity_status: string | null; capacity_quote: string | null;
  pricing_status: string | null; pricing: string | null; amenities: string[]; restrictions: string[]; notes: string | null; shortlist_rank: number | null;
};
export type MissionContribution = {
  inclusion: string; connection: string; accessibility: string; recognition: string; charitable_alignment: string;
  community_lessons_applied: string[]; open_questions: string[];
};
export type CommunityInsight = {
  lens: string; lens_label: string; observation: string; quote: string; reflection_ids: number[]; event_ids: number[];
  evidence_type: string; evidence_label: string;
};

export type ProposalRow = {
  round: number; label: string; venue: string; event_format: string; total_usd: number; upfront_cash_usd: number; base_net_usd: number | null;
  conservative_net_usd: number | null; verdict: string | null; conflicts: string[]; change_in_total_usd: number; change_in_upfront_usd: number;
};
export type FinanceFeedback = {
  venue: string; event_format: string; total_cost_usd: number; upfront_cash_usd: number; verdict: string | null;
  cost_drivers: { line: string; amount_usd: number; share_of_total: number | null }[];
  issues: { type: string; source: string; detail: string; limit_usd?: number; over_by_usd?: number }[];
};

export type StrategyPacket = {
  proposal_comparison?: ProposalRow[];
  finance_feedback?: FinanceFeedback[];
  authorized_budget_usd?: number | null;
  mission_contribution?: MissionContribution | null;
  community_insights?: CommunityInsight[];
  run: { id: number; status: string; research_mode: string | null; strategy: string; started_at: string; duration_ms: number | null; event_plan_id: number | null; options: { use_history?: boolean } | null; error: string | null };
  overview: { event: Record<string, string | number | null> | null; request: string; interpreted: Record<string, unknown> | null; routing: string | null };
  recommendation: BoardRecommendation | null;
  venues: PacketVenue[];
  shortlist: { option_id: string; venue: string; event_format: string; rank: number; total_usd: number; upfront_cash_usd: number; pricing_status: string; rationale: string; lessons_applied: string[]; verification: string; website: string | null; source_url: string | null }[];
  sources: { title: string; url: string | null; verification: string; http_status: number | null; retrieved_at: string | null; note: string | null }[];
  lessons: { kind: string; theme?: string; text: string; event_ids: number[]; reflection_ids: number[]; confidence: string; events: { id: number; name: string }[];
    basis?: string; basis_label?: string; area?: string }[];
  history_checks: { name: string; passed: boolean; detail: string; events: { id: number; name: string }[]; reflection_ids: number[] }[];
  what_we_learned?: {
    used: boolean;
    events_consulted: { id: number; name: string; reasons: string[]; score: number }[];
    quantitative_observations: { area: string; text: string; sample_note: string; events: string[]; basis_label: string }[];
    lessons: { text: string; basis_label: string }[];
    constraints: { name: string; detail: string }[];
    influence: { area: string; detail: string; by: string; events?: string[] }[];
  };
  revision: { original: PlanSnapshot | null; revised: PlanSnapshot | null; reasons: { type: string; detail: string; source: string }[]; history: PlanSnapshot[] };
  budget_warnings: { level: "conflict" | "warning" | "unknown"; text: string }[];
  drafts: { id: number; recipient: string; subject: string; body: string; status: "draft" | "reviewed" | "archived"; draft_type: string; is_synthetic_target: boolean | null }[];
  trace: { n: number; step_key: string; from_agent: string; to_agent: string; kind: string | null; revision_round: number | null; status: string; objective: string; duration_ms: number | null; summary: string | null; models: string[]; input_tokens: number; output_tokens: number; cost_usd: number }[];
  usage: { model_calls: number; input_tokens: number; cached_input_tokens: number; output_tokens: number; web_search_calls: number; cost_usd: number;
    by_agent: Record<string, { calls: number; input_tokens: number; cached_input_tokens: number; output_tokens: number; cost_usd: number }>;
    by_model: Record<string, { calls: number; input_tokens: number; cached_input_tokens: number; output_tokens: number; cost_usd: number }> };
  verification: { passed: boolean; checks: Check[] } | null;
  finance_visible: boolean;
  financial_model?: EventModel; affordability?: Affordability; position?: Record<string, number | string | null>;
};

// ── Financial Intelligence (Prompt 6) ─────────────────────────────────────────────

export type FinanceMetric = {
  key: string; label: string; value: number | null; display: string;
  status: "recorded" | "calculated" | "partial" | "not_documented"; explanation: string; basis: string;
};
export type VarianceRow = {
  category: string; budget_usd: number | null; actual_usd: number | null; variance_usd: number | null; variance_pct: number | null; direction: string;
};
export type FinanceDashboard = {
  is_demo: boolean; basis: string; metrics: FinanceMetric[];
  monthly: { period: string; income: number; expense: number; net: number }[];
  income_by_category: { category: string; amount_usd: number; share: number | null }[];
  expense_by_category: { category: string; amount_usd: number; share: number | null }[];
  expense_ratios: { total_usd: number; by_purpose: Record<string, number>; ratios: Record<string, number> };
  restrictions: Record<string, number | null>;
  donation_trend: { period: string; donations: number; events: number; grants: number; other: number }[];
  gifts_by_month: { period: string; gifts: number; amount_usd: number }[] | null;
  past_events: { id: number; name: string; event_date: string | null; fundraising_goal_usd: number | null; funds_raised_usd: number | null;
    total_cost_usd: number | null; funds_directed_usd: number | null; net_usd: number | null; is_demo: boolean }[];
  legacy_funds_directed_usd: number | null;
  variances: { label: string; kind: string; months: number; months_with_actuals: number; rows: VarianceRow[] }[];
  statements: { period_label: string; revenue_usd: number; expenses_usd: number; net_usd: number }[];
  scenarios: { label: string; basis: string; rows: { scenario: string; revenue_usd: number; cost_usd: number; net_usd: number; vs_first_usd: number }[] } | null;
  warnings: { severity: "high" | "medium" | "low"; title: string; detail: string }[];
  missing: string[]; pending_review: number; method: string;
};
export type FinanceDocument = {
  id: number; filename: string; file_type: "csv" | "pdf"; doc_type: string; doc_type_label: string; size_bytes: number;
  status: string; page_count: number | null; notes: string[]; period_label: string | null; run_id: number | null; is_demo: boolean;
  created_at: string; figures: Record<string, number>;
};
export type ExtractedFigureRow = {
  id: number; document_id: number; label: string; kind: string; category: string; restriction: string | null; purpose: string | null;
  amount_usd: number | null; original_amount: string; currency: string; period: string | null; period_label: string | null;
  period_months: number | null; page: number | null; found_on_page: boolean | null; status: "pending" | "approved" | "rejected" | "reference";
  check_notes: string[] | null; record_id: number | null;
};

// ── Donations & Compliance (Prompt 6) ─────────────────────────────────────────────

export type DonationFlag = { code: string; severity: "high" | "medium" | "low"; text: string; ref: string | null };
export type DonationRow = {
  id: number; donation_id: string; donor_id: string | null; donor_name: string; has_email: boolean; amount_usd: number; currency: string;
  received_on: string; method: string | null; designation: string; contribution_type: string; restriction: string | null;
  payment_status: string; ack_status: string; acknowledged: boolean; campaign_id: number | null; campaign: string | null;
  in_kind_description: string | null; goods_services_value_usd: number | null; notes: string; source: string; is_demo: boolean;
  created_at: string | null; updated_at: string | null; tax_treatment: string; flags: DonationFlag[];
};
export type CampaignRow = { id: number; name: string; kind: string; goal_usd: number | null; is_demo: boolean; received_usd?: number; pledged_usd?: number; gifts?: number; progress?: number | null };
export type DonationSummary = {
  received_usd: number; gifts_received: number; donors: number; average_gift_usd: number | null; pledged_outstanding_usd: number; pledges: number;
  in_kind_gifts: number; event_related_usd: number; unassigned_usd: number; by_month: { period: string; amount_usd: number }[];
  by_campaign: CampaignRow[]; ack_status: Record<string, number>; by_restriction: Record<string, number>; duplicates_excluded: number;
  reconciliation: { period: string; donation_records_usd: number; ledger_donations_usd: number; difference_usd: number }[]; notes: string[];
};
export type DonationsResponse = {
  donations: DonationRow[]; summary: DonationSummary; campaigns: CampaignRow[];
  totals: { count: number; amount_usd: number; needs_attention: number; unacknowledged: number }; is_demo: boolean; note: string;
};
export type ComplianceRef = {
  id: string; title: string; authority: string; jurisdiction: string; kind: string; url: string; source_updated: string; checked_on: string;
  stale: boolean; points: string[];
};
export type ComplianceItem = {
  key: string; title: string; detail: string; kind: "verified_requirement" | "general_guidance" | "needs_professional_review";
  professional: string | null; donation_ids: number[]; references: ComplianceRef[];
};

export type SafetyLimit = { key: string; label: string; value: number; minimum: number; hard_cap: number; kind: "usd" | "int" };
export type SafetyLimitsResponse = { limits: SafetyLimit[]; editable: boolean; note: string };
export type SecurityEventRow = {
  id: number; category: string; label: string; severity: "info" | "low" | "medium" | "high"; agent: string | null; run_id: number | null;
  defense: string; created_at: string; detail: string;
};
export type SafetyTestRow = {
  name: string; category: string; mode: "mocked" | "live"; passed: boolean; observed: string; expected: string | null;
  defense: string | null; run_id: number | null; ran_at: string;
};
export type SafetyOverview = {
  admin: boolean;
  limits: SafetyLimit[];
  matrix: {
    agents: { agent: string; name: string; purpose: string; data_scopes: string[]; tools: { tool: string; data_scope: string }[] }[];
    prohibited: { name: string; label: string }[];
    notes: string[];
  };
  tests: SafetyTestRow[];
  events: {
    counts: Record<string, { label: string; count: number }>;
    total_30_days: number;
    blocked_actions: SecurityEventRow[];
    budget: SecurityEventRow[];
    injections: SecurityEventRow[];
    data_access: SecurityEventRow[];
    other: SecurityEventRow[];
  };
  risks: { risk: string; mitigation: string; residual: string }[];
};
