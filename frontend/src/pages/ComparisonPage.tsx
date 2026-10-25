import { ArrowLeft, BookOpenCheck, GitCompareArrows, PenLine, Scale } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { HistoryComparison, ImpactScenario } from "../api/types";
import { formatDate, useApi } from "../api/useApi";
import { AnalyticsTabs, Quiet } from "../components/impactui";
import { Card, ErrorState, LoadingState, PageHeader, Toast } from "../components/ui";

const VERDICT: Record<string, string> = {
  "changed, with supporting lessons": "bg-[#e3f1e8] text-sage", "different, but no specific lesson identified": "bg-[#fbf1e3] text-amber",
  "no history-attributed change": "bg-ivory text-muted ring-1 ring-lavender/40", "not addressed by either": "bg-white text-muted ring-1 ring-lavender/40",
};
const money = (v: number | null, measure: string) => v == null ? "—" : measure === "Contingency" ? `${Math.round(v * 100)}%`
  : measure.includes("USD") ? `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : String(v);

export default function ComparisonPage() {
  const { id } = useParams();
  const scen = useApi<ImpactScenario>("/api/impact/scenario");
  const [c, setC] = useState<HistoryComparison | null>(null);
  const [state, setState] = useState<{ status: string; error: string | null } | null>(null);
  const [scores, setScores] = useState<Record<string, Record<string, string>>>({ without_history: {}, with_history: {} });
  const [toast, setToast] = useState<{ message: string; tone: "success" | "error" } | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await api<{ comparison: HistoryComparison | null; status: string; error: string | null }>(`/api/impact/history-comparisons/${id}`);
      setState({ status: res.status, error: res.error });
      if (res.comparison) setC(res.comparison);
      return res.status;
    } catch (e) {
      setState({ status: "error", error: e instanceof Error ? e.message : "Could not load." });
      return "error";
    }
  }, [id]);
  useEffect(() => {
    let stop = false;
    const tick = async () => { const st = await load(); if (!stop && (st === "running" || st === "queued")) window.setTimeout(tick, 4000); };
    tick();
    return () => { stop = true; };
  }, [load]);

  async function save(condition: "without_history" | "with_history") {
    const sc = Object.fromEntries(Object.entries(scores[condition]).filter(([, v]) => v !== "").map(([k, v]) => [k, Number(v)]));
    try {
      await api(`/api/impact/history-comparisons/${id}/scores`, { json: { condition, scores: sc } });
      setToast({ message: "Scores saved.", tone: "success" });
      load();
    } catch (e) {
      setToast({ message: e instanceof Error ? e.message : "Could not save.", tone: "error" });
    }
  }

  if (!state) return <LoadingState rows={4} />;
  if (state.status === "error") return <ErrorState message={state.error ?? "Could not load."} onRetry={load} />;
  return (
    <>
      <Link to="/safety/impact" className="mb-4 inline-flex items-center gap-1 text-sm text-royal hover:underline"><ArrowLeft size={14} aria-hidden="true" /> Impact & Evaluation</Link>
      <PageHeader eyebrow={`Historical learning · comparison #${id}`} title="Without vs. with Our Legacy"
        subtitle={c ? c.request : "The two planning runs are in progress. This page updates when both finish."} />
      <AnalyticsTabs />
      {!c && <Card><p className="flex items-center gap-2 text-sm text-plum"><span className="h-2 w-2 animate-pulse rounded-full bg-royal" aria-hidden="true" />Running both plans ({state.status})…{state.error && <span className="text-danger"> {state.error}</span>}</p></Card>}
      {c && (
        <>
          <div className="mb-5 grid gap-3 md:grid-cols-2">
            {(["without_history", "with_history"] as const).map((k) => {
              const r = c.runs[k];
              return (
                <div key={k} className="rounded-2xl bg-white/85 p-4 ring-1 ring-lavender/40">
                  <p className="eyebrow">{k === "without_history" ? "A · without historical knowledge" : "B · with historical knowledge"}</p>
                  <p className="mt-1 font-display text-xl font-semibold text-plum">{r?.headline ?? "—"}</p>
                  <p className="mt-1 text-xs text-muted">Run <Link className="text-royal underline" to={`/activity/runs/${r?.run_id}`}>#{r?.run_id}</Link> · {r?.models?.join(", ")} · {r?.usage.model_calls} calls ·
                    {" "}{(r?.usage.input_tokens ?? 0).toLocaleString()} in / {(r?.usage.output_tokens ?? 0).toLocaleString()} out · ${r?.usage.cost_usd.toFixed(4)} · {r?.duration_s}s</p>
                </div>);
            })}
          </div>

          <Card title="What changed, and why" icon={<GitCompareArrows size={16} aria-hidden="true" />} className="mb-5">
            <p className="mb-3 text-sm text-ink">{c.summary.unique_statements_changed} statement(s) that the agents attributed to past events rest on a specific lesson, touching {c.summary.dimensions_changed_with_support} of {c.dimensions.length} areas;
              {" "}{c.summary.statements_different_without_lesson} attributed to history rest on no specific lesson; {c.summary.other_differences} other wording difference(s) may be ordinary run-to-run variation and are not counted. Budget figures {c.summary.budget_numbers_changed ? "changed" : "did not change"}.</p>
            <div className="space-y-3">{c.dimensions.map((d, di) => (
              <details key={d.key} className="rounded-2xl bg-ivory/70 p-3" open={di === 0}>
                <summary className="flex cursor-pointer flex-wrap items-center gap-2"><b className="text-plum">{d.label}</b>
                  <span className={`rounded-full px-2 py-0.5 text-[0.7rem] font-semibold ${VERDICT[d.verdict]}`}>{d.verdict}</span></summary>
                {d.changed_by_history.length > 0 && (
                  <ul className="mt-2 space-y-2">{d.changed_by_history.slice(0, 3).map((x, i) => (
                    <li key={i} className="rounded-xl bg-white px-3 py-2 text-sm ring-1 ring-lavender/30">
                      <p className="text-ink"><span className="mr-1 rounded bg-[#e3f1e8] px-1.5 text-[0.65rem] font-semibold uppercase text-sage">only with history</span>{x.statement}</p>
                      {x.supported_by.slice(0, 1).map((sp, j) => (
                        <p key={j} className="mt-1 text-xs text-muted"><BookOpenCheck size={12} className="mr-1 inline text-royal" aria-hidden="true" />
                          {sp.kind === "lesson" ? "Lesson" : "History constraint"}: “{sp.text}”{sp.events?.length ? ` (${sp.events.join(", ")})` : ""}</p>))}
                    </li>))}</ul>
                )}
                {d.changed_by_history.length > 3 && <p className="mt-1 text-xs text-muted">…and {d.changed_by_history.length - 3} more (all in the exported evidence).</p>}
                {d.other_differences > 0 && <p className="mt-2 text-xs text-muted">{d.other_differences} other statement(s) in B differ from A without being attributed to history (possible run-to-run variation; not counted).</p>}
                {d.different_without_specific_lesson.length > 0 && (
                  <div className="mt-2"><p className="text-xs font-semibold text-amber">Different in B, but no specific lesson found (not counted as an improvement):</p>
                    <ul className="list-disc pl-5 text-xs text-muted">{d.different_without_specific_lesson.slice(0, 4).map((x, i) => <li key={i}>{x.statement}</li>)}</ul></div>
                )}
                <div className="mt-2 grid gap-2 text-xs md:grid-cols-2">
                  <div><p className="font-semibold text-plum">A said ({d.without_history.length})</p><ul className="list-disc pl-5 text-muted">{d.without_history.slice(0, 4).map((x, i) => <li key={i}>{x}</li>)}</ul>{!d.without_history.length && <p className="text-muted">—</p>}</div>
                  <div><p className="font-semibold text-plum">B said ({d.with_history.length})</p><ul className="list-disc pl-5 text-muted">{d.with_history.slice(0, 4).map((x, i) => <li key={i}>{x}</li>)}</ul>{!d.with_history.length && <p className="text-muted">—</p>}</div>
                </div>
              </details>))}</div>
            <p className="mt-3 text-xs text-muted">{c.method_note}</p>
          </Card>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Budget figures (computed in code)" icon={<Scale size={16} aria-hidden="true" />}>
              <table className="w-full text-sm"><thead><tr className="text-left text-xs uppercase tracking-wider text-muted"><th className="py-1">Measure</th><th>A</th><th>B</th></tr></thead>
                <tbody>{c.numbers.map((n) => (
                  <tr key={n.measure} className="border-t border-lavender/25"><td className="py-1.5">{n.measure}</td><td>{money(n.without_history, n.measure)}</td>
                    <td className={n.changed ? "font-semibold text-royal" : ""}>{money(n.with_history, n.measure)}</td></tr>))}</tbody></table>
              <p className="mt-3 label">Past events B consulted</p>
              {c.events_consulted.length ? <ul className="text-sm">{c.events_consulted.map((e) => <li key={e.id}><Link className="text-royal underline" to={`/legacy/${e.id}`}>{e.name}</Link> <span className="text-xs text-muted">{e.reasons.join(" · ")}</span></li>)}</ul>
                : <Quiet>This comparison ran before past events were ranked by similarity.</Quiet>}
              <p className="mt-2 text-xs text-muted">Same request, event plan, research data, and strategy for both runs. {c.inputs.same_inputs_note}</p>
            </Card>

            <Card title="Overall quality: a person decides" icon={<PenLine size={16} aria-hidden="true" />}>
              <p className="mb-2 text-sm text-muted">Score both recommendations with the same rubric (0–4). Nothing is scored automatically, and B is not assumed to be better.</p>
              {Object.keys(c.human_scores).length > 0 && <p className="mb-2 text-sm">Saved: {Object.entries(c.human_scores).map(([k, v]) => `${k === "with_history" ? "B" : "A"} ${Object.values(v).reduce((x, y) => x + y, 0)}/${4 * Object.keys(v).length}`).join(" · ")}</p>}
              <table className="w-full text-sm"><thead><tr className="text-left text-xs uppercase tracking-wider text-muted"><th className="py-1">Dimension</th><th>A</th><th>B</th></tr></thead>
                <tbody>{scen.data?.rubric.map((d) => (
                  <tr key={d.key} className="border-t border-lavender/25"><td className="py-1">{d.label}</td>
                    {(["without_history", "with_history"] as const).map((k) => (
                      <td key={k}><select aria-label={`${d.label} ${k}`} className="field !w-16 !py-0.5" value={scores[k][d.key] ?? (c.human_scores[k]?.[d.key] != null ? String(c.human_scores[k][d.key]) : "")}
                        onChange={(e) => setScores({ ...scores, [k]: { ...scores[k], [d.key]: e.target.value } })}><option value="">—</option>{[0, 1, 2, 3, 4].map((n) => <option key={n}>{n}</option>)}</select></td>))}</tr>))}</tbody></table>
              <div className="mt-3 flex justify-end gap-2"><button className="btn btn-soft text-sm" onClick={() => save("without_history")}>Save A</button><button className="btn btn-soft text-sm" onClick={() => save("with_history")}>Save B</button></div>
            </Card>
          </div>

          <Card title={`Lessons available to B (${c.lessons.length})`} icon={<BookOpenCheck size={16} aria-hidden="true" />} className="mt-5">
            <ul className="space-y-1.5 text-sm">{c.lessons.map((l, i) => <li key={i} className="rounded-xl bg-ivory/70 px-3 py-1.5">{l.text} <span className="text-xs text-muted">({l.events.join(", ") || `${l.reflection_ids.length} reflection(s)`})</span></li>)}</ul>
            <p className="mt-2 text-xs text-muted">Compared {formatDate(c.date)} · research data: {c.research_mode}.</p>
          </Card>
        </>
      )}
      {toast && <Toast message={toast.message} tone={toast.tone} onDone={() => setToast(null)} />}
    </>
  );
}
