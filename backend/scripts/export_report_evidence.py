"""Export tokenomics and spending-limit evidence for the final report from the app's own logs.

    python -m backend.scripts.export_report_evidence

Writes docs/evidence/report/:
  tokenomics.{json,md}   every recorded model call, grouped by model, agent, and workflow type; caching savings;
                         routing step-downs; steps that ran in code; monthly cost projections
  spending_limits.md     runs the per-workflow and daily limits stopped, with the refused calls that were never sent

Every number is read from the model_usage, agent_runs, agent_handoffs, and security_events tables. The only typed-in
values are the monthly usage ASSUMPTIONS below, which are labeled as assumptions wherever they appear.
No prompts, keys, page text, or donor details are exported.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select

from backend.app.core.config import get_settings
from backend.app.core.env import REPO_ROOT
from backend.app.db.database import Database
from backend.app.db.models import AgentHandoff, AgentRun, ModelUsage, SecurityEvent

PRICES = json.loads((REPO_ROOT / "backend" / "app" / "ai" / "pricing.json").read_text())

# ASSUMPTIONS (not measurements): how often one board member runs each workflow in a month.
MONTHLY_RUNS_PER_USER = {
    "plan_event": 1,             # plan or re-plan one fundraiser
    "mission_discovery": 2,      # two research questions
    "partnership_outreach": 1,   # one partnership round with drafts and a packet
    "financial_review": 1,       # one financial review
    "donations_review": 1,       # one donations and compliance review
    "legacy_import": 2,          # record two past events
    "event_learning": 1,         # one analysis of past events
}
USERS = (1, 100, 10_000)
OK = ("completed", "completed_with_warnings")


def _money(v: float) -> str:
    return f"${v:,.4f}" if v < 1 else f"${v:,.2f}"


def _saved_by_cache(model: str, cached: int) -> float:
    p = (PRICES["models"].get(model) or {}).get("short")
    return cached * (p["input"] - p["cached_input"]) / 1e6 if p and cached else 0.0


def collect(db: Database) -> dict:
    with db.session() as s:
        runs = {r.id: r for r in s.scalars(select(AgentRun))}
        calls = s.scalars(select(ModelUsage).order_by(ModelUsage.id)).all()
        handoffs = s.scalars(select(AgentHandoff)).all()
        events = s.scalars(select(SecurityEvent).order_by(SecurityEvent.id)).all()
        calls = [{k: getattr(c, k) for k in ("run_id", "handoff_id", "agent", "task", "requested_tier", "selected_model", "model_used",
                                             "substitution_note", "input_tokens", "cached_input_tokens", "output_tokens",
                                             "estimated_cost_usd", "status", "web_search_calls", "latency_ms")} for c in calls]
        runs = {i: {"id": r.id, "workflow_type": r.workflow_type, "status": r.status, "research_mode": r.research_mode,
                    "spent_usd": r.spent_usd or 0.0, "model_calls": r.model_calls, "duration_ms": r.duration_ms, "error": r.error,
                    "request": (r.request_text or "")[:140], "started_at": r.started_at.isoformat()} for i, r in runs.items()}
        handoffs = [{"id": h.id, "run_id": h.run_id, "step_key": h.step_key, "to_agent": h.to_agent, "status": h.status} for h in handoffs]
        events = [{"id": e.id, "run_id": e.run_id, "category": e.category, "detail": e.detail, "created_at": e.created_at.isoformat()}
                  for e in events]
    return {"runs": runs, "calls": calls, "handoffs": handoffs, "events": events}


def group(calls: list[dict], key) -> list[dict]:
    g: dict = defaultdict(lambda: {"calls": 0, "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
                                   "web_search_calls": 0})
    for c in calls:
        if c["status"] != "ok":
            continue
        row = g[key(c)]
        row["calls"] += 1
        for k in ("input_tokens", "cached_input_tokens", "output_tokens", "web_search_calls"):
            row[k] += c[k] or 0
        row["cost_usd"] += c["estimated_cost_usd"] or 0.0
    return [{"key": k, **v, "cost_usd": round(v["cost_usd"], 6)} for k, v in sorted(g.items(), key=lambda kv: -kv[1]["cost_usd"])]


def tokenomics(data: dict) -> dict:
    runs, calls = data["runs"], data["calls"]
    ok_calls = [c for c in calls if c["status"] == "ok"]
    per_workflow = []
    for wf in sorted({r["workflow_type"] for r in runs.values()}):
        done = [r for r in runs.values() if r["workflow_type"] == wf and r["status"] in OK and r["spent_usd"] > 0]
        if not done:
            continue
        costs = [r["spent_usd"] for r in done]
        tok = defaultdict(list)
        for r in done:
            rc = [c for c in ok_calls if c["run_id"] == r["id"]]
            tok["in"].append(sum(c["input_tokens"] or 0 for c in rc))
            tok["cached"].append(sum(c["cached_input_tokens"] or 0 for c in rc))
            tok["out"].append(sum(c["output_tokens"] or 0 for c in rc))
        per_workflow.append({"workflow_type": wf, "completed_runs": len(done), "run_ids": sorted(r["id"] for r in done),
                             "median_cost_usd": round(statistics.median(costs), 6), "mean_cost_usd": round(statistics.mean(costs), 6),
                             "min_cost_usd": round(min(costs), 6), "max_cost_usd": round(max(costs), 6),
                             "median_input_tokens": int(statistics.median(tok["in"])),
                             "median_cached_input_tokens": int(statistics.median(tok["cached"])),
                             "median_output_tokens": int(statistics.median(tok["out"]))})
    medians = {w["workflow_type"]: w["median_cost_usd"] for w in per_workflow}
    lines = [{"workflow_type": wf, "runs_per_user_per_month": n, "median_cost_usd": medians.get(wf),
              "monthly_cost_per_user_usd": round(n * medians[wf], 4) if wf in medians else None}
             for wf, n in MONTHLY_RUNS_PER_USER.items()]
    per_user = sum(x["monthly_cost_per_user_usd"] or 0 for x in lines)
    tiers = {"fast": "gpt-6-luna", "intermediate": "gpt-6.1-sol", "advanced": "gpt-6-astra"}
    stepped = [c for c in calls if c["status"] == "ok" and c["requested_tier"] in tiers and c["selected_model"] != tiers[c["requested_tier"]]]
    cached = sum(c["cached_input_tokens"] or 0 for c in ok_calls)
    saved = sum(_saved_by_cache(c["selected_model"], c["cached_input_tokens"] or 0) for c in ok_calls)
    with_model = {c["handoff_id"] for c in calls if c["handoff_id"]}
    code_steps = defaultdict(int)
    for h in data["handoffs"]:
        if h["id"] not in with_model and h["status"] == "completed":
            code_steps[h["step_key"].split("_revision_")[0]] += 1
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "app database (model_usage, agent_runs, agent_handoffs); prices from backend/app/ai/pricing.json "
                  f"({PRICES['source']}, retrieved {PRICES['retrieved_on']})",
        "totals": {"runs": len(runs), "model_calls_ok": len(ok_calls), "refused_calls": sum(c["status"] == "refused" for c in calls),
                   "input_tokens": sum(c["input_tokens"] or 0 for c in ok_calls), "cached_input_tokens": cached,
                   "output_tokens": sum(c["output_tokens"] or 0 for c in ok_calls),
                   "cost_usd": round(sum(c["estimated_cost_usd"] or 0 for c in ok_calls), 4)},
        "by_model": group(calls, lambda c: c["selected_model"]),
        "by_agent": group(calls, lambda c: c["agent"]),
        "by_workflow": per_workflow,
        "runs_by_research_mode": {m: sum(r["research_mode"] == m for r in runs.values()) for m in sorted({r["research_mode"] for r in runs.values()})},
        "optimization": {
            "cached_input_tokens": cached, "saved_by_caching_usd": round(saved, 4),
            "budget_stepdowns": [{"run_id": c["run_id"], "agent": c["agent"], "requested_tier": c["requested_tier"], "model": c["selected_model"],
                                  "note": c["substitution_note"]} for c in stepped],
            "steps_run_in_code_without_a_model": dict(sorted(code_steps.items(), key=lambda kv: -kv[1])),
        },
        "monthly_projection": {"ASSUMPTION": "runs per board member per month (typed in, not measured)", "lines": lines,
                               "per_user_usd": round(per_user, 4),
                               "by_users": {str(u): round(per_user * u, 4) for u in USERS}},
    }


def tokenomics_md(t: dict) -> str:
    out = ["# Tokenomics: measured from the app's logs", "",
           f"Generated {t['generated_at']} by `python -m backend.scripts.export_report_evidence`. Source: {t['source']}.", "",
           "All costs are at OpenAI's list prices (standard tier) for the tokens each call actually used. Runs in synthetic mode used real "
           "models on labeled demo data, so their token counts and costs are real.", "",
           "## Totals", "", "| Runs | Model calls | Refused (never sent) | Input tokens | Cached input | Output tokens | Cost |", "|---|---|---|---|---|---|---|"]
    x = t["totals"]
    out.append(f"| {x['runs']} | {x['model_calls_ok']} | {x['refused_calls']} | {x['input_tokens']:,} | {x['cached_input_tokens']:,} | "
               f"{x['output_tokens']:,} | {_money(x['cost_usd'])} |")
    for title, rows in (("By model", t["by_model"]), ("By agent", t["by_agent"])):
        out += ["", f"## {title}", "", "| | Calls | Input | Cached input | Output | Web searches | Cost |", "|---|---|---|---|---|---|---|"]
        out += [f"| `{r['key']}` | {r['calls']} | {r['input_tokens']:,} | {r['cached_input_tokens']:,} | {r['output_tokens']:,} | "
                f"{r['web_search_calls']} | {_money(r['cost_usd'])} |" for r in rows]
    out += ["", "## Cost per workflow (completed runs)", "",
            "| Workflow | Runs | Median cost | Mean | Min–max | Median tokens in (cached) / out |", "|---|---|---|---|---|---|"]
    out += [f"| `{w['workflow_type']}` | {w['completed_runs']} | {_money(w['median_cost_usd'])} | {_money(w['mean_cost_usd'])} | "
            f"{_money(w['min_cost_usd'])}–{_money(w['max_cost_usd'])} | {w['median_input_tokens']:,} ({w['median_cached_input_tokens']:,}) / "
            f"{w['median_output_tokens']:,} |" for w in t["by_workflow"]]
    o = t["optimization"]
    out += ["", "## Cost controls observed in the logs", "",
            f"- **Prompt caching:** {o['cached_input_tokens']:,} input tokens were billed at the cached rate, saving {_money(o['saved_by_caching_usd'])} "
            "against the full input price.",
            f"- **Budget step-downs:** {len(o['budget_stepdowns'])} calls ran on a cheaper model than their tier because the remaining budget "
            "was tight (each is recorded with the router's note).",
            "- **Steps that ran in code, with no model call** (completed handoffs): "
            + ", ".join(f"`{k}` × {v}" for k, v in o["steps_run_in_code_without_a_model"].items()) + ".",
            "", "## Monthly cost projection", "",
            f"> **ASSUMPTION:** {t['monthly_projection']['ASSUMPTION']}. Costs per run are the measured medians above.", "",
            "| Workflow | Runs per user per month (assumed) | Median cost per run (measured) | Monthly cost per user |", "|---|---|---|---|"]
    out += [f"| `{x['workflow_type']}` | {x['runs_per_user_per_month']} | {_money(x['median_cost_usd']) if x['median_cost_usd'] is not None else 'no completed run'} | "
            f"{_money(x['monthly_cost_per_user_usd']) if x['monthly_cost_per_user_usd'] is not None else '—'} |" for x in t["monthly_projection"]["lines"]]
    m = t["monthly_projection"]
    out += ["", "| Users | Monthly model cost |", "|---|---|"] + [f"| {int(u):,} | {_money(v)} |" for u, v in m["by_users"].items()]
    out += ["", "Model cost only: hosting, storage, and web-search fees beyond those already in the per-call costs are not included."]
    return "\n".join(out) + "\n"


def spending_md(data: dict) -> str:
    runs, calls = data["runs"], data["calls"]
    stops = [e for e in data["events"] if e["category"] == "budget_limit"]
    changes = [e for e in data["events"] if e["category"] == "limit_changed"]
    out = ["# Spending limits: enforced, from the logs", "",
           "Each paid call first reserves its worst-case cost against the workflow budget and the daily cap. When it does not fit, the call is "
           "**never sent**: it is recorded with status `refused` and no cost, a `budget_limit` security event is written, and the run stops.", ""]
    for e in stops:
        r = runs.get(e["run_id"]) or {}
        rc = [c for c in calls if c["run_id"] == e["run_id"]]
        out += [f"## Run #{e['run_id']} ({r.get('workflow_type')}, {r.get('research_mode')}): {r.get('status')}", "",
                f"- Security event #{e['id']} at {e['created_at']}: {e['detail']}",
                f"- Spent before the stop: {_money(r.get('spent_usd') or 0)}", "",
                "| # | Agent | Task | Model | Status | Cost |", "|---|---|---|---|---|---|"]
        out += [f"| {i} | {c['agent']} | {c['task']} | `{c['selected_model']}` | **{c['status']}** | "
                f"{_money(c['estimated_cost_usd']) if c['estimated_cost_usd'] is not None else 'not sent'} |" for i, c in enumerate(rc, 1)]
        out.append("")
    if changes:
        out += ["## Limit changes (chair only, logged)", ""] + [f"- {e['created_at']}: {e['detail']}" for e in changes] + [""]
    return "\n".join(out)


def main() -> None:
    db = Database(get_settings().database_path)
    data = collect(db)
    out = REPO_ROOT / "docs" / "evidence" / "report"
    out.mkdir(parents=True, exist_ok=True)
    t = tokenomics(data)
    (out / "tokenomics.json").write_text(json.dumps(t, indent=2), encoding="utf-8")
    (out / "tokenomics.md").write_text(tokenomics_md(t), encoding="utf-8")
    (out / "spending_limits.md").write_text(spending_md(data), encoding="utf-8")
    print(f"Wrote {out}: {t['totals']['model_calls_ok']} model calls, {_money(t['totals']['cost_usd'])} total; "
          f"projection {_money(t['monthly_projection']['per_user_usd'])} per user per month (assumed usage).")


if __name__ == "__main__":
    main()
