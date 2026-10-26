import { ArrowRight, ChevronDown, Minus, Send } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Intent, ResearchMode, RunSummary } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Butterfly } from "../butterflies/Butterfly";
import { useButterflies } from "../butterflies/ButterflyProvider";
import { LiveProgress, useRunPoll } from "./progress";

const SIR_PHOTO = "/brand/sir.webp";
const ACTIVE = new Set(["queued", "running"]);
const INTENTS: { value: Intent | ""; label: string; needs?: string }[] = [
  { value: "", label: "Let SAM SPACE decide" },
  { value: "plan_event", label: "Plan an event" },
  { value: "mission_discovery", label: "Find a cause" },
  { value: "partnership_outreach", label: "Find partners and draft outreach" },
  { value: "event_learning", label: "Learn from past events" },
  { value: "financial_review", label: "Review finances", needs: "view_financials" },
  { value: "donations_review", label: "Review donations", needs: "view_donor_data" },
];
const RESULT_PAGE: Record<string, (id: number) => string> = {
  plan_event: (id) => `/events/packets/${id}`,
  partnership_outreach: (id) => `/partnerships/packets/${id}`,
};

/** A purple ribbon for Sir, drawn over the corner of his photo (the photo itself is never altered). */
function Ribbon({ size }: { size: number }) {
  return (
    <svg viewBox="0 0 48 34" width={size} height={size * 0.71} aria-hidden="true" className="pointer-events-none absolute drop-shadow-sm"
      style={{ top: -size * 0.18, right: -size * 0.28, transform: "rotate(18deg)" }}>
      <path d="M22 18 L15 33 L20.5 31 L24 19 Z" fill="#5A2D85" />
      <path d="M26 18 L33 33 L27.5 31 L24 19 Z" fill="#5A2D85" />
      <path d="M24 16 C15 3 2 5 3.5 16 C2 27 15 29 24 16 Z" fill="#70409B" />
      <path d="M24 16 C33 3 46 5 44.5 16 C46 27 33 29 24 16 Z" fill="#70409B" />
      <path d="M8 11 C12 8 17 10 20 14" stroke="#B69AD9" strokeWidth="1.6" fill="none" strokeLinecap="round" />
      <path d="M40 11 C36 8 31 10 28 14" stroke="#B69AD9" strokeWidth="1.6" fill="none" strokeLinecap="round" />
      <ellipse cx="24" cy="16" rx="4.6" ry="5.2" fill="#8B5CC0" />
    </svg>
  );
}

function SirAvatar({ size }: { size: number }) {
  const [missing, setMissing] = useState(false);  // without the photo file (it is optional in the repository), a butterfly stands in
  return (
    <span className="relative inline-block shrink-0" style={{ width: size, height: size }}>
      {/* framed on his face; the photo file itself is shown unaltered */}
      <span className="grid h-full w-full place-items-center overflow-hidden rounded-full bg-lilac ring-[3px] ring-royal ring-offset-2 ring-offset-white">
        {missing ? <Butterfly size={size * 0.62} motion="still" palette={1} /> : (
          <img src={SIR_PHOTO} alt="Sir, Sabrina's dog" draggable={false} className="h-full w-full object-cover" onError={() => setMissing(true)}
            style={{ objectPosition: "21% 32%", transform: "scale(1.75)", transformOrigin: "21% 32%" }} />
        )}
      </span>
      <Ribbon size={size * 0.72} />
    </span>
  );
}

/**
 * Sir's Office: the "ask SAM SPACE anything" box, always in the bottom-right corner. Named for Sir, the dog Sabrina adored.
 * It starts a real workflow, shows each agent's step live, and links to the results. Nothing is ever sent or paid.
 */
export function SirsOffice() {
  const { can } = useAuth();
  const { celebrate } = useButterflies();
  const [open, setOpen] = useState(() => sessionStorage.getItem("sirs-office-open") === "1");
  const [text, setText] = useState("");
  const [intent, setIntent] = useState<Intent | "">("");
  const [speed, setSpeed] = useState<"economy" | "auto">("economy");
  const [mode, setMode] = useState<ResearchMode>("synthetic");
  const [runId, setRunId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const detail = useRunPoll(runId);
  const working = !!detail && ACTIVE.has(detail.run.status);

  useEffect(() => { sessionStorage.setItem("sirs-office-open", open ? "1" : "0"); if (open) window.setTimeout(() => input.current?.focus(), 50); }, [open]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: globalThis.KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  if (!can("run_agents")) return null;

  async function ask(e?: FormEvent) {
    e?.preventDefault();
    if (text.trim().length < 5 || busy) return;
    setBusy(true);
    setError(null);
    celebrate("ask");
    try {
      const res = await api<{ run: RunSummary }>("/api/runs", { json: { request: text.trim(), intent: intent || null, research_mode: mode, strategy: speed } });
      setRunId(res.run.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sir couldn't start that. Please try again.");
    } finally {
      setBusy(false);
    }
  }
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } };
  const done = detail && !ACTIVE.has(detail.run.status);
  const intentDone = detail?.result?.intent ?? detail?.run.workflow_type ?? "";
  const resultLink = detail ? (RESULT_PAGE[intentDone]?.(detail.run.id) ?? `/activity/runs/${detail.run.id}`) : "";

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col items-end gap-3 sm:bottom-6 sm:right-6">
      {open && (
        <section role="dialog" aria-label="Sir's Office" className="sirs-office flex max-h-[min(78vh,720px)] w-[min(420px,calc(100vw-2rem))] flex-col overflow-hidden rounded-3xl border border-lavender/50 bg-white shadow-[0_24px_60px_-20px_rgb(59_20_88/0.55)]">
          <header className="flex items-center gap-3 bg-gradient-to-br from-royal to-plum px-4 py-3.5 text-white">
            <SirAvatar size={48} />
            <div className="min-w-0 flex-1">
              <p className="font-display text-xl font-semibold leading-tight">Sir's Office</p>
              <p className="text-xs text-lilac/90">Ask SAM SPACE anything</p>
            </div>
            <button type="button" onClick={() => setOpen(false)} className="rounded-lg p-2 text-lilac/90 transition hover:bg-white/15 hover:text-white" aria-label="Minimize Sir's Office">
              <Minus size={18} aria-hidden="true" />
            </button>
          </header>
          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            {detail ? (
              <>
                <p className="rounded-2xl bg-lilac/50 px-3 py-2 text-sm text-plum">“{detail.run.request}”</p>
                <LiveProgress detail={detail} />
                {done && (
                  <div className="flex flex-wrap gap-2">
                    {detail.run.status.startsWith("completed") && <Link to={resultLink} className="btn btn-primary !py-2 text-sm">See the results <ArrowRight size={14} aria-hidden="true" /></Link>}
                    <button type="button" className="btn btn-soft !py-2 text-sm" onClick={() => { setRunId(null); setText(""); }}>Ask something else</button>
                  </div>
                )}
              </>
            ) : (
              <form onSubmit={ask} className="space-y-3">
                <label className="sr-only" htmlFor="sir-ask">What would you like to ask?</label>
                <textarea id="sir-ask" ref={input} rows={3} className="field" value={text} onChange={(e) => setText(e.target.value)} onKeyDown={onKeyDown} maxLength={2000}
                  placeholder="e.g. Plan a 150-person spring gala in Manhattan and check whether we can afford it." />
                <details className="group rounded-2xl bg-ivory/80 px-3 py-2 text-sm">
                  <summary className="flex cursor-pointer list-none items-center justify-between font-semibold text-plum">Options
                    <ChevronDown size={14} className="transition group-open:rotate-180" aria-hidden="true" /></summary>
                  <div className="mt-2 grid grid-cols-1 gap-2">
                    <label className="text-xs font-semibold text-plum">What kind of task
                      <select className="field mt-1 !py-1.5 text-sm" value={intent} onChange={(e) => setIntent(e.target.value as Intent | "")}>
                        {INTENTS.filter((i) => !i.needs || can(i.needs)).map((i) => <option key={i.value} value={i.value}>{i.label}</option>)}
                      </select></label>
                    <label className="text-xs font-semibold text-plum">Speed
                      <select className="field mt-1 !py-1.5 text-sm" value={speed} onChange={(e) => setSpeed(e.target.value as "economy" | "auto")}>
                        <option value="economy">Faster</option><option value="auto">Most thorough</option>
                      </select></label>
                    <label className="text-xs font-semibold text-plum">Research
                      <select className="field mt-1 !py-1.5 text-sm" value={mode} onChange={(e) => setMode(e.target.value as ResearchMode)}>
                        <option value="synthetic">Practice data (free)</option><option value="live">Live web research</option>
                      </select></label>
                  </div>
                </details>
                {error && <p role="alert" className="rounded-xl bg-[#fbeef3] px-3 py-2 text-sm text-danger">{error}</p>}
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[0.7rem] text-muted">Enter to ask · Shift+Enter for a new line. Nothing is ever sent or paid.</p>
                  <button type="submit" className="btn btn-primary !py-2" disabled={busy || text.trim().length < 5}>
                    <Send size={15} aria-hidden="true" /> {busy ? "Asking…" : "Ask"}
                  </button>
                </div>
              </form>
            )}
          </div>
        </section>
      )}
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-label={open ? "Minimize Sir's Office" : "Open Sir's Office: ask SAM SPACE anything"}
        className="group flex items-center gap-3 rounded-full bg-white py-2 pl-4 pr-2 shadow-[0_14px_36px_-12px_rgb(59_20_88/0.55)] ring-1 ring-lavender/60 transition hover:-translate-y-0.5 hover:ring-royal">
        <span className="hidden text-left sm:block">
          <span className="block font-display text-base font-semibold leading-tight text-plum">Sir's Office</span>
          <span className="block text-[0.7rem] text-muted">{working ? "Working on it…" : "Ask SAM SPACE anything"}</span>
        </span>
        <span className="relative">
          <SirAvatar size={52} />
          {working && <span className="absolute -bottom-0.5 -left-0.5 h-3.5 w-3.5 animate-pulse rounded-full bg-rose ring-2 ring-white" aria-hidden="true" />}
        </span>
      </button>
    </div>
  );
}
