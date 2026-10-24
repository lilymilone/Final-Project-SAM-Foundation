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
export type ResearchMode = "synthetic" | "live";

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
  finance?: { verdict: string; affordability: { checks: Check[] }; budget: { total_usd: number; upfront_cash_usd: number; line_items: { name: string; amount_usd: number; basis: string }[]; contingency_pct: number; contingency_usd: number; assumptions: string[] }; position: Record<string, number | string | null>; break_even: { break_even_attendance: number | null }; venue: string; event_format: string } | null;
  shortlist: { option_id: string; venue: string; event_format: string; total_usd: number; upfront_cash_usd: number; rationale: string; verification: string; source_url: string | null }[];
  drafts: { id: number; recipient: string; subject: string; draft_type: string; synthetic_target: boolean }[];
  lessons: { kind: string; text: string; event_ids: number[]; reflection_ids: number[]; confidence: string }[];
  disagreements: { topic: string; positions: string[]; evidence_reflection_ids: number[] }[];
  findings: { id: number; title: string; url: string | null; category: string; alignment: string; verification: string; summary: string; date: string | null; uncertainty: string }[];
  donations: { aggregate: Record<string, unknown>; drafts_created: number; review_items: { issue: string; why_professional_review: string }[] } | null;
  event_plan_id: number | null;
};

export type RunDetail = {
  run: RunSummary;
  steps: RunStep[];
  result: RunResult | null;
  totals: { model_calls: number; input_tokens: number; cached_input_tokens: number; output_tokens: number; web_search_calls: number; cost_usd: number; tool_calls: number; denied_tool_calls: number; handoffs: number; revisions: number };
};

export type Draft = {
  id: number; run_id: number | null; agent: string | null; draft_type: string; recipient_name: string; recipient_org: string;
  subject: string; body: string; status: "draft" | "reviewed" | "archived"; personalization_basis: string | null;
  is_synthetic_target: boolean | null; created_at: string;
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
