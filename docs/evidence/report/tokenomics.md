# Tokenomics: measured from the app's logs

Generated 2026-10-26T02:18:33+00:00 by `python -m backend.scripts.export_report_evidence`. Source: app database (model_usage, agent_runs, agent_handoffs); prices from backend/app/ai/pricing.json (https://developers.openai.com/api/docs/pricing, retrieved 2026-10-24).

All costs are at OpenAI's list prices (standard tier) for the tokens each call actually used. Runs in synthetic mode used real models on labeled demo data, so their token counts and costs are real.

## Totals

| Runs | Model calls | Refused (never sent) | Input tokens | Cached input | Output tokens | Cost |
|---|---|---|---|---|---|---|
| 49 | 234 | 4 | 803,676 | 89,471 | 282,156 | $6.33 |

## By model

| | Calls | Input | Cached input | Output | Web searches | Cost |
|---|---|---|---|---|---|---|
| `gpt-6-astra` | 25 | 142,876 | 0 | 37,289 | 0 | $3.65 |
| `gpt-6.1-sol` | 111 | 371,724 | 61,909 | 171,880 | 0 | $2.50 |
| `gpt-6-luna` | 98 | 289,076 | 27,562 | 72,987 | 11 | $0.1763 |

## By agent

| | Calls | Input | Cached input | Output | Web searches | Cost |
|---|---|---|---|---|---|---|
| `orchestrator` | 61 | 222,860 | 0 | 60,882 | 0 | $3.78 |
| `fundraising_events` | 46 | 230,053 | 23,344 | 71,636 | 4 | $0.9617 |
| `event_intelligence` | 26 | 114,455 | 35,472 | 63,755 | 0 | $0.6501 |
| `financial_analysis` | 47 | 83,807 | 21,811 | 33,890 | 0 | $0.4252 |
| `mission_discovery` | 21 | 115,205 | 6,444 | 30,844 | 7 | $0.3895 |
| `partnerships_outreach` | 28 | 32,483 | 2,400 | 19,182 | 0 | $0.0993 |
| `donations_compliance` | 5 | 4,813 | 0 | 1,967 | 0 | $0.0184 |

## Cost per workflow (completed runs)

| Workflow | Runs | Median cost | Mean | Min–max | Median tokens in (cached) / out |
|---|---|---|---|---|---|
| `auto` | 6 | $0.2171 | $0.1757 | $0.0009–$0.3151 | 15,654 (0) / 6,786 |
| `document_extraction` | 1 | $0.0005 | $0.0005 | $0.0005–$0.0005 | 1,157 (0) / 678 |
| `donations_review` | 3 | $0.0006 | $0.0065 | $0.0005–$0.0184 | 1,584 (0) / 824 |
| `event_learning` | 3 | $0.0319 | $0.0381 | $0.0215–$0.0609 | 5,007 (0) / 3,267 |
| `financial_review` | 2 | $0.0232 | $0.0232 | $0.0112–$0.0352 | 7,021 (1,269) / 3,331 |
| `legacy_import` | 4 | $0.0006 | $0.0006 | $0.0004–$0.0008 | 1,493 (1,151) / 1,011 |
| `mission_discovery` | 3 | $0.0886 | $0.0860 | $0.0742–$0.0953 | 23,897 (1,681) / 8,403 |
| `partnership_outreach` | 4 | $0.1575 | $0.1526 | $0.0680–$0.2271 | 7,857 (0) / 5,223 |
| `plan_event` | 19 | $0.2366 | $0.2214 | $0.0089–$0.3468 | 27,236 (2,262) / 10,181 |

## Cost controls observed in the logs

- **Prompt caching:** 89,471 input tokens were billed at the cached rate, saving $0.1201 against the full input price.
- **Budget step-downs:** 8 calls ran on a cheaper model than their tier because the remaining budget was tight (each is recorded with the router's note).
- **Steps that ran in code, with no model call** (completed handoffs): `verification` × 42, `intake` × 33, `evaluate` × 13, `outreach_decision` × 8, `select` × 3, `finance` × 1.

## Monthly cost projection

> **ASSUMPTION:** runs per board member per month (typed in, not measured). Costs per run are the measured medians above.

| Workflow | Runs per user per month (assumed) | Median cost per run (measured) | Monthly cost per user |
|---|---|---|---|
| `plan_event` | 1 | $0.2366 | $0.2366 |
| `mission_discovery` | 2 | $0.0886 | $0.1771 |
| `partnership_outreach` | 1 | $0.1575 | $0.1575 |
| `financial_review` | 1 | $0.0232 | $0.0232 |
| `donations_review` | 1 | $0.0006 | $0.0006 |
| `legacy_import` | 2 | $0.0006 | $0.0011 |
| `event_learning` | 1 | $0.0319 | $0.0319 |

| Users | Monthly model cost |
|---|---|
| 1 | $0.6280 |
| 100 | $62.80 |
| 10,000 | $6,280.00 |

Model cost only: hosting, storage, and web-search fees beyond those already in the per-call costs are not included.
