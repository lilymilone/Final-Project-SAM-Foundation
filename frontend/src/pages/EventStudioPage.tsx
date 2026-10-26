import { ArrowRight, CalendarHeart, FileText, FlaskConical, Gem, Globe2, History, MapPin, Sparkles, Users, Wand2, Zap } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { EventPlan, ResearchMode, RunDetail, RunSummary } from "../api/types";
import { formatDate, usd, useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { useButterflies } from "../butterflies/ButterflyProvider";
import { StatusPill } from "../components/agents";
import { VenueCandidates } from "../components/outputs";
import { LiveProgress } from "../components/progress";
import { Card, DemoBadge, EmptyState, ErrorState, LoadingState, PageHeader } from "../components/ui";

type Form = {
  name: string; event_type: string; event_format: string; city: string; target_date: string; date_end: string; expected_attendance: string;
  ticket_price_usd: string; fundraising_goal_usd: string; budget_limit_usd: string; instructions: string;
};
const EMPTY: Form = { name: "", event_type: "gala", event_format: "", city: "", target_date: "", date_end: "", expected_attendance: "",
  ticket_price_usd: "", fundraising_goal_usd: "", budget_limit_usd: "", instructions: "" };
const DEFAULT_CASE: Form = {
  name: "Smile Like Sab Spring Gala", event_type: "gala", event_format: "", city: "Manhattan, New York, NY", target_date: "2027-04-17",
  date_end: "2027-04-24", expected_attendance: "150", ticket_price_usd: "250", fundraising_goal_usd: "40000", budget_limit_usd: "18000",
  instructions: "A warm, personal evening honoring Sabrina, with a short talk from a recovery speaker. Wheelchair accessible.",
};
const TYPES = ["gala", "dinner", "reception", "community walk", "panel", "concert", "auction", "other"];
const num = (v: string) => (v.trim() === "" ? null : Number(v));

function fromPlan(p: EventPlan): Form {
  const s = (v: unknown) => (v == null ? "" : String(v));
  return { name: p.name, event_type: p.event_type || "gala", event_format: s(p.event_format), city: p.city, target_date: s(p.target_date),
    date_end: s(p.date_end), expected_attendance: s(p.expected_attendance), ticket_price_usd: s(p.ticket_price_usd),
    fundraising_goal_usd: s(p.fundraising_goal_usd), budget_limit_usd: s(p.budget_limit_usd), instructions: s(p.instructions) };
}

function requestText(f: Form): string {
  const when = f.target_date ? (f.date_end ? ` between ${f.target_date} and ${f.date_end}` : ` on ${f.target_date}`) : "";
  return `Plan a ${f.expected_attendance || "?"}-person fundraising ${f.event_type} in ${f.city || "Manhattan"}${when} for the Sabrina Audrey Milone Foundation, `
    + `called "${f.name}". Ticket price ${f.ticket_price_usd ? "$" + f.ticket_price_usd : "not set"}, fundraising target `
    + `${f.fundraising_goal_usd ? "$" + f.fundraising_goal_usd : "not set"}, maximum planning budget ${f.budget_limit_usd ? "$" + f.budget_limit_usd : "not set"}. `
    + `Use lessons from previous fundraisers and check whether we can afford it.${f.instructions ? " " + f.instructions : ""}`;
}

function PlanStrategies({ plan }: { plan: EventPlan }) {
  const { data } = useApi<{ strategies: { run_id: number; status: string; research_mode: string; started_at: string; headline: string | null; spent_usd: number }[] }>(`/api/events/${plan.id}/strategies`);
  if (!data || data.strategies.length === 0) return <p className="text-xs text-muted">No strategies generated yet.</p>;
  return (
    <ul className="mt-2 space-y-1.5">{data.strategies.slice(0, 4).map((s) => (
      <li key={s.run_id}><Link to={`/events/packets/${s.run_id}`} className="flex items-center justify-between gap-2 rounded-xl bg-white/80 px-3 py-2 text-sm ring-1 ring-lavender/30 hover:bg-lilac/50">
        <span className="min-w-0"><span className="flex items-center gap-1.5 font-semibold text-plum"><FileText size={13} aria-hidden="true" /> Packet #{s.run_id}
          <span className="text-xs font-normal text-muted">· {formatDate(s.started_at)} · {s.research_mode} · ${s.spent_usd.toFixed(3)}</span></span>
          {s.headline && <span className="block truncate text-xs text-muted">{s.headline}</span>}</span>
        <StatusPill status={s.status} />
      </Link></li>))}</ul>
  );
}

export default function EventStudioPage() {
  const { can } = useAuth();
  const { celebrate } = useButterflies();
  const plans = useApi<{ events: EventPlan[] }>("/api/events");
  const [planId, setPlanId] = useState<number | null>(null);
  const [form, setForm] = useState<Form>(DEFAULT_CASE);
  const [mode, setMode] = useState<ResearchMode>("live");
  const [useHistory, setUseHistory] = useState(true);
  const [speed, setSpeed] = useState<"economy" | "auto">("economy");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [run, setRun] = useState<RunDetail | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [params] = useSearchParams();
  // /events?plan=7 (from the dashboard) opens that saved plan in the form.
  useEffect(() => {
    const wanted = Number(params.get("plan"));
    const p = wanted ? plans.data?.events.find((x) => x.id === wanted) : undefined;
    if (p) { setPlanId(p.id); setForm(fromPlan(p)); }
  }, [params, plans.data]);
  const set = (k: keyof Form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const poll = useCallback(async (id: number) => {
    const d = await api<RunDetail>(`/api/runs/${id}`).catch(() => null);
    if (!d) return;
    setRun(d);
    if (["queued", "running"].includes(d.run.status)) window.setTimeout(() => poll(id), 1500);
    else {
      setBusy(false);
      plans.reload();
      if (d.run.status.startsWith("completed")) celebrate("workflow", panelRef.current);
    }
  }, [celebrate, plans]);

  async function generate(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    setRun(null);
    const body = {
      name: form.name.trim(), event_type: form.event_type, event_format: form.event_format || null, city: form.city.trim(),
      target_date: form.target_date || null, date_end: form.date_end || null, expected_attendance: num(form.expected_attendance),
      ticket_price_usd: num(form.ticket_price_usd), fundraising_goal_usd: num(form.fundraising_goal_usd), budget_limit_usd: num(form.budget_limit_usd),
      instructions: form.instructions.trim() || null, status: "planning", notes: "",
    };
    try {
      const targetId = planId ?? plans.data?.events.find((p) => p.name.trim() === body.name)?.id ?? null;  // reuse a plan with the same name
      const saved = targetId
        ? await api<{ event: EventPlan }>(`/api/events/${targetId}`, { method: "PUT", json: body })
        : await api<{ event: EventPlan }>("/api/events", { json: body });
      setPlanId(saved.event.id);
      const res = await api<{ run: RunSummary }>("/api/runs", {
        json: { request: requestText(form), intent: "plan_event", event_plan_id: saved.event.id, research_mode: mode, use_history: useHistory, interpret: true,
                strategy: speed },
      });
      poll(res.run.id);
      window.setTimeout(() => panelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 400);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the strategy.");
      setBusy(false);
    }
  }

  const done = run && !["queued", "running"].includes(run.run.status);
  const field = (k: keyof Form, label: string, props: Record<string, unknown> = {}) => (
    <div><label className="label" htmlFor={`es-${k}`}>{label}</label>
      <input id={`es-${k}`} className="field" value={form[k]} onChange={set(k)} {...props} /></div>
  );

  return (
    <>
      <PageHeader eyebrow="Event Studio" title="Plan an event"
        subtitle="Enter the details. The agents research venues, check the budget and past lessons, revise if needed, and draft venue inquiries for your review." />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <Card title="Event details" icon={<CalendarHeart size={16} aria-hidden="true" />}
          action={<button type="button" className="btn btn-ghost !py-1 text-sm" onClick={() => { setPlanId(null); setForm(DEFAULT_CASE); }}>
            <Sparkles size={13} aria-hidden="true" /> Load an example</button>}>
          {plans.data && plans.data.events.length > 0 && (
            <div className="mb-4">
              <label className="label" htmlFor="es-plan">Start from a saved plan (optional)</label>
              <select id="es-plan" className="field" value={planId ?? ""} onChange={(e) => {
                const p = plans.data!.events.find((x) => x.id === Number(e.target.value));
                setPlanId(p ? p.id : null);
                setForm(p ? fromPlan(p) : EMPTY);
              }}>
                <option value="">New fundraiser</option>
                {plans.data.events.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
          )}
          <form onSubmit={generate} className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <p className="sm:col-span-2 -mb-1 mt-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-royal"><span className="grid h-5 w-5 place-items-center rounded-full bg-lilac text-[0.7rem]">1</span>The event</p>
              <div className="sm:col-span-2">{field("name", "Fundraiser name *", { required: true, maxLength: 200 })}</div>
              <div><label className="label" htmlFor="es-type">Event type</label>
                <select id="es-type" className="field" value={form.event_type} onChange={set("event_type")}>{TYPES.map((t) => <option key={t}>{t}</option>)}</select></div>
              <div><label className="label" htmlFor="es-format">Format</label>
                <select id="es-format" className="field" value={form.event_format} onChange={set("event_format")}>
                  <option value="">Let the agents decide from the type</option><option value="seated_dinner">Seated dinner</option><option value="reception">Standing reception</option>
                </select></div>
              <div className="sm:col-span-2">{field("city", "Location *", { required: true, placeholder: "Manhattan, New York, NY" })}</div>
              {field("target_date", "Date (or start of range)", { type: "date" })}
              {field("date_end", "End of date range (optional)", { type: "date" })}
              {field("expected_attendance", "Expected attendees *", { type: "number", min: 1, max: 5000, required: true })}
              <div className="hidden sm:block" />
              <p className="sm:col-span-2 -mb-1 mt-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-royal"><span className="grid h-5 w-5 place-items-center rounded-full bg-lilac text-[0.7rem]">2</span>Money</p>
              {field("ticket_price_usd", "Ticket price (USD)", { type: "number", min: 0 })}
              {field("fundraising_goal_usd", "Fundraising target (USD)", { type: "number", min: 0 })}
              {field("budget_limit_usd", "Maximum planning budget (USD)", { type: "number", min: 0 })}
              <div className="hidden sm:block" />
              <div className="sm:col-span-2"><label className="label" htmlFor="es-instr">Additional instructions</label>
                <textarea id="es-instr" rows={3} className="field" value={form.instructions} onChange={set("instructions")} maxLength={2000}
                  placeholder="Accessibility needs, tone, program, anything the agents should respect" /></div>
            </div>
            <p className="sm:col-span-2 -mb-1 mt-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-royal"><span className="grid h-5 w-5 place-items-center rounded-full bg-lilac text-[0.7rem]">3</span>How the agents should work</p>
            <fieldset className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <legend className="label">Venue research</legend>
              {([["live", Globe2, "Live web research", "Real venues. Websites are fetched and prices are checked against the page, otherwise \"Quote required.\""],
                 ["synthetic", FlaskConical, "Practice venues", "Demo Manhattan venues, clearly labeled. Good for trying it out."]] as const).map(([v, Icon, label, hint]) => (
                <label key={v} className={`cursor-pointer rounded-2xl border p-3 text-sm transition ${mode === v ? "border-royal bg-lilac/60" : "border-lavender/40 bg-white/70 hover:border-lavender"}`}>
                  <input type="radio" name="es-mode" className="sr-only" checked={mode === v} onChange={() => setMode(v)} />
                  <span className="flex items-center gap-1.5 font-semibold text-plum"><Icon size={14} aria-hidden="true" /> {label}</span>
                  <span className="block text-xs text-muted">{hint}</span>
                </label>
              ))}
            </fieldset>
            <fieldset className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <legend className="label">Speed</legend>
              {([["economy", Zap, "Faster", "About 2 minutes. Mostly the fast model; lowest cost."],
                 ["auto", Gem, "Most thorough", "About 3–4 minutes. Stronger models for strategy and the final recommendation."]] as const).map(([v, Icon, label, hint]) => (
                <label key={v} className={`cursor-pointer rounded-2xl border p-3 text-sm transition ${speed === v ? "border-royal bg-lilac/60" : "border-lavender/40 bg-white/70 hover:border-lavender"}`}>
                  <input type="radio" name="es-speed" className="sr-only" checked={speed === v} onChange={() => setSpeed(v)} />
                  <span className="flex items-center gap-1.5 font-semibold text-plum"><Icon size={14} aria-hidden="true" /> {label}</span>
                  <span className="block text-xs text-muted">{hint}</span>
                </label>
              ))}
            </fieldset>
            <label className="flex items-center gap-2 text-sm text-plum">
              <input type="checkbox" checked={useHistory} onChange={(e) => setUseHistory(e.target.checked)} />
              <History size={14} aria-hidden="true" /> Use lessons from past events (Event Intelligence)
            </label>
            {error && <p role="alert" className="rounded-xl bg-[#fbeef3] px-3 py-2 text-sm text-danger">{error}</p>}
            {can("run_agents") && can("manage_events") ? (
              <button type="submit" disabled={busy || !form.name.trim() || !form.city.trim() || !form.expected_attendance}
                className="btn btn-primary w-full !py-3.5 text-base shadow-[0_14px_30px_-12px_rgb(112_64_155/0.9)]">
                <Wand2 size={18} aria-hidden="true" /> {busy ? "Agents at work…" : "Generate Event Plan"}
              </button>
            ) : <p className="text-sm text-muted">Your board role can view strategies but not generate them.</p>}
            <p className="text-center text-xs text-muted">Nothing is booked, paid, or sent.</p>
          </form>
        </Card>

        <div className="space-y-6" ref={panelRef}>
          {run && (
            <Card title={done ? (run.run.status.startsWith("completed") ? "Event plan ready" : "Planning stopped") : "The agents are working"} icon={<Sparkles size={16} aria-hidden="true" />}>
              {done && run.result?.recommendation && (
                <div className="mb-3 rounded-2xl bg-ivory/80 p-3">
                  <p className="font-semibold text-plum">{run.result.recommendation.headline}</p>
                  <p className="mt-1 text-xs text-muted">
                    {(run.result.shortlist ?? []).length} venue{(run.result.shortlist ?? []).length === 1 ? "" : "s"} shortlisted
                    {run.result.finance?.verdict ? ` · finance: ${run.result.finance.verdict.replace(/_/g, " ")}` : ""}
                    {` · ${(run.result.drafts ?? []).length} venue inquir${(run.result.drafts ?? []).length === 1 ? "y" : "ies"} drafted`}
                    {(run.result.revision_history ?? []).length > 1 ? ` · revised ${(run.result.revision_history ?? []).length - 1} time(s)` : ""}
                  </p>
                </div>
              )}
              {done && run.run.status.startsWith("completed") && (
                <div className="mb-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <Link to={`/events/packets/${run.run.id}`} className="btn btn-primary">Open the event plan <ArrowRight size={16} aria-hidden="true" /></Link>
                  <Link to="/partnerships#drafts" className="btn btn-soft">Review venue inquiries</Link>
                </div>
              )}
              <LiveProgress detail={run} />
            </Card>
          )}
          <Card title="Your fundraisers" icon={<CalendarHeart size={16} aria-hidden="true" />}>
            {plans.loading && <LoadingState rows={2} />}
            {plans.error && <ErrorState message={plans.error.message} onRetry={plans.reload} />}
            {plans.data && (plans.data.events.length === 0 ? <EmptyState title="No fundraisers yet">Fill in the form to generate your first strategy.</EmptyState> : (
              <ul className="space-y-3">{plans.data.events.map((p) => (
                <li key={p.id} className="rounded-2xl border border-lavender/30 bg-ivory/60 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="font-display text-lg font-semibold text-plum">{p.name}</p>
                      <p className="flex flex-wrap items-center gap-x-3 text-xs text-muted">
                        <span>{formatDate(p.target_date)}</span><span className="inline-flex items-center gap-1"><MapPin size={11} aria-hidden="true" />{p.city || "City TBD"}</span>
                        {p.expected_attendance != null && <span className="inline-flex items-center gap-1"><Users size={11} aria-hidden="true" />{p.expected_attendance}</span>}
                        <span>budget {usd(p.budget_limit_usd)}</span>
                      </p>
                    </div>
                    {p.is_demo && <DemoBadge label="Demo" />}
                  </div>
                  <PlanStrategies plan={p} />
                  <details className="mt-2"><summary className="cursor-pointer text-xs font-semibold text-royal">Venue candidates</summary><VenueCandidates eventId={p.id} /></details>
                </li>))}</ul>
            ))}
          </Card>
        </div>
      </div>
    </>
  );
}
