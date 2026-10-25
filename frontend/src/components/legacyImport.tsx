import { FileSpreadsheet, FileText, Image as ImageIcon, MessageSquareText, NotebookPen, Upload } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { FieldSource, LegacyDocument, LegacyImport } from "../api/types";

/** Our Legacy: the three ways to add history (files, a description, or by hand) and the provenance badges. */

export const ORIGIN: Record<string, { label: string; cls: string }> = {
  source_fact: { label: "From the source", cls: "bg-[#e3f1e8] text-sage" },
  ai_interpretation: { label: "AI interpretation", cls: "bg-lilac text-royal" },
  board_choice: { label: "Board's choice between sources", cls: "bg-[#fbf1e3] text-amber" },
  board_edited: { label: "Edited by the board", cls: "bg-ivory text-plum ring-1 ring-lavender/50" },
  board_entered: { label: "Entered by the board", cls: "bg-ivory text-plum ring-1 ring-lavender/50" },
  missing: { label: "Not in the sources", cls: "bg-white text-muted ring-1 ring-lavender/40" },
};

export function OriginBadge({ origin }: { origin: string }) {
  const o = ORIGIN[origin] ?? ORIGIN.missing;
  return <span className={`inline-flex shrink-0 rounded-full px-2 py-0.5 text-[0.68rem] font-semibold ${o.cls}`}>{o.label}</span>;
}

export function Provenance({ source }: { source?: FieldSource }) {
  if (!source) return null;
  return (
    <span className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[0.7rem] text-muted">
      <OriginBadge origin={source.origin} />
      {source.sources && source.sources.length > 0 && <span>{source.sources.join(", ")}</span>}
      {source.quotes && source.quotes[0] && <span className="italic">“{source.quotes[0].slice(0, 120)}”</span>}
    </span>
  );
}

const TYPE_ICON: Record<string, ReactNode> = {
  pdf: <FileText size={14} aria-hidden="true" />, csv: <FileSpreadsheet size={14} aria-hidden="true" />,
  xlsx: <FileSpreadsheet size={14} aria-hidden="true" />, text: <NotebookPen size={14} aria-hidden="true" />,
  image: <ImageIcon size={14} aria-hidden="true" />,
};

export function DocumentList({ docs, showOpen = true }: { docs: LegacyDocument[]; showOpen?: boolean }) {
  if (!docs.length) return <p className="text-sm text-muted">No source files.</p>;
  return (
    <ul className="space-y-2">
      {docs.map((d) => (
        <li key={d.id} className="rounded-xl bg-ivory/80 px-3 py-2 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-royal">{TYPE_ICON[d.file_type]}</span>
            <span className="font-medium text-plum">{d.filename}</span>
            <span className="text-xs text-muted">{d.file_type.toUpperCase()} · {d.size_bytes < 1024 ? `${d.size_bytes} bytes` : `${(d.size_bytes / 1024).toFixed(0)} KB`} · {d.status === "photo" ? "photo (not read)" : d.status}</span>
            {showOpen && (d.can_open ?? true) && <a className="ml-auto text-xs text-royal underline" href={d.url} target="_blank" rel="noreferrer">Open original</a>}
            {showOpen && d.can_open === false && <span className="ml-auto text-xs text-muted">Original visible to the treasurer, the chair, or the uploader</span>}
          </div>
          {d.notes.length > 0 && <ul className="mt-1 list-disc pl-5 text-xs text-muted">{d.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>}
        </li>
      ))}
    </ul>
  );
}

const ACCEPT = ".pdf,.csv,.xlsx,.jpg,.jpeg,.png,.txt,.md";

function useCreateImport(targetEventId?: number) {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function create(form: FormData) {
    setBusy(true);
    setError(null);
    if (targetEventId) form.append("target_event_id", String(targetEventId));
    try {
      const res = await api<{ import: LegacyImport }>("/api/legacy/imports", { method: "POST", body: form });
      navigate(`/legacy/imports/${res.import.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the import.");
    } finally {
      setBusy(false);
    }
  }
  return { create, error, busy };
}

export function UploadForm({ targetEventId }: { targetEventId?: number }) {
  const [files, setFiles] = useState<File[]>([]);
  const [note, setNote] = useState("");
  const { create, error, busy } = useCreateImport(targetEventId);
  function submit(e: FormEvent) {
    e.preventDefault();
    const form = new FormData();
    form.append("method", "upload");
    if (note.trim()) form.append("description", note.trim());
    files.forEach((f) => form.append("files", f));
    create(form);
  }
  return (
    <form onSubmit={submit} className="space-y-3">
      <label className="flex cursor-pointer flex-col items-center gap-2 rounded-2xl border border-dashed border-lavender bg-ivory/60 px-4 py-6 text-center text-sm text-muted hover:bg-lilac/30">
        <Upload size={20} className="text-royal" aria-hidden="true" />
        <span><b className="text-plum">Choose files</b> for one event: PDF reports, CSV or XLSX spreadsheets, JPG/PNG photos, .txt/.md notes</span>
        <span className="text-xs">Up to 8 files · PDFs 10 MB, spreadsheets 5 MB, photos 5 MB. Checked by their contents, kept privately.</span>
        <input type="file" multiple accept={ACCEPT} className="sr-only" onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
      </label>
      {files.length > 0 && <ul className="text-sm text-plum">{files.map((f) => <li key={f.name}>• {f.name} <span className="text-xs text-muted">({(f.size / 1024).toFixed(0)} KB)</span></li>)}</ul>}
      <div>
        <label className="label" htmlFor="up-note">Anything to add? (optional)</label>
        <textarea id="up-note" rows={2} className="field" value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. These are the recap and budget from our spring raffle." />
      </div>
      <p className="text-xs text-muted">The Event Intelligence agent reads the text and proposes details with the exact words they come from. Photos are kept with the event but never read for numbers. Nothing is saved until you review and approve.</p>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      <div className="flex justify-end"><button className="btn btn-primary" disabled={busy || files.length === 0}>{busy ? "Uploading…" : "Upload and extract"}</button></div>
    </form>
  );
}

export function TellUsForm({ targetEventId }: { targetEventId?: number }) {
  const [text, setText] = useState("");
  const { create, error, busy } = useCreateImport(targetEventId);
  function submit(e: FormEvent) {
    e.preventDefault();
    const form = new FormData();
    form.append("method", "conversation");
    form.append("description", text.trim());
    create(form);
  }
  return (
    <form onSubmit={submit} className="space-y-3">
      <label className="label" htmlFor="tell">Describe the event in your own words</label>
      <textarea id="tell" rows={5} className="field" value={text} onChange={(e) => setText(e.target.value)}
        placeholder="We hosted a fundraiser in Garden City. Attendance was strong, guests especially enjoyed the raffle, and we had challenges coordinating volunteers." />
      <p className="text-xs text-muted">Mention whatever you remember: name, date, place, how much was raised, what worked, what didn't. Anything you don't mention stays blank; nothing is invented. You'll see a preview to edit before anything is saved.</p>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      <div className="flex justify-end"><button className="btn btn-primary" disabled={busy || text.trim().length < 20}>{busy ? "Reading…" : "Show me the preview"}</button></div>
    </form>
  );
}

export function AddToLegacy({ manual, targetEventId }: { manual?: ReactNode; targetEventId?: number }) {
  const tabs = [
    { key: "upload", label: "Upload files", icon: <Upload size={14} aria-hidden="true" /> },
    { key: "tell", label: "Tell us about an event", icon: <MessageSquareText size={14} aria-hidden="true" /> },
    ...(manual ? [{ key: "manual", label: "Enter details by hand", icon: <NotebookPen size={14} aria-hidden="true" /> }] : []),
  ];
  const [tab, setTab] = useState(tabs[0].key);
  return (
    <div>
      <div role="tablist" className="mb-4 flex flex-wrap gap-1.5">
        {tabs.map((t) => (
          <button key={t.key} role="tab" aria-selected={tab === t.key} type="button" onClick={() => setTab(t.key)}
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-semibold ${tab === t.key ? "bg-plum text-white" : "bg-lilac/60 text-plum hover:bg-lilac"}`}>
            {t.icon}{t.label}
          </button>
        ))}
      </div>
      {tab === "upload" && <UploadForm targetEventId={targetEventId} />}
      {tab === "tell" && <TellUsForm targetEventId={targetEventId} />}
      {tab === "manual" && manual}
      <p className="mt-4 text-xs text-muted">Board reflections are added on each event's page, one per board member, in their own words.</p>
    </div>
  );
}
