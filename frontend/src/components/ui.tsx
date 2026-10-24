import { AlertTriangle, Lock, RefreshCw, Sparkles } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { Butterfly } from "../butterflies/Butterfly";

export function PageHeader({ eyebrow, title, subtitle, actions }: { eyebrow?: string; title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-7 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between animate-fade-up">
      <div>
        {eyebrow && <p className="eyebrow mb-2">{eyebrow}</p>}
        <h1 className="font-display text-4xl font-semibold leading-tight text-plum sm:text-[2.6rem]">{title}</h1>
        {subtitle && <p className="mt-2 max-w-2xl text-[0.98rem] text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function Card({ title, icon, action, children, className = "", id }: { title?: ReactNode; icon?: ReactNode; action?: ReactNode; children: ReactNode; className?: string; id?: string }) {
  return (
    <section className={`card p-5 sm:p-6 animate-fade-up ${className}`} id={id}>
      {(title || action) && (
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="flex items-center gap-2.5 font-display text-[1.45rem] font-semibold text-plum">
            {icon && <span className="grid h-8 w-8 place-items-center rounded-full bg-lilac text-royal">{icon}</span>}
            {title}
          </h2>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function DemoBadge({ label = "Demo data" }: { label?: string }) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border border-rose/40 bg-blush/70 px-2.5 py-0.5 text-[0.7rem] font-semibold uppercase tracking-wider text-plum"
      title="Synthetic demonstration record, not real foundation data"
    >
      <Sparkles size={11} aria-hidden="true" /> {label}
    </span>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-dashed border-lavender/70 bg-ivory/60 px-6 py-8 text-center">
      <Butterfly size={40} motion="still" palette={2} className="mb-3 opacity-80" />
      <p className="font-display text-xl font-semibold text-plum">{title}</p>
      {children && <div className="mt-1.5 max-w-md text-sm text-muted">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function LoadingState({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3" role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton h-14" style={{ opacity: 1 - i * 0.18 }} />
      ))}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-2xl border border-danger/25 bg-[#fbeef3] p-4 text-sm text-plum">
      <AlertTriangle size={18} className="mt-0.5 shrink-0 text-danger" aria-hidden="true" />
      <div className="flex-1">
        <p className="font-semibold">We couldn't load this.</p>
        <p className="text-muted">{message}</p>
      </div>
      {onRetry && (
        <button className="btn btn-ghost !px-3 !py-1.5 text-sm" onClick={onRetry}>
          <RefreshCw size={14} aria-hidden="true" /> Retry
        </button>
      )}
    </div>
  );
}

export function RestrictedState({ area }: { area: string }) {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-lavender/60 bg-white/70 px-6 py-10 text-center">
      <span className="mb-3 grid h-12 w-12 place-items-center rounded-full bg-lilac text-royal">
        <Lock size={20} aria-hidden="true" />
      </span>
      <p className="font-display text-2xl font-semibold text-plum">{area} is restricted</p>
      <p className="mt-1.5 max-w-md text-sm text-muted">
        Your board role doesn't include access to {area.toLowerCase()}. The board chair or treasurer can review it. This rule is enforced on the server.
      </p>
    </div>
  );
}

export function StatTile({ label, value, hint, demo }: { label: string; value: ReactNode; hint?: ReactNode; demo?: boolean }) {
  return (
    <div className="rounded-2xl border border-lavender/35 bg-gradient-to-br from-white to-ivory p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[0.78rem] font-semibold uppercase tracking-wider text-muted">{label}</p>
        {demo && <DemoBadge label="Demo" />}
      </div>
      <p className="mt-1 font-display text-3xl font-semibold text-plum">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-muted">{hint}</p>}
    </div>
  );
}

export function Toast({ message, tone = "success", onDone }: { message: string; tone?: "success" | "error"; onDone: () => void }) {
  useEffect(() => {
    const t = window.setTimeout(onDone, 4200);
    return () => window.clearTimeout(t);
  }, [onDone]);
  return (
    <div
      role="status"
      aria-live="polite"
      className={`fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-full px-5 py-2.5 text-sm font-semibold shadow-[var(--shadow-lift)] animate-fade-up ${
        tone === "success" ? "bg-plum text-white" : "bg-danger text-white"
      }`}
    >
      {message}
    </div>
  );
}

export function SeverityDot({ severity }: { severity: "high" | "medium" | "low" }) {
  const color = severity === "high" ? "bg-danger" : severity === "medium" ? "bg-amber" : "bg-sage";
  return <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${color}`} aria-label={`${severity} severity`} />;
}
