import {
  ArrowLeft, ArrowRight, CheckCircle2, ChevronDown, CircleSlash, Coins, FileText, FlaskConical, Gauge, Lightbulb, ListChecks,
  RefreshCcw, ShieldCheck, Square, Wrench, XCircle,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Check, RunDetail, RunStep } from "../api/types";
import { useButterflies } from "../butterflies/ButterflyProvider";
import { AGENT_LABELS, INTENT_LABELS, ModeBadge, StatusPill, VerificationBadge, money, stepLabel } from "../components/agents";
import { Card, ErrorState, LoadingState } from "../components/ui";

const ACTIVE = new Set(["queued", "running"]);
const fmtTokens = (n: number | null | undefined) => (n == null ? "—" : n.toLocaleString());
const secs = (ms: number | null | undefined) => (ms == null ? "—" : `${(ms / 1000).toFixed(1)}s`);

function CheckRow({ c }: { c: Check }) {
  const Icon = c.passed === true ? CheckCircle2 : c.passed === false ? XCircle : CircleSlash;
  const color = c.passed === true ? "text-sage" : c.passed === false ? "text-danger" : "text-amber";
  return (
    <li className="flex gap-2.5 text-sm">
      <Icon size={17} className={`mt-0.5 shrink-0 ${color}`} aria-label={c.passed === true ? "passed" : c.passed === false ? "failed" : "note"} />
      <div><span className="font-semibold text-plum">{c.name}.</span> <span className="text-muted">{c.detail}</span></div>
    </li>
  );
}

function StepCard({ step, index }: { step: RunStep; index: number }) {
  const [open, setOpen] = useState(false);
  const r = step.result;
  const cost = step.model_calls.reduce((a, c) => a + (c.cost_usd ?? 0), 0);
  const tokensIn = step.model_calls.reduce((a, c) => a + (c.input_tokens ?? 0), 0);
  const tokensOut = step.model_calls.reduce((a, c) => a + (c.output_tokens ?? 0), 0);
  const models = [...new Set(step.model_calls.map((c) => c.model))];
  const isRevision = step.kind === "revision";
  return (
    <li className={`relative rounded-2xl border bg-white/85 p-4 shadow-sm ${isRevision ? "border-rose/60 ring-1 ring-rose/30" : "border-lavender/35"}`}>
      <button className="flex w-full flex-wrap items-start justify-between gap-3 text-left" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <div className="flex min-w-0 gap-3">
          <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-full text-sm font-bold ${isRevision ? "bg-rose text-white" : "bg-lilac text-plum"}`}>{index + 1}</span>
          <div className="min-w-0">
            <p className="flex flex-wrap items-center gap-x-2 text-xs font-semibold uppercase tracking-wide text-muted">
              {AGENT_LABELS[step.from_agent] ?? step.from_agent} <ArrowRight size={12} aria-hidden="true" /> <span className="text-royal">{AGENT_LABELS[step.to_agent] ?? step.to_agent}</span>
              {isRevision && <span className="rounded-full bg-rose/15 px-2 text-rose"><RefreshCcw size={10} className="mr-1 inline" aria-hidden="true" />revision {step.revision_round}</span>}
            </p>
            <p className="mt-0.5 font-display text-xl font-semibold text-plum">{stepLabel(step.step_key)}</p>
            <p className="text-sm text-muted">{step.redacted ? "Details hidden for your board role." : r?.summary ?? step.objective}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill status={step.status} />
          <span className="text-xs text-muted">{secs(step.duration_ms)}</span>
          <ChevronDown size={16} className={`text-muted transition ${open ? "rotate-180" : ""}`} aria-hidden="true" />
        </div>
      </button>
      <div className="mt-2 flex flex-wrap gap-1.5 pl-11 text-[0.7rem]">
        {models.map((m) => <span key={m} className="rounded-full bg-plum/90 px-2 py-0.5 font-semibold text-white">{m}</span>)}
        {step.model_calls.length > 0 && <span className="rounded-full bg-lilac px-2 py-0.5 text-plum">{fmtTokens(tokensIn)} in · {fmtTokens(tokensOut)} out · ${cost.toFixed(4)}</span>}
        {step.tool_calls.length > 0 && <span className="rounded-full bg-ivory px-2 py-0.5 text-plum ring-1 ring-lavender/40">{step.tool_calls.length} tool calls</span>}
      </div>
      {isRevision && step.constraints.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5 pl-11">
          {step.constraints.map((c, i) => (
            <li key={i} className="rounded-lg bg-[#fbf1e3] px-2 py-1 text-xs text-amber" title={c.detail}>
              {AGENT_LABELS[c.source_agent ?? ""] ?? "Constraint"}: {c.detail}
            </li>
          ))}
        </ul>
      )}
      {open && !step.redacted && (
        <div className="mt-4 space-y-4 border-t border-lavender/30 pt-4 pl-11 text-sm">
          {step.error && <p className="rounded-xl bg-[#fbeef3] px-3 py-2 text-danger">{step.error}</p>}
          {r && r.findings.length > 0 && (
            <div><p className="label">Findings</p><ul className="list-disc space-y-1 pl-5">{r.findings.map((f, i) => <li key={i}><span className="mr-1 rounded bg-lilac px-1.5 text-[0.65rem] uppercase text-royal">{f.kind.replace("_", " ")}</span>{f.claim}</li>)}</ul></div>
          )}
          {r && r.assumptions.length > 0 && <div><p className="label">Assumptions</p><ul className="list-disc space-y-0.5 pl-5 text-muted">{r.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul></div>}
          {r && r.warnings.length > 0 && <div><p className="label">Warnings &amp; uncertainties</p><ul className="list-disc space-y-0.5 pl-5 text-amber">{r.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></div>}
          {r && r.next_steps.length > 0 && <div><p className="label">Recommended next steps</p><ul className="list-disc space-y-0.5 pl-5">{r.next_steps.map((n, i) => <li key={i}>{n}</li>)}</ul></div>}
          {r && r.sources.length > 0 && (
            <div><p className="label">Sources</p><ul className="space-y-1">{r.sources.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center gap-2">
                <VerificationBadge value={s.verification} />
                {s.url && s.verification !== "synthetic" ? <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-royal underline">{s.title}</a> : <span>{s.title}</span>}
                {s.published && <span className="text-xs text-muted">{s.published}</span>}
              </li>))}</ul></div>
          )}
          {step.tool_calls.length > 0 && (
            <div><p className="label flex items-center gap-1"><Wrench size={13} aria-hidden="true" /> Tool calls</p>
              <ul className="space-y-1 text-xs">{step.tool_calls.map((t) => (
                <li key={t.id} className="flex flex-wrap gap-2">
                  <code className={`rounded px-1.5 ${t.allowed ? "bg-ivory text-plum" : "bg-[#fbeef3] text-danger"}`}>{t.tool}</code>
                  <span className="text-muted">{t.allowed ? (t.ok === false ? `error: ${t.error}` : t.summary) : `denied: ${t.denial}`}</span>
                  <span className="text-muted">{t.duration_ms != null ? `${t.duration_ms} ms` : ""}</span>
                </li>))}</ul></div>
          )}
          {step.model_calls.length > 0 && (
            <div className="-mx-2 overflow-x-auto"><p className="label px-2">Model calls</p>
              <table className="w-full min-w-[560px] text-left text-xs">
                <thead className="text-muted"><tr><th className="px-2">Model</th><th className="px-2">Why this model</th><th className="px-2">In / cached / out</th><th className="px-2">Cost</th><th className="px-2">Time</th></tr></thead>
                <tbody>{step.model_calls.map((c) => (
                  <tr key={c.id} className="border-t border-lavender/25 align-top">
                    <td className="px-2 py-1.5 font-semibold text-plum">{c.model}{c.attempt && c.attempt > 1 ? <span className="block font-normal text-amber">retry #{c.attempt - 1}</span> : null}{c.web_search_calls ? <span className="block font-normal text-muted">{c.web_search_calls} web search</span> : null}</td>
                    <td className="px-2 py-1.5 text-muted">{c.reason}{c.substitution && <span className="block text-amber">{c.substitution}</span>}</td>
                    <td className="px-2 py-1.5">{fmtTokens(c.input_tokens)} / {fmtTokens(c.cached_input_tokens)} / {fmtTokens(c.output_tokens)}</td>
                    <td className="px-2 py-1.5">{c.cost_usd == null ? "—" : `$${c.cost_usd.toFixed(5)}`}</td>
                    <td className="px-2 py-1.5">{secs(c.latency_ms)}</td>
                  </tr>))}</tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

export default function RunPage() {
  const { id } = useParams();
  const { celebrate } = useButterflies();
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);
  const finalRef = useRef<HTMLDivElement>(null);
  const wasActive = useRef(false);

  const load = useCallback(async () => {
    try {
      const d = await api<RunDetail>(`/api/runs/${id}`);
      setDetail(d);
      setError(null);
      return d;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the run.");
      return null;
    }
  }, [id]);

  useEffect(() => {
    let timer: number | undefined;
    let cancelled = false;
    const tick = async () => {
      const d = await load();
      if (cancelled || !d) return;
      if (ACTIVE.has(d.run.status)) {
        wasActive.current = true;
        timer = window.setTimeout(tick, 1500);
      }
    };
    tick();
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [load]);

  useEffect(() => {
    if (detail && wasActive.current && (detail.run.status === "completed" || detail.run.status === "completed_with_warnings")) {
      wasActive.current = false;
      window.setTimeout(() => celebrate("workflow", finalRef.current), 300);
    }
  }, [detail, celebrate]);

  if (error && !detail) return <ErrorState message={error} onRetry={load} />;
  if (!detail) return <LoadingState rows={4} />;
  const { run, steps, result, totals } = detail;
  const active = ACTIVE.has(run.status);
  const rec = result?.recommendation;
  const spentPct = Math.min(100, (totals.cost_usd / Math.max(run.budget_usd, 0.0001)) * 100);

  async function stop() {
    setStopping(true);
    await api(`/api/runs/${run.id}/stop`, { method: "POST" }).catch(() => undefined);
  }

  return (
    <>
      <Link to="/activity" className="mb-4 inline-flex items-center gap-1 text-sm text-royal hover:underline"><ArrowLeft size={14} aria-hidden="true" /> Agent Activity</Link>
      <Card className="mb-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="eyebrow">Workflow #{run.id} · {INTENT_LABELS[result?.intent ?? run.workflow_type] ?? run.workflow_type}{result?.routing ? ` · ${result.routing} routing` : ""}</p>
            <h1 className="mt-1 font-display text-3xl font-semibold leading-tight text-plum">“{run.request}”</h1>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <StatusPill status={run.status} /><ModeBadge mode={run.research_mode} />
              <span className="rounded-full bg-lilac px-2.5 py-0.5 text-xs font-semibold capitalize text-plum">Strategy: {run.strategy}</span>
              <span className="text-xs text-muted">{run.duration_ms ? `${secs(run.duration_ms)} total` : active ? "working…" : ""}</span>
            </div>
          </div>
          {active && <button className="btn btn-soft" onClick={stop} disabled={stopping}><Square size={14} aria-hidden="true" /> {stopping ? "Stopping…" : "Stop"}</button>}
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-4">
          <div className="rounded-2xl bg-ivory p-3"><p className="text-xs font-semibold uppercase tracking-wide text-muted"><Coins size={12} className="mr-1 inline" aria-hidden="true" />Spend</p>
            <p className="font-display text-2xl font-semibold text-plum">${totals.cost_usd.toFixed(4)}</p>
            <div className="mt-1 h-1.5 rounded-full bg-lilac" aria-hidden="true"><div className="h-1.5 rounded-full bg-gradient-to-r from-royal to-rose" style={{ width: `${spentPct}%` }} /></div>
            <p className="mt-1 text-[0.7rem] text-muted">of ${run.budget_usd.toFixed(2)} workflow budget</p></div>
          <div className="rounded-2xl bg-ivory p-3"><p className="text-xs font-semibold uppercase tracking-wide text-muted"><Gauge size={12} className="mr-1 inline" aria-hidden="true" />Tokens</p>
            <p className="font-display text-2xl font-semibold text-plum">{fmtTokens(totals.input_tokens + totals.output_tokens)}</p>
            <p className="text-[0.7rem] text-muted">{fmtTokens(totals.input_tokens)} in ({fmtTokens(totals.cached_input_tokens)} cached) · {fmtTokens(totals.output_tokens)} out</p></div>
          <div className="rounded-2xl bg-ivory p-3"><p className="text-xs font-semibold uppercase tracking-wide text-muted">Model calls</p>
            <p className="font-display text-2xl font-semibold text-plum">{totals.model_calls}</p>
            <p className="text-[0.7rem] text-muted">{totals.web_search_calls} web searches · {totals.tool_calls} tool calls{totals.denied_tool_calls ? ` · ${totals.denied_tool_calls} denied` : ""}</p></div>
          <div className="rounded-2xl bg-ivory p-3"><p className="text-xs font-semibold uppercase tracking-wide text-muted">Handoffs</p>
            <p className="font-display text-2xl font-semibold text-plum">{totals.handoffs}</p>
            <p className="text-[0.7rem] text-muted">{totals.revisions} revision step{totals.revisions === 1 ? "" : "s"}</p></div>
        </div>
        {run.error && <p className="mt-3 rounded-xl bg-[#fbeef3] px-3 py-2 text-sm text-danger">{run.error}</p>}
        {run.research_mode === "synthetic" && (
          <p className="mt-3 flex items-center gap-2 rounded-xl bg-blush/60 px-3 py-2 text-xs text-plum">
            <FlaskConical size={14} aria-hidden="true" /> This run used labeled synthetic research fixtures (venues, partners). It demonstrates the agents' collaboration; it is not live web research.
          </p>
        )}
      </Card>

      <div className="grid gap-5 xl:grid-cols-[1.15fr_1fr]">
        <section aria-label="Agent handoffs">
          <h2 className="mb-3 font-display text-2xl font-semibold text-plum">Handoffs, step by step</h2>
          <ol className="space-y-3">
            {steps.map((s, i) => <StepCard key={s.id} step={s} index={i} />)}
            {active && <li className="rounded-2xl border border-dashed border-lavender p-4 text-sm text-muted"><span className="mr-2 inline-block h-2 w-2 animate-pulse rounded-full bg-royal" aria-hidden="true" />The Orchestrator is working on the next step…</li>}
          </ol>
        </section>

        <div ref={finalRef} className="space-y-5">
          {result?.message && <Card title="Orchestrator"><p className="text-sm text-muted">{result.message}</p></Card>}
          {rec && (
            <Card title="Board recommendation" icon={<Lightbulb size={16} aria-hidden="true" />}>
              <p className="font-display text-2xl font-semibold leading-snug text-plum">{rec.headline}</p>
              <p className="mt-2 text-sm leading-relaxed text-ink">{rec.recommendation}</p>
              {rec.options.length > 0 && (
                <div className="mt-4 space-y-2">{rec.options.map((o, i) => (
                  <div key={i} className="rounded-xl bg-ivory px-3 py-2 text-sm"><p className="font-semibold text-plum">{o.title}</p><p className="text-muted">{o.summary}</p></div>))}</div>
              )}
              {[["Why", rec.rationale], ["Decisions for the board", rec.decisions_for_board], ["Risks", rec.risks], ["Next steps", rec.next_steps], ["Lessons applied", rec.lessons_applied], ["Caveats", rec.caveats]].map(([label, items]) =>
                (items as string[]).length ? (
                  <div key={label as string} className="mt-4"><p className="label">{label as string}</p><ul className="list-disc space-y-1 pl-5 text-sm">{(items as string[]).map((x, i) => <li key={i}>{x}</li>)}</ul></div>
                ) : null)}
            </Card>
          )}
          {result?.revision_history && result.revision_history.length > 0 && (
            <Card title="How the plan changed" icon={<RefreshCcw size={16} aria-hidden="true" />}>
              <ol className="space-y-2">{result.revision_history.map((h) => (
                <li key={h.round} className={`rounded-xl px-3 py-2 text-sm ${h.verdict === "affordable" ? "bg-[#e3f1e8]" : "bg-[#fbf1e3]"}`}>
                  <p className="font-semibold text-plum">{h.round === 0 ? "First plan" : `Revision ${h.round}`}: {h.venue} · {h.event_format.replace("_", " ")}</p>
                  <p className="text-muted">Total {money(h.total_usd)} · upfront {money(h.upfront_cash_usd)} · Finance: <b>{(h.verdict ?? h.finance_status).replace(/_/g, " ")}</b></p>
                  {h.conflicts.length > 0 && <ul className="mt-1 list-disc pl-5 text-xs text-amber">{h.conflicts.map((c, i) => <li key={i}>{c}</li>)}</ul>}
                </li>))}</ol>
            </Card>
          )}
          {result?.finance && (
            <Card title="Affordability (computed in Python)" icon={<ListChecks size={16} aria-hidden="true" />}>
              <p className="mb-3 text-sm">Verdict for <b>{result.finance.venue}</b>: <span className="font-semibold capitalize text-royal">{result.finance.verdict.replace(/_/g, " ")}</span></p>
              <ul className="space-y-2">{result.finance.affordability.checks.map((c) => <CheckRow key={c.name} c={c} />)}</ul>
              <table className="mt-4 w-full text-left text-sm"><tbody>
                {result.finance.budget.line_items.map((li) => <tr key={li.name} className="border-t border-lavender/25"><td className="py-1.5">{li.name}<span className="block text-xs text-muted">{li.basis}</span></td><td className="py-1.5 text-right">{money(li.amount_usd, 2)}</td></tr>)}
                <tr className="border-t border-lavender/25"><td className="py-1.5">Contingency ({Math.round(result.finance.budget.contingency_pct * 100)}%)</td><td className="py-1.5 text-right">{money(result.finance.budget.contingency_usd, 2)}</td></tr>
                <tr className="border-t-2 border-plum/30 font-semibold text-plum"><td className="py-1.5">Projected total</td><td className="py-1.5 text-right">{money(result.finance.budget.total_usd, 2)}</td></tr>
              </tbody></table>
            </Card>
          )}
          {result?.verification && (
            <Card title="Verification" icon={<ShieldCheck size={16} aria-hidden="true" />}
              action={<span className={`text-sm font-semibold ${result.verification.passed ? "text-sage" : "text-danger"}`}>{result.verification.passed ? "All checks passed" : "Check the flags"}</span>}>
              <ul className="space-y-2">{result.verification.checks.map((c) => <CheckRow key={c.name} c={c} />)}</ul>
            </Card>
          )}
          {result && result.drafts.length > 0 && (
            <Card title="Unsent drafts created" icon={<FileText size={16} aria-hidden="true" />} action={<Link className="btn btn-ghost !py-1 text-sm" to="/partnerships">Review →</Link>}>
              <ul className="space-y-1.5 text-sm">{result.drafts.map((d) => <li key={d.id}><b className="text-plum">{d.recipient}</b>: <span className="text-muted">{d.subject}</span></li>)}</ul>
            </Card>
          )}
          {result && result.findings.length > 0 && (
            <Card title="Research findings" action={<Link className="btn btn-ghost !py-1 text-sm" to="/mission">Save the best →</Link>}>
              <ul className="space-y-2 text-sm">{result.findings.map((f) => (
                <li key={f.id} className="rounded-xl bg-ivory px-3 py-2">
                  <div className="flex flex-wrap items-center gap-2"><VerificationBadge value={f.verification} /><span className="text-xs capitalize text-muted">{f.category} · {f.alignment} alignment</span></div>
                  {f.url && f.verification !== "synthetic" ? <a className="font-semibold text-royal underline" href={f.url} target="_blank" rel="noopener noreferrer">{f.title}</a> : <p className="font-semibold text-plum">{f.title}</p>}
                  <p className="text-muted">{f.summary}</p>
                </li>))}</ul>
            </Card>
          )}
          {result?.donations && (
            <Card title="Donations summary">
              <p className="text-sm">{result.donations.drafts_created} acknowledgment drafts created (names merged locally; the AI saw only counts).</p>
              <Link className="btn btn-ghost mt-2 !px-0 text-sm" to="/donations">Review acknowledgments →</Link>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
