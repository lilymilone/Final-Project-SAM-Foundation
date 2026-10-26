import { Activity, AlertTriangle, ArrowRight, CalendarHeart, CalendarPlus, Compass, Landmark, Lightbulb, Mail, Sprout, Star } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Overview } from "../api/types";
import { formatDate, usd, useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { Butterfly } from "../butterflies/Butterfly";
import { Logo } from "../components/Brand";
import { PHILOSOPHY } from "../components/Philosophy";
import { StatusPill } from "../components/agents";
import { Card, DemoBadge, EmptyState, ErrorState, LoadingState, SeverityDot } from "../components/ui";

const clip = (t: string, n = 170) => (t.length > n ? `${t.slice(0, n).replace(/\s+\S*$/, "")}…` : t);

function QuickAction({ to, icon, label, hint, badge }: { to: string; icon: ReactNode; label: string; hint: string; badge?: number }) {
  return (
    <Link to={to} className="group relative flex flex-col gap-2 rounded-2xl border border-lavender/40 bg-white/85 p-4 shadow-sm transition hover:-translate-y-0.5 hover:border-royal hover:shadow-[var(--shadow-soft)]">
      <span className="grid h-10 w-10 place-items-center rounded-xl bg-lilac text-royal transition group-hover:bg-royal group-hover:text-white">{icon}</span>
      <span className="font-semibold text-plum">{label}</span>
      <span className="text-xs text-muted">{hint}</span>
      {badge ? <span className="absolute right-3 top-3 rounded-full bg-rose px-2 py-0.5 text-xs font-semibold text-white">{badge}</span> : null}
    </Link>
  );
}

function MoreLink({ to, children }: { to: string; children: ReactNode }) {
  return <Link to={to} className="inline-flex items-center gap-1 text-sm font-semibold text-royal hover:underline">{children} <ArrowRight size={14} aria-hidden="true" /></Link>;
}

export default function OverviewPage() {
  const { user, can } = useAuth();
  const { data, error, loading, reload } = useApi<Overview>("/api/overview");
  const today = new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
  const flags = data ? [...new Map(data.financial.flags.map((f) => [f.title, f])).values()] : [];

  return (
    <>
      <header className="philosophy mb-6 grid grid-cols-1 items-center gap-6 overflow-hidden rounded-3xl p-6 sm:grid-cols-[auto_minmax(0,1fr)] sm:p-8 animate-fade-up">
        <Logo size={132} className="mx-auto sm:mx-0" />
        <div className="min-w-0 text-center sm:text-left">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-royal">{today}</p>
          <h1 className="mt-1 inline-flex items-center gap-3 font-display text-4xl font-semibold text-plum sm:text-5xl">
            Hello, {data?.first_name ?? user?.first_name}
            <Butterfly size={38} motion="still" palette={2} className="rotate-12" />
          </h1>
          <p className="mt-1 text-sm text-muted">{user?.organization?.name}</p>
          <blockquote className="mt-4 font-display text-xl italic leading-snug text-royal sm:text-2xl">“{PHILOSOPHY}”</blockquote>
        </div>
      </header>

      <section aria-label="Quick actions" className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <QuickAction to="/events" icon={<CalendarPlus size={20} aria-hidden="true" />} label="Plan an Event" hint="Venues, budget, and inquiries" />
        <QuickAction to="/mission" icon={<Compass size={20} aria-hidden="true" />} label="Find a Cause" hint="Organizations and research to support" />
        {can("view_financials") && (
          <QuickAction to="/finance#analyze" icon={<Landmark size={20} aria-hidden="true" />} label="Analyze Finances" hint="Revenue, spending, and what we can afford" />
        )}
        <QuickAction to="/partnerships#drafts" icon={<Mail size={20} aria-hidden="true" />} label="Review Outreach Drafts" hint="Edit, copy, and mark reviewed"
          badge={data?.drafts_awaiting_total} />
        {can("manage_events") && (
          <QuickAction to="/legacy?add=1" icon={<Sprout size={20} aria-hidden="true" />} label="Add a Past Event" hint="Upload records or describe it" />
        )}
        <QuickAction to="/activity" icon={<Activity size={20} aria-hidden="true" />} label="Review Agent Activity" hint="Every step, tool, and cost" />
      </section>

      {loading && <LoadingState rows={4} />}
      {error && <ErrorState message={error.message} onRetry={reload} />}
      {data && (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
          <Card title="Events being planned" icon={<CalendarHeart size={16} aria-hidden="true" />} className="lg:col-span-2"
            action={<MoreLink to="/events">Event Studio</MoreLink>}>
            {data.planned_events.length === 0 ? (
              <EmptyState title="No events planned yet" action={<Link to="/events" className="btn btn-soft">Plan an event</Link>}>
                Fill in the event details and the agents will research venues, check the budget, and draft inquiries.
              </EmptyState>
            ) : (
              <ul className="space-y-2">
                {data.planned_events.slice(0, 6).map((e) => (
                  <li key={e.id}>
                    <Link to={`/events?plan=${e.id}`} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-lavender/30 bg-ivory/60 px-4 py-3 transition hover:border-royal hover:bg-lilac/40">
                      <div className="min-w-0">
                        <p className="truncate font-semibold text-plum">{e.name}</p>
                        <p className="text-sm text-muted">{formatDate(e.target_date)} · {e.city || "City to be decided"} · {e.status}</p>
                      </div>
                      <div className="flex items-center gap-3 text-sm">
                        <span className="text-muted">Goal <b className="text-plum">{usd(e.fundraising_goal_usd)}</b></span>
                        <span className="text-muted">Budget <b className="text-plum">{usd(e.budget_limit_usd)}</b></span>
                        {e.is_demo && <DemoBadge label="Demo" />}
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Drafts awaiting review" icon={<Mail size={16} aria-hidden="true" />}
            action={data.drafts_awaiting_total > 0 ? <span className="rounded-full bg-rose/15 px-2.5 py-0.5 text-sm font-semibold text-rose">{data.drafts_awaiting_total}</span> : undefined}>
            {data.drafts_awaiting_review.length === 0 ? (
              <EmptyState title="Nothing to review">New outreach drafts from the agents will appear here.</EmptyState>
            ) : (
              <>
                <ul className="space-y-1.5 text-sm">{data.drafts_awaiting_review.map((d) => (
                  <li key={d.id}><Link to={`/partnerships#draft-${d.id}`} className="block rounded-xl px-2 py-1.5 hover:bg-lilac/50">
                    <span className="block truncate font-semibold text-plum">{d.recipient_org}</span>
                    <span className="block truncate text-muted">{d.subject}</span></Link></li>))}
                </ul>
                <div className="mt-3"><MoreLink to="/partnerships#drafts">Open the review center</MoreLink></div>
              </>
            )}
          </Card>

          <Card title="Recent insights from past events" icon={<Lightbulb size={16} aria-hidden="true" />} className="lg:col-span-2"
            action={<MoreLink to="/legacy">Our Legacy</MoreLink>}>
            {data.lessons.length === 0 ? (
              <EmptyState title="No lessons yet">Add past events and board reflections, then generate lessons from an event's page.</EmptyState>
            ) : (
              <ul className="space-y-2">
                {data.lessons.map((l) => (
                  <li key={l.id}>
                    <Link to={l.focus_event_id ? `/legacy/${l.focus_event_id}` : "/legacy"} className="block rounded-2xl bg-ivory/70 px-4 py-3 text-sm transition hover:bg-lilac/50">
                      {l.theme && <span className="mb-0.5 block text-xs font-semibold uppercase tracking-wide text-royal">{l.theme}</span>}
                      <span className="text-ink/90">{clip(l.lesson)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-3 text-xs text-muted">
              {data.history.events_recorded} past events recorded · {usd(data.history.total_raised_usd)} raised in recorded events
              {data.history.is_demo && " (includes demo records)"}
            </p>
          </Card>

          <Card title="Financial warnings" icon={<AlertTriangle size={16} aria-hidden="true" />}
            action={!data.financial.restricted ? <MoreLink to="/finance">Finance</MoreLink> : undefined}>
            {data.financial.restricted ? (
              <p className="text-sm text-muted">Financial details are limited to the chair and treasurer.</p>
            ) : flags.length === 0 ? (
              <p className="text-sm text-muted">No warnings right now.</p>
            ) : (
              <ul className="space-y-3">
                {flags.slice(0, 4).map((f) => (
                  <li key={f.title} className="flex gap-2.5">
                    <SeverityDot severity={f.severity} />
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-plum">{f.title}</p>
                      <p className="text-sm text-muted">{clip(f.detail, 120)}</p>
                    </div>
                  </li>
                ))}
                {data.financial.is_demo && <li><DemoBadge label="Computed from demo books" /></li>}
              </ul>
            )}
          </Card>

          <Card title="Saved opportunities" icon={<Star size={16} aria-hidden="true" />}>
            {data.saved_opportunities.length === 0 ? (
              <EmptyState title="Nothing saved yet" action={<Link to="/mission" className="btn btn-soft">Find a cause</Link>}>
                Save organizations from Mission Discovery to keep them here.
              </EmptyState>
            ) : (
              <ul className="space-y-1.5 text-sm">{data.saved_opportunities.map((o) => (
                <li key={o.id}><Link to={`/mission#finding-${o.id}`} className="block truncate rounded-xl px-2 py-1.5 font-semibold text-plum hover:bg-lilac/50">{o.title}</Link></li>))}
              </ul>
            )}
          </Card>

          <Card title="Recently completed workflows" icon={<Activity size={16} aria-hidden="true" />} className="lg:col-span-2"
            action={<MoreLink to="/activity">Agent Activity</MoreLink>}>
            {data.recent_activity.length === 0 ? (
              <EmptyState title="No completed workflows yet">Plan an event or find a cause to start one.</EmptyState>
            ) : (
              <ul className="space-y-1.5 text-sm">
                {data.recent_activity.map((r) => (
                  <li key={r.id}><Link to={`/activity/runs/${r.id}`} className="flex items-center justify-between gap-3 rounded-xl px-2 py-1.5 hover:bg-lilac/50">
                    <span className="min-w-0 truncate text-plum">#{r.id} · {r.request || r.workflow_type.replace(/_/g, " ")}</span>
                    <span className="flex shrink-0 items-center gap-2 text-xs text-muted">${r.spent_usd.toFixed(3)}<StatusPill status={r.status} /></span></Link></li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}

    </>
  );
}
