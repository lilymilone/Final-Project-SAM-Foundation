import { AlertTriangle, ArrowLeft, CheckCircle2, ClipboardCheck, FileSearch, ListChecks, Scale, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { LegacyEvent, LegacyImport, SourcedField, SourcedItem } from "../api/types";
import { formatDate, usd } from "../api/useApi";
import { useButterflies } from "../butterflies/ButterflyProvider";
import { StatusPill } from "../components/agents";
import { DocumentList, OriginBadge } from "../components/legacyImport";
import { Card, ErrorState, LoadingState, PageHeader } from "../components/ui";

type Values = Record<string, string>;
const GROUPS: { title: string; fields: { key: string; label: string; type?: "number" | "date" | "textarea" }[] }[] = [
  { title: "The event", fields: [
    { key: "name", label: "Event title" }, { key: "event_date", label: "Date", type: "date" }, { key: "event_year", label: "Year", type: "number" },
    { key: "location", label: "Location" }, { key: "venue", label: "Venue" }, { key: "event_type", label: "Type" },
    { key: "summary", label: "Description", type: "textarea" }] },
  { title: "Figures (optional; leave blank when unknown)", fields: [
    { key: "attendance", label: "Attendance", type: "number" }, { key: "fundraising_goal_usd", label: "Fundraising goal (USD)", type: "number" },
    { key: "funds_raised_usd", label: "Revenue / funds raised (USD)", type: "number" }, { key: "total_cost_usd", label: "Expenses (USD)", type: "number" },
    { key: "sponsorship_usd", label: "Sponsorship (USD)", type: "number" }, { key: "planned_budget_usd", label: "Planned budget (USD)", type: "number" },
    { key: "volunteers_count", label: "Volunteers", type: "number" }, { key: "sponsorship_info", label: "Sponsors" }] },
  { title: "What happened", fields: [
    { key: "positive_outcomes", label: "What worked", type: "textarea" }, { key: "problems_encountered", label: "What did not work", type: "textarea" },
    { key: "lessons_learned", label: "Lessons learned", type: "textarea" }] },
];
const NUMBERS = new Set(["event_year", "attendance", "fundraising_goal_usd", "funds_raised_usd", "total_cost_usd", "sponsorship_usd", "planned_budget_usd", "volunteers_count"]);
const LISTS = new Set(["positive_outcomes", "problems_encountered", "lessons_learned"]);

type Overwrite = { field: string; label: string; current: unknown; proposed: unknown };

export default function ImportReviewPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { celebrate } = useButterflies();
  const [imp, setImp] = useState<LegacyImport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [values, setValues] = useState<Values>({});
  const [resolved, setResolved] = useState<Record<string, boolean>>({});
  const [target, setTarget] = useState<"new" | "existing">("new");
  const [sample, setSample] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [overwrites, setOverwrites] = useState<Overwrite[] | null>(null);
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});
  const saveRef = useRef<HTMLButtonElement>(null);

  const load = useCallback(async () => {
    try {
      const res = await api<{ import: LegacyImport }>(`/api/legacy/imports/${id}`);
      setImp(res.import);
      if (res.import.status !== "extracting") {
        setValues(Object.fromEntries(Object.entries(res.import.candidate).map(([k, v]) => [k, v == null ? "" : String(v)])));
        setTarget(res.import.target_event ? "existing" : "new");
      }
      return res.import;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the import.");
      return null;
    }
  }, [id]);

  useEffect(() => {
    let stop = false;
    const tick = async () => {
      const got = await load();
      if (!stop && got?.status === "extracting") window.setTimeout(tick, 1500);
    };
    tick();
    return () => { stop = true; };
  }, [load]);

  if (error && !imp) return <ErrorState message={error} onRetry={load} />;
  if (!imp) return <LoadingState rows={4} />;
  const ex = imp.extraction;
  const fields = ex?.fields ?? {};
  const lists = ex?.lists;
  const conflicts = ex?.conflicts ?? [];
  const decided = imp.status === "approved" || imp.status === "discarded";

  function body(confirm: string[] = []) {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(values)) {
      const t = v.trim();
      out[k] = t === "" ? null : NUMBERS.has(k) ? Number(t) : t;
    }
    return {
      fields: out, target_event_id: target === "existing" ? imp!.target_event?.id ?? null : null,
      resolved_conflicts: Object.keys(resolved).filter((k) => resolved[k]), confirm_overwrite: confirm, mark_as_sample: sample,
    };
  }

  async function approve(confirm: string[] = []) {
    setSaving(true);
    setSaveError(null);
    try {
      const res = await api<{ event: LegacyEvent; created: boolean }>(`/api/legacy/imports/${imp!.id}/approve`, { json: body(confirm) });
      celebrate("save", saveRef.current);
      window.setTimeout(() => navigate(`/legacy/${res.event.id}`), 700);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && e.detail && typeof e.detail === "object" && "items" in e.detail) {
        const items = (e.detail as { items: Overwrite[] }).items;
        if (items.length && "current" in items[0]) {
          setOverwrites(items);
          setConfirmed(Object.fromEntries(items.map((i) => [i.field, false])));
        }
      }
      setSaveError(e instanceof Error ? e.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  async function discard() {
    await api(`/api/legacy/imports/${imp!.id}/discard`, { method: "POST" }).catch(() => undefined);
    load();
  }

  const net = values.funds_raised_usd && values.total_cost_usd ? Number(values.funds_raised_usd) - Number(values.total_cost_usd) : null;

  function sourceLine(key: string) {
    if (LISTS.has(key)) {
      const items: SourcedItem[] = lists?.[key as keyof typeof lists] ?? [];
      if (!items.length) return <OriginBadge origin="missing" />;
      return (
        <span className="flex flex-col gap-0.5">
          {items.map((i, n) => (
            <span key={n} className="flex flex-wrap items-center gap-1.5 text-[0.7rem] text-muted">
              <OriginBadge origin={i.origin} /><span className="italic">“{i.quote}”</span><span>· {i.source_label}</span>
            </span>
          ))}
        </span>
      );
    }
    const f: SourcedField | undefined = fields[key];
    const conflict = conflicts.find((c) => c.field === key);
    if (conflict) return <span className="text-[0.7rem] font-semibold text-amber">Sources disagree: choose below</span>;
    if (!f) return <OriginBadge origin="missing" />;
    return (
      <span className="flex flex-wrap items-center gap-1.5 text-[0.7rem] text-muted">
        <OriginBadge origin={f.origin} /><span className="italic">“{f.quote}”</span><span>· {f.source_label}{f.also_in?.length ? `, also ${f.also_in.join(", ")}` : ""}</span>
        {f.note && <span className="text-amber">{f.note}</span>}
      </span>
    );
  }

  const edited = (key: string) => String(imp.candidate[key] ?? "") !== (values[key] ?? "");

  return (
    <>
      <Link to="/legacy" className="mb-4 inline-flex items-center gap-1 text-sm text-royal hover:underline"><ArrowLeft size={14} aria-hidden="true" /> Our Legacy</Link>
      <PageHeader eyebrow={`Our Legacy · Import #${imp.id}`} title="Review before saving"
        subtitle="These are candidates read from your sources by the Event Intelligence agent and checked against the exact words they came from. They are not verified accounting data. Edit anything, then approve." />

      {imp.status === "extracting" && (
        <Card className="mb-5"><p className="flex items-center gap-2 text-sm text-plum"><span className="h-2 w-2 animate-pulse rounded-full bg-royal" aria-hidden="true" />
          Reading the sources and checking every value against them…{imp.run && <Link className="ml-2 text-royal underline" to={`/activity/runs/${imp.run.id}`}>view the agent trace</Link>}</p></Card>
      )}
      {imp.status === "failed" && <div className="mb-5"><ErrorState message={imp.run?.error || "The extraction did not finish. You can discard this import and try again."} /></div>}
      {decided && (
        <Card className="mb-5"><p className="flex items-center gap-2 text-sm text-plum"><CheckCircle2 size={16} className="text-sage" aria-hidden="true" />
          This import was {imp.status}.{imp.approved_event_id && <Link className="text-royal underline" to={`/legacy/${imp.approved_event_id}`}>Open the event</Link>}</p></Card>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <div className="space-y-5">
          {conflicts.length > 0 && !decided && (
            <Card title="Sources disagree" icon={<Scale size={16} aria-hidden="true" />}>
              <p className="mb-3 text-sm text-muted">SAM SPACE never picks between conflicting figures. Choose the right one, type another, or leave it blank.</p>
              {conflicts.map((c) => (
                <fieldset key={c.field} className="mb-3 rounded-xl border border-amber/30 bg-[#fbf1e3]/60 p-3">
                  <legend className="px-1 text-sm font-semibold text-plum">{c.label}</legend>
                  {c.values.map((v, i) => (
                    <label key={i} className="flex items-start gap-2 py-1 text-sm">
                      <input type="radio" name={`c-${c.field}`} checked={values[c.field] === String(v.value) && !!resolved[c.field]}
                        onChange={() => { setValues((s) => ({ ...s, [c.field]: String(v.value) })); setResolved((r) => ({ ...r, [c.field]: true })); }} />
                      <span><b>{v.value.toLocaleString()}</b> <span className="text-muted">from {v.source_label}: “{v.quote}”</span></span>
                    </label>
                  ))}
                  <label className="flex items-center gap-2 py-1 text-sm">
                    <input type="radio" name={`c-${c.field}`} checked={!!resolved[c.field] && !c.values.some((v) => String(v.value) === values[c.field])}
                      onChange={() => { setValues((s) => ({ ...s, [c.field]: "" })); setResolved((r) => ({ ...r, [c.field]: true })); }} />
                    Leave blank (or type a value in the form below)
                  </label>
                </fieldset>
              ))}
            </Card>
          )}

          {ex && (
            <Card title="Editable preview" icon={<ClipboardCheck size={16} aria-hidden="true" />}>
              {ex.summary && <p className="mb-4 text-sm text-ink">{ex.summary}</p>}
              {GROUPS.map((g) => (
                <fieldset key={g.title} className="mb-5" disabled={decided}>
                  <legend className="mb-2 font-display text-lg font-semibold text-plum">{g.title}</legend>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {g.fields.map((f) => (
                      <div key={f.key} className={f.type === "textarea" ? "sm:col-span-2" : ""}>
                        <label className="label flex items-center gap-2" htmlFor={`f-${f.key}`}>{f.label}
                          {edited(f.key) && <span className="rounded-full bg-ivory px-1.5 text-[0.65rem] font-semibold normal-case text-plum ring-1 ring-lavender/50">edited</span>}</label>
                        {f.type === "textarea" ? (
                          <textarea id={`f-${f.key}`} rows={LISTS.has(f.key) ? 3 : 2} className="field" value={values[f.key] ?? ""}
                            onChange={(e) => setValues((s) => ({ ...s, [f.key]: e.target.value }))} />
                        ) : (
                          <input id={`f-${f.key}`} className="field" type={f.type ?? "text"} min={f.type === "number" ? 0 : undefined} value={values[f.key] ?? ""}
                            onChange={(e) => {
                              setValues((s) => ({ ...s, [f.key]: e.target.value }));
                              if (conflicts.some((c) => c.field === f.key)) setResolved((r) => ({ ...r, [f.key]: true }));
                            }} />
                        )}
                        <div className="mt-1">{sourceLine(f.key)}</div>
                        {target === "existing" && imp.target_event && imp.target_event.values[f.key] != null && imp.target_event.values[f.key] !== "" && (
                          <p className="mt-0.5 text-[0.7rem] text-muted">Currently recorded: <b>{String(imp.target_event.values[f.key])}</b></p>
                        )}
                      </div>
                    ))}
                  </div>
                </fieldset>
              ))}
              <p className="text-sm text-muted">Net proceeds (always calculated from revenue and expenses): <b className="text-plum">{net == null ? "—" : usd(net)}</b></p>
            </Card>
          )}
        </div>

        <div className="space-y-5">
          <Card title="Sources" icon={<FileSearch size={16} aria-hidden="true" />}>
            {imp.raw_text && (
              <blockquote className="mb-3 rounded-xl bg-ivory/80 px-3 py-2 text-sm italic text-ink">“{imp.raw_text}”
                <span className="mt-1 block text-[0.7rem] not-italic text-muted">Your description, kept exactly as written · {formatDate(imp.created_at)}</span></blockquote>
            )}
            <DocumentList docs={imp.documents} />
            {(ex?.injection_flags ?? 0) > 0 && (
              <p className="mt-3 flex items-start gap-2 rounded-xl bg-[#fbeef3] px-3 py-2 text-xs text-plum"><AlertTriangle size={14} className="mt-0.5 shrink-0 text-danger" aria-hidden="true" />
                {ex!.injection_flags} instruction-like sentence(s) in the sources were removed before the AI read them, and were not followed.</p>
            )}
            {imp.run && <p className="mt-3 flex items-center gap-2 text-xs text-muted"><StatusPill status={imp.run.status} />
              <Link className="text-royal underline" to={`/activity/runs/${imp.run.id}`}>Agent trace #{imp.run.id}</Link> · ${imp.run.spent_usd?.toFixed(4) ?? "0.0000"}</p>}
          </Card>

          {ex && (
            <Card title="What's missing or left out" icon={<ListChecks size={16} aria-hidden="true" />}>
              {ex.missing.length > 0 ? (
                <><p className="label">Not in the sources (left blank, never guessed)</p>
                  <ul className="mb-3 flex flex-wrap gap-1.5">{ex.missing.map((m) => <li key={m} className="rounded-full bg-white px-2 py-0.5 text-xs text-muted ring-1 ring-lavender/40">{m}</li>)}</ul></>
              ) : <p className="mb-3 text-sm text-muted">All key details were found.</p>}
              {ex.warnings.map((w, i) => <p key={i} className="mb-2 rounded-xl bg-[#fbf1e3] px-3 py-2 text-xs text-amber">{w}</p>)}
              {ex.dropped.length > 0 && (
                <details className="text-xs text-muted"><summary className="cursor-pointer font-semibold text-plum">{ex.dropped.length} AI suggestion(s) removed by code</summary>
                  <ul className="mt-1 list-disc space-y-0.5 pl-5">{ex.dropped.map((d, i) => <li key={i}>{d}</li>)}</ul></details>
              )}
            </Card>
          )}

          {ex && !decided && (
            <Card title="Save to Our Legacy" icon={<CheckCircle2 size={16} aria-hidden="true" />}>
              <fieldset className="space-y-1.5 text-sm">
                <label className="flex items-center gap-2"><input type="radio" checked={target === "new"} onChange={() => setTarget("new")} /> Create a new past event</label>
                {imp.target_event && (
                  <label className="flex items-center gap-2"><input type="radio" checked={target === "existing"} onChange={() => setTarget("existing")} />
                    Add to “{imp.target_event.name}” (blank fields keep what's recorded)</label>
                )}
                <label className="mt-2 flex items-center gap-2"><input type="checkbox" checked={sample} onChange={(e) => setSample(e.target.checked)} />
                  This is a sample or test record, not a real foundation event</label>
              </fieldset>
              {saveError && <p role="alert" className="mt-3 text-sm text-danger">{saveError}</p>}
              <div className="mt-4 flex flex-wrap justify-end gap-2">
                <button type="button" className="btn btn-ghost" onClick={discard}><Trash2 size={14} aria-hidden="true" /> Discard</button>
                <button ref={saveRef} type="button" className="btn btn-primary" disabled={saving || imp.status !== "ready"} onClick={() => approve()}>
                  {saving ? "Saving…" : "Approve and save"}</button>
              </div>
              <p className="mt-2 text-xs text-muted">Each saved value keeps its source and quote. Approving does not mark figures as verified; the treasurer can do that on the event page.</p>
            </Card>
          )}
        </div>
      </div>

      {overwrites && (
        <div role="dialog" aria-modal="true" aria-labelledby="ow-title" className="fixed inset-0 z-50 grid place-items-center bg-plum/40 p-4">
          <div className="card w-full max-w-lg p-6">
            <h2 id="ow-title" className="font-display text-2xl font-semibold text-plum">Change recorded values?</h2>
            <p className="mt-1 text-sm text-muted">These values are already recorded for “{imp.target_event?.name}”. Tick each one you want to replace.</p>
            <ul className="mt-3 space-y-2">{overwrites.map((o) => (
              <li key={o.field} className="rounded-xl bg-ivory px-3 py-2 text-sm">
                <label className="flex items-start gap-2"><input type="checkbox" checked={!!confirmed[o.field]} onChange={(e) => setConfirmed((c) => ({ ...c, [o.field]: e.target.checked }))} />
                  <span><b className="text-plum">{o.label}</b>: {String(o.current)} → <b>{String(o.proposed)}</b></span></label>
              </li>))}</ul>
            <div className="mt-4 flex justify-end gap-2">
              <button className="btn btn-ghost" onClick={() => setOverwrites(null)}>Go back</button>
              <button className="btn btn-primary" disabled={!overwrites.every((o) => confirmed[o.field])}
                onClick={() => { const c = overwrites.map((o) => o.field); setOverwrites(null); approve(c); }}>Replace and save</button>
            </div>
            <p className="mt-2 text-xs text-muted">Every change is written to the audit log with the before and after values.</p>
          </div>
        </div>
      )}
    </>
  );
}
