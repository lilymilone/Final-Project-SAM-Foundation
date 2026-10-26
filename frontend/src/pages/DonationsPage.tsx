import { FileUp, HandCoins, HeartHandshake, Layers, ListChecks, PlusCircle, Scale, Sparkles, TableProperties } from "lucide-react";
import { useMemo, useState } from "react";
import type { DonationsResponse } from "../api/types";
import { useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { BarChart, SERIES_COLORS } from "../components/charts";
import { ACK_LABEL, ComplianceArea, DonationForm, DonationTable, FilterBar, ExportButton, ImportDonations, money } from "../components/donations";
import { DraftsPanel } from "../components/outputs";
import { RunLauncher } from "../components/RunLauncher";
import { Card, DemoBadge, ErrorState, LoadingState, PageHeader, RestrictedState, StatTile } from "../components/ui";

const month = (p: string) => new Date(Number(p.slice(0, 4)), Number(p.slice(5, 7)) - 1, 1).toLocaleDateString("en-US", { month: "short", year: "2-digit" });

function DonationsBody() {
  const { can } = useAuth();
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [panel, setPanel] = useState<"add" | "import" | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const toRecords = (f: Record<string, string>, message: string | null) => {
    setFilters(f);
    setHint(message);
    window.setTimeout(() => document.getElementById("records")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  };
  const query = useMemo(() => {
    const p = new URLSearchParams(Object.entries(filters).filter(([, v]) => v));
    return p.toString() ? `?${p}` : "";
  }, [filters]);
  const { data, error, loading, reload } = useApi<DonationsResponse>(`/api/donations${query}`);
  if (loading && !data) return <LoadingState rows={5} />;
  if (error) return <ErrorState message={error.message} onRetry={reload} />;
  if (!data) return null;
  const s = data.summary;
  const needAck = (s.ack_status.not_started ?? 0) + (s.ack_status.prepared ?? 0);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-2" aria-label="Donation actions">
        {can("manage_donations") && <button className={`btn ${panel === "add" ? "btn-primary" : "btn-soft"}`} onClick={() => setPanel(panel === "add" ? null : "add")}><PlusCircle size={15} aria-hidden="true" /> Add Donation</button>}
        {can("manage_donations") && <button className={`btn ${panel === "import" ? "btn-primary" : "btn-soft"}`} onClick={() => setPanel(panel === "import" ? null : "import")}><FileUp size={15} aria-hidden="true" /> Import Donation CSV</button>}
        <button className="btn btn-soft" onClick={() => toRecords({}, null)}><TableProperties size={15} aria-hidden="true" /> View Donation Records</button>
        <button className="btn btn-soft" onClick={() => toRecords({ payment_status: "received", ack_status: "not_started" }, "Received gifts with no acknowledgment yet. Press “Draft thank-you” on a gift to create its draft.")}>
          <Sparkles size={15} aria-hidden="true" /> Generate Acknowledgment Draft</button>
        <button className="btn btn-soft" onClick={() => toRecords({ flagged: "true" }, "Records with missing or questionable information. Edit a record to fix it.")}>
          <ListChecks size={15} aria-hidden="true" /> Review Missing Information</button>
      </div>
      {panel === "add" && <Card title="Add a donation" icon={<PlusCircle size={16} aria-hidden="true" />}><DonationForm campaigns={data.campaigns} onDone={() => { setPanel(null); reload(); }} onCancel={() => setPanel(null)} /></Card>}
      {panel === "import" && <Card title="Import donations from a CSV" icon={<FileUp size={16} aria-hidden="true" />}><ImportDonations onDone={() => { setPanel(null); reload(); }} /></Card>}
      {data.is_demo && (
        <p className="flex items-center gap-2 rounded-2xl bg-blush/60 px-4 py-2.5 text-sm text-plum">
          <DemoBadge label="Fictional demonstration data" /> Every donor and gift shown is invented for testing. None are real supporters of the foundation.
        </p>
      )}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 xl:grid-cols-6">
        <StatTile label="Received" value={money(s.received_usd)} hint={`${s.gifts_received} gift(s) · ${s.donors} donor(s)`} />
        <StatTile label="Average gift" value={money(s.average_gift_usd)} />
        <StatTile label="Pledged, not received" value={money(s.pledged_outstanding_usd)} hint={`${s.pledges} pledge(s), not counted as received`} />
        <StatTile label="Event-related" value={money(s.event_related_usd)} hint="tickets, sponsorships, event campaigns" />
        <StatTile label="In-kind gifts" value={s.in_kind_gifts} hint="counted, never valued by us" />
        <StatTile label="Need acknowledgment" value={needAck} hint={`${s.ack_status.completed ?? 0} completed`} />
      </div>

      <Card id="records" title="Donation records" icon={<HandCoins size={16} aria-hidden="true" />} action={<ExportButton />}>
        <FilterBar value={filters} onChange={(f) => { setFilters(f); setHint(null); }} campaigns={data.campaigns} />
        {hint && <p className="mt-2 rounded-xl bg-lilac/60 px-3 py-2 text-sm text-plum">{hint}</p>}
        <p className="my-2 text-xs text-muted">Showing {data.donations.length} of {data.totals.count} records{s.duplicates_excluded ? ` · ${s.duplicates_excluded} possible duplicate(s) counted once in the totals` : ""}.</p>
        <DonationTable rows={data.donations} campaigns={data.campaigns} onChange={reload} />
      </Card>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-5">
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <Card title="Gifts received by month" icon={<Sparkles size={16} aria-hidden="true" />}>
              {s.by_month.length === 0 ? <p className="text-sm text-muted">No received gifts yet.</p> : (
                <BarChart width={380} height={220} caption="Donations received by month" series={[{ key: "amount", label: "Received", color: SERIES_COLORS[0] }]}
                  rows={s.by_month.map((m) => ({ label: month(m.period), values: { amount: m.amount_usd } }))} />)}
              <p className="mt-2 text-xs text-muted">Pledges and in-kind gifts are excluded; duplicates count once.</p>
            </Card>
            <Card title="Campaigns and events" icon={<Layers size={16} aria-hidden="true" />}>
              <ul className="space-y-3">{s.by_campaign.map((c) => (
                <li key={c.id}>
                  <div className="flex items-baseline justify-between gap-2 text-sm"><span className="text-plum">{c.name}<span className="ml-1 text-xs text-muted">{c.kind}</span></span>
                    <span className="tabular-nums"><b>{money(c.received_usd)}</b>{c.goal_usd ? <span className="text-xs text-muted"> of {money(c.goal_usd)}</span> : null}</span></div>
                  {c.goal_usd ? <div className="mt-1 h-2 rounded-full bg-lilac/60" aria-hidden="true"><div className="h-2 rounded-full bg-royal" style={{ width: `${Math.min(100, (c.progress ?? 0) * 100)}%` }} /></div> : null}
                  <p className="text-xs text-muted">{c.gifts} gift(s){c.pledged_usd ? ` · ${money(c.pledged_usd)} pledged, not received` : ""}</p>
                </li>))}</ul>
              {s.unassigned_usd > 0 && <p className="mt-2 text-xs text-muted">{money(s.unassigned_usd)} received without a campaign.</p>}
            </Card>
          </div>
          <Card title="Acknowledgment tracking" icon={<HeartHandshake size={16} aria-hidden="true" />}>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-4">{Object.entries(ACK_LABEL).map(([k, v]) => (
              <div key={k} className="rounded-2xl bg-ivory/80 px-3 py-2"><p className="text-xs text-muted">{v}</p><p className="font-display text-2xl font-semibold text-plum">{s.ack_status[k] ?? 0}</p></div>))}</div>
            <p className="mt-2 text-xs text-muted">Received gifts only. “Completed” means a board member sent the acknowledgment outside SAM SPACE and recorded it here.</p>
          </Card>
          {s.reconciliation.length > 0 && (
            <Card title="Reconciliation with the financial records" icon={<Scale size={16} aria-hidden="true" />}>
              <table className="w-full text-sm"><thead><tr className="text-left text-xs text-muted"><th className="py-1">Month</th><th className="py-1 text-right">Donation records</th><th className="py-1 text-right">Ledger donations</th><th className="py-1 text-right">Difference</th></tr></thead>
                <tbody>{s.reconciliation.map((r) => (
                  <tr key={r.period} className="border-t border-lavender/30"><td className="py-1.5 text-plum">{month(r.period)}</td><td className="py-1.5 text-right tabular-nums">{money(r.donation_records_usd)}</td>
                    <td className="py-1.5 text-right tabular-nums">{money(r.ledger_donations_usd)}</td><td className={`py-1.5 text-right tabular-nums ${r.difference_usd ? "text-amber" : "text-sage"}`}>{money(r.difference_usd)}</td></tr>))}</tbody></table>
              <p className="mt-2 text-xs text-muted">Shown side by side, never added together, so no gift is double-counted. Differences usually mean a gift is in one record set and not the other; review them with your treasurer.</p>
            </Card>
          )}
          <DraftsPanel kind="donor" title="Acknowledgment drafts (unsent)" />
        </div>
        <div className="min-w-0 space-y-5">
          <RunLauncher title="Review donations with the agents" intent="donations_review" lockIntent submitLabel="Review donations"
            request="Which donations still need thank-you letters, and what should our accountant review?" />
          <ComplianceArea />
        </div>
      </div>
    </div>
  );
}

export default function DonationsPage() {
  const { can } = useAuth();
  return (
    <>
      <PageHeader eyebrow="Donations & Compliance" title="Donations"
        subtitle="Record gifts, keep acknowledgments on track, and see what to take to your accountant. SAM SPACE never contacts donors or files anything." />
      {can("view_donor_data") ? <DonationsBody /> : <RestrictedState area="Donations & Compliance" />}
    </>
  );
}
