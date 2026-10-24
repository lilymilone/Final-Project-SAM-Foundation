"""Synthetic demonstration data.

Everything here is made up for teaching-staff testing and is flagged
is_demo=True. None of it is a real Sabrina Audrey Milone Foundation result,
donor, or board member. Only the inputs a small nonprofit would already have
are seeded (past events, reflections, books, donations, one planned event).
AI output tables stay empty until a real agent run fills them.
"""

from __future__ import annotations

import os
from datetime import date

from sqlalchemy.orm import Session

from ..core.security import hash_password
from .models import (
    BoardMembership,
    BoardReflection,
    Donation,
    EventPlan,
    FinancialRecord,
    HistoricalEvent,
    Organization,
    User,
)

# Demo login for the teaching staff. It is also shown on the login page and in
# the README. It unlocks synthetic data only.
DEMO_PASSWORD_DEFAULT = "SmileLikeSab-demo"
DEMO_ACCOUNTS = [
    # email, first, last, role, title
    ("chair@demo.samspace", "Avery", "Brooks", "chair", "Board Chair (demo)"),
    ("member@demo.samspace", "Sam", "Rivera", "member", "Board Member (demo)"),
]

MISSION = (
    "In memory of Sabrina Audrey Milone: supporting mental health awareness, "
    "eating disorder research, and community-building initiatives."
)


def demo_password() -> str:
    return os.getenv("DEMO_PASSWORD", "").strip() or DEMO_PASSWORD_DEFAULT


def seed_demo_workspace(db: Session) -> Organization:
    org = Organization(name="Sabrina Audrey Milone Foundation", mission=MISSION, is_demo=True)
    db.add(org)
    db.flush()

    password_hash = hash_password(demo_password())
    users: dict[str, User] = {}
    for email, first, last, role, title in DEMO_ACCOUNTS:
        user = User(email=email, first_name=first, last_name=last, password_hash=password_hash, is_demo=True)
        db.add(user)
        db.flush()
        db.add(BoardMembership(user_id=user.id, organization_id=org.id, role=role, title=title))
        users[role] = user

    _seed_history(db, org.id)
    _seed_books(db, org.id)
    _seed_donations(db, org.id)
    db.add(
        EventPlan(
            organization_id=org.id,
            created_by=users["chair"].id,
            name="Manhattan Spring Gala (sample plan)",
            event_type="gala",
            city="New York, NY",
            target_date=date(2027, 4, 17),
            expected_attendance=150,
            fundraising_goal_usd=40000,
            budget_limit_usd=18000,
            status="planning",
            notes="Sample plan for the demo. Venue not chosen. Board wants a warm, personal evening.",
            is_demo=True,
        )
    )
    return org


def _seed_history(db: Session, org_id: int) -> None:
    events = [
        dict(
            name="Spring Awareness Walk (sample)", event_date=date(2025, 4, 26), location="New Haven, CT",
            event_type="community walk", attendance=210, funds_raised_usd=14200, total_cost_usd=3100,
            summary="Sample 5K awareness walk with a resource fair from local mental-health groups.",
            reflections=[
                ("Demo board member A", "Turnout beat our goal and families stayed for the resource fair.",
                 "Permit paperwork took six weeks; we almost missed the deadline.",
                 "Start the city permit process in January.", 5),
                ("Demo board member B", "Local businesses sponsored water and T-shirts.",
                 "Online registration closed early by mistake.",
                 "Test the registration form with a friend before launch.", 4),
            ],
        ),
        dict(
            name="Butterfly Benefit Dinner (sample)", event_date=date(2025, 10, 18), location="Greenwich, CT",
            event_type="dinner", attendance=95, funds_raised_usd=31500, total_cost_usd=16800,
            summary="Sample seated dinner with a speaker on eating-disorder recovery and a silent auction.",
            reflections=[
                ("Demo board member A", "The speaker moved people; auction pledges were strong.",
                 "Catering was 22% over the quote after the guest count changed.",
                 "Lock the guest count two weeks out and get the per-head price in writing.", 4),
                ("Demo board member C", "Volunteers ran check-in smoothly.",
                 "Several pledges were never collected after the event.",
                 "Collect payment at the table, not by follow-up.", 3),
            ],
        ),
        dict(
            name="Campus Wellness Panel (sample)", event_date=date(2026, 2, 12), location="New Haven, CT",
            event_type="panel", attendance=120, funds_raised_usd=2600, total_cost_usd=900,
            summary="Sample student panel on body image and asking for help, co-hosted with a campus group.",
            reflections=[
                ("Demo board member B", "Students asked for a follow-up session.",
                 "Low fundraising; this was an awareness event, not a fundraiser.",
                 "Pair awareness events with a small, clear giving ask.", 4),
            ],
        ),
    ]
    for data in events:
        reflections = data.pop("reflections")
        event = HistoricalEvent(organization_id=org_id, is_demo=True, **data)
        db.add(event)
        db.flush()
        for author, well, challenge, differently, rating in reflections:
            db.add(
                BoardReflection(
                    historical_event_id=event.id, author_label=author, went_well=well, challenges=challenge,
                    do_differently=differently, rating=rating, is_demo=True,
                )
            )


def _seed_books(db: Session, org_id: int) -> None:
    rows = [
        # period, kind, category, amount
        ("2026-05", "income", "Individual donations", 4200), ("2026-05", "expense", "Programs", 3100),
        ("2026-05", "expense", "Operations", 650),
        ("2026-06", "income", "Individual donations", 2900), ("2026-06", "expense", "Programs", 3600),
        ("2026-06", "expense", "Operations", 640),
        ("2026-07", "income", "Event revenue", 1800), ("2026-07", "expense", "Programs", 2800),
        ("2026-07", "expense", "Operations", 700),
        ("2026-08", "income", "Individual donations", 3500), ("2026-08", "expense", "Programs", 2500),
        ("2026-08", "expense", "Operations", 660),
        ("2026-09", "income", "Grants", 5000), ("2026-09", "expense", "Programs", 3900),
        ("2026-09", "expense", "Operations", 720),
        ("2026-09", "reserve", "Operating reserve balance", 21500),
    ]
    for period, kind, category, amount in rows:
        db.add(
            FinancialRecord(
                organization_id=org_id, period=period, kind=kind, category=category, amount_usd=amount,
                description="Synthetic demo figure", source="demo", is_demo=True,
            )
        )


def _seed_donations(db: Session, org_id: int) -> None:
    rows = [
        # donor, email, amount, received, method, acknowledged
        ("Sample Donor 01", "donor01@example.org", 500, date(2026, 8, 3), "check", True),
        ("Sample Donor 02", None, 1200, date(2026, 8, 19), "online", False),
        ("Sample Donor 03", "donor03@example.org", 75, date(2026, 9, 2), "online", False),
        ("Sample Donor 04", "donor04@example.org", 250, date(2026, 9, 14), None, False),
        ("Sample Donor 05", "donor05@example.org", 2500, date(2026, 9, 28), "wire", True),
        ("Sample Donor 06", None, 40, date(2026, 10, 5), "cash", False),
    ]
    for donor, email, amount, received, method, acknowledged in rows:
        db.add(
            Donation(
                organization_id=org_id, donor_name=donor, donor_email=email, amount_usd=amount,
                received_on=received, method=method, acknowledged=acknowledged,
                acknowledged_on=received if acknowledged else None, is_demo=True,
            )
        )
