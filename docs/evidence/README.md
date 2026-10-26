# Evidence index for the final report

Every file here comes from the app's own logs, real test runs, or real screenshots. Nothing is typed in by hand except where a file says **ASSUMPTION** (the monthly usage pattern in the tokenomics projection).

**Labels used throughout:**
- **live**: real models and real public web pages.
- **synthetic** or **controlled demo**: real models on labeled demo data (venues and organizations on `example.org`). The token counts and costs are real; the organizations are not.
- **fixture**: server-side safety-test pages.
- **mocked**: a scripted model in the automated tests (no API calls).

Finances, donors, and board members in the demo workspace are synthetic. No real foundation records are in this repository.

## 1. The app and its agents

| Evidence | Files |
|---|---|
| Agent architecture diagram (inline-SVG ready) | [report/agent_architecture.svg](report/agent_architecture.svg) |
| Each agent's tools, data scopes, and the 23 prohibited actions | [safety/permission_matrix.md](safety/permission_matrix.md) |
| App walkthrough screenshots (sign-in, dashboard with butterflies, every workspace, member restrictions) | `../screenshots/walkthrough-01-login.jpg` … `walkthrough-16-member-donations-restricted.jpg` |
| Integration audit: pages, errors, restrictions, tests | [report/integration_audit.md](report/integration_audit.md) |
| The working interface, task by task: 10 board-member acceptance tests through the UI (including a full event plan, run #46) and 33 free controls clicked on every page | [report/ui_acceptance_tests.md](report/ui_acceptance_tests.md), screenshots `../screenshots/app-*.jpg` |

## 2. The Boss Agent (Orchestrator) coordinating real specialists

| Evidence | Files |
|---|---|
| Walkthrough of the Boss Agent, reports, decision rules, contact rules, and the three workflows | [../boss_outreach_workflow.md](../boss_outreach_workflow.md) |
| **Workflow A, venue (live run #40, $0.2112)**: 12 steps, one revision round, structured reports, decision, draft #56 with a verified public email | [boss_outreach/A_venue_live_run_40.json](boss_outreach/A_venue_live_run_40.json), [boss_outreach/trace_run_40.json](boss_outreach/trace_run_40.json) |
| **Workflow B, charity (live run #43, $0.0953)**: three charity drafts, Finance consulted with no amount proposed | [boss_outreach/B_charity_live_run_43.json](boss_outreach/B_charity_live_run_43.json), [boss_outreach/trace_run_43.json](boss_outreach/trace_run_43.json) |
| **Workflow C, sponsorship (live run #44, $0.0742)**: no business sponsor found; drafted to peer galas (the gap that was then fixed) | [boss_outreach/C_sponsor_live_run_44.json](boss_outreach/C_sponsor_live_run_44.json), [boss_outreach/trace_run_44.json](boss_outreach/trace_run_44.json) |
| **Workflow C rerun after the fix (live run #45, $0.0886)**: skipped all six non-sponsor results with reasons; no off-request draft; no business sponsor found | [boss_outreach/C_sponsor_live_run_45.json](boss_outreach/C_sponsor_live_run_45.json), [boss_outreach/trace_run_45.json](boss_outreach/trace_run_45.json) |
| All live outreach runs in one file | [boss_outreach/live_summary.json](boss_outreach/live_summary.json) |
| Screenshots: Drafts for Board Review, the decision step, a specialist's structured report | `../screenshots/outreach-review-center*.jpg`, `boss-decision-step.jpg`, `boss-venues-report-step.jpg`, `walkthrough-10-partnerships-review-center.jpg` |
| Earlier cross-agent runs (gala with revision, partnerships, afford-a-gala) | [event_studio/](event_studio/), [partnerships/](partnerships/), [finance_donations/packet_run_19.md](finance_donations/packet_run_19.md) |

## 3. Proactive outreach drafts and verified contact sources

Each draft in the `boss_outreach/*_run_*.json` files contains:
- the recipient, category, subject, and body
- the Orchestrator's reason, the agent that found it, and the model that wrote it
- financial considerations
- a `contact` block: email (only if published on the organization's own site), contact page, source URL, verification time, status, confidence, and notes

| Draft | Contact | Source |
|---|---|---|
| #56 David Rubenstein Atrium (run #40) | verified email on the venue's own page | `yourevent.lincolncenter.org/venues/david-rubenstein-atrium/` |
| #57 Western NY Comprehensive Care Center (run #43) | official contact page, no published email | `nyeatingdisorders.org/contact-us` |
| #60 WithAll (run #44) | verified email | `withall.org/spring-event/` |
| #62 Project Blackbird (run #44) | verified email | `projectblackbirdinc.org/gala/` |
| #61 NEDA gala (run #44) | not read: the site's robots.txt disallows automated tools | ticketing page link only |

## 4. Financial safety and outreach safety

| Evidence | Files |
|---|---|
| Restrictions audit, from code: 44 data-changing API routes (none sends or spends), 36 agent tools (no prohibited action reachable), 23 of 23 prohibited actions refused, 10 restriction tests passing | [report/restrictions_audit.md](report/restrictions_audit.md) |
| Threat model and defenses, with test outcomes | [safety/threat_model.md](safety/threat_model.md) |
| Mocked adversarial suite (19 tests, 34 cases) | [safety/mocked_test_results.md](safety/mocked_test_results.md) |
| Live safety tests (real models): injection, unauthorized outreach, budget stop, Portkey Luna-only, flagship | [safety/live/live_test_results.md](safety/live/live_test_results.md) and `safety/live/*.json` |
| Prompt-injection fixture: the attack page, what screening let through, the live response | [safety/injection_fixture/](safety/injection_fixture/) |
| Security event log (redacted) | [safety/security_events.json](safety/security_events.json) |
| Known remaining vulnerabilities | [safety/known_vulnerabilities.md](safety/known_vulnerabilities.md) |

## 5. Spending limits, enforced

| Evidence | Files |
|---|---|
| Runs stopped by a limit, with the refused calls that were **never sent** (no cost): #28 (the $0.01 workflow budget), #41 and #42 (the $5.00 daily cap) | [report/spending_limits.md](report/spending_limits.md) |
| Budget tests and reservations | [safety/budget_evidence.md](safety/budget_evidence.md), [safety/limits.md](safety/limits.md) |
| Run #40: the router stepped the board recommendation down from Astra to Sol because Astra's worst case exceeded the remaining budget | [boss_outreach/trace_run_40.json](boss_outreach/trace_run_40.json) (the recommendation step's model call) |

## 6. Tokenomics

| Evidence | Files |
|---|---|
| Every recorded model call by model, agent, and workflow: input, cached input, and output tokens; web searches; cost | [report/tokenomics.md](report/tokenomics.md), [report/tokenomics.json](report/tokenomics.json) |
| Cost per workflow (median of completed runs) and the monthly projection for 1, 100, and 10,000 users (**usage pattern is an assumption**) | same files |
| Cost controls observed: prompt caching, budget step-downs, steps run in code with no model | same files |
| Caching before/after on the same task (run #5 $0.0319 vs run #8 $0.0215) | [../legacy_workflow.md](../legacy_workflow.md) §4 |
| **Cost cut with a quality check:** the same event plan on Faster vs Most thorough (runs #46, #48, #49): 206 s → 131–135 s and $0.347 → $0.045, with the same venue, verdict, revisions, drafts, and 9/9 verification | [report/speed_ab.md](report/speed_ab.md) |
| Per-run usage for every workflow (each trace's `model_calls`) | `*/trace_run_*.json` |

## 7. Historical learning (Our Legacy)

| Evidence | Files |
|---|---|
| History comparison #3: gala plan without vs with history (runs #38/#39), 10 lesson-backed changes, budget unchanged | [impact/history_comparison_3_report.md](impact/history_comparison_3_report.md), [impact/history_comparison_3_gala.json](impact/history_comparison_3_gala.json) |
| History experiment #2 (runs #36/#37) using imported history | [legacy_import/history_ab_experiment_2.md](legacy_import/history_ab_experiment_2.md) |
| History experiment #1 (runs #6/#7): contingency 10% to 22% after a reflection reported a catering overrun | [history_ab_experiment_1.md](history_ab_experiment_1.md) |
| Imports (upload and conversation), review before approval, final records | [legacy_import/](legacy_import/) |
| Our Legacy re-verified live through the UI (12 of 12 checks) | [impact/legacy_verification_live.json](impact/legacy_verification_live.json) |

**Caveat:** no person has scored these plans' quality yet. The comparisons show the plans *changed* because of evidence-linked lessons, not that they raise more money.

## 8. Clean-clone installation test

See [report/clean_clone_test.md](report/clean_clone_test.md): a fresh clone from GitHub, with the `.env` one folder above, following the README exactly, with the measured times.

## 9. Real-user feedback

**None collected yet.** The Impact & Evaluation pilot is ready (Analytics & Safety → Impact & Evaluation) and its dashboard shows *Pilot pending*. The method, rubric, and instructions are in [impact/](impact/) (`methodology.md`, `rubric.md`, `test_instructions.md`, `impact_summary.md`). No quotes, times, or scores are reported anywhere because none exist.

## How to regenerate

```bash
python -m backend.scripts.export_trace boss_outreach 40 43 44
python -m backend.scripts.export_report_evidence
python -m backend.scripts.audit_restrictions
python -m backend.scripts.run_safety_suite
python -m backend.scripts.export_safety_evidence
python -m backend.scripts.export_impact_evidence
```
