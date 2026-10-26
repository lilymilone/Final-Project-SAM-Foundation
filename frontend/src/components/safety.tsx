import { AlertTriangle, Ban, Check, ChevronDown, Eye, FileWarning, Lock, ShieldAlert, ShieldCheck, SlidersHorizontal, Wallet, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { SafetyLimit, SafetyLimitsResponse, SafetyOverview, SafetyTestRow, SecurityEventRow } from "../api/types";
import { useApi } from "../api/useApi";
import { Card, ErrorState, LoadingState, StatTile, Toast } from "./ui";

/**
 * The Safety section of Analytics & Safety. Every number and row comes from logged records
 * (security_events, safety_tests) or from the code that enforces the rule. No butterflies here:
 * warnings should read as warnings.
 */

const fmtLimit = (l: SafetyLimit, v: number = l.value) => (l.kind === "usd" ? `$${v.toFixed(2)}` : v.toLocaleString());
const when = (iso: string) => new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

function Quiet({ children }: { children: ReactNode }) {
  return <p className="rounded-xl bg-ivory/80 px-3 py-2.5 text-sm text-muted">{children}</p>;
}

export function PassFail({ passed }: { passed: boolean }) {
  return passed ? (
    <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-[#e6f0ea] px-2 py-0.5 text-xs font-bold text-sage"><Check size={12} aria-hidden="true" />PASS</span>
  ) : (
    <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-[#fbeef3] px-2 py-0.5 text-xs font-bold text-danger"><X size={12} aria-hidden="true" />FAIL</span>
  );
}

function ModeBadge({ mode }: { mode: "mocked" | "live" }) {
  return mode === "live" ? (
    <span className="shrink-0 rounded-full bg-plum px-2 py-0.5 text-[0.7rem] font-semibold uppercase tracking-wide text-white">Live model</span>
  ) : (
    <span className="shrink-0 rounded-full bg-lilac px-2 py-0.5 text-[0.7rem] font-semibold uppercase tracking-wide text-royal">Mocked model</span>
  );
}

function SeverityMark({ severity }: { severity: SecurityEventRow["severity"] }) {
  const color = severity === "high" ? "bg-danger" : severity === "medium" ? "bg-amber" : severity === "low" ? "bg-royal" : "bg-lavender";
  return <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${color}`} title={`${severity} severity`} aria-label={`${severity} severity`} />;
}

export function SafetySummary({ data }: { data: SafetyOverview }) {
  const mocked = data.tests.filter((t) => t.mode === "mocked");
  const live = data.tests.filter((t) => t.mode === "live");
  const blocked = data.events.blocked_actions.length + data.events.data_access.length;
  const ratio = (rows: SafetyTestRow[]) => (rows.length ? `${rows.filter((t) => t.passed).length}/${rows.length}` : "none yet");
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <StatTile label="Deterministic tests passing" value={ratio(mocked)} hint="pytest, scripted model, latest run of each" />
      <StatTile label="Live-model tests passing" value={ratio(live)} hint="real OpenAI calls, latest run of each" />
      <StatTile label="Safety events, 30 days" value={data.events.total_30_days} hint="from the security event log" />
      <StatTile label="Blocked or denied" value={blocked} hint="tool, action, URL, and data-access refusals (latest 15 per list)" />
    </div>
  );
}

export function LimitsCard({ onSaved }: { onSaved: () => void }) {
  const limits = useApi<SafetyLimitsResponse>("/api/safety/limits");
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ message: string; tone: "success" | "error" } | null>(null);

  useEffect(() => {
    if (limits.data) setDraft(Object.fromEntries(limits.data.limits.map((l) => [l.key, String(l.value)])));
  }, [limits.data]);

  const changed = limits.data?.limits.filter((l) => draft[l.key] !== undefined && Number(draft[l.key]) !== l.value) ?? [];

  const save = async () => {
    setSaving(true);
    try {
      const res = await api<{ changed: Record<string, { from: number; to: number; requested: number }> }>("/api/safety/limits", {
        method: "PUT",
        json: { limits: Object.fromEntries(changed.map((l) => [l.key, Number(draft[l.key])])) },
      });
      const clamped = Object.values(res.changed).filter((c) => c.to !== c.requested).length;
      setToast({ message: `Limits saved${clamped ? `; ${clamped} value(s) held to the allowed range` : ""}.`, tone: "success" });
      limits.reload();
      onSaved();
    } catch (e) {
      setToast({ message: e instanceof ApiError ? e.message : "Could not save the limits.", tone: "error" });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card title="Workflow safety limits" icon={<SlidersHorizontal size={16} aria-hidden="true" />}
      action={limits.data?.editable && changed.length > 0 ? (
        <button className="btn btn-primary !px-3.5 !py-1.5 text-sm" disabled={saving} onClick={save}>{saving ? "Saving…" : `Save ${changed.length} change${changed.length > 1 ? "s" : ""}`}</button>
      ) : undefined}>
      {limits.loading && <LoadingState rows={3} />}
      {limits.error && <ErrorState message={limits.error.message} onRetry={limits.reload} />}
      {limits.data && (
        <>
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wider text-muted">
              <tr><th className="py-1.5 pr-2">Limit</th><th className="px-2 text-right">Active</th><th className="pl-2 text-right">Hard cap</th></tr>
            </thead>
            <tbody>
              {limits.data.limits.map((l) => (
                <tr key={l.key} className="border-t border-lavender/25">
                  <td className="py-1.5 pr-2 text-plum">{l.label}</td>
                  <td className="px-2 py-1.5 text-right font-semibold text-plum">
                    {limits.data!.editable ? (
                      <input aria-label={l.label} type="number" className="field !w-24 !px-2 !py-1 text-right" min={l.minimum} max={l.hard_cap}
                        step={l.kind === "usd" ? 0.01 : 1} value={draft[l.key] ?? ""} onChange={(e) => setDraft({ ...draft, [l.key]: e.target.value })} />
                    ) : fmtLimit(l)}
                  </td>
                  <td className="py-1.5 pl-2 text-right text-muted">{fmtLimit(l, l.hard_cap)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-xs text-muted">
            {limits.data.note} {limits.data.editable ? "Values outside the allowed range are held to it, and every change is logged." : "Only the board chair can change limits."}
          </p>
        </>
      )}
      {toast && <Toast message={toast.message} tone={toast.tone} onDone={() => setToast(null)} />}
    </Card>
  );
}

export function PermissionMatrix({ matrix }: { matrix: SafetyOverview["matrix"] }) {
  return (
    <Card title="Agent tool permissions" icon={<Lock size={16} aria-hidden="true" />} className="lg:col-span-2">
      <div className="-mx-2 overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="text-xs uppercase tracking-wider text-muted">
            <tr><th className="px-2 py-1.5">Agent</th><th className="px-2">Data it may read</th><th className="px-2">Allowed tools (data scope)</th></tr>
          </thead>
          <tbody>
            {matrix.agents.map((a) => (
              <tr key={a.agent} className="border-t border-lavender/25 align-top">
                <td className="px-2 py-2.5"><b className="text-plum">{a.name}</b><span className="block max-w-[16rem] text-xs text-muted">{a.purpose}</span></td>
                <td className="px-2 py-2.5">
                  <div className="flex flex-wrap gap-1">{a.data_scopes.length ? a.data_scopes.map((s) => <span key={s} className="rounded-full bg-lilac px-2 py-0.5 text-xs text-royal">{s}</span>) : <span className="text-xs text-muted">none (works from what the Orchestrator hands it)</span>}</div>
                </td>
                <td className="px-2 py-2.5">
                  <div className="flex flex-wrap gap-1">{a.tools.length ? a.tools.map((t) => (
                    <span key={t.tool} className="rounded-full border border-lavender/50 bg-white px-2 py-0.5 text-xs text-plum">{t.tool} <span className="text-muted">· {t.data_scope}</span></span>
                  )) : <span className="text-xs text-muted">no tools (delegates in code)</span>}</div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 rounded-2xl border border-danger/20 bg-[#fdf5f8] p-3.5">
        <p className="flex items-center gap-2 text-sm font-semibold text-plum"><Ban size={15} className="text-danger" aria-hidden="true" />No agent can do any of these. The tools do not exist, and the registry refuses the names.</p>
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {matrix.prohibited.map((p) => <li key={p.name} className="rounded-full bg-[#fbeef3] px-2.5 py-0.5 text-xs font-medium text-danger">{p.label}</li>)}
        </ul>
      </div>
      <ul className="mt-3 list-disc space-y-0.5 pl-5 text-xs text-muted">{matrix.notes.map((n) => <li key={n}>{n}</li>)}</ul>
    </Card>
  );
}

function TestRow({ t }: { t: SafetyTestRow }) {
  return (
    <li className="rounded-xl border border-lavender/30 bg-white/70 px-3 py-2.5">
      <details className="group">
        <summary className="flex cursor-pointer list-none items-start gap-2.5">
          <PassFail passed={t.passed} />
          <span className="flex-1 text-sm font-medium text-plum">{t.name}</span>
          <ModeBadge mode={t.mode} />
          <ChevronDown size={16} className="mt-0.5 shrink-0 text-muted transition group-open:rotate-180" aria-hidden="true" />
        </summary>
        <dl className="mt-2.5 space-y-1.5 border-t border-lavender/25 pt-2.5 text-xs">
          {t.expected && <div><dt className="inline font-semibold text-plum">Expected: </dt><dd className="inline text-muted">{t.expected}</dd></div>}
          <div><dt className="font-semibold text-plum">Observed:</dt>
            {t.observed.includes(" | ") ? (
              <dd><ul className="mt-0.5 space-y-0.5">{t.observed.replace(/^(PASS|FAIL): /, "").split(" | ").map((line, i) => (
                <li key={i} className={`break-words ${line.startsWith("✗") ? "text-danger" : "text-ink"}`}>{line}</li>))}</ul></dd>
            ) : <dd className="whitespace-pre-wrap break-words text-ink">{t.observed}</dd>}
          </div>
          {t.defense && <div><dt className="inline font-semibold text-plum">Responsible defense: </dt><dd className="inline text-muted">{t.defense}</dd></div>}
          <div className="text-muted">Ran {when(t.ran_at)}{t.run_id && <> · <Link className="text-royal underline" to={`/activity/runs/${t.run_id}`}>run #{t.run_id} trace</Link></>}</div>
        </dl>
      </details>
    </li>
  );
}

export function TestResults({ tests }: { tests: SafetyTestRow[] }) {
  const live = tests.filter((t) => t.mode === "live");
  const mocked = tests.filter((t) => t.mode === "mocked");
  return (
    <Card title="Safety test results" icon={<ShieldCheck size={16} aria-hidden="true" />} className="lg:col-span-2">
      <p className="mb-3 text-sm text-muted">
        PASS appears only when the executed test's checks held. <b className="text-plum">Mocked</b> tests run the real code with a scripted model (repeatable, free).
        {" "}<b className="text-plum">Live</b> tests send the attack through real OpenAI models.
      </p>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div>
          <h3 className="mb-2 font-display text-lg font-semibold text-plum">Live-model tests</h3>
          {live.length ? <ul className="space-y-2">{live.map((t) => <TestRow key={t.name} t={t} />)}</ul> : <Quiet>No live-model safety tests recorded yet.</Quiet>}
        </div>
        <div>
          <h3 className="mb-2 font-display text-lg font-semibold text-plum">Deterministic tests (mocked model)</h3>
          {mocked.length ? <ul className="space-y-2">{mocked.map((t) => <TestRow key={t.name} t={t} />)}</ul> : <Quiet>No recorded runs of the adversarial suite yet.</Quiet>}
        </div>
      </div>
    </Card>
  );
}

export function EventList({ title, icon, rows, empty, admin }: { title: string; icon: ReactNode; rows: SecurityEventRow[]; empty: string; admin: boolean }) {
  return (
    <Card title={title} icon={icon}>
      {rows.length === 0 ? <Quiet>{empty}</Quiet> : (
        <ul className="space-y-2">
          {rows.map((e) => (
            <li key={e.id} className="flex gap-2.5 rounded-xl bg-ivory/70 px-3 py-2 text-sm">
              <SeverityMark severity={e.severity} />
              <div className="min-w-0 flex-1">
                <p className="font-medium text-plum">{e.label}{e.agent && <span className="font-normal text-muted"> · {e.agent.replace(/_/g, " ")}</span>}</p>
                <p className={`break-words text-xs ${admin ? "text-ink" : "italic text-muted"}`}>{e.detail}</p>
                <p className="mt-0.5 text-[0.72rem] text-muted">
                  {when(e.created_at)}{e.defense && <> · {e.defense}</>}
                  {e.run_id && <> · <Link className="text-royal underline" to={`/activity/runs/${e.run_id}`}>run #{e.run_id}</Link></>}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function SafetyEvents({ data }: { data: SafetyOverview }) {
  const e = data.events;
  return (
    <>
      <EventList title="Blocked unauthorized actions" icon={<Ban size={16} aria-hidden="true" />} rows={e.blocked_actions} admin={data.admin}
        empty="No tool, action, or URL has been blocked in the last 30 days." />
      <EventList title="Prompt-injection outcomes" icon={<ShieldAlert size={16} aria-hidden="true" />} rows={e.injections} admin={data.admin}
        empty="No injected instructions were found in retrieved or uploaded content in the last 30 days." />
      <EventList title="Budget and limit events" icon={<Wallet size={16} aria-hidden="true" />} rows={e.budget} admin={data.admin}
        empty="No workflow hit a budget, step, time, or tool-call limit in the last 30 days." />
      <EventList title="Data-access warnings" icon={<Eye size={16} aria-hidden="true" />} rows={e.data_access} admin={data.admin}
        empty="No role or workspace access was denied in the last 30 days." />
      <EventList title="Uploads, outputs, and model policy" icon={<FileWarning size={16} aria-hidden="true" />} rows={e.other} admin={data.admin}
        empty="No rejected uploads, flagged outputs, model restrictions, or limit changes in the last 30 days." />
      <RisksCard risks={data.risks} />
    </>
  );
}

function RisksCard({ risks }: { risks: SafetyOverview["risks"] }) {
  return (
    <Card title="Known unresolved risks" icon={<AlertTriangle size={16} aria-hidden="true" />}>
      <ul className="space-y-2.5">
        {risks.map((r) => (
          <li key={r.risk} className="rounded-xl border-l-4 border-amber/70 bg-ivory/70 px-3 py-2 text-sm">
            <p className="font-semibold text-plum">{r.risk}</p>
            <p className="mt-0.5 text-xs text-muted"><b className="text-plum">Mitigation:</b> {r.mitigation}</p>
            <p className="mt-0.5 text-xs text-amber"><b>Still possible:</b> {r.residual}</p>
          </li>
        ))}
      </ul>
    </Card>
  );
}
