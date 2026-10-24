"""Synthetic research fixtures for the controlled demo.

These are NOT live web research. Every name ends in "(synthetic)", every link
points to the reserved example.org domain, and every SourceRecord built from
them has verification="synthetic". The UI shows a banner whenever a run uses
them. They exist so the multi-agent collaboration (the Finance check sending
the Events agent back for a revision) can be shown reliably and tested offline.

The venue numbers are chosen so a 150-guest seated gala under an $18,000 limit
fails the finance checks (both seated options exceed it even with no
contingency), and a reception-format revision passes them with any
contingency of up to 30%.
"""

from __future__ import annotations

SYNTHETIC_NOTE = "Synthetic fixture for the controlled demo, not live web research."

VENUES = [
    {
        "key": "lavender-loft", "name": "Lavender Loft (synthetic)", "neighborhood": "Flatiron", "city": "Manhattan",
        "capacity": {"seated_dinner": 180, "reception": 250}, "rental_usd": 9500.0,
        "fnb_per_guest_usd": {"seated_dinner": 145.0, "reception": 95.0}, "deposit_pct": 0.5,
        "notes": "Skylit loft with in-house catering; elegant for a seated gala.",
    },
    {
        "key": "hudson-garden-room", "name": "Hudson Garden Room (synthetic)", "neighborhood": "West Village", "city": "Manhattan",
        "capacity": {"seated_dinner": 160}, "rental_usd": 4000.0,
        "fnb_per_guest_usd": {"seated_dinner": 110.0}, "deposit_pct": 0.5,
        "notes": "Garden-view dining room; seated events only.",
    },
    {
        "key": "chelsea-atelier", "name": "Chelsea Atelier (synthetic)", "neighborhood": "Chelsea", "city": "Manhattan",
        "capacity": {"reception": 200}, "rental_usd": 1800.0,
        "fnb_per_guest_usd": {"reception": 58.0}, "deposit_pct": 0.3,
        "notes": "Gallery space for standing receptions with passed bites; flexible staging for a speaker.",
    },
    {
        "key": "harbor-salon", "name": "Harbor Salon (synthetic)", "neighborhood": "Battery Park City", "city": "Manhattan",
        "capacity": {"seated_dinner": 90, "reception": 120}, "rental_usd": 3000.0,
        "fnb_per_guest_usd": {"seated_dinner": 120.0, "reception": 70.0}, "deposit_pct": 0.4,
        "notes": "Intimate waterfront salon.",
    },
]

ORGANIZATIONS = [
    {
        "key": "recovery-circle", "title": "Recovery Circle Network (synthetic)", "category": "organization",
        "summary": "Peer-support circles for people recovering from eating disorders and their families.",
        "published": "2026-09-12",
    },
    {
        "key": "campus-minds", "title": "Campus Minds Collective (synthetic)", "category": "organization",
        "summary": "Student-run mental-health awareness programs across Connecticut campuses.",
        "published": "2026-08-30",
    },
    {
        "key": "body-image-fund", "title": "Body Image Research Fund: Spring Grant Call (synthetic)", "category": "research",
        "summary": "Small grants for early-career eating-disorder researchers; partner funders invited.",
        "published": "2026-10-01",
    },
    {
        "key": "awareness-week", "title": "Eating Disorder Awareness Week Community Walk (synthetic)", "category": "event",
        "summary": "Annual community walk that invites local foundations to host resource tables.",
        "published": "2026-07-15",
    },
    {
        "key": "city-running", "title": "City Running Club Charity Series (synthetic)", "category": "partnership",
        "summary": "Running club that donates race proceeds to a different local charity each month.",
        "published": "2026-06-20",
    },
]

SPONSORS = [
    {"key": "lilac-florists", "title": "Lilac & Co. Florists (synthetic)", "category": "partnership",
     "summary": "Local florist that sponsors in-kind arrangements for community events.", "published": None},
    {"key": "hudson-wellness", "title": "Hudson Wellness Studio (synthetic)", "category": "partnership",
     "summary": "Yoga and wellness studio with a community-giving program focused on mental health.", "published": None},
]


def fixture_url(kind: str, key: str) -> str:
    return f"https://example.org/synthetic/{kind}/{key}"
