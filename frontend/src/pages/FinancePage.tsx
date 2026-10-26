import { AlertTriangle, BarChart3, Calculator, CalendarRange, CheckCircle2, FilePlus2, HelpCircle, Landmark, PieChart, Scale, TrendingUp, Upload, Wand2, XCircle } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import type { Affordability, EventModel, FinanceDashboard } from "../api/types";
import { formatDate, useApi } from "../api/useApi";
import { useAuth } from "../auth/AuthContext";
import { BarChart, BarList, SERIES_COLORS } from "../components/charts";
import { FinancialModelEditor } from "../components/studio";
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
        <div className="overflow-x-auto"><table className="w-full text-sm">
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
        </table></div>
      </div>))}
      <p className="text-xs text-muted">For expenses, spending less than budget is favorable; for revenue, bringing in more is. The records show the size of each difference, not its cause.</p>
    </div>
  );
}

const SCENARIO_FIELDS: [string, string, string][] = [
  ["attendance", "Guests", "150"], ["ticket_price_usd", "Ticket price ($)", "250"], ["venue_rental_usd", "Venue rental ($)", "6000"],
  ["catering_per_guest_usd", "Catering per guest ($)", "95"], ["entertainment_usd", "Entertainment ($)", "1500"], ["marketing_usd", "Marketing ($)", "800"],
  ["staffing_usd", "Staffing ($)", "1200"], ["insurance_usd", "Insurance and permits ($)", "500"], ["contingency_pct", "Contingency (0–0.6)", "0.1"],
  ["deposit_pct", "Deposit share (0–1)", "0.3"], ["sponsorship_confirmed_usd", "Confirmed sponsorship ($)", "0"], ["sponsorship_usd", "Expected sponsorship ($)", "0"],
  ["donations_per_attendee_usd", "Donations per guest ($)", "0"],
];

/** A what-if budget for an event, computed by the backend's deterministic event model (no AI involved). */
function BudgetScenario() {
  const [values, setValues] = useState<Record<string, string>>({});
  const [limits, setLimits] = useState({ max: "", target: "" });
  const [result, setResult] = useState<{ model: EventModel; affordability: Affordability } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function calculate() {
    setBusy(true);
    setError(null);
    try {
      const assumptions = Object.fromEntries(Object.entries(values).filter(([, v]) => v.trim() !== "")
        .map(([k, v]) => [k, { value: Number(v), kind: "board", basis: "Entered for this scenario" }]));
      setResult(await api<{ model: EventModel; affordability: Affordability }>("/api/event-model/calculate", {
        json: { assumptions, max_budget_usd: limits.max ? Number(limits.max) : null, target_usd: limits.target ? Number(limits.target) : null } }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not calculate.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card id="scenario" title="Budget scenario" icon={<Calculator size={16} aria-hidden="true" />}
      action={<button type="button" className="btn btn-ghost !py-1 text-sm" onClick={() => setValues(Object.fromEntries(SCENARIO_FIELDS.map(([k, , ex]) => [k, ex])))}>Fill example values</button>}>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {SCENARIO_FIELDS.map(([k, label]) => (
          <label key={k} className="block"><span className="mb-1 block text-xs font-semibold text-plum">{label}</span>
            <input type="number" step="any" min={0} className="field !py-1.5 text-sm" value={values[k] ?? ""} onChange={(e) => setValues((v) => ({ ...v, [k]: e.target.value }))} /></label>
        ))}
        <label className="block"><span className="mb-1 block text-xs font-semibold text-plum">Maximum budget ($)</span>
          <input type="number" min={0} className="field !py-1.5 text-sm" value={limits.max} onChange={(e) => setLimits((l) => ({ ...l, max: e.target.value }))} /></label>
        <label className="block"><span className="mb-1 block text-xs font-semibold text-plum">Fundraising target ($)</span>
          <input type="number" min={0} className="field !py-1.5 text-sm" value={limits.target} onChange={(e) => setLimits((l) => ({ ...l, target: e.target.value }))} /></label>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button type="button" className="btn btn-primary" onClick={calculate} disabled={busy}><Calculator size={15} aria-hidden="true" /> {busy ? "Calculating…" : "Calculate scenario"}</button>
        {result && <span className="text-sm text-plum">Verdict: <b>{result.affordability.verdict.replace(/_/g, " ")}</b></span>}
      </div>
      {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
      {result && <div className="mt-4"><FinancialModelEditor model={result.model} affordability={result.affordability} planId={null} /></div>}
    </Card>
  );
}

function FinanceActions({ onScenario }: { onScenario: () => void }) {
  const { can } = useAuth();
  return (
    <div className="mb-5 flex flex-wrap gap-2" aria-label="Finance actions">
      {can("manage_financials") && <a href="#upload" className="btn btn-soft"><Upload size={15} aria-hidden="true" /> Upload Financial Documents</a>}
      {can("manage_financials") && <a href="#add-record" className="btn btn-soft"><FilePlus2 size={15} aria-hidden="true" /> Add Financial Record</a>}
      {can("run_agents") && <a href="#analyze" className="btn btn-soft"><Wand2 size={15} aria-hidden="true" /> Analyze Finances</a>}
      <button type="button" className="btn btn-primary" onClick={onScenario}><Calculator size={15} aria-hidden="true" /> Create Budget Scenario</button>
    </div>
  );
}

function FinanceBody() {
  const [scenario, setScenario] = useState(false);
  const { data, error, loading, reload } = useApi<FinanceDashboard>("/api/finance/dashboard");
  if (loading && !data) return <LoadingState rows={5} />;
  if (error) return <ErrorState message={error.message} onRetry={reload} />;
  if (!data) return null;
  const sources = [{ key: "donations", label: "Donations", color: SERIES_COLORS[0] }, { key: "events", label: "Events", color: SERIES_COLORS[1] },
    { key: "grants", label: "Grants", color: SERIES_COLORS[2] }].filter((s) => data.donation_trend.some((r) => (r as Record<string, number | string>)[s.key] as number > 0));
  const purposes = Object.entries(data.expense_ratios.by_purpose).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ label: PURPOSE[k] ?? k, value: v }));

  return (
    <>
      <FinanceActions onScenario={() => { setScenario(true); window.setTimeout(() => document.getElementById("scenario")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50); }} />
      <DemoNotice show={data.is_demo} />
      {scenario && <div className="mb-5"><BudgetScenario /></div>}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-5">
          <p className="flex items-center gap-2 text-sm text-muted"><CalendarRange size={15} className="text-royal" aria-hidden="true" />Basis: <b className="text-plum">{data.basis}</b></p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">{data.metrics.map((m) => <MetricCard key={m.key} m={m} />)}</div>
          <p className="text-xs text-muted">Available capacity is not authorization to spend; the board decides.</p>

          <Card title="Revenue and expenses by month" icon={<BarChart3 size={16} aria-hidden="true" />}>
            {data.monthly.length === 0 ? <p className="text-sm text-muted">No monthly records yet.</p> : (
              <BarChart caption="Recorded revenue and expenses by month" rows={data.monthly.map((m) => ({ label: month(m.period), values: { income: m.income, expense: m.expense } }))}
                series={[{ key: "income", label: "Revenue", color: SERIES_COLORS[0] }, { key: "expense", label: "Expenses", color: SERIES_COLORS[1] }]}
                footer={{ label: "Net", values: data.monthly.map((m) => money(m.net)) }} />)}
            <p className="mt-2 text-xs text-muted">Recorded revenue is not cash on hand. Net is revenue minus expenses for the month.</p>
          </Card>

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
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
              <div className="overflow-x-auto"><table className="w-full text-sm">
                <thead><tr className="text-left text-xs text-muted"><th className="py-1">Scenario</th><th className="py-1 text-right">Revenue</th><th className="py-1 text-right">Expenses</th><th className="py-1 text-right">Net</th><th className="py-1 text-right">vs. averages</th></tr></thead>
                <tbody>{data.scenarios.rows.map((r) => (
                  <tr key={r.scenario} className="border-t border-lavender/30"><td className="py-1.5 text-plum">{r.scenario}</td><td className="py-1.5 text-right tabular-nums">{money(r.revenue_usd)}</td>
                    <td className="py-1.5 text-right tabular-nums">{money(r.cost_usd)}</td><td className={`py-1.5 text-right font-semibold tabular-nums ${r.net_usd < 0 ? "text-danger" : "text-sage"}`}>{money(r.net_usd)}</td>
                    <td className="py-1.5 text-right tabular-nums">{r.vs_first_usd ? money(r.vs_first_usd) : "—"}</td></tr>))}</tbody>
              </table></div>
              <p className="mt-2 text-xs text-muted">{data.scenarios.basis} These show sensitivity, not expected results.</p>
            </Card>
          )}

          <Card title="Events: what they cost and raised" icon={<Landmark size={16} aria-hidden="true" />}>
            {data.past_events.length === 0 ? <p className="text-sm text-muted">No past events recorded in Our Legacy.</p> : (
              <div className="overflow-x-auto"><table className="w-full text-sm">
                <thead><tr className="text-left text-xs text-muted"><th className="py-1">Event</th><th className="py-1 text-right">Goal</th><th className="py-1 text-right">Raised</th><th className="py-1 text-right">Cost</th><th className="py-1 text-right">Net</th><th className="py-1 text-right">To programs</th></tr></thead>
                <tbody>{data.past_events.map((e) => (
                  <tr key={e.id} className="border-t border-lavender/30"><td className="py-1.5 text-plum">{e.name}<span className="block text-xs text-muted">{e.event_date ? formatDate(e.event_date) : ""}</span></td>
                    <td className="py-1.5 text-right tabular-nums">{money(e.fundraising_goal_usd)}</td><td className="py-1.5 text-right tabular-nums">{money(e.funds_raised_usd)}</td>
                    <td className="py-1.5 text-right tabular-nums">{money(e.total_cost_usd)}</td><td className="py-1.5 text-right tabular-nums">{money(e.net_usd)}</td>
                    <td className="py-1.5 text-right tabular-nums">{e.funds_directed_usd == null ? "Not recorded" : money(e.funds_directed_usd)}</td></tr>))}</tbody>
              </table></div>)}
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
          <div id="upload"><DocumentsPanel onChange={reload} /></div>
          <div id="add-record"><ManualEntryGate onSaved={reload} /></div>
          <div id="analyze"><RunLauncher title="Analyze finances" intent="financial_review" lockIntent submitLabel="Analyze Finances"
            request="Explain our financial position, our budget variances, and how much we could responsibly spend on an event." /></div>
          <RecordsPanel onChange={reload} />
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
      <PageHeader eyebrow="Financial Intelligence" title="Finances"
        subtitle="Computed from your records. Revenue is not cash, restricted gifts are not spendable, and figures read from documents wait for your review." />
      {can("view_financials") ? <FinanceBody /> : <RestrictedState area="Financial Intelligence" />}
    </>
  );
}
