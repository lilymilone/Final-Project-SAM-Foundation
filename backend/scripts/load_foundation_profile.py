"""Load a filled-in Foundation Knowledge Base file into the local database.

    python -m backend.scripts.load_foundation_profile path/to/profile.json

The file follows docs/foundation_knowledge_template.json. Keep the filled-in file out of git (backend/data/ is ignored):
real foundation facts live only in the local database. Entries are matched by (section, title), so running the script
again updates them instead of adding duplicates. An entry may name an Our Legacy record ("legacy_event_name") to link to it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from backend.app.core.config import get_settings
from backend.app.db.database import Database
from backend.app.db.models import HistoricalEvent, Organization
from backend.app.services.knowledge import import_entries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("file", type=Path)
    parser.add_argument("--contributor", default="Board member")
    args = parser.parse_args()
    data = json.loads(args.file.read_text(encoding="utf-8"))
    db = Database(get_settings().database_path)
    db.initialize()
    with db.transaction() as s:
        org_id = s.scalar(select(Organization.id).order_by(Organization.id).limit(1))
        events = {e.name.lower(): e.id for e in s.scalars(select(HistoricalEvent).where(HistoricalEvent.organization_id == org_id))}
        entries = []
        for item in data.get("entries", []):
            name = (item.pop("legacy_event_name", None) or "").lower()
            if name:
                if name not in events:
                    raise SystemExit(f"No Our Legacy record named {name!r}.")
                item["historical_event_id"] = events[name]
            entries.append(item)
        counts = import_entries(s, org_id, entries, contributor=data.get("contributor") or args.contributor, can_verify=True)
    print(f"Foundation Knowledge Base: {counts['added']} added, {counts['updated']} updated.")


if __name__ == "__main__":
    main()
