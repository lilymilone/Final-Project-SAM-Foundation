# Final integration audit

**Date:** 2026-10-25.
**Code audited:** `e2c2e62` plus this stage's documentation and evidence changes. No application features were added in this stage.

## 1. Automated tests

| Suite | Result |
|---|---|
| Full pytest suite (scripted model, no network) | **276 passed, 0 failed** (`python -m pytest`). Earlier counts: 273 → 274 → 276, as the run #44 fixes added tests. |
| Mocked adversarial safety suite | 19 of 19 passed (34 cases): [../safety/mocked_test_results.md](../safety/mocked_test_results.md) |
| Restriction tests (no send, no spend, permissions) | 10 of 10 passed: [restrictions_audit.md](restrictions_audit.md) |
| Static checks | pyflakes clean; TypeScript `tsc --noEmit` clean; no Python 3.12-only syntax |

## 2. Live workflows (real models)

| Workflow | Run | Outcome | Cost |
|---|---|---|---|
| A: venue | #40 | **Completed.** 12 steps with one revision round. Draft #56 to the David Rubenstein Atrium, with an email published on the venue's own page. | $0.2112 |
| B: charity | #41 | Stopped by the $5 daily cap (Sol synthesis call refused, never sent) | $0.0118 |
| B: charity | #43 | **Completed.** Six aligned organizations; the top three drafted (#57–#59). Finance gave the planning budget and proposed no amount. One official contact page; no email invented. | $0.0953 |
| C: sponsorship | #42 | Stopped by the daily cap (synthetic attempt) | $0.0001 |
| C: sponsorship | #44 | Completed, but **wrong drafts:** no business sponsor was found, and it drafted to other charities' galas, one past-dated. Led to two fixes (sponsor requests draft only for sponsors; past events skipped), a separate contact-page allowance, and a fix for a garbled cost note. | $0.0742 |
| C: sponsorship | #45 | **Completed with warnings** after the fixes. All six results skipped with reasons, so no off-request draft. No business sponsor found. Verification flagged one unconfirmed availability phrase in the recommendation. | $0.0886 |

**Cause of C's result:**
- Mission Discovery's live search is built for mission-aligned opportunities. For "local business sponsors" it surfaces charities' sponsorship pages and a chamber of commerce, not businesses.
- The sponsorship-draft path works in the automated test (`test_sponsor_discovery_triggers_a_sponsorship_draft`). It has not run live.
- No further paid runs were made: finding sponsors needs a new prospecting feature, not more testing.

**Spending limit:** the chair raised the daily limit to $10 for runs #43–#45 and set it back to **$5.00** after each session. The logged changes are in [spending_limits.md](spending_limits.md).

## 3. The Boss Agent's coordination (run #40, real models)

| Responsibility | Observed in run #40 |
|---|---|
| Receive the board member's request | `intake` (Orchestrator) |
| Assign work to specialists | `lessons` → Event Intelligence, `venues` → Fundraising & Events, `finance` → Financial Analysis, `outreach` → Partnerships & Outreach |
| Receive structured reports | An AgentReport is stored on every specialist handoff (findings, sources, assumptions, risks, financial considerations, outreach signal, other agents, approvals) |
| Coordinate information sharing | History lessons passed to Events; Finance's limits and cost drivers passed to Events; decision provenance passed to Outreach |
| Identify conflicting recommendations | `evaluate`: the projected total exceeded the $18,000 maximum |
| Request revisions | `venues_revision_1` → `finance_revision_1` → `evaluate_revision_1` |
| Delegate proactive outreach drafting | `outreach_decision` selected the Atrium, then `outreach` wrote draft #56 without being asked |
| Consolidate a board-ready recommendation | `recommendation` (stepped down from Astra to Sol by the budget guard) and `verification` |

**Handoffs are recorded and viewable:**
- Agent Activity → run #40 (screenshot `walkthrough-12-run-40-trace.jpg`).
- Exported to `../boss_outreach/trace_run_40.json`.

**Seven distinct agents:**
- Each has its own allow-list and data scopes ([../safety/permission_matrix.md](../safety/permission_matrix.md)).
- Only the Orchestrator can delegate (`test_specialists_cannot_delegate`).

## 4. Proactive outreach drafts

- Drafts #56–#62 were all written without a request for an email.
- Each stores:
  - the organization and category
  - the contact block (email only if published on the organization's own site; otherwise the contact page or website, with source URL, time, status, and confidence)
  - a personalized subject and an editable body
  - the Orchestrator's reason, the agent that found it, and the model that wrote it
  - financial considerations, related findings, sources, and the review status
- The Review Center (Partnerships & Outreach → Drafts for Board Review) listed **41 drafts**. Its status filters responded, and it shows **0 send buttons** (walkthrough audit).
- Statuses are AI Draft, Needs Review, Reviewed, and Archived; none is "sent". Editing and status changes are tested to persist (`test_review_statuses_and_edits_persist`).

## 5. Financial and outreach safety

From [restrictions_audit.md](restrictions_audit.md), generated from the code:
- **44 data-changing API routes, none of which sends, pays, books, or commits.** The donation "acknowledgment" route creates a draft.
- **36 tools** can be given to agents. None is a prohibited action, and none has a send or spend name.
- **23 of 23 prohibited actions are refused** when registered as a tool: send, reply, forward, DM, submit form, schedule, publish, pay, transfer, allocate funds, purchase, book, sign contract, approve donation, commit resources, and others.
- Finance reads, calculates, compares, and recommends only. A member without financial access gets 403 on financial and donor routes, and the UI says so (`walkthrough-16-member-finance-restricted.jpg`).
- Marking a draft *Reviewed* leaves the donations ledger unchanged (`test_no_sending_and_no_spending_capability_exists`).

## 6. Historical learning (Our Legacy)

- **Supported:** uploads (PDF, CSV, XLSX, photos, notes), conversational entry, attributed reflections, evidence-linked lessons, and history-informed planning.
  - Re-verified live through the UI in the previous stage, 12 of 12 checks: [../impact/legacy_verification_live.json](../impact/legacy_verification_live.json).
- **Observed effect:** three comparisons of the same plan without and with history.
  - #3: 10 lesson-backed changes.
  - #2: 14 changes.
  - #1: contingency rose from 10% to 22% after a reflection reported a 22% catering overrun.
  - Files: [../impact/history_comparison_3_report.md](../impact/history_comparison_3_report.md), [../history_ab_experiment_1.md](../history_ab_experiment_1.md).
- **Not fabricated:** sample past events are labeled "(sample)", and imported figures stay *not verified* until the treasurer confirms them.

## 7. Tokenomics and safety evidence

- **Tokenomics:** [tokenomics.md](tokenomics.md) is exported from the logs.
  - 205 model calls, real input, cached-input, and output tokens, $5.65 in total.
  - Cost by model, by agent, and by workflow (median per completed run).
  - Caching savings, 8 budget step-downs, and the steps that ran in code.
  - Monthly projection: $0.63 per board member, $63.26 for 100, $6,326 for 10,000. The usage pattern is an **ASSUMPTION**.
- **Safety:** prompt injection (mocked and live), no-send, no-spend, iteration and handoff limits (`test_E_…`, `test_E2_…`), spending limits enforced live (runs #28, #41, #42), and data-access protections (403 plus audit). Index: [../README.md](../README.md) §4–§5.

## 8. App walkthrough (headless Chrome, chair and member accounts)

| Step | Result |
|---|---|
| Launch, sign in as the demo chair | Works. Butterflies played after sign-in (1 flight). |
| Purple dashboard | Renders (`walkthrough-02/03`) |
| Smile Like Sab logo | **Missing file:** `assets/smile-like-sab.png` is not in the repository, so the designed fallback (butterfly plus "Smile Like Sab") shows. This 404 is the only browser error on any page. |
| Mission Discovery, Event Studio, Our Legacy (and a past event), Financial Intelligence, Donations, Partnerships (Review Center), Agent Activity, run #40 trace, Analytics & Safety, Impact & Evaluation, Settings | All load in about 1.5 s with content. No page errors, no failed API calls, no error text. |
| Member account | Financial Intelligence shows "restricted"; enforced by the server |
| Generating drafts in the UI | Not re-run (paid). The drafts from live runs #40–#45 were reviewed in the Review Center instead. |

## 9. Clean-clone installation

**Passed.** The app was usable 93 s after `git clone` (350 s during a slow network moment). The keys loaded from the parent `.env`; sign-in, the UI, and a real donations workflow worked. Details: [clean_clone_test.md](clean_clone_test.md).

## 10. GitHub readiness

**Secrets:**
- All 10 commits were scanned with `git log -p --all`.
- The only matches are the `.env.example` placeholder and two dummy test values (`sk-test-DUMMYKEY…`, `Bearer DUMMYTOKEN…`).
- No `.env`, database, upload, key, or credential file was ever committed.

**Tracked files:**
- Contents: source code, tests, the prebuilt frontend, docs, samples (fictional), evidence, and screenshots.
- Emails found are public organization addresses from live research, `example.org` fixtures, or test placeholders. No local paths or personal data.

**`.gitignore`** excludes `.env*` (except `.env.example`), the local database and uploads, `node_modules`, `.claude/`, and editor files.

**Logo:** the authentic logo file is still to be added by Lily (`assets/smile-like-sab.png`).

**Commit:** this stage's commit is local only. It will be pushed after Lily approves publication.

## 11. Issues

**Critical (must fix before submission)**
- None in the code.
- **Real-user evidence is missing:** no board member has used the app or completed the pilot. The report's Impact section needs at least one real person (a quote, a screenshot, and a before-and-after time). This needs Lily, not code.

**Important (fix if feasible)**
- **The authentic Smile Like Sab logo file is not in the repository.** Lily needs to add `assets/smile-like-sab.png`. It must not be recreated.
- **The live sponsorship draft is not demonstrated.** Two live searches found no business sponsor. The path is covered by automated tests.
- **Contact research after the allowance fix is untested live.** No live draft has been written since the separate allowance was added (run #45 drafted nothing). Covered by tests.
- **No quality comparison for a cost cut.** Caching savings and budget step-downs are measured, but no cost cut has been compared on quality (for example, partner introductions on Luna instead of Sol).
- **The history comparisons have no human quality scores.**

**Future enhancements**
- Microsoft Outlook: read-only, authorized, drafts only, never sends ([../../roadmap.md](../../roadmap.md)).
- A sponsor-prospecting search for local businesses.
- Re-checking a draft's contact before use.
- A shared budget store for several server processes.
- Multi-factor sign-in.
