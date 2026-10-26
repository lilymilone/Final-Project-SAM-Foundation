# Interface acceptance tests (board-member view)

Run on 2026-10-26 with headless Chrome against the real backend, signed in as the demo Board Chair. Every task was done through the interface.

The one paid step is the event plan, which used the **controlled demo**: real models on labeled synthetic Manhattan venues.

- Run #46: completed, synthetic research, $0.3468, 8 model calls, 206 s.
- Models: gpt-6-astra × 1 ($0.1996), gpt-6-luna × 2 ($0.0006), gpt-6.1-sol × 5 ($0.1466).
- Steps (as the backend recorded them and the live view showed them): intake → lessons → venues → finance → evaluate → venues_revision_1 → finance_revision_1 → evaluate_revision_1 → outreach_decision → outreach → recommendation → verification.

## The ten tasks

| # | Task | Result | What was checked |
|---|---|---|---|
| 1 | Log in | PASS | Hello, Tauhid |
| 2 | Create an event plan | PASS | run #46 in 207 s; live steps seen while running: 1; 12 steps |
| 3 | View the researched venues | PASS | packet #46; venue mentions 12 |
| 4 | Inspect the financial analysis | PASS | cost table, scenarios, and checks shown |
| 5 | Review and edit an automatically generated venue inquiry | PASS | draft #63: subject saved and reloaded |
| 6 | Save a charitable opportunity | PASS | saved “Manhattan Chamber of Commerce”; it appears under Saved opportunities |
| 7 | Review a past event | PASS | Butterfly Benefit Dinner (sample) |
| 8 | View an Event Intelligence recommendation | PASS | event page lessons + the new plan's “What We Learned” |
| 9 | Enter a donation record | PASS | 1 matching row(s) after saving |
| 10 | View agent activity and token usage | PASS | totals on Agent Activity; run #46 tokens and cost |

Task 6 first saved the Manhattan Chamber of Commerce, which is a business network, not a charity. That save was undone in the UI, and Columbia Center for Eating Disorders was saved instead; it appears under *Saved opportunities* on the dashboard.

No page errors occurred during the run.

## Free controls clicked on every page

33 of 33 passed. These are the controls that cost nothing and change nothing important (filters, panels, links, and the budget calculator).

| Control | Result | Detail |
|---|---|---|
| Overview quick action: Plan an Event | PASS | /events |
| Overview quick action: Find a Cause | PASS | /mission |
| Overview quick action: Analyze Finances | PASS | /finance#analyze |
| Overview quick action: Review Outreach Drafts | PASS | /partnerships#drafts |
| Overview quick action: Add a Past Event | PASS | /legacy?add=1 |
| Overview quick action: Review Agent Activity | PASS | /activity |
| Overview: open a planned event in Event Studio | PASS | Spring raffle in Manhattan (synthetic test plan) |
| Overview: open a draft in the review center | PASS | /partnerships#draft-62 |
| Overview: open a completed workflow | PASS | /activity/runs/45 |
| Mission: type filter | PASS | 10 -> 5 |
| Mission: fit filter | PASS | 10 shown |
| Mission: text filter | PASS | 2 |
| Mission: Details expands a card | PASS |  |
| Mission: Show all | PASS | 10 -> 31 |
| Mission: Saved tab loads | PASS |  |
| Finance: Upload Financial Documents goes to its section | PASS | top 24 |
| Finance: Add Financial Record goes to its section | PASS | top 23 |
| Finance: Analyze Finances goes to its section | PASS | top 23 |
| Finance: Create Budget Scenario calculates (backend event model) | PASS | Verdict: affordable with conditions |
| Donations: Add Donation opens the form | PASS |  |
| Donations: Import Donation CSV opens the importer | PASS |  |
| Donations: Generate Acknowledgment Draft filters to gifts needing one | PASS | 7 rows |
| Donations: Review Missing Information filters flagged records | PASS | 7 rows |
| Donations: View Donation Records clears filters | PASS |  |
| Partnerships: Show all drafts | PASS | 8 -> 41 |
| Partnerships: status filters respond | PASS |  |
| Partnerships: a draft opens with subject, body, copy buttons | PASS |  |
| Partnerships: draft links to its origin | PASS | /mission#finding-27 |
| Partnerships: no send button anywhere | PASS |  |
| Legacy: Add a past event opens the form | PASS |  |
| Legacy: open an event | PASS | /legacy/3 |
| Help: agents and explanations | PASS |  |
| No page errors during the audit | PASS |  |

A code scan of every `<button>` in the interface found **0** without a click handler or form submit, and **0** `href="#"` links.

Screenshots: `docs/screenshots/app-*.jpg`.
