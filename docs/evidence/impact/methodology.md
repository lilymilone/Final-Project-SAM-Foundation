# Impact evaluation: methodology

**Question:** does SAM SPACE help a real board member prepare a better event proposal in less time than their usual way of working?

**Fixed task:** Prepare an initial fundraising event proposal for a 150-person gala in Manhattan, including three potential venues, a preliminary event budget, relevant lessons from past foundation events, and one draft venue inquiry email.

**Design:** a within-participant pilot. The same board member does the task twice, with the same financial records and Our Legacy history:
1. **Manual baseline:** their usual tools (web search, spreadsheets, notes, email).
2. **SAM SPACE-assisted:** Event Studio (Manhattan Spring Gala plan), including the time spent reading and correcting the output.

**What is recorded, and how:**

| Measure | Source |
|---|---|
| Start, finish, minutes | Server clock (Start/Finish buttons) or times the participant typed; minutes are computed in code |
| Venues, verified sources, financial model, history used, draft (manual) | The participant's answers |
| Agents, venues, sources, financial completeness, verification, lessons, drafts, model time and cost (SAM SPACE) | The linked agent run's own logs |
| Calculation correctness, draft usefulness, errors, unsupported claims | The participant's review |
| Quality (9 dimensions, 0–4) | A person scores both proposals with the same rubric; no AI scoring |
| Ease, usefulness, confidence, yes/no questions, comments | The 12-question feedback form, stored exactly as written |
| Mission (8 dimensions + 'advances the mission?') | The participant's judgment; never converted into emotional-impact statistics |

**Calculations (deterministic Python, `services/impact_eval.py`):**
- Minutes saved = manual minutes − SAM SPACE minutes. Negative values are kept: they mean SAM SPACE took longer.
- Percentage time reduction = minutes saved ÷ manual minutes × 100. Only computed when manual minutes > 0.
- Projected annual hours = measured minutes saved × the administrator's assumed tasks per year ÷ 60. A projection, labeled as one.
- Averages use only submitted, real (non-practice) evaluations. Minutes saved use only evaluations that have both times.

**Honesty rules built into the app:**
- Practice and test records (`is_synthetic`) are kept apart and never counted.
- With no real submissions, the dashboard shows: *Pilot pending — no real-user evaluation data collected yet.*
- With fewer than five participants, results are labeled a small pilot, not statistically representative.
- Reports show participant codes (P1, P2…) unless a participant chose to be named **and** allowed attribution.

**Historical-learning comparison:** the same fixed planning request runs twice through the production pipeline:
- once without the Event Intelligence step
- once with it

For seven dimensions, code lists what each run said. A with-history statement counts as changed by history only if:
- it is new, and
- it shares at least two meaningful words with a specific lesson or history constraint, which is shown.

New statements without a matching lesson are listed as *different, no specific lesson found*. Overall quality is left to human scores.

**Limits:** one organization; a handful of participants at most; self-reported counts for the manual baseline; the participant knows which condition is which (no blinding); model outputs vary run to run.

