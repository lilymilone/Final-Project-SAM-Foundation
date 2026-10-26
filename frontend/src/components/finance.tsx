import {
  AlertTriangle, Check, ChevronDown, FileSpreadsheet, FileText, FileUp, Info, PencilLine, PlusCircle, ShieldAlert, Sparkles, X,
} from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { ExtractedFigureRow, FinanceDocument, FinanceMetric, RunSummary } from "../api/types";
import { formatDate, useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { useButterflies } from "../butterflies/ButterflyProvider";
import { Card, DemoBadge, EmptyState, LoadingState } from "./ui";

const STATUS: Record<FinanceMetric["status"], [string, string]> = {
  recorded: ["Recorded", "bg-[#e3f1e8] text-sage"], calculated: ["Calculated", "bg-lilac text-royal"],
  partial: ["Partly documented", "bg-[#fbf1e3] text-amber"], not_documented: ["Not documented", "bg-[#f4eef6] text-muted"],
};
export const KIND_LABEL: Record<string, string> = {
  income: "Revenue", expense: "Expense", reserve: "Reserve balance", cash: "Cash balance", budget_income: "Budgeted revenue",
  budget_expense: "Budgeted expense",
};
const RESTRICTION_LABEL: Record<string, string> = {
  unrestricted: "Unrestricted", temporarily_restricted: "Restricted (purpose or time)", permanently_restricted: "Permanently restricted",
};

export function MetricCard({ m }: { m: FinanceMetric }) {
  const [label, cls] = STATUS[m.status];
  const muted = m.status === "not_documented";
  return (
    <div className="flex flex-col rounded-2xl border border-lavender/35 bg-white/85 p-4">
      <div className="flex flex-wrap items-start justify-between gap-x-2 gap-y-1">
        <p className="text-xs font-semibold text-muted">{m.label}</p>
        <span className={`shrink-0 rounded-full px-1.5 py-px text-[0.62rem] font-semibold ${cls}`}>{label}</span>
      </div>
      <p className={`mt-1 font-display font-semibold leading-tight ${muted ? "text-lg text-muted" : m.display.length > 16 ? "text-xl text-plum" : "text-[1.7rem] text-plum"}`}>{m.display}</p>
      <p className="mt-1 text-[0.78rem] leading-snug text-ink/80">{m.explanation}</p>
      {m.basis && (
        <details className="group mt-auto pt-2 text-[0.7rem] text-muted">
          <summary className="flex cursor-pointer list-none items-center gap-1 font-semibold text-royal"><Info size={11} aria-hidden="true" />How it's computed
            <ChevronDown size={11} className="transition group-open:rotate-180" aria-hidden="true" /></summary>
          <p className="mt-1">{m.basis}</p>
        </details>
      )}
    </div>
  );
}

// ── Upload ──────────────────────────────────────────────────────────────────────

export function UploadPanel({ docTypes, onUploaded }: { docTypes: Record<string, string>; onUploaded: () => void }) {
  const { celebrate } = useButterflies();
  const uploadBtn = useRef<HTMLButtonElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [docType, setDocType] = useState("income_statement");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [dupe, setDupe] = useState(false);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  async function send(allowDuplicates = false) {
    if (!file) return;
    setBusy(true);
    setMsg(null);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("doc_type", file.name.toLowerCase().endsWith(".csv") && docType === "income_statement" ? "ledger" : docType);
    fd.append("allow_duplicate_rows", String(allowDuplicates));
    try {
      const r = await api<{ document: FinanceDocument }>("/api/finance/documents", { method: "POST", body: fd });
      const d = r.document;
      setMsg({ ok: d.status !== "unreadable", text: d.file_type === "csv" ? `Imported: ${d.notes.join(" ")}`
        : d.status === "unreadable" ? `Saved, but no readable text was found. ${d.notes.join(" ")}` : `Saved ${d.page_count} page(s). Next: organize its figures for review.` });
      if (d.status !== "unreadable") celebrate("save", uploadBtn.current);  // only when the document was saved and is usable
      setFile(null);
      setDupe(false);
      if (input.current) input.current.value = "";
      onUploaded();
    } catch (e) {
      const text = e instanceof Error ? e.message : "Upload failed.";
      setDupe(text.includes("upload again and confirm"));
      setMsg({ ok: false, text });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Upload financial documents" icon={<FileUp size={16} aria-hidden="true" />}>
      <p className="mb-3 text-xs text-muted">CSV (up to 2 MB) or PDF (up to 10 MB, 40 pages). CSVs are checked row by row in code. PDFs are read for text only;
        scripts or attachments inside them are never run, and scanned pages are flagged for manual entry.</p>
      <div className="space-y-2">
        <label className="label" htmlFor="fin-file">File</label>
        <input ref={input} id="fin-file" type="file" accept=".csv,.pdf,text/csv,application/pdf" className="field !py-1.5 text-sm"
          onChange={(e) => { setFile(e.target.files?.[0] ?? null); setMsg(null); setDupe(false); }} />
        <label className="label" htmlFor="fin-type">What is it?</label>
        <select id="fin-type" className="field" value={docType} onChange={(e) => setDocType(e.target.value)}>
          {Object.entries(docTypes).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <p className="text-[0.7rem] text-muted">CSV columns: period (YYYY-MM), kind (income, expense, reserve, cash, budget_income, budget_expense), category,
          amount_usd; optional restriction, purpose, description, period_months, period_label. Try <code>docs/sample_ledger.csv</code>.</p>
        <button ref={uploadBtn} className="btn btn-primary w-full" disabled={!file || busy} onClick={() => send(false)}>{busy ? "Uploading…" : "Upload"}</button>
        {dupe && <button className="btn btn-soft w-full" disabled={busy} onClick={() => send(true)}>These are separate entries: import anyway</button>}
        {msg && <p role={msg.ok ? "status" : "alert"} className={`rounded-xl px-3 py-2 text-sm ${msg.ok ? "bg-[#e3f1e8] text-sage" : "bg-[#fbeef3] text-danger"}`}>{msg.text}</p>}
      </div>
    </Card>
  );
}

// ── Documents and the review queue ─────────────────────────────────────────────────

const DOC_STATUS: Record<string, [string, string]> = {
  imported: ["Imported (parsed in code)", "bg-[#e3f1e8] text-sage"], ready_for_extraction: ["Ready to organize", "bg-lilac text-royal"],
  needs_review: ["Waiting for review", "bg-[#fbf1e3] text-amber"], reviewed: ["Reviewed", "bg-[#e3f1e8] text-sage"],
  unreadable: ["Needs manual entry", "bg-[#fbeef3] text-danger"],
};

function FigureRow({ f, onDone }: { f: ExtractedFigureRow; onDone: () => void }) {
  const { can } = useAuth();
  const [edit, setEdit] = useState(false);
  const [form, setForm] = useState({ kind: f.kind, category: f.category, amount_usd: f.amount_usd ?? "", period: f.period ?? "", restriction: f.restriction ?? "", purpose: f.purpose ?? "" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function review(action: "approve" | "reject") {
    setBusy(true);
    setErr(null);
    const body: Record<string, unknown> = { action };
    if (action === "approve" && edit) {
      Object.assign(body, { kind: form.kind, category: form.category, period: form.period || null, amount_usd: form.amount_usd === "" ? null : Number(form.amount_usd),
        restriction: form.restriction || null, purpose: form.purpose || null });
    }
    try {
      await api(`/api/finance/figures/${f.id}/review`, { json: body });
      onDone();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save.");
      setBusy(false);
    }
  }
  const tone = f.status === "approved" ? "bg-[#e3f1e8]/60" : f.status === "rejected" ? "bg-[#f4eef6]/60 opacity-70" : f.status === "reference" ? "bg-ivory" : "bg-white";
  return (
    <li className={`rounded-xl border border-lavender/30 px-3 py-2 text-sm ${tone}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold text-plum">{f.label}</p>
          <p className="text-xs text-muted">As printed: <b className="text-ink">{f.original_amount}</b> · page {f.page ?? "?"} · {KIND_LABEL[f.kind] ?? f.kind}
            {f.restriction ? ` · ${RESTRICTION_LABEL[f.restriction]}` : ""} · {f.period_label || f.period || "period not set"}</p>
          <p className={`text-xs font-semibold ${f.found_on_page ? "text-sage" : "text-danger"}`}>{f.found_on_page ? "✓ Amount found on the cited page" : "✗ Amount not found on the cited page"}</p>
          {(f.check_notes ?? []).map((n) => <p key={n} className="text-xs text-amber">{n}</p>)}
        </div>
        <span className="text-xs font-semibold uppercase tracking-wide text-muted">{f.status === "reference" ? "total (cross-check only)" : f.status}</span>
      </div>
      {f.status === "pending" && can("manage_financials") && (
        <div className="mt-2 space-y-2">
          {edit && (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              <select className="field !py-1 text-xs" aria-label="Kind" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                {Object.entries(KIND_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
              <input className="field !py-1 text-xs" aria-label="Category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
              <input className="field !py-1 text-xs" aria-label="Amount (USD)" type="number" min={0} step="0.01" value={form.amount_usd} onChange={(e) => setForm({ ...form, amount_usd: e.target.value })} />
              <input className="field !py-1 text-xs" aria-label="Reporting month (YYYY-MM)" placeholder="YYYY-MM" value={form.period} onChange={(e) => setForm({ ...form, period: e.target.value })} />
              <select className="field !py-1 text-xs" aria-label="Restriction" value={form.restriction} onChange={(e) => setForm({ ...form, restriction: e.target.value })}>
                <option value="">Restriction not documented</option>{Object.entries(RESTRICTION_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
              <select className="field !py-1 text-xs" aria-label="Purpose" value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })}>
                <option value="">Purpose not stated</option>{["program", "event", "fundraising", "operations"].map((p) => <option key={p} value={p}>{p}</option>)}</select>
            </div>
          )}
          <div className="flex flex-wrap gap-1.5">
            <button className="btn btn-primary !py-1 text-xs" disabled={busy} onClick={() => review("approve")}><Check size={12} aria-hidden="true" /> {edit ? "Save correction & approve" : "Approve into records"}</button>
            <button className="btn btn-soft !py-1 text-xs" disabled={busy} onClick={() => setEdit((v) => !v)}><PencilLine size={12} aria-hidden="true" /> {edit ? "Cancel correction" : "Correct"}</button>
            <button className="btn btn-ghost !py-1 text-xs" disabled={busy} onClick={() => review("reject")}><X size={12} aria-hidden="true" /> Reject</button>
          </div>
          {err && <p role="alert" className="text-xs text-danger">{err}</p>}
        </div>
      )}
    </li>
  );
}

function DocumentFigures({ doc, onChange }: { doc: FinanceDocument; onChange: () => void }) {
  const { data, loading, reload } = useApi<{ figures: ExtractedFigureRow[] }>(`/api/finance/documents/${doc.id}/figures`);
  if (loading && !data) return <LoadingState rows={2} />;
  const figures = data?.figures ?? [];
  if (!figures.length) return <p className="text-xs text-muted">No figures staged yet.</p>;
  const order = { pending: 0, reference: 1, approved: 2, rejected: 3 };
  return (
    <ul className="mt-2 space-y-1.5">{[...figures].sort((a, b) => order[a.status] - order[b.status]).map((f) =>
      <FigureRow key={`${f.id}-${f.status}`} f={f} onDone={() => { reload(); onChange(); }} />)}</ul>
  );
}

export function DocumentsPanel({ onChange }: { onChange: () => void }) {
  const { can } = useAuth();
  const navigate = useNavigate();
  const { data, loading, reload } = useApi<{ documents: FinanceDocument[]; doc_types: Record<string, string> }>("/api/finance/documents");
  const [open, setOpen] = useState<number | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  async function extract(d: FinanceDocument) {
    setBusy(d.id);
    setErr(null);
    try {
      const r = await api<{ run: RunSummary }>("/api/runs", { json: { request: `Organize the figures in ${d.filename} for board review`, intent: "document_extraction", document_id: d.id } });
      navigate(`/activity/runs/${r.run.id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not start.");
      setBusy(null);
    }
  }
  return (
    <>
      {can("manage_financials") && data && <UploadPanel docTypes={data.doc_types} onUploaded={() => { reload(); onChange(); }} />}
      <Card title="Documents and review queue" icon={<FileText size={16} aria-hidden="true" />}>
        <p className="mb-3 text-xs text-muted">Figures the AI organizes from a PDF are <b>not</b> accounting records. Each one waits here until a board member
          approves, corrects, or rejects it, and only then counts in the dashboard.</p>
        {loading && !data && <LoadingState rows={2} />}
        {data && (data.documents.length === 0 ? <EmptyState title="No documents yet">Upload a CSV ledger or a PDF statement to begin.</EmptyState> : (
          <ul className="space-y-2">{data.documents.map((d) => {
            const [label, cls] = DOC_STATUS[d.status] ?? [d.status, "bg-lilac text-plum"];
            const pending = d.figures.pending ?? 0;
            return (
              <li key={d.id} className="rounded-2xl border border-lavender/35 bg-white/85 p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="flex items-center gap-1.5 truncate font-semibold text-plum">{d.file_type === "csv" ? <FileSpreadsheet size={14} aria-hidden="true" /> : <FileText size={14} aria-hidden="true" />}{d.filename}</p>
                    <p className="text-xs text-muted">{d.doc_type_label} · {formatDate(d.created_at)}{d.page_count ? ` · ${d.page_count} page(s)` : ""}
                      {d.figures.records ? ` · ${d.figures.records} record(s)` : ""}{pending ? ` · ${pending} waiting` : ""}</p>
                  </div>
                  <span className={`rounded-full px-2 py-0.5 text-[0.68rem] font-semibold ${cls}`}>{label}</span>
                </div>
                {d.notes.map((n) => <p key={n} className="mt-1 flex gap-1 text-xs text-amber">{n.includes("run") || n.includes("JavaScript") ? <ShieldAlert size={12} className="mt-0.5 shrink-0" aria-hidden="true" /> : <AlertTriangle size={12} className="mt-0.5 shrink-0" aria-hidden="true" />}{n}</p>)}
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {d.file_type === "pdf" && d.status !== "unreadable" && can("manage_financials") && (
                    <button className="btn btn-soft !py-1 text-xs" disabled={busy === d.id} onClick={() => extract(d)}>
                      <Sparkles size={12} aria-hidden="true" /> {busy === d.id ? "Starting…" : d.status === "ready_for_extraction" ? "Organize figures with Financial Analysis" : "Re-organize figures"}</button>)}
                  {d.file_type === "pdf" && <button className="btn btn-ghost !py-1 text-xs" onClick={() => setOpen(open === d.id ? null : d.id)}>{open === d.id ? "Hide figures" : "Review figures"}</button>}
                  {d.run_id && <Link to={`/activity/runs/${d.run_id}`} className="btn btn-ghost !py-1 text-xs">Agent trace</Link>}
                </div>
                {open === d.id && <DocumentFigures doc={d} onChange={() => { reload(); onChange(); }} />}
              </li>
            );
          })}</ul>
        ))}
        {err && <p role="alert" className="mt-2 text-sm text-danger">{err}</p>}
      </Card>
    </>
  );
}

// ── Manual entry ──────────────────────────────────────────────────────────────────

export function ManualEntry({ onSaved }: { onSaved: () => void }) {
  const { celebrate } = useButterflies();
  const saveBtn = useRef<HTMLButtonElement>(null);
  const blank = { period: "", kind: "income", category: "", amount_usd: "", restriction: "", purpose: "", description: "" };
  const [form, setForm] = useState(blank);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [dupe, setDupe] = useState(false);
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent | null, confirm = false) {
    e?.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await api("/api/finance/records", { json: { ...form, amount_usd: Number(form.amount_usd), restriction: form.restriction || null,
        purpose: form.purpose || null, confirm_duplicate: confirm } });
      setMsg({ ok: true, text: "Saved to the financial records (entered by a board member)." });
      celebrate("save", saveBtn.current);
      setForm(blank);
      setDupe(false);
      onSaved();
    } catch (err) {
      const text = err instanceof Error ? err.message : "Could not save.";
      setDupe(text.includes("Confirm if this is a separate entry"));
      setMsg({ ok: false, text });
    } finally {
      setBusy(false);
    }
  }
  const set = (k: keyof typeof blank) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  return (
    <Card title="Enter a figure manually" icon={<PlusCircle size={16} aria-hidden="true" />}>
      <form onSubmit={(e) => submit(e)} className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <div><label className="label" htmlFor="m-period">Month (YYYY-MM)</label><input id="m-period" className="field" placeholder="2026-10" value={form.period} onChange={set("period")} required pattern="\d{4}-(0[1-9]|1[0-2])" /></div>
        <div><label className="label" htmlFor="m-kind">Kind</label><select id="m-kind" className="field" value={form.kind} onChange={set("kind")}>
          {Object.entries(KIND_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
        <div><label className="label" htmlFor="m-cat">Category</label><input id="m-cat" className="field" placeholder="Individual donations" value={form.category} onChange={set("category")} required maxLength={80} /></div>
        <div><label className="label" htmlFor="m-amt">Amount (USD)</label><input id="m-amt" className="field" type="number" min={0} step="0.01" value={form.amount_usd} onChange={set("amount_usd")} required /></div>
        <div><label className="label" htmlFor="m-res">Restriction</label><select id="m-res" className="field" value={form.restriction} onChange={set("restriction")}>
          <option value="">Not documented</option>{Object.entries(RESTRICTION_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
        <div><label className="label" htmlFor="m-pur">Purpose</label><select id="m-pur" className="field" value={form.purpose} onChange={set("purpose")}>
          <option value="">Not stated</option>{["program", "event", "fundraising", "operations"].map((p) => <option key={p} value={p}>{p}</option>)}</select></div>
        <div className="sm:col-span-2"><label className="label" htmlFor="m-desc">Source or note</label><input id="m-desc" className="field" placeholder="e.g. October bank statement" value={form.description} onChange={set("description")} maxLength={500} /></div>
        <div className="flex flex-wrap gap-2 sm:col-span-2">
          <button ref={saveBtn} className="btn btn-primary" disabled={busy}>Save figure</button>
          {dupe && <button type="button" className="btn btn-soft" disabled={busy} onClick={() => submit(null, true)}>It's a separate entry: save anyway</button>}
        </div>
        {msg && <p role={msg.ok ? "status" : "alert"} className={`rounded-xl px-3 py-2 text-sm sm:col-span-2 ${msg.ok ? "bg-[#e3f1e8] text-sage" : "bg-[#fbeef3] text-danger"}`}>{msg.text}</p>}
      </form>
    </Card>
  );
}

export function DemoNotice({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <p className="mb-5 flex items-center gap-2 rounded-2xl bg-blush/60 px-4 py-2.5 text-sm text-plum">
      <DemoBadge label="Synthetic demo books" /> These figures are labeled sample data, not the foundation's real finances. Upload authorized records to replace them.
    </p>
  );
}

// ── Recorded figures (view and correct) ─────────────────────────────────────────────

type RecordRow = { id: number; period: string; kind: string; category: string; amount_usd: number; restriction: string | null; purpose: string | null;
  description: string; verification: string; original_amount: string | null; document_id: number | null; source_page: number | null;
  source_row: number | null; is_demo: boolean; period_months: number; period_label: string | null; updated_at: string | null };
const VERIFY_LABEL: Record<string, string> = { parsed_csv: "Parsed from CSV", entered_by_board: "Entered by a board member", board_reviewed: "Reviewed from a document",
  edited_by_board: "Corrected by a board member", demo: "Fictional demo", manual: "Entered manually", upload: "Imported" };

function RecordEditor({ r, onDone }: { r: RecordRow; onDone: () => void }) {
  const [f, setF] = useState({ category: r.category, amount_usd: String(r.amount_usd), restriction: r.restriction ?? "not_documented", purpose: r.purpose ?? "not_stated" });
  const [err, setErr] = useState<string | null>(null);
  async function save() {
    setErr(null);
    try {
      await api(`/api/finance/records/${r.id}`, { method: "PUT", json: { category: f.category, amount_usd: Number(f.amount_usd), restriction: f.restriction, purpose: f.purpose } });
      onDone();
    } catch (e) { setErr(e instanceof Error ? e.message : "Could not save."); }
  }
  const c = "field !py-1 text-xs";
  return (
    <div className="mt-1 grid grid-cols-1 gap-1.5 sm:grid-cols-5">
      <input className={c} aria-label="Category" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} />
      <input className={c} aria-label="Amount" type="number" min={0} step="0.01" value={f.amount_usd} onChange={(e) => setF({ ...f, amount_usd: e.target.value })} />
      <select className={c} aria-label="Restriction" value={f.restriction} onChange={(e) => setF({ ...f, restriction: e.target.value })}>
        <option value="not_documented">Restriction not documented</option>{Object.entries(RESTRICTION_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
      <select className={c} aria-label="Purpose" value={f.purpose} onChange={(e) => setF({ ...f, purpose: e.target.value })}>
        <option value="not_stated">Purpose not stated</option>{["program", "event", "fundraising", "operations"].map((p) => <option key={p} value={p}>{p}</option>)}</select>
      <button className="btn btn-primary !py-1 text-xs" onClick={save}>Save</button>
      {err && <p role="alert" className="text-xs text-danger sm:col-span-5">{err}</p>}
    </div>
  );
}

export function RecordsPanel({ onChange }: { onChange: () => void }) {
  const { can } = useAuth();
  const { data, reload } = useApi<{ records: RecordRow[] }>("/api/finance/records");
  const [edit, setEdit] = useState<number | null>(null);
  return (
    <Card title="Recorded figures" icon={<FileSpreadsheet size={16} aria-hidden="true" />}>
      <details>
        <summary className="cursor-pointer text-sm font-semibold text-royal">Show {data?.records.length ?? "…"} records with their sources</summary>
        <ul className="mt-2 max-h-96 space-y-1 overflow-auto pr-1 text-xs">{(data?.records ?? []).map((r) => (
          <li key={r.id} className="rounded-lg bg-ivory/70 px-2 py-1.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span><b className="text-plum">{r.period}</b> · {KIND_LABEL[r.kind] ?? r.kind} · {r.category}{r.period_months > 1 ? ` · ${r.period_label ?? `${r.period_months} months`}` : ""}</span>
              <span className="tabular-nums"><b>${r.amount_usd.toLocaleString("en-US")}</b>{r.original_amount && r.original_amount !== String(r.amount_usd) ? <span className="text-muted"> (as written: {r.original_amount})</span> : null}</span>
            </div>
            <p className="text-muted">{VERIFY_LABEL[r.verification] ?? r.verification}{r.document_id ? ` · document #${r.document_id}` : ""}{r.source_page ? ` p.${r.source_page}` : ""}{r.source_row ? ` row ${r.source_row}` : ""}
              {r.restriction ? ` · ${RESTRICTION_LABEL[r.restriction]}` : r.kind === "income" ? " · restriction not documented" : ""}{r.updated_at ? " · edited" : ""}
              {can("manage_financials") && <button className="ml-2 font-semibold text-royal hover:underline" onClick={() => setEdit(edit === r.id ? null : r.id)}>{edit === r.id ? "Cancel" : "Correct"}</button>}</p>
            {edit === r.id && <RecordEditor r={r} onDone={() => { setEdit(null); reload(); onChange(); }} />}
          </li>))}</ul>
      </details>
    </Card>
  );
}
