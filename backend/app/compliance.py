"""Compliance references the Donations & Compliance agent may cite.

Every compliance statement in SAM SPACE cites one of these sources, with its
jurisdiction and the date the page was checked. Two kinds:

  verified_requirement  the rule as the authoritative page states it (pages checked 2026-10-25)
  general_guidance      depends on facts SAM SPACE cannot verify (where the foundation solicits,
                        its size, its accounting); always routed to a professional

These are summaries for a volunteer board, not legal or tax advice. SAM SPACE
never determines whether a gift is deductible and never files anything. A
reference older than STALE_AFTER_DAYS is flagged to be re-checked.
"""

from __future__ import annotations

from datetime import date

CHECKED_ON = "2026-10-25"
STALE_AFTER_DAYS = 365

REFERENCES: dict[str, dict] = {
    "irs-written-ack": {
        "title": "Charitable contributions: written acknowledgments",
        "authority": "Internal Revenue Service", "jurisdiction": "United States (federal)", "kind": "verified_requirement",
        "url": "https://www.irs.gov/charities-non-profits/charitable-organizations/charitable-contributions-written-acknowledgments",
        "source_updated": "Page last reviewed or updated June 28, 2026",
        "points": ["A donor needs a written acknowledgment from the charity to deduct a single contribution of $250 or more.",
                   "It should state the organization's name and the amount of a cash gift, or describe (not value) a non-cash gift.",
                   "It should say whether the charity provided goods or services in return, and if so describe them with a good-faith "
                   "estimate of their value."],
    },
    "irs-quid-pro-quo": {
        "title": "Charitable contributions: quid pro quo contributions",
        "authority": "Internal Revenue Service", "jurisdiction": "United States (federal)", "kind": "verified_requirement",
        "url": "https://www.irs.gov/charities-non-profits/charitable-organizations/charitable-contributions-quid-pro-quo-contributions",
        "source_updated": "Page last reviewed or updated June 28, 2026",
        "points": ["When a payment over $75 is partly a gift and partly for goods or services (for example, a gala dinner), the "
                   "charity must give a written disclosure statement.",
                   "The statement says the deductible amount is limited to the amount above the value of what the donor received, "
                   "and gives a good-faith estimate of that value.",
                   "The penalty for failing to disclose is $10 per contribution, up to $5,000 per fundraising event or mailing, "
                   "unless the failure had reasonable cause. Some exceptions apply (e.g. insubstantial value)."],
    },
    "irs-990-series": {
        "title": "Form 990 series: which forms do exempt organizations file",
        "authority": "Internal Revenue Service", "jurisdiction": "United States (federal)", "kind": "verified_requirement",
        "url": "https://www.irs.gov/charities-non-profits/form-990-series-which-forms-do-exempt-organizations-file-filing-phase-in",
        "source_updated": "Page last reviewed or updated June 28, 2026",
        "points": ["Form 990-N (e-Postcard): gross receipts normally $50,000 or less.",
                   "Form 990-EZ: gross receipts under $200,000 and total assets under $500,000.",
                   "Form 990: gross receipts $200,000 or more, or total assets $500,000 or more."],
    },
    "ny-charities-registration": {
        "title": "Charities registration (New York Attorney General, Charities Bureau)",
        "authority": "New York State Office of the Attorney General", "jurisdiction": "New York State", "kind": "general_guidance",
        "url": "https://ag.ny.gov/resources/organizations/charities-nonprofits-fundraisers/charities-registration",
        "source_updated": "Official state agency page",
        "points": ["Most organizations that hold charitable assets, do charitable work, or solicit contributions in New York must "
                   "register with the Charities Bureau; some are exempt.",
                   "Registered organizations have annual filing requirements. Whether and how this applies to the foundation is "
                   "a question for counsel."],
    },
    "ct-charities-registration": {
        "title": "General information on the Connecticut Solicitation of Charitable Funds Act",
        "authority": "Connecticut Department of Consumer Protection", "jurisdiction": "Connecticut", "kind": "general_guidance",
        "url": "https://portal.ct.gov/dcp/charities/general-information-on-the-connecticut-solicitation-of-charitable-funds-act",
        "source_updated": "Official state agency page",
        "points": ["Organizations that solicit charitable contributions in Connecticut must register with the Department of "
                   "Consumer Protection before soliciting, unless they qualify for and claim an exemption.",
                   "Whether the foundation is registered or exempt should be confirmed with counsel or the Department."],
    },
}


def reference(ref_id: str, today: date | None = None) -> dict | None:
    ref = REFERENCES.get(ref_id)
    if ref is None:
        return None
    today = today or date.today()
    stale = (today - date.fromisoformat(CHECKED_ON)).days > STALE_AFTER_DAYS
    return {"id": ref_id, **ref, "checked_on": CHECKED_ON, "stale": stale,
            "note": "Re-check this source before relying on it." if stale else None}


def public_references() -> list[dict]:
    return [reference(k) for k in REFERENCES]
