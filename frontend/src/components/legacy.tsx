import {
  BookOpenCheck, CalendarDays, Check, CircleDollarSign, FlaskConical, Footprints, ImagePlus, Lightbulb, Mic, Quote, Repeat2, Scale,
  Sparkles, Trash2, Users, UtensilsCrossed, X,
} from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Experiment, LegacyEvent, LegacyMetrics, LegacyPhoto, LegacyReflection, LessonItem } from "../api/types";
import { formatDate, usd, useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { Butterfly } from "../butterflies/Butterfly";
import { useButterflies } from "../butterflies/ButterflyProvider";
import { Card, DemoBadge, ErrorState, LoadingState, StatTile } from "./ui";

// ── Cover art (decorative, never presented as a photograph) ────────────────────

const COVERS = [
  ["#efe4fa", "#f6d6e8", "#b69ad9"],
  ["#e8ddf7", "#dcc8ef", "#d58ab8"],
  ["#f3e7f8", "#ead9f5", "#8b5cc0"],
] as const;

function TypeIcon({ type, size = 22 }: { type: string; size?: number }) {
  const t = type.toLowerCase();
  const Icon = t.includes("walk") || t.includes("run") ? Footprints : t.includes("dinner") || t.includes("gala") || t.includes("brunch") ? UtensilsCrossed
    : t.includes("panel") || t.includes("talk") ? Mic : Sparkles;
  return <Icon size={size} aria-hidden="true" />;
}

export function EventCover({ event, className = "" }: { event: LegacyEvent; className?: string }) {
  const photo = event.photos[0];
  if (photo) {
    return <img src={photo.url} alt={photo.caption || `Photo from ${event.name}`} className={`h-full w-full object-cover ${className}`} loading="lazy" />;
  }
  const [a, b, c] = COVERS[event.id % COVERS.length];
  return (
    <div className={`relative h-full w-full overflow-hidden ${className}`} style={{ background: `radial-gradient(120% 90% at 15% 10%, ${a}, transparent 60%), radial-gradient(90% 80% at 90% 90%, ${b}, transparent 65%), linear-gradient(135deg, ${a}, ${b})` }} aria-hidden="true">
      <Butterfly size={64} motion="still" palette={(event.id % 3) as 0 | 1 | 2} className="absolute left-[12%] top-[22%] rotate-[-12deg] opacity-80" />
      <Butterfly size={34} motion="still" palette={((event.id + 1) % 3) as 0 | 1 | 2} className="absolute right-[18%] top-[14%] rotate-[16deg] opacity-60" />
      <Butterfly size={26} motion="still" palette={((event.id + 2) % 3) as 0 | 1 | 2} className="absolute bottom-[16%] right-[30%] rotate-[-4deg] opacity-50" />
      <span className="absolute bottom-3 left-3 grid h-10 w-10 place-items-center rounded-full bg-white/80 shadow-sm" style={{ color: c }}>
        <TypeIcon type={event.event_type} />
      </span>
    </div>
  );
}

// ── Impact metrics ─────────────────────────────────────────────────────────────

export function LegacyMetricsStrip({ refreshKey = 0 }: { refreshKey?: number }) {
  const { data, error, reload } = useApi<LegacyMetrics>(`/api/legacy/metrics?r=${refreshKey}`);
  if (error) return <ErrorState message={error.message} onRetry={reload} />;
  if (!data) return <LoadingState rows={1} />;
  return (
    <section aria-label="Impact metrics" className="mb-6 animate-fade-up">
      <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <StatTile label="Events recorded" value={data.events_recorded} hint={data.events_demo ? `${data.events_demo} synthetic demo` : undefined} />
        <StatTile label="Reflections" value={data.reflections_collected} hint={`from ${data.contributors} contributor${data.contributors === 1 ? "" : "s"}`} />
        <StatTile label="Lessons generated" value={data.lessons_generated} hint={`${data.lessons_current} current`} />
        <StatTile label="Recurring issues" value={data.recurring_issues.length} hint={data.recurring_issues[0]?.theme} />
        <StatTile label="Reviewed / adopted" value={`${data.recommendations_reviewed} / ${data.recommendations_adopted}`} hint="by the board" />
        <StatTile label="Outcome improvement" value={<span className="text-xl">Not yet measured</span>} hint="needs a future event's results" />
      </div>
      {data.recurring_issues.length > 0 && (
        <p className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted">
          <Repeat2 size={13} aria-hidden="true" /> Recurring issues:
          {data.recurring_issues.map((r) => <span key={r.theme} className="rounded-full bg-[#fbf1e3] px-2 py-0.5 capitalize text-amber">{r.theme} · {r.evidence_count} records</span>)}
        </p>
      )}
    </section>
  );
}

// ── Gallery card ──────────────────────────────────────────────────────────────

export function EventGalleryCard({ event }: { event: LegacyEvent }) {
  return (
    <Link to={`/legacy/${event.id}`} className="group card flex flex-col overflow-hidden !p-0 transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-lift)]">
      <div className="relative h-40 w-full">
        <EventCover event={event} />
        <div className="absolute right-3 top-3 flex gap-1.5">{event.is_demo && <DemoBadge label="Synthetic" />}</div>
      </div>
      <div className="flex flex-1 flex-col p-5">
        <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
          <CalendarDays size={12} aria-hidden="true" /> {formatDate(event.event_date)} · {event.location || "Location not recorded"}
        </p>
        <h3 className="mt-1 font-display text-2xl font-semibold leading-tight text-plum group-hover:text-royal">{event.name}</h3>
        <p className="mt-1 line-clamp-2 text-sm text-muted">{event.summary}</p>
        <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
          <div className="rounded-xl bg-ivory py-2"><p className="text-muted">Raised</p><p className="font-semibold text-plum">{usd(event.funds_raised_usd)}</p></div>
          <div className="rounded-xl bg-ivory py-2"><p className="text-muted">Net</p><p className="font-semibold text-plum">{usd(event.net_usd)}</p></div>
          <div className="rounded-xl bg-ivory py-2"><p className="text-muted">Of goal</p><p className="font-semibold text-plum">{event.goal_pct != null ? `${event.goal_pct}%` : "—"}</p></div>
        </div>
        {event.top_lesson && (
          <p className="mt-3 flex gap-2 rounded-xl bg-lilac/50 px-3 py-2 text-xs text-plum"><Lightbulb size={13} className="mt-0.5 shrink-0" aria-hidden="true" /><span className="line-clamp-2">{event.top_lesson}</span></p>
        )}
        <p className="mt-auto flex gap-3 pt-3 text-xs text-muted">
          <span>{event.reflection_count} reflection{event.reflection_count === 1 ? "" : "s"}</span>
          <span>{event.lesson_count ?? 0} lesson{event.lesson_count === 1 ? "" : "s"}</span>
          <span>{event.photos.length} photo{event.photos.length === 1 ? "" : "s"}</span>
        </p>
      </div>
    </Link>
  );
}

// ── Event form (create + edit) ────────────────────────────────────────────────

const FIELDS: { key: keyof LegacyEvent; label: string; type?: string; span?: boolean; textarea?: boolean }[] = [
  { key: "name", label: "Event name *", span: true },
  { key: "event_date", label: "Date", type: "date" },
  { key: "event_year", label: "Year (if the exact date is unknown)", type: "number" },
  { key: "event_type", label: "Type (walk, dinner, gala, panel…)" },
  { key: "venue", label: "Venue" },
  { key: "location", label: "City / location" },
  { key: "attendance", label: "Attendance (if known)", type: "number" },
  { key: "fundraising_goal_usd", label: "Fundraising goal (USD)", type: "number" },
  { key: "funds_raised_usd", label: "Funds raised (USD)", type: "number" },
  { key: "total_cost_usd", label: "Expenses (USD)", type: "number" },
  { key: "sponsorship_usd", label: "Sponsorship (USD)", type: "number" },
  { key: "planned_budget_usd", label: "Planned budget (USD, if one was set)", type: "number" },
  { key: "sponsorship_info", label: "Sponsors and what they gave", span: true },
  { key: "summary", label: "Event summary", span: true, textarea: true },
  { key: "notes", label: "Notes", span: true, textarea: true },
  { key: "volunteers_count", label: "Volunteers (leave blank if not recorded)", type: "number" },
  { key: "repeat_participants", label: "Returning participants (if recorded)", type: "number" },
  { key: "partnerships_formed", label: "Partnerships formed", type: "number" },
  { key: "funds_directed_usd", label: "Funds directed to charitable programs (USD)", type: "number" },
  { key: "community_outcomes", label: "Documented community outcomes (what actually happened, not impressions)", span: true, textarea: true },
  { key: "positive_outcomes", label: "What worked", span: true, textarea: true },
  { key: "problems_encountered", label: "Problems encountered", span: true, textarea: true },
  { key: "lessons_learned", label: "Lessons the board learned (in your own words)", span: true, textarea: true },
];
const NUMERIC = new Set(["attendance", "fundraising_goal_usd", "funds_raised_usd", "total_cost_usd", "sponsorship_usd", "volunteers_count",
  "repeat_participants", "partnerships_formed", "funds_directed_usd", "event_year", "planned_budget_usd"]);

export function EventForm({ initial, onSaved, onCancel }: { initial?: LegacyEvent; onSaved: (e: LegacyEvent, milestone: string | null, anchor: Element | null) => void; onCancel: () => void }) {
  const [form, setForm] = useState<Record<string, string>>(() =>
    Object.fromEntries(FIELDS.map((f) => [f.key, initial?.[f.key] == null ? (f.key === "event_type" ? "fundraiser" : "") : String(initial[f.key])])));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const raised = Number(form.funds_raised_usd), cost = Number(form.total_cost_usd);
  const net = form.funds_raised_usd !== "" && form.total_cost_usd !== "" ? raised - cost : null;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    const body: Record<string, unknown> = {};
    for (const f of FIELDS) {
      const v = form[f.key].trim();
      body[f.key] = NUMERIC.has(f.key) ? (v === "" ? null : Number(v)) : f.key === "event_date" ? v || null : v || (["sponsorship_info", "notes", "venue", "community_outcomes", "positive_outcomes", "problems_encountered", "lessons_learned"].includes(f.key) ? null : "");
    }
    try {
      const res = initial
        ? await api<{ event: LegacyEvent }>(`/api/legacy/events/${initial.id}`, { method: "PUT", json: body })
        : await api<{ event: LegacyEvent; milestone: string | null }>("/api/legacy/events", { json: body });
      onSaved(res.event, "milestone" in res ? (res as { milestone: string | null }).milestone : null, buttonRef.current);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
      {FIELDS.map((f) => (
        <div key={f.key} className={f.span ? "sm:col-span-2" : ""}>
          <label className="label" htmlFor={`ev-${f.key}`}>{f.label}</label>
          {f.textarea ? (
            <textarea id={`ev-${f.key}`} rows={3} className="field" value={form[f.key]} onChange={(e) => setForm((s) => ({ ...s, [f.key]: e.target.value }))} />
          ) : (
            <input id={`ev-${f.key}`} className="field" type={f.type ?? "text"} min={f.type === "number" ? 0 : undefined} value={form[f.key]}
              onChange={(e) => setForm((s) => ({ ...s, [f.key]: e.target.value }))} required={f.key === "name"} />
          )}
        </div>
      ))}
      <p className="text-sm text-muted sm:col-span-2">Net proceeds (calculated): <b className="text-plum">{net == null ? "—" : usd(net)}</b></p>
      {error && <p role="alert" className="text-sm text-danger sm:col-span-2">{error}</p>}
      <div className="flex justify-end gap-2 sm:col-span-2">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>Cancel</button>
        <button ref={buttonRef} className="btn btn-primary" disabled={saving || form.name.trim().length < 2}>{saving ? "Saving…" : initial ? "Save changes" : "Save to Our Legacy"}</button>
      </div>
    </form>
  );
}

// ── Reflections ───────────────────────────────────────────────────────────────

export function ReflectionCard({ r }: { r: LegacyReflection }) {
  const answered = r.answers.filter((a) => a.answer.trim());
  return (
    <article className="rounded-2xl border border-lavender/35 bg-white/85 p-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 font-semibold text-plum"><Quote size={14} className="text-rose" aria-hidden="true" />{r.author}
          {r.recorded_by && <span className="text-xs font-normal text-muted">recorded by {r.recorded_by}</span>}</p>
        <p className="flex items-center gap-2 text-xs text-muted">
          {r.rating && <span aria-label={`${r.rating} of 5`}>{"★".repeat(r.rating)}</span>}
          Submitted {formatDate(r.created_at)}{r.is_demo && <DemoBadge label="Synthetic" />}
        </p>
      </header>
      <dl className="mt-2 grid gap-2 sm:grid-cols-2">
        {answered.map((a) => (
          <div key={a.key} className="rounded-xl bg-ivory/80 px-3 py-2">
            <dt className="text-[0.7rem] font-semibold uppercase tracking-wide text-royal">{a.question}</dt>
            <dd className="mt-0.5 text-sm text-ink">{a.answer}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-[0.7rem] text-muted">Original words, preserved as submitted. AI analysis is stored separately and never edits a reflection.</p>
    </article>
  );
}

export function ReflectionForm({ eventId, questions, onSaved }: { eventId: number; questions: { key: string; question: string }[]; onSaved: (anchor: Element | null) => void }) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [rating, setRating] = useState("");
  const [onBehalf, setOnBehalf] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api(`/api/legacy/events/${eventId}/reflections`, {
        json: { ...answers, rating: rating ? Number(rating) : null, attributed_to: onBehalf.trim() || null },
      });
      onSaved(buttonRef.current);
      setAnswers({});
      setRating("");
      setOnBehalf("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }
  return (
    <form onSubmit={submit} className="space-y-3">
      <ol className="grid gap-3 sm:grid-cols-2">
        {questions.map((q, i) => (
          <li key={q.key} className={i === questions.length - 1 ? "sm:col-span-2" : ""}>
            <label className="label" htmlFor={`rq-${q.key}`}>{i + 1}. {q.question}</label>
            <textarea id={`rq-${q.key}`} rows={2} className="field" value={answers[q.key] ?? ""} onChange={(e) => setAnswers((a) => ({ ...a, [q.key]: e.target.value }))} />
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <label className="label" htmlFor="rq-rating">Overall rating (optional)</label>
          <select id="rq-rating" className="field !w-40" value={rating} onChange={(e) => setRating(e.target.value)}>
            <option value="">No rating</option>{[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{"★".repeat(n)}</option>)}
          </select>
        </div>
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
        <button ref={buttonRef} className="btn btn-primary" disabled={saving || !Object.values(answers).some((v) => v.trim())}>{saving ? "Saving…" : "Submit my reflection"}</button>
      </div>
      <details className="text-xs text-muted">
        <summary className="cursor-pointer font-semibold text-plum">Recording another board member's reflection?</summary>
        <label className="label mt-2" htmlFor="rq-behalf">Their name (both names are kept: theirs as the author, yours as the recorder)</label>
        <input id="rq-behalf" className="field !w-80" maxLength={120} value={onBehalf} onChange={(e) => setOnBehalf(e.target.value)} placeholder="e.g. Jordan Lee (shared by phone)" />
      </details>
      <p className="text-xs text-muted">Your name and today's date are saved with your answers. Reflections can't be edited afterwards, so the original record stays intact, and different views are kept side by side.</p>
    </form>
  );
}

// ── Lessons with board review ───────────────────────────────────────────────────

const KIND: Record<string, { label: string; cls: string }> = {
  what_worked: { label: "Strength", cls: "bg-[#e3f1e8] text-sage" },
  recurring_problem: { label: "Recurring problem", cls: "bg-[#fbf1e3] text-amber" },
  recommendation: { label: "Recommendation", cls: "bg-lilac text-royal" },
  community_insight: { label: "Community insight", cls: "bg-blush/70 text-plum" },
};
const STATUS: Record<string, string> = { new: "Not reviewed", reviewed: "Reviewed", adopted: "Adopted", dismissed: "Dismissed", superseded: "Superseded" };

export function LessonCard({ lesson, onChange }: { lesson: LessonItem; onChange?: (l: LessonItem) => void }) {
  const { can } = useAuth();
  const [busy, setBusy] = useState(false);
  async function review(status: LessonItem["status"]) {
    setBusy(true);
    try {
      await api(`/api/lessons/${lesson.id}/review`, { json: { status } });
      onChange?.({ ...lesson, status });
    } finally {
      setBusy(false);
    }
  }
  const kind = KIND[lesson.kind ?? ""] ?? { label: "Lesson", cls: "bg-lilac text-plum" };
  return (
    <li className={`rounded-2xl border p-4 text-sm ${lesson.status === "adopted" ? "border-sage/50 bg-[#f1f8f3]" : lesson.status === "dismissed" ? "border-lavender/30 bg-white/60 opacity-70" : "border-lavender/35 bg-white/85"}`}>
      <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
        <span className={`rounded-full px-2 py-0.5 text-[0.7rem] font-semibold ${kind.cls}`}>{kind.label}</span>
        {lesson.theme && <span className="rounded-full bg-ivory px-2 py-0.5 text-[0.7rem] capitalize text-plum ring-1 ring-lavender/40">{lesson.theme}</span>}
        <span className="text-[0.7rem] text-muted">{lesson.confidence} confidence · {STATUS[lesson.status]}</span>
        {lesson.based_on_demo_data && <DemoBadge label="From demo data" />}
      </div>
      <p className="text-ink">{lesson.lesson}</p>
      <p className="mt-2 flex flex-wrap items-center gap-1 text-[0.7rem]">
        <span className="text-muted">Evidence:</span>
        {lesson.evidence.map((e) => (
          <Link key={`${e.type}-${e.id}`} to={`/legacy/${e.event_id}`} className="rounded bg-ivory px-1.5 py-0.5 text-royal ring-1 ring-lavender/40 hover:underline">
            {e.type === "reflection" ? "Reflection: " : "Event: "}{e.label}
          </Link>
        ))}
        {lesson.run_id && <Link to={`/activity/runs/${lesson.run_id}`} className="ml-1 text-muted hover:underline">· run #{lesson.run_id}</Link>}
      </p>
      {can("run_agents") && lesson.status !== "superseded" && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {(["reviewed", "adopted", "dismissed"] as const).map((s) => (
            <button key={s} disabled={busy || lesson.status === s} onClick={() => review(s)}
              className={`rounded-full px-2.5 py-1 text-xs font-semibold transition ${lesson.status === s ? "bg-plum text-white" : "bg-lilac text-plum hover:bg-[#e2d4f2]"}`}>
              {s === "reviewed" ? <><Check size={11} className="mr-1 inline" aria-hidden="true" />Reviewed</> : s === "adopted" ? <><BookOpenCheck size={11} className="mr-1 inline" aria-hidden="true" />Adopt</> : <><X size={11} className="mr-1 inline" aria-hidden="true" />Dismiss</>}
            </button>
          ))}
        </div>
      )}
    </li>
  );
}

export function LessonList({ lessons, empty, limit }: { lessons: LessonItem[]; empty: ReactNode; limit?: number }) {
  const [items, setItems] = useState(lessons);
  const [showAll, setShowAll] = useState(false);
  useEffect(() => setItems(lessons), [lessons]);
  if (items.length === 0) return <>{empty}</>;
  const visible = limit && !showAll ? items.slice(0, limit) : items;
  return (
    <>
      <ul className="space-y-3">{visible.map((l) => <LessonCard key={l.id} lesson={l} onChange={(n) => setItems((all) => all.map((x) => (x.id === n.id ? n : x)))} />)}</ul>
      {limit && items.length > limit && (
        <button className="btn btn-ghost mt-2 text-sm" onClick={() => setShowAll((s) => !s)}>{showAll ? "Show fewer" : `Show all ${items.length} lessons`}</button>
      )}
    </>
  );
}

// ── Photos ────────────────────────────────────────────────────────────────────

export function PhotoManager({ eventId, photos, onChange }: { eventId: number; photos: LegacyPhoto[]; onChange: () => void }) {
  const { can } = useAuth();
  const { celebrate } = useButterflies();
  const [caption, setCaption] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function upload(file: File | undefined) {
    if (!file) return;
    setError(null);
    if (file.size > 5 * 1024 * 1024) return setError("Photos must be 5 MB or smaller.");
    const fd = new FormData();
    fd.append("file", file);
    fd.append("caption", caption);
    setBusy(true);
    try {
      const res = await fetch(`/api/legacy/events/${eventId}/photos`, { method: "POST", body: fd, credentials: "same-origin", headers: { "X-SAM-Request": "1" } });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? "Upload failed.");
      setCaption("");
      celebrate("save", inputRef.current?.parentElement ?? null);
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }
  async function remove(id: number) {
    await api(`/api/legacy/photos/${id}`, { method: "DELETE" });
    onChange();
  }

  return (
    <div>
      {photos.length === 0 ? <p className="text-sm text-muted">No photos yet.</p> : (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {photos.map((p) => (
            <li key={p.id} className="group relative overflow-hidden rounded-2xl bg-ivory">
              <img src={p.url} alt={p.caption || "Event photo"} className="aspect-[4/3] w-full object-cover" loading="lazy" />
              {p.caption && <p className="px-2 py-1.5 text-xs text-muted">{p.caption}</p>}
              {can("manage_events") && (
                <button onClick={() => remove(p.id)} className="absolute right-2 top-2 rounded-full bg-white/90 p-1.5 text-danger opacity-0 shadow transition group-hover:opacity-100 focus:opacity-100" aria-label="Remove photo">
                  <Trash2 size={14} aria-hidden="true" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {can("manage_events") && (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <div className="min-w-48 flex-1"><label className="label" htmlFor="photo-caption">Caption (optional)</label>
            <input id="photo-caption" className="field" value={caption} onChange={(e) => setCaption(e.target.value)} maxLength={300} /></div>
          <label className="btn btn-soft cursor-pointer">
            <ImagePlus size={15} aria-hidden="true" /> {busy ? "Uploading…" : "Add a photo"}
            <input ref={inputRef} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" onChange={(e) => upload(e.target.files?.[0])} disabled={busy} />
          </label>
        </div>
      )}
      {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
      <p className="mt-2 text-xs text-muted">PNG, JPEG, or WebP up to 5 MB. Photos are private to signed-in board members.</p>
    </div>
  );
}

// ── Evidence: planning with vs. without history ───────────────────────────────

function fmtNumber(label: string, v: number | null) {
  if (v == null) return "—";
  if (label.includes("Contingency")) return `${Math.round(v * 100)}%`;
  if (label.includes("Cost")) return `$${v.toFixed(4)}`;
  if (label.includes("USD")) return usd(v);
  return v.toLocaleString();
}

export function HistoryExperimentCard() {
  const { can } = useAuth();
  const { celebrate } = useButterflies();
  const { data, reload } = useApi<{ experiments: Experiment[] }>("/api/experiments");
  const [error, setError] = useState<string | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const latest = data?.experiments.find((e) => e.kind === "history_ab");
  const running = latest?.status === "running" || latest?.status === "queued";
  const wasRunning = useRef(false);

  useEffect(() => {
    if (!running) {
      if (wasRunning.current && latest?.status === "completed") celebrate("workflow", cardRef.current);
      wasRunning.current = false;
      return;
    }
    wasRunning.current = true;
    const t = window.setTimeout(reload, 2500);
    return () => window.clearTimeout(t);
  }, [running, latest?.status, reload, celebrate]);

  async function start() {
    setError(null);
    try {
      await api("/api/experiments/history-ab", { json: {} });
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start.");
    }
  }

  const c = latest?.comparison;
  return (
    <div ref={cardRef}>
      <Card title="Does history change the plan?" icon={<Scale size={16} aria-hidden="true" />}
        action={latest?.status === "completed" && can("view_financials") ? <a className="btn btn-ghost !py-1 text-sm" href={`/api/experiments/${latest.id}/report.md`} target="_blank" rel="noopener">Markdown report</a> : undefined}>
        <p className="text-sm text-muted">
          The same gala request runs twice with identical data: once <b>without</b> Event Intelligence and once <b>with</b> it. Code then compares the two results and the API usage of each run.
        </p>
        {!latest && can("run_agents") && <button className="btn btn-primary mt-3" onClick={start}>Run the comparison (2 workflows)</button>}
        {latest && running && (
          <p className="mt-3 flex items-center gap-2 rounded-xl bg-lilac/60 px-3 py-2 text-sm text-plum">
            <span className="h-2 w-2 animate-pulse rounded-full bg-royal" aria-hidden="true" /> Running experiment #{latest.id}: watch
            <Link to={`/activity/runs/${latest.run_a_id}`} className="underline">run A (without)</Link> and
            <Link to={`/activity/runs/${latest.run_b_id}`} className="underline">run B (with history)</Link>.
          </p>
        )}
        {latest?.status === "failed" && <p className="mt-3 text-sm text-danger">Experiment #{latest.id} failed: {latest.error}</p>}
        {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
        {c && latest && (
          <div className="mt-4 space-y-4">
            <ul className="space-y-1.5 text-sm">{c.summary_of_changes.map((x, i) => <li key={i} className="flex gap-2"><Sparkles size={13} className="mt-1 shrink-0 text-rose" aria-hidden="true" />{x}</li>)}</ul>
            <div className="-mx-2 overflow-x-auto">
              <table className="w-full min-w-[520px] text-left text-sm">
                <thead className="text-xs uppercase tracking-wide text-muted"><tr><th className="px-2 py-1.5">Measure</th>
                  <th className="px-2"><Link className="hover:underline" to={`/activity/runs/${latest.run_a_id}`}>Without history (#{latest.run_a_id})</Link></th>
                  <th className="px-2"><Link className="hover:underline" to={`/activity/runs/${latest.run_b_id}`}>With history (#{latest.run_b_id})</Link></th></tr></thead>
                <tbody>{Object.entries(c.numbers).map(([label, v]) => (
                  <tr key={label} className="border-t border-lavender/25"><td className="px-2 py-1.5 text-muted">{label}</td>
                    <td className="px-2 py-1.5">{fmtNumber(label, v.without_history)}</td><td className="px-2 py-1.5 font-semibold text-plum">{fmtNumber(label, v.with_history)}</td></tr>
                ))}</tbody>
              </table>
            </div>
            {c.history_constraints.length > 0 && (
              <div><p className="label">What Event Intelligence told the Events agent</p>
                <ul className="list-disc space-y-1 pl-5 text-sm">{c.history_constraints.map((x, i) => <li key={i}>{typeof x === "string" ? x : (x as { detail: string }).detail}</li>)}</ul></div>
            )}
            {(["lessons_applied", "fundraising_strategy", "logistics_notes", "next_steps"] as const).map((k) => c[k].only_with.length > 0 && (
              <div key={k}><p className="label">Only with history: {k.replace(/_/g, " ")}</p>
                <ul className="list-disc space-y-1 pl-5 text-sm">{c[k].only_with.slice(0, 6).map((x, i) => <li key={i}>{x}</li>)}</ul></div>
            ))}
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl bg-ivory p-3 text-sm"><p className="label">Without history</p><p className="font-semibold text-plum">{c.headlines.without_history}</p></div>
              <div className="rounded-xl bg-lilac/60 p-3 text-sm"><p className="label">With history</p><p className="font-semibold text-plum">{c.headlines.with_history}</p></div>
            </div>
            <p className="flex items-start gap-2 text-xs text-muted"><FlaskConical size={13} className="mt-0.5 shrink-0" aria-hidden="true" />{c.note}</p>
            {can("run_agents") && <button className="btn btn-soft text-sm" onClick={start} disabled={running}><CircleDollarSign size={14} aria-hidden="true" /> Run it again</button>}
          </div>
        )}
      </Card>
    </div>
  );
}

export function FactRow({ icon, label, value }: { icon: ReactNode; label: string; value: ReactNode }) {
  return (
    <div className="flex items-start gap-2.5 rounded-xl bg-ivory/80 px-3 py-2">
      <span className="mt-0.5 text-royal">{icon}</span>
      <div><p className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">{label}</p><p className="text-sm font-semibold text-plum">{value}</p></div>
    </div>
  );
}

export const factIcons = { Users, CalendarDays, CircleDollarSign };
