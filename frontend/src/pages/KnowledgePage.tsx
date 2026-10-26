import { ArrowLeft, BookHeart, CheckCircle2, Download, Eye, FileUp, Link2, Pencil, Plus, Search, Trash2, Undo2 } from "lucide-react";
import { useCallback, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { KnowledgeBase, KnowledgeEntry, KnowledgePreview, KnowledgeVerification } from "../api/types";
import { formatDate, useApi } from "../api/useApi";
import { AGENT_LABELS } from "../components/agents";
import { Card, DemoBadge, EmptyState, ErrorState, LoadingState, PageHeader, Toast } from "../components/ui";

const TONE: Record<KnowledgeVerification, string> = {
  verified: "bg-sage/20 text-[#2f6b4f] border-sage/40",
  board_reported: "bg-lilac text-royal border-lavender/50",
  estimate: "bg-amber/15 text-[#8a5a12] border-amber/40",
  needs_confirmation: "bg-blush text-rose border-rose/40",
  demo: "bg-ivory text-muted border-lavender/40",
};

function StatusPill({ status, label }: { status: KnowledgeVerification; label: string }) {
  return <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[0.7rem] font-semibold uppercase tracking-wide ${TONE[status]}`}>{label}</span>;
}

type Draft = {
  id?: number; section: string; title: string; body: string; details: Record<string, string>; aliases: string; source: string;
  source_url: string; verification: Exclude<KnowledgeVerification, "demo">; share_externally: boolean; historical_event_id: string;
};

const blank = (section: string): Draft => ({ section, title: "", body: "", details: {}, aliases: "", source: "", source_url: "",
  verification: "board_reported", share_externally: false, historical_event_id: "" });

const fromEntry = (e: KnowledgeEntry): Draft => ({
  id: e.id, section: e.section, title: e.title, body: e.body,
  details: Object.fromEntries(Object.entries(e.details).filter(([k]) => k !== "core").map(([k, v]) => [k, Array.isArray(v) ? v.join("; ") : String(v)])),
  aliases: e.aliases.join(", "), source: e.source, source_url: e.source_url ?? "",
  verification: e.verification === "demo" ? "board_reported" : e.verification, share_externally: e.share_externally,
  historical_event_id: e.historical_event_id ? String(e.historical_event_id) : "",
});

function EntryForm({ kb, draft, onCancel, onSaved }: { kb: KnowledgeBase; draft: Draft; onCancel: () => void; onSaved: (msg: string) => void }) {
  const [d, setD] = useState<Draft>(draft);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const section = kb.sections.find((s) => s.key === d.section)!;
  const core = draft.id ? kb.entries.find((e) => e.id === draft.id)?.details.core : undefined;

  async function submit(ev: FormEvent) {
    ev.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      section: d.section, title: d.title, body: d.body, source: d.source, source_url: d.source_url || null,
      details: { ...Object.fromEntries(Object.entries(d.details).filter(([, v]) => v.trim())), ...(core ? { core: true } : {}) },
      aliases: d.aliases.split(",").map((a) => a.trim()).filter(Boolean), verification: d.verification,
      share_externally: d.share_externally, historical_event_id: d.historical_event_id ? Number(d.historical_event_id) : null,
    };
    try {
      await api(d.id ? `/api/knowledge/${d.id}` : "/api/knowledge", { method: d.id ? "PUT" : "POST", json: body });
      onSaved(d.id ? "Fact corrected" : "Fact added");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  const input = "w-full rounded-xl border border-lavender/50 bg-white px-3 py-2 text-sm focus:border-royal focus:outline-none";
  return (
    <form onSubmit={submit} className="space-y-4 rounded-2xl border border-royal/30 bg-white/90 p-4 sm:p-5" aria-label={d.id ? "Correct a fact" : "Add a fact"}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="text-sm font-semibold text-plum">Section
          <select className={`${input} mt-1`} value={d.section} onChange={(e) => setD({ ...d, section: e.target.value })}>
            {kb.sections.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
        </label>
        <label className="text-sm font-semibold text-plum">Name or title
          <input className={`${input} mt-1`} required minLength={2} maxLength={200} value={d.title} onChange={(e) => setD({ ...d, title: e.target.value })}
            placeholder="e.g. Annual Gala, a vendor's name, an organization" />
        </label>
      </div>
      <p className="text-xs text-muted">{section.hint}</p>
      <label className="block text-sm font-semibold text-plum">In a few sentences
        <textarea className={`${input} mt-1 min-h-[4.5rem]`} maxLength={4000} value={d.body} onChange={(e) => setD({ ...d, body: e.target.value })} />
      </label>
      <fieldset className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <legend className="mb-1 text-sm font-semibold text-plum">Details (leave blank what you don't know; nothing is guessed)</legend>
        {section.fields.map((f) => (
          <label key={f.key} className="text-xs font-semibold uppercase tracking-wide text-muted">{f.label}
            <input className={`${input} mt-1 normal-case tracking-normal`} value={d.details[f.key] ?? ""}
              onChange={(e) => setD({ ...d, details: { ...d.details, [f.key]: e.target.value } })} />
          </label>
        ))}
      </fieldset>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="text-sm font-semibold text-plum">Source
          <input className={`${input} mt-1`} maxLength={300} value={d.source} onChange={(e) => setD({ ...d, source: e.target.value })}
            placeholder="Who or what this comes from (a board member, a receipt, a record)" />
        </label>
        <label className="text-sm font-semibold text-plum">Source link (optional)
          <input className={`${input} mt-1`} type="url" value={d.source_url} onChange={(e) => setD({ ...d, source_url: e.target.value })} />
        </label>
        <label className="text-sm font-semibold text-plum">Other names (comma-separated)
          <input className={`${input} mt-1`} value={d.aliases} onChange={(e) => setD({ ...d, aliases: e.target.value })} placeholder="e.g. an acronym" />
        </label>
        <label className="text-sm font-semibold text-plum">Our Legacy record (optional)
          <select className={`${input} mt-1`} value={d.historical_event_id} onChange={(e) => setD({ ...d, historical_event_id: e.target.value })}>
            <option value="">None</option>
            {kb.legacy_events.map((ev) => <option key={ev.id} value={ev.id}>{ev.name}</option>)}
          </select>
        </label>
        <label className="text-sm font-semibold text-plum">How sure are we?
          <select className={`${input} mt-1`} value={d.verification} onChange={(e) => setD({ ...d, verification: e.target.value as Draft["verification"] })}>
            <option value="board_reported">Board-reported (a board member says so)</option>
            <option value="estimate">Approximate (a rough figure)</option>
            <option value="needs_confirmation">Needs confirmation</option>
            {kb.can_verify && <option value="verified">Verified (confirmed against a record)</option>}
          </select>
        </label>
        <label className="flex items-start gap-2 self-end rounded-xl bg-lilac/50 px-3 py-2 text-sm text-plum">
          <input type="checkbox" className="mt-1" checked={d.share_externally} onChange={(e) => setD({ ...d, share_externally: e.target.checked })} />
          <span>May appear in outreach drafts. Leave off for costs, internal notes, and anything about people.</span>
        </label>
      </div>
      {error && <p className="text-sm text-danger" role="alert">{error}</p>}
      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>Cancel</button>
        <button className="btn btn-primary" disabled={busy}>{busy ? "Saving…" : d.id ? "Save correction" : "Add fact"}</button>
      </div>
    </form>
  );
}

function EntryCard({ e, kb, onEdit, onChanged }: { e: KnowledgeEntry; kb: KnowledgeBase; onEdit: () => void; onChanged: (msg: string) => void }) {
  const labels = Object.fromEntries((kb.sections.find((s) => s.key === e.section)?.fields ?? []).map((f) => [f.key, f.label]));
  const details = Object.entries(e.details).filter(([k, v]) => k !== "core" && v !== "" && v != null);
  async function setStatus(v: string) {
    await api(`/api/knowledge/${e.id}/verify`, { method: "POST", json: { verification: v } });
    onChanged(v === "verified" ? "Marked verified" : "Status updated");
  }
  async function remove() {
    const reason = window.prompt("Why is this fact being removed? (kept for the record)");
    if (!reason || reason.trim().length < 3) return;
    await api(`/api/knowledge/${e.id}/remove`, { method: "POST", json: { reason } });
    onChanged("Removed. Agents no longer see it.");
  }
  async function restore() {
    await api(`/api/knowledge/${e.id}/restore`, { method: "POST" });
    onChanged("Restored");
  }
  return (
    <li id={`kb-${e.id}`} className={`rounded-2xl border p-4 ${e.status === "removed" ? "border-dashed border-lavender/60 bg-ivory/50 opacity-75" : "border-lavender/40 bg-white/85"}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold text-plum">{e.title} <span className="ml-1 text-xs font-normal text-muted">{e.code}</span></p>
          {e.body && <p className="mt-1 text-sm text-ink/85">{e.body}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {e.is_demo ? <DemoBadge label="Sample" /> : <StatusPill status={e.verification} label={e.verification_label} />}
          {e.share_externally && <span className="rounded-full bg-white px-2 py-0.5 text-[0.68rem] font-semibold text-royal ring-1 ring-lavender/50">Shareable</span>}
          {e.status === "active" && e.used_by_agents === false && <span className="rounded-full bg-ivory px-2 py-0.5 text-[0.68rem] text-muted ring-1 ring-lavender/40" title="Real facts in this section replace the samples">Not used (replaced)</span>}
        </div>
      </div>
      {details.length > 0 && (
        <dl className="mt-3 grid grid-cols-1 gap-x-5 gap-y-1.5 text-sm sm:grid-cols-2">
          {details.map(([k, v]) => (
            <div key={k} className="min-w-0"><dt className="text-[0.68rem] font-semibold uppercase tracking-wide text-muted">{labels[k] ?? k.replace(/_/g, " ")}</dt>
              <dd className="break-words text-ink/90">{Array.isArray(v) ? v.join("; ") : v}</dd></div>
          ))}
        </dl>
      )}
      <p className="mt-3 text-xs text-muted">
        Source: {e.source || "not recorded"}{e.source_url && <> · <a className="text-royal hover:underline" href={e.source_url} target="_blank" rel="noreferrer">link</a></>}
        {" · "}Added by {e.contributor || "—"} {e.recorded_at && <>on {formatDate(e.recorded_at)}</>}
        {e.updated_at && e.updated_at !== e.recorded_at && <> · Updated {formatDate(e.updated_at)} by {e.updated_by}</>}
        {e.verified_by && <> · Verified by {e.verified_by}</>}
        {e.historical_event_id && <> · <Link className="text-royal hover:underline" to={`/legacy/${e.historical_event_id}`}><Link2 size={11} className="inline" aria-hidden="true" /> {e.historical_event_name}</Link></>}
      </p>
      {e.status === "removed" && <p className="mt-1 text-xs text-rose">Removed: {e.removed_reason}</p>}
      <div className="mt-3 flex flex-wrap gap-2">
        {e.status === "active" && kb.can_edit && <button className="btn btn-ghost !py-1 text-xs" onClick={onEdit}><Pencil size={12} aria-hidden="true" /> Correct</button>}
        {e.status === "active" && kb.can_verify && !e.is_demo && (
          <select aria-label={`Status of ${e.title}`} className="rounded-lg border border-lavender/50 bg-white px-2 py-1 text-xs" value={e.verification}
            onChange={(ev) => setStatus(ev.target.value)}>
            {(["verified", "board_reported", "estimate", "needs_confirmation"] as const).map((v) => <option key={v} value={v}>{kb.verification_labels[v]}</option>)}
          </select>
        )}
        {e.status === "active" && kb.can_verify && <button className="btn btn-ghost !py-1 text-xs text-rose" onClick={remove}><Trash2 size={12} aria-hidden="true" /> Remove</button>}
        {e.status === "removed" && kb.can_verify && <button className="btn btn-ghost !py-1 text-xs" onClick={restore}><Undo2 size={12} aria-hidden="true" /> Restore</button>}
      </div>
    </li>
  );
}

function RetrievalPreview({ kb }: { kb: KnowledgeBase }) {
  const [agent, setAgent] = useState("fundraising_events");
  const [query, setQuery] = useState("Plan our next gala");
  const [out, setOut] = useState<KnowledgePreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function run(ev: FormEvent) {
    ev.preventDefault();
    setError(null);
    try {
      setOut(await api<KnowledgePreview>(`/api/knowledge/preview?agent=${encodeURIComponent(agent)}&query=${encodeURIComponent(query)}`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not preview");
    }
  }
  return (
    <Card title="What an agent would see" icon={<Eye size={16} aria-hidden="true" />}>
      <p className="mb-3 text-sm text-muted">Agents never get the whole knowledge base. Try a task to see exactly which facts the shared retrieval service hands one agent (no AI call, no cost).</p>
      <form onSubmit={run} className="flex flex-col gap-2 sm:flex-row">
        <select aria-label="Agent" className="rounded-xl border border-lavender/50 bg-white px-3 py-2 text-sm" value={agent} onChange={(e) => setAgent(e.target.value)}>
          {kb.agents.map((a) => <option key={a} value={a}>{AGENT_LABELS[a] ?? a}</option>)}
        </select>
        <input aria-label="Task" className="min-w-0 flex-1 rounded-xl border border-lavender/50 bg-white px-3 py-2 text-sm" value={query} minLength={3}
          onChange={(e) => setQuery(e.target.value)} />
        <button className="btn btn-soft"><Search size={14} aria-hidden="true" /> Preview</button>
      </form>
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}
      {out && (
        <div className="mt-4">
          <p className="text-xs text-muted">{out.returned} of {out.considered} facts in this agent's sections · about {out.est_tokens} tokens of context</p>
          {out.facts.length === 0 ? <p className="mt-2 text-sm text-muted">Nothing recorded bears on this task, so the agent works from its own data alone.</p> : (
            <ol className="mt-2 space-y-2">
              {out.facts.map((f) => (
                <li key={f.id} className="rounded-xl bg-ivory/70 px-3 py-2 text-sm">
                  <p className="flex flex-wrap items-center gap-2"><b className="text-plum">{f.id} · {f.title}</b>
                    <StatusPill status={f.sample ? "demo" : f.verification} label={f.sample ? "Sample" : kb.verification_labels[f.verification]} />
                    <span className="text-xs text-muted">{f.why}</span></p>
                  <p className="mt-0.5 text-ink/80">{f.fact}</p>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </Card>
  );
}

export default function KnowledgePage() {
  const [showRemoved, setShowRemoved] = useState(false);
  const { data: kb, error, loading, reload } = useApi<KnowledgeBase>(`/api/knowledge${showRemoved ? "?include_removed=true" : ""}`);
  const [section, setSection] = useState("signature_events");
  const [editing, setEditing] = useState<Draft | null>(null);
  const [legacyId, setLegacyId] = useState("");
  const [toast, setToast] = useState<{ message: string; tone: "success" | "error" } | null>(null);
  const clearToast = useCallback(() => setToast(null), []);
  const done = (message: string) => { setEditing(null); setToast({ message, tone: "success" }); reload(); };
  const fail = (e: unknown) => setToast({ message: e instanceof Error ? e.message : "Something went wrong", tone: "error" });

  const bySection = useMemo(() => {
    const m: Record<string, KnowledgeEntry[]> = {};
    kb?.entries.forEach((e) => { (m[e.section] ??= []).push(e); });
    // Real facts first, then samples, then removed facts.
    const rank = (e: KnowledgeEntry) => (e.status === "removed" ? 2 : e.is_demo ? 1 : 0);
    Object.values(m).forEach((list) => list.sort((a, b) => rank(a) - rank(b) || a.id - b.id));
    return m;
  }, [kb]);

  async function fromLegacy() {
    if (!legacyId) return;
    try {
      await api(`/api/knowledge/from-legacy/${legacyId}`, { method: "POST" });
      setLegacyId("");
      setSection("past_fundraisers");
      done("Linked from Our Legacy");
    } catch (e) { fail(e); }
  }

  async function importFile(file: File) {
    try {
      const parsed = JSON.parse(await file.text());
      const got = await api<{ added: number; updated: number }>("/api/knowledge/import", { method: "POST", json: { entries: parsed.entries ?? [] } });
      done(`Imported: ${got.added} added, ${got.updated} updated`);
    } catch (e) { fail(e); }
  }

  const current = kb?.sections.find((s) => s.key === section);
  const real = kb ? kb.entries.filter((e) => !e.is_demo && e.status === "active").length : 0;
  return (
    <>
      <Link to="/settings" className="mb-3 inline-flex items-center gap-1 text-sm font-semibold text-royal hover:underline"><ArrowLeft size={14} aria-hidden="true" /> Settings</Link>
      <PageHeader eyebrow="Settings" title="Foundation Knowledge Base"
        subtitle="What SAM SPACE knows about the Sabrina Audrey Milone Foundation: its history, events, vendors, relationships, community, and board. Each agent reads only the facts its task needs."
        actions={kb && (<>
          {kb.can_edit && <button className="btn btn-primary" onClick={() => setEditing(blank(section))}><Plus size={15} aria-hidden="true" /> Add a fact</button>}
          <Link className="btn btn-soft" to="/legacy?add=1"><FileUp size={15} aria-hidden="true" /> Upload records</Link>
          <a className="btn btn-ghost" href="/api/knowledge/template" download="foundation_knowledge_template.json"><Download size={15} aria-hidden="true" /> Blank template</a>
        </>)} />
      {loading && !kb && <LoadingState rows={4} />}
      {error && <ErrorState message={error.message} onRetry={reload} />}
      {kb && (
        <>
          <section aria-label="Verification summary" className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-5">
            {(["verified", "board_reported", "estimate", "needs_confirmation", "demo"] as const).map((v) => (
              <div key={v} className="rounded-2xl border border-lavender/35 bg-white/85 p-3">
                <p className="text-[0.7rem] font-semibold uppercase tracking-wider text-muted">{kb.verification_labels[v]}</p>
                <p className="font-display text-2xl font-semibold text-plum">{kb.counts[v] ?? 0}</p>
              </div>
            ))}
          </section>

          {editing && <div className="mb-5"><EntryForm key={editing.id ?? `new-${editing.section}`} kb={kb} draft={editing} onCancel={() => setEditing(null)} onSaved={done} /></div>}

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-[15rem_minmax(0,1fr)]">
            <nav aria-label="Knowledge sections" className="lg:sticky lg:top-6 lg:self-start">
              <ul className="flex gap-1.5 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible">
                {kb.sections.map((s) => {
                  const n = (bySection[s.key] ?? []).filter((e) => e.status === "active" && !e.is_demo).length;
                  return (
                    <li key={s.key} className="shrink-0">
                      <button onClick={() => setSection(s.key)} aria-current={section === s.key}
                        className={`flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left text-sm transition ${section === s.key ? "bg-royal text-white" : "bg-white/80 text-plum hover:bg-lilac"}`}>
                        <span>{s.label}</span><span className={`text-xs ${section === s.key ? "text-white/80" : "text-muted"}`}>{n}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
              <label className="mt-3 flex items-center gap-2 text-xs text-muted"><input type="checkbox" checked={showRemoved} onChange={(e) => setShowRemoved(e.target.checked)} /> Show removed facts</label>
            </nav>

            <div className="min-w-0 space-y-5">
              {current && (
                <Card title={current.label} icon={<BookHeart size={16} aria-hidden="true" />}
                  action={kb.can_edit ? <button className="btn btn-ghost !py-1 text-sm" onClick={() => setEditing(blank(current.key))}><Plus size={13} aria-hidden="true" /> Add</button> : undefined}>
                  <p className="mb-4 text-sm text-muted">{current.hint}</p>
                  {current.key === "past_fundraisers" && kb.can_edit && (
                    <div className="mb-4 flex flex-col gap-2 rounded-2xl bg-lilac/40 p-3 sm:flex-row sm:items-center">
                      <span className="text-sm text-plum">Bring in an Our Legacy record:</span>
                      <select aria-label="Our Legacy record" className="min-w-0 flex-1 rounded-xl border border-lavender/50 bg-white px-3 py-1.5 text-sm" value={legacyId} onChange={(e) => setLegacyId(e.target.value)}>
                        <option value="">Choose a past event…</option>
                        {kb.legacy_events.map((ev) => <option key={ev.id} value={ev.id}>{ev.name}</option>)}
                      </select>
                      <button className="btn btn-soft !py-1.5 text-sm" onClick={fromLegacy} disabled={!legacyId}>Link it</button>
                    </div>
                  )}
                  {(bySection[current.key] ?? []).length === 0 ? (
                    <EmptyState title="Nothing recorded yet">Add what the board knows. Leave out anything you're unsure of, or mark it "Needs confirmation".</EmptyState>
                  ) : (
                    <ul className="space-y-3">
                      {(bySection[current.key] ?? []).map((e) => (
                        <EntryCard key={e.id} e={e} kb={kb} onEdit={() => setEditing(fromEntry(e))} onChanged={(m) => done(m)} />
                      ))}
                    </ul>
                  )}
                </Card>
              )}

              <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
                <Card title="Missing information" icon={<CheckCircle2 size={16} aria-hidden="true" />}>
                  {kb.gaps.length === 0 ? <p className="text-sm text-muted">Nothing obvious is missing.</p> : (
                    <ul className="space-y-1.5 text-sm">
                      {kb.gaps.map((g, i) => (
                        <li key={i} className="flex gap-2"><span className="shrink-0 text-xs font-semibold uppercase tracking-wide text-royal">{g.section}</span>
                          <span className="text-ink/85">{g.detail}</span></li>
                      ))}
                    </ul>
                  )}
                  <p className="mt-3 text-xs text-muted">{real} real fact{real === 1 ? "" : "s"} recorded. Samples stand in only for sections with no real facts.</p>
                </Card>
                {kb.financial_sources && (
                  <Card title="Which financial data is real" icon={<CheckCircle2 size={16} aria-hidden="true" />}>
                    <p className="text-sm text-ink/90">{kb.financial_sources.ledger.statement}</p>
                    <dl className="mt-3 space-y-2 text-sm">
                      {([["Verified history", kb.financial_sources.verified_history], ["Board estimates", kb.financial_sources.board_estimates],
                         ["Authorized budgets", kb.financial_sources.authorized_budgets]] as const).map(([label, items]) => (
                        <div key={label}><dt className="text-[0.68rem] font-semibold uppercase tracking-wide text-muted">{label}</dt>
                          <dd className="text-ink/85">{items.length ? items.join("; ") : "None recorded"}</dd></div>
                      ))}
                    </dl>
                    <p className="mt-3 text-xs text-muted">{kb.financial_sources.rule}</p>
                  </Card>
                )}
              </div>

              <RetrievalPreview kb={kb} />

              {kb.can_verify && (
                <Card title="Import a filled-in template">
                  <p className="mb-3 text-sm text-muted">Download the blank template, fill it in, and import it here. Keep the filled-in file off GitHub: real facts stay in this app's local database.</p>
                  <input type="file" accept="application/json,.json" aria-label="Template file" className="text-sm"
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) importFile(f); e.target.value = ""; }} />
                </Card>
              )}
            </div>
          </div>
        </>
      )}
      {toast && <Toast message={toast.message} tone={toast.tone} onDone={clearToast} />}
    </>
  );
}
