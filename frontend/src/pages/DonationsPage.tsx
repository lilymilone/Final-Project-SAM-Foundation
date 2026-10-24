import { CheckCircle2, CircleAlert, HandCoins, ShieldCheck } from "lucide-react";
import type { Donations } from "../api/types";
import { formatDate, usd, useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { AgentPanel } from "../components/AgentPanel";
import { DraftsPanel } from "../components/outputs";
import { RunLauncher } from "../components/RunLauncher";
import { Card, DemoBadge, EmptyState, ErrorState, LoadingState, PageHeader, RestrictedState, StatTile } from "../components/ui";

function DonationsBody() {
  const { data, error, loading, reload } = useApi<Donations>("/api/donations");
  if (loading) return <LoadingState rows={4} />;
  if (error) return <ErrorState message={error.message} onRetry={reload} />;
  if (!data) return null;

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-4 animate-fade-up">
        <StatTile label="Gifts recorded" value={data.totals.count} demo={data.is_demo} />
        <StatTile label="Total received" value={usd(data.totals.amount_usd)} />
        <StatTile label="Need attention" value={data.totals.needs_attention} />
        <StatTile label="Not yet thanked" value={data.totals.unacknowledged} />
      </div>
      <div className="grid gap-5 lg:grid-cols-[1.5fr_1fr]">
        <Card title="Donation records" icon={<HandCoins size={16} aria-hidden="true" />} action={data.is_demo ? <DemoBadge label="Synthetic donors" /> : undefined}>
          {data.donations.length === 0 ? <EmptyState title="No donations recorded" /> : (
            <div className="-mx-2 overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-sm">
                <thead>
                  <tr className="text-xs uppercase tracking-wider text-muted">
                    <th className="px-2 py-2 font-semibold">Donor</th>
                    <th className="px-2 py-2 font-semibold">Amount</th>
                    <th className="px-2 py-2 font-semibold">Received</th>
                    <th className="px-2 py-2 font-semibold">Thanked</th>
                    <th className="px-2 py-2 font-semibold">For review</th>
                  </tr>
                </thead>
                <tbody>
                  {data.donations.map((d) => (
                    <tr key={d.id} className="border-t border-lavender/25 align-top">
                      <td className="px-2 py-3 font-semibold text-plum">{d.donor_name}<span className="block text-xs font-normal text-muted">{d.method ?? "method missing"}</span></td>
                      <td className="px-2 py-3">{usd(d.amount_usd)}</td>
                      <td className="px-2 py-3 text-muted">{formatDate(d.received_on)}</td>
                      <td className="px-2 py-3">
                        {d.acknowledged
                          ? <CheckCircle2 size={17} className="text-sage" aria-label="Acknowledged" />
                          : <CircleAlert size={17} className="text-amber" aria-label="Not acknowledged" />}
                      </td>
                      <td className="px-2 py-3">
                        {d.flags.length === 0 ? <span className="text-muted">—</span> : (
                          <ul className="space-y-1">{d.flags.map((f) => <li key={f} className="rounded-lg bg-[#fbf1e3] px-2 py-1 text-xs text-amber">{f}</li>)}</ul>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="mt-4 flex items-center gap-2 rounded-xl bg-lilac/60 px-3 py-2 text-xs text-plum">
            <ShieldCheck size={14} aria-hidden="true" /> {data.note} Donor emails stay on the server and are never shown here.
          </p>
        </Card>
        <div className="space-y-5">
          <RunLauncher title="Ask Donations & Compliance" intent="donations_review" lockIntent
            examples={["Which donations still need thank-you letters, and what should our accountant review?"]} />
          <AgentPanel agents={["donations_compliance"]} upcoming={[]} />
        </div>
      </div>
      <DraftsPanel kind="donor" title="Acknowledgment drafts (unsent)" />
    </div>
  );
}

export default function DonationsPage() {
  const { can } = useAuth();
  return (
    <>
      <PageHeader eyebrow="Donations & Compliance" title="Every gift, honored and in order"
        subtitle="Organize records, spot missing details, and prepare thank-you notes. SAM SPACE never contacts donors on its own." />
      {can("view_donor_data") ? <DonationsBody /> : <RestrictedState area="Donor records" />}
    </>
  );
}
