import { BookOpenCheck, Download, ExternalLink, FileUp, Pencil, PlusCircle, Scale, Search, ShieldCheck, Sparkles, X } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { CampaignRow, ComplianceItem, ComplianceRef, DonationRow, RunSummary } from "../api/types";
import { formatDate, useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { useButterflies } from "../butterflies/ButterflyProvider";
import { Card, DemoBadge, EmptyState, LoadingState, ShowMore } from "./ui";

export const money = (n: number | null | undefined) => n == null ? "—" : `$${n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
export const TYPE_LABEL: Record<string, string> = { monetary: "Monetary", in_kind: "In-kind", event_ticket: "Event ticket", sponsorship: "Sponsorship", matching_gift: "Matching gift" };
export const PAYMENT_LABEL: Record<string, string> = { received: "Received", pledged: "Pledged (not received)", pending: "Pending", returned: "Returned" };
export const ACK_LABEL: Record<string, string> = { not_started: "Not started", prepared: "Prepared", completed: "Completed (sent by a person)", not_needed: "Not needed" };
export const RESTRICTION_LABEL: Record<string, string> = { unrestricted: "Unrestricted", temporarily_restricted: "Restricted (purpose/time)", permanently_restricted: "Permanently restricted" };
const SEV: Record<string, string> = { high: "bg-[#fbeef3] text-danger", medium: "bg-[#fbf1e3] text-amber", low: "bg-ivory text-muted" };
const KIND: Record<string, [string, string]> = {
  verified_requirement: ["Verified requirement (cited)", "bg-[#e3f1e8] text-sage"], general_guidance: ["General guidance", "bg-lilac text-royal"],
  needs_professional_review: ["Needs professional review", "bg-[#fbf1e3] text-amber"],
};

// ── Add / edit ──────────────────────────────────────────────────────────────────

type FormState = Record<string, string>;
const blank: FormState = { donor_name: "", donor_email: "", received_on: "", amount_usd: "", contribution_type: "monetary", payment_status: "received",
  ack_status: "not_started", restriction: "", designation: "General fund", method: "", campaign_id: "", in_kind_description: "", goods_services_value_usd: "", notes: "" };

function toForm(d: DonationRow): FormState {
  return { donor_name: d.donor_name, donor_email: "", received_on: d.received_on, amount_usd: String(d.amount_usd), contribution_type: d.contribution_type,
    payment_status: d.payment_status, ack_status: d.ack_status, restriction: d.restriction ?? "", designation: d.designation, method: d.method ?? "",
    campaign_id: d.campaign_id ? String(d.campaign_id) : "", in_kind_description: d.in_kind_description ?? "",
    goods_services_value_usd: d.goods_services_value_usd != null ? String(d.goods_services_value_usd) : "", notes: d.notes };
}

export function DonationForm({ campaigns, initial, onDone, onCancel }: { campaigns: CampaignRow[]; initial?: DonationRow; onDone: () => void; onCancel?: () => void }) {
  const { celebrate } = useButterflies();
  const [f, setF] = useState<FormState>(initial ? toForm(initial) : blank);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [dupe, setDupe] = useState(false);
  const [busy, setBusy] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);
  const set = (k: string) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  async function submit(e: FormEvent | null, confirm = false) {
    e?.preventDefault();
    setBusy(true);
    setMsg(null);
    const body: Record<string, unknown> = {
      received_on: f.received_on, amount_usd: Number(f.amount_usd || 0), contribution_type: f.contribution_type, payment_status: f.payment_status,
      ack_status: f.ack_status, restriction: f.restriction || (initial ? "not_documented" : null), designation: f.designation, method: f.method || null,
      campaign_id: f.campaign_id ? Number(f.campaign_id) : null, in_kind_description: f.in_kind_description || null,
      goods_services_value_usd: f.goods_services_value_usd ? Number(f.goods_services_value_usd) : null, notes: f.notes,
    };
    try {
      if (initial) {
        await api(`/api/donations/${initial.id}`, { method: "PUT", json: body });
      } else {
        await api("/api/donations", { json: { ...body, donor_name: f.donor_name, donor_email: f.donor_email || null, confirm_duplicate: confirm } });
        celebrate("save", btn.current);  // only after the record was saved
        setF(blank);
      }
      setMsg({ ok: true, text: initial ? "Changes saved." : "Donation recorded." });
      setDupe(false);
      onDone();
    } catch (err) {
      const text = err instanceof Error ? err.message : "Could not save.";
      setDupe(text.includes("Confirm if this is a separate gift"));
      setMsg({ ok: false, text });
    } finally {
      setBusy(false);
    }
  }
  const field = "field !py-1.5 text-sm";
  return (
    <form onSubmit={(e) => submit(e)} className="grid grid-cols-1 gap-2 sm:grid-cols-3">
      {!initial && <>
        <div><label className="label" htmlFor="dn">Donor name</label><input id="dn" className={field} required maxLength={200} value={f.donor_name} onChange={set("donor_name")} /></div>
        <div><label className="label" htmlFor="de">Email (optional)</label><input id="de" type="email" className={field} value={f.donor_email} onChange={set("donor_email")} /></div>
      </>}
      <div><label className="label" htmlFor="dd">Date received</label><input id="dd" type="date" className={field} required value={f.received_on} onChange={set("received_on")} /></div>
      <div><label className="label" htmlFor="da">Amount (USD)</label><input id="da" type="number" min={0} step="0.01" className={field} required value={f.amount_usd} onChange={set("amount_usd")} /></div>
      <div><label className="label" htmlFor="dt">Contribution type</label><select id="dt" className={field} value={f.contribution_type} onChange={set("contribution_type")}>
        {Object.entries(TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
      <div><label className="label" htmlFor="dp">Payment status</label><select id="dp" className={field} value={f.payment_status} onChange={set("payment_status")}>
        {Object.entries(PAYMENT_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
      <div><label className="label" htmlFor="dc">Campaign or event</label><select id="dc" className={field} value={f.campaign_id} onChange={set("campaign_id")}>
        <option value="">None</option>{campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
      <div><label className="label" htmlFor="dr">Restriction</label><select id="dr" className={field} value={f.restriction} onChange={set("restriction")}>
        <option value="">Not documented</option>{Object.entries(RESTRICTION_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
      <div><label className="label" htmlFor="dm">Method</label><select id="dm" className={field} value={f.method} onChange={set("method")}>
        <option value="">Not recorded</option>{["check", "online", "wire", "cash", "card", "stock", "other"].map((m) => <option key={m} value={m}>{m}</option>)}</select></div>
      <div><label className="label" htmlFor="dk">Acknowledgment</label><select id="dk" className={field} value={f.ack_status} onChange={set("ack_status")}>
        {Object.entries(ACK_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
      <div><label className="label" htmlFor="dg">Goods/services value received (if any)</label><input id="dg" type="number" min={0} step="0.01" className={field} value={f.goods_services_value_usd} onChange={set("goods_services_value_usd")} /></div>
      {f.contribution_type === "in_kind" && <div className="sm:col-span-2"><label className="label" htmlFor="di">In-kind description (no value)</label><input id="di" className={field} maxLength={300} value={f.in_kind_description} onChange={set("in_kind_description")} /></div>}
      <div className="sm:col-span-3"><label className="label" htmlFor="dno">Notes</label><input id="dno" className={field} maxLength={1000} value={f.notes} onChange={set("notes")} /></div>
      <div className="flex flex-wrap gap-2 sm:col-span-3">
        <button ref={btn} className="btn btn-primary !py-1.5 text-sm" disabled={busy}>{initial ? "Save changes" : "Record donation"}</button>
        {dupe && <button type="button" className="btn btn-soft !py-1.5 text-sm" disabled={busy} onClick={() => submit(null, true)}>It's a separate gift: save anyway</button>}
        {onCancel && <button type="button" className="btn btn-ghost !py-1.5 text-sm" onClick={onCancel}>Cancel</button>}
      </div>
      {msg && <p role={msg.ok ? "status" : "alert"} className={`rounded-xl px-3 py-2 text-sm sm:col-span-3 ${msg.ok ? "bg-[#e3f1e8] text-sage" : "bg-[#fbeef3] text-danger"}`}>{msg.text}</p>}
      <p className="text-[0.7rem] text-muted sm:col-span-3">Only the details needed for acknowledgments are kept. SAM SPACE never decides whether a gift is tax-deductible.</p>
    </form>
  );
}

export function ImportDonations({ onDone }: { onDone: () => void }) {
  const { celebrate } = useButterflies();
  const [file, setFile] = useState<File | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [dupe, setDupe] = useState(false);
  const [busy, setBusy] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);
  async function send(allow = false) {
    if (!file) return;
    setBusy(true);
    setMsg(null);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("allow_duplicates", String(allow));
    try {
      const r = await api<{ imported: number }>("/api/donations/import", { method: "POST", body: fd });
      setMsg({ ok: true, text: `Imported ${r.imported} donation(s).` });
      celebrate("save", btn.current);
      setDupe(false);
      setFile(null);
      onDone();
    } catch (e) {
      const text = e instanceof Error ? e.message : "Import failed.";
      setDupe(text.includes("import again and confirm"));
      setMsg({ ok: false, text });
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-2">
      <input type="file" accept=".csv,text/csv" aria-label="Donation CSV file" className="field !py-1.5 text-sm" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setMsg(null); }} />
      <p className="text-[0.7rem] text-muted">Columns: donor_name, donation_date (YYYY-MM-DD), amount_usd; optional donor_email, contribution_type, payment_status,
        ack_status, restriction, method, campaign (an existing name), designation, in_kind_description, goods_services_value_usd, notes. Nothing is imported unless every row is valid.</p>
      <div className="flex flex-wrap gap-2">
        <button ref={btn} className="btn btn-primary !py-1.5 text-sm" disabled={!file || busy} onClick={() => send(false)}><FileUp size={13} aria-hidden="true" /> {busy ? "Importing…" : "Import CSV"}</button>
        {dupe && <button className="btn btn-soft !py-1.5 text-sm" disabled={busy} onClick={() => send(true)}>They're separate gifts: import anyway</button>}
      </div>
      {msg && <p role={msg.ok ? "status" : "alert"} className={`rounded-xl px-3 py-2 text-sm ${msg.ok ? "bg-[#e3f1e8] text-sage" : "bg-[#fbeef3] text-danger"}`}>{msg.text}</p>}
    </div>
  );
}

// ── Table ───────────────────────────────────────────────────────────────────────

export function DonationTable({ rows, campaigns, onChange }: { rows: DonationRow[]; campaigns: CampaignRow[]; onChange: () => void }) {
  const { can } = useAuth();
  const navigate = useNavigate();
  const [editing, setEditing] = useState<number | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  async function setAck(d: DonationRow, status: string) {
    setBusy(d.id);
    try { await api(`/api/donations/${d.id}/acknowledgment`, { json: { status } }); onChange(); } finally { setBusy(null); }
  }
  async function draft(d: DonationRow) {
    setBusy(d.id);
    setErr(null);
    try {
      const r = await api<{ run: RunSummary }>("/api/runs", { json: { request: `Draft a thank-you for ${d.donation_id}`, intent: "donations_review", donation_ids: [d.id], drafts_only: true } });
      navigate(`/activity/runs/${r.run.id}`);
    } catch (e) { setErr(e instanceof Error ? e.message : "Could not start."); setBusy(null); }
  }
  if (!rows.length) return <EmptyState title="No donations match">Clear a filter or record a donation.</EmptyState>;
  return (
    <div className="-mx-2 overflow-x-auto">
      <table className="w-full min-w-[1000px] text-left text-sm">
        <caption className="sr-only">Donation records</caption>
        <thead><tr className="text-xs uppercase tracking-wider text-muted">
          {["Gift", "Donor", "Date", "Amount", "Type · campaign", "Status", "Acknowledgment", "For review", ""].map((h) => <th key={h} className="px-2 py-2 font-semibold">{h}</th>)}</tr></thead>
        <tbody>{rows.map((d) => (
          editing === d.id ? (
            <tr key={d.id} className="border-t border-lavender/25 bg-lilac/30"><td colSpan={9} className="px-2 py-3">
              <p className="mb-2 text-sm font-semibold text-plum">Editing {d.donation_id} · {d.donor_name}</p>
              <DonationForm campaigns={campaigns} initial={d} onDone={() => { setEditing(null); onChange(); }} onCancel={() => setEditing(null)} />
            </td></tr>
          ) : (
            <tr key={d.id} className="border-t border-lavender/25 align-top">
              <td className="px-2 py-2.5 text-xs text-muted">{d.donation_id}{d.is_demo && <span className="block"><DemoBadge label="Fictional" /></span>}</td>
              <td className="whitespace-nowrap px-2 py-2.5"><b className="text-plum">{d.donor_name}</b><span className="block text-xs text-muted">{d.donor_id}{d.has_email ? " · email on file" : ""}</span></td>
              <td className="whitespace-nowrap px-2 py-2.5 text-muted">{formatDate(d.received_on)}</td>
              <td className="px-2 py-2.5 tabular-nums">{d.contribution_type === "in_kind" ? <span className="text-xs">{d.in_kind_description || "In-kind"}<span className="block text-muted">no value assigned</span></span> : money(d.amount_usd)}
                {d.goods_services_value_usd ? <span className="block text-xs text-muted">received goods ≈ {money(d.goods_services_value_usd)}</span> : null}</td>
              <td className="px-2 py-2.5 text-xs">{TYPE_LABEL[d.contribution_type] ?? d.contribution_type}<span className="block text-muted">{d.campaign ?? "No campaign"}</span>
                <span className="block text-muted">{d.restriction ? RESTRICTION_LABEL[d.restriction] : "Restriction not documented"}</span></td>
              <td className="px-2 py-2.5 text-xs"><span className={d.payment_status === "received" ? "text-sage" : "text-amber"}>{PAYMENT_LABEL[d.payment_status]}</span></td>
              <td className="px-2 py-2.5 text-xs">
                {can("manage_donations") ? (
                  <select aria-label={`Acknowledgment status for ${d.donation_id}`} className="field !w-36 !py-1 text-xs" value={d.ack_status} disabled={busy === d.id}
                    onChange={(e) => setAck(d, e.target.value)}>{Object.entries(ACK_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
                ) : ACK_LABEL[d.ack_status]}
              </td>
              <td className="min-w-[260px] px-2 py-2.5">{d.flags.length === 0 ? <span className="text-xs text-muted">—</span> : (
                <ul className="space-y-1">{d.flags.map((f) => <li key={f.code} className={`rounded-lg px-2 py-0.5 text-[0.7rem] ${SEV[f.severity]}`}>{f.text}</li>)}</ul>)}</td>
              <td className="px-2 py-2.5">{can("manage_donations") && (
                <div className="flex flex-col gap-1">
                  <button className="btn btn-ghost !px-2 !py-1 text-xs" onClick={() => setEditing(d.id)}><Pencil size={12} aria-hidden="true" /> Edit</button>
                  {d.payment_status === "received" && <button className="btn btn-soft !px-2 !py-1 text-xs" disabled={busy === d.id} onClick={() => draft(d)}><Sparkles size={12} aria-hidden="true" /> Draft thank-you</button>}
                </div>)}</td>
            </tr>
          )))}</tbody>
      </table>
      {err && <p role="alert" className="mt-2 text-sm text-danger">{err}</p>}
    </div>
  );
}

// ── Compliance ──────────────────────────────────────────────────────────────────

function RefLine({ r }: { r: ComplianceRef }) {
  return (
    <li className="text-xs text-muted">
      <a href={r.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-semibold text-royal hover:underline">{r.title}<ExternalLink size={11} aria-hidden="true" /></a>
      {" "}· {r.authority} · <b className="text-plum">{r.jurisdiction}</b> · {r.source_updated}; checked {r.checked_on}{r.stale && <span className="text-danger"> · re-check this source</span>}
    </li>
  );
}

export function ComplianceArea() {
  const { data, loading } = useApi<{ items: ComplianceItem[]; references: ComplianceRef[]; disclaimer: string }>("/api/compliance");
  const [limit, setLimit] = useState(3);
  return (
    <Card title="Compliance review" icon={<Scale size={16} aria-hidden="true" />}>
      <p className="mb-3 flex items-start gap-2 rounded-xl bg-lilac/60 px-3 py-2 text-xs text-plum"><ShieldCheck size={14} className="mt-0.5 shrink-0" aria-hidden="true" />{data?.disclaimer ?? "Loading…"}</p>
      {loading && <LoadingState rows={3} />}
      {data && (
        <><ul className="space-y-3">{data.items.slice(0, limit).map((i) => {
          const [label, cls] = KIND[i.kind];
          return (
            <li key={i.key} className="rounded-2xl border border-lavender/35 bg-white/85 p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <p className="font-semibold text-plum">{i.title}</p>
                <span className="flex gap-1"><span className={`rounded-full px-2 py-0.5 text-[0.66rem] font-semibold ${cls}`}>{label}</span>
                  {i.professional && <span className="rounded-full bg-ivory px-2 py-0.5 text-[0.66rem] font-semibold capitalize text-plum ring-1 ring-lavender/40">Ask your {i.professional}</span>}</span>
              </div>
              <p className="mt-1 text-sm text-ink/85">{i.detail}</p>
              {i.references.length > 0 ? <ul className="mt-1.5 space-y-0.5">{i.references.map((r) => <RefLine key={r.id} r={r} />)}</ul>
                : i.kind === "needs_professional_review"
                  ? <p className="mt-1 text-xs text-amber">No authoritative source is on file for this question, so it is routed to a professional.</p>
                  : <p className="mt-1 text-xs text-muted">Good recordkeeping practice; no specific rule is cited.</p>}
            </li>
          );
        })}</ul>
        <ShowMore shown={Math.min(limit, data.items.length)} total={data.items.length} onMore={() => setLimit(data.items.length)} /></>
      )}
    </Card>
  );
}

export function AckGuide() {
  return (
    <Card title="Two kinds of drafts" icon={<BookOpenCheck size={16} aria-hidden="true" />}>
      <ul className="space-y-2 text-sm">
        <li><b className="text-plum">General thank-you letter.</b> Warm and personal, written from a template with the donor's verified details filled in on the server. It is not a tax acknowledgment and never mentions deductibility.</li>
        <li><b className="text-plum">Contribution acknowledgment (for accountant review).</b> For gifts of $250 or more, in-kind gifts, and gifts where the donor received something. Built in code from the record, with the IRS source cited and every uncertain statement marked [confirm].</li>
      </ul>
      <p className="mt-2 text-xs text-muted">Both are drafts: edit, save, copy, or archive them. There is no send button. Mark the acknowledgment “Completed” only after a person has sent it.</p>
    </Card>
  );
}

export function ExportButton() {
  return <a className="btn btn-soft !py-1.5 text-sm" href="/api/donations/export.csv"><Download size={13} aria-hidden="true" /> Export CSV</a>;
}

export function FilterBar({ value, onChange, campaigns }: { value: Record<string, string>; onChange: (v: Record<string, string>) => void; campaigns: CampaignRow[] }) {
  const set = (k: string) => (e: { target: { value: string } }) => onChange({ ...value, [k]: e.target.value });
  const f = "field !w-auto !py-1.5 text-sm";
  const active = Object.values(value).some(Boolean);
  return (
    <div className="flex flex-wrap items-center gap-2" role="search">
      <span className="relative"><Search size={14} className="pointer-events-none absolute left-2.5 top-2.5 text-muted" aria-hidden="true" />
        <input aria-label="Search donor, ID, campaign, or notes" placeholder="Search donor, ID, campaign…" className={`${f} !pl-8`} value={value.search ?? ""} onChange={set("search")} /></span>
      <select aria-label="Campaign" className={f} value={value.campaign_id ?? ""} onChange={set("campaign_id")}><option value="">All campaigns</option>{campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
      <select aria-label="Payment status" className={f} value={value.payment_status ?? ""} onChange={set("payment_status")}><option value="">Any status</option>{Object.entries(PAYMENT_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
      <select aria-label="Acknowledgment" className={f} value={value.ack_status ?? ""} onChange={set("ack_status")}><option value="">Any acknowledgment</option>{Object.entries(ACK_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
      <select aria-label="Contribution type" className={f} value={value.contribution_type ?? ""} onChange={set("contribution_type")}><option value="">Any type</option>{Object.entries(TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
      <input aria-label="From date" type="date" className={f} value={value.date_from ?? ""} onChange={set("date_from")} />
      <input aria-label="To date" type="date" className={f} value={value.date_to ?? ""} onChange={set("date_to")} />
      <label className="inline-flex items-center gap-1.5 text-sm text-plum"><input type="checkbox" checked={value.flagged === "true"} onChange={(e) => onChange({ ...value, flagged: e.target.checked ? "true" : "" })} /> Needs attention</label>
      {active && <button className="btn btn-ghost !py-1.5 text-sm" onClick={() => onChange({})}><X size={13} aria-hidden="true" /> Clear</button>}
    </div>
  );
}

export function AddDonationCard({ campaigns, onDone }: { campaigns: CampaignRow[]; onDone: () => void }) {
  const [open, setOpen] = useState<"add" | "import" | null>(null);
  return (
    <Card title="Add or import donations" icon={<PlusCircle size={16} aria-hidden="true" />}>
      <div className="mb-3 flex flex-wrap gap-2">
        <button className={`btn !py-1.5 text-sm ${open === "add" ? "btn-primary" : "btn-soft"}`} onClick={() => setOpen(open === "add" ? null : "add")}>Record a donation</button>
        <button className={`btn !py-1.5 text-sm ${open === "import" ? "btn-primary" : "btn-soft"}`} onClick={() => setOpen(open === "import" ? null : "import")}>Import a CSV</button>
        <ExportButton />
      </div>
      {open === "add" && <DonationForm campaigns={campaigns} onDone={onDone} />}
      {open === "import" && <ImportDonations onDone={onDone} />}
      {!open && <p className="text-xs text-muted">Exports include donor IDs and gift details but never email addresses, and every export is logged.</p>}
    </Card>
  );
}
