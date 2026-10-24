import { AlertTriangle, Calculator, Landmark } from "lucide-react";
import type { FinanceSummary } from "../api/types";
import { usd, useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { AgentPanel } from "../components/AgentPanel";
import { Card, DemoBadge, ErrorState, LoadingState, PageHeader, RestrictedState, SeverityDot, StatTile } from "../components/ui";

function FinanceBody() {
  const { data, error, loading, reload } = useApi<FinanceSummary>("/api/finance/summary");
  if (loading) return <LoadingState rows={4} />;
  if (error) return <ErrorState message={error.message} onRetry={reload} />;
  if (!data) return null;
  const peak = Math.max(1, ...data.months.flatMap((m) => [m.income, m.expense]));

  return (
    <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
      <div className="space-y-5">
        <div className="grid gap-3 sm:grid-cols-3 animate-fade-up">
          <StatTile label="Operating reserve" value={usd(data.reserve_usd)} hint={data.reserve_period ? `as of ${data.reserve_period}` : undefined} demo={data.is_demo} />
          <StatTile label="Avg. monthly expense" value={usd(data.average_monthly_expense)} />
          <StatTile label="Months covered" value={data.reserve_months_covered ?? "—"} hint="reserve ÷ average expense" />
        </div>

        <Card title="Income and expenses by month" icon={<Landmark size={16} aria-hidden="true" />}
          action={data.is_demo ? <DemoBadge label="Demo books" /> : undefined}>
          <div className="space-y-3">
            {data.months.map((m) => (
              <div key={m.period} className="grid grid-cols-[4.5rem_1fr_6rem] items-center gap-3 text-sm">
                <span className="font-semibold text-plum">{m.period}</span>
                <div className="space-y-1" aria-hidden="true">
                  <div className="h-2.5 rounded-full bg-gradient-to-r from-lavender to-royal" style={{ width: `${(m.income / peak) * 100}%` }} />
                  <div className="h-2.5 rounded-full bg-gradient-to-r from-blush to-rose" style={{ width: `${(m.expense / peak) * 100}%` }} />
                </div>
                <span className={`text-right font-semibold ${m.net < 0 ? "text-danger" : "text-sage"}`}>
                  {m.net < 0 ? "−" : "+"}{usd(Math.abs(m.net))}
                </span>
              </div>
            ))}
          </div>
          <div className="mt-4 flex gap-4 text-xs text-muted">
            <span className="inline-flex items-center gap-1.5"><span className="h-2 w-4 rounded-full bg-royal" /> Income</span>
            <span className="inline-flex items-center gap-1.5"><span className="h-2 w-4 rounded-full bg-rose" /> Expenses</span>
            <span>Right column: net for the month</span>
          </div>
          <table className="sr-only">
            <caption>Monthly income, expenses and net</caption>
            <thead><tr><th>Month</th><th>Income</th><th>Expenses</th><th>Net</th></tr></thead>
            <tbody>{data.months.map((m) => <tr key={m.period}><td>{m.period}</td><td>{m.income}</td><td>{m.expense}</td><td>{m.net}</td></tr>)}</tbody>
          </table>
        </Card>

        <Card title="Warning flags" icon={<AlertTriangle size={16} aria-hidden="true" />}>
          {data.flags.length === 0 ? <p className="text-sm text-muted">No warning flags.</p> : (
            <ul className="space-y-3">
              {data.flags.map((f) => (
                <li key={f.title} className="flex gap-2.5">
                  <SeverityDot severity={f.severity} />
                  <div><p className="text-sm font-semibold text-plum">{f.title}</p><p className="text-sm text-muted">{f.detail}</p></div>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-4 flex items-center gap-2 rounded-xl bg-lilac/60 px-3 py-2 text-xs text-plum">
            <Calculator size={14} aria-hidden="true" /> {data.method}
          </p>
        </Card>
      </div>
      <AgentPanel
        agents={["financial_analysis"]}
        upcoming={["Upload statements (validated CSV)", "Event affordability, computed in Python", "Budget constraints for every plan", "Clear labels: estimate vs. verified"]}
      />
    </div>
  );
}

export default function FinancePage() {
  const { can } = useAuth();
  return (
    <>
      <PageHeader eyebrow="Financial Intelligence" title="Know what the foundation can afford"
        subtitle="Every number is computed by code from your records. The AI only interprets the results, and it never does arithmetic." />
      {can("view_financials") ? <FinanceBody /> : <RestrictedState area="Financial Intelligence" />}
    </>
  );
}
