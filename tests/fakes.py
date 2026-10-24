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
    overrun = next((r for r in refl if "over" in (r["challenges"] or "").lower()), refl[0])
    return {
        "summary": f"Reviewed {len(events)} events and {len(refl)} reflections.",
        "lessons": [
            {"kind": "what_worked", "text": "A personal speaker moved guests to give.", "evidence_event_ids": [overrun["event_id"]],
             "evidence_reflection_ids": [overrun["id"]], "confidence": "medium"},
            {"kind": "recurring_problem", "text": "Catering costs rose after guest counts changed.", "evidence_event_ids": [],
             "evidence_reflection_ids": [overrun["id"]], "confidence": "high"},
        ],
        "disagreements": [{"topic": "Dinner value", "positions": ["Pledges were strong", "Pledges went uncollected"],
                           "evidence_reflection_ids": [r["id"] for r in refl if r["event_id"] == overrun["event_id"]]}],
        "planning_constraints": [{"name": "lock_guest_count", "detail": "Lock the guest count two weeks out.",
                                  "evidence_reflection_ids": [overrun["id"]]}],
        "recommended_contingency_pct": 0.15,
        "contingency_evidence_reflection_ids": [overrun["id"]],
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


def mission(p: dict, kw: dict) -> dict:
    return {"summary": "Found aligned organizations.", "gaps": ["Check eligibility."], "findings": [
        {"source_id": s["source_id"], "category": "organization", "alignment": "high", "summary": s["snippet"][:120],
         "date_text": s.get("published"), "uncertainty": "Synthetic fixture.", "why_relevant": "Mission aligned."}
        for s in p["sources"][:3]]}


def drafts(p: dict, kw: dict) -> dict:
    return {"summary": f"{len(p['targets'])} drafts.", "drafts": [
        {"target_id": t["target_id"], "draft_type": "venue_inquiry" if t["type"] == "venue_inquiry" else "sponsor",
         "subject": f"Inquiry: {t['name']}", "body": f"Hello {t['name']} team,\nWe are planning an event.\n[Board member name]",
         "personalization_basis": "Venue notes."} for t in p["targets"]]}


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
    "AcknowledgmentTemplate": ack, "MissionOutput": mission, "DraftsOutput": drafts, "BoardRecommendation": recommendation,
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
