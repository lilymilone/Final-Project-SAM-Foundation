import {
  AlertTriangle, ArrowLeft, Building2, CheckCircle2, CircleSlash, Coins, Download, ExternalLink, FileText, History, Lightbulb, ListTree,
  Lock, Printer, RefreshCcw, ShieldCheck, XCircle,
} from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Draft, RunDetail, StrategyPacket } from "../api/types";
import { formatDate } from "../api/useApi";
import { AGENT_LABELS, ModeBadge, StatusPill, VerificationBadge, money, stepLabel } from "../components/agents";
import { DraftItem } from "../components/outputs";
import { FinancialModelEditor, StrategyProgress } from "../components/studio";
import { Card, ErrorState, LoadingState } from "../components/ui";

const SECTIONS = [
  ["overview", "Overview"], ["recommendation", "Recommendation"], ["revision", "Original vs revised"], ["venues", "Venues"],
  ["model", "Financial model"], ["warnings", "Budget warnings"], ["lessons", "What We Learned"], ["drafts", "Outreach drafts"],
  ["sources", "Sources"], ["trace", "Agent trace"], ["usage", "Tokens & cost"],
] as const;

function Section({ id, title, icon, children, action }: { id: string; title: string; icon: ReactNode; children: ReactNode; action?: ReactNode }) {
  return <div id={id} className="scroll-mt-6 print-break-inside-avoid"><Card title={title} icon={icon} action={action}>{children}</Card></div>;
}

function Snapshot({ label, s, tone }: { label: string; s: StrategyPacket["revision"]["original"]; tone: "amber" | "green" | "plain" }) {
  if (!s) return null;
  const bg = tone === "amber" ? "bg-[#fbf1e3]" : tone === "green" ? "bg-[#e3f1e8]" : "bg-ivory";
  return (
    <div className={`rounded-2xl p-4 ${bg}`}>
      <p className="eyebrow">{label}</p>
      <p className="mt-1 font-display text-xl font-semibold text-plum">{s.venue}</p>
      <p className="text-sm capitalize text-muted">{s.event_format.replace("_", " ")}{s.pricing_status === "quote_required" ? " · quote required" : ""}</p>
      {s.total_usd != null && (
        <dl className="mt-2 grid grid-cols-2 gap-1 text-sm">
          <dt className="text-muted">Projected cost</dt><dd className="text-right font-semibold text-plum">{money(s.total_usd)}</dd>
          <dt className="text-muted">Upfront cash</dt><dd className="text-right">{money(s.upfront_cash_usd)}</dd>
          <dt className="text-muted">Base-case net</dt><dd className="text-right">{s.base_net_usd == null ? "incomplete" : money(s.base_net_usd)}</dd>
          <dt className="text-muted">Finance verdict</dt><dd className="text-right capitalize">{(s.verdict ?? s.finance_status ?? "—").replace(/_/g, " ")}</dd>
        </dl>
      )}
      {s.changes_from_previous && <p className="mt-2 text-sm text-ink"><b>What changed:</b> {s.changes_from_previous}</p>}
    </div>
  );
}

export default function PacketPage() {
  const { id } = useParams();
  const [packet, setPacket] = useState<StrategyPacket | null>(null);
  const [live, setLive] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const p = (await api<{ packet: StrategyPacket }>(`/api/runs/${id}/packet`)).packet;
      setPacket(p);
      if (["queued", "running"].includes(p.run.status)) {
        setLive(await api<RunDetail>(`/api/runs/${id}`));
        window.setTimeout(load, 2000);
      } else setLive(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the packet.");
    }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  if (error && !packet) return <ErrorState message={error} onRetry={load} />;
  if (!packet) return <LoadingState rows={5} />;
  const ev = (packet.overview.event ?? {}) as Record<string, string | number | null>;
  const rec = packet.recommendation;
  const m = packet.financial_model;
  const incomplete = ["stopped", "failed", "interrupted"].includes(packet.run.status);  // never presented as a finished plan
  const minContingency = packet.lessons.length ? (m?.assumptions.contingency_pct.kind === "lesson" ? m.assumptions.contingency_pct.value : null) : null;

  return (
    <>
      <div className="no-print mb-4 flex flex-wrap items-center justify-between gap-2">
        <Link to="/events" className="inline-flex items-center gap-1 text-sm text-royal hover:underline"><ArrowLeft size={14} aria-hidden="true" /> Event Studio</Link>
        <div className="flex flex-wrap gap-2">
          <a className="btn btn-soft text-sm" href={`/api/runs/${packet.run.id}/packet.md`}><Download size={14} aria-hidden="true" /> Download (Markdown)</a>
          <button className="btn btn-soft text-sm" onClick={() => window.print()}><Printer size={14} aria-hidden="true" /> Print / PDF</button>
          <Link className="btn btn-ghost text-sm" to={`/activity/runs/${packet.run.id}`}><ListTree size={14} aria-hidden="true" /> Full agent trace</Link>
        </div>
      </div>

      <header className="card mb-6 overflow-hidden !p-0">
        <div className="bg-gradient-to-br from-plum via-royal to-[#8b5cc0] px-6 py-7 text-white sm:px-8">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-lilac/90">Event Strategy Packet · #{packet.run.id}</p>
          <h1 className="mt-1 font-display text-4xl font-semibold leading-tight">{String(ev.name ?? "Fundraiser")}</h1>
          <p className="mt-1 text-sm text-lilac">
            {ev.attendance} guests · {String(ev.event_type ?? "")} · {String(ev.city ?? "")} · {ev.target_date ? formatDate(String(ev.target_date)) : "date to be set"}
            {ev.date_end ? ` to ${formatDate(String(ev.date_end))}` : ""}
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2"><StatusPill status={packet.run.status} /><ModeBadge mode={packet.run.research_mode} />
            {packet.run.options?.use_history === false && <span className="rounded-full bg-white/20 px-2.5 py-0.5 text-xs">History not used</span>}
            <span className="text-xs text-lilac">Generated {formatDate(packet.run.started_at)} · {packet.run.duration_ms ? `${Math.round(packet.run.duration_ms / 1000)} s` : ""} · ${packet.usage.cost_usd.toFixed(4)}</span>
          </div>
        </div>
        <nav aria-label="Packet sections" className="no-print flex flex-wrap gap-1 px-6 py-3 sm:px-8">
          {SECTIONS.map(([k, label]) => <a key={k} href={`#${k}`} className="rounded-full bg-lilac/60 px-2.5 py-1 text-xs font-semibold text-plum hover:bg-lilac">{label}</a>)}
        </nav>
      </header>

      {live && <Card title="The agents are still working" className="mb-6"><StrategyProgress detail={live} /></Card>}
      {incomplete && (
        <div role="alert" className="mb-6 flex gap-3 rounded-2xl border border-danger/25 bg-[#fbeef3] p-4 text-sm text-plum">
          <AlertTriangle size={18} className="mt-0.5 shrink-0 text-danger" aria-hidden="true" />
          <div>
            <p className="font-semibold">This workflow {packet.run.status === "failed" ? "failed" : "stopped"} before it finished.</p>
            {packet.run.error && <p className="text-muted">{packet.run.error}</p>}
            <p className="mt-1">The sections below show only what was finished before that point. There is no board recommendation, and an empty section means the step never ran, not that it found nothing.</p>
          </div>
        </div>
      )}

      <div className="space-y-6">
        <Section id="overview" title="1. Event overview" icon={<FileText size={16} aria-hidden="true" />}>
          <dl className="grid gap-2 sm:grid-cols-3">
            {([["Ticket price", money(ev.ticket_price_usd as number | null)], ["Fundraising target", money(ev.fundraising_goal_usd as number | null)],
               ["Maximum planning budget", money(ev.budget_limit_usd as number | null)], ["Expected attendees", ev.attendance], ["Event type", ev.event_type],
               ["Format", ev.event_format ? String(ev.event_format).replace("_", " ") : "chosen by the agents"]] as const).map(([k, v]) => (
              <div key={k} className="rounded-xl bg-ivory px-3 py-2"><dt className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">{k}</dt><dd className="font-semibold capitalize text-plum">{String(v ?? "—")}</dd></div>
            ))}
          </dl>
          {ev.instructions && <p className="mt-3 text-sm"><b className="text-plum">Board instructions:</b> {String(ev.instructions)}</p>}
          <p className="mt-2 text-xs text-muted">Request interpreted by the Orchestrator ({packet.overview.routing}).</p>
        </Section>

        {rec && (
          <Section id="recommendation" title="2. Board-ready recommendation" icon={<Lightbulb size={16} aria-hidden="true" />}>
            <p className="font-display text-2xl font-semibold leading-snug text-plum">{rec.headline}</p>
            <p className="mt-2 leading-relaxed">{rec.recommendation}</p>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              {([["Decisions for the board", rec.decisions_for_board], ["Next steps", rec.next_steps], ["Risks", rec.risks], ["Caveats", rec.caveats]] as const).map(([t, items]) =>
                items.length ? <div key={t}><p className="label">{t}</p><ul className="list-disc space-y-1 pl-5 text-sm">{items.map((x, i) => <li key={i}>{x}</li>)}</ul></div> : null)}
            </div>
            {rec.mission_impact_considerations && rec.mission_impact_considerations.length > 0 && (
              <div className="mt-5 rounded-2xl bg-blush/40 p-4">
                <p className="label">Mission impact considerations</p>
                <ul className="list-disc space-y-1 pl-5 text-sm">{rec.mission_impact_considerations.map((x, i) => <li key={i}>{x}</li>)}</ul>
                <p className="mt-1 text-xs text-muted">No scores. Mission alignment never overrides a financial limit or a spending restriction; the decision stays with the board.</p>
              </div>
            )}
            {packet.mission_contribution && (
              <div className="mt-5 rounded-2xl bg-lilac/40 p-4">
                <p className="label">Mission contribution (alongside the financial checks, never instead of them)</p>
                <dl className="mt-1 grid gap-2 text-sm md:grid-cols-2">
                  {([["inclusion", "Inclusion"], ["connection", "Connection"], ["accessibility", "Accessibility"], ["recognition", "Recognition"], ["charitable_alignment", "Charitable alignment"]] as const).map(([k, l]) => (
                    <div key={k}><dt className="font-semibold text-plum">{l}</dt><dd className="text-ink/85">{packet.mission_contribution?.[k] || "—"}</dd></div>))}
                </dl>
                {packet.mission_contribution.community_lessons_applied.length > 0 && (
                  <div className="mt-3 text-sm"><b className="text-plum">Community feedback applied</b>
                    <ul className="mt-1 list-disc space-y-0.5 pl-5">{packet.mission_contribution.community_lessons_applied.map((x, i) => <li key={i}>{x}</li>)}</ul></div>)}
                {packet.mission_contribution.open_questions.length > 0 && (
                  <div className="mt-2 text-sm"><b className="text-plum">Open questions</b>
                    <ul className="mt-1 list-disc space-y-0.5 pl-5">{packet.mission_contribution.open_questions.map((x, i) => <li key={i}>{x}</li>)}</ul></div>)}
              </div>
            )}
          </Section>
        )}

        <Section id="revision" title="3. Original and revised strategy" icon={<RefreshCcw size={16} aria-hidden="true" />}>
          {(packet.proposal_comparison ?? []).length > 1 && (
            <div className="-mx-2 mb-4 overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <caption className="sr-only">Proposals compared</caption>
                <thead><tr className="text-left text-xs text-muted"><th className="px-2 py-1">Proposal</th><th className="px-2 py-1">Venue</th><th className="px-2 py-1 text-right">Total</th>
                  <th className="px-2 py-1 text-right">Upfront</th><th className="px-2 py-1 text-right">Base net</th><th className="px-2 py-1 text-right">Conservative net</th><th className="px-2 py-1">Finance verdict</th></tr></thead>
                <tbody>{packet.proposal_comparison!.map((c) => (
                  <tr key={c.round} className="border-t border-lavender/30"><td className="px-2 py-1.5 font-semibold text-plum">{c.label}</td>
                    <td className="px-2 py-1.5">{c.venue}<span className="block text-xs capitalize text-muted">{c.event_format.replace("_", " ")}</span></td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{money(c.total_usd)}{c.round > 0 && <span className="block text-xs text-sage">{money(c.change_in_total_usd)}</span>}</td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{money(c.upfront_cash_usd)}</td><td className="px-2 py-1.5 text-right tabular-nums">{c.base_net_usd == null ? "—" : money(c.base_net_usd)}</td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{c.conservative_net_usd == null ? "—" : money(c.conservative_net_usd)}</td>
                    <td className="px-2 py-1.5 text-xs capitalize">{(c.verdict ?? "—").replace(/_/g, " ")}</td></tr>))}</tbody>
              </table>
            </div>
          )}
          {(packet.finance_feedback ?? []).map((fb, i) => (
            <div key={i} className="mb-4 rounded-2xl bg-[#fbf1e3]/70 p-3 text-sm">
              <p className="font-semibold text-plum">Structured feedback Finance sent to the Events agent about {fb.venue}</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5">{fb.issues.map((x, j) => <li key={j}>{x.detail}{x.over_by_usd != null ? ` Over by ${money(x.over_by_usd)}.` : ""}</li>)}</ul>
              <p className="mt-1 text-xs text-muted">Largest costs: {fb.cost_drivers.map((d) => `${d.line} ${money(d.amount_usd)}${d.share_of_total ? ` (${Math.round(d.share_of_total * 100)}%)` : ""}`).join(" · ")}</p>
            </div>
          ))}
          {packet.revision.revised ? (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                <Snapshot label="Original plan" s={packet.revision.original} tone="amber" />
                <Snapshot label="Revised plan" s={packet.revision.revised} tone="green" />
              </div>
              <p className="label mt-4">Why the Orchestrator asked for a revision</p>
              <ul className="space-y-1.5 text-sm">{packet.revision.reasons.map((r, i) => (
                <li key={i} className="flex gap-2"><span className={`h-fit rounded-full px-2 py-0.5 text-[0.65rem] font-semibold uppercase ${r.source === "history" ? "bg-blush text-plum" : "bg-[#fbf1e3] text-amber"}`}>{r.source}</span>{r.detail}</li>))}</ul>
            </>
          ) : (
            <><Snapshot label="Plan" s={packet.revision.original} tone="plain" />
              <p className="mt-3 text-sm text-muted">{incomplete ? "Not produced: the workflow stopped before the plan was checked." : "No revision was needed: the first plan passed Finance's checks and the history checks."}</p></>
          )}
        </Section>

        <Section id="venues" title="4. Venue shortlist and research" icon={<Building2 size={16} aria-hidden="true" />}>
          <div className="grid gap-3 lg:grid-cols-2">
            {[...packet.venues].sort((a, b) => (a.shortlist_rank ?? 99) - (b.shortlist_rank ?? 99)).map((v) => (
              <article key={v.name} className={`rounded-2xl border p-4 ${v.shortlist_rank ? "border-royal/50 bg-lilac/30" : "border-lavender/35 bg-white/80"}`}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div><p className="font-display text-xl font-semibold text-plum">{v.shortlist_rank ? `#${v.shortlist_rank} ` : ""}{v.name}</p>
                    <p className="text-xs text-muted">{v.location ?? "Location not stated"}</p></div>
                  <VerificationBadge value={v.verification} />
                </div>
                <dl className="mt-2 grid grid-cols-[7rem_1fr] gap-y-1 text-sm">
                  <dt className="text-muted">Website</dt><dd>{v.website && v.verification !== "synthetic" ? <a href={v.website} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-royal underline">{new URL(v.website).hostname}<ExternalLink size={11} aria-hidden="true" /></a> : v.website ? <span className="text-muted">example.org (synthetic)</span> : "—"}
                    <span className="ml-1 text-xs text-muted">({v.website_status ?? "unchecked"}{v.verified_at ? `, checked ${formatDate(v.verified_at)}` : ""})</span></dd>
                  <dt className="text-muted">Capacity</dt><dd>{Object.entries(v.capacity).map(([k, n]) => `${k.replace("_", " ")} ${n}`).join(" · ") || "not published"}
                    {v.capacity_status && v.capacity_status !== "published" && <span className="ml-1 text-xs text-amber">({v.capacity_status.replace("_", " ")})</span>}</dd>
                  <dt className="text-muted">Pricing</dt><dd className={v.pricing_status === "published" ? "" : "font-semibold text-amber"}>{v.pricing}</dd>
                </dl>
                {v.amenities.length > 0 && <p className="mt-2 flex flex-wrap gap-1">{v.amenities.map((a) => <span key={a} className="rounded-full bg-[#e3f1e8] px-2 py-0.5 text-[0.7rem] text-sage">{a}</span>)}</p>}
                {v.restrictions.length > 0 && <p className="mt-1 flex flex-wrap gap-1">{v.restrictions.map((a) => <span key={a} className="rounded-full bg-[#fbeef3] px-2 py-0.5 text-[0.7rem] text-danger">{a}</span>)}</p>}
                {v.notes && <p className="mt-2 text-xs text-muted">{v.notes}</p>}
              </article>
            ))}
          </div>
          {packet.venues.length === 0 && <p className="text-sm text-muted">{incomplete ? "Not produced: the workflow stopped before venue research finished." : "No venues were found for this request."}</p>}
        </Section>

        <Section id="model" title="5. Preliminary financial model" icon={<Coins size={16} aria-hidden="true" />}>
          {packet.finance_visible ? (m ? <FinancialModelEditor model={m} affordability={packet.affordability} planId={packet.run.event_plan_id} minContingency={minContingency as number | null} />
            : <p className="text-sm text-muted">Finance did not complete for this run.</p>)
            : <p className="flex items-center gap-2 text-sm text-muted"><Lock size={15} aria-hidden="true" /> Financial details are limited to the chair and treasurer.</p>}
        </Section>

        <Section id="warnings" title="6. Budget warnings" icon={<AlertTriangle size={16} aria-hidden="true" />}>
          {packet.budget_warnings.length === 0 ? <p className="text-sm text-sage">No warnings.</p> : (
            <ul className="space-y-1.5 text-sm">{packet.budget_warnings.map((w, i) => {
              const Icon = w.level === "conflict" ? XCircle : w.level === "warning" ? AlertTriangle : CircleSlash;
              return <li key={i} className="flex gap-2"><Icon size={16} className={`mt-0.5 shrink-0 ${w.level === "conflict" ? "text-danger" : w.level === "warning" ? "text-amber" : "text-muted"}`} aria-label={w.level} />{w.text}</li>;
            })}</ul>
          )}
        </Section>

        <Section id="lessons" title="7. What We Learned" icon={<History size={16} aria-hidden="true" />}>
          {(packet.what_we_learned?.events_consulted ?? []).length > 0 && (
            <div className="mb-4"><p className="label">Past events consulted (chosen in code by similarity to this plan)</p>
              <ul className="flex flex-wrap gap-2">{packet.what_we_learned!.events_consulted.map((c) => (
                <li key={c.id} className="rounded-xl bg-lilac/40 px-3 py-1.5 text-sm"><Link to={`/legacy/${c.id}`} className="font-semibold text-royal underline">{c.name}</Link>
                  <span className="block text-xs text-muted">{c.reasons.join(" · ")}</span></li>))}</ul></div>
          )}
          {(packet.what_we_learned?.quantitative_observations ?? []).length > 0 && (
            <div className="mb-4"><p className="label">Computed from recorded figures</p>
              <ul className="space-y-1.5 text-sm">{packet.what_we_learned!.quantitative_observations.map((o, i) => (
                <li key={i} className="rounded-xl bg-ivory/80 px-3 py-2">{o.text} <span className="text-xs text-muted">{o.sample_note}</span></li>))}</ul></div>
          )}
          {packet.lessons.length === 0 ? <p className="text-sm text-muted">Historical lessons were not used in this run.</p> : (
            <ul className="space-y-2.5">{packet.lessons.map((l, i) => (
              <li key={i} className="rounded-xl bg-ivory/80 px-3.5 py-2.5 text-sm">
                <p><span className="mr-1.5 rounded bg-lilac px-1.5 text-[0.65rem] uppercase text-royal">{l.kind.replace(/_/g, " ")}</span>{l.text}
                  {l.basis_label && <span className={`ml-1.5 rounded-full px-1.5 py-0.5 text-[0.65rem] font-semibold ${l.basis === "board_feedback" ? "bg-blush/70 text-plum" : "bg-white text-royal ring-1 ring-lavender/40"}`}>{l.basis_label}</span>}</p>
                <p className="mt-1 flex flex-wrap gap-1.5 text-xs"><span className="text-muted">Supporting records:</span>
                  {l.events.map((e) => <Link key={e.id} to={`/legacy/${e.id}`} className="text-royal underline">{e.name}</Link>)}
                  {l.reflection_ids.length > 0 && <span className="text-muted">{l.reflection_ids.length} board reflection{l.reflection_ids.length === 1 ? "" : "s"}</span>}</p>
              </li>))}</ul>
          )}
          {(packet.community_insights ?? []).length > 0 && (
            <div className="mt-4"><p className="label">Community feedback from past events (quoted from board reflections)</p>
              <ul className="space-y-1.5 text-sm">{packet.community_insights?.map((c, i) => (
                <li key={i} className="rounded-xl bg-blush/40 px-3 py-2"><b className="text-plum">{c.lens_label}:</b> {c.observation} <span className="italic text-ink/80">“{c.quote}”</span>
                  <span className="ml-1 text-xs text-muted">({c.evidence_label})</span></li>))}</ul></div>
          )}
          {(packet.what_we_learned?.influence ?? []).length > 0 && (
            <div className="mt-4"><p className="label">How prior experience shaped this plan</p>
              <ul className="space-y-1.5 text-sm">{packet.what_we_learned!.influence.filter((x) => x.area !== "History check").map((x, i) => (
                <li key={i} className="rounded-xl bg-white/80 px-3 py-2 ring-1 ring-lavender/30"><b className="text-plum">{x.area}:</b> {x.detail} <span className="text-xs text-muted">({x.by})</span></li>))}</ul></div>
          )}
          {packet.history_checks.length > 0 && (
            <div className="mt-4"><p className="label">How history was checked against the plan</p>
              <ul className="space-y-1.5 text-sm">{packet.history_checks.map((h, i) => (
                <li key={i} className="flex gap-2">{h.passed ? <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-sage" aria-label="passed" /> : <XCircle size={16} className="mt-0.5 shrink-0 text-danger" aria-label="failed" />}
                  <span><b className="text-plum">{h.name}.</b> {h.detail} {h.events.map((e) => <Link key={e.id} to={`/legacy/${e.id}`} className="ml-1 text-xs text-royal underline">{e.name}</Link>)}</span></li>))}</ul></div>
          )}
        </Section>

        <Section id="drafts" title="8. Unsent venue inquiry drafts" icon={<FileText size={16} aria-hidden="true" />}>
          <p className="mb-3 text-xs text-muted">Editable and saved. SAM SPACE cannot send email: copy a draft and send it yourself if the board agrees.</p>
          {packet.drafts.length === 0 ? <p className="text-sm text-muted">No drafts were created.</p> : (
            <ul className="space-y-3">{packet.drafts.map((d) => (
              <DraftItem key={d.id} onChange={load} draft={{ id: d.id, run_id: packet.run.id, agent: "partnerships_outreach", draft_type: d.draft_type, recipient_name: "",
                recipient_org: d.recipient, subject: d.subject, body: d.body, status: d.status, personalization_basis: null, is_synthetic_target: d.is_synthetic_target,
                created_at: packet.run.started_at } as Draft} />))}</ul>
          )}
        </Section>

        <Section id="sources" title="9. Supporting sources" icon={<ExternalLink size={16} aria-hidden="true" />}>
          <ul className="space-y-1.5 text-sm">{packet.sources.map((s, i) => (
            <li key={i} className="flex flex-wrap items-center gap-2"><VerificationBadge value={s.verification} />
              {s.url && s.verification !== "synthetic" ? <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-royal underline">{s.title || s.url}</a> : <span>{s.title}</span>}
              {s.http_status && <span className="text-xs text-muted">HTTP {s.http_status}</span>}
              {s.retrieved_at && <span className="text-xs text-muted">checked {formatDate(s.retrieved_at)}</span>}
              {s.note && s.verification !== "verified" && <span className="text-xs text-amber">{s.note}</span>}
            </li>))}
            {packet.sources.length === 0 && <li className="text-muted">No external sources.</li>}</ul>
        </Section>

        <Section id="trace" title="10. Agent handoff trace" icon={<ListTree size={16} aria-hidden="true" />}
          action={<Link className="no-print text-xs text-royal hover:underline" to={`/activity/runs/${packet.run.id}`}>Open the full trace</Link>}>
          <div className="-mx-2 overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-muted"><tr><th className="px-2 py-1">#</th><th className="px-2">From → to</th><th className="px-2">Step</th><th className="px-2">Status</th><th className="px-2">Models</th><th className="px-2">Tokens in/out</th><th className="px-2">Cost</th></tr></thead>
              <tbody>{packet.trace.map((t) => (
                <tr key={t.n} className={`border-t border-lavender/25 align-top ${t.kind === "revision" ? "bg-blush/30" : ""}`}>
                  <td className="px-2 py-1.5">{t.n}</td>
                  <td className="px-2 py-1.5 text-xs">{AGENT_LABELS[t.from_agent] ?? t.from_agent} → <b className="text-plum">{AGENT_LABELS[t.to_agent] ?? t.to_agent}</b></td>
                  <td className="px-2 py-1.5">{stepLabel(t.step_key)}</td>
                  <td className="px-2 py-1.5"><StatusPill status={t.status} /></td>
                  <td className="px-2 py-1.5 text-xs">{t.models.join(", ") || "code only"}</td>
                  <td className="px-2 py-1.5 text-xs">{t.input_tokens.toLocaleString()} / {t.output_tokens.toLocaleString()}</td>
                  <td className="px-2 py-1.5 text-xs">${t.cost_usd.toFixed(4)}</td>
                </tr>))}</tbody>
            </table>
          </div>
        </Section>

        <Section id="usage" title="11. Token usage and cost" icon={<Coins size={16} aria-hidden="true" />}>
          <div className="grid gap-3 sm:grid-cols-4">
            {([["Model calls", packet.usage.model_calls], ["Web searches", packet.usage.web_search_calls],
               ["Tokens in (cached)", `${packet.usage.input_tokens.toLocaleString()} (${packet.usage.cached_input_tokens.toLocaleString()})`],
               ["Tokens out", packet.usage.output_tokens.toLocaleString()]] as const).map(([k, v]) => (
              <div key={k} className="rounded-xl bg-ivory px-3 py-2"><p className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">{k}</p><p className="font-display text-2xl font-semibold text-plum">{v}</p></div>
            ))}
          </div>
          <p className="mt-3 text-sm">Total cost at official list prices: <b className="text-plum">${packet.usage.cost_usd.toFixed(4)}</b></p>
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            {([["By agent", packet.usage.by_agent], ["By model", packet.usage.by_model]] as const).map(([t, rows]) => (
              <div key={t}><p className="label">{t}</p><table className="w-full text-left text-xs"><tbody>
                {Object.entries(rows).map(([k, r]) => <tr key={k} className="border-t border-lavender/25"><td className="py-1">{AGENT_LABELS[k] ?? k}</td><td className="py-1">{r.calls} calls</td>
                  <td className="py-1">{r.input_tokens.toLocaleString()} / {r.output_tokens.toLocaleString()}</td><td className="py-1 text-right">${r.cost_usd.toFixed(4)}</td></tr>)}
              </tbody></table></div>))}
          </div>
          {packet.verification && (
            <div className="mt-4"><p className="label flex items-center gap-1"><ShieldCheck size={13} aria-hidden="true" /> Verification</p>
              <ul className="space-y-1 text-sm">{packet.verification.checks.map((c) => (
                <li key={c.name} className="flex gap-2">{c.passed === true ? <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-sage" aria-label="passed" /> : c.passed === false ? <XCircle size={15} className="mt-0.5 shrink-0 text-danger" aria-label="failed" /> : <CircleSlash size={15} className="mt-0.5 shrink-0 text-amber" aria-label="note" />}
                  <span><b className="text-plum">{c.name}.</b> <span className="text-muted">{c.detail}</span></span></li>))}</ul></div>
          )}
        </Section>
      </div>
    </>
  );
}
