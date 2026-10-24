"""Agent 6: Partnerships & Outreach.

Builds a target list from the event shortlist (venue inquiries), saved
research findings, and, for partner requests, a bounded search with links
verified by fetching. Then writes personalized drafts. Every draft is saved
with status "draft". SAM SPACE has no email-sending tool or mail integration,
so a person must copy a draft and send it themselves.
"""

from __future__ import annotations

from ..base import BaseAgent
from ..contracts import AgentName, AgentResult, AgentTask, Finding, SourceRecord
from ..outputs import DraftsOutput
from ..registry import OUTREACH_DRAFTS
from ..runtime import RunContext, dedupe_sources
from ..verification import action_claims

INSTRUCTIONS = """Write one personalized outreach draft per target (use only target_id values from "targets").
- venue_inquiry: ask about availability, capacity, pricing, deposits, and accessibility for the event details given.
- sponsor / partnership: explain the foundation's mission in Sabrina's memory and a specific, modest ask.
- personalization_basis: which facts from the target data you used. Do not invent facts about the recipient.
- Sign off with placeholders like [Board member name] and [Phone]. Never claim anything was sent, booked, or agreed.
- Do not include donor names, amounts, or private financial details."""



class PartnershipsOutreachAgent(BaseAgent):
    name = AgentName.PARTNERSHIPS_OUTREACH

    def execute(self, task: AgentTask, ctx: RunContext) -> AgentResult:
        targets: list[dict] = []
        sources: list[SourceRecord] = []
        warnings: list[str] = []
        event = task.inputs.get("event")

        for item in (task.inputs.get("shortlist") or [])[:2]:
            v = item["venue"]
            targets.append({"target_id": f"venue:{v['venue_key']}", "type": "venue_inquiry", "name": v["name"],
                            "details": {"neighborhood": v.get("neighborhood"), "format": item["event_format"], "notes": v.get("notes")},
                            "synthetic": v.get("verification") == "synthetic", "source_id": v.get("source_id")})

        want_partners = task.inputs.get("find_partners", False)
        if want_partners:
            topic = task.inputs.get("topic") or "Local businesses and organizations that sponsor mental-health or eating-disorder causes"
            found = self.tool(ctx, "search_web", query=topic, purpose="sponsors")
            warnings += found.warnings
            for h in (found.data or [])[:4]:
                check = self.tool(ctx, "fetch_source", url=h["url"], source_id=h["source_id"])
                src = check.sources[0] if check.sources else SourceRecord(id=h["source_id"], title=h["title"], url=h["url"], verification="unverified")
                src.title = h["title"]
                sources.append(src)
                targets.append({"target_id": h["source_id"], "type": "sponsor", "name": h["title"], "details": {"summary": h["snippet"]},
                                "synthetic": src.verification == "synthetic", "source_id": h["source_id"],
                                "link_verified": src.verification == "verified"})
        saved = self.tool(ctx, "read_saved_findings", categories=["partnership", "organization"]).data or []
        for f in [f for f in saved if f["saved"]][:2]:
            targets.append({"target_id": f"finding:{f['id']}", "type": "partnership", "name": f["title"],
                            "details": {"summary": f["summary"]}, "synthetic": f["verification"] == "synthetic",
                            "source_id": f"finding:{f['id']}"})
        if not targets:
            return self.result(task, "completed", "No outreach targets yet. Save opportunities in Mission Discovery first.",
                               next_steps=["Run Mission Discovery and save promising partners."])

        out = self.think(ctx, OUTREACH_DRAFTS, INSTRUCTIONS, {
            "foundation": "Sabrina Audrey Milone Foundation (Smile Like Sab)", "event": event, "targets": targets,
        }, DraftsOutput)
        by_id = {t["target_id"]: t for t in targets}
        made = []
        for d in out.drafts:
            target = by_id.get(d.target_id)
            if target is None:
                warnings.append(f"Ignored a draft for an unknown target ({d.target_id}).")
                continue
            if action_claims(d.body):
                warnings.append(f"Rejected a draft to {target['name']} that claimed an action was taken.")
                continue
            row = self.tool(ctx, "create_outreach_draft", draft_type=d.draft_type, recipient_org=target["name"], subject=d.subject,
                            body=d.body, personalization_basis=d.personalization_basis, is_synthetic_target=target["synthetic"])
            if row.ok:
                made.append({"id": row.data["id"], "recipient": target["name"], "subject": d.subject, "draft_type": d.draft_type,
                             "synthetic_target": target["synthetic"]})
        findings = [Finding(claim=f"Draft {m['draft_type'].replace('_', ' ')} to {m['recipient']}: “{m['subject']}”", kind="recommendation")
                    for m in made]
        return self.result(
            task, "completed", out.summary, findings=findings, sources=dedupe_sources(sources), warnings=warnings,
            assumptions=["Some recipients are synthetic demo fixtures."] if any(m["synthetic_target"] for m in made) else [],
            next_steps=["Review and personalize each draft in Partnerships & Outreach, then send it yourself if appropriate."],
            data={"drafts": made},
        )
