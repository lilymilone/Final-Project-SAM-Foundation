# SAM SPACE

**Board management and AI decision support for the Sabrina Audrey Milone Foundation (Smile Like Sab).**

SAM SPACE helps a small, volunteer-run nonprofit board plan fundraisers, learn from past events, keep donation records in order, and make better-informed decisions with a team of AI agents. The agents research, calculate, draft, and recommend. A person always makes the final call and does any sending, paying, or booking.

*MGT 409 (AI Foundations) final project · Lily Milone · Yale School of Management*

> **Build stage 2:** the seven-agent system works end to end with real tools, real data, and real model calls.
> Try the controlled demo in two clicks: **Event Studio → Plan with the agents → Run the agents**.

---

## Run it (teaching staff, about 5 minutes)

You need **Python 3.11 or newer**. Node.js is **not** required: the web interface is prebuilt in `frontend/dist`.

**1. Clone the repo next to your `.env` file.**

```
submissions/
├── .env                          <- PORTKEY_API_KEY and/or OPENAI_API_KEY
└── Final-Project-SAM-Foundation/ <- this repo
```

```bash
git clone https://github.com/lilymilone/Final-Project-SAM-Foundation.git
cd Final-Project-SAM-Foundation
```

**2. Install the Python packages.**

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**3. Start the app.**

```bash
python run.py
```

**4. Open http://127.0.0.1:8000 and sign in with a demo account.** The login page has one-click buttons for both.

| Account | Email | Password | Access |
|---|---|---|---|
| Board Chair (demo) | `chair@demo.samspace` | `SmileLikeSab-demo` | Everything |
| Board Member (demo) | `member@demo.samspace` | `SmileLikeSab-demo` | No donor or financial records |

These accounts and every record marked **Demo** are synthetic. No real foundation finances, donors, or board members are in this repository.

### Where the app finds the API keys

The backend loads settings in this order, and earlier sources win:

1. Variables already set in your shell.
2. `.env` in this repo folder.
3. `.env` in the folder **one level above** this repo (the teaching-staff layout above).

You never need to move your keys. Keys stay on the server: they are never printed, logged, returned by the API, or sent to the browser. **Analytics & Safety** shows which keys were *found* (yes/no) and which `.env` files were loaded.

| Key | What happens |
|---|---|
| `OPENAI_API_KEY` | Full model routing across gpt-6-luna, gpt-6.1-sol, and gpt-6-astra, within budget limits. |
| `PORTKEY_API_KEY` only | Course key mode: **gpt-6-luna only**. Sol and Astra are never attempted, escalation is off, and users can't override it. |

When both keys are present, `AI_PROVIDER=auto` (the default) uses OpenAI. Set `AI_PROVIDER=portkey` to force the course key. All options are listed in `.env.example`.

### Useful options

```bash
python run.py --port 8001     # if port 8000 is busy
python run.py --reset-db      # delete the local database and re-create the demo workspace
python run.py --open          # open the browser automatically
python -m pytest              # run the automated tests (148 tests, no API key or network needed)
```

---

## The agents

```
                      Board member's request
                               │
                        ┌──────▼───────┐   intake: model routing (gpt-6-luna) with keyword fallback
                        │ Orchestrator │   plan: fixed template per intent (no invented agents or loops)
                        └──────┬───────┘   recommend: gpt-6-astra · verify in code · one bounded fix
     ┌───────────┬────────────┼──────────────┬───────────────┬────────────────┐
     ▼           ▼            ▼              ▼               ▼                ▼
 Event         Fundraising   Financial      Partnerships    Mission          Donations &
 Intelligence  & Events      Analysis       & Outreach      Discovery        Compliance
 lessons +     venues +      Python math:   unsent drafts   web search +     template + local
 evidence IDs  budgets       affordability  (drafts only)   A–D alignment    merge (no PII to AI)
     └──lessons──►│◄──conflicts / constraints (≤1 revision round)──┘
```

| Agent | Tools (its allow-list only) | What the model does | What code does |
|---|---|---|---|
| Orchestrator | read/create event plan, read/select opportunities, verify result | classify the request; write the board recommendation or partnership packet | plan template, dispatch, revision loop, **candidate selection by the fit rubric**, verification |
| Event Intelligence | past events, reflections, compare outcomes, save lesson | lessons, disagreements, constraints, community insights, citing record IDs | outcome metrics; drops lessons citing records that don't exist and community insights whose quote is not word for word in the cited record |
| Fundraising & Events | search venues, fetch source, budget, revenue scenarios, save venue | rank options, fundraising strategy, mission contribution (inclusion, connection, accessibility, recognition) | every budget; re-ranks if a revision still breaks Finance's limits |
| Financial Analysis | ledger, position, full analysis, event model, affordability, document text, stage figures | plain-English review; organizes figures from uploaded PDFs | all arithmetic, the verdict, conflicts, structured feedback to Events; every extracted figure checked against its page and held for board review |
| Donations & Compliance | donations, flags, compliance checklist, thank-you drafts, contribution acknowledgments | reporting questions citing sources (Sol); one thank-you template (Luna) | merges donor details locally (the AI never sees them); builds contribution acknowledgments in code; never sends, files, or changes records |
| Partnerships & Outreach | saved findings, create draft (**no web, mail, messaging, or scheduling tool**) | personalized drafts with purpose, opportunity, next step | saves drafts as unsent; rejects drafts that claim an action, invent a relationship, commit the foundation, or quote an amount not in the research (one bounded rewrite) |
| Mission Discovery | web search, fetch source, alignment check, save finding | plan the search; explain alignment in four parts (A charitable, B philosophical, C practical, D evidence) | scrubs private details from queries; fetches every link; removes injected instructions; checks dates and costs against the page; applies the fit rubric |

**The controlled example.** With the demo gala plan ($18,000 limit) and synthetic research:

1. Event Intelligence reads the reflections and recommends contingency (one reflection reports a 22% catering overrun).
2. Events shortlists a seated dinner.
3. Finance finds it over the limit and needing more upfront cash than the $9,938 available above the reserve floor. Result: **needs revision**.
4. The Orchestrator sends those limits back.
5. Events switches to a reception.
6. Finance re-checks: **affordable**.
7. Outreach drafts unsent inquiries.
8. Verification checks every dollar figure.
9. The Orchestrator writes the board recommendation.

The fixtures are labeled synthetic everywhere and live on `example.org`. **Live web research** is a toggle on every launcher.

**Measured runs** (real OpenAI calls, official list prices, recorded in Agent Activity):

| Workflow | Model calls | Tokens in / out | Cost | Time |
|---|---|---|---|---|
| Gala plan, synthetic research, 1 revision | 8 | 15,088 / 6,868 | $0.1967 | 112 s |
| Mission discovery, live web search (1 search), 6 links verified | 4 | 16,030 / 2,371 | $0.0130 | 31 s |
| Donations review | 3 | 2,255 / 1,254 | $0.0009 | 15 s |
| Analyze one past event (Event Intelligence) | 2 | 5,007 / 3,267 | $0.0319 | 43 s |
| Same analysis again (2,867 input tokens cached) | 2 | 4,838 / 2,733 | $0.0215 | 36 s |
| Gala plan without history (A/B run A) | 6 | 10,326 / 4,848 | $0.1375 | 90 s |
| Gala plan with history (A/B run B) | 7 | 16,718 / 7,828 | $0.2115 | 134 s |
| Event Studio default case, **live** venue research (#10) | 9 (+2 web searches) | 44,690 / 9,450 | $0.2722 | 153 s |
| Event Studio controlled demo from the UI (#12) | 8 | 21,141 / 8,047 | $0.2322 | 173 s |
| **Partnership workflow, live research** (#13): research → select → 3 unsent drafts → packet | 5 (+1 web search) | 24,157 / 9,011 | $0.2271 | 124 s |
| Partnership workflow, fixture demo with injected page and conflicting dates (#14) | 4 | 10,380 / 8,284 | $0.2171 | 102 s |
| Financial Intelligence: organize a sample statement PDF (#16) | 1 | 1,157 / 678 | $0.0005 | 7 s |
| Financial review, plain English (#18) | 3 | 5,705 (2,539 cached) / 2,653 | $0.0112 | 31 s |
| **"Can the foundation afford a 150-person gala in Manhattan?"** (#19): finance feedback → revision → comparison | 8 | 28,623 (1,062) / 10,525 | $0.3151 | 174 s |
| Donations review with sourced compliance questions and drafts (#20) | 3 | 4,467 / 2,120 | $0.0184 | 25 s |
| Event Studio with mission contribution and community feedback (#15) | 8 | 25,332 (1,042 cached) / 10,240 | $0.2950 | 172 s |

**Safeguards** (all tested):

- **Bounded runs:**
  - Revisions are capped (`MAX_REVISIONS`, default 1, hard cap 2).
  - Handoffs per run are capped (16).
  - The workflow budget and model-call cap are checked before every call.
  - There is a daily spend cap.
  - Only one workflow can run at a time, and a Stop button ends a run.
- **Structured output:**
  - Every model output is Pydantic-validated, with at most 2 retries.
  - Invalid outputs fall back safely.
- **Permissions:**
  - Specialists cannot delegate.
  - Tool allow-lists and board roles are enforced in the tool registry.
  - Finance and donor details are redacted in the run log for roles without access.
- **Web fetching:** blocks private and loopback addresses and follows at most 3 redirects. Pages are capped at 600 KB with an 8-second timeout.
- **Logging:** activity logs show objectives, results, tools, tokens, and cost, never prompts or keys.

## Event Studio (the flagship workflow)

Open **Event Studio**, press **Load the default test case**, then **Generate Event Strategy**. The full walkthrough, with screenshots, measured runs, and the five test scenarios, is in **[docs/event_studio_workflow.md](docs/event_studio_workflow.md)**.

- **Inputs:**
  - name, type, location, and date or date range
  - attendees, ticket price, fundraising target, maximum planning budget
  - additional instructions
- **Two research modes:**
  - **Live web research:** real venues, with every website fetched. A price or capacity counts as published only if it appears on the page; otherwise the venue shows **"Quote required."**
  - **Controlled demo:** labeled synthetic venues that reliably show a revision.
- **Nine visible steps:** interpret, lessons, venues, finance, evaluate constraints, revise (for a budget conflict or a neglected lesson), unsent venue inquiries, verification, and the board-ready plan.
- **Deterministic financial model:**
  - **Costs:** venue, catering (including minimums), entertainment, marketing, staffing, insurance, contingency
  - **Revenue:** tickets, sponsorship, donations
  - **Results:** net proceeds and break-even
  - **Scenarios:** conservative, base, and optimistic
  - **Assumptions:** every one is labeled by source. The board can edit and recalculate them with no AI involved, and save them for the next run.
  - **Cash:** recorded income is never treated as cash.
- **Event Strategy Packet:**
  - overview, recommendation, original vs. revised (with reasons)
  - venue research, financial model, budget warnings
  - lessons linked to past events, editable unsent drafts, sources
  - agent trace, and token usage and cost
  - downloadable as Markdown or printable to PDF
- **Evidence:** packets and structured traces of real runs #10 (live) and #12 (controlled demo) are in `docs/evidence/event_studio/`.

## Mission Discovery and Partnerships (the foundation's philosophy at work)

“Be somebody who makes everybody feel like somebody.” The full walkthrough, with screenshots, real runs, and the nine required tests, is in **[docs/partnership_workflow.md](docs/partnership_workflow.md)**.

- **Shared mission config** (`backend/app/mission.py`): the philosophy becomes seven decision criteria, evidence rules, and an explicit fit rubric (Strong / Possible / Weak / Needs research) applied in code. There are no numeric scores, and clinical research is never down-ranked.
- **Mission Discovery dashboard:** cards with name, category, geography, purpose, activities, checked source, dates (confirmed / conflicting / unconfirmed), alignment A–D, partnership type, costs verified on the page, missing information, next step, and date last checked. The board can save, dismiss, categorize, add private notes (never sent to a model or website), request more research, or generate a draft. Every statistic comes from stored records.
- **Cross-agent workflow:** *“Find three organizations in New York that support mental health awareness and community belonging, and draft partnership inquiries.”* runs Mission Discovery → Orchestrator selection (code) → Partnerships & Outreach → a board-ready **Partnership Opportunity Packet**. Sources and uncertainty travel with every handoff.
- **Drafts only, enforced in code:** Outreach's only tools read research and save drafts; send/contact/schedule/publish tools cannot be registered; drafts have no “sent” status; the API rejects one (422).
- **Untrusted web content:** instruction-like sentences are removed before any model sees a page, and the card says so. Private names, emails, and amounts are removed from search queries.
- **Evidence:** `docs/evidence/partnerships/` (live run #13, fixture demo #14) and `docs/evidence/event_studio/packet_run_15.md` (mission contribution).

## Financial Intelligence and Donations & Compliance

The full walkthrough, with screenshots, real runs, and the 17 required tests, is in **[docs/finance_donations_workflow.md](docs/finance_donations_workflow.md)**.

- **Dashboard:**
  - recorded revenue, expenses, and net result; cash on hand; restricted vs. unrestricted funds
  - program and event spending, revenue trends, budget vs. actual, a three-month outlook (estimates)
  - preliminary event budget capacity, warnings, and missing information
  - each figure explained in plain English
  - **Revenue is never shown as cash, and restricted gifts are never spendable.**
- **Uploads:**
  - CSV (parsed in code) and PDF (text only; scripts never run; scanned files flagged for manual entry)
  - size limits, content checks, and sanitized names; private storage scoped to each organization; duplicate detection
  - Figures the AI organizes from a PDF wait in a **review queue** until a board member approves, corrects, or rejects each one.
  - Manual entry and corrections are audited.
- **Event finance:**
  - pledged sponsorship is never counted as guaranteed (the conservative case uses confirmed sponsorship only)
  - Miscellaneous costs and other documented revenue lines are included.
  - a second break-even shows the headcount needed without unconfirmed sponsorship
  - Finance sends the Events agent structured feedback (limits, how much over, cost drivers)
  - original and revised proposals are compared side by side
- **Donations:**
  - full records: IDs, campaigns, restriction, payment and acknowledgment status
  - add, edit, CSV import and export, search and filters, campaign totals, reconciliation with the ledger
  - duplicate and double-counting safeguards
- **Compliance review:**
  - each item is a cited IRS requirement (US federal), general guidance (NY and CT registration), or routed to an accountant or attorney
  - general thank-you drafts and separate contribution-acknowledgment drafts for accountant review
  - no send button anywhere
- **Sample files to try:** `docs/sample_ledger.csv` and `docs/samples/sample_statement_FY2025.pdf` (both fictional).

## Our Legacy (institutional memory)

The full walkthroughs, with screenshots and measured runs, are in **[docs/legacy_workflow.md](docs/legacy_workflow.md)** and
**[docs/legacy_import_workflow.md](docs/legacy_import_workflow.md)** (imports and organizational memory).

- **Three ways to add history:**
  - **Upload files:** PDF, CSV, XLSX, JPG/PNG photos, .txt/.md notes. Each is checked by its contents, stored privately, and read in an isolated process. Photos are never read for numbers.
  - **Tell us about an event** in plain words.
  - **Board reflections**, one per member, with optional attributed entry.
- **Extraction you review first:** the Event Intelligence agent proposes details, each quoting its source.
  - Code drops anything whose words are not in the source.
  - Disagreeing figures become conflicts for the board, and missing details stay blank.
  - Nothing is saved until a board member edits and approves the preview; recorded values change only with per-field confirmation.
  - Each saved field keeps its source and quote. Imported figures are labeled *not verified accounting data* until the treasurer verifies them.
- **Try it:** sample files for a made-up event are in [docs/samples/legacy/](docs/samples/legacy/).

- **Event gallery and records:**
  - date, type, venue, attendance, goal, funds raised, expenses, **calculated net**, sponsors, summary, notes
  - photos, checked by file contents and served privately
  - edits are audited; events are never deleted
- **Structured reflections:** seven post-event questions plus four community questions (welcome, connection, volunteer appreciation, accessibility) per board member, with name and date. They are **append-only**, and AI never edits them.
- **"Analyze Event & Generate Lessons":**
  - Event Intelligence finds themes, strengths and weaknesses, and disagreements (in the members' own words).
  - It compares outcomes in code when the data allows.
  - Every lesson links to its event and reflection records.
  - The board can mark lessons reviewed, adopted, or dismissed.
- **Planning integration:**
  - The Orchestrator first ranks past events by similarity in code (type, area, size, recency, with reasons).
  - It then asks Event Intelligence for lessons from those events before the Events agent plans.
  - History constraints are advisory and namespaced. Hard limits come only from Financial Analysis.
  - The Event Strategy Packet's **What We Learned** section shows the events consulted, the computed observations, the lessons, and which parts of the plan they shaped. Every handoff log records what history was passed.
- **Cross-event insights:** observations computed from recorded figures (net by event type, goal attainment, cost overruns against the planned budget, sponsorship share) are kept apart from AI interpretations and board feedback, and each links to its records.
- **Evidence test:** the same plan is run without and with history, and code compares the results and API usage.
  - Experiment #1 is in [docs/evidence/history_ab_experiment_1.md](docs/evidence/history_ab_experiment_1.md).
  - Experiment #2, a raffle plan using imported history, is in [docs/evidence/legacy_import/](docs/evidence/legacy_import/).
- **Impact metrics:**
  - events, reflections, contributors, lessons
  - recurring issues (2+ records)
  - reviewed and adopted counts
  - outcome improvement, shown as **not yet measured**
- **Community impact** (from records only): participants, volunteers, repeat participants, partnerships formed, funds directed to programs, feedback, reported belonging, documented outcomes, and community insights. Each is labeled **Actual observation**, **Self-reported**, **AI interpretation**, or **Estimate**. Blank fields show as “Not recorded”, never zero.

## Safety, privacy, and spending controls

The walkthrough, with the threat model, test results, and screenshots, is in **[docs/safety_workflow.md](docs/safety_workflow.md)**. Evidence is in [docs/evidence/safety/](docs/evidence/safety/).

- **One safety layer per workflow** (`backend/app/safety/manager.py`). It decides, in code:
  - which tools an agent may call (an allow-list) and which data each tool may read (a data scope, a second wall)
  - whether a model call fits the budget (the worst-case cost is reserved first, under a lock)
  - whether another handoff, revision, tool call, search, or page fetch is allowed
  - what happens to outside text (instruction-like sentences are removed; the rest reaches a model only as labeled data)

  Every refusal is written to a redacted security log.
- **Nothing leaves in the foundation's name.** No send, contact, schedule, publish, book, or pay tool exists, and the registry refuses those names. Drafts have no "sent" status.
- **Limits the chair controls:** spend per workflow and per day, model calls, handoffs, tool calls, retries, output tokens, duration, revisions, searches, page fetches, and contact pages per outreach draft.
  - Each is clamped to a hard cap that only a code change can move.
  - A run that hits a limit stops and keeps its finished steps, labeled partial. It never shows a fake success, and no butterflies play.
- **Course key:** `PORTKEY_API_KEY` only ever reaches `gpt-6-luna`. The router and the provider wrapper each enforce this.
- **Safe web retrieval:**
  - http(s) on standard ports only, with no credentials in links
  - every resolved address must be public, and the checked IP is pinned (DNS rebinding)
  - redirects are re-checked; size, type, and time limits apply
  - links carrying donor names or emails are never fetched
- **Uploads** are parsed as text only, in a separate, resource-limited process that has no keys.
- **Analytics & Safety → Safety** shows the active limits (editable by the chair), the permission matrix, mocked and live test results, blocked actions, budget events, injection outcomes, data-access warnings, and known risks. All of it comes from logged records.
- **Run the tests yourself:**
  - `python -m backend.scripts.run_safety_suite`: the adversarial suite, scripted model, free
  - `python -m backend.scripts.run_live_safety`: real models, about $1
  - `python -m backend.scripts.export_safety_evidence`: writes the evidence files

## The Boss Agent and proactive outreach drafts

The walkthrough is in **[docs/boss_outreach_workflow.md](docs/boss_outreach_workflow.md)**.

- **The Orchestrator acts as the AI Chief of Staff.** It delegates to the specialists, and each one returns a structured **AgentReport** covering:
  - findings, sources, assumptions, and risks
  - financial considerations
  - whether outreach is appropriate, which other agents should contribute, and whether board or professional review is needed

  The Orchestrator reads these reports and decides, in a logged `outreach_decision` step, which venues, charities, research initiatives, or sponsors deserve a draft.
- **Drafts are prepared automatically.** Nobody has to ask for an email each time.
  - The Partnerships & Outreach agent looks up **public inquiry details on each organization's own website**. An email is used only if it is listed there; otherwise the draft says *"Contact email not verified — use official contact page."*
  - It never guesses addresses, never names people, and never adds phone numbers. Code rejects any draft that does.
- **Drafts for Board Review** (Partnerships & Outreach) shows, for every draft:
  - the contact and where it came from
  - why the Orchestrator recommended it, and which agent found it
  - financial considerations and sources
  - the model that wrote it, and the review status (AI Draft, Needs Review, Reviewed, Archived)

  Board members can edit, copy the email, subject, or message, mark reviewed, and archive. **Nothing can be sent, and no money can be committed.**
- **Live runs** (evidence in [docs/evidence/boss_outreach/](docs/evidence/boss_outreach/)):
  - **Venue inquiry, run #40 ($0.21):** one draft, with an events email published on the venue's own page.
  - **Charity introductions, run #43 ($0.10):** three drafts; contact pages only, no emails invented.
  - **Sponsor search, run #44 ($0.07):** found no business sponsor and drafted introductions to other charities' galas instead. This is a known gap, described in the walkthrough.
- **Microsoft Outlook** is a planned future integration, read-only and with no send permission. It is not implemented: see [docs/roadmap.md](docs/roadmap.md).

## Impact & Evaluation (real-user pilot)

The walkthrough is in **[docs/impact_evaluation_workflow.md](docs/impact_evaluation_workflow.md)**. Evidence is in [docs/evidence/impact/](docs/evidence/impact/).

- **Analytics & Safety → Impact & Evaluation** compares the board's usual way of preparing a 150-person gala proposal with SAM SPACE.
  - Times are recorded on the server clock and include reviewing the AI's work.
  - The run's own logs supply venues, sources, finance, lessons, drafts, and the agents' time and cost.
  - Both proposals are scored on the same human rubric, followed by a 12-question feedback form and mission questions.
- **Honest by construction:**
  - With no real submissions, the dashboard says *Pilot pending — no real-user evaluation data collected yet.*
  - Practice runs are never counted.
  - Negative time savings and unfavorable feedback are shown as recorded.
  - Names appear only with the participant's permission.
- **Historical learning:** the same plan runs without and with Our Legacy, and code shows which recommendations changed and the specific lesson each one rests on.
- **Export:** `python -m backend.scripts.export_impact_evidence` writes the methodology, instructions, rubric, anonymized results, and comparisons.

## What's in this stage

- **Board sign-in.**
  - Passwords are hashed with scrypt.
  - Sessions are server-side, in an HttpOnly + SameSite=Strict cookie. They expire after 8 hours and can be signed out.
  - Failed sign-ins are limited to 5 per 15 minutes.
  - State-changing calls need a same-origin header.
- **Role-based access.** Chair, treasurer, and member roles. Donor and financial routes are blocked on the server (403) for members, and denied attempts are audited.
- **Ten screens:**
  - Overview
  - Mission Discovery
  - Event Studio
  - Financial Intelligence
  - Donations & Compliance
  - Partnerships & Outreach
  - Our Legacy
  - Agent Activity
  - Analytics & Safety
  - Settings

  Each has loading, error, and empty states.
- **CSV import of financial records:** validated row by row, and nothing is saved unless every row passes. Try `docs/sample_ledger.csv`.
- **Working records:**
  - Plan fundraisers (Event Studio).
  - Record past events and board reflections (Our Legacy).
  - Financial warning flags and donation-compliance flags, computed in plain Python with no AI.
- **ModelRouter.** Deterministic and auditable model choice per task, with no model call spent choosing a model. It handles:
  - the Auto / Economy / Balanced / Advanced strategies
  - verified model availability
  - explicit, recorded fallbacks
  - budget-aware downgrades
  - the Portkey lock
- **LLMService + budgets.** Every model call is checked against:
  - the per-workflow budget
  - the per-workflow call cap
  - the daily spend cap

  Each call is recorded with:
  - agent
  - selected model, the model the API reported, and the reason
  - input, cached-input, and output tokens
  - cost at official list prices
  - latency
- **Agent architecture.** Seven agents with typed handoffs (Pydantic), per-agent tool allow-lists, and a dependency-ordered orchestration plan. Prohibited actions (sending email, payments, bookings, publishing, tax filings, and more) are refused by the tool registry in code.
- **Butterflies.** Gentle SVG butterflies appear only after real successes: sign-in, saving a fundraiser, saving a past event or reflection, milestones. They respect `prefers-reduced-motion` and a Settings toggle, never block clicks, and are hidden from screen readers.

## Models and prices

Checked on 2026-10-24: each model below appeared in the API key's model list and answered a test call.

| Tier | Model | Input | Cached input | Output |
|---|---|---|---|---|
| Fast (Luna) | `gpt-6-luna` | $0.10 | $0.01 | $0.50 |
| Intermediate (Sol) | `gpt-6.1-sol` (fallback `gpt-6-sol`) | $2.00 | $0.10 | $10.00 |
| Advanced (Astra) | `gpt-6-astra` (fallback `gpt-6.1-sol`) | $10.00 | $1.00 | $50.00 |

Prices are USD per 1M tokens, standard tier, prompts up to 272K input tokens. Source: [OpenAI API pricing](https://developers.openai.com/api/docs/pricing), retrieved 2026-10-24. They are stored in `backend/app/ai/pricing.json`.

Routing rule: `score = complexity (0–2) + 1 if multi-step reasoning + 1 if high risk`. The chosen strategy maps the score to a tier (see `backend/app/ai/router.py`).

## Project layout

```
backend/app/
  core/       env loading, settings, password hashing, roles, rate limit
  db/         SQLite schema (SQLAlchemy), init, synthetic demo seed
  api/        FastAPI routes + auth/permission dependencies
  ai/         ModelRouter, providers (OpenAI / Portkey), LLMService, budgets, pricing
  agents/     agent interfaces, the seven agent specs, orchestration plans
  tools/      tool registry with allow-lists and prohibited-action blocking
  safety/     SafetyManager (permissions, limits, budgets, events), limits, redaction, injection screening,
              query and link scrubbing, the prompt-injection scenario, known risks
  services/   deterministic finance, event model, mission fit, opportunity selection, impact, packets
  mission.py  FoundationMission: philosophy, criteria, fit rubric (shared by the agents)
  compliance.py  cited compliance sources (IRS, NY, CT) with jurisdiction and check date
backend/scripts/  verify_models.py, create_user.py, export_packet.py, export_partnership_packet.py, export_trace.py,
                  run_safety_suite.py, run_live_safety.py, export_safety_evidence.py, export_impact_evidence.py
frontend/     React + TypeScript + Vite + Tailwind (built output in frontend/dist)
tests/        pytest suite
assets/       Smile Like Sab logo (smile-like-sab.png)
docs/         screenshots for the report
run.py        one-command start
```

## For development

```bash
python run.py      # backend on :8000 (terminal 1)
cd frontend        # terminal 2
npm install
npm run dev        # http://localhost:5173, proxies /api to the backend on :8000
npm run build      # rebuild frontend/dist before committing UI changes
```

Other commands:

- **Check models:** `python -m backend.scripts.verify_models` lists the models your key can use. Add `--probe` to make one tiny, recorded call per tier.
- **Add a real board member:** `python -m backend.scripts.create_user --email you@example.org --first Lily --role chair`. The password is typed at a prompt and never stored in code.
