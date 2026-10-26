import { Archive, BookmarkCheck, BookmarkPlus, Check, Copy, ExternalLink, FileText, MapPin, MailX, Pencil } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Draft, ResearchFindingRow, VenueCandidateRow } from "../api/types";
import { useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { VerificationBadge, money } from "./agents";
import { Card, DemoBadge, EmptyState, ErrorState, LoadingState , ShowMore } from "./ui";

// ── Drafts (never sent) ─────────────────────────────────────────────────────────

const DRAFT_LABELS: Record<string, string> = {
  partnership_inquiry: "Partnership inquiry", nonprofit_collaboration: "Nonprofit collaboration", research_support: "Research-support inquiry",
  community_program: "Community-program proposal", corporate_sponsorship: "Corporate sponsorship", venue_inquiry: "Venue inquiry",
  partnership: "Partnership", sponsor: "Sponsor", donor_acknowledgment: "Donor acknowledgment",
  donor_thank_you: "General thank-you (not a tax acknowledgment)", contribution_acknowledgment: "Contribution acknowledgment (for accountant review)",
};

export function DraftItem({ draft, onChange }: { draft: Draft; onChange: () => void }) {
  const { can } = useAuth();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ subject: draft.subject, body: draft.body, purpose: draft.purpose ?? "", opportunity: draft.opportunity ?? "", next_step: draft.next_step ?? "" });
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const structured = draft.purpose != null || draft.next_step != null;

  async function save(patch: Partial<Draft>) {
    setBusy(true);
    setError(null);
    try {
      await api(`/api/drafts/${draft.id}`, { method: "PUT", json: patch });
      setEditing(false);
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }
  async function copy() {
    await navigator.clipboard?.writeText(`Subject: ${form.subject}\n\n${form.body}`).catch(() => undefined);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <li className="rounded-2xl border border-lavender/35 bg-white/80 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">{DRAFT_LABELS[draft.draft_type] ?? draft.draft_type.replace(/_/g, " ")} · to {draft.recipient_org || draft.recipient_name}</p>
          {editing ? <input className="field mt-1" value={form.subject} onChange={set("subject")} aria-label="Subject" />
            : <p className="font-display text-lg font-semibold text-plum">{draft.subject}</p>}
        </div>
        <div className="flex items-center gap-1.5">
          {draft.is_synthetic_target && <DemoBadge label="Synthetic recipient" />}
          <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${draft.status === "reviewed" ? "bg-[#e3f1e8] text-sage" : draft.status === "archived" ? "bg-[#f4eef6] text-muted" : "bg-lilac text-plum"}`}>
            {draft.status === "reviewed" ? "Reviewed · unsent" : draft.status === "archived" ? "Archived · unsent" : "Unsent draft"}</span>
        </div>
      </div>
      {structured && (
        <dl className="mt-2 grid grid-cols-1 gap-2 text-sm md:grid-cols-3">
          {(["purpose", "opportunity", "next_step"] as const).map((k) => (
            <div key={k} className="rounded-xl bg-ivory/80 px-3 py-2">
              <dt className="text-[0.68rem] font-semibold uppercase tracking-wide text-royal">{k === "next_step" ? "Next step" : k}</dt>
              <dd className="mt-0.5">{editing ? <textarea rows={2} className="field text-sm" value={form[k]} onChange={set(k)} aria-label={k} /> : (draft[k] || "—")}</dd>
            </div>
          ))}
        </dl>
      )}
      {editing ? <textarea className="field mt-2 font-mono text-sm" rows={11} value={form.body} onChange={set("body")} aria-label="Draft body" />
        : <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-xl bg-ivory p-3 font-sans text-sm text-ink">{draft.body}</pre>}
      {draft.review_notes && draft.review_notes.length > 0 && (
        <div className="mt-2 rounded-xl bg-[#fbf1e3]/80 px-3 py-2 text-xs text-amber">
          <p className="font-semibold">Confirm before anyone sends this (carried over from research):</p>
          <ul className="mt-0.5 list-disc pl-4">{draft.review_notes.map((n) => <li key={n}>{n}</li>)}</ul>
        </div>
      )}
      {draft.sources && draft.sources.length > 0 && (
        <p className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted">Supporting sources:
          {draft.sources.map((src, i) => (
            <span key={i} className="inline-flex items-center gap-1">
              {src.url && src.verification !== "synthetic" ? <a className="text-royal hover:underline" href={src.url} target="_blank" rel="noopener noreferrer">{src.title || src.url}</a> : <span>{src.title}</span>}
              <VerificationBadge value={src.verification} />
            </span>
          ))}
        </p>
      )}
      {draft.personalization_basis && <p className="mt-1 text-xs text-muted">Personalized from: {draft.personalization_basis}</p>}
      {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
      {can("run_agents") && (
        <div className="mt-3 flex flex-wrap gap-2">
          {editing ? (
            <>
              <button className="btn btn-primary !py-1.5 text-sm" disabled={busy} onClick={() => save(structured ? form : { subject: form.subject, body: form.body })}>Save edits</button>
              <button className="btn btn-ghost !py-1.5 text-sm" onClick={() => { setEditing(false); setForm({ subject: draft.subject, body: draft.body, purpose: draft.purpose ?? "", opportunity: draft.opportunity ?? "", next_step: draft.next_step ?? "" }); }}>Cancel</button>
            </>
          ) : (
            <>
              <button className="btn btn-soft !py-1.5 text-sm" onClick={() => setEditing(true)}><Pencil size={13} aria-hidden="true" /> Edit</button>
              <button className="btn btn-soft !py-1.5 text-sm" onClick={copy}>{copied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />} {copied ? "Copied" : "Copy text"}</button>
              {draft.status === "draft" && <button className="btn btn-soft !py-1.5 text-sm" disabled={busy} onClick={() => save({ status: "reviewed" })}><Check size={13} aria-hidden="true" /> Mark reviewed</button>}
              {draft.status === "archived"
                ? <button className="btn btn-ghost !py-1.5 text-sm" disabled={busy} onClick={() => save({ status: "draft" })}>Restore</button>
                : <button className="btn btn-ghost !py-1.5 text-sm" disabled={busy} onClick={() => save({ status: "archived" })}><Archive size={13} aria-hidden="true" /> Archive</button>}
            </>
          )}
        </div>
      )}
    </li>
  );
}

export function DraftsPanel({ kind, title }: { kind: "outreach" | "donor"; title: string }) {
  const [archived, setArchived] = useState(false);
  const [limit, setLimit] = useState(4);
  const { data, error, loading, reload } = useApi<{ drafts: Draft[] }>(`/api/drafts?kind=${kind}${archived ? "&archived=true" : ""}`);
  return (
    <Card title={title} icon={<FileText size={16} aria-hidden="true" />}
      action={<button className="btn btn-ghost !py-1 text-xs" onClick={() => setArchived((a) => !a)}>{archived ? "Show current drafts" : "Show archived"}</button>}>
      <p className="mb-3 flex items-start gap-2 rounded-xl bg-lilac/50 px-3 py-2 text-xs text-plum">
        <MailX size={14} className="mt-0.5 shrink-0" aria-hidden="true" /> SAM SPACE has no way to send mail or messages. Edit a draft, copy it, and send it yourself if the board agrees.
      </p>
      {loading && <LoadingState rows={2} />}
      {error && <ErrorState message={error.message} onRetry={reload} />}
      {data && (data.drafts.length === 0 ? <EmptyState title={archived ? "No archived drafts" : "No drafts yet"}>Run the agents and their drafts will wait here for your review.</EmptyState> : (
        <><ul className="space-y-3">{data.drafts.slice(0, limit).map((d) => <DraftItem key={`${d.id}-${d.updated_at ?? ""}`} draft={d} onChange={reload} />)}</ul>
          <ShowMore shown={Math.min(limit, data.drafts.length)} total={data.drafts.length} onMore={() => setLimit(data.drafts.length)} /></>
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
