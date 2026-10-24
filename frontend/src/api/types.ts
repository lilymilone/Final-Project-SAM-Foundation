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
