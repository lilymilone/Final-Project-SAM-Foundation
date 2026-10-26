import {
  AlertTriangle, BookmarkCheck, BookmarkPlus, CalendarClock, ChevronDown, Compass, ExternalLink, FilePenLine, Search, ShieldAlert,
  StickyNote, Undo2, XCircle,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { AlignmentLevel, Opportunity, OpportunityStats, RunSummary } from "../api/types";
import { formatDate, useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { VerificationBadge } from "./agents";
import { Card, DemoBadge, EmptyState, ErrorState, LoadingState, ShowMore } from "./ui";

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
      <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2">
        <Levels title="A · Charitable alignment" levels={a.charitable} />
        <Levels title="B · Philosophical alignment" levels={a.philosophical} />
        <div>
          <p className="text-[0.7rem] font-semibold uppercase tracking-wide text-royal">C · Practical feasibility</p>
          <dl className="mt-1 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-sm">
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

function ContactLine({ o }: { o: Opportunity }) {
  const c = o.contact;
  if (o.is_synthetic && c?.email) return <span className="text-ink/85">{c.email} <span className="text-xs text-muted">(synthetic demo contact)</span></span>;
  if (c?.email) return <span className="text-ink/85">{c.email} <span className="text-xs text-sage">published on their site</span></span>;
  if (c?.contact_page_url && !o.is_synthetic)
    return <a href={c.contact_page_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-royal hover:underline">Official contact page <ExternalLink size={12} aria-hidden="true" /></a>;
  if (c) return <span className="text-muted">No public email found; use their official website.</span>;
  return <span className="text-muted">Looked up from their official site when you generate a draft.</span>;
}

function OpportunityCard({ o, categories, onChange }: { o: Opportunity; categories: string[]; onChange: (o: Opportunity) => void }) {
  const { can } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(location.hash === `#finding-${o.id}`);
  const [busy, setBusy] = useState<string | null>(null);
  const [notes, setNotes] = useState(o.notes ?? "");
  const [draftType, setDraftType] = useState(SUGGESTED[o.category] ?? "partnership_inquiry");
  const [error, setError] = useState<string | null>(null);
  const live = !o.is_synthetic;
  useEffect(() => { if (location.hash === `#finding-${o.id}`) setOpen(true); }, [location.hash, o.id]);

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
      intent: "mission_discovery", research_mode: live ? "live" : "synthetic", follow_up_finding_id: o.id, strategy: "economy" } });
    navigate(`/activity/runs/${res.run.id}`);
  });
  const draft = () => act("draft", async () => {
    const label = DRAFT_TYPES.find(([v]) => v === draftType)?.[1] ?? "outreach draft";
    const res = await api<{ run: RunSummary }>("/api/runs", { json: {
      request: `Draft a ${label.toLowerCase()} to ${o.name}`.slice(0, 1900), intent: "partnership_outreach",
      research_mode: live ? "live" : "synthetic", finding_ids: [o.id], draft_type: draftType, strategy: "economy" } });
    navigate(`/activity/runs/${res.run.id}`);
  });

  const dateStyle = o.date_status ? DATE_STYLE[o.date_status] : undefined;
  return (
    <li id={`finding-${o.id}`} className={`rounded-3xl border p-5 transition ${o.status === "saved" ? "border-royal/60 bg-lilac/30" : o.status === "dismissed" ? "border-lavender/30 bg-white/50 opacity-80" : "border-lavender/35 bg-white/85"}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
            <FitBadge fit={o.fit} />
            <VerificationBadge value={o.verification} />
            <span className="text-xs capitalize text-muted">{o.category}{o.geography ? ` · ${o.geography}` : ""}</span>
            {o.board_category && <span className="rounded-full bg-white px-2 py-0.5 text-[0.7rem] font-semibold text-plum ring-1 ring-lavender/40">{o.board_category}</span>}
            {o.is_synthetic && <DemoBadge label="Synthetic" />}
            {o.known_relationship && (
              <Link to="/settings/knowledge" title={o.known_relationship.summary}
                className="rounded-full bg-royal px-2 py-0.5 text-[0.7rem] font-semibold text-white hover:bg-plum">
                Known to the foundation · {o.known_relationship.relationship_type}
              </Link>
            )}
          </div>
          <p className="font-display text-xl font-semibold text-plum">{o.name}</p>
          {o.known_relationship && <p className="mt-0.5 text-xs text-royal">{o.known_relationship.summary}</p>}
          <p className="mt-1 line-clamp-2 text-sm text-ink/85">{o.purpose || o.summary || "Purpose not stated on the source."}</p>
        </div>
        {can("run_agents") && (
          <div className="flex flex-wrap gap-1.5">
            {o.status === "saved"
              ? <button className="btn btn-primary !py-1.5 text-sm" disabled={!!busy} onClick={() => setStatus("new")} aria-pressed="true"><BookmarkCheck size={14} aria-hidden="true" /> Saved</button>
              : <button className="btn btn-soft !py-1.5 text-sm" disabled={!!busy} onClick={() => setStatus("saved")}><BookmarkPlus size={14} aria-hidden="true" /> Save</button>}
            {o.status === "dismissed"
              ? <button className="btn btn-ghost !py-1.5 text-sm" disabled={!!busy} onClick={() => setStatus("new")}><Undo2 size={14} aria-hidden="true" /> Restore</button>
              : <button className="btn btn-ghost !py-1.5 text-sm" disabled={!!busy} onClick={() => setStatus("dismissed")} aria-label={`Dismiss ${o.name}`}><XCircle size={14} aria-hidden="true" /> Dismiss</button>}
          </div>
        )}
      </div>

      {o.activities.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1" aria-label="Programs and activities">
          {o.activities.slice(0, 6).map((a) => <span key={a} className="rounded-full bg-ivory px-2 py-0.5 text-xs text-plum ring-1 ring-lavender/30">{a}</span>)}
        </div>
      )}

      <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1.5 text-sm md:grid-cols-2">
        <div className="min-w-0"><dt className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">Website</dt>
          <dd className="truncate">{o.website && !o.is_synthetic
            ? <a href={o.website} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-royal hover:underline">{o.website.replace(/^https?:\/\//, "").slice(0, 60)} <ExternalLink size={12} aria-hidden="true" /></a>
            : <span className="text-muted">{o.is_synthetic ? "example.org fixture" : "Not found"}</span>}</dd></div>
        <div className="min-w-0"><dt className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">Contact</dt><dd><ContactLine o={o} /></dd></div>
        <div className="md:col-span-2"><dt className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">Mission alignment</dt>
          <dd className="text-ink/90">{o.fit_reason || o.alignment_detail?.summary || o.summary}</dd></div>
      </dl>

      {open && (
        <div className="mt-3 space-y-3 border-t border-lavender/30 pt-3">
          <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm md:grid-cols-2">
            <div className="md:col-span-2"><dt className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">Why it may fit</dt><dd className="text-ink/90">{o.alignment_detail?.summary || o.summary}</dd></div>
            <div><dt className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">Dates</dt>
              <dd>{o.dates_text || "Not stated"}{dateStyle && <span className={`ml-1.5 text-xs font-semibold ${dateStyle[1]}`}>· {dateStyle[0]}</span>}</dd></div>
            <div><dt className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">Known costs (on the page)</dt><dd>{o.known_costs || "Not stated on the source"}</dd></div>
            <div><dt className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">Partnership type</dt><dd>{o.partnership_types.join(", ") || "Not stated"}</dd></div>
            <div><dt className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">Ways we could contribute</dt><dd>{o.contribution_ways.join("; ") || "—"}</dd></div>
          </dl>
          {o.warnings.length > 0 && (
            <ul className="space-y-1 rounded-2xl bg-[#fbf1e3]/80 px-3 py-2 text-sm text-amber">
              {o.warnings.map((w) => <li key={w} className="flex gap-1.5">{w.includes("AI system") ? <ShieldAlert size={14} className="mt-0.5 shrink-0" aria-hidden="true" /> : <AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden="true" />}{w}</li>)}
            </ul>
          )}
          {o.missing_info.length > 0 && <p className="text-sm"><span className="font-semibold text-plum">Missing before outreach:</span> <span className="text-ink/85">{o.missing_info.join(" · ")}</span></p>}
          {o.next_step && <p className="text-sm"><span className="font-semibold text-plum">Suggested next step:</span> {o.next_step}</p>}
          <AlignmentDetails o={o} />
          {can("run_agents") && (
            <div className="flex flex-wrap items-end gap-2">
              <div><label className="label" htmlFor={`cat-${o.id}`}>Board category</label>
                <select id={`cat-${o.id}`} className="field !w-auto !py-1.5 text-sm" value={o.board_category ?? ""} disabled={!!busy}
                  onChange={(e) => edit({ board_category: e.target.value })}>
                  <option value="">None</option>{categories.map((c) => <option key={c} value={c}>{c}</option>)}
                </select></div>
              <div className="min-w-[240px] flex-1"><label className="label" htmlFor={`notes-${o.id}`}>Private notes (never sent to an AI model or a website)</label>
                <div className="flex gap-2"><input id={`notes-${o.id}`} className="field !py-1.5 text-sm" value={notes} maxLength={4000} onChange={(e) => setNotes(e.target.value)} />
                  <button className="btn btn-soft !py-1.5 text-sm" disabled={!!busy || notes === (o.notes ?? "")} onClick={() => edit({ notes })}><StickyNote size={14} aria-hidden="true" /> Save</button></div></div>
            </div>
          )}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-lavender/30 pt-3">
        <span className="inline-flex flex-wrap items-center gap-1 text-xs text-muted"><CalendarClock size={13} aria-hidden="true" />Checked {o.last_checked ? formatDate(o.last_checked) : "—"}
          {o.source_url && !o.is_synthetic && <> · <a href={o.source_url} className="text-royal hover:underline" target="_blank" rel="noopener noreferrer">source</a></>}
          {o.run_id && <> · <Link to={`/activity/runs/${o.run_id}`} className="text-royal hover:underline">workflow #{o.run_id}</Link></>}
          {o.contact?.draft_id && <> · <Link to={`/partnerships#draft-${o.contact.draft_id}`} className="text-royal hover:underline">outreach draft</Link></>}
        </span>
        <div className="flex flex-wrap items-center gap-1.5">
          <button className="btn btn-ghost !py-1.5 text-sm" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            <ChevronDown size={14} className={`transition ${open ? "rotate-180" : ""}`} aria-hidden="true" /> {open ? "Less" : "Details"}</button>
          {can("run_agents") && (
            <>
              <button className="btn btn-ghost !py-1.5 text-sm" disabled={!!busy} onClick={research}><Search size={14} aria-hidden="true" /> {busy === "research" ? "Starting…" : "Analyze further"}</button>
              <label className="sr-only" htmlFor={`dt-${o.id}`}>Draft type</label>
              <select id={`dt-${o.id}`} className="field !w-auto max-w-full !py-1.5 text-sm" value={draftType} onChange={(e) => setDraftType(e.target.value)}>
                {DRAFT_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <button className="btn btn-soft !py-1.5 text-sm" disabled={!!busy || o.status === "dismissed"} onClick={draft}><FilePenLine size={14} aria-hidden="true" /> {busy === "draft" ? "Starting…" : "Draft outreach"}</button>
            </>
          )}
        </div>
      </div>
      {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
    </li>
  );
}

const TABS: [string, string][] = [["active", "All open"], ["saved", "Saved"], ["new", "New"], ["dismissed", "Dismissed"]];
const CATEGORIES: [string, string][] = [["", "Any type"], ["organization", "Organizations"], ["research", "Research"], ["event", "Events"],
  ["sponsor", "Sponsors"], ["partnership", "Partnerships"]];
const FITS = ["Strong fit", "Possible fit", "Needs research", "Weak fit"];

export function OpportunityDashboard({ runId, refreshKey = 0, onClearRun }: { runId?: number | null; refreshKey?: number; onClearRun?: () => void }) {
  const [tab, setTab] = useState("active");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [fit, setFit] = useState("");
  const location = useLocation();
  const [limit, setLimit] = useState(location.hash.startsWith("#finding-") ? 1000 : 10);  // a link to one opportunity shows them all
  const { data, error, loading, reload, setData } = useApi<{ opportunities: Opportunity[]; stats: OpportunityStats; board_categories: string[] }>(`/api/opportunities?status=${tab}`);
  useEffect(() => { if (refreshKey) reload(); }, [refreshKey]);  // eslint-disable-line react-hooks/exhaustive-deps
  function replace(o: Opportunity) {
    setData((d) => d && { ...d, opportunities: d.opportunities.map((x) => (x.id === o.id ? { ...o, contact: x.contact } : x)) });
    window.setTimeout(reload, 350);  // refresh counts from the stored records
  }
  const s = data?.stats;
  const q = query.trim().toLowerCase();
  const shown = (data?.opportunities ?? []).filter((o) => (!runId || o.run_id === runId) && (!category || o.category === category) && (!fit || o.fit === fit)
    && (!q || `${o.name} ${o.purpose ?? ""} ${o.geography ?? ""} ${o.activities.join(" ")}`.toLowerCase().includes(q)));
  const f = "field !w-auto !py-1.5 text-sm";
  return (
    <Card title="Opportunities" icon={<Compass size={16} aria-hidden="true" />}
      action={s ? <span className="text-xs text-muted">{s.total} on record · {s.by_status.saved ?? 0} saved · {s.by_fit["Strong fit"] ?? 0} strong fit</span> : undefined}>
      <div className="flex flex-wrap items-center gap-2" role="search">
        <span className="relative"><Search size={14} className="pointer-events-none absolute left-2.5 top-2.5 text-muted" aria-hidden="true" />
          <input aria-label="Filter by name, program, or place" placeholder="Filter by name, program, place…" className={`${f} !pl-8`} value={query} onChange={(e) => setQuery(e.target.value)} /></span>
        <select aria-label="Type" className={f} value={category} onChange={(e) => setCategory(e.target.value)}>{CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        <select aria-label="Fit" className={f} value={fit} onChange={(e) => setFit(e.target.value)}><option value="">Any fit</option>{FITS.map((x) => <option key={x}>{x}</option>)}</select>
        <div role="tablist" aria-label="Status" className="flex flex-wrap gap-1.5">
          {TABS.map(([v, l]) => (
            <button key={v} role="tab" aria-selected={tab === v} onClick={() => setTab(v)}
              className={`rounded-full px-3 py-1 text-sm font-semibold transition ${tab === v ? "bg-royal text-white" : "bg-lilac/60 text-plum hover:bg-lilac"}`}>{l}</button>
          ))}
        </div>
      </div>
      {runId && (
        <p className="mt-3 flex flex-wrap items-center gap-2 rounded-xl bg-lilac/60 px-3 py-2 text-sm text-plum">Showing results from this search (workflow #{runId}).
          {onClearRun && <button className="btn btn-ghost !py-1 text-xs" onClick={onClearRun}>Show all</button>}</p>
      )}
      <div className="mt-4">
        {loading && !data && <LoadingState rows={3} />}
        {error && <ErrorState message={error.message} onRetry={reload} />}
        {data && (shown.length === 0
          ? <EmptyState title={data.opportunities.length === 0 ? "No opportunities yet" : "No matches"}>
              {data.opportunities.length === 0 ? "Search above to find organizations, research, and events aligned with the foundation." : "Try a different filter."}</EmptyState>
          : <><ul className="space-y-4">{shown.slice(0, limit).map((o) => <OpportunityCard key={o.id} o={o} categories={data.board_categories} onChange={replace} />)}</ul>
              <ShowMore shown={Math.min(limit, shown.length)} total={shown.length} onMore={() => setLimit(shown.length)} /></>)}
      </div>
    </Card>
  );
}
