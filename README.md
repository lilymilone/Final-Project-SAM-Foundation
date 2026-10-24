# SAM SPACE

**Board management and AI decision support for the Sabrina Audrey Milone Foundation (Smile Like Sab).**

SAM SPACE helps a small, volunteer-run nonprofit board plan fundraisers, learn from past events, keep donation records in order, and make better-informed decisions with a team of AI agents. The agents research, calculate, draft, and recommend. A person always makes the final call and does any sending, paying, or booking.

*MGT 409 (AI Foundations) final project · Lily Milone · Yale School of Management*

> **Build stage:** This is the application foundation:
> - sign-in and board roles
> - all ten screens
> - the database and demo data
> - deterministic finance checks
> - the ModelRouter and spending guards
> - the agent interfaces
>
> The seven agents are wired in during the next stage. Screens that depend on them say so and show honest empty states.

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
python -m pytest              # run the automated tests (68 tests, no API key or network needed)
```

---

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
  safety/     oversight policy, untrusted-content wrapper
  services/   deterministic finance + donation checks
backend/scripts/  verify_models.py, create_user.py
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
