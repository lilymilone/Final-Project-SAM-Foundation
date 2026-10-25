import {
  ArrowLeft, Building2, CalendarDays, CircleDollarSign, Handshake, Lightbulb, MapPin, MessageSquareHeart, Pencil, Scale, Sparkles, Target,
  Users, Wand2,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { LegacyEventDetail, RunDetail, RunSummary } from "../api/types";
import { formatDate, usd, useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { useButterflies } from "../butterflies/ButterflyProvider";
import { StatusPill } from "../components/agents";
import { EventCover, EventForm, FactRow, LessonList, PhotoManager, ReflectionCard, ReflectionForm } from "../components/legacy";
import { Card, DemoBadge, EmptyState, ErrorState, LoadingState, Toast } from "../components/ui";

type AnalysisData = {
  run_id?: number;
  date?: string;
  themes?: { name: string; polarity: string; description: string }[];
  disagreements?: { topic: string; positions: string[] }[];
  comparison?: { sufficient: boolean; note: string | null } | null;
  numeric_comparison_note?: string | null;
};

function AnalyzeButton({ eventId, eventName, onDone }: { eventId: number; eventName: string; onDone: (d: RunDetail) => void }) {
  const { can } = useAuth();
  const { celebrate } = useButterflies();
  const [runId, setRunId] = useState<number | null>(null);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!runId) return;
    let stop = false;
    const tick = async () => {
      const d = await api<RunDetail>(`/api/runs/${runId}`).catch(() => null);
      if (stop || !d) return;
      setDetail(d);
      if (d.run.status === "queued" || d.run.status === "running") window.setTimeout(tick, 1500);
      else {
        if (d.run.status.startsWith("completed")) celebrate("workflow", boxRef.current);
        onDone(d);
      }
    };
    tick();
    return () => { stop = true; };
  }, [runId, celebrate, onDone]);

  if (!can("run_agents")) return null;
  const running = detail ? ["queued", "running"].includes(detail.run.status) : !!runId;
  const current = detail?.steps[detail.steps.length - 1];

  async function start() {
    setError(null);
    setDetail(null);
    try {
      const res = await api<{ run: RunSummary }>("/api/runs", {
        json: { request: `Analyze ${eventName} and generate lessons`, intent: "event_learning", historical_event_id: eventId, research_mode: "synthetic" },
      });
      setRunId(res.run.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the analysis.");
    }
  }

  return (
    <div ref={boxRef}>
      <button className="btn btn-primary" onClick={start} disabled={running}>
        <Wand2 size={16} aria-hidden="true" /> {running ? "Analyzing…" : "Analyze Event & Generate Lessons"}
      </button>
      {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
      {detail && (
        <p className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
          <StatusPill status={detail.run.status} />
          {running && current ? `${current.to_agent.replace(/_/g, " ")}: ${current.objective}` : `${detail.totals.model_calls} model calls · $${detail.totals.cost_usd.toFixed(4)}`}
          <Link to={`/activity/runs/${detail.run.id}`} className="text-royal underline">view handoffs</Link>
        </p>
      )}
    </div>
  );
}

export default function LegacyEventPage() {
  const { id } = useParams();
  const { can } = useAuth();
  const { celebrate } = useButterflies();
  const { data, error, loading, reload } = useApi<LegacyEventDetail>(`/api/legacy/events/${id}`);
  const [editing, setEditing] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisData | null>(null);
  const clearToast = useCallback(() => setToast(null), []);
  const onAnalysisDone = useCallback((d: RunDetail) => {
    const step = d.steps.find((s) => s.to_agent === "event_intelligence");
    setAnalysis(step?.result?.data ? { ...(step.result.data as AnalysisData), run_id: d.run.id, date: d.run.started_at } : null);
    reload();
  }, [reload]);
  const shown: AnalysisData | null = analysis ?? data?.latest_analysis ?? null;

  if (loading && !data) return <LoadingState rows={4} />;
  if (error) return <ErrorState message={error.message} onRetry={reload} />;
  if (!data) return null;
  const e = data.event;

  return (
    <>
      <Link to="/legacy" className="mb-4 inline-flex items-center gap-1 text-sm text-royal hover:underline"><ArrowLeft size={14} aria-hidden="true" /> Our Legacy</Link>

      <section className="card mb-6 overflow-hidden !p-0 animate-fade-up">
        <div className="relative h-56 sm:h-64"><EventCover event={e} /></div>
        <div className="p-6 sm:p-8">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="eyebrow">{e.event_type}</p>
              <h1 className="mt-1 font-display text-4xl font-semibold leading-tight text-plum">{e.name}</h1>
              <p className="mt-1 flex flex-wrap items-center gap-3 text-sm text-muted">
                <span className="inline-flex items-center gap-1"><CalendarDays size={14} aria-hidden="true" />{formatDate(e.event_date)}</span>
                <span className="inline-flex items-center gap-1"><MapPin size={14} aria-hidden="true" />{[e.venue, e.location].filter(Boolean).join(" · ") || "Location not recorded"}</span>
                {e.is_demo && <DemoBadge label="Synthetic demonstration record" />}
              </p>
            </div>
            <div className="flex flex-wrap items-start gap-2">
              {can("manage_events") && !editing && <button className="btn btn-soft" onClick={() => setEditing(true)}><Pencil size={14} aria-hidden="true" /> Edit record</button>}
              <AnalyzeButton eventId={e.id} eventName={e.name} onDone={onAnalysisDone} />
            </div>
          </div>
          {editing ? (
            <div className="mt-6"><EventForm initial={e} onCancel={() => setEditing(false)} onSaved={(_, __, anchor) => {
              celebrate("save", anchor);
              setToast("Event record updated. The change is in the audit log.");
              setEditing(false);
              reload();
            }} /></div>
          ) : (
            <>
              <div className="mt-6 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                <FactRow icon={<Users size={15} />} label="Attendance" value={e.attendance ?? "Not recorded"} />
                <FactRow icon={<Target size={15} />} label="Fundraising goal" value={usd(e.fundraising_goal_usd)} />
                <FactRow icon={<CircleDollarSign size={15} />} label="Funds raised" value={<>{usd(e.funds_raised_usd)}{e.goal_pct != null && <span className="ml-1 text-xs font-normal text-muted">({e.goal_pct}% of goal)</span>}</>} />
                <FactRow icon={<Building2 size={15} />} label="Expenses" value={usd(e.total_cost_usd)} />
                <FactRow icon={<Scale size={15} />} label="Net proceeds (calculated)" value={usd(e.net_usd)} />
                <FactRow icon={<Handshake size={15} />} label="Sponsorship" value={usd(e.sponsorship_usd)} />
                <div className="rounded-xl bg-ivory/80 px-3 py-2 sm:col-span-2"><p className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">Sponsors</p><p className="text-sm text-plum">{e.sponsorship_info || "—"}</p></div>
                <FactRow icon={<Users size={15} />} label="Volunteers" value={e.volunteers_count ?? "Not recorded"} />
                <FactRow icon={<Users size={15} />} label="Returning participants" value={e.repeat_participants ?? "Not recorded"} />
                <FactRow icon={<Handshake size={15} />} label="Partnerships formed" value={e.partnerships_formed ?? "Not recorded"} />
                <FactRow icon={<CircleDollarSign size={15} />} label="Directed to programs" value={e.funds_directed_usd == null ? "Not recorded" : usd(e.funds_directed_usd)} />
                {e.community_outcomes && <div className="rounded-xl bg-ivory/80 px-3 py-2 sm:col-span-2 lg:col-span-4"><p className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">Documented community outcomes (board-recorded)</p><p className="text-sm text-plum">{e.community_outcomes}</p></div>}
              </div>
              {e.summary && <p className="mt-5 max-w-3xl leading-relaxed text-ink">{e.summary}</p>}
              {e.notes && <p className="mt-2 max-w-3xl text-sm text-muted"><b>Notes:</b> {e.notes}</p>}
            </>
          )}
        </div>
      </section>

      {shown && (
        <Card title="What the Event Intelligence agent found" icon={<Sparkles size={16} aria-hidden="true" />} className="mb-6"
          action={shown.run_id ? <Link to={`/activity/runs/${shown.run_id}`} className="text-xs text-royal hover:underline">Analysis #{shown.run_id}{shown.date ? ` · ${formatDate(shown.date)}` : ""}</Link> : undefined}>
          {shown.themes && shown.themes.length > 0 && (
            <div className="mb-4"><p className="label">Recurring themes</p><ul className="grid gap-2 sm:grid-cols-2">{shown.themes.map((t) => (
              <li key={t.name} className={`rounded-xl px-3 py-2 text-sm ${t.polarity === "strength" ? "bg-[#e3f1e8]" : t.polarity === "weakness" ? "bg-[#fbf1e3]" : "bg-lilac/60"}`}>
                <p className="font-semibold capitalize text-plum">{t.name} <span className="text-xs font-normal text-muted">· {t.polarity}</span></p><p className="text-muted">{t.description}</p></li>))}</ul></div>
          )}
          {shown.disagreements && shown.disagreements.length > 0 && (
            <div className="mb-4"><p className="label">Where board members disagree</p>{shown.disagreements.map((d) => (
              <div key={d.topic} className="mb-2 rounded-xl bg-white/80 p-3 ring-1 ring-lavender/40"><p className="font-semibold text-plum">{d.topic}</p>
                <ul className="mt-1 list-disc pl-5 text-sm">{d.positions.map((p, i) => <li key={i}>{p}</li>)}</ul></div>))}</div>
          )}
          <p className="text-sm text-muted"><b>Numbers:</b> {shown.comparison?.sufficient ? shown.numeric_comparison_note ?? "Compared in code across events." : shown.comparison?.note ?? "Not enough data to compare."}</p>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-[1.35fr_1fr]">
        <div className="space-y-6">
          <Card title={`Board reflections (${e.reflections.length})`} icon={<MessageSquareHeart size={16} aria-hidden="true" />}>
            {e.reflections.length === 0 ? <EmptyState title="No reflections yet">Be the first to share what you learned.</EmptyState>
              : <div className="space-y-3">{e.reflections.map((r) => <ReflectionCard key={r.id} r={r} />)}</div>}
          </Card>
          {can("write_reflections") && (
            <Card title="Share your post-event reflection" icon={<Pencil size={16} aria-hidden="true" />}>
              <ReflectionForm eventId={e.id} questions={data.questions} onSaved={(anchor) => {
                celebrate("reflection", anchor);
                setToast("Thank you. Your reflection is saved with your name and today's date.");
                reload();
              }} />
            </Card>
          )}
        </div>
        <div className="space-y-6">
          <Card title="Lessons linked to this event" icon={<Lightbulb size={16} aria-hidden="true" />}>
            <LessonList lessons={data.lessons} limit={6} empty={<EmptyState title="No lessons yet">Press “Analyze Event & Generate Lessons”. Every lesson links back to the records behind it.</EmptyState>} />
          </Card>
          <Card title="Photos" icon={<Sparkles size={16} aria-hidden="true" />}>
            <PhotoManager eventId={e.id} photos={e.photos} onChange={reload} />
          </Card>
        </div>
      </div>
      {toast && <Toast message={toast} onDone={clearToast} />}
    </>
  );
}
