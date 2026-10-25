"""Save the structured log of any workflow run for the final report.

    python -m backend.scripts.export_trace finance_donations 16 18 19 20 22

Writes docs/evidence/<folder>/trace_run_<id>.json: every handoff, tool call, and model call
(model, routing reason, tokens, cached tokens, cost, latency), plus the run's final result.
No prompts, keys, page text, or donor details are included.
"""

from __future__ import annotations

import json
import sys

from backend.app.core.config import get_settings
from backend.app.core.env import REPO_ROOT
from backend.app.db.database import Database
from backend.app.db.models import AgentRun
from backend.scripts.export_packet import trace

REDACT_KEYS = {"donations", "per_gift", "draft_ids"}


def _scrub(obj):
    if isinstance(obj, dict):
        return {k: ("[redacted]" if k in REDACT_KEYS else _scrub(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    return obj


def main() -> None:
    folder, ids = sys.argv[1], [int(x) for x in sys.argv[2:]]
    db = Database(get_settings().database_path)
    out = REPO_ROOT / "docs" / "evidence" / folder
    out.mkdir(parents=True, exist_ok=True)
    for run_id in ids:
        with db.session() as s:
            run = s.get(AgentRun, run_id)
            result = run.result if run else None
        if run is None:
            print(f"Run #{run_id} not found.")
            continue
        data = trace(db, run_id)
        data["result"] = _scrub(result)
        (out / f"trace_run_{run_id}.json").write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        print(f"Run #{run_id}: wrote trace_run_{run_id}.json")


if __name__ == "__main__":
    main()
