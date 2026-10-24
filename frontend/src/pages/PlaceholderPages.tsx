import { Compass, HeartHandshake, MailX, Search } from "lucide-react";
import type { Overview } from "../api/types";
import { useApi } from "../api/useApi";
import { AgentPanel } from "../components/AgentPanel";
import { Card, EmptyState, ErrorState, LoadingState, PageHeader } from "../components/ui";

export function MissionDiscoveryPage() {
  const { data, error, loading, reload } = useApi<Overview>("/api/overview");
  return (
    <>
      <PageHeader eyebrow="Mission Discovery" title="Find the people already doing this work"
        subtitle="Mental-health and eating-disorder organizations, awareness events, research initiatives, and partners, each with sources you can check." />
      <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <Card title="Opportunities" icon={<Compass size={16} aria-hidden="true" />}>
          <div className="mb-4 flex items-center gap-2 rounded-2xl border border-lavender/50 bg-white px-3.5 py-2.5 text-sm text-muted">
            <Search size={16} aria-hidden="true" />
            <span>Research requests open in the next build stage, when the Mission Discovery agent is connected.</span>
          </div>
          {loading && <LoadingState rows={2} />}
          {error && <ErrorState message={error.message} onRetry={reload} />}
          {data && (data.saved_opportunities.length === 0 ? (
            <EmptyState title="No opportunities saved yet">Findings will appear here with their source link and a label: verified, unverified, or estimate.</EmptyState>
          ) : (
            <ul className="space-y-2 text-sm">{data.saved_opportunities.map((o) => <li key={o.id}>{o.title}</li>)}</ul>
          ))}
        </Card>
        <AgentPanel agents={["mission_discovery"]}
          upcoming={["Organization and event research", "Every claim linked to a source", "Untrusted web text quarantined", "Save opportunities to the board"]} />
      </div>
    </>
  );
}

export function PartnershipsPage() {
  const { data, error, loading, reload } = useApi<Overview>("/api/overview");
  return (
    <>
      <PageHeader eyebrow="Partnerships & Outreach" title="Warm, thoughtful outreach, reviewed by you"
        subtitle="Sponsor research and editable partnership and venue-inquiry drafts. A person always reviews and sends them outside SAM SPACE." />
      <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-5">
          <Card title="Drafts awaiting review" icon={<HeartHandshake size={16} aria-hidden="true" />}>
            {loading && <LoadingState rows={2} />}
            {error && <ErrorState message={error.message} onRetry={reload} />}
            {data && (data.drafts_awaiting_review.length === 0 ? (
              <EmptyState title="No drafts yet">Drafts written by the Partnerships agent will wait here for your edits.</EmptyState>
            ) : (
              <ul className="space-y-2 text-sm">{data.drafts_awaiting_review.map((d) => <li key={d.id}>{d.subject} · {d.recipient_org}</li>)}</ul>
            ))}
          </Card>
          <div className="flex items-start gap-3 rounded-2xl border border-lavender/40 bg-white/70 p-4 text-sm text-plum">
            <MailX size={18} className="mt-0.5 shrink-0 text-royal" aria-hidden="true" />
            <p><b>SAM SPACE cannot send email.</b> There is no sending tool in the app at all, and the server refuses send actions, so a draft can only leave when a person copies it.</p>
          </div>
        </div>
        <AgentPanel agents={["partnerships_outreach"]}
          upcoming={["Sponsor research with sources", "Venue inquiry drafts", "Partnership proposals in your voice", "Edit, copy, archive (never send)"]} />
      </div>
    </>
  );
}
