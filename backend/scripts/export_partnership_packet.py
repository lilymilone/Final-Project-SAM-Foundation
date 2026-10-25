"""Save a Partnership Opportunity Packet and its full structured log for the final report.

    python -m backend.scripts.export_partnership_packet 13 14

For each run, writes to docs/evidence/partnerships/:
  packet_run_<id>.md    the readable packet
  packet_run_<id>.json  the packet data
  trace_run_<id>.json   every handoff, tool call, and model call (no prompts, no keys, no page text)
"""

from __future__ import annotations

import json
import sys

from backend.app.core.config import get_settings
from backend.app.core.env import REPO_ROOT
from backend.app.db.database import Database
from backend.app.services.partnership_packet import build_partnership_packet, partnership_markdown
from backend.scripts.export_packet import trace


def main() -> None:
    db = Database(get_settings().database_path)
    out = REPO_ROOT / "docs" / "evidence" / "partnerships"
    out.mkdir(parents=True, exist_ok=True)
    for arg in sys.argv[1:]:
        run_id = int(arg)
        packet = build_partnership_packet(db, run_id, 1)
        if packet is None:
            print(f"Run #{run_id} is not a partnership run.")
            continue
        (out / f"packet_run_{run_id}.md").write_text(partnership_markdown(packet), encoding="utf-8")
        (out / f"packet_run_{run_id}.json").write_text(json.dumps(packet, indent=2, default=str), encoding="utf-8")
        (out / f"trace_run_{run_id}.json").write_text(json.dumps(trace(db, run_id), indent=2, default=str), encoding="utf-8")
        print(f"Run #{run_id}: wrote packet_run_{run_id}.md/.json and trace_run_{run_id}.json")


if __name__ == "__main__":
    main()
