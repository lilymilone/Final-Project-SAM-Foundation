import {
  AlertTriangle, ArrowLeft, CheckCircle2, CircleSlash, Coins, Download, ExternalLink, FileText, ListTree, Printer, ShieldCheck, Sparkles,
  Users, XCircle,
} from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Opportunity, PartnershipPacket } from "../api/types";
import { formatDate } from "../api/useApi";
import { AGENT_LABELS, ModeBadge, StatusPill, VerificationBadge } from "../components/agents";
import { AlignmentDetails, FitBadge } from "../components/opportunities";
import { Card, DemoBadge, ErrorState, LoadingState } from "../components/ui";

const SECTIONS = [["recommendation", "Recommendation"], ["selected", "Selected"], ["excluded", "Not selected"], ["drafts", "Drafts"],
  ["sources", "Sources"], ["trace", "Agent trace"], ["usage", "Tokens & cost"]] as const;

function Section({ id, title, icon, children }: { id: string; title: string; icon: ReactNode; children: ReactNode }) {
  return <div id={id} className="scroll-mt-6 print-break-inside-avoid"><Card title={title} icon={icon}>{children}</Card></div>;
}

function Selected({ o }: { o: Opportunity }) {
  return (
    <li className="rounded-2xl border border-lavender/35 bg-white/85 p-4">
      <div className="flex flex-wrap items-center gap-1.5"><FitBadge fit={o.fit} /><VerificationBadge value={o.verification} />
        <span className="text-xs capitalize text-muted">{o.category}{o.geography ? ` · ${o.geography}` : ""}</span>{o.is_synthetic && <DemoBadge label="Synthetic fixture" />}</div>
      <p className="mt-1 font-display text-xl font-semibold text-plum">{o.name}</p>
      <p className="text-sm text-ink/90">{o.purpose}</p>
      <p className="mt-1 text-sm"><b className="text-plum">Why selected:</b> {o.selection_reason}</p>
      <dl className="mt-2 grid grid-cols-1 gap-1 text-sm sm:grid-cols-2">
        <div><dt className="inline text-muted">Dates: </dt><dd className="inline">{o.dates_text || "not stated"}{o.date_status && o.date_status !== "none" ? ` (${o.date_status})` : ""}</dd></div>
        <div><dt className="inline text-muted">Known costs: </dt><dd className="inline">{o.known_costs || "not stated on the source"}</dd></div>
        <div><dt className="inline text-muted">Last checked: </dt><dd className="inline">{o.last_checked ? formatDate(o.last_checked) : "—"}</dd></div>
        <div><dt className="inline text-muted">Next step: </dt><dd className="inline">{o.next_step || "—"}</dd></div>
      </dl>
      {(o.warnings.length > 0 || o.missing_info.length > 0) && (
        <ul className="mt-2 space-y-0.5 rounded-xl bg-[#fbf1e3]/80 px-3 py-2 text-xs text-amber">
          {o.warnings.map((w) => <li key={w}>⚠ {w}</li>)}{o.missing_info.map((m) => <li key={m}>Missing: {m}</li>)}
        </ul>
      )}
      <AlignmentDetails o={o} />
    </li>
  );
}

export default function PartnershipPacketPage() {
  const { id } = useParams();
  const [p, setP] = useState<PartnershipPacket | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      const packet = (await api<{ packet: PartnershipPacket }>(`/api/runs/${id}/partnership-packet`)).packet;
      setP(packet);
      if (["queued", "running"].includes(packet.run.status)) window.setTimeout(load, 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the packet.");
    }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  if (error && !p) return <ErrorState message={error} onRetry={load} />;
  if (!p) return <LoadingState rows={5} />;
  const rec = p.recommendation;
  return (
    <>
      <div className="no-print mb-4 flex flex-wrap items-center justify-between gap-2">
        <Link to="/partnerships" className="inline-flex items-center gap-1 text-sm text-royal hover:underline"><ArrowLeft size={14} aria-hidden="true" /> Partnerships & Outreach</Link>
        <div className="flex flex-wrap gap-2">
          <a className="btn btn-soft text-sm" href={`/api/runs/${p.run.id}/partnership-packet.md`}><Download size={14} aria-hidden="true" /> Download (Markdown)</a>
          <button className="btn btn-soft text-sm" onClick={() => window.print()}><Printer size={14} aria-hidden="true" /> Print / PDF</button>
          <Link className="btn btn-ghost text-sm" to={`/activity/runs/${p.run.id}`}><ListTree size={14} aria-hidden="true" /> Full agent trace</Link>
        </div>
      </div>
      <Card className="mb-5">
        <p className="eyebrow">Partnership Opportunity Packet · workflow #{p.run.id}</p>
        <h1 className="mt-1 font-display text-3xl font-semibold leading-tight text-plum">“{p.request}”</h1>
        <p className="mt-1 font-display text-lg italic text-royal">“{p.philosophy}”</p>
        <div className="mt-2 flex flex-wrap items-center gap-2"><StatusPill status={p.run.status} /><ModeBadge mode={p.run.research_mode} />
          <span className="text-xs text-muted">{formatDate(p.run.started_at)}{p.run.duration_ms ? ` · ${(p.run.duration_ms / 1000).toFixed(0)} s` : ""}</span></div>
        <p className="mt-3 flex items-start gap-2 rounded-xl bg-lilac/60 px-3 py-2 text-sm text-plum">
          <ShieldCheck size={15} className="mt-0.5 shrink-0" aria-hidden="true" />Nothing in this packet has been sent. Every draft waits for a person to review it and send it outside SAM SPACE.
        </p>
        {p.run.research_mode === "synthetic" && <p className="mt-2 rounded-xl bg-blush/60 px-3 py-2 text-xs text-plum">This run used labeled synthetic fixtures (example.org). The organizations are not real.</p>}
        {p.run.error && <p className="mt-2 rounded-xl bg-[#fbeef3] px-3 py-2 text-sm text-danger">{p.run.error}</p>}
        <nav aria-label="Packet sections" className="no-print mt-4 flex flex-wrap gap-1.5">
          {SECTIONS.map(([k, l]) => <a key={k} href={`#${k}`} className="rounded-full bg-lilac/60 px-3 py-1 text-xs font-semibold text-plum hover:bg-lilac">{l}</a>)}
        </nav>
      </Card>

      <div className="space-y-5">
        <Section id="recommendation" title="Board recommendation" icon={<Sparkles size={16} aria-hidden="true" />}>
          {!rec ? <p className="text-sm text-muted">{["queued", "running"].includes(p.run.status) ? "The agents are still working…" : "No recommendation was produced."}</p> : (
            <>
              <p className="font-display text-2xl font-semibold text-plum">{rec.headline}</p>
              <p className="mt-1 text-ink">{rec.recommendation}</p>
              <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2">
                <div><p className="eyebrow">Why</p><ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm">{rec.rationale.map((x) => <li key={x}>{x}</li>)}</ul></div>
                <div><p className="eyebrow">Decisions for the board</p><ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm">{rec.decisions_for_board.map((x) => <li key={x}>{x}</li>)}</ul></div>
                <div><p className="eyebrow">Risks</p><ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm">{rec.risks.map((x) => <li key={x}>{x}</li>)}</ul></div>
                <div><p className="eyebrow">Next steps</p><ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm">{rec.next_steps.map((x) => <li key={x}>{x}</li>)}</ul></div>
              </div>
              {rec.caveats.length > 0 && <ul className="mt-3 space-y-0.5 rounded-xl bg-ivory px-3 py-2 text-xs text-muted">{rec.caveats.map((c) => <li key={c}>• {c}</li>)}</ul>}
            </>
          )}
        </Section>

        <Section id="selected" title={`Selected opportunities (${p.selected.length}${p.count_requested ? ` of ${p.count_requested} requested` : ""})`} icon={<Users size={16} aria-hidden="true" />}>
          {p.selection_warnings.map((w) => <p key={w} className="mb-2 flex gap-1.5 text-sm text-amber"><AlertTriangle size={14} className="mt-0.5" aria-hidden="true" />{w}</p>)}
          {p.unresolved.map((u) => <p key={u.detail} className="mb-2 text-sm text-amber">{u.detail}</p>)}
          <ul className="space-y-3">{p.selected.map((o) => <Selected key={o.id} o={o} />)}</ul>
        </Section>

        <Section id="excluded" title="Considered but not selected" icon={<CircleSlash size={16} aria-hidden="true" />}>
          {p.excluded.length === 0 ? <p className="text-sm text-muted">None.</p> : (
            <ul className="space-y-1.5 text-sm">{p.excluded.map((x) => (
              <li key={x.id} className="flex flex-wrap items-center gap-1.5"><FitBadge fit={x.fit ?? null} /><b className="text-plum">{x.name}</b><span className="text-ink/80">{x.reason}</span></li>))}</ul>
          )}
          <p className="mt-2 text-xs text-muted">Selection is done in code by the fit rubric (Strong, then Possible fit, with checked sources first). Dismissed opportunities are never selected.</p>
        </Section>

        <Section id="drafts" title="Unsent outreach drafts" icon={<FileText size={16} aria-hidden="true" />}>
          <ul className="space-y-4">{p.drafts.map((d) => (
            <li key={d.id} className="rounded-2xl border border-lavender/35 bg-white/85 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">{d.draft_type.replace(/_/g, " ")} · to {d.recipient} · <span className="text-royal">{d.status === "draft" ? "unsent draft" : `${d.status}, unsent`}</span></p>
              <p className="font-display text-lg font-semibold text-plum">{d.subject}</p>
              <dl className="mt-1 grid grid-cols-1 gap-1 text-sm md:grid-cols-3">
                <div><dt className="text-muted">Purpose</dt><dd>{d.purpose || "—"}</dd></div>
                <div><dt className="text-muted">Opportunity</dt><dd>{d.opportunity || "—"}</dd></div>
                <div><dt className="text-muted">Next step</dt><dd>{d.next_step || "—"}</dd></div>
              </dl>
              <pre className="mt-2 whitespace-pre-wrap rounded-xl bg-ivory p-3 font-sans text-sm text-ink">{d.body}</pre>
              {d.review_notes.length > 0 && <ul className="mt-2 list-disc pl-5 text-xs text-amber">{d.review_notes.map((n) => <li key={n}>Confirm first: {n}</li>)}</ul>}
              <p className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted">Sources: {d.sources.map((s, i) => (
                <span key={i} className="inline-flex items-center gap-1">{s.url && s.verification !== "synthetic" ? <a href={s.url} className="text-royal hover:underline" target="_blank" rel="noopener noreferrer">{s.title}</a> : s.title}<VerificationBadge value={s.verification} /></span>))}</p>
            </li>))}</ul>
          <p className="no-print mt-3 text-xs text-muted">Edit, copy, or archive these drafts in <Link to="/partnerships" className="text-royal hover:underline">Partnerships & Outreach</Link>.</p>
        </Section>

        <Section id="sources" title="Supporting sources" icon={<ExternalLink size={16} aria-hidden="true" />}>
          <ul className="space-y-1.5 text-sm">{p.sources.map((s, i) => (
            <li key={i} className="flex flex-wrap items-center gap-2"><VerificationBadge value={s.verification} />
              {s.url && s.verification !== "synthetic" ? <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-royal hover:underline">{s.title}</a> : <span>{s.title}</span>}
              <span className="text-xs text-muted">{s.retrieved_at ? `checked ${formatDate(s.retrieved_at)}` : ""}{s.note ? ` · ${s.note}` : ""}</span></li>))}</ul>
        </Section>

        <Section id="trace" title="Agent handoff trace" icon={<ListTree size={16} aria-hidden="true" />}>
          <ol className="space-y-2">{p.trace.map((t) => (
            <li key={t.n} className="rounded-xl bg-ivory/80 px-3 py-2 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span><b className="text-plum">{t.n}. {AGENT_LABELS[t.from_agent] ?? t.from_agent} → {AGENT_LABELS[t.to_agent] ?? t.to_agent}</b> <span className="text-muted">({t.step_key})</span></span>
                <span className="flex items-center gap-2 text-xs text-muted">{t.models.join(", ") || "code"} · {t.input_tokens.toLocaleString()}/{t.output_tokens.toLocaleString()} tok · ${t.cost_usd.toFixed(4)}<StatusPill status={t.status} /></span>
              </div>
              <p className="text-ink/85">{t.objective}</p>
              {t.summary && <p className="text-xs text-muted">{t.summary}</p>}
              {t.constraints && t.constraints.length > 0 && (
                <ul className="mt-1 space-y-0.5 text-xs text-royal">{t.constraints.map((c) => <li key={c.name}>Passed along: {c.detail}</li>)}</ul>)}
            </li>))}</ol>
        </Section>

        <Section id="usage" title="Tokens and cost" icon={<Coins size={16} aria-hidden="true" />}>
          <p className="text-sm">{p.usage.model_calls} model calls · {p.usage.web_search_calls} web searches · {p.usage.input_tokens.toLocaleString()} input tokens ({p.usage.cached_input_tokens.toLocaleString()} cached) · {p.usage.output_tokens.toLocaleString()} output · <b className="text-plum">${p.usage.cost_usd.toFixed(4)}</b></p>
          <table className="mt-2 w-full text-sm"><thead><tr className="text-left text-xs text-muted"><th>Model</th><th>Calls</th><th>In (cached)</th><th>Out</th><th className="text-right">Cost</th></tr></thead>
            <tbody>{Object.entries(p.usage.by_model).map(([m, u]) => (
              <tr key={m} className="border-t border-lavender/30"><td className="py-1 font-semibold text-plum">{m}</td><td>{u.calls}</td><td>{u.input_tokens.toLocaleString()} ({u.cached_input_tokens.toLocaleString()})</td><td>{u.output_tokens.toLocaleString()}</td><td className="text-right">${u.cost_usd.toFixed(4)}</td></tr>))}</tbody></table>
          {p.verification && (
            <ul className="mt-3 space-y-1 text-sm">{p.verification.checks.map((c) => (
              <li key={c.name} className="flex gap-1.5">{c.passed ? <CheckCircle2 size={15} className="mt-0.5 text-sage" aria-hidden="true" /> : c.passed === false ? <XCircle size={15} className="mt-0.5 text-danger" aria-hidden="true" /> : <CircleSlash size={15} className="mt-0.5 text-muted" aria-hidden="true" />}
                <span><b className="text-plum">{c.name}.</b> {c.detail}</span></li>))}</ul>
          )}
        </Section>
      </div>
    </>
  );
}
