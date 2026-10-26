"""SQLite engine, sessions, and reproducible schema initialization.

The schema is created from the ORM models with create_all(), so a fresh clone
gets the same database every time. To start over, run:  python run.py --reset-db
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import URL, create_engine, event, inspect, select, text
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
            connect_args={"check_same_thread": False, "timeout": 30},
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
        self._add_missing_columns()
        if not seed_demo:
            return False
        with self.transaction() as db:
            if db.scalar(select(Organization.id).limit(1)) is not None:
                from .seed import upgrade_demo_books, upgrade_demo_donations, upgrade_demo_history

                upgrade_demo_history(db)  # idempotent: fills new demo fields in older databases
                upgrade_demo_books(db)
                upgrade_demo_donations(db)
                _seed_knowledge(db)
                return False
            from .seed import seed_demo_workspace

            seed_demo_workspace(db)
            db.flush()
            _seed_knowledge(db)
            return True

    def _add_missing_columns(self) -> None:
        """Tiny forward-only migration: add any new (nullable) columns to tables
        created by an older version. Fresh databases already have them."""
        existing = inspect(self.engine)
        with self.engine.begin() as conn:
            for table in Base.metadata.sorted_tables:
                if not existing.has_table(table.name):
                    continue
                present = {c["name"] for c in existing.get_columns(table.name)}
                for column in table.columns:
                    if column.name not in present and column.nullable:
                        col_type = column.type.compile(dialect=self.engine.dialect)
                        conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))
            # Lessons saved before lessons had a scope can never be superseded by a newer
            # analysis; retire unreviewed ones so the board sees only current lessons.
            if existing.has_table("historical_lessons"):
                conn.execute(text("UPDATE historical_lessons SET status = 'superseded' "
                                  "WHERE scope IS NULL AND (status IS NULL OR status = 'new')"))

    def reset(self) -> None:
        self.engine.dispose()
        if self.path.exists():
            self.path.unlink()


def _seed_knowledge(db: Session) -> None:
    """Give every workspace without a knowledge base its starting entries (identity and labeled samples)."""
    from ..services.knowledge import seed_knowledge

    for org_id in db.scalars(select(Organization.id)).all():
        seed_knowledge(db, org_id)


def _enable_foreign_keys(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")  # background agent runs write while the UI reads
    cursor.close()
