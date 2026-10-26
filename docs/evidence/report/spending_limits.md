# Spending limits: enforced, from the logs

Each paid call first reserves its worst-case cost against the workflow budget and the daily cap. When it does not fit, the call is **never sent**: it is recorded with status `refused` and no cost, a `budget_limit` security event is written, and the run stops.

## Run #28 (plan_event, live): stopped

- Security event #12 at 2026-10-25T11:00:13.743251: Workflow stopped: BudgetExceededError: Stopped: the next call could cost up to $0.0250, more than the $0.0085 left in this workflow's $0.01 budget.
- Spent before the stop: $0.0015

| # | Agent | Task | Model | Status | Cost |
|---|---|---|---|---|---|
| 1 | event_intelligence | Synthesize lessons from events and reflections | `gpt-6-luna` | **ok** | $0.0015 |
| 2 | fundraising_events | Web search: venue candidates | `gpt-6-luna` | **refused** | not sent |

## Run #41 (mission_discovery, live): stopped

- Security event #19 at 2026-10-25T22:40:00.707764: Workflow stopped: Stopped: the daily AI budget of $5.00 would be exceeded (spent $4.8916, in flight $0.0000).
- Spent before the stop: $0.0118

| # | Agent | Task | Model | Status | Cost |
|---|---|---|---|---|---|
| 1 | mission_discovery | Understand the research request (extraction) | `gpt-6-luna` | **ok** | $0.0001 |
| 2 | mission_discovery | Web search: mission-aligned opportunities | `gpt-6-luna` | **ok** | $0.0118 |
| 3 | mission_discovery | Compare sources and synthesize mission alignment | `gpt-6.1-sol` | **refused** | not sent |

## Run #42 (mission_discovery, synthetic): stopped

- Security event #21 at 2026-10-25T22:40:06.638452: Workflow stopped: Stopped: the daily AI budget of $5.00 would be exceeded (spent $4.8916, in flight $0.0000).
- Spent before the stop: $0.0001

| # | Agent | Task | Model | Status | Cost |
|---|---|---|---|---|---|
| 1 | mission_discovery | Understand the research request (extraction) | `gpt-6-luna` | **ok** | $0.0001 |
| 2 | mission_discovery | Compare sources and synthesize mission alignment | `gpt-6.1-sol` | **refused** | not sent |

## Limit changes (chair only, logged)

- 2026-10-25T22:59:28.126451: Daily AI spending limit (USD): 5.0 → 10.0
- 2026-10-25T23:07:16.474558: Daily AI spending limit (USD): 10.0 → 5.0
- 2026-10-25T23:41:39.722134: Daily AI spending limit (USD): 5.0 → 10.0
- 2026-10-25T23:44:24.601538: Daily AI spending limit (USD): 10.0 → 5.0
