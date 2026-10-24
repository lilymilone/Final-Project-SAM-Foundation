import { CalendarHeart, MapPin, Plus, Users, X } from "lucide-react";
import { useCallback, useRef, useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { EventPlan } from "../api/types";
import { formatDate, usd, useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { useButterflies } from "../butterflies/ButterflyProvider";
import { AgentPanel } from "../components/AgentPanel";
import { Card, DemoBadge, EmptyState, ErrorState, LoadingState, PageHeader, Toast } from "../components/ui";

const EMPTY = {
  name: "", event_type: "fundraiser", city: "", target_date: "", expected_attendance: "",
  fundraising_goal_usd: "", budget_limit_usd: "", status: "idea", notes: "",
};

const num = (v: string) => (v.trim() === "" ? null : Number(v));

export default function EventStudioPage() {
  const { can } = useAuth();
  const { celebrate } = useButterflies();
  const { data, error, loading, reload } = useApi<{ events: EventPlan[] }>("/api/events");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<number | null>(null);
  const saveRef = useRef<HTMLButtonElement>(null);
  const clearToast = useCallback(() => setToast(null), []);
  const set = (k: keyof typeof EMPTY) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      const res = await api<{ event: EventPlan }>("/api/events", {
        json: {
          ...form,
          target_date: form.target_date || null,
          expected_attendance: num(form.expected_attendance),
          fundraising_goal_usd: num(form.fundraising_goal_usd),
          budget_limit_usd: num(form.budget_limit_usd),
        },
      });
      celebrate("save", saveRef.current);
      setToast(`Saved “${res.event.name}” to Event Studio`);
      setHighlight(res.event.id);
      setForm(EMPTY);
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
      <PageHeader
        eyebrow="Event Studio"
        title="Plan fundraisers with care"
        subtitle="Capture the idea, the budget, and the goal. The agents will research venues, check affordability, and draft outreach for your review."
        actions={can("manage_events") && !open && (
          <button className="btn btn-primary" onClick={() => setOpen(true)}><Plus size={16} aria-hidden="true" /> New event plan</button>
        )}
      />

      {open && (
        <Card title="New event plan" icon={<CalendarHeart size={16} aria-hidden="true" />} className="mb-5"
          action={<button className="btn btn-ghost !p-2" onClick={() => setOpen(false)} aria-label="Close form"><X size={16} aria-hidden="true" /></button>}>
          <form onSubmit={onSave} className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="label" htmlFor="ev-name">Event name *</label>
              <input id="ev-name" className="field" value={form.name} onChange={set("name")} placeholder="e.g. Butterfly Garden Brunch" required maxLength={200} />
            </div>
            <div>
              <label className="label" htmlFor="ev-type">Type</label>
              <select id="ev-type" className="field" value={form.event_type} onChange={set("event_type")}>
                {["fundraiser", "gala", "community walk", "dinner", "panel", "concert", "auction"].map((t) => <option key={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="ev-city">City</label>
              <input id="ev-city" className="field" value={form.city} onChange={set("city")} placeholder="New York, NY" maxLength={120} />
            </div>
            <div>
              <label className="label" htmlFor="ev-date">Target date</label>
              <input id="ev-date" type="date" className="field" value={form.target_date} onChange={set("target_date")} />
            </div>
            <div>
              <label className="label" htmlFor="ev-att">Expected attendance</label>
              <input id="ev-att" type="number" min={0} className="field" value={form.expected_attendance} onChange={set("expected_attendance")} />
            </div>
            <div>
              <label className="label" htmlFor="ev-goal">Fundraising goal (USD)</label>
              <input id="ev-goal" type="number" min={0} className="field" value={form.fundraising_goal_usd} onChange={set("fundraising_goal_usd")} />
            </div>
            <div>
              <label className="label" htmlFor="ev-budget">Budget limit (USD)</label>
              <input id="ev-budget" type="number" min={0} className="field" value={form.budget_limit_usd} onChange={set("budget_limit_usd")} />
            </div>
            <div className="sm:col-span-2">
              <label className="label" htmlFor="ev-notes">Notes for the board</label>
              <textarea id="ev-notes" rows={3} className="field" value={form.notes} onChange={set("notes")} maxLength={4000}
                placeholder="What should this evening feel like? Any constraints?" />
            </div>
            {formError && <p role="alert" className="text-sm text-danger sm:col-span-2">{formError}</p>}
            <div className="flex justify-end gap-2 sm:col-span-2">
              <button type="button" className="btn btn-ghost" onClick={() => setOpen(false)}>Cancel</button>
              <button ref={saveRef} type="submit" className="btn btn-primary" disabled={saving || form.name.trim().length < 2}>
                {saving ? "Saving…" : "Save event plan"}
              </button>
            </div>
          </form>
        </Card>
      )}

      <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <Card title="Event plans" icon={<CalendarHeart size={16} aria-hidden="true" />}>
          {loading && <LoadingState rows={3} />}
          {error && <ErrorState message={error.message} onRetry={reload} />}
          {data && data.events.length === 0 && (
            <EmptyState title="No event plans yet">Create your first plan and it will appear here.</EmptyState>
          )}
          {data && data.events.length > 0 && (
            <ul className="space-y-3">
              {data.events.map((e) => (
                <li key={e.id} className={`rounded-2xl border p-4 transition ${highlight === e.id ? "border-royal bg-lilac/60" : "border-lavender/30 bg-ivory/60"}`}>
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="font-display text-xl font-semibold text-plum">{e.name}</p>
                      <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
                        <span>{formatDate(e.target_date)}</span>
                        <span className="inline-flex items-center gap-1"><MapPin size={13} aria-hidden="true" />{e.city || "City TBD"}</span>
                        {e.expected_attendance != null && <span className="inline-flex items-center gap-1"><Users size={13} aria-hidden="true" />{e.expected_attendance} guests</span>}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="rounded-full bg-lilac px-2.5 py-0.5 text-xs font-semibold capitalize text-plum">{e.status.replace("_", " ")}</span>
                      {e.is_demo && <DemoBadge label="Demo" />}
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-4 text-sm">
                    <span className="text-muted">Goal <b className="text-plum">{usd(e.fundraising_goal_usd)}</b></span>
                    <span className="text-muted">Budget limit <b className="text-plum">{usd(e.budget_limit_usd)}</b></span>
                    <span className="capitalize text-muted">{e.event_type}</span>
                  </div>
                  {e.notes && <p className="mt-2 text-sm text-ink/80">{e.notes}</p>}
                </li>
              ))}
            </ul>
          )}
        </Card>
        <AgentPanel
          agents={["fundraising_events", "orchestrator"]}
          upcoming={["Venue research with sources", "Preliminary budgets computed in Python", "Lessons from past events applied", "Board-ready recommendation packet"]}
        />
      </div>
      {toast && <Toast message={toast} onDone={clearToast} />}
    </>
  );
}
