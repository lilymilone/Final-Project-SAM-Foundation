"""Synthetic research fixtures for the controlled demo.

These are NOT live web research. Every name ends in "(synthetic)", every link
points to the reserved example.org domain, and every SourceRecord built from
them has verification="synthetic". The UI shows a banner whenever a run uses
them. They exist so the multi-agent collaboration (the Finance check sending
the Events agent back for a revision) can be shown reliably and tested offline.

The venue numbers make the controlled demo reliable:
  * a 150-guest seated gala under an $18,000 limit fails the finance checks,
    and a reception-format revision passes them
  * the seated venues carry food-and-beverage minimums, so the history lesson
    "food costs ran over" can trigger a revision on its own
  * Gramercy Hall publishes no pricing, so "Quote required" can be exercised
"""

from __future__ import annotations

SYNTHETIC_NOTE = "Synthetic fixture for the controlled demo, not live web research."

VENUES = [
    {
        "key": "lavender-loft", "name": "Lavender Loft (synthetic)", "neighborhood": "Flatiron", "city": "Manhattan",
        "address": "Flatiron, Manhattan (synthetic address)",
        "capacity": {"seated_dinner": 180, "reception": 250}, "capacity_quote": "Seats 180 for dinner; 250 for receptions.",
        "pricing_status": "published", "rental_usd": 9500.0, "fnb_per_guest_usd": {"seated_dinner": 145.0, "reception": 95.0},
        "fnb_minimum_usd": 25000.0, "deposit_pct": 0.5,
        "pricing_quote": "Rental $9,500; dinner from $145 per guest; $25,000 food-and-beverage minimum.",
        "catering": "In-house catering only; $25,000 food-and-beverage minimum.",
        "amenities": ["In-house catering", "Skylights", "Built-in AV", "Coat check"],
        "restrictions": ["In-house catering only", "Music must end by 11 pm"],
        "notes": "Skylit loft with in-house catering; elegant for a seated gala.",
    },
    {
        "key": "hudson-garden-room", "name": "Hudson Garden Room (synthetic)", "neighborhood": "West Village", "city": "Manhattan",
        "address": "West Village, Manhattan (synthetic address)",
        "capacity": {"seated_dinner": 160}, "capacity_quote": "Seats up to 160 for dinner.",
        "pricing_status": "published", "rental_usd": 4000.0, "fnb_per_guest_usd": {"seated_dinner": 110.0},
        "fnb_minimum_usd": 18000.0, "deposit_pct": 0.3,
        "pricing_quote": "Rental $4,000; dinner from $110 per guest; $18,000 food-and-beverage minimum.",
        "catering": "In-house catering only; $18,000 food-and-beverage minimum.",
        "amenities": ["Garden view", "In-house catering", "Wheelchair accessible"],
        "restrictions": ["Seated events only", "No outside caterers"],
        "notes": "Garden-view dining room; seated events only.",
    },
    {
        "key": "chelsea-atelier", "name": "Chelsea Atelier (synthetic)", "neighborhood": "Chelsea", "city": "Manhattan",
        "address": "Chelsea, Manhattan (synthetic address)",
        "capacity": {"reception": 200}, "capacity_quote": "Standing receptions up to 200.",
        "pricing_status": "published", "rental_usd": 1800.0, "fnb_per_guest_usd": {"reception": 58.0},
        "fnb_minimum_usd": None, "deposit_pct": 0.3,
        "pricing_quote": "Rental $1,800; outside caterers allowed (reception menus from about $58 per guest).",
        "catering": "Outside caterers allowed; no food-and-beverage minimum.",
        "amenities": ["Gallery lighting", "Small stage for a speaker", "Outside caterers allowed"],
        "restrictions": ["Standing receptions only", "Load-in after 4 pm"],
        "notes": "Gallery space for standing receptions with passed bites; flexible staging for a speaker.",
    },
    {
        "key": "gramercy-hall", "name": "Gramercy Hall (synthetic)", "neighborhood": "Gramercy", "city": "Manhattan",
        "address": "Gramercy, Manhattan (synthetic address)",
        "capacity": {"seated_dinner": 170, "reception": 220}, "capacity_quote": "Seats 170; receptions to 220.",
        "pricing_status": "quote_required", "rental_usd": None, "fnb_per_guest_usd": None, "fnb_minimum_usd": None, "deposit_pct": None,
        "pricing_quote": None, "catering": "Catering terms not published.",
        "amenities": ["Ballroom", "Dance floor", "Bridal suite"],
        "restrictions": ["Pricing on request only"],
        "notes": "Historic ballroom; the venue does not publish prices.",
    },
    {
        "key": "harbor-salon", "name": "Harbor Salon (synthetic)", "neighborhood": "Battery Park City", "city": "Manhattan",
        "address": "Battery Park City, Manhattan (synthetic address)",
        "capacity": {"seated_dinner": 90, "reception": 120}, "capacity_quote": "Seats 90; receptions to 120.",
        "pricing_status": "published", "rental_usd": 3000.0, "fnb_per_guest_usd": {"seated_dinner": 120.0, "reception": 70.0},
        "fnb_minimum_usd": 6000.0, "deposit_pct": 0.4,
        "pricing_quote": "Rental $3,000; dinner from $120 per guest; $6,000 minimum.",
        "catering": "Preferred caterer list; $6,000 minimum.",
        "amenities": ["Waterfront terrace"], "restrictions": ["Terrace closes at 9 pm"],
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
