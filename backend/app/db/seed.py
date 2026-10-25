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

from sqlalchemy import select
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
            ticket_price_usd=250,
            instructions="A warm, personal evening honoring Sabrina, with a short talk from a recovery speaker.",
            status="planning",
            notes="Sample plan for the demo. Venue not chosen. Board wants a warm, personal evening.",
            is_demo=True,
        )
    )
    return org


# Synthetic past events and structured reflections. The reflections disagree on
# purpose: several members flag food costs, while one argues the meal was worth it.
DEMO_HISTORY = [
    dict(
        name="Spring Awareness Walk (sample)", event_date=date(2025, 4, 26), location="New Haven, CT", event_type="community walk",
        venue="Lighthouse Point Park (sample)", attendance=210, fundraising_goal_usd=12000, funds_raised_usd=14200,
        total_cost_usd=3100, sponsorship_usd=1800, sponsorship_info="Water and T-shirts from two local businesses (sample).",
        summary="Sample 5K awareness walk with a resource fair from local mental-health groups.",
        notes="Synthetic demo record for teaching-staff testing.",
        reflections=[
            dict(author_label="Demo board member A", went_well="Turnout beat our goal and families stayed for the resource fair.",
                 challenges="Permit paperwork took six weeks; we almost missed the deadline.",
                 unexpected_costs="Food-truck vouchers for volunteers cost about $600 more than planned.",
                 attendee_feedback="Families loved the resource fair and asked for more shade and water stations.",
                 should_repeat="The resource fair with local mental-health groups.",
                 do_differently="Start the city permit process in January.",
                 advice="Budget food for volunteers separately from attendee food.", rating=5),
            dict(author_label="Demo board member B", went_well="Local businesses sponsored water and T-shirts.",
                 challenges="Online registration closed early by mistake.",
                 unexpected_costs="Rush printing after a sponsor logo arrived late.",
                 attendee_feedback="Runners wanted clearer course signs.",
                 should_repeat="Business sponsorships for water and shirts.",
                 do_differently="Test the registration form with a friend before launch.",
                 advice="Lock sponsor logos a month before printing.", rating=4),
            dict(author_label="Demo board member C", went_well="Volunteers were energized and on time.",
                 challenges="The food trucks ran out of food early.",
                 unexpected_costs="One food truck charged an $800 minimum guarantee we had not budgeted.",
                 attendee_feedback="Some families left early because food ran out.",
                 should_repeat="The volunteer team structure.",
                 do_differently="Read vendor minimums before signing.",
                 advice="Food is where small events lose money; get every food quote in writing.", rating=3),
        ],
    ),
    dict(
        name="Butterfly Benefit Dinner (sample)", event_date=date(2025, 10, 18), location="Greenwich, CT", event_type="dinner",
        venue="Harbor Club Dining Room (sample)", attendance=95, fundraising_goal_usd=30000, funds_raised_usd=31500,
        total_cost_usd=16800, sponsorship_usd=5000, sponsorship_info="Two table sponsors (sample).",
        summary="Sample seated dinner with a speaker on eating-disorder recovery and a silent auction.",
        notes="Synthetic demo record for teaching-staff testing.",
        reflections=[
            dict(author_label="Demo board member A", went_well="The speaker moved people; auction pledges were strong.",
                 challenges="Catering was 22% over the quote after the guest count changed.",
                 unexpected_costs="The venue's food-and-beverage minimum applied on top of the per-head price change.",
                 attendee_feedback="Guests said the speaker was the heart of the night.",
                 should_repeat="A personal recovery speaker.",
                 do_differently="Lock the guest count two weeks out and get the per-head price in writing.",
                 advice="Treat catering as the biggest budget risk.", rating=4),
            dict(author_label="Demo board member C", went_well="Volunteers ran check-in smoothly.",
                 challenges="Several pledges were never collected after the event.",
                 unexpected_costs="Rush delivery for two auction items.",
                 attendee_feedback="A few guests found the program too long.",
                 should_repeat="The volunteer check-in team.",
                 do_differently="Collect payment at the table, not by follow-up.",
                 advice="Shorten the program to under an hour.", rating=3),
            dict(author_label="Demo board member D", went_well="The plated dinner made guests feel honored. It was worth the cost.",
                 challenges="The seating chart changed at the last minute.",
                 unexpected_costs="None beyond catering.",
                 attendee_feedback="Several donors said the meal set the tone for giving.",
                 should_repeat="A seated, plated dinner. Guests give more when they feel cared for.",
                 do_differently="Keep the dinner format; trim decor instead of food.",
                 advice="Do not cut the meal to save money.", rating=5),
        ],
    ),
    dict(
        name="Campus Wellness Panel (sample)", event_date=date(2026, 2, 12), location="New Haven, CT", event_type="panel",
        venue="Campus auditorium (sample)", attendance=120, fundraising_goal_usd=3000, funds_raised_usd=2600,
        total_cost_usd=900, sponsorship_usd=0, sponsorship_info="No sponsors (sample).",
        summary="Sample student panel on body image and asking for help, co-hosted with a campus group.",
        notes="Synthetic demo record for teaching-staff testing.",
        reflections=[
            dict(author_label="Demo board member B", went_well="Students asked for a follow-up session.",
                 challenges="Low fundraising; this was an awareness event, not a fundraiser.",
                 unexpected_costs="Pizza for 120 students cost more than the room.",
                 attendee_feedback="Students wanted a quieter space to talk afterwards.",
                 should_repeat="Co-hosting with a student group.",
                 do_differently="Pair awareness events with a small, clear giving ask.",
                 advice="Decide up front whether an event is for awareness or for fundraising.", rating=4),
        ],
    ),
]

EVENT_FIELDS = ("event_date", "location", "event_type", "venue", "attendance", "fundraising_goal_usd", "funds_raised_usd",
                "total_cost_usd", "sponsorship_usd", "sponsorship_info", "summary", "notes")
REFLECTION_FIELDS = ("went_well", "challenges", "unexpected_costs", "attendee_feedback", "should_repeat", "do_differently", "advice", "rating")


def _seed_history(db: Session, org_id: int) -> None:
    for data in DEMO_HISTORY:
        event = HistoricalEvent(organization_id=org_id, is_demo=True, name=data["name"], **{k: data[k] for k in EVENT_FIELDS})
        db.add(event)
        db.flush()
        for r in data["reflections"]:
            db.add(BoardReflection(historical_event_id=event.id, is_demo=True, author_label=r["author_label"],
                                   **{k: r[k] for k in REFLECTION_FIELDS}))


def upgrade_demo_history(db: Session) -> int:
    """Bring an older demo database up to date: fill only empty new fields on
    demo rows and add demo reflections that are missing. Never touches
    non-demo (real) records or any text that is already set."""
    changes = 0
    plan = db.scalar(select(EventPlan).where(EventPlan.is_demo.is_(True), EventPlan.name.like("Manhattan Spring Gala%")))
    if plan is not None and plan.ticket_price_usd is None:
        plan.ticket_price_usd = 250
        plan.instructions = plan.instructions or "A warm, personal evening honoring Sabrina, with a short talk from a recovery speaker."
        changes += 1
    for data in DEMO_HISTORY:
        event = db.scalar(select(HistoricalEvent).where(HistoricalEvent.name == data["name"], HistoricalEvent.is_demo.is_(True)))
        if event is None:
            continue
        for k in EVENT_FIELDS:
            if getattr(event, k) in (None, "") and data[k] not in (None, ""):
                setattr(event, k, data[k])
                changes += 1
        existing = {r.author_label: r for r in db.scalars(select(BoardReflection).where(
            BoardReflection.historical_event_id == event.id, BoardReflection.is_demo.is_(True)))}
        for r in data["reflections"]:
            row = existing.get(r["author_label"])
            if row is None:
                db.add(BoardReflection(historical_event_id=event.id, is_demo=True, author_label=r["author_label"],
                                       **{k: r[k] for k in REFLECTION_FIELDS}))
                changes += 1
                continue
            for k in REFLECTION_FIELDS:
                if getattr(row, k) in (None, "") and r[k] not in (None, ""):
                    setattr(row, k, r[k])
                    changes += 1
    return changes


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
