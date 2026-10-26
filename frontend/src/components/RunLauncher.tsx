import { Sparkles, Wand2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { EventPlan, Intent, ResearchMode, RunSummary } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Card } from "./ui";

const INTENTS: { value: Intent | ""; label: string; needs?: string }[] = [
  { value: "", label: "Auto-detect (Orchestrator decides)" },
  { value: "plan_event", label: "Plan a fundraising event" },
  { value: "mission_discovery", label: "Discover mission-aligned opportunities" },
  { value: "partnership_outreach", label: "Find partners and draft outreach" },
  { value: "event_learning", label: "Learn from past events" },
  { value: "financial_review", label: "Review finances", needs: "view_financials" },
  { value: "donations_review", label: "Review donations & acknowledgments", needs: "view_donor_data" },
];

type Props = {
  title?: string;
  intent?: Intent | "";
  request?: string;
  mode?: ResearchMode;
  examples?: string[];
  eventPlans?: EventPlan[];
  eventPlanId?: number | null;
  lockIntent?: boolean;
  submitLabel?: string;
  placeholder?: string;
  /** Stay on the page and hand the new run to the caller (for an inline progress view) instead of opening its trace. */
  onStarted?: (runId: number) => void;
};

export function RunLauncher({ title = "Ask the agents", intent = "", request = "", mode = "synthetic", examples = [], eventPlans, eventPlanId = null, lockIntent,
  submitLabel = "Run the agents", placeholder, onStarted }: Props) {
  const { can } = useAuth();
  const navigate = useNavigate();
  const [text, setText] = useState(request);
  const [chosenIntent, setChosenIntent] = useState<Intent | "">(intent);
  const [researchMode, setResearchMode] = useState<ResearchMode>(mode);
  const [planId, setPlanId] = useState<number | null>(eventPlanId);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => setPlanId(eventPlanId), [eventPlanId]);

  if (!can("run_agents")) return null;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api<{ run: RunSummary }>("/api/runs", {
        json: { request: text, intent: chosenIntent || null, research_mode: researchMode, event_plan_id: planId },
      });
      if (onStarted) { onStarted(res.run.id); setBusy(false); }
      else navigate(`/activity/runs/${res.run.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the workflow.");
      setBusy(false);
    }
  }

  return (
    <Card title={title} icon={<Wand2 size={16} aria-hidden="true" />}>
      <form onSubmit={submit} className="@container space-y-3">
        <label className="sr-only" htmlFor="run-request">What should the agents do?</label>
        <textarea id="run-request" rows={3} className="field" value={text} onChange={(e) => setText(e.target.value)} maxLength={2000}
          placeholder={placeholder ?? "e.g. Plan a 150-person Manhattan fundraising gala using lessons from our past events, and check whether we can afford it."} />
        {examples.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {examples.map((ex) => (
              <button key={ex} type="button" onClick={() => setText(ex)}
                className="rounded-full border border-lavender/50 bg-white px-3 py-1 text-left text-xs text-plum transition hover:border-royal hover:bg-lilac/50">
                <Sparkles size={11} className="mr-1 inline text-rose" aria-hidden="true" />{ex}
              </button>
            ))}
          </div>
        )}
        <div className="grid grid-cols-1 gap-3 @lg:grid-cols-2">
          {!lockIntent && (
            <div>
              <label className="label" htmlFor="run-intent">Workflow</label>
              <select id="run-intent" className="field" value={chosenIntent} onChange={(e) => setChosenIntent(e.target.value as Intent | "")}>
                {INTENTS.filter((i) => !i.needs || can(i.needs)).map((i) => <option key={i.value} value={i.value}>{i.label}</option>)}
              </select>
            </div>
          )}
          {eventPlans && eventPlans.length > 0 && (chosenIntent === "plan_event" || chosenIntent === "") && (
            <div>
              <label className="label" htmlFor="run-plan">Event plan (budget limit, date)</label>
              <select id="run-plan" className="field" value={planId ?? ""} onChange={(e) => setPlanId(e.target.value ? Number(e.target.value) : null)}>
                <option value="">Create a new plan from my request</option>
                {eventPlans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
          )}
        </div>
        <fieldset>
          <legend className="label">Research source</legend>
          <div className="grid grid-cols-1 gap-2 @sm:grid-cols-2">
            {([
              ["synthetic", "Synthetic demo data", "Labeled practice fixtures: free of web costs, same result every time."],
              ["live", "Live web research", "Real web search; every link is fetched to verify it. About 1¢ per search."],
            ] as const).map(([value, label, hint]) => (
              <label key={value} className={`cursor-pointer rounded-2xl border p-3 text-sm transition ${researchMode === value ? "border-royal bg-lilac/60" : "border-lavender/40 bg-white/70 hover:border-lavender"}`}>
                <input type="radio" name="research-mode" value={value} checked={researchMode === value} onChange={() => setResearchMode(value)} className="sr-only" />
                <span className="block font-semibold text-plum">{label}</span>
                <span className="block text-xs text-muted">{hint}</span>
              </label>
            ))}
          </div>
        </fieldset>
        {error && <p role="alert" className="rounded-xl bg-[#fbeef3] px-3 py-2 text-sm text-danger">{error}</p>}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-muted">Nothing is ever sent, booked, or paid.</p>
          <button type="submit" className="btn btn-primary" disabled={busy || text.trim().length < 5}>
            {busy ? "Starting…" : submitLabel}
          </button>
        </div>
      </form>
    </Card>
  );
}
