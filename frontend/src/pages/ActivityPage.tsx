import { Activity as ActivityIcon, ArrowDown, Cpu, Network } from "lucide-react";
import type { Activity, AgentInfo } from "../api/types";
import { useApi } from "../api/useApi";
import { Card, EmptyState, ErrorState, LoadingState, PageHeader, StatTile } from "../components/ui";

const n = (v: number | null | undefined) => (v == null ? "—" : v.toLocaleString());

export default function ActivityPage() {
  const agents = useApi<{ agents: AgentInfo[] }>("/api/agents");
  const activity = useApi<Activity>("/api/activity");
  const orchestrator = agents.data?.agents.find((a) => a.name === "orchestrator");
  const specialists = agents.data?.agents.filter((a) => a.name !== "orchestrator") ?? [];

  return (
    <>
      <PageHeader eyebrow="Agent Activity" title="See exactly what the agents did"
        subtitle="Every run, handoff, tool call, and model call is recorded with the model chosen, why, tokens, cost, and time. Nothing here is estimated or invented." />

      <Card title="How the team is organized" icon={<Network size={16} aria-hidden="true" />} className="mb-5">
        {agents.loading && <LoadingState rows={2} />}
        {agents.error && <ErrorState message={agents.error.message} onRetry={agents.reload} />}
        {orchestrator && (
          <div className="flex flex-col items-center">
            <div className="w-full max-w-md rounded-2xl bg-gradient-to-br from-royal to-plum p-4 text-center text-white shadow-[var(--shadow-lift)]">
              <p className="font-display text-2xl font-semibold">{orchestrator.display_name}</p>
              <p className="mt-1 text-sm text-lilac/90">{orchestrator.purpose}</p>
            </div>
            <ArrowDown className="my-2 text-lavender" aria-hidden="true" />
            <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted">Structured handoffs to specialists</p>
            <ul className="grid w-full gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {specialists.map((a) => (
                <li key={a.name} className="rounded-2xl border border-lavender/40 bg-ivory/70 p-3.5">
                  <p className="font-semibold text-plum">{a.display_name}</p>
                  <p className="mt-0.5 text-xs text-muted">{a.purpose}</p>
                  <p className="mt-2 text-[0.7rem] font-semibold uppercase tracking-wide text-royal">{a.allowed_tools.length} allowed tools</p>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      {activity.loading && <LoadingState rows={3} />}
      {activity.error && <ErrorState message={activity.error.message} onRetry={activity.reload} />}
      {activity.data && (
        <>
          <div className="mb-5 grid gap-3 sm:grid-cols-4">
            <StatTile label="Model calls" value={n(activity.data.totals.model_calls)} />
            <StatTile label="Input tokens" value={n(activity.data.totals.input_tokens)} hint={`${n(activity.data.totals.cached_input_tokens)} cached`} />
            <StatTile label="Output tokens" value={n(activity.data.totals.output_tokens)} />
            <StatTile label="Spend" value={`$${activity.data.totals.estimated_cost_usd.toFixed(4)}`} hint="at official list prices" />
          </div>
          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Workflow runs" icon={<ActivityIcon size={16} aria-hidden="true" />}>
              {activity.data.runs.length === 0 ? (
                <EmptyState title="No workflows run yet">Runs appear here when the agents are connected in the next build stage.</EmptyState>
              ) : (
                <ul className="space-y-2 text-sm">
                  {activity.data.runs.map((r) => (
                    <li key={r.id} className="flex justify-between rounded-xl bg-ivory/70 px-3 py-2">
                      <span>{r.workflow_type}</span><span className="text-muted">{r.status} · ${r.spent_usd.toFixed(4)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card title="Model calls" icon={<Cpu size={16} aria-hidden="true" />}>
              {activity.data.model_calls.length === 0 ? (
                <EmptyState title="No model calls recorded">Each call will show the agent, the model selected and actually used, the reason, tokens, cost, and latency.</EmptyState>
              ) : (
                <div className="-mx-2 overflow-x-auto">
                  <table className="w-full min-w-[620px] text-left text-xs">
                    <thead className="uppercase tracking-wider text-muted">
                      <tr><th className="px-2 py-1.5">Agent / task</th><th className="px-2">Model</th><th className="px-2">In / cached / out</th><th className="px-2">Cost</th><th className="px-2">Time</th></tr>
                    </thead>
                    <tbody>
                      {activity.data.model_calls.map((c) => (
                        <tr key={c.id} className="border-t border-lavender/25 align-top" title={c.selection_reason}>
                          <td className="px-2 py-2"><b className="text-plum">{c.agent}</b><span className="block text-muted">{c.task}</span></td>
                          <td className="px-2 py-2">{c.selected_model}{c.model_used && c.model_used !== c.selected_model && <span className="block text-muted">API: {c.model_used}</span>}<span className="block text-muted">{c.provider}</span></td>
                          <td className="px-2 py-2">{n(c.input_tokens)} / {n(c.cached_input_tokens)} / {n(c.output_tokens)}</td>
                          <td className="px-2 py-2">{c.estimated_cost_usd == null ? "—" : `$${c.estimated_cost_usd.toFixed(6)}`}</td>
                          <td className="px-2 py-2">{c.latency_ms == null ? "—" : `${(c.latency_ms / 1000).toFixed(1)}s`}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </div>
        </>
      )}
    </>
  );
}
