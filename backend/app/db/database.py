"""SQLite engine, sessions, and reproducible schema initialization.

The schema is created from the ORM models with create_all(), so a fresh clone
gets the same database every time. To start over, run:  python run.py --reset-db
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import URL, create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, Organization


def as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes. Everything is stored in UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            URL.create("sqlite", database=str(self.path)),
            connect_args={"check_same_thread": False},
        )
        event.listen(self.engine, "connect", _enable_foreign_keys)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> Session:
        return self._sessions()

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        with self._sessions() as db, db.begin():
            yield db

    def initialize(self, seed_demo: bool = True) -> bool:
        """Create tables. Seed the demo workspace if the database is empty.
        Returns True if the demo data was seeded on this call."""
        Base.metadata.create_all(self.engine)
        if not seed_demo:
            return False
        with self.transaction() as db:
            if db.scalar(select(Organization.id).limit(1)) is not None:
                return False
            from .seed import seed_demo_workspace

            seed_demo_workspace(db)
            return True

    def reset(self) -> None:
        self.engine.dispose()
        if self.path.exists():
            self.path.unlink()


def _enable_foreign_keys(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
