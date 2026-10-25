"""A scripted stand-in for the OpenAI client, used only in tests.

It answers each structured-output request according to the schema name
(RequestAnalysis, LessonsOutput, ...). Replies are built from the data the
agent actually sent, so the workflow runs end to end offline and the same
way every time. Token counts here are fake, and they never appear in the app.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from backend.app.agents.orchestrator import keyword_analysis


def _payload(kw: dict) -> dict:
    text = kw.get("input", "")
    marker = "DATA (JSON):\n"
    if marker in text:
        body = text.split(marker, 1)[1].split("\n\nYOUR PREVIOUS REPLY WAS REJECTED", 1)[0]
        return json.loads(body)
    return {"query": text}


def analysis(p: dict, kw: dict) -> dict:
    return keyword_analysis(p["request"]).model_dump()


def lessons(p: dict, kw: dict) -> dict:
    events, refl = p["events"], p["reflections"]

    def text(r):
        return " ".join(str(r.get(k) or "") for k in ("did_not_go_as_planned", "unexpected_costs_or_complications", "change")).lower()

    food = [r for r in refl if any(w in text(r) for w in ("catering", "food"))] or refl[:1]
    overrun = next((r for r in food if "%" in text(r) or "over" in text(r)), food[0])
    praise = [r for r in refl if "worth" in str(r.get("what_worked") or "").lower()]
    return {
        "summary": f"Reviewed {len(events)} events and {len(refl)} reflections.",
        "themes": [{"name": "Food and catering costs", "polarity": "weakness" if len(food) > 1 else "mixed",
                    "description": "Several members flag food costs.", "evidence_event_ids": sorted({r["event_id"] for r in food}),
                    "evidence_reflection_ids": [r["id"] for r in food]}],
        "lessons": [
            {"kind": "what_worked", "theme": "speaker", "text": "A personal speaker moved guests to give.",
             "evidence_event_ids": [overrun["event_id"]], "evidence_reflection_ids": [overrun["id"]], "confidence": "medium"},
            {"kind": "recurring_problem", "theme": "food and catering costs", "text": "Food costs ran over at more than one event.",
             "evidence_event_ids": [], "evidence_reflection_ids": [r["id"] for r in food], "confidence": "high"},
            {"kind": "recommendation", "theme": "food and catering costs",
             "text": "Compare venue catering minimums before selecting a venue.", "evidence_event_ids": [],
             "evidence_reflection_ids": [r["id"] for r in food], "confidence": "high"},
        ],
        "disagreements": [{"topic": "Is the meal worth the cost?", "positions": ["Food costs are a problem", "The meal was worth it"],
                           "evidence_reflection_ids": [overrun["id"]] + [r["id"] for r in praise]}],
        "planning_constraints": [
            {"name": "lock_guest_count", "detail": "Lock the guest count two weeks out.", "evidence_reflection_ids": [overrun["id"]]},
            {"name": "compare_catering_minimums", "detail": "Compare venue catering minimums before choosing a venue.",
             "evidence_reflection_ids": [r["id"] for r in food]},
        ],
        "recommended_contingency_pct": 0.15,
        "contingency_evidence_reflection_ids": [overrun["id"]],
        "numeric_comparison_note": "The dinner had the highest net." if p["comparison"]["sufficient"] else None,
        "uncertainties": ["Small sample of demo events."],
    }


def strategy(p: dict, kw: dict) -> dict:
    options = p["options"]
    limits = {c["name"]: c.get("value") for c in p.get("constraints", [])}
    if "max_total_usd" in limits:  # revision: pick the cheapest option that meets the limit
        fitting = [o for o in options if o["total_usd"] <= float(limits["max_total_usd"])]
        chosen = sorted(fitting or options, key=lambda o: o["total_usd"])[0]
        changes = f"Switched to {chosen['venue']} to stay within the budget limit."
    else:  # first pass: the most elegant (most expensive) seated option
        chosen = sorted(options, key=lambda o: -o["total_usd"])[0]
        changes = None
    return {"summary": f"Recommend {chosen['venue']}.", "shortlist": [{"option_id": chosen["option_id"], "rank": 1,
            "rationale": "Fits the guest count and applies the guest-count lesson.", "lessons_applied": ["Lock the guest count"]}],
            "fundraising_strategy": ["Ticket tiers", "Paddle raise"], "logistics_notes": ["Lock guest count two weeks out"],
            "changes_from_previous": changes, "risks": [], "uncertainties": ["Synthetic venues."]}


def finance(p: dict, kw: dict) -> dict:
    verdict = (p.get("affordability") or {}).get("verdict", "n/a")
    return {"summary": f"Verdict: {verdict}.", "explanation": "Computed by code.", "conditions": ["Secure sponsors before deposits."],
            "risks": ["Attendance could fall short."], "questions_for_board": ["Approve the budget?"]}


def ack(p: dict, kw: dict) -> dict:
    return {"summary": f"{p['aggregate']['unacknowledged_gifts']} gifts need thank-you notes.",
            "subject": "Thank you, {{donor_name}}",
            "body": "Dear {{donor_name}},\nThank you for your gift of {{amount}} on {{date}}.\n[Board member name]",
            "review_items": [{"issue": "Large gifts without acknowledgment", "why_professional_review": "Receipt rules vary.",
                              "related_flag": "250_plus"}]}


def research_plan(p: dict, kw: dict) -> dict:
    return {"search_query": p["request"][:120], "geography": "New York, NY" if "new york" in p["request"].lower() else None,
            "count_requested": None, "opportunity_types": ["organization"], "focus_criteria": ["mental health", "belonging"]}


def _lvl(level: str, why: str) -> dict:
    return {"level": level, "explanation": why}


def mission(p: dict, kw: dict) -> dict:
    """Reads the sources it was given, like the real model: strong research alignment for research pages,
    community alignment for community pages, and costs only when a dollar figure is in the page excerpt."""
    import re as _re
    out = []
    for s in p["sources"]:
        text = f"{s['title']} {s['search_snippet']} {s['page_excerpt']}".lower()
        research = "research" in text or "clinical" in text
        community = any(w in text for w in ("community", "welcome", "neighbors", "walk", "circle"))
        mental = "mental-health" in text or "mental health" in text
        cost = _re.search(r"[^.]*\$\d[\d,]*[^.]*", s["page_excerpt"])
        out.append({
            "source_id": s["source_id"], "name": s["title"], "category": s.get("category_hint") or "organization",
            "geography": s.get("geography_hint"), "purpose": s["search_snippet"][:160],
            "activities": ["Workshops"] if "workshop" in text else [], "dates_text": s.get("date_claimed_by_search"),
            "partnership_types": ["Co-host"] if "partner" in text else [], "known_costs": cost.group(0).strip() if cost else None,
            "contribution_ways": ["Co-host an awareness event"],
            "charitable": {"mental_health": _lvl("strong" if mental else "unclear", "From the page."),
                           "eating_disorders": _lvl("strong" if "eating" in text else "none", "From the page."),
                           "community_wellbeing": _lvl("strong" if community else "unclear", "From the page.")},
            "philosophical": {"compassion": _lvl("partial", "Peer support."), "belonging_inclusion": _lvl("strong" if community else "unclear", "Welcomes newcomers."),
                              "human_connection": _lvl("strong" if community else "unclear", "Gatherings."),
                              "seen_heard_valued": _lvl("unclear" if research else "partial", "Not shown.")},
            "practical": {"geography": s.get("geography_hint") or "Unknown", "cost": "Not stated", "volunteers": "Unknown",
                          "timing": s.get("date_claimed_by_search") or "Not stated", "operations": "Unknown",
                          "blockers": ["Outside New York"] if (s.get("geography_hint") or "") == "Connecticut" else []},
            "evidence": {"reliability": "official_source", "verified_items": ["Purpose"], "unconfirmed_claims": [],
                         "missing_info": ["Contact person"]},
            "alignment_summary": "Aligned with the foundation's purpose areas per the page.",
            "next_step": "Ask about co-hosting a spring workshop.",
        })
    return {"summary": f"Analyzed {len(out)} sources.", "opportunities": out, "gaps": ["Check eligibility."]}


def drafts(p: dict, kw: dict) -> dict:
    out = []
    for t in p["targets"]:
        venue = t["suggested_type"] == "venue_inquiry"
        out.append({"target_id": t["target_id"], "draft_type": t["suggested_type"],
                    "subject": f"{'Inquiry' if venue else 'Introduction'}: {t['name']}",
                    "purpose": "To ask about a possible collaboration.", "foundation_background": "Smile Like Sab.",
                    "opportunity": "Event inquiry." if venue else (t["details"].get("purpose") or "")[:120],
                    "body": f"Hello {t['name']} team,\nWe are writing to ask whether you would be open to a short conversation.\n"
                            "[Board member name]", "next_step": "A 20-minute call.", "personalization_basis": "Target details.",
                    "source_ids": t["source_ids"]})
    return {"summary": f"{len(p['targets'])} drafts.", "drafts": out}


def recommendation(p: dict, kw: dict) -> dict:
    figs = p.get("figures", {})
    total = figs.get("top_option_total_usd")
    line = f"Projected total ${total:,.2f}." if total else "See specialist results."
    return {"headline": "Proceed with conditions", "recommendation": line, "rationale": ["Finance checks were run in code."],
            "options": [{"title": "Top option", "option_id": (p.get("option_ids") or [None])[0], "summary": line}],
            "risks": ["Attendance risk."], "decisions_for_board": ["Approve the venue inquiry."], "next_steps": ["Review drafts."],
            "lessons_applied": ["Lock the guest count."], "caveats": []}


DEFAULT_HANDLERS: dict[str, Callable[[dict, dict], Any]] = {
    "RequestAnalysis": analysis, "LessonsOutput": lessons, "EventStrategyOutput": strategy, "FinanceNarrative": finance,
    "AcknowledgmentTemplate": ack, "MissionAnalysis": mission, "ResearchPlan": research_plan, "DraftsOutput": drafts,
    "BoardRecommendation": recommendation,
}


class ScriptedClient:
    def __init__(self, overrides: dict[str, Callable[[dict, dict], Any]] | None = None):
        self.handlers = {**DEFAULT_HANDLERS, **(overrides or {})}
        self.calls: list[dict] = []
        self.responses = self
        self.models = SimpleNamespace(list=lambda: [SimpleNamespace(id=m) for m in ("gpt-6-luna", "gpt-6.1-sol", "gpt-6-sol", "gpt-6-astra")])

    def schema_calls(self, name: str) -> list[dict]:
        return [c for c in self.calls if c["text"]["format"]["name"] == name]

    def create(self, **kw):
        self.calls.append(kw)
        name = kw["text"]["format"]["name"]
        out = self.handlers[name](_payload(kw), kw)
        text = out if isinstance(out, str) else json.dumps(out)
        usage = SimpleNamespace(input_tokens=1200, output_tokens=300,
                                input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=0))
        return SimpleNamespace(model=kw["model"], output_text=text, status="completed", output=[], usage=usage)
