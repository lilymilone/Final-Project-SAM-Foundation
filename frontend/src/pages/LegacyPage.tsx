import { MessageSquareHeart, Plus, Sprout, Star, X } from "lucide-react";
import { useCallback, useRef, useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { HistoricalEvent, HistoryStats, Reflection } from "../api/types";
import { formatDate, usd, useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { useButterflies } from "../butterflies/ButterflyProvider";
import { AgentPanel } from "../components/AgentPanel";
import { LessonsPanel } from "../components/outputs";
import { RunLauncher } from "../components/RunLauncher";
import { Card, DemoBadge, EmptyState, ErrorState, LoadingState, PageHeader, StatTile, Toast } from "../components/ui";

type Data = { events: HistoricalEvent[]; stats: HistoryStats };
const EMPTY_EVENT = { name: "", event_date: "", location: "", event_type: "fundraiser", attendance: "", funds_raised_usd: "", total_cost_usd: "", summary: "" };
const num = (v: string) => (v.trim() === "" ? null : Number(v));

function ReflectionForm({ eventId, onSaved }: { eventId: number; onSaved: (r: Reflection, anchor: Element | null) => void }) {
  const [form, setForm] = useState({ went_well: "", challenges: "", do_differently: "", rating: "" });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function save(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const res = await api<{ reflection: Reflection }>(`/api/legacy/events/${eventId}/reflections`, {
        json: { ...form, rating: num(form.rating) },
      });
      onSaved(res.reflection, buttonRef.current);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={save} className="mt-3 grid gap-3 rounded-2xl bg-white/80 p-4 ring-1 ring-lavender/40 sm:grid-cols-3">
      <div><label className="label" htmlFor={`ww-${eventId}`}>What went well</label><textarea id={`ww-${eventId}`} rows={2} className="field" value={form.went_well} onChange={set("went_well")} /></div>
      <div><label className="label" htmlFor={`ch-${eventId}`}>Challenges</label><textarea id={`ch-${eventId}`} rows={2} className="field" value={form.challenges} onChange={set("challenges")} /></div>
      <div><label className="label" htmlFor={`dd-${eventId}`}>Do differently</label><textarea id={`dd-${eventId}`} rows={2} className="field" value={form.do_differently} onChange={set("do_differently")} /></div>
      <div className="flex flex-wrap items-end justify-between gap-3 sm:col-span-3">
        <div>
          <label className="label" htmlFor={`rt-${eventId}`}>Overall rating</label>
          <select id={`rt-${eventId}`} className="field !w-36" value={form.rating} onChange={set("rating")}>
            <option value="">No rating</option>
            {[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{"★".repeat(n)}</option>)}
          </select>
        </div>
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
        <button ref={buttonRef} className="btn btn-primary" disabled={saving}>{saving ? "Saving…" : "Save reflection"}</button>
      </div>
    </form>
  );
}

export default function LegacyPage() {
  const { can } = useAuth();
  const { celebrate } = useButterflies();
  const { data, error, loading, reload } = useApi<Data>("/api/legacy/events");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_EVENT);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [reflectingOn, setReflectingOn] = useState<number | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const saveRef = useRef<HTMLButtonElement>(null);
  const headerRef = useRef<HTMLDivElement>(null);
  const clearToast = useCallback(() => setToast(null), []);
  const set = (k: keyof typeof EMPTY_EVENT) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function saveEvent(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      const res = await api<{ event: HistoricalEvent; milestone: string | null }>("/api/legacy/events", {
        json: {
          ...form,
          event_date: form.event_date || null,
          attendance: num(form.attendance),
          funds_raised_usd: num(form.funds_raised_usd),
          total_cost_usd: num(form.total_cost_usd),
        },
      });
      celebrate("reflection", saveRef.current);
      if (res.milestone) {
        window.setTimeout(() => celebrate("milestone", headerRef.current), 600);
        setToast(`Milestone: ${res.milestone}`);
      } else {
        setToast(`“${res.event.name}” is preserved in Our Legacy`);
      }
      setForm(EMPTY_EVENT);
      setOpen(false);
      reload();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div ref={headerRef}>
        <PageHeader
          eyebrow="Our Legacy"
          title="Every event teaches us something"
          subtitle="Preserve what happened, what it cost, and what the board learned, so the next fundraiser starts wiser."
          actions={can("manage_events") && !open && (
            <button className="btn btn-primary" onClick={() => setOpen(true)}><Plus size={16} aria-hidden="true" /> Record a past event</button>
          )}
        />
      </div>

      {data && (
        <div className="mb-5 grid gap-3 sm:grid-cols-4 animate-fade-up">
          <StatTile label="Events" value={data.stats.events_recorded} demo={data.stats.is_demo} />
          <StatTile label="Raised" value={usd(data.stats.total_raised_usd)} />
          <StatTile label="Net after costs" value={usd(data.stats.total_net_usd)} />
          <StatTile label="Highest net" value={data.stats.highest_net_event ? usd(data.stats.highest_net_event.net_usd) : "—"} hint={data.stats.highest_net_event?.name} />
        </div>
      )}

      {open && (
        <Card title="Record a past event" icon={<Sprout size={16} aria-hidden="true" />} className="mb-5"
          action={<button className="btn btn-ghost !p-2" onClick={() => setOpen(false)} aria-label="Close form"><X size={16} aria-hidden="true" /></button>}>
          <form onSubmit={saveEvent} className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2"><label className="label" htmlFor="h-name">Event name *</label><input id="h-name" className="field" value={form.name} onChange={set("name")} required maxLength={200} /></div>
            <div><label className="label" htmlFor="h-date">Date</label><input id="h-date" type="date" className="field" value={form.event_date} onChange={set("event_date")} /></div>
            <div><label className="label" htmlFor="h-loc">Location</label><input id="h-loc" className="field" value={form.location} onChange={set("location")} maxLength={200} /></div>
            <div><label className="label" htmlFor="h-att">Attendance</label><input id="h-att" type="number" min={0} className="field" value={form.attendance} onChange={set("attendance")} /></div>
            <div><label className="label" htmlFor="h-type">Type</label><input id="h-type" className="field" value={form.event_type} onChange={set("event_type")} maxLength={60} /></div>
            <div><label className="label" htmlFor="h-raised">Funds raised (USD)</label><input id="h-raised" type="number" min={0} className="field" value={form.funds_raised_usd} onChange={set("funds_raised_usd")} /></div>
            <div><label className="label" htmlFor="h-cost">Total cost (USD)</label><input id="h-cost" type="number" min={0} className="field" value={form.total_cost_usd} onChange={set("total_cost_usd")} /></div>
            <div className="sm:col-span-2"><label className="label" htmlFor="h-sum">What happened</label><textarea id="h-sum" rows={3} className="field" value={form.summary} onChange={set("summary")} maxLength={4000} /></div>
            {formError && <p role="alert" className="text-sm text-danger sm:col-span-2">{formError}</p>}
            <div className="flex justify-end gap-2 sm:col-span-2">
              <button type="button" className="btn btn-ghost" onClick={() => setOpen(false)}>Cancel</button>
              <button ref={saveRef} className="btn btn-primary" disabled={saving || form.name.trim().length < 2}>{saving ? "Saving…" : "Save to Our Legacy"}</button>
            </div>
          </form>
        </Card>
      )}

      <div className="grid gap-5 lg:grid-cols-[1.5fr_1fr]">
        <div className="space-y-5">
          {loading && <LoadingState rows={3} />}
          {error && <ErrorState message={error.message} onRetry={reload} />}
          {data && data.events.length === 0 && <Card><EmptyState title="No past events yet">Record your first event to begin the foundation's memory.</EmptyState></Card>}
          {data?.events.map((ev) => (
            <Card key={ev.id}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="text-sm text-muted">{formatDate(ev.event_date)} · {ev.location || "Location not recorded"}</p>
                  <h2 className="font-display text-2xl font-semibold text-plum">{ev.name}</h2>
                </div>
                {ev.is_demo && <DemoBadge />}
              </div>
              {ev.summary && <p className="mt-2 text-sm text-ink/85">{ev.summary}</p>}
              <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm">
                <span className="text-muted">Attendance <b className="text-plum">{ev.attendance ?? "—"}</b></span>
                <span className="text-muted">Raised <b className="text-plum">{usd(ev.funds_raised_usd)}</b></span>
                <span className="text-muted">Cost <b className="text-plum">{usd(ev.total_cost_usd)}</b></span>
                <span className="text-muted">Net <b className="text-plum">{usd(ev.net_usd)}</b></span>
              </div>

              <div className="mt-4 border-t border-lavender/30 pt-3">
                <div className="flex items-center justify-between">
                  <p className="flex items-center gap-2 text-sm font-semibold text-plum"><MessageSquareHeart size={15} aria-hidden="true" /> Board reflections ({ev.reflections.length})</p>
                  {can("write_reflections") && (
                    <button className="btn btn-ghost !py-1 text-sm" onClick={() => setReflectingOn(reflectingOn === ev.id ? null : ev.id)}>
                      {reflectingOn === ev.id ? "Close" : "Add reflection"}
                    </button>
                  )}
                </div>
                <ul className="mt-2 space-y-2">
                  {ev.reflections.map((r) => (
                    <li key={r.id} className="rounded-xl bg-ivory/80 px-3.5 py-2.5 text-sm">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-plum">{r.author}</span>
                        {r.rating && <span className="inline-flex items-center gap-0.5 text-rose" aria-label={`${r.rating} of 5`}>{Array.from({ length: r.rating }).map((_, i) => <Star key={i} size={12} fill="currentColor" aria-hidden="true" />)}</span>}
                      </div>
                      {r.went_well && <p><span className="text-sage">Went well:</span> {r.went_well}</p>}
                      {r.challenges && <p><span className="text-amber">Challenge:</span> {r.challenges}</p>}
                      {r.do_differently && <p><span className="text-royal">Next time:</span> {r.do_differently}</p>}
                    </li>
                  ))}
                </ul>
                {reflectingOn === ev.id && (
                  <ReflectionForm
                    eventId={ev.id}
                    onSaved={(_, anchor) => {
                      celebrate("reflection", anchor);
                      setToast("Reflection saved. Thank you for sharing it.");
                      setReflectingOn(null);
                      reload();
                    }}
                  />
                )}
              </div>
            </Card>
          ))}
        </div>
        <div className="space-y-5">
          <RunLauncher title="Learn from our history" intent="event_learning" lockIntent
            examples={["What lessons can we learn from our previous events?", "Where do board members disagree about our past fundraisers?"]} />
          <LessonsPanel />
          <AgentPanel agents={["event_intelligence"]} upcoming={[]} />
        </div>
      </div>
      {toast && <Toast message={toast} onDone={clearToast} />}
    </>
  );
}
