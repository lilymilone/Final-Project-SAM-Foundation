import { HeartHandshake } from "lucide-react";
import type { Impact } from "../api/types";
import { useApi } from "../api/useApi";
import { Card, DemoBadge, LoadingState } from "./ui";

const TYPE_STYLE: Record<string, string> = {
  "Actual observation": "bg-[#e3f1e8] text-sage", "Self-reported": "bg-lilac text-royal",
  "AI interpretation": "bg-blush/70 text-plum", Estimate: "bg-[#fbf1e3] text-amber",
};

/** Community impact from stored records only. Every metric says what kind of evidence it is. */
export function ImpactPanel({ compact = false }: { compact?: boolean }) {
  const { data, loading } = useApi<Impact>("/api/impact");
  return (
    <Card title="Community impact" icon={<HeartHandshake size={16} aria-hidden="true" />}
      action={data?.is_demo ? <DemoBadge label="From demo records" /> : undefined}>
      {loading && <LoadingState rows={3} />}
      {data && (
        <>
          <ul className={`grid gap-2 ${compact ? "sm:grid-cols-2" : "sm:grid-cols-2"}`}>
            {(compact ? data.metrics.slice(0, 6) : data.metrics).map((m) => (
              <li key={m.key} className="rounded-2xl bg-ivory/80 px-3 py-2.5">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-xs font-semibold text-muted">{m.label}</p>
                  <span className={`shrink-0 rounded-full px-1.5 py-px text-[0.62rem] font-semibold ${TYPE_STYLE[m.type] ?? "bg-lilac text-plum"}`}>{m.type}</span>
                </div>
                <p className={`font-display font-semibold text-plum ${m.value == null || m.display.startsWith("Not") ? "text-lg text-muted" : "text-2xl"}`}>{m.display}</p>
                <p className="text-[0.68rem] text-muted">{m.coverage}. {m.basis}</p>
                {!compact && m.examples.length > 0 && (
                  <ul className="mt-1 space-y-0.5 text-xs text-ink/80">{m.examples.slice(0, 2).map((x, i) => <li key={i}>“{x.text}” <span className="text-muted">({x.source})</span></li>)}</ul>
                )}
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[0.7rem] text-muted">Computed only from what the board recorded. Blank fields show as “Not recorded”, never zero. No testimonials or figures are generated.</p>
        </>
      )}
    </Card>
  );
}
