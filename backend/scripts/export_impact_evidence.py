"""Export the impact-evaluation evidence for the report.

    python -m backend.scripts.export_impact_evidence

Writes docs/evidence/impact/:
  methodology.md        how the pilot works, what is measured, and how (generated from the code that runs it)
  test_instructions.md  the participant instructions and the fixed task
  rubric.md             the quality rubric (the same for manual and SAM SPACE proposals)
  impact_evidence.json  every evaluation (anonymized) and every history comparison, as stored
  impact_summary.md     the report-ready summary; says plainly what is missing
Participant names appear only where a participant chose to be named and allowed attribution.
"""

from __future__ import annotations

import json

from backend.app.api.routes.impact import export_bundle
from backend.app.core.config import get_settings
from backend.app.core.env import REPO_ROOT
from backend.app.db.database import Database
from backend.app.services import impact_eval as ie

OUT = REPO_ROOT / "docs" / "evidence" / "impact"


def methodology() -> str:
    return "\n".join([
        "# Impact evaluation: methodology", "",
        "**Question:** does SAM SPACE help a real board member prepare a better event proposal in less time than their usual way of working?", "",
        f"**Fixed task:** {ie.SCENARIO['task']}", "",
        "**Design:** a within-participant pilot. The same board member does the task twice, with the same financial records and Our Legacy "
        "history:",
        "1. **Manual baseline:** their usual tools (web search, spreadsheets, notes, email).",
        "2. **SAM SPACE-assisted:** Event Studio (Manhattan Spring Gala plan), including the time spent reading and correcting the output.", "",
        "**What is recorded, and how:**", "",
        "| Measure | Source |", "|---|---|",
        "| Start, finish, minutes | Server clock (Start/Finish buttons) or times the participant typed; minutes are computed in code |",
        "| Venues, verified sources, financial model, history used, draft (manual) | The participant's answers |",
        "| Agents, venues, sources, financial completeness, verification, lessons, drafts, model time and cost (SAM SPACE) | The linked agent run's own logs |",
        "| Calculation correctness, draft usefulness, errors, unsupported claims | The participant's review |",
        "| Quality (9 dimensions, 0–4) | A person scores both proposals with the same rubric; no AI scoring |",
        "| Ease, usefulness, confidence, yes/no questions, comments | The 12-question feedback form, stored exactly as written |",
        "| Mission (8 dimensions + 'advances the mission?') | The participant's judgment; never converted into emotional-impact statistics |", "",
        "**Calculations (deterministic Python, `services/impact_eval.py`):**",
        "- Minutes saved = manual minutes − SAM SPACE minutes. Negative values are kept: they mean SAM SPACE took longer.",
        "- Percentage time reduction = minutes saved ÷ manual minutes × 100. Only computed when manual minutes > 0.",
        "- Projected annual hours = measured minutes saved × the administrator's assumed tasks per year ÷ 60. A projection, labeled as one.",
        "- Averages use only submitted, real (non-practice) evaluations. Minutes saved use only evaluations that have both times.", "",
        "**Honesty rules built into the app:**",
        "- Practice and test records (`is_synthetic`) are kept apart and never counted.",
        "- With no real submissions, the dashboard shows: *Pilot pending — no real-user evaluation data collected yet.*",
        "- With fewer than five participants, results are labeled a small pilot, not statistically representative.",
        "- Reports show participant codes (P1, P2…) unless a participant chose to be named **and** allowed attribution.", "",
        "**Historical-learning comparison:** the same fixed planning request runs twice through the production pipeline:",
        "- once without the Event Intelligence step",
        "- once with it",
        "",
        "For seven dimensions, code lists what each run said. A with-history statement counts as changed by history only if:",
        "- it is new, and",
        "- it shares at least two meaningful words with a specific lesson or history constraint, which is shown.",
        "",
        "New statements without a matching lesson are listed as *different, no specific lesson found*. Overall quality is left to human scores.", "",
        "**Limits:** one organization; a handful of participants at most; self-reported counts for the manual baseline; the participant knows "
        "which condition is which (no blinding); model outputs vary run to run.", "",
    ]) + "\n"


def instructions() -> str:
    s = ie.SCENARIO
    return "\n".join(["# Participant instructions", "", f"**Task:** {s['task']}", "", "**The proposal should include:**", ""] +
                     [f"{i}. {d}" for i, d in enumerate(s["deliverables"], 1)] + ["", "**Steps:**", ""] +
                     [f"{i}. {x}" for i, x in enumerate(s["instructions"], 1)] + ["", f"_{s['data_note']}_", "",
                      "Where: Analytics & Safety → Impact & Evaluation → Start an evaluation. You can save and come back at any time.", ""]) + "\n"


def rubric() -> str:
    L = ["# Quality rubric", "", "Used for both the manual and the SAM SPACE proposal, by a person. Scale: " +
         ", ".join(f"{k} = {v}" for k, v in ie.SCALE.items()) + ".", "", "| Dimension | Question |", "|---|---|"]
    L += [f"| {label} | {q} |" for _, label, q in ie.RUBRIC]
    L += ["", "No AI model assigns these scores. If one is ever used to suggest scores, the model, tokens, and cost must be recorded "
          "and a person must confirm or correct each score.", ""]
    return "\n".join(L) + "\n"


def main() -> None:
    settings = get_settings()
    db = Database(settings.database_path)
    db.initialize(seed_demo=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with db.session() as s:
        bundle = export_bundle(s, 1)
    (OUT / "impact_evidence.json").write_text(json.dumps(bundle, indent=2, default=str), encoding="utf-8")
    (OUT / "impact_summary.md").write_text(ie.bundle_markdown(bundle), encoding="utf-8")
    (OUT / "methodology.md").write_text(methodology(), encoding="utf-8")
    (OUT / "test_instructions.md").write_text(instructions(), encoding="utf-8")
    (OUT / "rubric.md").write_text(rubric(), encoding="utf-8")
    real = bundle["real"]["summary"]["completed_evaluations"]
    print(f"Exported to {OUT.relative_to(REPO_ROOT)}: {real} real evaluation(s), "
          f"{bundle['synthetic']['summary']['completed_evaluations']} practice record(s), {len(bundle['history_comparisons'])} history comparison(s).")


if __name__ == "__main__":
    main()
