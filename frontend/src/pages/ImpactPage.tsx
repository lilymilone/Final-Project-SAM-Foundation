import { ClipboardList, Download, FlaskConical, GitCompareArrows, ListChecks, MessageSquareQuote, PlayCircle, Sigma, Users } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { ImpactEvaluation, ImpactOverview, ImpactScenario } from "../api/types";
import { formatDate, useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { Butterfly } from "../butterflies/Butterfly";
import { ANSWER_LABELS, AnalyticsTabs, BasisTag, CompareBars, Quiet, fmtMin } from "../components/impactui";
import { Card, ErrorState, LoadingState, PageHeader, StatTile, Toast } from "../components/ui";

export default function ImpactPage() {
  const { can } = useAuth();
  const navigate = useNavigate();
  const overview = useApi<ImpactOverview>("/api/impact/overview");
  const scenario = useApi<ImpactScenario>("/api/impact/scenario");
  const mine = useApi<{ evaluations: { id: number; participant_code: string; status: string; is_synthetic: boolean; task_date: string | null; is_mine: boolean }[] }>("/api/impact/evaluations");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<{ message: string; tone: "success" | "error" } | null>(null);
  const [tasks, setTasks] = useState<string>("");

  async function start(practice: boolean) {
    setBusy(true);
    try {
      const res = await api<{ evaluation: ImpactEvaluation }>("/api/impact/evaluations", { json: { is_synthetic: practice } });
      navigate(`/safety/impact/evaluations/${res.evaluation.id}`);
    } catch (e) {
      setToast({ message: e instanceof Error ? e.message : "Could not start.", tone: "error" });
    } finally {
      setBusy(false);
    }
  }

  async function runComparison() {
    if (!scenario.data) return;
    setBusy(true);
    try {
      const res = await api<{ experiment: { id: number } }>("/api/experiments/history-ab", {
        json: { request: "Plan a 150-person Manhattan fundraising gala with three venue options, a preliminary budget, lessons from past events, and a venue inquiry draft.",
                event_plan_id: scenario.data.event_plan_id, research_mode: "synthetic" } });
      navigate(`/safety/impact/comparisons/${res.experiment.id}`);
    } catch (e) {
      setToast({ message: e instanceof Error ? e.message : "Could not start the comparison.", tone: "error" });
    } finally {
      setBusy(false);
    }
  }

  async function saveTasks() {
    try {
      await api("/api/impact/assumptions", { method: "PUT", json: { tasks_per_year: Number(tasks) } });
      setToast({ message: "Assumption saved. Projections now use it, labeled as an assumption.", tone: "success" });
      overview.reload();
    } catch (e) {
      setToast({ message: e instanceof Error ? e.message : "Could not save.", tone: "error" });
    }
  }

  const o = overview.data;
  const r = o?.real;
  const s = scenario.data;

  return (
    <>
      <PageHeader eyebrow="Analytics & Safety" title="Impact & Evaluation"
        subtitle="Does SAM SPACE actually help the board? This pilot compares the usual way of preparing an event proposal with SAM SPACE, using real timings, real agent logs, and board members' own feedback." />
      <AnalyticsTabs />

      {overview.loading && <LoadingState rows={3} />}
      {overview.error && <ErrorState message={overview.error.message} onRetry={overview.reload} />}
      {o && r && (
        <>
          {o.pilot_pending ? (
            <div className="mb-5 flex flex-wrap items-center gap-4 rounded-2xl border border-lavender/50 bg-gradient-to-br from-white to-lilac/40 p-5">
              <Butterfly size={34} motion="still" palette={1} className="opacity-80" />
              <div className="min-w-0 flex-1">
                <p className="font-display text-2xl font-semibold text-plum">{o.pilot_message}</p>
                <p className="mt-1 text-sm text-muted">The numbers below fill in only from submitted evaluations by real board members. Practice runs are kept separately and never counted.</p>
              </div>
            </div>
          ) : (
            <p className="mb-4 rounded-xl bg-[#fbf1e3] px-3 py-2 text-sm text-amber">{r.sample_note}</p>
          )}

          <section aria-label="Impact dashboard" className="mb-6">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatTile label="Completed evaluations" value={r.completed_evaluations} hint={<><BasisTag kind="observed" /> real participants only</>} />
              <StatTile label="Average time, usual way" value={fmtMin(r.time.manual_avg_minutes)} hint={<><BasisTag kind="observed" /> {r.time.manual_unavailable ? `${r.time.manual_unavailable} without a manual baseline` : "start to finish"}</>} />
              <StatTile label="Average time, SAM SPACE" value={fmtMin(r.time.assisted_avg_minutes)} hint={<><BasisTag kind="observed" /> includes reviewing the AI's work</>} />
              <StatTile label="Minutes saved" value={fmtMin(r.time.minutes_saved)}
                hint={<><BasisTag kind="calculated" /> {r.time.pct_reduction == null ? "no percentage without a manual time" : `${r.time.pct_reduction}% ${r.time.pct_reduction >= 0 ? "faster" : "slower"}`} · {r.time.paired_evaluations} paired</>} />
              <StatTile label="Average usefulness" value={r.ratings.usefulness == null ? "—" : `${r.ratings.usefulness} / 5`} hint={<><BasisTag kind="feedback" /> ease {r.ratings.ease_of_use ?? "—"} · sources {r.ratings.source_confidence ?? "—"}</>} />
              <StatTile label="Verified sources" value={`${r.sources.manual_avg_verified ?? "—"} vs ${r.sources.assisted_avg_verified_live ?? "—"}`}
                hint={<><BasisTag kind="logs" /> usual way (self-reported) vs live-verified in the run{r.sources.assisted_avg_synthetic ? ` (+${r.sources.assisted_avg_synthetic} synthetic)` : ""}</>} />
              <StatTile label="Financial accuracy (rubric)" value={`${r.financial_accuracy.manual_avg_score ?? "—"} vs ${r.financial_accuracy.assisted_avg_score ?? "—"}`}
                hint={<><BasisTag kind="feedback" /> human scores out of 4, usual way vs SAM SPACE</>} />
              <StatTile label="Projected hours saved / year" value={r.projection.annual_hours_saved == null ? "—" : `${r.projection.annual_hours_saved} h`}
                hint={<><BasisTag kind="extrapolated" /> {r.projection.tasks_per_year == null ? "set the tasks-per-year assumption" : `assumes ${r.projection.tasks_per_year} similar tasks a year`}</>} />
            </div>
            <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
              <CompareBars title="Task time (average, minutes)" manual={r.time.paired_manual_avg} assisted={r.time.paired_assisted_avg} unit=" min"
                note={r.time.paired_evaluations ? `${r.time.paired_evaluations} evaluation(s) with both times. ${r.time.basis}` : "No evaluation has both times yet."} />
              <CompareBars title="Verified sources per proposal (average)" manual={r.sources.manual_avg_verified} assisted={r.sources.assisted_avg_verified_live} unit=""
                note="Usual way: as the participant reported. SAM SPACE: pages fetched and checked live, from the run's logs (synthetic demo sources are not counted)." />
            </div>
          </section>

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
            <div className="space-y-5">
              <Card title="Take part" icon={<ClipboardList size={16} aria-hidden="true" />}>
                {s && (
                  <>
                    <p className="text-sm text-ink"><b className="text-plum">The task:</b> {s.scenario.task}</p>
                    <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-sm text-ink">{s.scenario.instructions.map((x, i) => <li key={i}>{x}</li>)}</ol>
                    <p className="mt-2 text-xs text-muted">{s.scenario.data_note} It takes about as long as the task itself, and you can save and come back.</p>
                  </>
                )}
                <div className="mt-4 flex flex-wrap gap-2">
                  <button className="btn btn-primary" disabled={busy} onClick={() => start(false)}><PlayCircle size={16} aria-hidden="true" /> Start my evaluation</button>
                  <button className="btn btn-soft" disabled={busy} onClick={() => start(true)}><FlaskConical size={14} aria-hidden="true" /> Practice run (not counted)</button>
                </div>
                {mine.data && mine.data.evaluations.length > 0 && (
                  <div className="mt-4"><p className="label">{can("manage_users") ? "Evaluations" : "My evaluations"}</p>
                    <ul className="space-y-1 text-sm">{mine.data.evaluations.map((e) => (
                      <li key={e.id}><Link className="text-royal underline" to={`/safety/impact/evaluations/${e.id}`}>{e.participant_code}</Link>
                        <span className="text-muted"> · {e.status === "submitted" ? "submitted" : "in progress"}{e.is_synthetic ? " · practice (not counted)" : ""}{e.task_date ? ` · ${formatDate(e.task_date)}` : ""}{!e.is_mine ? " · another member" : ""}</span></li>))}</ul></div>
                )}
              </Card>

              <Card title="What participants said" icon={<MessageSquareQuote size={16} aria-hidden="true" />}>
                {o.real_feedback.length === 0 ? <Quiet>No feedback yet. Every answer will appear here exactly as written, favorable or not.</Quiet> : (
                  <ul className="space-y-3">{o.real_feedback.map((f, i) => (
                    <li key={i} className="rounded-xl bg-ivory/80 px-3 py-2.5 text-sm">
                      <p className="font-semibold text-plum">{f.participant} <span className="text-xs font-normal text-muted">· {f.date ? formatDate(f.date) : ""}</span></p>
                      <p className="text-xs text-muted">Ease {f.answers.ease_of_use}/5 · usefulness {f.answers.usefulness}/5 · source confidence {f.answers.source_confidence}/5 · would use again: {ANSWER_LABELS[String(f.answers.would_use_again)]}</p>
                      {(["worked_well", "confusing", "improve_first", "comments"] as const).map((k) => f.answers[k] ? (
                        <p key={k} className="mt-1"><span className="text-xs font-semibold uppercase tracking-wide text-royal">{{ worked_well: "Worked well", confusing: "Confusing or frustrating", improve_first: "Improve first", comments: "Comments" }[k]}:</span> “{String(f.answers[k])}”</p>) : null)}
                    </li>))}</ul>
                )}
                {Object.keys(r.answers).length > 0 && r.completed_evaluations > 0 && (
                  <div className="mt-3 grid grid-cols-1 gap-1 text-xs text-muted sm:grid-cols-2">{s?.feedback_questions.filter((q) => q.kind !== "scale" && q.kind !== "text").map((q) => (
                    <p key={q.key}><b className="text-plum">{q.question}</b> {Object.entries(r.answers[q.key] ?? {}).map(([k, n]) => `${ANSWER_LABELS[k] ?? k}: ${n}`).join(" · ") || "—"}</p>))}</div>
                )}
              </Card>
            </div>

            <div className="space-y-5">
              <Card title="Historical learning" icon={<GitCompareArrows size={16} aria-hidden="true" />}>
                <p className="text-sm text-muted">The same planning request runs twice: without and with lessons from Our Legacy. The comparison shows what changed and which lesson each change came from; it does not assume the version with history is better.</p>
                <ul className="mt-3 space-y-1.5 text-sm">{o.history_comparisons.map((c) => (
                  <li key={c.id}><Link className="font-semibold text-royal underline" to={`/safety/impact/comparisons/${c.id}`}>Comparison #{c.id}</Link>
                    <span className="text-muted"> · runs #{c.run_a_id} / #{c.run_b_id} · {formatDate(c.date)}</span><span className="block text-xs text-muted">{c.request}</span></li>))}</ul>
                {o.history_comparisons.length === 0 && <Quiet>No comparison has been run yet.</Quiet>}
                {can("run_agents") && (
                  <button className="btn btn-soft mt-3 text-sm" disabled={busy || !scenario.data?.event_plan_id} onClick={runComparison}>
                    Run the comparison for the gala task</button>
                )}
                <p className="mt-1 text-xs text-muted">Uses two full planning runs (about $0.50 at the costs measured so far), within the usual spending limits.</p>
              </Card>

              <Card title="Calculations and assumptions" icon={<Sigma size={16} aria-hidden="true" />}>
                <ul className="space-y-1.5 text-sm text-ink">
                  <li><BasisTag kind="calculated" /> Minutes saved = usual-way minutes − SAM SPACE minutes (negative means SAM SPACE took longer).</li>
                  <li><BasisTag kind="calculated" /> Percentage = minutes saved ÷ usual-way minutes × 100, only when the usual-way time is above zero.</li>
                  <li><BasisTag kind="extrapolated" /> Hours per year = measured minutes saved × similar tasks per year ÷ 60.</li>
                </ul>
                <div className="mt-3 flex flex-wrap items-end gap-2 text-sm">
                  <div><label className="label" htmlFor="tasks">Similar tasks per year <BasisTag kind="assumption" /></label>
                    <input id="tasks" type="number" min={0} className="field !w-32" placeholder={String(o.assumptions.tasks_per_year ?? "not set")}
                      value={tasks} disabled={!o.assumptions.editable} onChange={(e) => setTasks(e.target.value)} /></div>
                  {o.assumptions.editable && <button className="btn btn-soft" disabled={tasks === ""} onClick={saveTasks}>Save</button>}
                </div>
                <p className="mt-1 text-xs text-muted">{o.assumptions.editable ? "Only the chair can change this." : "Set by the chair."} Currently: {o.assumptions.tasks_per_year ?? "not set"}.</p>
              </Card>

              <Card title="Evidence for the report" icon={<Download size={16} aria-hidden="true" />}>
                <p className="text-sm text-muted">Anonymized: participant codes only, unless someone chose to be named and allowed it.</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <a className="btn btn-soft text-sm" href="/api/impact/export.md">Summary (Markdown)</a>
                  <a className="btn btn-ghost text-sm" href="/api/impact/export" target="_blank" rel="noreferrer">All data (JSON)</a>
                </div>
              </Card>

              <Card title="Practice and test records" icon={<ListChecks size={16} aria-hidden="true" />}>
                <p className="text-sm text-muted"><Users size={13} className="mr-1 inline" aria-hidden="true" />{o.synthetic.completed_evaluations} submitted practice record(s), {o.synthetic.drafts_in_progress} in progress. {o.synthetic.note}</p>
              </Card>
            </div>
          </div>
        </>
      )}
      {toast && <Toast message={toast.message} tone={toast.tone} onDone={() => setToast(null)} />}
    </>
  );
}
