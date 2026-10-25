"""Agent 5: Donations & Compliance.

Privacy by design. The model never sees a donor's name, email, or individual
gift amount:
  * the review (gpt-6.1-sol) receives counts by flag and campaign totals, plus the
    deterministic compliance checklist with its cited sources
  * the thank-you template (gpt-6-luna) has merge fields; Python fills in each
    donor's verified record locally
  * contribution acknowledgments for $250+ gifts and gifts where the donor
    received something are built entirely in code from the record, marked for
    accountant review

Every reporting question must cite a reference from compliance.py (with its
jurisdiction), or it is routed to an accountant or attorney. The agent never
sends anything, files anything, decides deductibility, or changes a record:
acknowledgment status changes only when a board member marks it.
"""

from __future__ import annotations

import re

from ...compliance import REFERENCES
from ...mission import PHILOSOPHY
from ...services.donations import duplicate_key
from ..base import BaseAgent
from ..contracts import AgentName, AgentResult, AgentTask, Finding
from ..outputs import AcknowledgmentTemplate, DonationReview
from ..registry import ACK_TEMPLATE, DONATION_REVIEW
from ..runtime import RunContext

REVIEW_INSTRUCTIONS = """Review the foundation's donation records for a volunteer board. You see only counts, campaign totals,
and a compliance checklist computed in code; you never see donors.
- summary: what the records show and what needs attention first, in plain English.
- incomplete_records: the kinds of incomplete records and how many (e.g. "4 gifts lack a payment method").
- campaign_notes: how gifts are distributed across campaigns and events (received vs pledged; pledges are not received money).
- reporting_questions: questions the board should take to its accountant or attorney. Each cites ref_ids from "references"
  ONLY. kind: verified_requirement only when a cited reference states the rule; general_guidance when it depends on facts;
  needs_professional_review when no reference covers it. Name the jurisdiction in the question.
- Never give a definitive tax or legal opinion, never say a gift is or is not deductible, and never suggest SAM SPACE file or send anything."""

ACK_INSTRUCTIONS = f"""Write ONE warm donor thank-you letter template.
- The body MUST include the merge fields {{{{donor_name}}}}, {{{{gift}}}}, and {{{{date}}}}. {{{{gift}}}} is the gift itself ("$250.00" or
  "floral arrangements for the gala tables"), so write "your gift of {{{{gift}}}}". You may use {{{{campaign}}}} and {{{{designation}}}}.
  All are filled in locally; you never see donor details.
- Reflect the foundation's philosophy, "{PHILOSOPHY}", naturally, not as a slogan. Where it fits, say that donors help
  support mental health awareness, eating disorder research, community connection, and compassion and belonging.
- Do not say how this specific gift was or will be spent, and do not promise outcomes.
- This is a general thank-you, not a tax acknowledgment: do not mention tax deductibility, receipts, or legal language.
- Sign with placeholders: [Board member name], [Title], Sabrina Audrey Milone Foundation.
- review_items: [] (compliance is reviewed separately)."""

SPENDING_CLAIMS = re.compile(r"\byour (gift|donation|support|generosity)\s+(will\s+|has\s+)?(fund|funded|funds|paid for|pays for|purchased|"
                             r"buys|bought|was used|will be used|covered|covers|made possible)\b|\bthanks to your gift, we (built|bought|funded|hired)\b",
                             re.IGNORECASE)
TAX_CLAIMS = re.compile(r"tax[- ]deductible|deductib|tax receipt|for tax purposes|IRS|charitable deduction", re.IGNORECASE)
DRAFT_CAP = 12


def template_problems(subject: str, body: str) -> list[str]:
    text = f"{subject}\n{body}"
    out = [f"claims how a gift was spent (“{m.group(0)}”)" for m in SPENDING_CLAIMS.finditer(text)]
    out += [f"mentions tax treatment (“{m.group(0)}”), which belongs only in the separate contribution acknowledgment"
            for m in TAX_CLAIMS.finditer(text)]
    return out


class DonationsComplianceAgent(BaseAgent):
    name = AgentName.DONATIONS_COMPLIANCE

    def execute(self, task: AgentTask, ctx: RunContext) -> AgentResult:
        donations = self.tool(ctx, "read_donations")
        items = donations.data["donations"]
        if not items:
            return self.result(task, "completed", "No donations are recorded yet.", data={"aggregate": {"gifts_recorded": 0}})
        flags = self.tool(ctx, "flag_donation_issues", donations=items).data
        aggregate = flags["aggregate"]
        requested = task.inputs.get("donation_ids")
        drafts_only = bool(task.inputs.get("drafts_only"))
        warnings: list[str] = []
        demo = any(d.get("is_demo") for d in items)

        review, compliance = None, None
        if not drafts_only:
            compliance = self.tool(ctx, "read_compliance_items").data
            out = self.think(ctx, DONATION_REVIEW, REVIEW_INSTRUCTIONS,
                             {"aggregate": aggregate, "compliance_checklist": compliance["items"],
                              "references": [{k: r[k] for k in ("id", "title", "authority", "jurisdiction", "kind", "checked_on", "points")}
                                             for r in compliance["references"]]}, DonationReview)
            questions = []
            for q in out.reporting_questions:
                refs = [r for r in q.ref_ids if r in REFERENCES]
                kind = q.kind
                if len(refs) < len(q.ref_ids):
                    warnings.append(f"Removed an unknown source from: “{q.question[:60]}…”")
                if kind == "verified_requirement" and not any(REFERENCES[r]["kind"] == "verified_requirement" for r in refs):
                    kind = "needs_professional_review"  # no authoritative source, so it goes to a professional
                questions.append({**q.model_dump(), "ref_ids": refs, "kind": kind,
                                  "jurisdictions": sorted({REFERENCES[r]["jurisdiction"] for r in refs}) or ["Not determined"],
                                  "professional": q.professional if q.professional != "none" or kind == "verified_requirement" else "accountant"})
            review = {**out.model_dump(), "reporting_questions": questions}

        # Thank-you drafts: requested gifts, or received gifts nobody has started acknowledging.
        by_id = {d["id"]: d for d in items}
        if requested:
            targets = [i for i in requested if i in by_id][:DRAFT_CAP]
        else:
            targets, seen, skipped = [], set(), 0
            for d in sorted(items, key=lambda x: x["id"]):
                if d["payment_status"] != "received" or d["ack_status"] != "not_started":
                    continue
                key = duplicate_key(d["donor_name"], d["received_on"], d["amount_usd"])
                if key in seen:  # a likely duplicate record: one letter per gift, never two
                    skipped += 1
                    continue
                seen.add(key)
                targets.append(d["id"])
            targets = targets[:DRAFT_CAP]
            if skipped:
                warnings.append(f"Skipped {skipped} likely duplicate record(s); resolve them before drafting a second letter.")
        thank_you = contrib = 0
        draft_ids: list[int] = []
        template = None
        if targets:
            payload = {"gift_types": sorted({by_id[i]["contribution_type"] for i in targets}),
                       "has_restricted_gifts": any(by_id[i]["restriction"] in ("temporarily_restricted", "permanently_restricted") for i in targets),
                       "campaign_names": sorted({by_id[i]["campaign"] for i in targets if by_id[i]["campaign"]})}
            template = self.think(ctx, ACK_TEMPLATE, ACK_INSTRUCTIONS, payload, AcknowledgmentTemplate)
            problems = template_problems(template.subject, template.body)
            if problems:  # one bounded rewrite
                template = self.think(ctx, ACK_TEMPLATE, ACK_INSTRUCTIONS, {**payload, "rejected_because": problems}, AcknowledgmentTemplate)
                problems = template_problems(template.subject, template.body)
            if problems:
                warnings.append("No thank-you drafts were saved: the template still " + "; ".join(problems) + ".")
            else:
                made = self.tool(ctx, "create_acknowledgment_drafts", subject=template.subject, body=template.body, donation_ids=targets).data
                thank_you, draft_ids = made["drafts_created"], made["draft_ids"]
            needs_formal = [i for i in targets if by_id[i]["payment_status"] == "received" and
                            any(f["code"] in ("ack_250", "quid_pro_quo", "in_kind") for f in by_id[i]["flags"])]
            if needs_formal:
                made = self.tool(ctx, "create_contribution_acknowledgments", donation_ids=needs_formal).data
                contrib = made["drafts_created"]
                draft_ids += made["draft_ids"]

        findings = [Finding(claim=f"{aggregate['gifts_needing_attention']} of {aggregate['gifts_recorded']} gift records need attention.",
                            kind="computed", source_ids=["donations"])]
        if review:
            findings += [Finding(claim=f"{q['question']} ({', '.join(q['jurisdictions'])}; {q['kind'].replace('_', ' ')})",
                                 kind="recommendation", source_ids=q["ref_ids"]) for q in review["reporting_questions"]]
        summary = review["summary"] if review else f"Prepared {thank_you} thank-you draft(s) and {contrib} contribution acknowledgment draft(s)."
        return self.result(
            task, "completed", summary, findings=findings, warnings=warnings + ["Every draft is unsent. A board member reviews it and, "
                                                                               "if appropriate, sends it outside SAM SPACE."],
            assumptions=(["Donation records are fictional demonstration data."] if demo else []) +
                        ["The AI saw counts and campaign totals only; donor details were merged locally into drafts."],
            next_steps=[f"Review {thank_you + contrib} draft(s) in Donations & Compliance."] +
                       ([f"Take to your {q['professional']}: {q['question']}" for q in review["reporting_questions"] if q["professional"] != "none"]
                        if review else []),
            data={"aggregate": aggregate, "review": review, "compliance": compliance["items"] if compliance else None,
                  "thank_you_drafts": thank_you, "contribution_acknowledgment_drafts": contrib, "draft_ids": draft_ids,
                  "drafts_created": thank_you + contrib, "template_subject": template.subject if template else None},
        )
