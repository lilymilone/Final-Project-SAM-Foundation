import { Ban, Check, Gauge, KeyRound, Lock, Route, X } from "lucide-react";
import { useState } from "react";
import type { ModelsOverview, SafetyOverview, SafetyPolicy, Strategy, SystemStatus } from "../api/types";
import { useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { LimitsCard, PermissionMatrix, SafetyEvents, SafetySummary, TestResults } from "../components/safety";
import { Card, ErrorState, LoadingState, PageHeader } from "../components/ui";

function Yes({ ok, label }: { ok: boolean; label: string }) {
  return (
    <li className="flex items-center gap-2 text-sm">
      {ok ? <Check size={16} className="text-sage" aria-hidden="true" /> : <X size={16} className="text-muted" aria-hidden="true" />}
      <span>{label}</span>
      <span className="sr-only">{ok ? "yes" : "no"}</span>
    </li>
  );
}

export default function SafetyPage() {
  const { user } = useAuth();
  const [strategy, setStrategy] = useState<Strategy>(user?.settings.model_strategy ?? "auto");
  const status = useApi<SystemStatus>("/api/system/status");
  const models = useApi<ModelsOverview>(`/api/models?strategy=${strategy}`);
  const policy = useApi<SafetyPolicy>("/api/safety/policy");
  const overview = useApi<SafetyOverview>("/api/safety/overview");

  return (
    <>
      <PageHeader eyebrow="Analytics & Safety" title="Guardrails you can see"
        subtitle="Which AI provider and models are in use, how each task picks its model, what it costs, and what SAM SPACE will never do." />

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Configuration" icon={<KeyRound size={16} aria-hidden="true" />}>
          {status.loading && <LoadingState rows={2} />}
          {status.error && <ErrorState message={status.error.message} onRetry={status.reload} />}
          {status.data && (
            <div className="space-y-4">
              <ul className="space-y-1.5">
                <Yes ok={status.data.keys_detected.OPENAI_API_KEY} label="OPENAI_API_KEY found (value never shown)" />
                <Yes ok={status.data.keys_detected.PORTKEY_API_KEY} label="PORTKEY_API_KEY found (value never shown)" />
                <Yes ok={status.data.env_files_loaded.includes("repo")} label=".env in the repository folder" />
                <Yes ok={status.data.env_files_loaded.includes("parent")} label=".env one folder above the repository" />
              </ul>
              <p className="text-sm">Active provider: <b className="text-plum">{status.data.provider ?? "none"}</b> <span className="text-muted">(setting: {status.data.provider_setting})</span></p>
              <p className="text-sm">Model availability: <b className="text-plum">{status.data.model_availability.status}</b>
                {status.data.model_availability.checked_at && <span className="text-muted"> · checked {new Date(status.data.model_availability.checked_at).toLocaleTimeString()}</span>}
              </p>
              {status.data.model_availability.error && <p className="text-xs text-danger">{status.data.model_availability.error}</p>}
            </div>
          )}
        </Card>

        <Card title="Course key restriction" icon={<Lock size={16} aria-hidden="true" />}>
          {status.data && (
            <div className={`rounded-2xl p-4 text-sm ${status.data.portkey_policy.active ? "bg-plum text-white" : "bg-ivory text-plum ring-1 ring-lavender/40"}`}>
              <p className="font-semibold">{status.data.portkey_policy.active ? "Active: Portkey course key in use" : "Standing by: personal OpenAI key in use"}</p>
              <p className={`mt-1 ${status.data.portkey_policy.active ? "text-lilac" : "text-muted"}`}>{status.data.portkey_policy.rule}</p>
            </div>
          )}
          <p className="mt-3 text-xs text-muted">Enforced twice: once by the ModelRouter and again by the Portkey client, which refuses every model except {status.data?.portkey_policy.allowed_model ?? "gpt-6-luna"}.</p>
        </Card>

        <Card title="Model routing" icon={<Route size={16} aria-hidden="true" />} className="lg:col-span-2"
          action={
            <label className="flex items-center gap-2 text-sm">
              <span className="text-muted">Strategy</span>
              <select className="field !w-36 !py-1.5" value={strategy} onChange={(e) => setStrategy(e.target.value as Strategy)}>
                {(["auto", "economy", "balanced", "advanced"] as Strategy[]).map((s) => <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>)}
              </select>
            </label>
          }>
          {models.loading && <LoadingState rows={3} />}
          {models.error && <ErrorState message={models.error.message} onRetry={models.reload} />}
          {models.data && (
            <>
              <div className="mb-4 grid gap-3 sm:grid-cols-3">
                {Object.entries(models.data.tiers).map(([tier, info]) => {
                  const price = info.effective ? models.data!.pricing.models[info.effective] : undefined;
                  return (
                    <div key={tier} className="rounded-2xl border border-lavender/35 bg-ivory/60 p-3.5">
                      <p className="eyebrow">{models.data!.tier_names[tier]} · {tier}</p>
                      <p className="mt-1 font-display text-xl font-semibold text-plum">{info.effective ?? "unavailable"}</p>
                      <p className="text-xs text-muted">preferred: {info.preferred}{info.preferred_available === null ? " (checking…)" : info.preferred_available ? " ✓ available" : " ✗"}</p>
                      {info.note && <p className="mt-1 text-xs text-amber">{info.note}</p>}
                      {price && <p className="mt-2 text-xs text-plum">${price.input} in · ${price.cached_input} cached · ${price.output} out <span className="text-muted">per 1M</span></p>}
                    </div>
                  );
                })}
              </div>
              <p className="mb-3 rounded-xl bg-lilac/50 px-3 py-2 text-xs text-plum"><b>Rule:</b> {models.data.routing_rule} No model call is spent choosing a model.</p>
              <div className="-mx-2 overflow-x-auto">
                <table className="w-full min-w-[640px] text-left text-sm">
                  <thead className="text-xs uppercase tracking-wider text-muted">
                    <tr><th className="px-2 py-1.5">Agent · task</th><th className="px-2">Score</th><th className="px-2">Model</th><th className="px-2">Est. cost</th><th className="px-2">Why</th></tr>
                  </thead>
                  <tbody>
                    {models.data.routing_preview.map((r) => (
                      <tr key={`${r.agent}-${r.task}`} className="border-t border-lavender/25 align-top">
                        <td className="px-2 py-2"><b className="text-plum">{r.agent}</b><span className="block text-xs text-muted">{r.task}</span></td>
                        <td className="px-2 py-2">{r.score ?? "—"}</td>
                        <td className="px-2 py-2 font-semibold text-plum">{r.model ?? <span className="text-danger">{r.error}</span>}</td>
                        <td className="px-2 py-2">{r.estimated_cost_usd != null ? `$${r.estimated_cost_usd.toFixed(4)}` : "—"}</td>
                        <td className="px-2 py-2 text-xs text-muted">{r.reason}{r.substitution_note && <span className="block text-amber">{r.substitution_note}</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-3 text-xs text-muted">
                Prices: <a className="text-royal underline" href={models.data.pricing.source} target="_blank" rel="noreferrer">official OpenAI pricing</a>, retrieved {models.data.pricing.retrieved_on}. Estimates use each task's expected token counts. Real costs appear in Agent Activity.
              </p>
            </>
          )}
        </Card>

        <Card title="Accounts and sessions" icon={<Gauge size={16} aria-hidden="true" />}>
          {policy.data && (
            <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-2 text-sm">
              <dt className="text-muted">Session length</dt><dd className="text-right font-semibold text-plum">{policy.data.limits.session_hours} hours</dd>
              <dt className="text-muted">Failed sign-ins before a pause</dt><dd className="text-right font-semibold text-plum">{policy.data.limits.login_attempts}</dd>
            </dl>
          )}
          <p className="mt-3 text-xs text-muted">Sessions use an HttpOnly cookie; no key or token is ever stored in the browser.</p>
        </Card>
      </div>

      <section id="safety" className="mt-10 scroll-mt-6" aria-labelledby="safety-heading">
        <div className="mb-5">
          <p className="eyebrow mb-1.5">Safety</p>
          <h2 id="safety-heading" className="font-display text-3xl font-semibold text-plum">What the safeguards have actually done</h2>
          <p className="mt-1.5 max-w-3xl text-sm text-muted">
            Limits, permissions, test results, and events below come from the code that enforces them and from the security log.{" "}
            {overview.data && !overview.data.admin && "Event details are visible to the chair; you see categories and counts."}
          </p>
        </div>
        {overview.loading && <LoadingState rows={4} />}
        {overview.error && <ErrorState message={overview.error.message} onRetry={overview.reload} />}
        {overview.data && (
          <div className="space-y-5">
            <SafetySummary data={overview.data} />
            <div className="grid gap-5 lg:grid-cols-2">
              <LimitsCard onSaved={overview.reload} />
              <Card title="How a workflow is stopped" icon={<Ban size={16} aria-hidden="true" />}>
                <ul className="space-y-2 text-sm text-ink">
                  <li><b className="text-plum">Before every model call</b>, the worst-case cost is reserved against the workflow and daily budgets. If it does not fit, the call never happens.</li>
                  <li><b className="text-plum">Before every handoff</b>, the Orchestrator checks the step, revision, and repeat limits and the time limit.</li>
                  <li><b className="text-plum">Before every tool call</b>, the agent's allow-list, the tool's data scope, and the tool-call, search, and page-fetch limits are checked.</li>
                  <li><b className="text-plum">When a limit stops a run</b>, finished steps are kept and labeled partial. Nothing is reported as complete, and no celebration plays.</li>
                </ul>
              </Card>
              <PermissionMatrix matrix={overview.data.matrix} />
              <TestResults tests={overview.data.tests} />
              <SafetyEvents data={overview.data} />
            </div>
          </div>
        )}
      </section>
    </>
  );
}
