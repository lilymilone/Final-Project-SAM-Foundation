"""Agent 5: Donations & Compliance.

Privacy by design: donor names and amounts never reach the model. The agent
sends only counts and flag categories. The model writes one acknowledgment
template with merge fields, and Python fills it in locally for each gift that
still needs a thank-you. Drafts are never sent. The agent flags issues for a
professional instead of deciding tax treatment, and it never submits forms or
files returns.
"""

from __future__ import annotations

from ..base import BaseAgent
from ..contracts import AgentName, AgentResult, AgentTask, Finding
from ..outputs import AcknowledgmentTemplate
from ..registry import ACK_TEMPLATE
from ..runtime import RunContext

INSTRUCTIONS = """Write ONE donor acknowledgment template and list issues that need professional review.
- The body MUST include the merge fields {{donor_name}}, {{amount}}, and {{date}} (and may use {{designation}}).
  SAM SPACE fills them in locally; you will never see donor names or amounts.
- Warm, sincere tone honoring Sabrina's memory. Leave a placeholder signature such as [Board member name].
- Do not state definitive tax treatment. You may include a line like "No goods or services were provided in exchange
  for this gift" only as a suggestion marked [confirm with accountant].
- review_items: issues from the flag counts that a person or accountant should review. Say why each needs a professional."""


class DonationsComplianceAgent(BaseAgent):
    name = AgentName.DONATIONS_COMPLIANCE

    def execute(self, task: AgentTask, ctx: RunContext) -> AgentResult:
        donations = self.tool(ctx, "read_donations")
        flags = self.tool(ctx, "flag_donation_issues", donations=donations.data).data
        per_gift = flags["per_gift"]
        needs_ack = [g["id"] for g in per_gift if not g["acknowledged"]]
        aggregate = {
            "gifts_recorded": len(per_gift),
            "gifts_needing_attention": sum(1 for g in per_gift if g["flags"]),
            "unacknowledged_gifts": len(needs_ack),
            "unacknowledged_250_plus": sum(1 for g in per_gift if not g["acknowledged"] and g["amount_band"] == "250_plus"),
            "flag_counts": flags["flag_counts"],
        }
        if not per_gift:
            return self.result(task, "completed", "No donations are recorded yet.", data={"aggregate": aggregate})

        template = self.think(ctx, ACK_TEMPLATE, INSTRUCTIONS, {"aggregate": aggregate}, AcknowledgmentTemplate)
        created = 0
        if needs_ack:
            created = self.tool(ctx, "create_acknowledgment_drafts", subject=template.subject, body=template.body,
                                donation_ids=needs_ack).data["drafts_created"]
        demo = any(d.get("is_demo") for d in donations.data)
        findings = [Finding(claim=f"{aggregate['gifts_needing_attention']} of {aggregate['gifts_recorded']} gifts need attention; "
                                  f"{aggregate['unacknowledged_gifts']} have not been thanked.", kind="computed", source_ids=["donations"])]
        findings += [Finding(claim=f"{r.issue}: {r.why_professional_review}", kind="recommendation") for r in template.review_items]
        return self.result(
            task, "completed", template.summary, findings=findings,
            assumptions=(["Donation records are synthetic demo data."] if demo else []) +
                        ["Donor names and amounts were merged locally; the AI saw only counts."],
            warnings=["Acknowledgments are unsent drafts. A board member must review and send them outside SAM SPACE."],
            next_steps=[f"Review {created} acknowledgment draft(s) in Donations & Compliance."] +
                       [f"Ask a professional: {r.issue}" for r in template.review_items],
            data={"aggregate": aggregate, "drafts_created": created, "review_items": [r.model_dump() for r in template.review_items],
                  "template_subject": template.subject},
        )
