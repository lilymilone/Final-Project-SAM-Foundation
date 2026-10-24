import { ArrowDown, ChevronRight, History, Network } from "lucide-react";
import { Link } from "react-router-dom";
import type { Activity, AgentInfo, RunSummary } from "../api/types";
import { useApi } from "../api/useApi";
import { INTENT_LABELS, ModeBadge, StatusPill } from "../components/agents";
import { RunLauncher } from "../components/RunLauncher";
import { Card, EmptyState, ErrorState, LoadingState, PageHeader, StatTile } from "../components/ui";

const n = (v: number | null | undefined) => (v == null ? "—" : v.toLocaleString());
export const GALA_EXAMPLE = "Plan a 150-person Manhattan fundraising gala, using lessons from our previous events and checking whether we can afford it.";

export default function ActivityPage() {
  const agents = useApi<{ agents: AgentInfo[] }>("/api/agents");
  const activity = useApi<Activity>("/api/activity");
  const runs = useApi<{ runs: RunSummary[] }>("/api/runs");
  const orchestrator = agents.data?.agents.find((a) => a.name === "orchestrator");
  const specialists = agents.data?.agents.filter((a) => a.name !== "orchestrator") ?? [];

  return (
    <>
      <PageHeader eyebrow="Agent Activity" title="See exactly what the agents did"
        subtitle="Every run, handoff, tool call, and model call is recorded: which model, why, tokens, cost, and time. Nothing here is estimated or invented." />

      <div className="mb-5 grid gap-5 lg:grid-cols-[1.2fr_1fr]">
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
        <div className="mb-5 grid gap-3 sm:grid-cols-4">
          <StatTile label="Model calls (all time)" value={n(activity.data.totals.model_calls)} />
          <StatTile label="Input tokens" value={n(activity.data.totals.input_tokens)} hint={`${n(activity.data.totals.cached_input_tokens)} cached`} />
          <StatTile label="Output tokens" value={n(activity.data.totals.output_tokens)} />
          <StatTile label="Spend" value={`$${activity.data.totals.estimated_cost_usd.toFixed(4)}`} hint="at official list prices" />
        </div>
      )}

      <Card title="How the team is organized" icon={<Network size={16} aria-hidden="true" />}>
        {agents.loading && <LoadingState rows={2} />}
        {agents.error && <ErrorState message={agents.error.message} onRetry={agents.reload} />}
        {orchestrator && (
          <div className="flex flex-col items-center">
            <div className="w-full max-w-md rounded-2xl bg-gradient-to-br from-royal to-plum p-4 text-center text-white shadow-[var(--shadow-lift)]">
              <p className="font-display text-2xl font-semibold">{orchestrator.display_name}</p>
              <p className="mt-1 text-sm text-lilac/90">{orchestrator.purpose}</p>
            </div>
            <ArrowDown className="my-2 text-lavender" aria-hidden="true" />
            <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted">Typed handoffs to specialists · bounded revisions · no specialist can delegate</p>
            <ul className="grid w-full gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {specialists.map((a) => (
                <li key={a.name} className="rounded-2xl border border-lavender/40 bg-ivory/70 p-3.5">
                  <p className="font-semibold text-plum">{a.display_name}</p>
                  <p className="mt-0.5 text-xs text-muted">{a.purpose}</p>
                  <p className="mt-2 flex flex-wrap gap-1">{a.allowed_tools.map((t) => <code key={t} className="rounded bg-white px-1.5 text-[0.65rem] text-plum ring-1 ring-lavender/40">{t}</code>)}</p>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>
    </>
  );
}
