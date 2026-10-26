import { BarChart3, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { SERIES_COLORS } from "./charts";

/** Shared pieces for Analytics & Safety → Impact & Evaluation. */

export function AnalyticsTabs() {
  const cls = ({ isActive }: { isActive: boolean }) =>
    `inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-semibold ${isActive ? "bg-plum text-white" : "bg-lilac/60 text-plum hover:bg-lilac"}`;
  return (
    <nav aria-label="Analytics & Safety sections" className="mb-5 flex flex-wrap gap-2">
      <NavLink to="/safety" end className={cls}><ShieldCheck size={14} aria-hidden="true" /> Analytics & Safety</NavLink>
      <NavLink to="/safety/impact" className={cls}><BarChart3 size={14} aria-hidden="true" /> Impact & Evaluation</NavLink>
    </nav>
  );
}

const BASIS: Record<string, string> = {
  observed: "bg-[#e3f1e8] text-sage", calculated: "bg-lilac text-royal", extrapolated: "bg-[#fbf1e3] text-amber",
  feedback: "bg-blush/70 text-plum", logs: "bg-ivory text-plum ring-1 ring-lavender/50", assumption: "bg-[#fbf1e3] text-amber",
};

export function BasisTag({ kind, children }: { kind: keyof typeof BASIS; children?: ReactNode }) {
  return <span className={`inline-flex rounded-full px-2 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide ${BASIS[kind]}`}>{children ?? kind}</span>;
}

export function Quiet({ children }: { children: ReactNode }) {
  return <p className="rounded-xl bg-ivory/80 px-3 py-2.5 text-sm text-muted">{children}</p>;
}

/** Two labeled horizontal bars (manual vs SAM SPACE), rose vs plum (validated pair; rose is below 3:1 contrast, so
 * every bar has its label and value printed: color never carries meaning alone). */
export function CompareBars({ title, manual, assisted, unit, note }: { title: string; manual: number | null; assisted: number | null; unit: string; note?: string }) {
  const max = Math.max(1, manual ?? 0, assisted ?? 0);
  const row = (label: string, value: number | null, color: string) => (
    <div className="grid grid-cols-[7.5rem_minmax(0,1fr)_5rem] items-center gap-2 text-sm">
      <span className="text-muted">{label}</span>
      <span className="h-3 rounded-full bg-lilac/40">
        {value != null && <span className="block h-3 rounded-full" style={{ width: `${Math.max(2, (100 * value) / max)}%`, background: color }} />}
      </span>
      <span className="text-right font-semibold tabular-nums text-plum">{value == null ? "—" : `${value.toLocaleString()}${unit}`}</span>
    </div>
  );
  return (
    <figure className="rounded-2xl bg-white/80 p-3.5 ring-1 ring-lavender/30">
      <figcaption className="mb-2 text-sm font-semibold text-plum">{title}</figcaption>
      <div className="space-y-1.5">
        {row("Usual way", manual, SERIES_COLORS[1])}
        {row("With SAM SPACE", assisted, SERIES_COLORS[0])}
      </div>
      {note && <p className="mt-1.5 text-[0.7rem] text-muted">{note}</p>}
    </figure>
  );
}

export const fmtMin = (v: number | null | undefined) => (v == null ? "—" : `${v.toLocaleString(undefined, { maximumFractionDigits: 1 })} min`);
export const ANSWER_LABELS: Record<string, string> = { yes: "Yes", no: "No", unsure: "Unsure", maybe: "Maybe", needs_editing: "Needs editing",
  somewhat: "Somewhat", not_applicable: "Not applicable", usable: "Usable", not_usable: "Not usable" };
