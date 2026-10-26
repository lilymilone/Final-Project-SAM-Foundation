import { Calculator, CheckCircle2, CircleSlash, Save, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Affordability, EventModel, ModelCheck } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { money } from "./agents";

// ── Financial model with editable assumptions ─────────────────────────────────

const KIND_STYLE: Record<string, string> = {
  published: "bg-[#e3f1e8] text-sage", board: "bg-plum text-white", history: "bg-lilac text-royal", lesson: "bg-blush text-plum",
  placeholder: "bg-[#fbf1e3] text-amber", hypothetical: "bg-[#fbeef3] text-danger", missing: "bg-white text-muted ring-1 ring-lavender/50",
};
const LABELS: Record<string, string> = {
  attendance: "Expected attendees", ticket_price_usd: "Ticket price", venue_rental_usd: "Venue rental", catering_per_guest_usd: "Catering per guest",
  catering_minimum_usd: "Catering minimum", entertainment_usd: "Entertainment", marketing_usd: "Marketing", staffing_usd: "Staffing",
  insurance_usd: "Insurance and permits", misc_usd: "Miscellaneous", contingency_pct: "Contingency (0–0.6)",
  sponsorship_usd: "Sponsorship expected (pledged or prospective)", sponsorship_confirmed_usd: "Sponsorship confirmed (signed or received)",
  donations_per_attendee_usd: "Donations per attendee", other_revenue_usd: "Other documented revenue", deposit_pct: "Deposit share (0–1)",
};

function CheckLine({ c }: { c: ModelCheck }) {
  const Icon = c.passed === true ? CheckCircle2 : c.passed === false ? XCircle : CircleSlash;
  return (
    <li className="flex gap-2 text-sm">
      <Icon size={16} className={`mt-0.5 shrink-0 ${c.passed === true ? "text-sage" : c.passed === false ? "text-danger" : "text-amber"}`}
        aria-label={c.passed === true ? "passed" : c.passed === false ? "failed" : "unknown"} />
      <span><b className="text-plum">{c.name}.</b> <span className="text-muted">{c.detail}</span></span>
    </li>
  );
}

export function FinancialModelEditor({ model, affordability, planId, minContingency }: {
  model: EventModel; affordability?: Affordability; planId: number | null; minContingency?: number | null;
}) {
  const { can } = useAuth();
  const [values, setValues] = useState<Record<string, string>>({});
  const [current, setCurrent] = useState<{ model: EventModel; affordability?: Affordability }>({ model, affordability });
  const [edited, setEdited] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    setValues(Object.fromEntries(Object.entries(model.assumptions).map(([k, a]) => [k, a.value == null ? "" : String(a.value)])));
    setCurrent({ model, affordability });
    setEdited(false);
  }, [model, affordability]);

  const payload = () => Object.fromEntries(Object.entries(model.assumptions).map(([k, a]) => {
    const raw = values[k];
    const changed = raw !== (a.value == null ? "" : String(a.value));
    return [k, { value: raw === "" ? null : Number(raw), kind: changed ? "board" : a.kind, basis: changed ? "Edited by the board" : a.basis }];
  }));

  async function recalc() {
    setBusy(true);
    setMessage(null);
    try {
      const res = await api<{ model: EventModel; affordability: Affordability }>("/api/event-model/calculate", {
        json: { assumptions: payload(), max_budget_usd: model.max_budget_usd, target_usd: model.target_usd, min_contingency_pct: minContingency ?? null },
      });
      setCurrent(res);
      setEdited(true);
    } catch (e) {
      setMessage({ ok: false, text: e instanceof Error ? e.message : "Could not recalculate." });
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    if (!planId) return;
    const changed = Object.fromEntries(Object.entries(payload()).filter(([, a]) => a.kind === "board" && a.basis === "Edited by the board").map(([k, a]) => [k, a.value]));
    try {
      await api(`/api/events/${planId}/assumptions`, { method: "PUT", json: { assumptions: changed } });
      setMessage({ ok: true, text: "Saved to the plan. Generate the strategy again to apply them through every agent." });
    } catch (e) {
      setMessage({ ok: false, text: e instanceof Error ? e.message : "Could not save." });
    }
  }

  const m = current.model;
  const sc = m.scenarios;
  const checks = current.affordability?.checks ?? m.checks;
  return (
    <div className="space-y-5">
      {edited && <p className="rounded-xl bg-lilac/60 px-3 py-2 text-xs text-plum">Showing your recalculated model. Figures are computed in Python from the assumptions below; no AI is involved.</p>}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div>
          <p className="label">Costs</p>
          <table className="w-full text-left text-sm"><tbody>
            {m.lines.map((l) => (
              <tr key={l.category} className="border-t border-lavender/25 align-top"><td className="py-1.5 pr-2">{l.category}<span className="block text-[0.7rem] text-muted">{l.basis}</span></td>
                <td className="py-1.5 text-right">{money(l.amount_usd)}</td></tr>))}
            <tr className="border-t border-lavender/25"><td className="py-1.5">Contingency ({Math.round(m.contingency_pct * 100)}%)</td><td className="py-1.5 text-right">{money(m.contingency_usd)}</td></tr>
            <tr className="border-t-2 border-plum/30 font-semibold text-plum"><td className="py-1.5">Projected cost</td><td className="py-1.5 text-right">{money(m.total_cost_usd)}</td></tr>
            <tr><td className="py-1 text-xs text-muted">Upfront cash before the event</td><td className="py-1 text-right text-xs text-muted">{money(m.upfront_cash_usd)}</td></tr>
          </tbody></table>
        </div>
        <div>
          <p className="label">Revenue and net by scenario</p>
          <div className="-mx-2 overflow-x-auto">
            <table className="w-full min-w-[380px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-muted"><tr><th className="px-2 py-1"></th><th className="px-2">Conservative</th><th className="px-2">Base</th><th className="px-2">Optimistic</th></tr></thead>
              <tbody>
                {([["Attendance", "attendance"], ["Tickets", "ticket_revenue_usd"], ["Sponsorship", "sponsorship_revenue_usd"], ["Donations", "donations_usd"],
                   ["Other documented", "other_revenue_usd"], ["Revenue", "total_revenue_usd"], ["Net proceeds", "net_usd"], ["vs. target", "vs_target_usd"]] as const).map(([label, key]) => (
                  <tr key={key} className={`border-t border-lavender/25 ${key === "net_usd" ? "font-semibold text-plum" : ""}`}>
                    <td className="px-2 py-1.5 text-muted">{label}</td>
                    {(["conservative", "base", "optimistic"] as const).map((n) => {
                      const v = sc[n][key];
                      return <td key={n} className={`px-2 py-1.5 ${typeof v === "number" && v < 0 ? "text-danger" : ""}`}>{key === "attendance" ? v : v == null ? <span className="text-muted">incomplete</span> : money(v as number)}</td>;
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-muted">Break-even attendance: <b className="text-plum">{m.break_even_attendance ?? "—"}</b>{m.break_even_note ? ` (${m.break_even_note})` : ""}
            {m.break_even_confirmed_only != null && m.break_even_confirmed_only !== m.break_even_attendance ? <> · <b className="text-plum">{m.break_even_confirmed_only}</b> if no unconfirmed sponsorship arrives</> : null}.
            {" "}Scenarios: {Object.entries(m.scenario_definitions).map(([k, v]) => `${k} = ${v}`).join("; ")}. Pledged sponsorship is never counted as guaranteed.</p>
          <FinanceTerms />
        </div>
      </div>

      <div><p className="label">Checks</p><ul className="space-y-1.5">{checks.map((c) => <CheckLine key={c.name} c={c} />)}</ul>
        {current.affordability && <p className="mt-2 text-xs text-muted">{current.affordability.cash_note}</p>}</div>

      {can("view_financials") && (
        <details className="rounded-2xl border border-lavender/40 bg-ivory/60 p-4" open={edited}>
          <summary className="cursor-pointer font-semibold text-plum"><Calculator size={15} className="mr-1 inline" aria-hidden="true" /> Change assumptions and recalculate</summary>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(model.assumptions).map(([k, a]) => {
              const changed = (values[k] ?? "") !== (a.value == null ? "" : String(a.value));
              const kind = changed ? "board" : a.kind;
              return (
              <label key={k} className="block">
                <span className="mb-1 flex items-center justify-between gap-2 text-xs font-semibold text-plum">{LABELS[k] ?? k}
                  <span className={`rounded-full px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wide ${KIND_STYLE[kind] ?? ""}`} title={a.basis}>{changed ? "edited" : a.kind}</span></span>
                <input type="number" step="any" min={0} className="field !py-1.5 text-sm" value={values[k] ?? ""} placeholder="missing"
                  onChange={(e) => setValues((s) => ({ ...s, [k]: e.target.value }))} aria-describedby={`basis-${k}`} />
                <span id={`basis-${k}`} className="mt-0.5 block text-[0.65rem] leading-tight text-muted">{changed ? `Edited by you (was ${a.value ?? "missing"}: ${a.basis})` : a.basis}</span>
              </label>
              );
            })}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button className="btn btn-primary text-sm" onClick={recalc} disabled={busy}><Calculator size={14} aria-hidden="true" /> {busy ? "Calculating…" : "Recalculate"}</button>
            {planId && can("manage_events") && edited && <button className="btn btn-soft text-sm" onClick={save}><Save size={14} aria-hidden="true" /> Save assumptions to the plan</button>}
          </div>
          {message && <p role={message.ok ? "status" : "alert"} className={`mt-2 text-sm ${message.ok ? "text-sage" : "text-danger"}`}>{message.text}</p>}
        </details>
      )}
    </div>
  );
}


/** Plain-English definitions for board members without accounting training. */
export function FinanceTerms() {
  return (
    <details className="mt-2 rounded-xl bg-lilac/40 px-3 py-2 text-xs text-ink/85">
      <summary className="cursor-pointer font-semibold text-royal">What these terms mean</summary>
      <dl className="mt-1 space-y-1">
        <div><dt className="inline font-semibold text-plum">Net proceeds: </dt><dd className="inline">what is left for the mission after the event's costs are paid (revenue minus costs).</dd></div>
        <div><dt className="inline font-semibold text-plum">Break-even attendance: </dt><dd className="inline">the number of guests needed for revenue to cover costs. Fewer guests means the event loses money.</dd></div>
        <div><dt className="inline font-semibold text-plum">Restricted funds: </dt><dd className="inline">gifts a donor limited to a purpose (such as research). They can't pay for an event.</dd></div>
        <div><dt className="inline font-semibold text-plum">Planning budget: </dt><dd className="inline">the limit the board authorizes for this event. Available capacity in the books is not an authorization.</dd></div>
        <div><dt className="inline font-semibold text-plum">Financial uncertainty: </dt><dd className="inline">placeholder costs, quotes not yet received, unconfirmed sponsorship, and attendance that may fall short. The conservative scenario shows a cautious case.</dd></div>
      </dl>
    </details>
  );
}
