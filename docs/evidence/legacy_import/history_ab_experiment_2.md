# Evidence: planning without vs. with historical insights (experiment #2)

**Request:** Plan a spring raffle fundraiser for 120 guests in Manhattan and check whether we can afford it.  
**Research data:** synthetic · runs #36 (without history) and #37 (with history) · 2026-10-25

## What changed

- Final venue unchanged: Chelsea Atelier (synthetic) (reception).
- With history, Event Intelligence gave the Events agent 5 evidence-backed constraint(s).
- Extra cost of consulting history: $+0.1118 (+1 model calls).

## Side by side

| Measure | Without history | With history | Change |
|---|---|---|---|
| Projected total (USD) | $13,486 | $13,486 | +0.0 |
| Upfront cash (USD) | $3,728 | $3,728 | +0.0 |
| Contingency | 10% | 10% | +0% |
| Revision rounds | 1 | 1 | +0.0 |
| Historical constraints given to Events | 0 | 5 | +5.0 |
| Lessons applied in the recommendation | 1 | 6 | +5.0 |
| Model calls | 6 | 7 | +1.0 |
| Input tokens | 17,511 | 31,461 | +13,950.0 |
| Output tokens | 5,771 | 10,462 | +4,691.0 |
| Cost (USD) | $0.1944 | $0.3062 | +0.1118 |
| Duration (s) | 144.3 | 203.6 | +59.3 |

## Constraints Event Intelligence passed to the Events agent

- For the raffle, set the volunteer list three weeks out, brief the team the week before, and designate station leads rather than assigning roles at opening.
- Finalize print requirements before last-minute additions arise; the walk reflection recommends locking sponsor logos a month before printing. Include an explicit printing cushion, with the amount still to be determined.
- If food is included, compare written venue and vendor minimums, per-head prices, and guest-count change terms before choosing a provider. Budget volunteer food separately.
- Check entrance accessibility, room audibility, and availability of a quiet area before committing to a venue. These checks respond to recorded steps, excessive noise, and quiet-space requests.
- Rehearse a shorter draw rather than repeating the raffle's reported 40-minute draw. No exact target duration is supported by the raffle record.

## Lessons applied in the recommendation

- **Only with history:** Butterfly Spring Raffle: retain a staffed welcome table and raffle; explore donated bakery prizes; improve volunteer preparation and shorten the draw. No ideal draw duration is established.
- **Only with history:** Butterfly Spring Raffle and Spring Awareness Walk: finalize printing and sponsor artwork early to reduce last-minute cost exposure.
- **Only with history:** Campus Wellness Panel and Butterfly Spring Raffle: request a quiet conversation area. Hartford trivia night supports checking audibility and using a brief, optional mission-related conversation prompt.
- **Only with history:** Butterfly Benefit Dinner and Spring Awareness Walk: obtain written food prices and minimums, and plan volunteer meals separately. Personal recognition does not replace adequate food and breaks.
- **Only with history:** Butterfly Benefit Dinner: explicitly verify entrance access and, if deferred pledges are offered, plan event-day collection.
- **Only with history:** Campus Wellness Panel: settle the event’s purpose before evaluating additional programming and expense.
- **Only without history:** No past-event lessons or community insights were supplied. The Spring raffle in Manhattan is a synthetic test plan; the reference to an Our Legacy history comparison provides no named past-event evidence to apply.

## Fundraising strategy

- **Only with history:** Ask the board to confirm whether fundraising, awareness, or both is the primary purpose, applying the Campus Wellness Panel lesson before adding programming or expense.
- **Only with history:** Use the supplied $75 admission price as the planning baseline. Consider an optional supporter tier and sponsor-funded access tickets, with pricing and quantities still to be determined. Keep additional giving voluntary.
- **Only with history:** Draft cash-sponsorship asks for event support and access tickets. Record prospective, pledged, and collected support separately; do not assume sponsorship closes the cost-limit breach.
- **Only with history:** Explore donated bakery raffle prizes, applying the Butterfly Spring Raffle experience, and other relevant in-kind support. Confirm availability, food permissions, and actual budget treatment rather than assuming a donation's value or savings.
- **Only with history:** Consider a brief optional paddle raise or direct appeal tied to mental health awareness, eating disorder research, and community. If deferred pledges are offered, provide an event-day collection process, transferring the Butterfly Benefit Dinner lesson without claiming a past raffle collection problem.
- **Only with history:** Have Finance rerun the budget calculator after written proposals and sponsorship inputs are available. Base and conservative net proceeds are currently unknown, so achievement of the $12,000 goal cannot be assessed.
- **Only without history:** Keep the proposed $75 admission price as the planning baseline. Ask the board about sponsor-funded community tickets and an optional supporter tier; do not assign new prices or assume revenue before calculator review.
- **Only without history:** Draft sponsorship asks for catering, venue support, and donated raffle prizes. Record prospective support separately from confirmed commitments; sponsorship must not be treated as permission to exceed the cost ceiling.
- **Only without history:** Request alternative catering proposals and in-kind support, prioritizing the Finance-identified catering cost of $6,960. Explore entertainment alternatives against the modeled $1,500 cost and venue support against the $1,800 venue cost. Do not assume savings until documented and incorporated into the calculator.
- **Only without history:** Plan a brief, voluntary paddle raise or direct appeal tied to mental health awareness, eating disorder research, and community. Keep participation optional and separate from admission.
- **Only without history:** Before offering raffle entries, confirm applicable raffle eligibility, permissions, rules, prize handling, and volunteer procedures. Do not assume admission includes raffle entries.
- **Only without history:** Ask for the missing sponsorship expectations and obtain updated base and conservative net figures before assessing whether the $12,000 fundraising goal is achievable.

## Logistics notes

- **Only with history:** No event date is supplied. Confirm availability and build an event schedule around Chelsea's load-in-after-4-pm restriction.
- **Only with history:** Lock the volunteer list three weeks out, brief volunteers by phone the week before, and assign a lead for each station before doors open.
- **Only with history:** Confirm the caterer's final guest-count deadline and change terms. Resolve why catering-minimum scenarios elsewhere use 96 guests while planned attendance is 120; do not substitute either count into the supplied costs.
- **Only with history:** Obtain written catering prices, minimums, service scope, and food permissions before selecting a provider. Plan volunteer meals and access separately from guest food.
- **Only with history:** Finalize print requirements early, lock sponsor logos a month before printing, and ask Finance to include an explicit printing cushion with its amount still to be determined.
- **Only with history:** Check entrance access, toilets, seating accommodations within the standing-only restriction, room audibility, microphone provision, and quiet-area availability before commitment.
- **Only with history:** Rehearse a shorter raffle draw than the reported 40-minute Butterfly Spring Raffle draw; no exact replacement duration is established.
- **Only with history:** Confirm applicable raffle requirements and the foundation's ability to meet them before promoting or collecting raffle payments.
- **Only without history:** Chelsea permits standing receptions only, with load-in after 4 pm. Build setup, catering delivery, volunteer briefing, and guest arrival around that restriction; the event date and availability are unknown.
- **Only without history:** Confirm the guest-count lock deadline and reconcile the planned 120 attendees with the 96-guest catering scenarios shown for some other options before any future comparison.
- **Only without history:** Assign volunteer responsibilities for welcome, check-in, raffle administration, prize custody, the appeal, and cleanup.
- **Only without history:** Ask Chelsea about step-free entry, accessible restrooms, seating accommodations within its standing-reception restriction, sound levels, dietary needs, and emergency procedures. None of these accessibility details is supplied.
- **Only without history:** Request written catering, staffing, insurance, cancellation, deposit, and load-in terms. Preserve the supplied computed figures until a revised calculator result is available.

## Risks

- **Only with history:** Catering at $6,960 is the largest identified cost driver, followed by venue rental at $1,800 and entertainment at $1,500. Revised quotes may not deliver sufficient savings.
- **Only with history:** Prospective or pledged sponsorship is not available money. Restricted funds must not support unrestricted event spending, and receipts arriving after deposits are due cannot fund those deposits.
- **Only with history:** The $75 admission baseline may exclude some guests. Sponsor-funded access tickets could help only if funding and board approval are secured.
- **Only with history:** Standing-only reception rules may prevent some guests from participating comfortably. Entrance access, toilets, seating accommodations, dietary provision, sound, and quiet space remain unconfirmed.
- **Only without history:** Using unrestricted reserves for deposits would reduce the operating cushion; the recorded period shows a loss.
- **Only without history:** Restricted funds and pledged sponsorship are not available money. Later event revenue cannot fund deposits due earlier.
- **Only without history:** Placeholder costs and unidentified expenses could increase the final total.
- **Only without history:** The standing-only format could exclude guests who need seating. Accessibility cannot be inferred from the supplied amenities.
- **Only without history:** Raffle eligibility, permissions, rules, prize handling, and volunteer procedures remain unresolved.

## Decisions for the board

- **Only with history:** Confirm whether the event primarily serves fundraising, awareness, or both, and confirm the supplied $12,000 fundraising goal.
- **Only with history:** Choose whether to retain the $8,000 ceiling and require redesign, explicitly reconsider that ceiling subject to renewed financial review, or defer.
- **Only with history:** Confirm the $75 admission baseline and whether to develop optional supporter and sponsor-funded access ticket arrangements.
- **Only with history:** Set minimum accessibility and inclusion requirements before venue selection.
- **Only with history:** Make any eventual spending authorization separately from the feasibility review, after reviewing verified cash balances, restrictions, quotes, and permissions.
- **Only without history:** Choose whether to retain the current ceiling and redesign, request new options, consider a revised ceiling, or defer.
- **Only without history:** Determine whether any use of unrestricted reserves is acceptable after updated cash verification and preservation of the reserve floor.
- **Only without history:** Confirm the proposed $75 admission baseline and whether to explore sponsor-funded community tickets and an optional supporter tier, without assuming their revenue.
- **Only without history:** Select a target date and confirm format flexibility, accessibility requirements, mission language, and consent-based recognition practices.

## Next steps

- **Only with history:** Choose a proposed spring date and prepare a venue brief covering 120 guests, accessible participation, quiet space, sound, catering terms, volunteer meals, and load-in.
- **Only with history:** Have a person review the unsent Chelsea inquiry and verify the recipient before any outreach outside SAM SPACE.
- **Only with history:** Obtain written venue and vendor proposals, including minimums and known printing, permit, and miscellaneous costs. Explore donated bakery prizes without assuming availability or savings.
- **Only with history:** Confirm raffle permissions, operating requirements, food permissions, and payment arrangements before commitments or promotion.
- **Only with history:** Give Finance the supplied admission price, fundraising goal, explicit donation assumptions, and sponsorship scenarios, separating prospective, pledged, and collected support. Resolve Finance’s input gaps rather than treating the existing calculator output as complete.
- **Only with history:** Verify current unrestricted cash and restricted balances, preserve the reserve floor, and rerun total-cost, cash-timing, base, conservative, break-even, and target checks.
- **Only with history:** Once feasible, lock the volunteer list three weeks out, brief volunteers the week before, assign station leads, finalize printing early, and rehearse a shorter draw.
- **Only without history:** Review the unsent Chelsea inquiry. A person may send an edited inquiry outside SAM SPACE only after verifying the recipient; the supplied venue is synthetic.
- **Only without history:** Seek current pricing, alternative catering and entertainment proposals, deposit terms, availability, and documented accessibility arrangements. Replace placeholder costs and enter known miscellaneous expenses.
- **Only without history:** Confirm sponsorship expectations and receipt timing, separating prospective support and pledges from received funds. Confirm ticket and donation assumptions.
- **Only without history:** Have Finance rerun total cost, base and conservative net results, break-even attendance, and fundraising-target checks after the inputs are complete.
- **Only without history:** Verify current unrestricted cash and restricted balances, preserve the reserve floor, and check upfront obligations without relying on later event revenue.
- **Only without history:** Before offering raffle entries, establish applicable eligibility, permissions, rules, prize handling, and volunteer procedures. Do not assume admission includes raffle entries.

## Headlines

- Without history: Redesign before committing: the spring raffle is not affordable as planned.
- With history: Redesign before committing: the spring raffle is not affordable as planned.

## Recommendations

**Without history.** Keep the $8,000 ceiling and move the proposed Manhattan raffle for 120 guests into a cost-reduction and verification stage. No supplied venue option meets the ceiling. Chelsea Atelier is the closest candidate, but its projected $13,486 cost makes it unsuitable for approval as modeled. Retain it only for further planning while exploring lower-cost alternatives. Return to the board with revised financial checks, confirmed accessibility arrangements, and raffle requirements before any commitment.

**With history.** Continue planning a 120-guest Manhattan raffle, but do not commit funds under the current proposal. Chelsea Atelier’s synthetic reception estimate is $13,486 against the $8,000 cost limit. Retain it only as a research lead while seeking a lower-cost, accessible plan. Return to the board with written quotes, complete revenue assumptions, and a fresh Finance review before any spending decision.

_Both runs used the same request, event plan, research data, and model strategy. Only the Event Intelligence step differs. Model outputs vary between runs, so some text differences are wording, not substance._
