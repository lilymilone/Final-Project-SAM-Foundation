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
    Campaign,
    Donation,
    Donor,
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
    db.flush()
    _seed_donations(db, org.id)  # after the gala plan exists, so the gala campaign can link to it
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
        volunteers_count=24, repeat_participants=38, partnerships_formed=2, funds_directed_usd=9000,
        community_outcomes="Four local mental-health groups staffed resource tables, and 61 families signed up for follow-up "
                           "resource emails (sample).",
        reflections=[
            dict(author_label="Demo board member A", went_well="Turnout beat our goal and families stayed for the resource fair.",
                 challenges="Permit paperwork took six weeks; we almost missed the deadline.",
                 unexpected_costs="Food-truck vouchers for volunteers cost about $600 more than planned.",
                 attendee_feedback="Families loved the resource fair and asked for more shade and water stations.",
                 should_repeat="The resource fair with local mental-health groups.",
                 do_differently="Start the city permit process in January.",
                 advice="Budget food for volunteers separately from attendee food.", rating=5,
                 welcome_inclusion="Families with strollers and older walkers joined; the one-mile loop meant nobody was left behind.",
                 connection_moments="The resource fair, where families talked one-on-one with local mental-health groups.",
                 volunteer_appreciation="We thanked volunteers by name at the finish line, but their food ran short.",
                 accessibility_issues="Not enough shade or water stations for older walkers."),
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
                 advice="Food is where small events lose money; get every food quote in writing.", rating=3,
                 connection_moments="Volunteers who met that morning were still talking together at the end."),
        ],
    ),
    dict(
        name="Butterfly Benefit Dinner (sample)", event_date=date(2025, 10, 18), location="Greenwich, CT", event_type="dinner",
        venue="Harbor Club Dining Room (sample)", attendance=95, fundraising_goal_usd=30000, funds_raised_usd=31500,
        total_cost_usd=16800, sponsorship_usd=5000, sponsorship_info="Two table sponsors (sample).",
        summary="Sample seated dinner with a speaker on eating-disorder recovery and a silent auction.",
        notes="Synthetic demo record for teaching-staff testing.",
        volunteers_count=12, partnerships_formed=1, funds_directed_usd=12000,
        reflections=[
            dict(author_label="Demo board member A", went_well="The speaker moved people; auction pledges were strong.",
                 challenges="Catering was 22% over the quote after the guest count changed.",
                 unexpected_costs="The venue's food-and-beverage minimum applied on top of the per-head price change.",
                 attendee_feedback="Guests said the speaker was the heart of the night.",
                 should_repeat="A personal recovery speaker.",
                 do_differently="Lock the guest count two weeks out and get the per-head price in writing.",
                 advice="Treat catering as the biggest budget risk.", rating=4,
                 welcome_inclusion="Some first-time guests told me they felt out of place at a $250 dinner.",
                 connection_moments="After the recovery speaker, strangers at my table talked about their own families."),
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
                 advice="Do not cut the meal to save money.", rating=5,
                 volunteer_appreciation="Volunteers ate after the guests and some left hungry.",
                 accessibility_issues="The dining room had steps at the entrance, and one guest needed help getting in."),
        ],
    ),
    dict(
        name="Campus Wellness Panel (sample)", event_date=date(2026, 2, 12), location="New Haven, CT", event_type="panel",
        venue="Campus auditorium (sample)", attendance=120, fundraising_goal_usd=3000, funds_raised_usd=2600,
        total_cost_usd=900, sponsorship_usd=0, sponsorship_info="No sponsors (sample).",
        summary="Sample student panel on body image and asking for help, co-hosted with a campus group.",
        notes="Synthetic demo record for teaching-staff testing.",
        volunteers_count=6, partnerships_formed=1,
        community_outcomes="The co-hosting campus group asked to repeat the panel in the fall (sample).",
        reflections=[
            dict(author_label="Demo board member B", went_well="Students asked for a follow-up session.",
                 challenges="Low fundraising; this was an awareness event, not a fundraiser.",
                 unexpected_costs="Pizza for 120 students cost more than the room.",
                 attendee_feedback="Students wanted a quieter space to talk afterwards.",
                 should_repeat="Co-hosting with a student group.",
                 do_differently="Pair awareness events with a small, clear giving ask.",
                 advice="Decide up front whether an event is for awareness or for fundraising.", rating=4,
                 welcome_inclusion="Students said they felt heard because the panelists were their peers.",
                 accessibility_issues="Students wanted a quieter space to talk afterwards."),
        ],
    ),
]

EVENT_FIELDS = ("event_date", "location", "event_type", "venue", "attendance", "fundraising_goal_usd", "funds_raised_usd",
                "total_cost_usd", "sponsorship_usd", "sponsorship_info", "summary", "notes", "volunteers_count",
                "repeat_participants", "partnerships_formed", "funds_directed_usd", "community_outcomes")
REFLECTION_FIELDS = ("went_well", "challenges", "unexpected_costs", "attendee_feedback", "should_repeat", "do_differently", "advice", "rating",
                     "welcome_inclusion", "connection_moments", "volunteer_appreciation", "accessibility_issues")


def _seed_history(db: Session, org_id: int) -> None:
    for data in DEMO_HISTORY:
        event = HistoricalEvent(organization_id=org_id, is_demo=True, name=data["name"], **{k: data.get(k) for k in EVENT_FIELDS})
        db.add(event)
        db.flush()
        for r in data["reflections"]:
            db.add(BoardReflection(historical_event_id=event.id, is_demo=True, author_label=r["author_label"],
                                   **{k: r.get(k) for k in REFLECTION_FIELDS}))


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
            if getattr(event, k) in (None, "") and data.get(k) not in (None, ""):
                setattr(event, k, data[k])
                changes += 1
        existing = {r.author_label: r for r in db.scalars(select(BoardReflection).where(
            BoardReflection.historical_event_id == event.id, BoardReflection.is_demo.is_(True)))}
        for r in data["reflections"]:
            row = existing.get(r["author_label"])
            if row is None:
                db.add(BoardReflection(historical_event_id=event.id, is_demo=True, author_label=r["author_label"],
                                       **{k: r.get(k) for k in REFLECTION_FIELDS}))
                changes += 1
                continue
            for k in REFLECTION_FIELDS:
                if getattr(row, k) in (None, "") and r.get(k) not in (None, ""):
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
    ] + DEMO_BOOK_ADDITIONS
    for period, kind, category, amount in rows:
        restriction, purpose = DEMO_BOOK_TAGS.get(category, (None, None))
        budget = kind.startswith("budget_")
        db.add(
            FinancialRecord(
                organization_id=org_id, period=period, kind=kind, category=category, amount_usd=amount,
                description="Synthetic demo figure", source="demo", is_demo=True, restriction=None if budget else restriction,
                purpose=purpose, currency="USD", verification="demo", **(DEMO_BUDGET if budget else {}),
            )
        )


# Prompt 6: restriction and purpose tags for the demo books, and a cash balance. The $5,000 grant is
# restricted to programs, so it is never counted as spendable for events. Totals are unchanged.
DEMO_BOOK_TAGS = {
    "Individual donations": ("unrestricted", None), "Event revenue": ("unrestricted", None),
    "Grants": ("temporarily_restricted", None), "Programs": (None, "program"), "Operations": (None, "operations"),
    "Operating reserve balance": ("unrestricted", None), "Cash in bank (all accounts)": (None, None),
}
DEMO_BOOK_ADDITIONS = [
    ("2026-09", "cash", "Cash in bank (all accounts)", 26500),
    # A board-approved budget for the same five months, so budget-vs-actual variance can be explained.
    ("2026-09", "budget_income", "Individual donations", 12000), ("2026-09", "budget_income", "Event revenue", 2500),
    ("2026-09", "budget_income", "Grants", 5000), ("2026-09", "budget_expense", "Programs", 16000),
    ("2026-09", "budget_expense", "Operations", 3000),
]
DEMO_BUDGET = {"period_months": 5, "period_label": "Budget, May to Sep 2026 (sample)"}


def upgrade_demo_books(db: Session) -> int:
    """Tag older demo ledgers and add the demo cash balance. Never touches non-demo records."""
    changes = 0
    demo = db.scalars(select(FinancialRecord).where(FinancialRecord.is_demo.is_(True))).all()
    if not demo:
        return 0
    for r in demo:
        restriction, purpose = DEMO_BOOK_TAGS.get(r.category, (None, None))
        if r.restriction is None and restriction:
            r.restriction, changes = restriction, changes + 1
        if r.purpose is None and purpose:
            r.purpose, changes = purpose, changes + 1
        if r.verification is None:
            r.verification, r.currency = "demo", "USD"
    org_id = demo[0].organization_id
    for period, kind, category, amount in DEMO_BOOK_ADDITIONS:
        if not any(r.kind == kind and r.category == category for r in demo):
            budget = kind.startswith("budget_")
            db.add(FinancialRecord(organization_id=org_id, period=period, kind=kind, category=category, amount_usd=amount,
                                   description="Synthetic demo figure", source="demo", is_demo=True, currency="USD", verification="demo",
                                   purpose=DEMO_BOOK_TAGS.get(category, (None, None))[1], **(DEMO_BUDGET if budget else {})))
            changes += 1
    return changes


# Fictional demonstration donations (Prompt 6). Every donor and figure is invented and labeled
# "Sample". Fields cover the cases the compliance checks look for: a $250+ gift awaiting
# acknowledgment, a pledge (never counted as received), an in-kind gift (no value assigned),
# a gala ticket where the donor receives a dinner, a restricted gift, and a likely duplicate.
DEMO_CAMPAIGNS = [
    # name, kind, goal, starts, ends, link
    ("Fall Community Appeal 2026 (sample)", "campaign", 10000, date(2026, 8, 1), date(2026, 12, 31), None),
    ("Manhattan Spring Gala 2027 (sample)", "event", 40000, date(2026, 9, 1), date(2027, 4, 24), "plan"),
    ("Eating Disorder Research Fund (sample)", "campaign", None, None, None, None),
]
DEMO_DONATIONS = [
    # donor, email, amount, received, method, ack_status, campaign idx, type, restriction, payment, extras
    ("Sample Donor 01", "donor01@example.org", 500, date(2026, 8, 3), "check", "completed", 0, "monetary", "unrestricted", "received", {}),
    ("Sample Donor 02", None, 1200, date(2026, 8, 19), "online", "not_started", 0, "monetary", None, "received", {}),
    ("Sample Donor 03", "donor03@example.org", 75, date(2026, 9, 2), "online", "not_started", 0, "monetary", "unrestricted", "received", {}),
    ("Sample Donor 04", "donor04@example.org", 250, date(2026, 9, 14), None, "prepared", 0, "monetary", "unrestricted", "received", {}),
    ("Sample Donor 05", "donor05@example.org", 2500, date(2026, 9, 28), "wire", "completed", 2, "monetary", "temporarily_restricted", "received",
     {"designation": "Eating-disorder research (donor restricted)"}),
    ("Sample Donor 06", None, 40, date(2026, 10, 5), "cash", "not_started", None, "monetary", None, "received", {}),
    ("Sample Donor 07", "sponsor07@example.org", 5000, date(2026, 10, 1), None, "not_started", 1, "sponsorship", "unrestricted", "pledged",
     {"notes": "Sample: pledged gala sponsorship; not yet received."}),
    ("Sample Donor 08", "donor08@example.org", 250, date(2026, 10, 9), "online", "not_started", 1, "event_ticket", "unrestricted", "received",
     {"goods_services_value_usd": 95.0, "notes": "Sample: gala ticket; the guest receives a dinner valued at about $95."}),
    ("Sample Donor 09", "florist09@example.org", 0, date(2026, 10, 12), None, "not_started", 1, "in_kind", None, "received",
     {"in_kind_description": "Floral arrangements for the gala tables (sample)", "notes": "Sample: in-kind gift; the foundation does not assign a value."}),
    ("Sample Donor 01", "donor01@example.org", 500, date(2026, 10, 14), "check", "not_started", 0, "monetary", "unrestricted", "received", {}),
    ("Sample Donor 03", "donor03@example.org", 75, date(2026, 9, 2), "online", "not_started", 0, "monetary", "unrestricted", "received",
     {"notes": "Sample: entered twice by mistake, so the duplicate check has something to find."}),
]


def _demo_donors(db: Session, org_id: int) -> dict[str, Donor]:
    donors = {d.name: d for d in db.scalars(select(Donor).where(Donor.organization_id == org_id))}
    for name, email, *_ in DEMO_DONATIONS:
        if name not in donors:
            donors[name] = Donor(organization_id=org_id, donor_code=f"DNR-{len(donors) + 1:04d}", name=name, email=email, is_demo=True)
            db.add(donors[name])
    db.flush()
    return donors


def _demo_campaigns(db: Session, org_id: int) -> list[Campaign]:
    existing = {c.name: c for c in db.scalars(select(Campaign).where(Campaign.organization_id == org_id))}
    plan = db.scalar(select(EventPlan).where(EventPlan.organization_id == org_id, EventPlan.name.like("Manhattan Spring Gala%")))
    out = []
    for name, kind, goal, start, end, link in DEMO_CAMPAIGNS:
        c = existing.get(name) or Campaign(organization_id=org_id, name=name, kind=kind, goal_usd=goal, starts_on=start, ends_on=end, is_demo=True)
        if link == "plan" and plan is not None:
            c.event_plan_id = plan.id
        db.add(c)
        out.append(c)
    db.flush()
    return out


def _donation_fields(row, donors, campaigns) -> dict:
    name, email, amount, received, method, ack, camp, ctype, restriction, payment, extras = row
    return {"donor_name": name, "donor_email": email, "amount_usd": amount, "received_on": received, "method": method,
            "ack_status": ack, "acknowledged": ack == "completed", "acknowledged_on": received if ack == "completed" else None,
            "campaign_id": campaigns[camp].id if camp is not None else None, "contribution_type": ctype, "restriction": restriction,
            "payment_status": payment, "donor_id": donors[name].id, "currency": "USD", "source": "demo",
            "designation": extras.get("designation", "General fund"), "notes": extras.get("notes", ""),
            "in_kind_description": extras.get("in_kind_description"), "goods_services_value_usd": extras.get("goods_services_value_usd")}


def _seed_donations(db: Session, org_id: int) -> None:
    donors, campaigns = _demo_donors(db, org_id), _demo_campaigns(db, org_id)
    for row in DEMO_DONATIONS:
        db.add(Donation(organization_id=org_id, is_demo=True, **_donation_fields(row, donors, campaigns)))


def upgrade_demo_donations(db: Session) -> int:
    """Bring older demo donation tables up to the Prompt 6 structure. Only demo rows are touched."""
    demo = db.scalars(select(Donation).where(Donation.is_demo.is_(True)).order_by(Donation.id)).all()
    if not demo or all(d.donor_id is not None for d in demo):
        return 0
    org_id = demo[0].organization_id
    donors, campaigns = _demo_donors(db, org_id), _demo_campaigns(db, org_id)
    changes, used = 0, set()
    for row in DEMO_DONATIONS:
        fields = _donation_fields(row, donors, campaigns)
        match = next((d for d in demo if d.id not in used and d.donor_name == row[0] and d.amount_usd == row[2] and d.received_on == row[3]), None)
        if match is None:
            db.add(Donation(organization_id=org_id, is_demo=True, **fields))
        else:
            used.add(match.id)
            for k, v in fields.items():
                setattr(match, k, v)
        changes += 1
    return changes
