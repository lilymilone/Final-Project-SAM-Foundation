import {
  AlertTriangle, BookmarkCheck, BookmarkPlus, CalendarClock, ChevronDown, Compass, ExternalLink, FilePenLine, Search, ShieldAlert,
  StickyNote, Undo2, XCircle,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { AlignmentLevel, Opportunity, OpportunityStats, RunSummary } from "../api/types";
import { formatDate, useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { VerificationBadge } from "./agents";
import { Card, DemoBadge, EmptyState, ErrorState, LoadingState, StatTile } from "./ui";

export const DRAFT_TYPES: [string, string][] = [
  ["partnership_inquiry", "Partnership inquiry"], ["nonprofit_collaboration", "Nonprofit collaboration"],
  ["research_support", "Research-support inquiry"], ["community_program", "Community-program proposal"],
  ["corporate_sponsorship", "Corporate sponsorship request"], ["venue_inquiry", "Venue inquiry"],
];
const SUGGESTED: Record<string, string> = {
  research: "research_support", sponsor: "corporate_sponsorship", event: "community_program", partnership: "partnership_inquiry",
  organization: "nonprofit_collaboration",
};

const FIT_STYLE: Record<string, string> = {
  "Strong fit": "bg-[#e3f1e8] text-sage ring-sage/30", "Possible fit": "bg-lilac text-royal ring-lavender/50",
  "Needs research": "bg-[#fbf1e3] text-amber ring-amber/30", "Weak fit": "bg-[#f4eef6] text-muted ring-lavender/30",
};
const LEVEL_STYLE: Record<string, string> = {
  strong: "bg-[#e3f1e8] text-sage", partial: "bg-lilac text-royal", unclear: "bg-[#f4eef6] text-muted", none: "bg-white text-muted ring-1 ring-lavender/40",
};
const DATE_STYLE: Record<string, [string, string]> = {
  confirmed: ["Date confirmed on the page", "text-sage"], conflicting: ["Dates conflict between sources", "text-danger"],
  unconfirmed: ["Date not confirmed", "text-amber"],
};
const CRITERION_LABELS: Record<string, string> = {
  mental_health: "Mental health", eating_disorders: "Eating disorders", community_wellbeing: "Community well-being",
  compassion: "Compassion and kindness", belonging_inclusion: "Belonging and inclusion", human_connection: "Human connection",
  seen_heard_valued: "Feeling seen, heard, valued",
};

export function FitBadge({ fit }: { fit: string | null }) {
  if (!fit) return null;
  return <span className={`rounded-full px-2.5 py-0.5 text-[0.72rem] font-semibold ring-1 ${FIT_STYLE[fit] ?? FIT_STYLE["Weak fit"]}`}>{fit}</span>;
}

function Levels({ title, levels }: { title: string; levels: Record<string, AlignmentLevel> }) {
  return (
    <div>
      <p className="text-[0.7rem] font-semibold uppercase tracking-wide text-royal">{title}</p>
      <ul className="mt-1 space-y-1">
        {Object.entries(levels).map(([k, v]) => (
          <li key={k} className="text-sm">
            <span className={`mr-1.5 inline-block rounded-full px-1.5 py-px text-[0.66rem] font-semibold capitalize ${LEVEL_STYLE[v.level]}`}>{v.level}</span>
            <b className="text-plum">{CRITERION_LABELS[k] ?? k.replace(/_/g, " ")}:</b> <span className="text-ink/85">{v.explanation}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function AlignmentDetails({ o, open = false }: { o: Opportunity; open?: boolean }) {
  const a = o.alignment_detail;
  if (!a) return null;
  return (
    <details className="group mt-3 rounded-2xl bg-ivory/80 px-4 py-3" open={open}>
      <summary className="flex cursor-pointer list-none items-center justify-between text-sm font-semibold text-plum">
        Mission alignment, explained (A–D) <ChevronDown size={15} className="transition group-open:rotate-180" aria-hidden="true" />
      </summary>
      <div className="mt-3 grid gap-4 md:grid-cols-2">
        <Levels title="A · Charitable alignment" levels={a.charitable} />
        <Levels title="B · Philosophical alignment" levels={a.philosophical} />
        <div>
          <p className="text-[0.7rem] font-semibold uppercase tracking-wide text-royal">C · Practical feasibility</p>
          <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
            {(["geography", "cost", "volunteers", "timing", "operations"] as const).map((k) => (
              <div key={k} className="contents"><dt className="capitalize text-muted">{k}</dt><dd className="text-ink/85">{a.practical[k] || "—"}</dd></div>
            ))}
          </dl>
          {a.practical.blockers.length > 0 && <p className="mt-1 text-sm text-amber">Blockers: {a.practical.blockers.join("; ")}</p>}
        </div>
        <div>
          <p className="text-[0.7rem] font-semibold uppercase tracking-wide text-royal">D · Evidence quality ({a.evidence.reliability.replace(/_/g, " ")})</p>
          <ul className="mt-1 space-y-0.5 text-sm">
            {a.evidence.verified_items.map((x) => <li key={x}><span className="text-sage">✓</span> {x}</li>)}
            {a.evidence.unconfirmed_claims.map((x) => <li key={x}><span className="text-amber">?</span> {x}</li>)}
          </ul>
        </div>
      </div>
      <p className="mt-3 text-xs text-muted">Levels are explanations, not scores. The fit label comes from an explicit rubric applied in code; clinical research is never down-ranked for having less visible effect on belonging.</p>
    </details>
  );
}

function OpportunityCard({ o, categories, onChange }: { o: Opportunity; categories: string[]; onChange: (o: Opportunity) => void }) {
  const { can } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState<string | null>(null);
  const [notes, setNotes] = useState(o.notes ?? "");
  const [notesOpen, setNotesOpen] = useState(false);
  const [draftType, setDraftType] = useState(SUGGESTED[o.category] ?? "partnership_inquiry");
  const [error, setError] = useState<string | null>(null);
  const live = !o.is_synthetic;

  async function act(label: string, fn: () => Promise<void>) {
    setBusy(label);
    setError(null);
    try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : "Something went wrong."); } finally { setBusy(null); }
  }
  const setStatus = (status: Opportunity["status"]) => act(status, async () => {
    onChange((await api<{ opportunity: Opportunity }>(`/api/opportunities/${o.id}/status`, { json: { status } })).opportunity);
  });
  const edit = (patch: { board_category?: string; notes?: string }) => act("edit", async () => {
    onChange((await api<{ opportunity: Opportunity }>(`/api/opportunities/${o.id}`, { method: "PUT", json: patch })).opportunity);
  });
  const research = () => act("research", async () => {
    const res = await api<{ run: RunSummary }>("/api/runs", { json: {
      request: `Research more about ${o.name}: ${o.missing_info.slice(0, 2).join(" ") || "confirm details"}`.slice(0, 1900),
      intent: "mission_discovery", research_mode: live ? "live" : "synthetic", follow_up_finding_id: o.id } });
    navigate(`/activity/runs/${res.run.id}`);
  });
  const draft = () => act("draft", async () => {
    const label = DRAFT_TYPES.find(([v]) => v === draftType)?.[1] ?? "outreach draft";
    const res = await api<{ run: RunSummary }>("/api/runs", { json: {
      request: `Draft a ${label.toLowerCase()} to ${o.name}`.slice(0, 1900), intent: "partnership_outreach",
      research_mode: live ? "live" : "synthetic", finding_ids: [o.id], draft_type: draftType } });
    navigate(`/activity/runs/${res.run.id}`);
  });

  const dateStyle = o.date_status ? DATE_STYLE[o.date_status] : undefined;
  return (
    <li className={`rounded-3xl border p-5 transition ${o.status === "saved" ? "border-royal/60 bg-lilac/30" : o.status === "dismissed" ? "border-lavender/30 bg-white/50 opacity-80" : "border-lavender/35 bg-white/85"}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
            <FitBadge fit={o.fit} />
            <VerificationBadge value={o.verification} />
            <span className="text-xs capitalize text-muted">{o.category}{o.geography ? ` · ${o.geography}` : ""}</span>
            {o.board_category && <span className="rounded-full bg-white px-2 py-0.5 text-[0.7rem] font-semibold text-plum ring-1 ring-lavender/40">{o.board_category}</span>}
            {o.status !== "new" && <span className="text-[0.7rem] font-semibold uppercase tracking-wide text-royal">{o.status}</span>}
          </div>
          {o.website && !o.is_synthetic ? (
            <a href={o.website} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-display text-xl font-semibold text-royal hover:underline">
              {o.name} <ExternalLink size={14} aria-hidden="true" />
            </a>
          ) : <p className="font-display text-xl font-semibold text-plum">{o.name}</p>}
          {o.fit_reason && <p className="text-xs text-muted">{o.fit_reason}</p>}
        </div>
        {can("run_agents") && (
          <div className="flex flex-wrap gap-1.5">
            {o.status === "saved"
              ? <button className="btn btn-primary !py-1.5 text-sm" disabled={!!busy} onClick={() => setStatus("new")} aria-pressed="true"><BookmarkCheck size={14} aria-hidden="true" /> Saved</button>
              : <button className="btn btn-soft !py-1.5 text-sm" disabled={!!busy} onClick={() => setStatus("saved")}><BookmarkPlus size={14} aria-hidden="true" /> Save</button>}
            {o.status === "dismissed"
              ? <button className="btn btn-ghost !py-1.5 text-sm" disabled={!!busy} onClick={() => setStatus("new")}><Undo2 size={14} aria-hidden="true" /> Restore</button>
              : <button className="btn btn-ghost !py-1.5 text-sm" disabled={!!busy} onClick={() => setStatus("dismissed")}><XCircle size={14} aria-hidden="true" /> Dismiss</button>}
          </div>
        )}
      </div>

      <dl className="mt-3 grid gap-x-6 gap-y-2 text-sm md:grid-cols-2">
        <div className="md:col-span-2"><dt className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">Mission / purpose</dt><dd className="text-ink">{o.purpose || "Not stated on the source."}</dd></div>
        {o.activities.length > 0 && <div className="md:col-span-2"><dt className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">Activities</dt>
          <dd className="mt-0.5 flex flex-wrap gap-1">{o.activities.map((a) => <span key={a} className="rounded-full bg-ivory px-2 py-0.5 text-xs text-plum ring-1 ring-lavender/30">{a}</span>)}</dd></div>}
        <div><dt className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">Dates</dt>
          <dd>{o.dates_text || "Not stated"}{dateStyle && <span className={`ml-1.5 text-xs font-semibold ${dateStyle[1]}`}>· {dateStyle[0]}</span>}</dd></div>
        <div><dt className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">Known costs (verified on the page)</dt><dd>{o.known_costs || "Not stated on the source"}</dd></div>
        <div><dt className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">Partnership type</dt><dd>{o.partnership_types.join(", ") || "Not stated"}</dd></div>
        <div><dt className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">Ways we could contribute</dt><dd>{o.contribution_ways.join("; ") || "—"}</dd></div>
        <div className="md:col-span-2"><dt className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">Why it may fit</dt><dd className="text-ink/90">{o.alignment_detail?.summary || o.summary}</dd></div>
      </dl>

      {o.warnings.length > 0 && (
        <ul className="mt-3 space-y-1 rounded-2xl bg-[#fbf1e3]/80 px-3 py-2 text-sm text-amber">
          {o.warnings.map((w) => <li key={w} className="flex gap-1.5">{w.includes("AI system") ? <ShieldAlert size={14} className="mt-0.5 shrink-0" aria-hidden="true" /> : <AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden="true" />}{w}</li>)}
        </ul>
      )}
      {o.missing_info.length > 0 && (
        <div className="mt-2 text-sm"><span className="font-semibold text-plum">Missing before outreach:</span> <span className="text-ink/85">{o.missing_info.join(" · ")}</span></div>
      )}
      {o.next_step && <p className="mt-1 text-sm"><span className="font-semibold text-plum">Suggested next step:</span> {o.next_step}</p>}

      <AlignmentDetails o={o} />

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
        <span className="inline-flex items-center gap-1"><CalendarClock size={13} aria-hidden="true" />Last checked {o.last_checked ? formatDate(o.last_checked) : "—"}
          {o.website && <> · <a href={o.is_synthetic ? undefined : o.website} className={o.is_synthetic ? "" : "text-royal hover:underline"} target="_blank" rel="noopener noreferrer">{o.is_synthetic ? "example.org fixture" : "source"}</a></>}
        </span>
        {o.run_id && <Link to={`/activity/runs/${o.run_id}`} className="text-royal hover:underline">From workflow #{o.run_id}</Link>}
      </div>

      {can("run_agents") && (
        <div className="mt-3 space-y-2 border-t border-lavender/30 pt-3">
          <div className="flex flex-wrap items-center gap-2">
            <label className="sr-only" htmlFor={`cat-${o.id}`}>Board category</label>
            <select id={`cat-${o.id}`} className="field !w-auto !py-1.5 text-sm" value={o.board_category ?? ""} disabled={!!busy}
              onChange={(e) => edit({ board_category: e.target.value })}>
              <option value="">Categorize…</option>{categories.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <button className="btn btn-ghost !py-1.5 text-sm" onClick={() => setNotesOpen((v) => !v)}><StickyNote size={14} aria-hidden="true" /> {o.notes ? "Private notes" : "Add a note"}</button>
            <button className="btn btn-ghost !py-1.5 text-sm" disabled={!!busy} onClick={research}><Search size={14} aria-hidden="true" /> {busy === "research" ? "Starting…" : "Request more research"}</button>
            <span className="inline-flex items-center gap-1.5">
              <label className="sr-only" htmlFor={`dt-${o.id}`}>Draft type</label>
              <select id={`dt-${o.id}`} className="field !w-auto !py-1.5 text-sm" value={draftType} onChange={(e) => setDraftType(e.target.value)}>
                {DRAFT_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <button className="btn btn-soft !py-1.5 text-sm" disabled={!!busy || o.status === "dismissed"} onClick={draft}><FilePenLine size={14} aria-hidden="true" /> {busy === "draft" ? "Starting…" : "Generate draft"}</button>
            </span>
          </div>
          {notesOpen && (
            <div>
              <label className="label" htmlFor={`notes-${o.id}`}>Private board notes (never sent to an AI model or a website)</label>
              <textarea id={`notes-${o.id}`} rows={3} className="field" value={notes} maxLength={4000} onChange={(e) => setNotes(e.target.value)} />
              <button className="btn btn-primary mt-2 !py-1.5 text-sm" disabled={!!busy} onClick={() => edit({ notes })}>Save note</button>
            </div>
          )}
          {!notesOpen && o.notes && <p className="rounded-xl bg-ivory px-3 py-2 text-sm text-ink/85"><StickyNote size={13} className="mr-1 inline text-royal" aria-hidden="true" />{o.notes}</p>}
          {error && <p role="alert" className="text-sm text-danger">{error}</p>}
        </div>
      )}
    </li>
  );
}

const TABS: [string, string][] = [["active", "Active"], ["saved", "Saved"], ["new", "New"], ["dismissed", "Dismissed"], ["all", "All"]];

export function OpportunityDashboard() {
  const [tab, setTab] = useState("active");
  const { data, error, loading, reload, setData } = useApi<{ opportunities: Opportunity[]; stats: OpportunityStats; board_categories: string[] }>(`/api/opportunities?status=${tab}`);
  function replace(o: Opportunity) {
    setData((d) => d && { ...d, opportunities: d.opportunities.map((x) => (x.id === o.id ? o : x)) });
    window.setTimeout(reload, 350);  // refresh stats and filters from the stored records
  }
  const s = data?.stats;
  const checked = s ? (s.by_verification.verified ?? 0) + (s.by_verification.synthetic ?? 0) : 0;
  return (
    <Card title="Research dashboard" icon={<Compass size={16} aria-hidden="true" />}>
      {s && (
        <>
          <div className="grid gap-3 sm:grid-cols-5">
            <StatTile label="On record" value={s.total} hint={s.synthetic ? `${s.synthetic} synthetic` : undefined} />
            <StatTile label="Saved" value={s.by_status.saved ?? 0} />
            <StatTile label="Strong fit" value={s.by_fit["Strong fit"] ?? 0} hint={`${s.by_fit["Possible fit"] ?? 0} possible`} />
            <StatTile label="Checked sources" value={checked} hint={`${s.by_verification.unverified ?? 0} unverified`} />
            <StatTile label="Need attention" value={s.with_warnings} hint={s.injection_flagged ? `${s.injection_flagged} flagged page${s.injection_flagged === 1 ? "" : "s"}` : undefined} />
          </div>
          <p className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">Every count comes from stored records{s.last_checked ? `; sources last checked ${formatDate(s.last_checked)}` : ""}.
            {s.synthetic > 0 && <DemoBadge label={`${s.synthetic} synthetic fixtures (example.org)`} />}</p>
        </>
      )}
      <div role="tablist" aria-label="Filter opportunities" className="mt-4 flex flex-wrap gap-1.5">
        {TABS.map(([v, l]) => (
          <button key={v} role="tab" aria-selected={tab === v} onClick={() => setTab(v)}
            className={`rounded-full px-3 py-1 text-sm font-semibold transition ${tab === v ? "bg-royal text-white" : "bg-lilac/60 text-plum hover:bg-lilac"}`}>{l}</button>
        ))}
      </div>
      <div className="mt-4">
        {loading && !data && <LoadingState rows={3} />}
        {error && <ErrorState message={error.message} onRetry={reload} />}
        {data && (data.opportunities.length === 0
          ? <EmptyState title={tab === "active" ? "No opportunities yet" : "Nothing here"}>Ask Mission Discovery a question. Each opportunity it finds appears here with its sources, alignment, and what is still unknown.</EmptyState>
          : <ul className="space-y-4">{data.opportunities.map((o) => <OpportunityCard key={o.id} o={o} categories={data.board_categories} onChange={replace} />)}</ul>)}
      </div>
    </Card>
  );
}
