import { BadgeCheck, CircleDashed, FlaskConical, Globe2, Link2Off, Database, ShieldAlert } from "lucide-react";

export const AGENT_LABELS: Record<string, string> = {
  board: "Board member",
  orchestrator: "Orchestrator",
  mission_discovery: "Mission Discovery",
  fundraising_events: "Fundraising & Events",
  financial_analysis: "Financial Analysis",
  donations_compliance: "Donations & Compliance",
  partnerships_outreach: "Partnerships & Outreach",
  event_intelligence: "Event Intelligence",
};

export const INTENT_LABELS: Record<string, string> = {
  plan_event: "Plan an event",
  mission_discovery: "Mission discovery",
  partnership_outreach: "Partners & outreach",
  financial_review: "Financial review",
  donations_review: "Donations review",
  event_learning: "Learn from past events",
  legacy_import: "Import a past event",
  document_extraction: "Organize a financial document",
  unsupported: "Not supported",
  auto: "Auto-detect",
};

export const STEP_LABELS: Record<string, string> = {
  intake: "Understand the request",
  extract: "Extract details for board review",
  lessons: "Lessons from past events",
  venues: "Venue research & strategy",
  finance: "Affordability check",
  outreach: "Outreach drafts",
  research: "Mission research",
  donations: "Donations review",
  recommendation: "Board recommendation",
  recommendation_fix: "Correct the recommendation",
  verification: "Verify in code",
};

export function stepLabel(key: string): string {
  if (key.startsWith("venues_revision")) return `Revised venue plan (round ${key.split("_").pop()})`;
  if (key.startsWith("finance_revision")) return `Re-check affordability (round ${key.split("_").pop()})`;
  return STEP_LABELS[key] ?? key.replace(/_/g, " ");
}

const STATUS_STYLE: Record<string, string> = {
  queued: "bg-lilac text-plum",
  running: "bg-royal text-white",
  completed: "bg-[#e3f1e8] text-sage",
  completed_with_warnings: "bg-[#fbf1e3] text-amber",
  needs_revision: "bg-[#fbf1e3] text-amber",
  refused: "bg-[#f3e9f7] text-royal",
  failed: "bg-[#fbeef3] text-danger",
  stopped: "bg-[#fbeef3] text-danger",
};

export function StatusPill({ status }: { status: string }) {
  const label = status === "needs_revision" ? "needs revision" : status === "completed_with_warnings" ? "completed · check warnings" : status;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ${STATUS_STYLE[status] ?? "bg-lilac text-plum"}`}>
      {status === "running" && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" aria-hidden="true" />}
      {label}
    </span>
  );
}

const VERIFY: Record<string, { label: string; cls: string; icon: typeof BadgeCheck }> = {
  verified: { label: "Link verified", cls: "bg-[#e3f1e8] text-sage", icon: BadgeCheck },
  unverified: { label: "Unverified", cls: "bg-[#fbf1e3] text-amber", icon: Link2Off },
  synthetic: { label: "Synthetic fixture", cls: "bg-blush text-plum", icon: FlaskConical },
  internal: { label: "SAM SPACE record", cls: "bg-lilac text-plum", icon: Database },
};

export function VerificationBadge({ value }: { value: string | null | undefined }) {
  const v = VERIFY[value ?? ""] ?? { label: value ?? "unknown", cls: "bg-lilac text-plum", icon: CircleDashed };
  const Icon = v.icon;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[0.7rem] font-semibold ${v.cls}`}>
      <Icon size={11} aria-hidden="true" /> {v.label}
    </span>
  );
}

export function ModeBadge({ mode }: { mode: string | null | undefined }) {
  if (mode === "records") {  // Our Legacy imports: the board's own sources only, no web research
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-lilac px-2.5 py-0.5 text-xs font-semibold text-royal">
        <Database size={12} aria-hidden="true" /> Board sources only (no web)
      </span>
    );
  }
  if (mode === "fixture") {  // server-side safety-test fixture; never selectable from the app
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-[#fbeef3] px-2.5 py-0.5 text-xs font-semibold text-danger">
        <ShieldAlert size={12} aria-hidden="true" /> Safety test fixture
      </span>
    );
  }
  return mode === "live" ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-[#e3eef8] px-2.5 py-0.5 text-xs font-semibold text-[#2c5a85]">
      <Globe2 size={12} aria-hidden="true" /> Live web research
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-full bg-blush px-2.5 py-0.5 text-xs font-semibold text-plum">
      <FlaskConical size={12} aria-hidden="true" /> Synthetic research data
    </span>
  );
}

export const money = (n: number | null | undefined, digits = 0) =>
  n === null || n === undefined ? "—"
    : `${n < 0 ? "−" : ""}$${Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
