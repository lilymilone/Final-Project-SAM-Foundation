import { Archive, BookmarkCheck, BookmarkPlus, Check, Copy, ExternalLink, FileText, Lightbulb, MapPin, MailX, Pencil } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Draft, LessonRow, ResearchFindingRow, VenueCandidateRow } from "../api/types";
import { useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { VerificationBadge, money } from "./agents";
import { Card, DemoBadge, EmptyState, ErrorState, LoadingState } from "./ui";

// ── Drafts (never sent) ─────────────────────────────────────────────────────────

function DraftItem({ draft, onChange }: { draft: Draft; onChange: () => void }) {
  const { can } = useAuth();
  const [editing, setEditing] = useState(false);
  const [subject, setSubject] = useState(draft.subject);
  const [body, setBody] = useState(draft.body);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);

  async function save(patch: Partial<Draft>) {
    setBusy(true);
    try {
      await api(`/api/drafts/${draft.id}`, { method: "PUT", json: patch });
      setEditing(false);
      onChange();
    } finally {
      setBusy(false);
    }
  }
  async function copy() {
    await navigator.clipboard?.writeText(`Subject: ${subject}\n\n${body}`).catch(() => undefined);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }

  return (
    <li className="rounded-2xl border border-lavender/35 bg-white/80 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">{draft.draft_type.replace(/_/g, " ")} · to {draft.recipient_org || draft.recipient_name}</p>
          {editing ? <input className="field mt-1" value={subject} onChange={(e) => setSubject(e.target.value)} aria-label="Subject" />
            : <p className="font-display text-lg font-semibold text-plum">{draft.subject}</p>}
        </div>
        <div className="flex items-center gap-1.5">
          {draft.is_synthetic_target && <DemoBadge label="Synthetic recipient" />}
          <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${draft.status === "reviewed" ? "bg-[#e3f1e8] text-sage" : "bg-lilac text-plum"}`}>{draft.status === "reviewed" ? "Reviewed" : "Unsent draft"}</span>
        </div>
      </div>
      {editing ? <textarea className="field mt-2 font-mono text-sm" rows={9} value={body} onChange={(e) => setBody(e.target.value)} aria-label="Draft body" />
        : <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap rounded-xl bg-ivory p-3 font-sans text-sm text-ink">{draft.body}</pre>}
      {draft.personalization_basis && <p className="mt-2 text-xs text-muted">Personalized from: {draft.personalization_basis}</p>}
      {can("run_agents") && (
        <div className="mt-3 flex flex-wrap gap-2">
          {editing ? (
            <>
              <button className="btn btn-primary !py-1.5 text-sm" disabled={busy} onClick={() => save({ subject, body })}>Save edits</button>
              <button className="btn btn-ghost !py-1.5 text-sm" onClick={() => { setEditing(false); setSubject(draft.subject); setBody(draft.body); }}>Cancel</button>
            </>
          ) : (
            <>
              <button className="btn btn-soft !py-1.5 text-sm" onClick={() => setEditing(true)}><Pencil size={13} aria-hidden="true" /> Edit</button>
              <button className="btn btn-soft !py-1.5 text-sm" onClick={copy}>{copied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />} {copied ? "Copied" : "Copy text"}</button>
              {draft.status !== "reviewed" && <button className="btn btn-soft !py-1.5 text-sm" disabled={busy} onClick={() => save({ status: "reviewed" })}><Check size={13} aria-hidden="true" /> Mark reviewed</button>}
              <button className="btn btn-ghost !py-1.5 text-sm" disabled={busy} onClick={() => save({ status: "archived" })}><Archive size={13} aria-hidden="true" /> Archive</button>
            </>
          )}
        </div>
      )}
    </li>
  );
}

export function DraftsPanel({ kind, title }: { kind: "outreach" | "donor"; title: string }) {
  const { data, error, loading, reload } = useApi<{ drafts: Draft[] }>(`/api/drafts?kind=${kind}`);
  return (
    <Card title={title} icon={<FileText size={16} aria-hidden="true" />}>
      <p className="mb-3 flex items-start gap-2 rounded-xl bg-lilac/50 px-3 py-2 text-xs text-plum">
        <MailX size={14} className="mt-0.5 shrink-0" aria-hidden="true" /> SAM SPACE has no way to send mail. Edit a draft, copy it, and send it yourself if the board agrees.
      </p>
      {loading && <LoadingState rows={2} />}
      {error && <ErrorState message={error.message} onRetry={reload} />}
      {data && (data.drafts.length === 0 ? <EmptyState title="No drafts yet">Run the agents and their drafts will wait here for your review.</EmptyState> : (
        <ul className="space-y-3">{data.drafts.map((d) => <DraftItem key={d.id} draft={d} onChange={reload} />)}</ul>
      ))}
    </Card>
  );
}

// ── Research findings ───────────────────────────────────────────────────────────

export function FindingsPanel() {
  const { can } = useAuth();
  const { data, error, loading, reload, setData } = useApi<{ findings: ResearchFindingRow[] }>("/api/findings");
  async function toggle(f: ResearchFindingRow) {
    const res = await api<{ saved: boolean }>(`/api/findings/${f.id}/save`, { json: { saved: !f.saved } });
    setData((d) => d && { findings: d.findings.map((x) => (x.id === f.id ? { ...x, saved: res.saved } : x)) });
  }
  return (
    <Card title="Opportunities found" icon={<BookmarkPlus size={16} aria-hidden="true" />}>
      {loading && <LoadingState rows={2} />}
      {error && <ErrorState message={error.message} onRetry={reload} />}
      {data && (data.findings.length === 0 ? <EmptyState title="No research yet">Ask Mission Discovery a question to find organizations, research, and events with their sources.</EmptyState> : (
        <ul className="space-y-3">{data.findings.map((f) => (
          <li key={f.id} className={`rounded-2xl border p-4 ${f.saved ? "border-royal bg-lilac/40" : "border-lavender/35 bg-white/80"}`}>
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="mb-1 flex flex-wrap items-center gap-1.5">
                  <VerificationBadge value={f.verification} />
                  {f.alignment && <span className="rounded-full bg-ivory px-2 py-0.5 text-[0.7rem] font-semibold capitalize text-royal ring-1 ring-lavender/40">{f.alignment} alignment</span>}
                  <span className="text-xs capitalize text-muted">{f.category}{f.published ? ` · ${f.published}` : ""}</span>
                </div>
                {f.source_url && f.verification !== "synthetic" ? (
                  <a href={f.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-display text-lg font-semibold text-royal hover:underline">
                    {f.title} <ExternalLink size={13} aria-hidden="true" />
                  </a>
                ) : <p className="font-display text-lg font-semibold text-plum">{f.title}</p>}
              </div>
              {can("run_agents") && (
                <button className={`btn !py-1.5 text-sm ${f.saved ? "btn-primary" : "btn-soft"}`} onClick={() => toggle(f)} aria-pressed={f.saved}>
                  {f.saved ? <BookmarkCheck size={14} aria-hidden="true" /> : <BookmarkPlus size={14} aria-hidden="true" />} {f.saved ? "Saved" : "Save"}
                </button>
              )}
            </div>
            <p className="mt-1 text-sm text-ink/85">{f.summary}</p>
            {f.uncertainty && <p className="mt-1 text-xs text-amber">Uncertainty: {f.uncertainty}</p>}
            {f.run_id && <Link to={`/activity/runs/${f.run_id}`} className="mt-1 inline-block text-xs text-royal hover:underline">From workflow #{f.run_id}</Link>}
          </li>))}</ul>
      ))}
    </Card>
  );
}

// ── Lessons ─────────────────────────────────────────────────────────────────

const KIND_STYLE: Record<string, string> = {
  what_worked: "bg-[#e3f1e8] text-sage", recurring_problem: "bg-[#fbf1e3] text-amber", recommendation: "bg-lilac text-royal",
};

export function LessonsPanel() {
  const { data, error, loading, reload } = useApi<{ lessons: LessonRow[] }>("/api/lessons");
  return (
    <Card title="Lessons learned" icon={<Lightbulb size={16} aria-hidden="true" />}>
      {loading && <LoadingState rows={2} />}
      {error && <ErrorState message={error.message} onRetry={reload} />}
      {data && (data.lessons.length === 0 ? <EmptyState title="No lessons yet">Run "Learn from past events" and the Event Intelligence agent will add lessons, each citing its evidence.</EmptyState> : (
        <ul className="space-y-3">{data.lessons.slice(0, 12).map((l) => (
          <li key={l.id} className="rounded-2xl bg-ivory/80 p-3.5 text-sm">
            <div className="mb-1 flex flex-wrap items-center gap-1.5">
              <span className={`rounded-full px-2 py-0.5 text-[0.7rem] font-semibold capitalize ${KIND_STYLE[l.kind ?? ""] ?? "bg-lilac text-plum"}`}>{(l.kind ?? "lesson").replace(/_/g, " ")}</span>
              <span className="text-xs text-muted">{l.confidence} confidence</span>
              {l.based_on_demo_data && <DemoBadge label="From demo data" />}
            </div>
            <p className="text-ink">{l.lesson}</p>
            <p className="mt-1.5 flex flex-wrap gap-1 text-[0.7rem]">
              <span className="text-muted">Evidence:</span>
              {l.evidence.map((e) => <span key={`${e.type}-${e.id}`} className="rounded bg-white px-1.5 py-0.5 text-plum ring-1 ring-lavender/40">{e.label}</span>)}
            </p>
          </li>))}</ul>
      ))}
    </Card>
  );
}

// ── Venue candidates ───────────────────────────────────────────────────────────

export function VenueCandidates({ eventId }: { eventId: number }) {
  const { data, loading } = useApi<{ venues: VenueCandidateRow[] }>(`/api/events/${eventId}/venues`);
  if (loading) return <p className="text-xs text-muted">Loading venues…</p>;
  if (!data || data.venues.length === 0) return <p className="text-xs text-muted">No venue candidates yet. Ask the agents to plan this event.</p>;
  return (
    <ul className="mt-2 space-y-1.5">{data.venues.map((v) => (
      <li key={v.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-white/80 px-3 py-2 text-sm ring-1 ring-lavender/30">
        <span className="flex items-center gap-2"><MapPin size={13} className="text-royal" aria-hidden="true" /><b className="text-plum">{v.name}</b>
          <span className="text-xs text-muted">{v.neighborhood}{v.formats ? ` · ${v.formats.map((f) => f.replace("_", " ")).join(", ")}` : ""}</span></span>
        <span className="flex items-center gap-2"><VerificationBadge value={v.verification} /><span className="text-xs text-muted">est. {money(v.estimated_total_usd)}</span></span>
      </li>))}</ul>
  );
}
