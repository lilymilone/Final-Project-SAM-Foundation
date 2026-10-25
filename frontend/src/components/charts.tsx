import { Table2 } from "lucide-react";
import { useId, useRef, useState, type FocusEvent, type PointerEvent } from "react";

/**
 * Small, accessible SVG charts in the SAM SPACE palette.
 * Categorical order is fixed (validated for color-vision deficiency with the dataviz validator):
 * plum #70409B, rose #D58AB8, blue #3F72B8. Rose is below 3:1 contrast on white, so every chart
 * has a legend, a hover/focus tooltip, and a table view; color never carries meaning alone.
 */
export const SERIES_COLORS = ["#70409B", "#D58AB8", "#3F72B8"] as const;

export type Series = { key: string; label: string; color: string };
type Row = { label: string; values: Record<string, number> };

const money = (n: number) => `${n < 0 ? "−" : ""}$${Math.abs(n).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
const short = (n: number) => (Math.abs(n) >= 1000 ? `$${+(n / 1000).toFixed(1)}k` : `$${n}`);

/** Round tick step (1, 2, 2.5, 5 × 10^n) so axis labels read cleanly: $0, $2k, $4k, $6k. */
function niceTicks(maxValue: number, count = 4): number[] {
  const raw = Math.max(1, maxValue) / count;
  const p = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * p).find((m) => m >= raw) ?? raw;
  const top = Math.ceil(Math.max(1, maxValue) / step) * step;
  return Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step);
}

function Legend({ series }: { series: Series[] }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted" aria-hidden="true">
      {series.map((s) => <span key={s.key} className="inline-flex items-center gap-1.5"><span className="h-2.5 w-3.5 rounded-[3px]" style={{ background: s.color }} />{s.label}</span>)}
    </div>
  );
}

function DataTable({ caption, series, rows, extra }: { caption: string; series: Series[]; rows: Row[]; extra?: { label: string; values: string[] } }) {
  return (
    <table className="mt-3 w-full text-sm">
      <caption className="sr-only">{caption}</caption>
      <thead><tr className="text-left text-xs text-muted"><th className="py-1 font-semibold">Period</th>
        {series.map((s) => <th key={s.key} className="py-1 text-right font-semibold">{s.label}</th>)}
        {extra && <th className="py-1 text-right font-semibold">{extra.label}</th>}</tr></thead>
      <tbody>{rows.map((r, i) => (
        <tr key={r.label} className="border-t border-lavender/30"><td className="py-1 text-plum">{r.label}</td>
          {series.map((s) => <td key={s.key} className="py-1 text-right tabular-nums">{money(r.values[s.key] ?? 0)}</td>)}
          {extra && <td className="py-1 text-right tabular-nums">{extra.values[i]}</td>}</tr>))}</tbody>
    </table>
  );
}

/** Grouped (side-by-side) or stacked bars over periods. One y-axis, recessive grid, rounded data ends. */
export function BarChart({ rows, series, stacked = false, caption, height = 220, width = 640, footer }: {
  rows: Row[]; series: Series[]; stacked?: boolean; caption: string; height?: number; width?: number; footer?: { label: string; values: string[] };
}) {
  const id = useId();
  const wrap = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<{ x: number; y: number; row: Row; focus?: string } | null>(null);
  const [table, setTable] = useState(false);
  const W = width, H = height, L = 44, R = 8, T = 10, B = 26;
  const ticks = niceTicks(Math.max(1, ...rows.map((r) => stacked ? series.reduce((a, s) => a + (r.values[s.key] ?? 0), 0) : Math.max(...series.map((s) => r.values[s.key] ?? 0)))));
  const max = ticks[ticks.length - 1];
  const y = (v: number) => T + (H - T - B) * (1 - v / max);
  const band = (W - L - R) / Math.max(1, rows.length);
  const groupW = Math.min(band * 0.72, stacked ? 44 : 30 * series.length);
  const barW = stacked ? groupW : (groupW - 2 * (series.length - 1)) / series.length;

  function show(e: PointerEvent<SVGGElement> | FocusEvent<SVGGElement>, row: Row) {
    const box = wrap.current?.getBoundingClientRect();
    const target = (e.currentTarget as SVGGElement).getBoundingClientRect();
    if (!box) return;
    const pointer = "clientX" in e;
    const x = pointer ? e.clientX - box.left : target.left - box.left + target.width / 2;
    const yy = pointer ? e.clientY - box.top - 14 : box.height * 0.35;
    setTip({ x: Math.min(Math.max(x, 90), box.width - 90), y: Math.max(56, yy), row });
  }

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <Legend series={series} />
        <button type="button" className="inline-flex items-center gap-1 text-xs font-semibold text-royal hover:underline" onClick={() => setTable((t) => !t)}
          aria-expanded={table} aria-controls={`${id}-table`}><Table2 size={13} aria-hidden="true" /> {table ? "Hide table" : "Show as table"}</button>
      </div>
      <div ref={wrap} className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`${caption}. Use “Show as table” for exact values.`}>
          {ticks.map((t) => (
            <g key={t}><line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="#E7DDF3" strokeWidth={1} />
              <text x={L - 6} y={y(t) + 4} textAnchor="end" fontSize="10" fill="#6E5A85">{short(t)}</text></g>))}
          {rows.map((r, i) => {
            const x0 = L + band * i + (band - groupW) / 2;
            let acc = 0;
            return (
              <g key={r.label} tabIndex={0} role="button" aria-label={`${r.label}: ${series.map((s) => `${s.label} ${money(r.values[s.key] ?? 0)}`).join(", ")}`}
                onPointerMove={(e) => show(e, r)} onPointerLeave={() => setTip(null)} onFocus={(e) => show(e, r)} onBlur={() => setTip(null)}
                className="cursor-default outline-none [&:focus-visible>rect.hit]:stroke-royal">
                <rect className="hit" x={L + band * i} y={T} width={band} height={H - T - B} fill="transparent" strokeWidth={1.5} rx={6} />
                {series.map((s, j) => {
                  const v = Math.max(0, r.values[s.key] ?? 0);
                  if (!v) return null;
                  const top = stacked ? y(acc + v) : y(v);
                  const bottom = stacked ? y(acc) : y(0);
                  const x = stacked ? x0 : x0 + j * (barW + 2);
                  const isTop = !stacked || series.slice(j + 1).every((n) => !(r.values[n.key] > 0));
                  acc += v;
                  const h = Math.max(1, bottom - top - (stacked && acc - v > 0 ? 2 : 0));
                  return isTop
                    ? <path key={s.key} fill={s.color} opacity={tip && tip.row !== r ? 0.55 : 1}
                        d={`M${x},${top + h} v${-(h - Math.min(4, h))} q0,-${Math.min(4, h)} ${Math.min(4, barW / 2)},-${Math.min(4, h)} h${barW - 2 * Math.min(4, barW / 2)} q${Math.min(4, barW / 2)},0 ${Math.min(4, barW / 2)},${Math.min(4, h)} v${h - Math.min(4, h)} z`} />
                    : <rect key={s.key} x={x} y={top} width={barW} height={h} fill={s.color} opacity={tip && tip.row !== r ? 0.55 : 1} />;
                })}
                <text x={L + band * i + band / 2} y={H - 8} textAnchor="middle" fontSize="11" fill="#6E5A85">{r.label}</text>
              </g>
            );
          })}
          <line x1={L} x2={W - R} y1={y(0)} y2={y(0)} stroke="#B69AD9" strokeWidth={1} />
        </svg>
        {tip && (
          <div role="status" className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-xl bg-white px-3 py-2 text-xs shadow-lg ring-1 ring-lavender/50"
            style={{ left: tip.x, top: tip.y }}>
            <p className="mb-1 font-semibold text-muted">{tip.row.label}</p>
            {series.map((s) => (
              <p key={s.key} className="flex items-center justify-between gap-4">
                <span className="inline-flex items-center gap-1.5 text-muted"><span className="h-0.5 w-3 rounded" style={{ background: s.color }} />{s.label}</span>
                <b className="tabular-nums text-plum">{money(tip.row.values[s.key] ?? 0)}</b></p>))}
          </div>
        )}
      </div>
      {footer && <div className="mt-1 grid text-[0.7rem] text-muted" style={{ gridTemplateColumns: `${L / W * 100}% repeat(${rows.length}, 1fr) ${R / W * 100}%` }}>
        <span className="truncate">{footer.label}</span>{footer.values.map((v, i) => <span key={i} className="text-center tabular-nums">{v}</span>)}<span /></div>}
      <div id={`${id}-table`} hidden={!table}><DataTable caption={caption} series={series} rows={rows} extra={footer} /></div>
    </div>
  );
}

/** Single-series horizontal bars with direct labels (value and share). */
export function BarList({ items, color = SERIES_COLORS[0], caption }: { items: { label: string; value: number; note?: string }[]; color?: string; caption: string }) {
  const max = Math.max(1, ...items.map((i) => i.value));
  const total = items.reduce((a, i) => a + i.value, 0);
  return (
    <ul className="space-y-2.5" aria-label={caption}>
      {items.map((i) => (
        <li key={i.label}>
          <div className="mb-0.5 flex items-baseline justify-between gap-2 text-sm">
            <span className="text-plum">{i.label}{i.note && <span className="ml-1 text-xs text-muted">{i.note}</span>}</span>
            <span className="tabular-nums text-ink"><b>{money(i.value)}</b>{total > 0 && <span className="ml-1 text-xs text-muted">{Math.round((i.value / total) * 100)}%</span>}</span>
          </div>
          <div className="h-2.5 rounded-full bg-lilac/60" aria-hidden="true"><div className="h-2.5 rounded-full" style={{ width: `${(i.value / max) * 100}%`, background: color }} /></div>
        </li>
      ))}
    </ul>
  );
}
