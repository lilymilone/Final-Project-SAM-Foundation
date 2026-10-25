import { BarChart3, MessageSquareQuote } from "lucide-react";
import { Link } from "react-router-dom";
import type { LegacyInsights } from "../api/types";
import { formatDate, useApi } from "../api/useApi";
import { Card, ErrorState, LoadingState } from "./ui";

/** What our events teach us: numbers computed from the records (no AI) kept apart from interpretations and board
 * feedback, and every insight linked to the events and reflections behind it. */
export function InsightsPanel() {
  const { data, error, loading, reload } = useApi<LegacyInsights>("/api/legacy/insights");
  if (loading && !data) return <Card><LoadingState rows={3} /></Card>;
  if (error) return <ErrorState message={error.message} onRetry={reload} />;
  if (!data) return null;
  const latest = data.latest_analysis;
  const byArea = new Map<string, NonNullable<typeof latest>["lessons"]>();
  for (const l of latest?.lessons ?? []) byArea.set(l.area_label ?? l.area, [...(byArea.get(l.area_label ?? l.area) ?? []), l]);
  return (
    <Card title="What our events teach us" icon={<BarChart3 size={16} aria-hidden="true" />}
      action={latest ? <Link to={`/activity/runs/${latest.run_id}`} className="text-xs text-royal hover:underline">Analysis #{latest.run_id} · {formatDate(latest.date)}</Link> : undefined}>
      <div className="grid gap-5 lg:grid-cols-2">
        <div>
          <p className="label flex items-center gap-1.5"><BarChart3 size={13} aria-hidden="true" />Computed from recorded figures</p>
          {data.quantitative_observations.length === 0 ? <p className="text-sm text-muted">Not enough recorded figures to compare yet.</p> : (
            <ul className="space-y-2">{data.quantitative_observations.map((o, i) => (
              <li key={i} className="rounded-xl bg-ivory/80 px-3 py-2 text-sm">
                <p className="text-[0.68rem] font-semibold uppercase tracking-wide text-royal">{o.area_label}</p>
                <p className="text-ink">{o.text}</p>
                <p className="mt-0.5 text-[0.7rem] text-muted">{o.sample_note} {(o.events as { id: number; name: string | null }[] | undefined)?.map((e, j) => (
                  <Link key={e.id} to={`/legacy/${e.id}`} className="text-royal underline">{j ? ", " : ""}{e.name}</Link>))}</p>
              </li>))}</ul>
          )}
        </div>
        <div>
          <p className="label flex items-center gap-1.5"><MessageSquareQuote size={13} aria-hidden="true" />Interpretations and board feedback</p>
          {!latest ? <p className="text-sm text-muted">Run “Learn across all events” to compare approaches, recurring problems, sponsorship, costs, and community building.</p> : (
            <div className="space-y-3">{[...byArea.entries()].map(([area, items]) => (
              <div key={area}>
                <p className="text-[0.68rem] font-semibold uppercase tracking-wide text-royal">{area}</p>
                <ul className="space-y-1.5">{items.map((l, i) => (
                  <li key={i} className="rounded-xl bg-white/80 px-3 py-2 text-sm ring-1 ring-lavender/30">
                    <p className="text-ink">{l.text}</p>
                    <p className="mt-0.5 text-[0.7rem] text-muted"><span className={`mr-1 rounded-full px-1.5 py-0.5 font-semibold ${l.basis === "board_feedback" ? "bg-blush/70 text-plum" : "bg-lilac text-royal"}`}>{l.basis_label}</span>
                      {(l.evidence ?? []).map((e, j) => <Link key={j} to={`/legacy/${e.event_id}`} className="text-royal underline">{j ? " · " : ""}{e.label}</Link>)}</p>
                  </li>))}</ul>
              </div>))}</div>
          )}
        </div>
      </div>
      <p className="mt-3 text-xs text-muted">{data.note}</p>
    </Card>
  );
}
