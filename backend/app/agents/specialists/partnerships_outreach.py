"""Agent 6: Partnerships & Outreach.

Drafts only. The agent's allow-list is read_saved_findings and
create_outreach_draft: it has no web, mail, messaging, or scheduling tool, and
the registry refuses to register any tool named like send_email,
send_message, contact_organization, schedule_outreach, publish_message, or
make_commitment. Every draft is saved with status "draft"; a person copies
it and sends it outside SAM SPACE if the board agrees.

Targets come from the Orchestrator: verified opportunities handed over from
Mission Discovery (with their sources and uncertainty) or the Event Studio
venue shortlist. Code then rejects any draft that claims an action was taken,
implies a relationship that does not exist, commits the foundation to
anything, or quotes a dollar amount the research does not contain. Rejected
drafts get one bounded rewrite with the reasons; anything still failing is
dropped with a warning.
"""

from __future__ import annotations

import re

from ...mission import FOUNDATION, PHILOSOPHY
from ...safety.policy import wrap_untrusted
from ..base import KNOWLEDGE_RULES, BaseAgent
from ..contracts import AgentName, AgentResult, AgentTask, Finding
from ..outputs import DRAFT_TYPES, DraftsOutput
from ..registry import OUTREACH_DRAFTS, OUTREACH_PERSONALIZED
from ..runtime import RunContext
from ..verification import acknowledges_relationship, collect_amounts, outreach_violations

CONTACT_RULES = """Contact details: each target has a "contact" checked on the organization's official website. Write an email
address only if it is contact.email, exactly. Never write any other email address, any phone number, or the name of a person.
If contact.email is null, write no address at all: the board will use the official contact page."""

INSTRUCTIONS = f"""Write one outreach draft per target (use only target_id values from "targets").
Fields:
- draft_type: the target's suggested_type unless the target data clearly fits another of: {", ".join(DRAFT_TYPES)}.
- subject; purpose (one sentence: why we are writing); foundation_background (2-3 sentences from "foundation" and the
  shareable facts in "foundation_knowledge");
  opportunity (the specific opportunity, from the target data); next_step (one low-commitment ask, e.g. a short call);
  personalization_basis (which target facts you used); source_ids (the target's source_ids you relied on).
- body: the complete, ready-to-review message, greeting to sign-off. Warm and professional, specific to the recipient,
  under 230 words.
Rules:
- Use only facts in the target data. Never invent a past relationship, conversation, introduction, or shared history.
  This is a first contact unless the data says otherwise.
- Never commit the foundation to money, sponsorship, volunteers, or dates. Ask questions; do not promise.
- If dates conflict or information is missing, ask the recipient to confirm it instead of stating it.
- Mention a dollar amount only if it appears in the target data (e.g. a published table fee).
- The guiding philosophy ("{PHILOSOPHY}") may appear once if it fits naturally; it is never required.
- Sign off with placeholders: [Board member name], [Title], Sabrina Audrey Milone Foundation, [Email], [Phone].
- Never claim anything was sent, booked, agreed, or approved. No donor names, amounts, or private financial details.
- By type: a charitable or research organization: express interest in learning about its programs, impact, and how the
  foundation might support or collaborate, explain the mission alignment, and politely ask for more information; never
  promise or imply a donation or grant. A sponsor: describe the sponsorship opportunity and possible benefits as proposals,
  not guarantees, and invite a conversation. A research initiative: ask about the work and possible support; never invent a
  relationship with researchers or institutions.
""" + CONTACT_RULES

VENUE_INSTRUCTIONS = """Write one short venue-inquiry draft per target (use only target_id values from "targets").
- draft_type: venue_inquiry. Ask about availability, capacity, pricing, deposits, nonprofit rates, and accessibility for the
  event details given. purpose, foundation_background, opportunity, next_step: one sentence each.
- source_ids: the target's source_ids. personalization_basis: which venue facts you used.
- Use only facts in the data; do not invent anything about the venue. Never claim anything was sent, booked, or agreed.
- Include: the venue name, a short introduction to the foundation, the proposed event concept, the estimated attendance,
  questions about availability, capacity, pricing, and any nonprofit accommodations (ask about catering only for a meal or
  reception), and a professional closing.
- Make each draft specific to its venue: mention at least one detail from that venue's own data (its neighborhood, format,
  amenities, or published terms), so no two drafts read the same.
- Sign off with placeholders like [Board member name] and [Phone]. No donor names, amounts, or private financial details.
""" + CONTACT_RULES

KNOWLEDGE_INSTRUCTIONS = """Describing the foundation ("foundation_knowledge"):
- Introduce the foundation accurately from these facts (for example, that it was established in Sabrina's memory and
  supports mental health awareness, eating disorder research, and community connection). Quote the guiding philosophy only
  where it fits naturally.
- Only facts with shareable_in_outreach true may appear in a draft. The others (costs, internal notes, board details) are
  background for you and must stay out of the message.
- Adapt the introduction to the recipient instead of repeating one paragraph: a venue inquiry centers on the proposed event;
  a research or charity introduction centers on the shared charitable purpose; a sponsorship inquiry explains the fundraising
  opportunity and who it reaches.
- If a target has "known_relationship", the foundation already knows this organization: acknowledge the recorded connection
  accurately and modestly (for example, that the foundation has featured its work or held an event there), call it a
  partnership only if formal_partnership is true, and never introduce the foundation as if it were a stranger. Claim no
  conversation, meeting, or contact that is not recorded. A target without known_relationship is a first contact.
- Never invent fundraising results, attendance, or history."""

DRAFT_CATEGORY = {"venue_inquiry": "venue", "corporate_sponsorship": "sponsor", "research_support": "research",
                  "nonprofit_collaboration": "charity", "partnership_inquiry": "partner", "community_program": "partner"}
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?<![\w$])(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}\b")


def contact_violations(text: str, verified_email: str | None) -> list[str]:
    """Contact details in a draft must come from the official website: no other email, and no phone numbers at all."""
    problems = []
    stray = [e for e in EMAIL_RE.findall(text) if not verified_email or e.lower() != verified_email.lower()]
    if stray:
        problems.append("includes an email address that was not verified on the organization's website (" + ", ".join(stray[:3]) + ")")
    if PHONE_RE.search(text):
        problems.append("includes a phone number (SAM SPACE never adds phone numbers)")
    return problems


CATEGORY_TYPE = {"research": "research_support", "sponsor": "corporate_sponsorship", "event": "community_program",
                 "partnership": "partnership_inquiry", "organization": "nonprofit_collaboration"}


def _background() -> str:
    return (f"{FOUNDATION['name']} ({FOUNDATION['short_name']}). {FOUNDATION['established']} "
            f"Focus: {', '.join(FOUNDATION['purpose_areas']).lower()}.")


class PartnershipsOutreachAgent(BaseAgent):
    name = AgentName.PARTNERSHIPS_OUTREACH

    def execute(self, task: AgentTask, ctx: RunContext) -> AgentResult:
        targets: list[dict] = []
        warnings: list[str] = []
        event = task.inputs.get("event")
        forced_type = task.inputs.get("draft_type")

        for item in (task.inputs.get("shortlist") or [])[:3]:
            v = item["venue"]
            targets.append({"target_id": f"venue:{v['venue_key']}", "suggested_type": "venue_inquiry", "name": v["name"],
                            "details": {"neighborhood": v.get("neighborhood"), "format": item["event_format"],
                                        "notes": wrap_untrusted(v.get("notes") or "", f"venue listing {v.get('venue_key')}", max_chars=600),
                                        "pricing_quote": v.get("pricing_quote"), "website": v.get("website")},
                            "synthetic": v.get("verification") == "synthetic", "finding_id": None,
                            "source_ids": [v["source_id"]] if v.get("source_id") else [],
                            "sources": [{"title": v["name"], "url": v.get("website") or v.get("source_url"), "verification": v.get("verification")}],
                            "review_notes": []})

        opportunities = task.inputs.get("opportunities")
        if opportunities is None and not targets:  # called directly: fall back to the board's saved findings
            saved = self.tool(ctx, "read_saved_findings", categories=["partnership", "organization", "research", "event", "sponsor"]).data or []
            opportunities = [{"id": f["id"], "name": f["title"], "category": f["category"], "purpose": f["summary"],
                              "verification": f["verification"], "website": f["source_url"],
                              "sources": [{"source_id": f"finding:{f['id']}", "title": f["title"], "url": f["source_url"],
                                           "verification": f["verification"]}]} for f in saved if f["saved"]][:3]
        for o in opportunities or []:
            review = list(o.get("missing_info") or []) + list(o.get("warnings") or [])
            targets.append({
                "target_id": f"finding:{o['id']}", "suggested_type": forced_type or CATEGORY_TYPE.get(o.get("category") or "", "partnership_inquiry"),
                "name": o.get("name") or o.get("title"),
                "details": {k: o.get(k) for k in ("category", "geography", "purpose", "activities", "partnership_types", "contribution_ways",
                                                  "known_costs", "dates_text", "date_status", "alignment_summary", "next_step", "website")},
                "missing_or_unconfirmed": review[:8], "synthetic": bool(o.get("is_synthetic") or o.get("verification") == "synthetic"),
                "finding_id": o["id"], "source_ids": [s["source_id"] for s in o.get("sources") or [] if s.get("source_id")],
                "sources": [{"title": s.get("title"), "url": s.get("url"), "verification": s.get("verification"),
                             "retrieved_at": s.get("retrieved_at")} for s in o.get("sources") or []],
                "review_notes": review[:8],
            })
        if not targets:
            return self.result(task, "completed", "No outreach targets yet. Save opportunities in Mission Discovery first.",
                               next_steps=["Run Mission Discovery and save promising partners."])

        provenance = task.inputs.get("provenance") or {}
        for t in targets:  # official public contact details first; never guessed
            kind = "venue" if t["suggested_type"] == "venue_inquiry" else "sponsor" if t["suggested_type"] == "corporate_sponsorship" else "default"
            website = (t["details"] or {}).get("website") or next((x.get("url") for x in t["sources"] if x.get("url")), None)
            found = self.tool(ctx, "lookup_inquiry_details", name=t["name"], website=website, kind=kind)
            t["contact"] = found.data if found.ok else None
            t["details"] = {**(t["details"] or {}), "contact": {"email": (t["contact"] or {}).get("email"),
                                                                 "contact_page": (t["contact"] or {}).get("contact_page_url"),
                                                                 "status": (t["contact"] or {}).get("status")}}
            if t["contact"] and not t["contact"].get("email"):
                t["review_notes"] = list(t["review_notes"]) + [t["contact"]["display"]]
        # The relationship directory (and past vendors) first: a known organization is never approached as a stranger.
        orgs = [{"name": t["name"], "website": (t["details"] or {}).get("website"),
                 "kind": "venue" if t["suggested_type"] == "venue_inquiry" else "organization"} for t in targets]
        known = self.tool(ctx, "read_foundation_knowledge", agent=self.name.value, organizations=orgs).data.get("matches", {})
        for t in targets:
            rel = known.get(t["name"])
            t["known_relationship"] = ({k: rel[k] for k in ("summary", "relationship_type", "formal_partnership", "verification",
                                                            "entry_id")} if rel else None)
            if rel:
                t["review_notes"] = list(t["review_notes"]) + [rel["summary"]]
        topic = " ".join([t["name"] for t in targets] + [t["suggested_type"].replace("_", " ") for t in targets] +
                         [str((event or {}).get(k) or "") for k in ("name", "event_type", "city")] + [task.inputs.get("request") or ""])
        pack = self.knowledge(ctx, task, topic, limit=7)
        personalized = any(t["finding_id"] for t in targets)
        profile = OUTREACH_PERSONALIZED if personalized else OUTREACH_DRAFTS
        instructions = INSTRUCTIONS if personalized else VENUE_INSTRUCTIONS
        if pack or any(t["known_relationship"] for t in targets):
            instructions = f"{instructions}\n{KNOWLEDGE_INSTRUCTIONS}\n\n{KNOWLEDGE_RULES}"
        payload = {"foundation": {**FOUNDATION, "background": _background()}, "event": event,
                   "foundation_knowledge": self.knowledge_in(pack),
                   "targets": [{k: v for k, v in t.items() if k not in ("sources", "review_notes", "finding_id", "contact")} for t in targets]}
        shareable = [f for f in (pack or {}).get("facts", []) if f.get("shareable_in_outreach")]
        allowed_amounts = collect_amounts({"targets": payload["targets"], "event": event, "shareable": shareable})

        by_id = {t["target_id"]: t for t in targets}
        accepted: dict[str, object] = {}
        rejected: dict[str, list[str]] = {}
        out = self.think(ctx, profile, instructions, payload, DraftsOutput, max_output_tokens=9000)
        summary = out.summary
        for attempt in range(2):  # at most one rewrite of rejected drafts
            rejected = {}
            for d in out.drafts:
                target = by_id.get(d.target_id)
                if target is None:
                    warnings.append(f"Ignored a draft for an unknown target ({d.target_id}).")
                    continue
                if d.target_id in accepted:
                    continue
                text = f"{d.subject}\n{d.body}\n{d.opportunity}\n{d.next_step}"
                problems = outreach_violations(text, allowed_amounts, target.get("known_relationship"))
                problems += contact_violations(text, (target.get("contact") or {}).get("email"))
                rel = target.get("known_relationship")
                if rel and not acknowledges_relationship(text, rel):
                    problems.append("reads as a first introduction, but the foundation already knows this organization ("
                                    + rel["summary"][:160] + "); acknowledge that connection accurately")
                if problems:
                    rejected[d.target_id] = problems
                else:
                    accepted[d.target_id] = d
            if not rejected or attempt == 1:
                break
            retry_payload = {**payload, "targets": [t for t in payload["targets"] if t["target_id"] in rejected],
                             "rejected_because": rejected}
            out = self.think(ctx, profile, instructions + "\nYour previous drafts for these targets were rejected for the reasons in "
                             "\"rejected_because\". Rewrite them without those problems.", retry_payload, DraftsOutput, max_output_tokens=6000)
        for tid, problems in rejected.items():
            warnings.append(f"Dropped the draft to {by_id[tid]['name']}: it {'; '.join(problems)}.")

        made = []
        for tid, d in accepted.items():
            target = by_id[tid]
            draft_type = forced_type if forced_type in DRAFT_TYPES else d.draft_type
            used = [s for s in target["sources"]] if not d.source_ids else \
                [s for s, sid in zip(target["sources"], target["source_ids"]) if sid in d.source_ids] or target["sources"]
            prov = provenance.get(tid) or {}
            contact = target.get("contact")
            row = self.tool(ctx, "create_outreach_draft", draft_type=draft_type, recipient_org=target["name"], subject=d.subject,
                            body=d.body, personalization_basis=d.personalization_basis, is_synthetic_target=target["synthetic"],
                            purpose=d.purpose, opportunity=d.opportunity, next_step=d.next_step,
                            foundation_background=d.foundation_background, sources=used, finding_id=target["finding_id"],
                            review_notes=target["review_notes"], category=prov.get("category") or DRAFT_CATEGORY.get(draft_type),
                            contact=contact, found_by_agent=prov.get("found_by"), recommendation_reason=prov.get("reason"),
                            related_findings=prov.get("related_findings"), financial_considerations=prov.get("financial_considerations"))
            if row.ok:
                made.append({"id": row.data["id"], "recipient": target["name"], "subject": d.subject, "draft_type": draft_type,
                             "contact_status": (contact or {}).get("status"), "contact_email": (contact or {}).get("email"),
                             "finding_id": target["finding_id"], "synthetic_target": target["synthetic"], "status": "draft",
                             "purpose": d.purpose, "next_step": d.next_step, "sources": used, "review_notes": target["review_notes"],
                             "known_relationship": (target.get("known_relationship") or {}).get("summary"),
                             "knowledge_used": [k for k in (d.knowledge_used or []) if pack and k in pack["_ids"]]})
        findings = [Finding(claim=f"Unsent {m['draft_type'].replace('_', ' ')} draft to {m['recipient']}: “{m['subject']}”",
                            kind="recommendation", source_ids=by_id[f"finding:{m['finding_id']}"]["source_ids"] if m["finding_id"] else [])
                    for m in made]
        return self.result(
            task, "completed", summary, findings=findings, warnings=warnings,
            assumptions=(["Some recipients are synthetic fixtures (example.org), not real organizations."] if any(m["synthetic_target"] for m in made) else []) +
                        ["Nothing was sent. SAM SPACE has no tool that can send, schedule, or publish a message."],
            next_steps=["Review and edit each draft in Partnerships & Outreach. If the board agrees, a person sends it outside SAM SPACE."],
            data={"drafts": made, "rejected": [{"recipient": by_id[t]["name"], "problems": p} for t, p in rejected.items()],
                  **self.knowledge_record(pack, [k for d in accepted.values() for k in (d.knowledge_used or [])])},
        )
