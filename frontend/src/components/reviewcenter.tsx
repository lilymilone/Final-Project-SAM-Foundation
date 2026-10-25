import { Archive, Check, ChevronDown, Copy, ExternalLink, FileText, Info, MailX, RotateCcw, Save, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Draft } from "../api/types";
import { formatDate, useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { VerificationBadge } from "./agents";
import { Card, DemoBadge, ErrorState, LoadingState, Toast } from "./ui";

/** Partnerships & Outreach → Drafts for Board Review. Drafts are never sent: a person copies one and sends it outside SAM SPACE. */

const NOTICE = "AI-prepared draft. Review all details before contacting this organization.";
const NOT_VERIFIED = "Contact email not verified — use official contact page.";
const STATUS: Record<string, { label: string; cls: string }> = {
  draft: { label: "AI Draft", cls: "bg-lilac text-plum" }, needs_review: { label: "Needs Review", cls: "bg-[#fbf1e3] text-amber" },
  reviewed: { label: "Reviewed", cls: "bg-[#e3f1e8] text-sage" }, archived: { label: "Archived", cls: "bg-[#f4eef6] text-muted" },
};
const CATEGORY: Record<string, string> = { venue: "Venue", charity: "Charitable organization", sponsor: "Corporate sponsor", research: "Research initiative",
  partner: "Community partner" };
const AGENTS: Record<string, string> = { fundraising_events: "Fundraising & Events", mission_discovery: "Mission Discovery", board: "The board (saved finding)" };
const FILTERS = [["open", "All open"], ["draft", "AI Draft"], ["needs_review", "Needs Review"], ["reviewed", "Reviewed"], ["archived", "Archived"]] as const;

function CopyButton({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false);
  return (
    <button type="button" className="btn btn-ghost !px-2 !py-1 text-xs" onClick={async () => {
      await navigator.clipboard?.writeText(text).catch(() => undefined);
      setDone(true);
      window.setTimeout(() => setDone(false), 1500);
    }}>{done ? <Check size={12} aria-hidden="true" /> : <Copy size={12} aria-hidden="true" />} {done ? "Copied" : label}</button>
  );
}

function ContactBlock({ d }: { d: Draft }) {
  const c = d.contact;
  const email = c?.email ?? null;
  return (
    <div className="rounded-xl bg-ivory/80 p-3 text-sm">
      <p className="text-[0.68rem] font-semibold uppercase tracking-wide text-royal">Recommended recipient</p>
      <p className="text-plum">{c?.department ? `${c.department}, ` : ""}{d.recipient_org}</p>
      <div className="mt-1.5 flex flex-wrap items-center gap-2">
        {email ? <><b className="text-plum">{email}</b><CopyButton text={email} label="Copy email" /></>
          : <span className="font-semibold text-amber">{NOT_VERIFIED}</span>}
      </div>
      {c?.contact_page_url && <p className="mt-1 text-xs">Official contact page: {c.status?.startsWith("synthetic") ? <span className="text-muted">{c.contact_page_url} (synthetic)</span>
        : <a className="text-royal underline" href={c.contact_page_url} target="_blank" rel="noopener noreferrer">{c.contact_page_url}</a>}</p>}
      <p className="mt-1 text-xs text-muted">
        Source: {c?.source_url ? (c.status?.startsWith("synthetic") ? `${c.source_url} (synthetic demo fixture)` : c.source_url) : "none found"}
        {c?.verified_at ? ` · checked ${formatDate(c.verified_at)}` : ""} · status: {(c?.status ?? "not checked").replace(/_/g, " ")}
        {c?.confidence && c.confidence !== "none" ? ` · confidence ${c.confidence}` : ""}</p>
      {c?.notes && c.notes.length > 0 && <ul className="mt-1 list-disc pl-4 text-xs text-muted">{c.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
    </div>
  );
}

function DraftCard({ d, onChange }: { d: Draft; onChange: (msg: string) => void }) {
  const { can } = useAuth();
  const [open, setOpen] = useState(false);
  const [subject, setSubject] = useState(d.subject);
  const [body, setBody] = useState(d.body);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dirty = subject !== d.subject || body !== d.body;
  const st = STATUS[d.status] ?? STATUS.draft;

  async function save(patch: Record<string, unknown>, msg: string) {
    setBusy(true);
    setError(null);
    try {
      await api(`/api/drafts/${d.id}`, { method: "PUT", json: patch });
      onChange(msg);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="rounded-2xl border border-lavender/35 bg-white/85">
      <button type="button" className="flex w-full flex-wrap items-start justify-between gap-2 p-4 text-left" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">{CATEGORY[d.category ?? ""] ?? d.draft_type.replace(/_/g, " ")} · {formatDate(d.created_at)}</p>
          <p className="font-display text-lg font-semibold text-plum">{d.recipient_org}</p>
          <p className="truncate text-sm text-ink">{d.subject}</p>
        </div>
        <div className="flex items-center gap-1.5">
          {d.is_synthetic_target && <DemoBadge label="Synthetic recipient" />}
          <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${st.cls}`}>{st.label}</span>
          <span className="text-xs text-muted">{d.contact?.email ? "email verified" : "contact page"}</span>
          <ChevronDown size={16} className={`text-muted transition ${open ? "rotate-180" : ""}`} aria-hidden="true" />
        </div>
      </button>
      {open && (
        <div className="space-y-3 border-t border-lavender/30 p-4">
          <p className="flex items-start gap-2 rounded-xl bg-[#fbf1e3] px-3 py-2 text-sm font-semibold text-amber"><ShieldAlert size={16} className="mt-0.5 shrink-0" aria-hidden="true" />{NOTICE}</p>
          <ContactBlock d={d} />
          <div>
            <div className="flex items-center justify-between"><label className="label" htmlFor={`s-${d.id}`}>Subject</label><CopyButton text={subject} label="Copy subject" /></div>
            <input id={`s-${d.id}`} className="field" value={subject} disabled={!can("run_agents")} onChange={(e) => setSubject(e.target.value)} />
          </div>
          <div>
            <div className="flex items-center justify-between"><label className="label" htmlFor={`b-${d.id}`}>Message</label><CopyButton text={body} label="Copy message" /></div>
            <textarea id={`b-${d.id}`} rows={12} className="field text-sm" value={body} disabled={!can("run_agents")} onChange={(e) => setBody(e.target.value)} />
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-xl bg-lilac/30 p-3 text-sm">
              <p className="text-[0.68rem] font-semibold uppercase tracking-wide text-royal">Why the Orchestrator recommended outreach</p>
              <p className="mt-0.5 text-ink">{d.recommendation_reason || "Requested by a board member."}</p>
              <p className="mt-1 text-xs text-muted">Found by: {AGENTS[d.found_by_agent ?? ""] ?? (d.found_by_agent || "—")} · written by: {d.model_used || "—"}
                {d.run_id && <> · <Link className="text-royal underline" to={`/activity/runs/${d.run_id}`}>agent trace #{d.run_id}</Link></>}</p>
            </div>
            <div className="rounded-xl bg-ivory/80 p-3 text-sm">
              <p className="text-[0.68rem] font-semibold uppercase tracking-wide text-royal">Financial considerations</p>
              {(d.financial_considerations ?? []).length ? <ul className="mt-0.5 list-disc pl-4 text-ink">{d.financial_considerations!.map((x) => <li key={x}>{x}</li>)}</ul>
                : <p className="text-muted">None involved.</p>}
            </div>
          </div>
          {(d.related_findings ?? []).length > 0 && (
            <div className="text-sm"><p className="label">Related agent findings</p><ul className="list-disc pl-5 text-ink">{d.related_findings!.map((x) => <li key={x}>{x}</li>)}</ul></div>
          )}
          {d.review_notes && d.review_notes.length > 0 && (
            <div className="rounded-xl bg-[#fbf1e3]/80 px-3 py-2 text-xs text-amber"><p className="font-semibold">Confirm before anyone sends this:</p>
              <ul className="mt-0.5 list-disc pl-4">{d.review_notes.map((n) => <li key={n}>{n}</li>)}</ul></div>
          )}
          {d.sources && d.sources.length > 0 && (
            <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted">Supporting sources:
              {d.sources.map((s, i) => (
                <span key={i} className="inline-flex items-center gap-1">
                  {s.url && s.verification !== "synthetic" ? <a className="inline-flex items-center gap-0.5 text-royal hover:underline" href={s.url} target="_blank" rel="noopener noreferrer">{s.title || s.url}<ExternalLink size={10} aria-hidden="true" /></a> : <span>{s.title}</span>}
                  <VerificationBadge value={s.verification} />
                </span>))}
            </p>
          )}
          <p className="flex items-center gap-1.5 text-xs text-muted"><Info size={12} aria-hidden="true" />
            Created {formatDate(d.created_at)}{d.edited_at ? ` · edited ${formatDate(d.edited_at)}` : ""}{d.reviewed_at ? ` · reviewed by a board member ${formatDate(d.reviewed_at)}` : " · not yet reviewed by a person"}</p>
          {error && <p role="alert" className="text-sm text-danger">{error}</p>}
          {can("run_agents") && (
            <div className="flex flex-wrap gap-2">
              <button className="btn btn-primary !py-1.5 text-sm" disabled={busy || !dirty} onClick={() => save({ subject, body }, "Changes saved. The draft is still unsent.")}><Save size={13} aria-hidden="true" /> Save changes</button>
              {d.status !== "needs_review" && d.status !== "archived" && <button className="btn btn-soft !py-1.5 text-sm" disabled={busy} onClick={() => save({ status: "needs_review" }, "Marked as needing review.")}>Needs review</button>}
              {d.status !== "reviewed" && d.status !== "archived" && <button className="btn btn-soft !py-1.5 text-sm" disabled={busy || dirty} title={dirty ? "Save your changes first" : undefined}
                onClick={() => save({ status: "reviewed" }, "Marked reviewed. Nothing was sent.")}><Check size={13} aria-hidden="true" /> Mark reviewed</button>}
              {d.status === "archived"
                ? <button className="btn btn-ghost !py-1.5 text-sm" disabled={busy} onClick={() => save({ status: "draft" }, "Restored.")}><RotateCcw size={13} aria-hidden="true" /> Restore</button>
                : <button className="btn btn-ghost !py-1.5 text-sm" disabled={busy} onClick={() => save({ status: "archived" }, "Archived.")}><Archive size={13} aria-hidden="true" /> Archive</button>}
            </div>
          )}
        </div>
      )}
    </li>
  );
}

export function ReviewCenter() {
  const [filter, setFilter] = useState<(typeof FILTERS)[number][0]>("open");
  const [toast, setToast] = useState<string | null>(null);
  const { data, error, loading, reload } = useApi<{ drafts: Draft[] }>(`/api/drafts?kind=outreach${filter === "archived" ? "&archived=true" : ""}`);
  const rows = (data?.drafts ?? []).filter((d) => filter === "open" || filter === "archived" || d.status === filter);
  return (
    <Card title="Drafts for Board Review" icon={<FileText size={16} aria-hidden="true" />}>
      <p className="mb-3 flex items-start gap-2 rounded-xl bg-lilac/50 px-3 py-2 text-xs text-plum">
        <MailX size={14} className="mt-0.5 shrink-0" aria-hidden="true" /> The agents prepare these automatically when they find a promising venue, sponsor, charity, or
        research partner. SAM SPACE cannot send email, submit forms, or contact anyone: a person copies a reviewed draft and sends it outside SAM SPACE.
      </p>
      <div role="tablist" className="mb-3 flex flex-wrap gap-1.5">{FILTERS.map(([k, label]) => (
        <button key={k} role="tab" aria-selected={filter === k} className={`rounded-full px-3 py-1 text-xs font-semibold ${filter === k ? "bg-plum text-white" : "bg-lilac/60 text-plum"}`}
          onClick={() => setFilter(k)}>{label}</button>))}</div>
      {loading && <LoadingState rows={2} />}
      {error && <ErrorState message={error.message} onRetry={reload} />}
      {data && (rows.length === 0 ? <p className="rounded-xl bg-ivory/80 px-3 py-2.5 text-sm text-muted">No drafts here.</p> : (
        <ul className="space-y-3">{rows.map((d) => <DraftCard key={`${d.id}-${d.updated_at ?? ""}`} d={d} onChange={(m) => { setToast(m); reload(); }} />)}</ul>
      ))}
      {toast && <Toast message={toast} onDone={() => setToast(null)} />}
    </Card>
  );
}
