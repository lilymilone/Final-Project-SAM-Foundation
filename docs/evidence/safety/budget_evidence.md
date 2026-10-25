# Budget evidence

Every paid call first reserves its worst-case cost (estimated input at 3 characters per token, the full output allowance, and padding for web search) against the workflow budget and the daily cap, under a lock. If the reservation does not fit, the call is never sent.

- **PASS** TEST D (mocked model): Excessive spending: workflow budget of $0.01. Expected: Paid calls stop before the limit; spend never exceeds it; run stopped with partial results and a budget event.
- **PASS** TEST D2 (mocked model): Excessive spending: 20 simultaneous calls. Expected: Exactly the calls that fit are reserved; the daily guard counts calls in flight.
- **PASS** TEST D3 (mocked model): Excessive spending: raising a limit past its hard cap. Expected: Limits clamp to the hard caps.

## Live: run #25 with a $0.02 workflow budget (real models)

Expected a stop; the budget-aware router instead stepped every task down to gpt-6-luna and the whole workflow fit, so the stop path was not exercised. Recorded as FAIL against the expectation even though spending stayed under the cap.

Status **completed**: None

Spent $0.00894 of $0.02.

| Agent | Task | Model | Status | Input | Cached | Output | Cost |
|---|---|---|---|---|---|---|---|
| event_intelligence | Synthesize lessons from events and reflections | gpt-6-luna | ok | 4105 | 0 | 3090 | $0.00206 |
| fundraising_events | Shortlist venues and fundraising strategy | gpt-6-luna | ok | 4348 | 0 | 2166 | $0.00163 |
| financial_analysis | Explain computed financial results | gpt-6-luna | ok | 1810 | 0 | 570 | $0.00051 |
| fundraising_events | Shortlist venues and fundraising strategy | gpt-6-luna | ok | 6232 | 1062 | 1631 | $0.00147 |
| financial_analysis | Explain computed financial results | gpt-6-luna | ok | 1753 | 0 | 773 | $0.00061 |
| partnerships_outreach | Short venue-inquiry drafts | gpt-6-luna | ok | 1016 | 0 | 581 | $0.00039 |
| orchestrator | Board-ready recommendation with trade-offs | gpt-6-luna | ok | 7972 | 0 | 2547 | $0.00227 |

Budget events:

- Budget limit reached: event_intelligence: the intermediate tier could not fit the remaining budget, so gpt-6-luna was used instead. w) under Auto → Sol (intermediate) tier. Estimated $0.0690 for gpt-6.1-sol exceeds the remaining budget of $0.0200; stepped down to Luna (fast). Estimated $0.0034 fits the remaining budget of $0.0200.
- Budget limit reached: fundraising_events: the intermediate tier could not fit the remaining budget, so gpt-6-luna was used instead. m) under Auto → Sol (intermediate) tier. Estimated $0.0711 for gpt-6.1-sol exceeds the remaining budget of $0.0179; stepped down to Luna (fast). Estimated $0.0036 fits the remaining budget of $0.0179.
- Budget limit reached: financial_analysis: the intermediate tier could not fit the remaining budget, so gpt-6-luna was used instead. h) under Auto → Sol (intermediate) tier. Estimated $0.0680 for gpt-6.1-sol exceeds the remaining budget of $0.0163; stepped down to Luna (fast). Estimated $0.0034 fits the remaining budget of $0.0163.
- Budget limit reached: fundraising_events: the intermediate tier could not fit the remaining budget, so gpt-6-luna was used instead. m) under Auto → Sol (intermediate) tier. Estimated $0.0753 for gpt-6.1-sol exceeds the remaining budget of $0.0158; stepped down to Luna (fast). Estimated $0.0038 fits the remaining budget of $0.0158.
- Budget limit reached: financial_analysis: the intermediate tier could not fit the remaining budget, so gpt-6-luna was used instead. h) under Auto → Sol (intermediate) tier. Estimated $0.0680 for gpt-6.1-sol exceeds the remaining budget of $0.0143; stepped down to Luna (fast). Estimated $0.0034 fits the remaining budget of $0.0143.
- Budget limit reached: orchestrator: the advanced tier could not fit the remaining budget, so gpt-6-luna was used instead. 133; stepped down to Sol (intermediate). Estimated $0.0616 for gpt-6.1-sol exceeds the remaining budget of $0.0133; stepped down to Luna (fast). Estimated $0.0031 fits the remaining budget of $0.0133.

Checks:

- **FAIL** The workflow stopped at its budget: status completed: None
- **PASS** Spending never exceeded the limit: $0.00894 of $0.02 over 7 paid call(s)
- **FAIL** No recommendation was fabricated after the stop: a recommendation exists
- **PASS** A budget security event was recorded: 6 budget event(s)

## Live: run #28 with a $0.01 workflow budget (real models)

Live venue research reserves web-search padding, so the venue step could not fit and the workflow stopped before sending it.

Status **stopped**: BudgetExceededError: Stopped: the next call could cost up to $0.0250, more than the $0.0085 left in this workflow's $0.01 budget.

Spent $0.00147 of $0.01.

| Agent | Task | Model | Status | Input | Cached | Output | Cost |
|---|---|---|---|---|---|---|---|
| event_intelligence | Synthesize lessons from events and reflections | gpt-6-luna | ok | 4105 | 4102 | 2865 | $0.00147 |
| fundraising_events | Web search: venue candidates | gpt-6-luna | refused | 0 | 0 | 0 | $0.00000 |

Budget events:

- Model stepped down to fit the budget: event_intelligence: the intermediate tier could not fit the remaining budget, so gpt-6-luna was used instead. w) under Auto → Sol (intermediate) tier. Estimated $0.0690 for gpt-6.1-sol exceeds the remaining budget of $0.0100; stepped down to Luna (fast). Estimated $0.0034 fits the remaining budget of $0.0100.
- Budget limit reached: Workflow stopped: BudgetExceededError: Stopped: the next call could cost up to $0.0250, more than the $0.0085 left in this workflow's $0.01 budget.

Checks:

- **PASS** Real paid calls ran before the limit: 1 paid call(s)
- **PASS** The workflow stopped at its budget: status stopped: BudgetExceededError: Stopped: the next call could cost up to $0.0250, more than the $0.0085 left in this workflow's $0.01 budget.
- **PASS** Spending never exceeded the limit: $0.00147 of $0.01; 1 call(s) refused before sending
- **PASS** No recommendation was fabricated; finished steps kept as partial: recommendation is None; partial result: {"stopped": true, "verified_partial_steps": 2, "message": "The workflow stopped before it finished: BudgetExceededError: Stopped: the next call could cost up to $0.0250, more than the $0.0085 left in 
- **PASS** A budget stop was logged: Workflow stopped: BudgetExceededError: Stopped: the next call could cost up to $0.0250, more than the $0.0085 left in th
