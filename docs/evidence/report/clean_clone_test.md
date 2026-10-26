# Clean-clone installation test

**Latest run:** 2026-10-26, about 13:55–14:00 UTC.
**Commit tested:** `041fc93` (the version on GitHub at the time, including the Foundation Knowledge Base).
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

| Step | 2026-10-26 (`041fc93`) | 2026-10-25 (`e2c2e62`), for comparison |
|---|---|---|
| `git clone` (33 MB) | 5 s | 80 s (334 s on the first try, during a slow network moment) |
| Create the virtual environment and `pip install` | 6 s | 8 s |
| Start the server until `/api/health` answers | 8 s | 5 s |
| **Total until the app is usable** | **19 s** | **93 s** (350 s on the first try) |

`pip` used this machine's package cache both times. On a machine without it, the packages (about 25 MB of wheels) add roughly a minute on a typical connection. Either way, setup is well inside the 10-minute rule.

## What was checked (2026-10-26): 8 of 8 passed, plus the full test suite

| Check | Result |
|---|---|
| Demo sign-in (chair) | `POST /api/auth/login` → 200 |
| Keys from the parent `.env` only | `/api/system/status` reported provider `openai` and `env_files_loaded: ["parent"]`. No key value is ever returned. |
| Dashboard data | `/api/overview` → 1 planned fundraiser (demo) |
| Demo books | Financial Intelligence shows $84,000 cash (the resized demo books), labeled demo |
| Foundation Knowledge Base | 6 entries: the three identity facts already in the repository and three labeled samples. **None of the foundation's real facts are in the clone**; they live only in the developer's local database. |
| Our Legacy | 3 past events, all labeled samples |
| Web interface | Served from the prebuilt `frontend/dist`; no Node.js |
| A real AI workflow | Donations review (Faster setting) completed: run #1, 30 s, 4 model calls, $0.0023 |
| Every page in a real browser | Signed in through the login form, then opened Event Studio, Mission Discovery, Our Legacy, Finance, Donations, Partnerships, Agent Activity, the run page, Analytics & Safety, the Foundation Knowledge Base, and Help: all loaded, with no browser errors |
| Automated tests inside the clone | `python -m pytest` → **298 passed** in 24.8 s |
| Private files | The clone contains no `report.html`, `slides.html`, local foundation profile, database, or `.env` |

After the test, the server was stopped and the clone (with its own database and the one paid run) was deleted.

## Notes

- Each clone has its own fresh database, so its daily spending cap starts at $0, as it would on a grader's machine.
- No screenshot was kept from this run. The earlier run's screenshot is [../../screenshots/clean-clone-activity.jpg](../../screenshots/clean-clone-activity.jpg).
- **The earlier run (2026-10-25, `e2c2e62`)** also passed: the keys loaded from the parent `.env`, the UI and sign-in worked, and a donations review completed ($0.012–$0.019 per run, 30–38 s). It ran three times: the first probe script could not import the clone's code (a bug in the test script, not the app), and the third paid run happened by mistake while reading results.
