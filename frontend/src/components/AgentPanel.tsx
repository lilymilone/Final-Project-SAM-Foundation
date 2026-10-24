import { Bot, Wrench } from "lucide-react";
import type { AgentInfo, ModelsOverview } from "../api/types";
import { useApi } from "../api/useApi";
import { Card, ErrorState, LoadingState } from "./ui";

const TIER_STYLE: Record<string, string> = {
  fast: "bg-lilac text-plum",
  intermediate: "bg-[#e6dcf6] text-royal",
  advanced: "bg-plum text-white",
};

/**
 * Describes the agent(s) behind a tab: purpose, tool allow-list, and which
 * model the router would pick for their typical tasks (no model call is made).
 */
export function AgentPanel({ agents, upcoming }: { agents: string[]; upcoming: string[] }) {
  const info = useApi<{ agents: AgentInfo[] }>("/api/agents");
  const models = useApi<ModelsOverview>("/api/models");

  return (
    <Card title="The agents behind this tab" icon={<Bot size={16} aria-hidden="true" />}>
      {(info.loading || models.loading) && <LoadingState rows={2} />}
      {info.error && <ErrorState message={info.error.message} onRetry={info.reload} />}
      {info.data && (
        <div className="space-y-4">
          {info.data.agents
            .filter((a) => agents.includes(a.name))
            .map((agent) => {
              const rows = models.data?.routing_preview.filter((r) => r.agent === agent.display_name) ?? [];
              return (
                <div key={agent.name} className="rounded-2xl border border-lavender/35 bg-ivory/60 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-display text-xl font-semibold text-plum">{agent.display_name}</p>
                    <span className="rounded-full bg-white px-2.5 py-0.5 text-xs font-semibold text-royal ring-1 ring-lavender/50">
                      {agent.status === "planned" ? "Architecture ready · arrives next build stage" : "Active"}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-muted">{agent.purpose}</p>
                  <div className="mt-3 flex flex-wrap items-center gap-1.5">
                    <Wrench size={13} className="text-lavender" aria-hidden="true" />
                    {agent.allowed_tools.map((t) => (
                      <code key={t} className="rounded-md bg-white px-1.5 py-0.5 text-[0.72rem] text-plum ring-1 ring-lavender/40">{t}</code>
                    ))}
                  </div>
                  {rows.length > 0 && (
                    <ul className="mt-3 space-y-1.5">
                      {rows.map((r) => (
                        <li key={r.task} className="flex flex-wrap items-center gap-2 text-sm">
                          <span className="text-ink">{r.task}</span>
                          <span className="text-muted">→</span>
                          {r.model ? (
                            <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${TIER_STYLE[r.tier ?? "fast"]}`}>
                              {r.model}
                            </span>
                          ) : (
                            <span className="text-xs text-danger">{r.error}</span>
                          )}
                          {r.estimated_cost_usd != null && (
                            <span className="text-xs text-muted">est. ${r.estimated_cost_usd.toFixed(4)}/call</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          {upcoming.length > 0 && (
            <div>
              <p className="label !mb-2">Coming to this tab</p>
              <ul className="grid gap-1.5 text-sm text-muted sm:grid-cols-2">
                {upcoming.map((u) => (
                  <li key={u} className="flex gap-2"><span className="text-rose">✦</span>{u}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
