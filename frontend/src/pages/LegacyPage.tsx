import { Lightbulb, Plus, Sprout, X } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import type { HistoryStats, LegacyEvent, LessonItem } from "../api/types";
import { useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { useButterflies } from "../butterflies/ButterflyProvider";
import { EventForm, EventGalleryCard, LegacyMetricsStrip, LessonList } from "../components/legacy";
import { ImpactPanel } from "../components/impact";
import { InsightsPanel } from "../components/insights";
import { AddToLegacy } from "../components/legacyImport";
import { RunLauncher } from "../components/RunLauncher";
import { Card, EmptyState, ErrorState, LoadingState, PageHeader, Toast } from "../components/ui";

export default function LegacyPage() {
  const { can } = useAuth();
  const { celebrate } = useButterflies();
  const navigate = useNavigate();
  const { data, error, loading, reload } = useApi<{ events: LegacyEvent[]; stats: HistoryStats }>("/api/legacy/events");
  const lessons = useApi<{ lessons: LessonItem[] }>("/api/lessons");
  const [params] = useSearchParams();
  const [open, setOpen] = useState(params.get("add") === "1");
  const [toast, setToast] = useState<string | null>(null);
  const [metricsKey, setMetricsKey] = useState(0);
  const headerRef = useRef<HTMLDivElement>(null);
  const clearToast = useCallback(() => setToast(null), []);
  const lessonItems = (lessons.data?.lessons ?? []).filter((l) => l.status !== "dismissed").slice(0, 8);

  return (
    <>
      <div ref={headerRef}>
        <PageHeader eyebrow="Our Legacy" title="Past events"
          subtitle="Add past events, upload photos and documents, record reflections, and turn them into lessons for the next plan."
          actions={can("manage_events") && !open && <button className="btn btn-primary" onClick={() => setOpen(true)}><Plus size={16} aria-hidden="true" /> Add a past event</button>} />
      </div>

      <LegacyMetricsStrip refreshKey={metricsKey} />

      {open && (
        <Card title="Add a past event" icon={<Sprout size={16} aria-hidden="true" />} className="mb-6"
          action={<button className="btn btn-ghost !p-2" onClick={() => setOpen(false)} aria-label="Close form"><X size={16} aria-hidden="true" /></button>}>
          <AddToLegacy manual={<EventForm onCancel={() => setOpen(false)} onSaved={(ev, milestone, anchor) => {
            celebrate("reflection", anchor);
            if (milestone) window.setTimeout(() => celebrate("milestone", headerRef.current), 600);
            setToast(milestone ? `Milestone: ${milestone}` : `“${ev.name}” is preserved in Our Legacy`);
            setOpen(false);
            setMetricsKey((k) => k + 1);
            reload();
            window.setTimeout(() => navigate(`/legacy/${ev.id}`), 900);
          }} />} />
        </Card>
      )}

      <section aria-label="Event gallery" className="mb-8">
        <h2 className="mb-3 font-display text-3xl font-semibold text-plum">Event gallery</h2>
        {loading && <LoadingState rows={3} />}
        {error && <ErrorState message={error.message} onRetry={reload} />}
        {data && (data.events.length === 0 ? <Card><EmptyState title="No past events yet">Record your first event to begin the foundation's memory.</EmptyState></Card> : (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-3">{data.events.map((e) => <EventGalleryCard key={e.id} event={e} />)}</div>
        ))}
        {data?.events.some((e) => e.is_demo) && (
          <p className="mt-3 text-xs text-muted">Entries marked “Synthetic” are demonstration records, not real Sabrina Audrey Milone Foundation events or results. Covers without photos are decorative illustrations, not photographs.</p>
        )}
      </section>

      <div className="mb-5"><InsightsPanel /></div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <div className="space-y-5">
          <Card title="Lessons" icon={<Lightbulb size={16} aria-hidden="true" />}
            action={<Link to="/events" className="text-sm font-semibold text-royal hover:underline">Use them in a new plan →</Link>}>
            {lessons.loading && <LoadingState rows={2} />}
            {lessons.data && <LessonList lessons={lessonItems} limit={4} empty={
              <EmptyState title="No lessons yet">Open an event and press “Analyze Event & Generate Lessons”, or ask for lessons across all events.</EmptyState>} />}
          </Card>
        </div>
        <div className="space-y-5">
          <ImpactPanel />
          <RunLauncher title="Generate lessons across all events" intent="event_learning" lockIntent submitLabel="Generate lessons"
            request="What lessons can we learn from our previous events?"
            examples={["What lessons can we learn from our previous events?", "Which activities made people feel welcomed and connected?"]} />
        </div>
      </div>
      {toast && <Toast message={toast} onDone={clearToast} />}
    </>
  );
}
