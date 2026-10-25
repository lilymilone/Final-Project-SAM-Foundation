"""FoundationMission: the shared statement of purpose every relevant agent reads.

The Sabrina Audrey Milone Foundation was established in memory of Sabrina
Audrey Milone. Its guiding philosophy, "Be somebody who makes everybody feel
like somebody", is turned here into practical decision criteria. The agents
use them as questions to answer with evidence, not as feelings to express.
They must never assume a program creates belonging or improves mental health
without support from the sources.

The fit rubric below is explicit and deterministic (services/mission_fit.py).
There are no numeric scores, and clinical research is never down-ranked just
because its effect on belonging is less visible.
"""

from __future__ import annotations

PHILOSOPHY = "Be somebody who makes everybody feel like somebody."

FOUNDATION = {
    "name": "Sabrina Audrey Milone Foundation",
    "short_name": "Smile Like Sab",
    "established": "Established in memory of Sabrina Audrey Milone.",
    "purpose_areas": ["Mental health awareness", "Eating disorder research and support", "Community-building initiatives"],
    "philosophy": PHILOSOPHY,
}

CRITERIA = [
    {"key": "compassion", "label": "Compassion and kindness", "question": "Does it show practical care for the people it serves?"},
    {"key": "belonging", "label": "Belonging and inclusion", "question": "Does it welcome people regardless of background, ability, or circumstance?"},
    {"key": "mental_health", "label": "Mental health awareness", "question": "Does it increase understanding of, or access to, mental-health support?"},
    {"key": "eating_disorders", "label": "Eating disorder awareness and research", "question": "Does it advance awareness, treatment, or research on eating disorders?"},
    {"key": "connection", "label": "Human connection", "question": "Does it create real opportunities for people to connect?"},
    {"key": "community", "label": "Community building", "question": "Does it strengthen a community over time?"},
    {"key": "seen_valued", "label": "Helping people feel seen, heard, and valued", "question": "Does it give people a voice or recognition?"},
]

EVIDENCE_RULES = [
    "Judge each criterion only from what the sources say. If a source does not show it, answer 'unclear', not 'yes'.",
    "Never assume a program creates belonging or improves mental health without supporting evidence.",
    "Clinical and scientific research counts as strong alignment through eating-disorder or mental-health research, even when "
    "its effect on belonging is not directly visible.",
    "Be thoughtful, practical, and compassionate in tone, but not sentimental.",
]

# Explicit, defensible fit rubric (applied in code, never by the model).
FIT_RUBRIC = [
    {"label": "Strong fit", "rule": "Strong charitable alignment in at least one purpose area, a verified official source, and no blocking feasibility issue."},
    {"label": "Possible fit", "rule": "At least partial charitable alignment, but the source is unverified or key details are unconfirmed."},
    {"label": "Weak fit", "rule": "No more than an unclear connection to the purpose areas."},
    {"label": "Needs research", "rule": "Too much is missing to judge (no reachable source, or the purpose is unclear)."},
]

EVENT_CONSIDERATIONS = [
    "Is the event welcoming and inclusive (price points, format, language, who might feel left out)?",
    "Where are the opportunities for meaningful human connection?",
    "Accessibility: physical access, seating, sensory and dietary needs.",
    "Appropriate recognition of volunteers, sponsors, and participants.",
    "Alignment with the charitable purpose (mental health, eating disorders, community).",
    "These considerations complement financial feasibility; they never replace it.",
]

REFLECTION_LENSES = [
    "Did attendees appear to feel welcomed? (Board observations, not verified outcomes.)",
    "Which activities encouraged connection?",
    "Did volunteers feel appreciated?",
    "Which experiences created a sense of community?",
    "Were accessibility or inclusion problems reported?",
    "What could improve future events?",
]


def mission_brief() -> dict:
    """Compact, public description of the mission for agent payloads (no private data)."""
    return {"foundation": FOUNDATION, "criteria": [{"criterion": c["label"], "question": c["question"]} for c in CRITERIA],
            "evidence_rules": EVIDENCE_RULES}


def mission_instructions() -> str:
    crit = "; ".join(f"{c['label']} ({c['question']})" for c in CRITERIA)
    rules = " ".join(EVIDENCE_RULES)
    return (f'Foundation mission: {FOUNDATION["established"]} Purpose areas: {", ".join(FOUNDATION["purpose_areas"])}. '
            f'Guiding philosophy: "{PHILOSOPHY}" Decision criteria: {crit}. {rules}')


def public_config() -> dict:
    return {"foundation": FOUNDATION, "philosophy": PHILOSOPHY, "criteria": CRITERIA, "evidence_rules": EVIDENCE_RULES,
            "fit_rubric": FIT_RUBRIC, "event_considerations": EVENT_CONSIDERATIONS, "reflection_lenses": REFLECTION_LENSES}
