import { ChevronRight, History } from "lucide-react";
import { Link } from "react-router-dom";
import type { Activity, RunSummary } from "../api/types";
import { useApi } from "../api/useApi";
import { INTENT_LABELS, ModeBadge, StatusPill } from "../components/agents";
import { RunLauncher } from "../components/RunLauncher";
import { Card, EmptyState, ErrorState, LoadingState, PageHeader, StatTile } from "../components/ui";

const n = (v: number | null | undefined) => (v == null ? "—" : v.toLocaleString());
export const GALA_EXAMPLE = "Plan a 150-person Manhattan fundraising gala, using lessons from our previous events and checking whether we can afford it.";

export default function ActivityPage() {
  const activity = useApi<Activity>("/api/activity");
  const runs = useApi<{ runs: RunSummary[] }>("/api/runs");

  return (
    <>
      <PageHeader eyebrow="Agent Activity" title="See exactly what the agents did"
        subtitle="Every workflow, step, tool call, model, token, and cost, as recorded." />

      <div className="mb-5 grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <RunLauncher examples={[GALA_EXAMPLE, "Find eating disorder research initiatives in New York we could support", "What lessons can we learn from our previous events?"]} />
        <Card title="Recent workflows" icon={<History size={16} aria-hidden="true" />}>
          {runs.loading && <LoadingState rows={3} />}
          {runs.error && <ErrorState message={runs.error.message} onRetry={runs.reload} />}
          {runs.data && (runs.data.runs.length === 0 ? <EmptyState title="No workflows run yet">Ask the agents something to start your first workflow.</EmptyState> : (
            <ul className="space-y-2">{runs.data.runs.slice(0, 8).map((r) => (
              <li key={r.id}>
                <Link to={`/activity/runs/${r.id}`} className="flex items-center justify-between gap-3 rounded-2xl bg-ivory/70 px-3.5 py-2.5 transition hover:bg-lilac/60">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-plum">#{r.id} {r.request}</p>
                    <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted">
                      {INTENT_LABELS[r.intent ?? r.workflow_type] ?? r.workflow_type} · ${r.spent_usd.toFixed(4)} · {r.model_calls} calls
                      <ModeBadge mode={r.research_mode} />
                    </p>
                  </div>
                  <span className="flex items-center gap-1"><StatusPill status={r.status} /><ChevronRight size={15} className="text-muted" aria-hidden="true" /></span>
                </Link>
              </li>))}</ul>
          ))}
        </Card>
      </div>

      {activity.data && (
        <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-4">
          <StatTile label="Model calls (all time)" value={n(activity.data.totals.model_calls)} />
          <StatTile label="Input tokens" value={n(activity.data.totals.input_tokens)} hint={`${n(activity.data.totals.cached_input_tokens)} cached`} />
          <StatTile label="Output tokens" value={n(activity.data.totals.output_tokens)} />
          <StatTile label="Spend" value={`$${activity.data.totals.estimated_cost_usd.toFixed(4)}`} hint="at official list prices" />
        </div>
      )}

    </>
  );
}
