import { ArrowLeft, CheckCircle2, Clock, Heart, Link2, MessageSquareText, PenLine, Send, Sparkles, Timer, UserRound } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { ImpactEvaluation, ImpactScenario } from "../api/types";
import { formatDate, useApi } from "../api/useApi";
import { useButterflies } from "../butterflies/ButterflyProvider";
import { ANSWER_LABELS, AnalyticsTabs, BasisTag, fmtMin } from "../components/impactui";
import { Card, ErrorState, LoadingState, PageHeader, Toast } from "../components/ui";

type Draft = Record<string, string>;
const CHOICES: Record<string, string[]> = { yes_no_unsure: ["yes", "no", "unsure"], yes_no_editing: ["yes", "no", "needs_editing"],
  yes_no_maybe: ["yes", "no", "maybe"] };

function Step({ n, title, icon, done, children }: { n: number; title: string; icon: ReactNode; done?: boolean; children: ReactNode }) {
  return (
    <Card title={<span className="flex items-center gap-2">{n}. {title}{done && <CheckCircle2 size={16} className="text-sage" aria-label="done" />}</span>} icon={icon} className="mb-5">
      {children}
    </Card>
  );
}

function Elapsed({ since }: { since: string }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = window.setInterval(() => setNow(Date.now()), 15000); return () => window.clearInterval(t); }, []);
  return <span className="tabular-nums">{Math.max(0, Math.round((now - new Date(since).getTime()) / 60000))} min so far</span>;
}

export default function EvaluationPage() {
  const { id } = useParams();
  const { celebrate } = useButterflies();
  const scen = useApi<ImpactScenario>("/api/impact/scenario");
  const runs = useApi<{ runs: { id: number; workflow_type: string; status: string; started_at: string; spent_usd: number }[] }>("/api/runs");
  const [ev, setEv] = useState<ImpactEvaluation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [m, setM] = useState<Draft>({});
  const [a, setA] = useState<Draft>({});
  const [fb, setFb] = useState<Draft>({});
  const [mission, setMission] = useState<Draft>({});
  const [scores, setScores] = useState<Record<string, Record<string, string>>>({ manual: {}, assisted: {} });
  const [runId, setRunId] = useState("");
  const [toast, setToast] = useState<{ message: string; tone: "success" | "error" } | null>(null);
  const fbRef = useRef<HTMLButtonElement>(null);
  const submitRef = useRef<HTMLButtonElement>(null);

  const apply = useCallback((e: ImpactEvaluation) => {
    setEv(e);
    const s = (v: unknown) => (v == null ? "" : String(v));
    setM({ tools: e.manual.tools.join(", "), venues: s(e.manual.venues), verified_sources: s(e.manual.verified_sources),
      financial_model: s(e.manual.financial_model), history_used: s(e.manual.history_used), outreach_draft: s(e.manual.outreach_draft),
      difficulties: s(e.manual.difficulties), comments: s(e.manual.comments), minutes: s(e.manual.minutes), started_at: "", finished_at: "" });
    setA({ review_minutes: s(e.assisted.review_minutes), calculations_correct: s(e.assisted.calculations_correct),
      outreach_usefulness: s(e.assisted.outreach_usefulness), errors_encountered: s(e.assisted.errors_encountered),
      unsupported_claims_found: s(e.assisted.unsupported_claims_found), unsupported_claims_notes: s(e.assisted.unsupported_claims_notes),
      observations: s(e.assisted.observations), minutes: s(e.assisted.minutes) });
    setFb(Object.fromEntries(Object.entries(e.feedback ?? {}).map(([k, v]) => [k, String(v)])));
    setMission({ advances_mission: e.mission?.advances_mission ?? "", comment: e.mission?.comment ?? "", ...(e.mission?.dimensions ?? {}) });
    const sc: Record<string, Record<string, string>> = { manual: {}, assisted: {} };
    e.scores.forEach((x) => { (sc[x.condition] ??= {})[x.dimension] = String(x.score); });
    setScores(sc);
  }, []);

  const load = useCallback(async () => {
    try { apply((await api<{ evaluation: ImpactEvaluation }>(`/api/impact/evaluations/${id}`)).evaluation); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not load the evaluation."); }
  }, [id, apply]);
  useEffect(() => { load(); }, [load]);

  async function call(path: string, init: RequestInit & { json?: unknown }, ok?: string, anchor?: HTMLElement | null) {
    try {
      const res = await api<{ evaluation: ImpactEvaluation }>(path, init);
      apply(res.evaluation);
      if (ok) setToast({ message: ok, tone: "success" });
      if (anchor) celebrate("save", anchor);  // only after a successful save
      return true;
    } catch (e) {
      setToast({ message: e instanceof Error ? e.message : "Could not save.", tone: "error" });
      return false;
    }
  }

  if (error && !ev) return <ErrorState message={error} onRetry={load} />;
  if (!ev || !scen.data) return <LoadingState rows={4} />;
  const s = scen.data;
  const locked = ev.status === "submitted" || !ev.is_mine;
  const num = (v: string) => (v.trim() === "" ? null : Number(v));
  const bool = (v: string) => (v === "" ? null : v === "true");
  const timer = (part: string, action: string) => call(`/api/impact/evaluations/${ev.id}/timer`, { json: { part, action } });

  function saveManual() {
    const body: Record<string, unknown> = { manual_tools: m.tools.split(",").map((x) => x.trim()).filter(Boolean), manual_venues: num(m.venues),
      manual_verified_sources: num(m.verified_sources), manual_financial_model: bool(m.financial_model), manual_history_used: bool(m.history_used),
      manual_outreach_draft: bool(m.outreach_draft), manual_difficulties: m.difficulties, manual_comments: m.comments };
    if (m.started_at && m.finished_at) Object.assign(body, { manual_started_at: new Date(m.started_at).toISOString(), manual_finished_at: new Date(m.finished_at).toISOString() });
    else if (ev!.manual.status !== "completed" && m.minutes) body.manual_minutes = num(m.minutes);
    return call(`/api/impact/evaluations/${ev!.id}`, { method: "PUT", json: body }, "Saved. You can come back later.");
  }
  function saveAssisted() {
    const body: Record<string, unknown> = { review_minutes: num(a.review_minutes), calculations_correct: a.calculations_correct || null,
      outreach_usefulness: a.outreach_usefulness || null, errors_encountered: a.errors_encountered, unsupported_claims_found: num(a.unsupported_claims_found),
      unsupported_claims_notes: a.unsupported_claims_notes, assisted_observations: a.observations };
    if (ev!.assisted.status !== "completed" && a.minutes) body.assisted_minutes = num(a.minutes);
    return call(`/api/impact/evaluations/${ev!.id}`, { method: "PUT", json: body }, "Saved. You can come back later.");
  }
  function saveFeedback() {
    const f: Record<string, unknown> = {};
    s.feedback_questions.forEach((q) => { f[q.key] = q.kind === "scale" ? num(fb[q.key] ?? "") : (fb[q.key] ?? (q.kind === "text" ? "" : null)); });
    const dims = Object.fromEntries(s.mission_dimensions.filter((d) => mission[d.key]).map((d) => [d.key, mission[d.key]]));
    return call(`/api/impact/evaluations/${ev!.id}/feedback`, { json: { feedback: f, mission: { advances_mission: mission.advances_mission || null, dimensions: dims, comment: mission.comment ?? "" } } },
      "Thank you. Your feedback is saved exactly as written.", fbRef.current);
  }
  function saveScores(condition: "manual" | "assisted") {
    const sc = Object.fromEntries(Object.entries(scores[condition] ?? {}).filter(([, v]) => v !== "").map(([k, v]) => [k, Number(v)]));
    return call(`/api/impact/evaluations/${ev!.id}/scores`, { json: { condition, scores: sc } }, "Scores saved.");
  }

  const planRuns = (runs.data?.runs ?? []).filter((r) => r.workflow_type === "plan_event" && !["queued", "running"].includes(r.status));
  const rm = ev.assisted.run_metrics;
  const inputCls = "field";

  return (
    <>
      <Link to="/safety/impact" className="mb-4 inline-flex items-center gap-1 text-sm text-royal hover:underline"><ArrowLeft size={14} aria-hidden="true" /> Impact & Evaluation</Link>
      <PageHeader eyebrow={`Evaluation ${ev.participant_code}${ev.is_synthetic ? " · practice run (not counted)" : ""}`} title="Usual way vs. SAM SPACE"
        subtitle={s.scenario.task} />
      <AnalyticsTabs />
      {ev.is_synthetic && <p className="mb-4 rounded-xl bg-[#fbf1e3] px-3 py-2 text-sm text-amber">Practice run: kept apart from real results and never counted.</p>}
      {ev.status === "submitted" && <p className="mb-4 rounded-xl bg-[#e3f1e8] px-3 py-2 text-sm text-sage">Submitted {ev.submitted_at ? formatDate(ev.submitted_at) : ""}. Answers are kept as given and can no longer be changed.</p>}

      <fieldset disabled={locked}>
        <Step n={1} title="About this evaluation" icon={<UserRound size={16} aria-hidden="true" />} done>
          <p className="text-sm text-ink">You appear in reports as <b className="text-plum">{ev.display_name}</b>. Role: {ev.participant_role || "board member"} · date {ev.task_date ? formatDate(ev.task_date) : "—"}.</p>
          <div className="mt-2 space-y-1 text-sm">
            <label className="flex items-center gap-2"><input type="checkbox" checked={ev.show_name_in_reports}
              onChange={(e) => call(`/api/impact/evaluations/${ev.id}`, { method: "PUT", json: { show_name_in_reports: e.target.checked } })} /> Show my name in reports (otherwise only my code)</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={ev.attribution_permission}
              onChange={(e) => call(`/api/impact/evaluations/${ev.id}`, { method: "PUT", json: { attribution_permission: e.target.checked } })} /> I give permission to quote my comments with my name in the class report and slides</label>
          </div>
          <p className="mt-1 text-xs text-muted">Your name is shown only if both boxes are ticked. Please don't include private personal or donor details in your answers.</p>
        </Step>

        <Step n={2} title="Your usual way (manual baseline)" icon={<Clock size={16} aria-hidden="true" />} done={ev.manual.status === "completed" || ev.manual.status === "unavailable"}>
          <p className="text-sm text-muted">Do the task with your usual tools. Press Start when you begin and Finish when you'd share the draft with the board.</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {ev.manual.status !== "in_progress" && <button type="button" className="btn btn-soft" onClick={() => timer("manual", "start")}><Timer size={14} aria-hidden="true" /> Start</button>}
            {ev.manual.status === "in_progress" && <button type="button" className="btn btn-primary" onClick={() => timer("manual", "finish")}>Finish</button>}
            {ev.manual.status === "in_progress" && ev.manual.started_at && <span className="text-sm text-plum"><Elapsed since={ev.manual.started_at} /></span>}
            {ev.manual.status === "completed" && <span className="text-sm"><BasisTag kind="observed" /> <b className="text-plum">{fmtMin(ev.manual.minutes)}</b></span>}
            {ev.manual.status === "unavailable" && <span className="text-sm text-amber">Marked unavailable: no manual comparison will be counted.</span>}
            {ev.manual.status !== "unavailable" && <button type="button" className="btn btn-ghost text-sm" onClick={() => timer("manual", "unavailable")}>I can't do a manual comparison</button>}
          </div>
          <details className="mt-2 text-sm"><summary className="cursor-pointer text-royal">Already did it earlier? Enter the times</summary>
            <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
              <div><label className="label" htmlFor="m-start">Started</label><input id="m-start" type="datetime-local" className={inputCls} value={m.started_at} onChange={(e) => setM({ ...m, started_at: e.target.value })} /></div>
              <div><label className="label" htmlFor="m-end">Finished</label><input id="m-end" type="datetime-local" className={inputCls} value={m.finished_at} onChange={(e) => setM({ ...m, finished_at: e.target.value })} /></div>
              <div><label className="label" htmlFor="m-min">…or total minutes</label><input id="m-min" type="number" min={0} className={inputCls} value={m.minutes} onChange={(e) => setM({ ...m, minutes: e.target.value })} /></div>
            </div></details>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="sm:col-span-3"><label className="label" htmlFor="m-tools">Tools you used (comma-separated)</label><input id="m-tools" className={inputCls} placeholder="Google, Excel, past emails" value={m.tools} onChange={(e) => setM({ ...m, tools: e.target.value })} /></div>
            <div><label className="label" htmlFor="m-venues">Venue options found</label><input id="m-venues" type="number" min={0} className={inputCls} value={m.venues} onChange={(e) => setM({ ...m, venues: e.target.value })} /></div>
            <div><label className="label" htmlFor="m-src">Sources you checked</label><input id="m-src" type="number" min={0} className={inputCls} value={m.verified_sources} onChange={(e) => setM({ ...m, verified_sources: e.target.value })} /></div>
            {([["financial_model", "Financial model completed?"], ["history_used", "Past-event lessons used?"], ["outreach_draft", "Outreach draft written?"]] as const).map(([k, label]) => (
              <div key={k}><label className="label" htmlFor={`m-${k}`}>{label}</label>
                <select id={`m-${k}`} className={inputCls} value={m[k]} onChange={(e) => setM({ ...m, [k]: e.target.value })}><option value="">—</option><option value="true">Yes</option><option value="false">No</option></select></div>))}
            <div className="sm:col-span-3"><label className="label" htmlFor="m-diff">Major difficulties</label><textarea id="m-diff" rows={2} className={inputCls} value={m.difficulties} onChange={(e) => setM({ ...m, difficulties: e.target.value })} /></div>
            <div className="sm:col-span-3"><label className="label" htmlFor="m-com">Comments</label><textarea id="m-com" rows={2} className={inputCls} value={m.comments} onChange={(e) => setM({ ...m, comments: e.target.value })} /></div>
          </div>
          <div className="mt-3 flex justify-end"><button type="button" className="btn btn-primary" onClick={saveManual}>Save this step</button></div>
        </Step>

        <Step n={3} title="With SAM SPACE" icon={<Sparkles size={16} aria-hidden="true" />} done={ev.assisted.status === "completed"}>
          <p className="text-sm text-muted">Press Start, then open <Link className="text-royal underline" to="/events" target="_blank">Event Studio</Link> and plan the Manhattan Spring Gala. Read and correct the packet as you would before sharing it, then press Finish. Your reading and correcting time counts.</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {ev.assisted.status !== "in_progress" && <button type="button" className="btn btn-soft" onClick={() => timer("assisted", "start")}><Timer size={14} aria-hidden="true" /> Start</button>}
            {ev.assisted.status === "in_progress" && <button type="button" className="btn btn-primary" onClick={() => timer("assisted", "finish")}>Finish</button>}
            {ev.assisted.status === "in_progress" && ev.assisted.started_at && <span className="text-sm text-plum"><Elapsed since={ev.assisted.started_at} /></span>}
            {ev.assisted.status === "completed" && <span className="text-sm"><BasisTag kind="observed" /> <b className="text-plum">{fmtMin(ev.assisted.minutes)}</b> (your time, including review)</span>}
          </div>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <div><label className="label" htmlFor="a-run">Which planning run did you use?</label>
              <select id="a-run" className={`${inputCls} !w-72`} value={runId} onChange={(e) => setRunId(e.target.value)}>
                <option value="">Choose a run…</option>{planRuns.map((r) => <option key={r.id} value={r.id}>#{r.id} · {formatDate(r.started_at)} · ${r.spent_usd.toFixed(2)}</option>)}</select></div>
            <button type="button" className="btn btn-soft" disabled={!runId} onClick={() => call(`/api/impact/evaluations/${ev.id}/link-run`, { json: { run_id: Number(runId) } }, "Linked. These numbers come from the run's own logs.")}><Link2 size={14} aria-hidden="true" /> Link</button>
          </div>
          {rm && (
            <div className="mt-3 rounded-xl bg-ivory/80 p-3 text-sm">
              <p className="mb-1 flex items-center gap-2 font-semibold text-plum"><BasisTag kind="logs">From run #{rm.run_id}'s logs</BasisTag> <Link className="text-xs text-royal underline" to={`/activity/runs/${rm.run_id}`}>trace</Link></p>
              <ul className="grid grid-cols-1 gap-x-4 gap-y-0.5 sm:grid-cols-2">
                <li>Agents: {rm.agents_involved.map((x) => x.replace(/_/g, " ")).join(", ")}</li>
                <li>Venues: {rm.venues_considered} considered, {rm.venues_shortlisted} shortlisted</li>
                <li>Sources: {rm.sources_verified_live} verified live, {rm.sources_synthetic} synthetic demo</li>
                <li>Financial model complete: {rm.financial_model_complete ? "yes" : "no"} ({(rm.affordability_verdict ?? "—").replace(/_/g, " ")})</li>
                <li>All figures trace to calculations: {rm.figures_trace_to_calculations == null ? "—" : rm.figures_trace_to_calculations ? "yes" : "no"}</li>
                <li>Past events consulted: {rm.history_events_consulted} · lessons applied: {rm.lessons_applied}</li>
                <li>Outreach drafts: {rm.outreach_drafts} ({rm.drafts_unsent ? "all unsent" : "check status"})</li>
                <li>Agents' own time: {rm.model_execution_minutes} min · {rm.model_calls} model calls · ${rm.cost_usd.toFixed(4)}</li>
              </ul>
              <p className="mt-1 text-xs text-muted">The agents' time is not your task time; your Start–Finish time above is what the comparison uses.</p>
            </div>
          )}
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div><label className="label" htmlFor="a-review">Minutes spent reviewing and correcting</label><input id="a-review" type="number" min={0} className={inputCls} value={a.review_minutes} onChange={(e) => setA({ ...a, review_minutes: e.target.value })} /></div>
            <div><label className="label" htmlFor="a-calc">Were the calculations correct?</label>
              <select id="a-calc" className={inputCls} value={a.calculations_correct} onChange={(e) => setA({ ...a, calculations_correct: e.target.value })}><option value="">—</option><option value="yes">Yes</option><option value="no">No</option><option value="unsure">Unsure</option></select></div>
            <div><label className="label" htmlFor="a-draft">The outreach draft was…</label>
              <select id="a-draft" className={inputCls} value={a.outreach_usefulness} onChange={(e) => setA({ ...a, outreach_usefulness: e.target.value })}><option value="">—</option><option value="usable">Usable</option><option value="needs_editing">Usable after editing</option><option value="not_usable">Not usable</option></select></div>
            <div><label className="label" htmlFor="a-unsup">Unsupported claims you found</label><input id="a-unsup" type="number" min={0} className={inputCls} value={a.unsupported_claims_found} onChange={(e) => setA({ ...a, unsupported_claims_found: e.target.value })} /></div>
            <div className="sm:col-span-2"><label className="label" htmlFor="a-unsup-n">Which claims?</label><input id="a-unsup-n" className={inputCls} value={a.unsupported_claims_notes} onChange={(e) => setA({ ...a, unsupported_claims_notes: e.target.value })} /></div>
            <div className="sm:col-span-3"><label className="label" htmlFor="a-err">Errors you ran into</label><textarea id="a-err" rows={2} className={inputCls} value={a.errors_encountered} onChange={(e) => setA({ ...a, errors_encountered: e.target.value })} /></div>
            <div className="sm:col-span-3"><label className="label" htmlFor="a-obs">Observations</label><textarea id="a-obs" rows={2} className={inputCls} value={a.observations} onChange={(e) => setA({ ...a, observations: e.target.value })} /></div>
            {ev.assisted.status !== "completed" && <div><label className="label" htmlFor="a-min">…or total minutes (if timed elsewhere)</label><input id="a-min" type="number" min={0} className={inputCls} value={a.minutes} onChange={(e) => setA({ ...a, minutes: e.target.value })} /></div>}
          </div>
          <div className="mt-3 flex justify-end"><button type="button" className="btn btn-primary" onClick={saveAssisted}>Save this step</button></div>
        </Step>

        <Step n={4} title="Quality: score both proposals the same way" icon={<PenLine size={16} aria-hidden="true" />} done={ev.scores.length > 0}>
          <p className="mb-2 text-sm text-muted">0 = missing · 1 = weak · 2 = adequate · 3 = good · 4 = excellent. {s.scoring_note}</p>
          <div className="-mx-2 overflow-x-auto"><table className="w-full min-w-[560px] text-sm">
            <thead><tr className="text-left text-xs uppercase tracking-wider text-muted"><th className="px-2 py-1">Dimension</th><th className="px-2">Usual way</th><th className="px-2">SAM SPACE</th></tr></thead>
            <tbody>{s.rubric.map((d) => (
              <tr key={d.key} className="border-t border-lavender/25"><td className="px-2 py-1.5"><b className="text-plum">{d.label}</b><span className="block text-xs text-muted">{d.question}</span></td>
                {(["manual", "assisted"] as const).map((c) => (
                  <td key={c} className="px-2"><select aria-label={`${d.label}, ${c === "manual" ? "usual way" : "SAM SPACE"}`} className="field !w-20 !py-1" value={scores[c]?.[d.key] ?? ""}
                    onChange={(e) => setScores({ ...scores, [c]: { ...scores[c], [d.key]: e.target.value } })}><option value="">—</option>{[0, 1, 2, 3, 4].map((n) => <option key={n} value={n}>{n}</option>)}</select></td>))}</tr>))}</tbody>
          </table></div>
          <div className="mt-3 flex flex-wrap justify-end gap-2">
            <button type="button" className="btn btn-soft" onClick={() => saveScores("manual")}>Save usual-way scores</button>
            <button type="button" className="btn btn-soft" onClick={() => saveScores("assisted")}>Save SAM SPACE scores</button>
          </div>
        </Step>

        <Step n={5} title="Your feedback" icon={<MessageSquareText size={16} aria-hidden="true" />} done={!!ev.feedback_saved_at}>
          <ol className="grid grid-cols-1 gap-3 sm:grid-cols-2">{s.feedback_questions.map((q, i) => (
            <li key={q.key} className={q.kind === "text" ? "sm:col-span-2" : ""}>
              <p className="label">{i + 1}. {q.question}</p>
              {q.kind === "scale" && <div className="flex gap-1.5" role="radiogroup" aria-label={q.question}>{[1, 2, 3, 4, 5].map((n) => (
                <label key={n} className={`grid h-9 w-9 cursor-pointer place-items-center rounded-full text-sm font-semibold ${fb[q.key] === String(n) ? "bg-plum text-white" : "bg-lilac/60 text-plum"}`}>
                  <input type="radio" className="sr-only" name={q.key} checked={fb[q.key] === String(n)} onChange={() => setFb({ ...fb, [q.key]: String(n) })} />{n}</label>))}
                <span className="ml-1 self-center text-xs text-muted">1 = not at all · 5 = very</span></div>}
              {CHOICES[q.kind] && <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label={q.question}>{CHOICES[q.kind].map((c) => (
                <label key={c} className={`cursor-pointer rounded-full px-3 py-1 text-sm font-semibold ${fb[q.key] === c ? "bg-plum text-white" : "bg-lilac/60 text-plum"}`}>
                  <input type="radio" className="sr-only" name={q.key} checked={fb[q.key] === c} onChange={() => setFb({ ...fb, [q.key]: c })} />{ANSWER_LABELS[c]}</label>))}</div>}
              {q.kind === "text" && <textarea rows={2} className={inputCls} aria-label={q.question} value={fb[q.key] ?? ""} onChange={(e) => setFb({ ...fb, [q.key]: e.target.value })} />}
            </li>))}</ol>
          <div className="mt-5 rounded-2xl bg-lilac/30 p-4">
            <p className="flex items-center gap-2 font-display text-lg font-semibold text-plum"><Heart size={16} className="text-rose" aria-hidden="true" /> “Be somebody who makes everybody feel like somebody.”</p>
            <p className="mt-1 text-sm text-muted">Did SAM SPACE's recommendations support these parts of the mission? Your judgment only; nothing here is turned into a statistic about how guests felt.</p>
            <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">{s.mission_dimensions.map((d) => (
              <label key={d.key} className="flex items-center justify-between gap-2 text-sm"><span className="text-plum">{d.label}</span>
                <select className="field !w-40 !py-1" value={mission[d.key] ?? ""} onChange={(e) => setMission({ ...mission, [d.key]: e.target.value })}>
                  <option value="">—</option><option value="yes">Yes</option><option value="somewhat">Somewhat</option><option value="no">No</option><option value="not_applicable">Not applicable</option></select></label>))}</div>
            <p className="label mt-3">Does SAM SPACE help preserve and advance the foundation's mission?</p>
            <div className="flex gap-1.5">{["yes", "no", "unsure"].map((c) => (
              <label key={c} className={`cursor-pointer rounded-full px-3 py-1 text-sm font-semibold ${mission.advances_mission === c ? "bg-plum text-white" : "bg-white text-plum ring-1 ring-lavender/50"}`}>
                <input type="radio" className="sr-only" name="advances" checked={mission.advances_mission === c} onChange={() => setMission({ ...mission, advances_mission: c })} />{ANSWER_LABELS[c]}</label>))}</div>
            <textarea rows={2} className={`${inputCls} mt-2`} aria-label="Mission comment" placeholder="Why? (optional)" value={mission.comment ?? ""} onChange={(e) => setMission({ ...mission, comment: e.target.value })} />
          </div>
          <div className="mt-3 flex justify-end"><button ref={fbRef} type="button" className="btn btn-primary" onClick={saveFeedback}>Save my feedback</button></div>
        </Step>

        <Step n={6} title="Review and submit" icon={<Send size={16} aria-hidden="true" />} done={ev.status === "submitted"}>
          <div className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-4">
            <p>Usual way: <b className="text-plum">{ev.manual.status === "unavailable" ? "unavailable" : fmtMin(ev.comparison.manual_minutes)}</b></p>
            <p>With SAM SPACE: <b className="text-plum">{fmtMin(ev.comparison.assisted_minutes)}</b></p>
            <p>Minutes saved: <b className="text-plum">{fmtMin(ev.comparison.minutes_saved)}</b> <BasisTag kind="calculated" /></p>
            <p>Change: <b className="text-plum">{ev.comparison.pct_reduction == null ? "—" : `${ev.comparison.pct_reduction}%`}</b></p>
          </div>
          <p className="mt-2 text-xs text-muted">A negative number means SAM SPACE took longer; that is a useful result too.</p>
          <div className="mt-3 flex justify-end">
            <button ref={submitRef} type="button" className="btn btn-primary" onClick={() => call(`/api/impact/evaluations/${ev.id}/submit`, { method: "POST" }, "Submitted. Thank you for helping the foundation learn.", submitRef.current)}>Submit evaluation</button>
          </div>
        </Step>
      </fieldset>
      {toast && <Toast message={toast.message} tone={toast.tone} onDone={() => setToast(null)} />}
    </>
  );
}
