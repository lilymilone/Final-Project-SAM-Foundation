"""Save an experiment's comparison for the final report.

    python -m backend.scripts.export_experiment 1

Writes docs/evidence/history_ab_experiment_<id>.md (readable) and .json (full data).
"""

from __future__ import annotations

import json
import sys

from backend.app.api.routes.experiments import experiment_out
from backend.app.core.config import get_settings
from backend.app.core.env import REPO_ROOT
from backend.app.db.database import Database
from backend.app.db.models import Experiment
from backend.app.services.comparison import comparison_markdown


def main() -> None:
    exp_id = int(sys.argv[1])
    db = Database(get_settings().database_path)
    with db.session() as s:
        e = s.get(Experiment, exp_id)
        if e is None or not e.result:
            sys.exit(f"Experiment #{exp_id} not found or not finished.")
        data = experiment_out(e, True)
    out = REPO_ROOT / "docs" / "evidence"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"history_ab_experiment_{exp_id}.md").write_text(comparison_markdown(data), encoding="utf-8")
    (out / f"history_ab_experiment_{exp_id}.json").write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(f"Wrote docs/evidence/history_ab_experiment_{exp_id}.md and .json")


if __name__ == "__main__":
    main()
