import { Lightbulb, Plus, Sprout, X } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { HistoryStats, LegacyEvent, LessonItem } from "../api/types";
import { useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { useButterflies } from "../butterflies/ButterflyProvider";
import { EventForm, EventGalleryCard, HistoryExperimentCard, LegacyMetricsStrip, LessonList } from "../components/legacy";
import { ImpactPanel } from "../components/impact";
import { RunLauncher } from "../components/RunLauncher";
import { Card, EmptyState, ErrorState, LoadingState, PageHeader, Toast } from "../components/ui";

export default function LegacyPage() {
  const { can } = useAuth();
  const { celebrate } = useButterflies();
  const navigate = useNavigate();
  const { data, error, loading, reload } = useApi<{ events: LegacyEvent[]; stats: HistoryStats }>("/api/legacy/events");
  const lessons = useApi<{ lessons: LessonItem[] }>("/api/lessons");
  const [open, setOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [metricsKey, setMetricsKey] = useState(0);
  const headerRef = useRef<HTMLDivElement>(null);
  const clearToast = useCallback(() => setToast(null), []);
  const lessonItems = (lessons.data?.lessons ?? []).filter((l) => l.status !== "dismissed").slice(0, 8);

  return (
    <>
      <div ref={headerRef}>
        <PageHeader eyebrow="Our Legacy" title="Every event teaches us something"
          subtitle="The foundation's memory: what happened, what it cost, what the board felt, and what we learned. Kept so the next board starts wiser."
          actions={can("manage_events") && !open && <button className="btn btn-primary" onClick={() => setOpen(true)}><Plus size={16} aria-hidden="true" /> Record a past event</button>} />
      </div>

      <LegacyMetricsStrip refreshKey={metricsKey} />

      {open && (
        <Card title="Record a past event" icon={<Sprout size={16} aria-hidden="true" />} className="mb-6"
          action={<button className="btn btn-ghost !p-2" onClick={() => setOpen(false)} aria-label="Close form"><X size={16} aria-hidden="true" /></button>}>
          <EventForm onCancel={() => setOpen(false)} onSaved={(ev, milestone, anchor) => {
            celebrate("reflection", anchor);
            if (milestone) window.setTimeout(() => celebrate("milestone", headerRef.current), 600);
            setToast(milestone ? `Milestone: ${milestone}` : `“${ev.name}” is preserved in Our Legacy`);
            setOpen(false);
            setMetricsKey((k) => k + 1);
            reload();
            window.setTimeout(() => navigate(`/legacy/${ev.id}`), 900);
          }} />
        </Card>
      )}

      <section aria-label="Event gallery" className="mb-8">
        <h2 className="mb-3 font-display text-3xl font-semibold text-plum">Event gallery</h2>
        {loading && <LoadingState rows={3} />}
        {error && <ErrorState message={error.message} onRetry={reload} />}
        {data && (data.events.length === 0 ? <Card><EmptyState title="No past events yet">Record your first event to begin the foundation's memory.</EmptyState></Card> : (
          <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">{data.events.map((e) => <EventGalleryCard key={e.id} event={e} />)}</div>
        ))}
        {data?.events.some((e) => e.is_demo) && (
          <p className="mt-3 text-xs text-muted">Entries marked “Synthetic” are demonstration records, not real Sabrina Audrey Milone Foundation events or results. Covers without photos are decorative illustrations, not photographs.</p>
        )}
      </section>

      <div className="grid gap-5 lg:grid-cols-[1.25fr_1fr]">
        <div className="space-y-5">
          <HistoryExperimentCard />
          <Card title="Lessons the board can act on" icon={<Lightbulb size={16} aria-hidden="true" />}>
            {lessons.loading && <LoadingState rows={2} />}
            {lessons.data && <LessonList lessons={lessonItems} empty={
              <EmptyState title="No lessons yet">Open an event and press “Analyze Event & Generate Lessons”, or ask for lessons across all events.</EmptyState>} />}
          </Card>
        </div>
        <div className="space-y-5">
          <ImpactPanel />
          <RunLauncher title="Learn across all events" intent="event_learning" lockIntent
            examples={["What lessons can we learn from our previous events?", "Which activities made people feel welcomed and connected?"]} />
        </div>
      </div>
      {toast && <Toast message={toast} onDone={clearToast} />}
    </>
  );
}
