import { CheckCircle2, ChevronDown, Circle, Loader2, RefreshCcw, Square, Wrench, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { RunDetail, RunStep } from "../api/types";
import { WorkingButterflies } from "../butterflies/WorkingButterflies";
import { AGENT_LABELS, StatusPill } from "./agents";
import { ExtLink, isPublicUrl } from "./ui";

const ACTIVE = new Set(["queued", "running"]);

/** What each step is doing, in the board's words. Keys are the backend's step keys; revisions share their base key. */
const DOING: Record<string, [string, string]> = {
  intake: ["Coordinating the request", "Coordinated the request"],
  lessons: ["Reviewing historical lessons", "Reviewed historical lessons"],
  venues: ["Researching venues", "Researched venues"],
  finance: ["Checking the budget", "Checked the budget"],
  evaluate: ["Reviewing constraints", "Reviewed constraints"],
  outreach_decision: ["Deciding which inquiries to draft", "Decided which inquiries to draft"],
  outreach: ["Preparing draft inquiries", "Prepared draft inquiries"],
  recommendation: ["Writing the board recommendation", "Wrote the board recommendation"],
  recommendation_fix: ["Correcting the recommendation", "Corrected the recommendation"],
  verification: ["Verifying figures and claims", "Verified figures and claims"],
  research: ["Researching opportunities", "Researched opportunities"],
  select: ["Selecting the strongest candidates", "Selected the strongest candidates"],
  donations: ["Reviewing donation records", "Reviewed donation records"],
  extract: ["Reading the uploaded records", "Read the uploaded records"],
};

function doing(step: RunStep): string {
  const base = step.step_key.replace(/_revision_\d+$/, "");
  const pair = DOING[base];
  const running = ACTIVE.has(step.status);
  const text = pair ? pair[running ? 0 : 1] : step.step_key.replace(/_/g, " ");
  return step.kind === "revision" ? `${text} (revision ${step.revision_round ?? ""})`.trim() : text;
}

/** Poll a workflow until it finishes. Returns the latest detail from the backend. */
export function useRunPoll(runId: number | null, onDone?: (d: RunDetail) => void): RunDetail | null {
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const done = useRef(onDone);
  done.current = onDone;
  useEffect(() => {
    if (runId == null) { setDetail(null); return; }
    let cancelled = false;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const d = await api<RunDetail>(`/api/runs/${runId}`);
        if (cancelled) return;
        setDetail(d);
        if (ACTIVE.has(d.run.status)) timer = window.setTimeout(tick, 1500);
        else done.current?.(d);
      } catch {
        if (!cancelled) timer = window.setTimeout(tick, 3000);
      }
    };
    tick();
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [runId]);
  return detail;
}

function StepRow({ step }: { step: RunStep }) {
  const [open, setOpen] = useState(false);
  const running = ACTIVE.has(step.status);
  const failed = ["failed", "stopped", "refused"].includes(step.status);
  const revise = step.status === "needs_revision";
  const Icon = running ? Loader2 : failed ? XCircle : revise ? RefreshCcw : CheckCircle2;
  const color = running ? "text-royal" : failed ? "text-danger" : revise ? "text-rose" : "text-sage";
  const findings = step.result?.findings ?? [];
  const cost = step.model_calls.reduce((a, c) => a + (c.cost_usd ?? 0), 0);
  return (
    <li className={`rounded-xl ${running ? "bg-lilac/70" : revise ? "bg-blush/50" : "bg-white/70"} ring-1 ring-lavender/25`}>
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm">
        <Icon size={17} className={`shrink-0 ${color} ${running ? "animate-spin" : ""}`} aria-hidden="true" />
        <span className="min-w-0 flex-1">
          <b className="text-plum">{AGENT_LABELS[step.to_agent] ?? step.to_agent}</b>
          <span className="text-ink/80"> — {doing(step)}</span>
        </span>
        <span className="hidden shrink-0 text-xs text-muted sm:inline">
          {step.tool_calls.length > 0 && <>{step.tool_calls.length} tool{step.tool_calls.length === 1 ? "" : "s"} · </>}
          {step.duration_ms != null ? `${(step.duration_ms / 1000).toFixed(1)}s` : running ? "working…" : ""}
        </span>
        <ChevronDown size={15} className={`shrink-0 text-muted transition ${open ? "rotate-180" : ""}`} aria-hidden="true" />
      </button>
      {open && (
        <div className="space-y-2 border-t border-lavender/30 px-3 pb-3 pt-2 text-xs">
          {step.redacted ? <p className="text-muted">Details hidden for your board role.</p> : (
            <>
              {step.result?.summary && <p className="text-ink/85">{step.result.summary}</p>}
              {step.tool_calls.length > 0 && (
                <ul className="space-y-1">{step.tool_calls.map((t) => (
                  <li key={t.id} className="flex gap-1.5"><Wrench size={12} className="mt-0.5 shrink-0 text-lavender" aria-hidden="true" />
                    <span><code className="text-plum">{t.tool}</code> <span className="text-muted">{t.allowed ? (t.summary ?? "") : `refused: ${t.denial}`}</span>
                      {t.allowed && isPublicUrl(t.url) && <> · <ExtLink href={t.url}>open page</ExtLink></>}</span></li>))}
                </ul>
              )}
              {findings.length > 0 && (
                <ul className="list-disc space-y-0.5 pl-4 text-ink/85">{findings.slice(0, 4).map((f, i) => <li key={i}>{f.claim}</li>)}</ul>
              )}
              {step.model_calls.length > 0 && (
                <p className="text-muted">{step.model_calls.map((m) => m.model).join(", ")} · ${cost.toFixed(4)}</p>
              )}
              {step.error && <p className="text-danger">{step.error}</p>}
            </>
          )}
        </div>
      )}
    </li>
  );
}

const COUNTS_HELP = "Steps: each hand-off from the Orchestrator to an agent (more appear as the work continues). AI calls: requests to a "
  + "language model, including web searches. Tool actions: lookups, page checks, and calculations done in code, which cost nothing. "
  + "The dollar figure is the AI cost so far.";

/**
 * Live view of a workflow, built only from what the backend has recorded: each handoff appears when the
 * Orchestrator opens it, with its real status, tool calls, findings, and model usage.
 */
export function LiveProgress({ detail, onStop }: { detail: RunDetail; onStop?: () => void }) {
  const active = ACTIVE.has(detail.run.status);
  const steps = detail.steps.filter((s) => s.step_key);
  const [stopping, setStopping] = useState(false);
  async function stop() {
    setStopping(true);
    await api(`/api/runs/${detail.run.id}/stop`, { method: "POST" }).catch(() => undefined);
    onStop?.();
  }
  return (
    <div className="space-y-3" aria-live="polite">
      {active && <WorkingButterflies />}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <StatusPill status={detail.run.status} />
          <span className="text-xs text-muted" title={COUNTS_HELP}>
            {active ? "So far: " : ""}{steps.length} step{steps.length === 1 ? "" : "s"} · {detail.totals.model_calls} AI call{detail.totals.model_calls === 1 ? "" : "s"}
            {" · "}{detail.totals.tool_calls} tool action{detail.totals.tool_calls === 1 ? "" : "s"} · ${detail.totals.cost_usd.toFixed(4)}{active ? "" : " total"}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {active && (
            <button type="button" className="btn btn-ghost !py-1 text-xs" onClick={stop} disabled={stopping}>
              <Square size={12} aria-hidden="true" /> {stopping ? "Stopping…" : "Stop"}
            </button>
          )}
          <Link to={`/activity/runs/${detail.run.id}`} className="text-xs text-royal hover:underline">Full trace</Link>
        </div>
      </div>
      <ol className="space-y-1.5">
        {steps.map((s) => <StepRow key={s.id} step={s} />)}
        {active && steps.length === 0 && (
          <li className="flex items-center gap-2.5 rounded-xl bg-lilac/60 px-3 py-2 text-sm">
            <Loader2 size={17} className="animate-spin text-royal" aria-hidden="true" />
            <b className="text-plum">Orchestrator</b><span className="text-ink/80"> — Starting the workflow</span>
          </li>
        )}
        {active && steps.length > 0 && !steps.some((s) => ACTIVE.has(s.status)) && (
          <li className="flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm text-muted">
            <Circle size={15} className="text-lavender" aria-hidden="true" /> Orchestrator — choosing the next step…
          </li>
        )}
      </ol>
      {detail.run.error && <p className="text-sm text-danger">{detail.run.error}</p>}
    </div>
  );
}
