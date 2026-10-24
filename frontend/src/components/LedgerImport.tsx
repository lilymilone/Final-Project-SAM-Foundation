import { FileUp } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import { Card } from "./ui";

/** Validated CSV import. The file is read in the browser and sent as text; the server checks every row. */
export function LedgerImport({ onImported }: { onImported: () => void }) {
  const [text, setText] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [replace, setReplace] = useState(true);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const rows = text ? Math.max(0, text.trim().split(/\r?\n/).length - 1) : 0;

  async function pick(file: File | undefined) {
    setMsg(null);
    if (!file) return;
    if (file.size > 200_000) {
      setMsg({ ok: false, text: "That file is larger than 200 KB." });
      return;
    }
    setName(file.name);
    setText(await file.text());
  }

  async function upload() {
    if (!text) return;
    setBusy(true);
    try {
      const r = await api<{ imported: number; replaced_demo_rows: number }>("/api/finance/import", { json: { csv_text: text, replace_demo: replace } });
      setMsg({ ok: true, text: `Imported ${r.imported} rows${r.replaced_demo_rows ? ` and removed ${r.replaced_demo_rows} demo rows` : ""}.` });
      setText(null);
      onImported();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "Import failed." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Import financial records" icon={<FileUp size={16} aria-hidden="true" />}>
      <p className="text-sm text-muted">CSV with columns <code className="text-plum">period, kind, category, amount_usd</code>. Kind is income, expense, or reserve, and period looks like 2026-09. Every row is validated, and nothing is saved unless the whole file is valid.</p>
      <label className="btn btn-soft mt-3 cursor-pointer text-sm">
        <FileUp size={14} aria-hidden="true" /> {name || "Choose a CSV file"}
        <input type="file" accept=".csv,text/csv" className="sr-only" onChange={(e) => pick(e.target.files?.[0])} />
      </label>
      {text && (
        <div className="mt-3 space-y-2 text-sm">
          <p className="text-plum">{rows} data row{rows === 1 ? "" : "s"} ready to check.</p>
          <label className="flex items-center gap-2"><input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} /> Replace the synthetic demo books</label>
          <button className="btn btn-primary text-sm" onClick={upload} disabled={busy}>{busy ? "Checking…" : "Validate and import"}</button>
        </div>
      )}
      {msg && <p role={msg.ok ? "status" : "alert"} className={`mt-3 rounded-xl px-3 py-2 text-sm ${msg.ok ? "bg-[#e3f1e8] text-sage" : "bg-[#fbeef3] text-danger"}`}>{msg.text}</p>}
      <p className="mt-3 text-xs text-muted">Try it with <code>docs/sample_ledger.csv</code> from the repository.</p>
    </Card>
  );
}
