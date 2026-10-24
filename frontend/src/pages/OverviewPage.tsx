import { Activity, AlertTriangle, BookHeart, CalendarHeart, Compass, FileText, HandCoins, Lightbulb, Plus, Sprout, Star } from "lucide-react";
import { Link } from "react-router-dom";
import type { Overview } from "../api/types";
import { formatDate, usd, useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { Butterfly } from "../butterflies/Butterfly";
import { RunLauncher } from "../components/RunLauncher";
import { StatusPill } from "../components/agents";
import { GALA_EXAMPLE } from "./ActivityPage";
import { Card, DemoBadge, EmptyState, ErrorState, LoadingState, PageHeader, SeverityDot, StatTile } from "../components/ui";

export default function OverviewPage() {
  const { user, can } = useAuth();
  const { data, error, loading, reload } = useApi<Overview>("/api/overview");
  const today = new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });

  return (
    <>
      <PageHeader
        eyebrow={today}
        title={
          <span className="inline-flex items-center gap-3">
            Hello, {data?.first_name ?? user?.first_name}
            <Butterfly size={40} motion="still" palette={2} className="rotate-12" />
          </span>
        }
        subtitle={<>Let's make a difference today. <span className="text-plum/80">{user?.organization?.name}</span></>}
      />

      <div className="mb-6 flex flex-wrap gap-2 animate-fade-up">
        <Link to="/events" className="btn btn-primary"><Plus size={16} aria-hidden="true" /> Plan a fundraiser</Link>
        <Link to="/legacy" className="btn btn-soft"><Sprout size={16} aria-hidden="true" /> Record a past event</Link>
        <Link to="/mission" className="btn btn-soft"><Compass size={16} aria-hidden="true" /> Discover partners</Link>
        {can("view_donor_data") && (
          <Link to="/donations" className="btn btn-soft"><HandCoins size={16} aria-hidden="true" /> Review donations</Link>
        )}
      </div>

      <div className="mb-5"><RunLauncher examples={[GALA_EXAMPLE]} /></div>

      {loading && <LoadingState rows={4} />}
      {error && <ErrorState message={error.message} onRetry={reload} />}
      {data && (
        <div className="grid gap-5 lg:grid-cols-3">
          <Card title="Planned fundraisers" icon={<CalendarHeart size={16} aria-hidden="true" />} className="lg:col-span-2"
            action={<Link to="/events" className="btn btn-ghost !py-1.5 text-sm">Event Studio →</Link>}>
            {data.planned_events.length === 0 ? (
              <EmptyState title="No events planned yet" action={<Link to="/events" className="btn btn-soft">Plan an event</Link>}>
                Start a plan in Event Studio. The agents will help with venues, budgets, and outreach.
              </EmptyState>
            ) : (
              <ul className="space-y-3">
                {data.planned_events.map((e) => (
                  <li key={e.id} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-lavender/30 bg-ivory/60 px-4 py-3">
                    <div>
                      <p className="font-semibold text-plum">{e.name}</p>
                      <p className="text-sm text-muted">{formatDate(e.target_date)} · {e.city || "City to be decided"} · {e.status}</p>
                    </div>
                    <div className="flex items-center gap-3 text-sm">
                      <span className="text-muted">Goal <b className="text-plum">{usd(e.fundraising_goal_usd)}</b></span>
                      <span className="text-muted">Budget <b className="text-plum">{usd(e.budget_limit_usd)}</b></span>
                      {e.is_demo && <DemoBadge label="Demo" />}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Financial flags" icon={<AlertTriangle size={16} aria-hidden="true" />}>
            {data.financial.restricted ? (
              <p className="text-sm text-muted">Financial details are limited to the chair and treasurer.</p>
            ) : data.financial.flags.length === 0 ? (
              <p className="text-sm text-muted">No warning flags right now.</p>
            ) : (
              <ul className="space-y-3">
                {data.financial.flags.map((f) => (
                  <li key={f.title} className="flex gap-2.5">
                    <SeverityDot severity={f.severity} />
                    <div>
                      <p className="text-sm font-semibold text-plum">{f.title}</p>
                      <p className="text-sm text-muted">{f.detail}</p>
                    </div>
                  </li>
                ))}
                {data.financial.is_demo && <li><DemoBadge label="Computed from demo books" /></li>}
              </ul>
            )}
          </Card>

          <Card title="From our history" icon={<BookHeart size={16} aria-hidden="true" />} className="lg:col-span-2"
            action={<Link to="/legacy" className="btn btn-ghost !py-1.5 text-sm">Our Legacy →</Link>}>
            {data.history.events_recorded === 0 ? (
              <EmptyState title="No past events recorded">Record past events so future plans can learn from them.</EmptyState>
            ) : (
              <div className="grid gap-3 sm:grid-cols-3">
                <StatTile label="Events recorded" value={data.history.events_recorded} demo={data.history.is_demo} />
                <StatTile label="Total raised" value={usd(data.history.total_raised_usd)} hint={`Net ${usd(data.history.total_net_usd)}`} />
                <StatTile
                  label="Most efficient"
                  value={data.history.most_efficient_event ? `${data.history.most_efficient_event.raised_per_dollar}×` : "—"}
                  hint={data.history.most_efficient_event ? `raised per $1 spent · ${data.history.most_efficient_event.name}` : undefined}
                />
              </div>
            )}
          </Card>

          <Card title="Lessons learned" icon={<Lightbulb size={16} aria-hidden="true" />}>
            {data.lessons.length === 0 ? (
              <p className="text-sm text-muted">
                The Event Intelligence agent will turn board reflections into lessons here. Nothing is shown until it has really run.
              </p>
            ) : (
              <ul className="space-y-2 text-sm">{data.lessons.map((l) => <li key={l.id}>{l.lesson}</li>)}</ul>
            )}
          </Card>

          <Card title="Recent agent activity" icon={<Activity size={16} aria-hidden="true" />}>
            {data.recent_activity.length === 0 ? (
              <EmptyState title="No agent runs yet">Every workflow you run will appear here, step by step.</EmptyState>
            ) : (
              <ul className="space-y-2 text-sm">
                {data.recent_activity.map((r) => (
                  <li key={r.id}><Link to={`/activity/runs/${r.id}`} className="flex items-center justify-between gap-2 rounded-xl px-2 py-1.5 hover:bg-lilac/50">
                    <span className="text-plum">Workflow #{r.id} · {r.workflow_type.replace(/_/g, " ")}</span><StatusPill status={r.status} /></Link></li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Saved opportunities" icon={<Star size={16} aria-hidden="true" />}>
            {data.saved_opportunities.length === 0 ? (
              <EmptyState title="Nothing saved yet">Opportunities found by Mission Discovery will show up here with their sources.</EmptyState>
            ) : (
              <ul className="space-y-2 text-sm">{data.saved_opportunities.map((o) => <li key={o.id}>{o.title}</li>)}</ul>
            )}
          </Card>

          <Card title="Drafts awaiting review" icon={<FileText size={16} aria-hidden="true" />}>
            {data.drafts_awaiting_review.length === 0 ? (
              <EmptyState title="No drafts to review">Outreach drafts wait here for a person to review and send outside SAM SPACE.</EmptyState>
            ) : (
              <ul className="space-y-2 text-sm">{data.drafts_awaiting_review.map((d) => <li key={d.id}>{d.subject}</li>)}</ul>
            )}
          </Card>
        </div>
      )}
    </>
  );
}
