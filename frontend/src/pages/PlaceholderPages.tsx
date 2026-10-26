import { Compass, FileStack, HandHeart, Lock, Scale, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import type { MissionConfig, RunSummary } from "../api/types";
import { formatDate, useApi } from "../api/useApi";
import { StatusPill } from "../components/agents";
import { OpportunityDashboard } from "../components/opportunities";
import { LiveProgress, useRunPoll } from "../components/progress";
import { ReviewCenter } from "../components/reviewcenter";
import { PHILOSOPHY } from "../components/Philosophy";
import { RunLauncher } from "../components/RunLauncher";
import { Card, PageHeader } from "../components/ui";

export const NY_PARTNERS_EXAMPLE =
  "Find three organizations in New York that support mental health awareness and community belonging, and draft partnership inquiries.";

export function MissionCriteria() {
  const { data } = useApi<MissionConfig>("/api/mission");
  if (!data) return null;
  return (
    <Card title="How opportunities are judged" icon={<Scale size={16} aria-hidden="true" />}>
      <p className="font-display text-lg italic text-royal">“{PHILOSOPHY}”</p>
      <p className="mt-1 text-xs text-muted">The philosophy becomes questions answered from sources, never assumptions:</p>
      <ul className="mt-2 space-y-1 text-sm">{data.criteria.map((c) => <li key={c.key}><b className="text-plum">{c.label}.</b> <span className="text-ink/80">{c.question}</span></li>)}</ul>
      <p className="mt-3 text-[0.7rem] font-semibold uppercase tracking-wide text-royal">Fit rubric (applied in code)</p>
      <ul className="mt-1 space-y-1 text-sm">{data.fit_rubric.map((r) => <li key={r.label}><b className="text-plum">{r.label}:</b> <span className="text-ink/80">{r.rule}</span></li>)}</ul>
      <p className="mt-2 text-xs text-muted">Clinical and scientific research counts as strong alignment on its own. Web pages are treated as untrusted data: instructions inside them are removed and never followed.</p>
    </Card>
  );
}

export function MissionDiscoveryPage() {
  const [runId, setRunId] = useState<number | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [showRun, setShowRun] = useState(false);
  const detail = useRunPoll(runId, () => { setRefresh((n) => n + 1); setShowRun(true); });
  return (
    <>
      <PageHeader eyebrow="Mission Discovery" title="Find a cause to support"
        subtitle="Search for organizations, research, and events aligned with the foundation. Every result links to its source." />
      <div className="space-y-5">
        <RunLauncher title="Search" intent="mission_discovery" mode="live" lockIntent submitLabel="Find Opportunities"
          placeholder="Find organizations in New York supporting eating disorder research."
          examples={["Find organizations in New York supporting eating disorder research.",
            "Which mental-health nonprofits in New York run peer-support or belonging programs?"]}
          onStarted={(id) => { setRunId(id); setShowRun(false); }} />
        {detail && (
          <Card title={["queued", "running"].includes(detail.run.status) ? "Searching…" : "Search finished"} icon={<Compass size={16} aria-hidden="true" />}>
            <LiveProgress detail={detail} />
          </Card>
        )}
        <OpportunityDashboard runId={showRun ? runId : null} refreshKey={refresh} onClearRun={() => setShowRun(false)} />
      </div>
    </>
  );
}

function PartnershipPackets() {
  const { data } = useApi<{ runs: RunSummary[] }>("/api/runs");
  const runs = (data?.runs ?? []).filter((r) => (r.intent ?? r.workflow_type) === "partnership_outreach").slice(0, 6);
  return (
    <Card title="Partnership opportunity packets" icon={<FileStack size={16} aria-hidden="true" />}>
      {runs.length === 0 ? <p className="text-sm text-muted">No partnership packets yet. Use Find partners above.</p> : (
        <ul className="space-y-2">{runs.map((r) => (
          <li key={r.id}><Link to={`/partnerships/packets/${r.id}`} className="flex items-center justify-between gap-2 rounded-xl bg-white/80 px-3 py-2 text-sm ring-1 ring-lavender/30 hover:bg-lilac/50">
            <span className="min-w-0 truncate text-plum">#{r.id} · {r.request}</span>
            <span className="flex shrink-0 items-center gap-2 text-xs text-muted">{formatDate(r.started_at)}<StatusPill status={r.status} /></span>
          </Link></li>))}</ul>
      )}
    </Card>
  );
}

export function OutreachRestriction() {
  return (
    <Card title="What Outreach can and cannot do" icon={<Lock size={16} aria-hidden="true" />}>
      <div className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
        <div><p className="mb-1 flex items-center gap-1.5 font-semibold text-sage"><ShieldCheck size={14} aria-hidden="true" />Can</p>
          <ul className="list-disc space-y-0.5 pl-5 text-ink/85"><li>Generate drafts</li><li>Let you edit and save them</li><li>Copy text for you</li><li>Archive drafts</li></ul></div>
        <div><p className="mb-1 flex items-center gap-1.5 font-semibold text-danger"><HandHeart size={14} aria-hidden="true" />Never</p>
          <ul className="list-disc space-y-0.5 pl-5 text-ink/85"><li>Send email or messages</li><li>Contact any organization</li><li>Schedule or publish anything</li><li>Commit the foundation</li></ul></div>
      </div>
      <p className="mt-2 text-xs text-muted">Enforced in code: the Outreach agent's only tools read research and save drafts, and send/contact/schedule/publish tools cannot be registered at all. Drafts have no “sent” status.</p>
    </Card>
  );
}

export function PartnershipsPage() {
  return (
    <>
      <PageHeader eyebrow="Partnerships & Outreach" title="Outreach drafts"
        subtitle="Review, edit, and copy the drafts the agents prepared. You send them yourself; SAM SPACE never contacts anyone." />
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <div className="min-w-0"><ReviewCenter /></div>
        <div className="min-w-0 space-y-5">
          <RunLauncher title="Find partners and draft outreach" intent="partnership_outreach" mode="live" lockIntent submitLabel="Find partners"
            examples={[NY_PARTNERS_EXAMPLE, "Draft partnership inquiries to the opportunities we saved in Mission Discovery"]} />
          <PartnershipPackets />
        </div>
      </div>
    </>
  );
}
