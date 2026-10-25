import { AlertTriangle, BarChart3, CalendarRange, CheckCircle2, HelpCircle, Landmark, PieChart, Scale, TrendingUp, XCircle } from "lucide-react";
import type { FinanceDashboard } from "../api/types";
import { formatDate, useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { AgentPanel } from "../components/AgentPanel";
import { BarChart, BarList, SERIES_COLORS } from "../components/charts";
import { FinanceTerms } from "../components/studio";
import { DemoNotice, DocumentsPanel, ManualEntry, MetricCard, RecordsPanel } from "../components/finance";
import { RunLauncher } from "../components/RunLauncher";
import { Card, ErrorState, LoadingState, PageHeader, RestrictedState, SeverityDot } from "../components/ui";

const month = (p: string) => new Date(Number(p.slice(0, 4)), Number(p.slice(5, 7)) - 1, 1).toLocaleDateString("en-US", { month: "short" });
const money = (n: number | null | undefined) => n == null ? "—" : `${n < 0 ? "−" : ""}$${Math.abs(n).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
const PURPOSE: Record<string, string> = { program: "Charitable programs", operations: "Operations", event: "Events", fundraising: "Fundraising", unclassified: "Not categorized" };

function Variance({ data }: { data: FinanceDashboard }) {
  if (!data.variances.length) return <p className="text-sm text-muted">No budget is recorded yet. Add budget lines (kind “budget_income” or “budget_expense”) to compare plans with results.</p>;
  return (
    <div className="space-y-4">{data.variances.map((v) => (
      <div key={`${v.label}-${v.kind}`}>
        <p className="mb-1 text-xs font-semibold text-muted">{v.label} · {v.kind === "income" ? "revenue" : "expenses"} · actuals for {v.months_with_actuals} of {v.months} months</p>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs text-muted"><th className="py-1">Category</th><th className="py-1 text-right">Budget</th><th className="py-1 text-right">Actual</th><th className="py-1 text-right">Difference</th><th className="py-1 pl-3">What it means</th></tr></thead>
          <tbody>{v.rows.map((r) => (
            <tr key={r.category} className="border-t border-lavender/30">
              <td className="py-1.5 text-plum">{r.category}</td><td className="py-1.5 text-right tabular-nums">{money(r.budget_usd)}</td>
              <td className="py-1.5 text-right tabular-nums">{money(r.actual_usd)}</td>
              <td className="py-1.5 text-right tabular-nums">{r.variance_usd == null ? "—" : `${r.variance_usd > 0 ? "+" : ""}${money(r.variance_usd)}${r.variance_pct != null ? ` (${Math.round(r.variance_pct * 100)}%)` : ""}`}</td>
              <td className="py-1.5 pl-3 text-xs">{r.direction === "favorable" ? <span className="inline-flex items-center gap-1 text-sage"><CheckCircle2 size={13} aria-hidden="true" />Favorable</span>
                : r.direction === "unfavorable" ? <span className="inline-flex items-center gap-1 text-danger"><XCircle size={13} aria-hidden="true" />Unfavorable</span>
                : <span className="inline-flex items-center gap-1 text-muted"><HelpCircle size={13} aria-hidden="true" />{r.direction}</span>}</td>
            </tr>))}</tbody>
        </table>
      </div>))}
      <p className="text-xs text-muted">For expenses, spending less than budget is favorable; for revenue, bringing in more is. The records show the size of each difference, not its cause.</p>
    </div>
  );
}

function FinanceBody() {
  const { data, error, loading, reload } = useApi<FinanceDashboard>("/api/finance/dashboard");
  if (loading && !data) return <LoadingState rows={5} />;
  if (error) return <ErrorState message={error.message} onRetry={reload} />;
  if (!data) return null;
  const sources = [{ key: "donations", label: "Donations", color: SERIES_COLORS[0] }, { key: "events", label: "Events", color: SERIES_COLORS[1] },
    { key: "grants", label: "Grants", color: SERIES_COLORS[2] }].filter((s) => data.donation_trend.some((r) => (r as Record<string, number | string>)[s.key] as number > 0));
  const purposes = Object.entries(data.expense_ratios.by_purpose).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ label: PURPOSE[k] ?? k, value: v }));

  return (
    <>
      <DemoNotice show={data.is_demo} />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-5">
          <p className="flex items-center gap-2 text-sm text-muted"><CalendarRange size={15} className="text-royal" aria-hidden="true" />Basis: <b className="text-plum">{data.basis}</b></p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{data.metrics.map((m) => <MetricCard key={m.key} m={m} />)}</div>
          <p className="text-xs text-muted">A surplus or available capacity does not by itself make an event affordable, and financial feasibility is never board authorization.</p>
          <FinanceTerms />

          <Card title="Revenue and expenses by month" icon={<BarChart3 size={16} aria-hidden="true" />}>
            {data.monthly.length === 0 ? <p className="text-sm text-muted">No monthly records yet.</p> : (
              <BarChart caption="Recorded revenue and expenses by month" rows={data.monthly.map((m) => ({ label: month(m.period), values: { income: m.income, expense: m.expense } }))}
                series={[{ key: "income", label: "Revenue", color: SERIES_COLORS[0] }, { key: "expense", label: "Expenses", color: SERIES_COLORS[1] }]}
                footer={{ label: "Net", values: data.monthly.map((m) => money(m.net)) }} />)}
            <p className="mt-2 text-xs text-muted">Recorded revenue is not cash on hand. Net is revenue minus expenses for the month.</p>
          </Card>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Where revenue came from" icon={<TrendingUp size={16} aria-hidden="true" />}>
              {sources.length === 0 ? <p className="text-sm text-muted">No revenue recorded.</p> : (
                <BarChart stacked height={230} width={380} caption="Revenue by source and month" series={sources}
                  rows={data.donation_trend.map((r) => ({ label: month(r.period), values: { donations: r.donations, events: r.events, grants: r.grants } }))} />)}
              {data.gifts_by_month && data.gifts_by_month.length > 0 && (
                <p className="mt-2 text-xs text-muted">Donation records: {data.gifts_by_month.map((g) => `${month(g.period)} ${g.gifts} gift(s), ${money(g.amount_usd)}`).join(" · ")}</p>)}
            </Card>
            <Card title="Where the money went" icon={<PieChart size={16} aria-hidden="true" />}>
              {purposes.length === 0 ? <p className="text-sm text-muted">No expenses recorded.</p> : <BarList caption="Expenses by purpose" items={purposes} />}
              <p className="mt-3 text-xs text-muted">Largest categories: {data.expense_by_category.slice(0, 3).map((c) => `${c.category} ${money(c.amount_usd)}`).join(" · ") || "—"}</p>
            </Card>
          </div>

          <Card title="Budget vs. actual" icon={<Scale size={16} aria-hidden="true" />}><Variance data={data} /></Card>

          {data.scenarios && (
            <Card title="Three-month outlook (estimates, not forecasts)" icon={<TrendingUp size={16} aria-hidden="true" />}>
              <table className="w-full text-sm">
                <thead><tr className="text-left text-xs text-muted"><th className="py-1">Scenario</th><th className="py-1 text-right">Revenue</th><th className="py-1 text-right">Expenses</th><th className="py-1 text-right">Net</th><th className="py-1 text-right">vs. averages</th></tr></thead>
                <tbody>{data.scenarios.rows.map((r) => (
                  <tr key={r.scenario} className="border-t border-lavender/30"><td className="py-1.5 text-plum">{r.scenario}</td><td className="py-1.5 text-right tabular-nums">{money(r.revenue_usd)}</td>
                    <td className="py-1.5 text-right tabular-nums">{money(r.cost_usd)}</td><td className={`py-1.5 text-right font-semibold tabular-nums ${r.net_usd < 0 ? "text-danger" : "text-sage"}`}>{money(r.net_usd)}</td>
                    <td className="py-1.5 text-right tabular-nums">{r.vs_first_usd ? money(r.vs_first_usd) : "—"}</td></tr>))}</tbody>
              </table>
              <p className="mt-2 text-xs text-muted">{data.scenarios.basis} These show sensitivity, not expected results.</p>
            </Card>
          )}

          <Card title="Events: what they cost and raised" icon={<Landmark size={16} aria-hidden="true" />}>
            {data.past_events.length === 0 ? <p className="text-sm text-muted">No past events recorded in Our Legacy.</p> : (
              <table className="w-full text-sm">
                <thead><tr className="text-left text-xs text-muted"><th className="py-1">Event</th><th className="py-1 text-right">Goal</th><th className="py-1 text-right">Raised</th><th className="py-1 text-right">Cost</th><th className="py-1 text-right">Net</th><th className="py-1 text-right">To programs</th></tr></thead>
                <tbody>{data.past_events.map((e) => (
                  <tr key={e.id} className="border-t border-lavender/30"><td className="py-1.5 text-plum">{e.name}<span className="block text-xs text-muted">{e.event_date ? formatDate(e.event_date) : ""}</span></td>
                    <td className="py-1.5 text-right tabular-nums">{money(e.fundraising_goal_usd)}</td><td className="py-1.5 text-right tabular-nums">{money(e.funds_raised_usd)}</td>
                    <td className="py-1.5 text-right tabular-nums">{money(e.total_cost_usd)}</td><td className="py-1.5 text-right tabular-nums">{money(e.net_usd)}</td>
                    <td className="py-1.5 text-right tabular-nums">{e.funds_directed_usd == null ? "Not recorded" : money(e.funds_directed_usd)}</td></tr>))}</tbody>
              </table>)}
            <p className="mt-2 text-xs text-muted">From Our Legacy records. Event costs here are not in the monthly ledger unless they were also recorded there.</p>
          </Card>

          {data.statements.length > 0 && (
            <Card title="Statement periods (kept separate from the monthly ledger)" icon={<CalendarRange size={16} aria-hidden="true" />}>
              <ul className="space-y-1 text-sm">{data.statements.map((s) => <li key={s.period_label}><b className="text-plum">{s.period_label}:</b> revenue {money(s.revenue_usd)}, expenses {money(s.expenses_usd)}, net {money(s.net_usd)}</li>)}</ul>
            </Card>
          )}

          <Card title="Warnings and missing information" icon={<AlertTriangle size={16} aria-hidden="true" />}>
            {data.warnings.length === 0 ? <p className="text-sm text-muted">No warnings.</p> : (
              <ul className="space-y-2.5">{data.warnings.map((w) => (
                <li key={w.title} className="flex gap-2.5"><SeverityDot severity={w.severity} />
                  <div><p className="text-sm font-semibold text-plum">{w.title}</p><p className="text-sm text-muted">{w.detail}</p></div></li>))}</ul>)}
            {data.missing.length > 0 && (
              <div className="mt-4"><p className="label">Missing information</p><ul className="list-disc space-y-0.5 pl-5 text-sm text-ink/85">{data.missing.map((m) => <li key={m}>{m}</li>)}</ul></div>)}
            <p className="mt-4 rounded-xl bg-lilac/60 px-3 py-2 text-xs text-plum">{data.method}</p>
          </Card>
        </div>

        <div className="min-w-0 space-y-5">
          <DocumentsPanel onChange={reload} />
          <ManualEntryGate onSaved={reload} />
          <RecordsPanel onChange={reload} />
          <RunLauncher title="Ask Financial Analysis" intent="financial_review" lockIntent
            examples={["Explain our financial position, our budget variances, and how much we could responsibly spend on an event."]} />
          <AgentPanel agents={["financial_analysis"]} upcoming={[]} />
        </div>
      </div>
    </>
  );
}

function ManualEntryGate({ onSaved }: { onSaved: () => void }) {
  const { can } = useAuth();
  return can("manage_financials") ? <ManualEntry onSaved={onSaved} /> : null;
}

export default function FinancePage() {
  const { can } = useAuth();
  return (
    <>
      <PageHeader eyebrow="Financial Intelligence" title="Know what the foundation can afford"
        subtitle="Every number is computed by code from your records, with a plain-English explanation. Revenue is never shown as cash, restricted gifts are never counted as spendable, and AI-read figures wait for your review." />
      {can("view_financials") ? <FinanceBody /> : <RestrictedState area="Financial Intelligence" />}
    </>
  );
}
