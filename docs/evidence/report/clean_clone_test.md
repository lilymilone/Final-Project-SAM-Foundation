# Clean-clone installation test

**Date:** 2026-10-25, 23:45–23:58 UTC.
**Commit tested:** `e2c2e62` (the version on GitHub at the time).
**Machine:** macOS, Python 3.14.7.

## Setup, exactly as the README says

```
submissions/
├── .env                          <- the API keys (one folder above the repo)
└── Final-Project-SAM-Foundation/ <- fresh git clone from GitHub
```

Before starting, `OPENAI_API_KEY`, `PORTKEY_API_KEY`, and `AI_PROVIDER` were **unset in the shell**, so the keys could only come from the parent `.env`. Then:

```bash
git clone https://github.com/lilymilone/Final-Project-SAM-Foundation.git
cd Final-Project-SAM-Foundation
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py --port 8001     # the README's option for when port 8000 is busy (it was, with the development copy)
```

## Measured times

| Step | Timed run (final) | First run |
|---|---|---|
| `git clone` (about 20 MB, mostly report screenshots) | 80 s | 334 s, during a slow network moment (about 60 KB/s) |
| Create the virtual environment and `pip install` | 8 s | 14 s |
| Start the server until `/api/health` answers | 5 s | 2 s |
| **Total until the app is usable** | **93 s** | **350 s** |

`pip` used this machine's package cache. On a machine without it, the packages (about 25 MB of wheels) add roughly a minute on a typical connection. Either way, setup is well inside the 10-minute rule.

## What was checked

| Check | Result |
|---|---|
| Environment loading | `/api/system/status` reported `env_files_loaded: ["parent"]` and provider `openai`: the keys came from the `.env` one folder above the repo. No key value is ever returned. |
| Database initialization and demo accounts | Created on first start. The demo workspace was seeded (1 planned fundraiser, 3 sample past events). |
| Backend | `/api/health` → `{"status": "ok", "database": "ok"}` |
| Frontend | The prebuilt UI loaded with no Node.js. Signing in as the demo chair showed "Hello, Avery" with no page errors. |
| Login | `POST /api/auth/login` → 200 |
| Basic workflow (real models) | A donations review completed: intake → Donations & Compliance → recommendation → verification, 3 model calls on gpt-6-luna and gpt-6.1-sol, in 30–38 s, for $0.012–$0.019 per run |

## Honest notes

- The clone test ran **three times**:
  1. The first run's probe script could not import the clone's code (a bug in the test script, not the app), so its workflow check did not run.
  2. The second run's donations review completed ($0.0189, 38 s).
  3. The third run happened by mistake while reading results, and completed the same review again ($0.0124, 30 s).
  4. A final run, with the paid workflow skipped, was used only to re-measure the times above.
- Each clone has its own fresh database, so its daily spending cap starts at $0, as it would on a grader's machine.
- Screenshot: [../../screenshots/clean-clone-activity.jpg](../../screenshots/clean-clone-activity.jpg) shows Agent Activity on the final, freshly installed copy. It is empty because that run skipped the workflow.
- Changes made after `e2c2e62` (the docs, evidence, and two evidence scripts in this stage's commit) do not touch installation or the app's code.
