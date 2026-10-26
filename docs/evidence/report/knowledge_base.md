# Foundation Knowledge Base: does foundation-specific knowledge change what the agents do?

**Date:** 2026-10-26. **Code:** the Foundation Knowledge Base stage (walkthrough: [../../knowledge_base_workflow.md](../../knowledge_base_workflow.md)).

**Privacy:** the live runs below used the foundation's real facts, which live only in the local database. This file
describes them generically ("the foundation's past gala venue"), with no names, dates, or costs from those records. The
committed tests use invented facts labeled "(test)".

## 1. What the knowledge base held during the live runs

28 facts in 9 of the 10 sections (the board directory is still empty):

| Status | Facts |
|---|---|
| Verified | 1 (that the books in SAM SPACE are demo data, a fact about the app's own records) |
| Board-reported | 23 |
| Approximate | 2 (a past gala's total cost, a past band's fee) |
| Needs confirmation | 2 (vendors whose names were not recorded) |

All facts came from one board member's descriptions. None has yet been verified by the chair or treasurer against a record.

## 2. Automated tests (scripted model, invented facts)

`tests/test_knowledge.py`: **18 passed**. The full suite: **297 passed**.

| Test | What it checks | Result |
|---|---|---|
| A. Gala planning | The Orchestrator passes the recorded gala to Events; the Events prompt contains its lessons; an id the agent was not given is dropped; the final answer sees it. With the knowledge base switched off, none of it reaches any model. | Pass |
| B. Cycling fundraiser | A spin-class request retrieves the cycling event first (not the gala), and is parsed as a 50-rider spin class, not a 100-guest gala | Pass |
| C. Charitable partnership | Research marks a recorded organization "Known to the foundation" (historical collaboration, not a formal partnership); unfamiliar organizations are still recommended; the opportunity card shows the relationship | Pass |
| D. Outreach | Drafts get the foundation's facts and the recipient-specific rules; a draft quoting an internal cost is rejected; a draft to a known organization that reads as a first introduction is rejected | Pass |
| E. Finance source safety | Finance labels the books demo, lists a past event's cost as a board estimate (never verified history), and the planning budget is unchanged by it | Pass |
| F. Boss Agent coordination | Each specialist receives only facts from its own sections; the board directory stays with the Orchestrator; no board contact reaches any model; the reviewer suggestion comes from the directory | Pass |

Plus: provenance on every fact, member vs chair permissions (members cannot verify or remove; contacts masked), Our
Legacy links, template import, samples giving way to real facts, task-relevant retrieval, and board names removed from
web searches.

## 3. Live runs (real models, live web research, Faster strategy)

| Run | Request (paraphrased) | Cost | Time | What the knowledge changed |
|---|---|---|---|---|
| #54 | Plan our next gala for 150 guests; can we afford it? | $0.0838 | 171 s | The Orchestrator read 8 of 28 facts (~504 tokens) and passed lessons 6, Events 6, Finance 4, and Outreach 7. Events listed the foundation's **past venue, caterer, and band** as vendors to ask before choosing new ones (none appeared in the web results). Finance listed two **board estimates** and labeled the books demo. Drafts introduced the foundation from its recorded facts. The answer named what the records lack (past gala attendance and revenue). Verification passed. |
| #55 | Same request, knowledge base **off** | $0.0761 | 129 s | No past-vendor step, no board estimates, generic foundation introductions. The plan still drew on the past gala's Our Legacy record through Event Intelligence, so some personalization comes from history records alone. |
| #56 | Plan the foundation's cycling fundraiser for 50 riders | $0.0730 | 129 s | The knowledge was right: the answer recommended **the studio the foundation used three years running** as the first inquiry. **Problem found:** the request parser read "50 riders" and "spin class" as a default 100-guest gala, so Events searched gala venues and Outreach wrote 3 gala-venue drafts. The final answer flagged the mismatch itself. The 3 drafts were archived. |
| #59 | Same as #56, **after the fix** | $0.0742 | 153 s | Parsed as a 50-person spin class; the live search included the past studio by name; it came back first, and Events marked it "among the options and a board-reported past vendor ... no current agreement." Drafts went to 3 studios. **Second problem found:** the draft to the past studio read like a first introduction. |
| #57 | Research eating-disorder and mental-health organizations in New York | $0.0183 | 100 s | 6 organizations found; the relationship check recognized **1 as already known** and the answer described the recorded connection accurately (board-reported, historical) instead of presenting it as a discovery. 3 introductions drafted to the others. |
| #58 | Review our finances: could we afford a gala like our last one? | $0.0015 | 18 s | "We cannot determine whether the foundation can afford another gala until its real finances are reviewed." The answer compared the demo planning figure with the past gala's approximate cost and said the comparison is "only illustrative": the cost is an estimate, and the demo budget is not money. |
| #60 | Draft an introduction to the organization recognized in #57, **after the second fix** | $0.0211 | 34 s | The draft acknowledged the recorded connection in the record's own terms, without calling it a partnership; the "Already known" note travels with the draft to the Review Center. |

**Total for these 7 runs: $0.348.**

## 4. Problems the live runs exposed, and the fixes

| Found in | Problem | Fix | Checked by |
|---|---|---|---|
| #55 | With no facts supplied, the model filled the recommendation's `knowledge_used` with free text | Code keeps only ids the Orchestrator supplied | `test_A_without_the_knowledge_base_the_same_plan_gets_none_of_it` |
| #56 | A spin class for 50 riders was planned as a 100-guest gala | The parser recognizes riders, participants, players, and runners; spin classes, tournaments, and similar event types; the live venue search uses the event type and includes past venues and studios | `test_B_a_spin_class_is_not_planned_as_a_gala`, run #59 |
| #59 | A draft to a past vendor read as a first introduction | Code rejects a draft to a known organization unless it acknowledges the connection (one rewrite, then dropped); venue drafts must mention a venue-specific detail and ask about catering only for a meal | `test_D_a_known_organization_never_gets_a_first_introduction`, run #60 |

## 5. Token cost of the context

**Retrieval size (estimated at 4 characters per token):** the Orchestrator's facts were ~439–749 tokens. Each
specialist's share was ~370–540 tokens. Never the whole base: at most 6–8 facts, from the agent's own sections only.

**Measured, same request with and without the knowledge base (#54 vs #55):**

| Step | Input tokens with | Input tokens without | Difference |
|---|---|---|---|
| Event Intelligence (lessons) | 9,767 | 8,628 | +1,139 |
| Fundraising & Events (venues, includes the web search) | 27,775 | 27,515 | +260 |
| Financial Analysis | 2,821 | 1,993 | +828 |
| Partnerships & Outreach | 3,038 | 1,583 | +1,455 |
| Final recommendation | 10,518 | 8,525 | +1,993 |
| **Whole run** | **53,919** | **48,244** | **+5,675 (+11.8%)** |

Cost: $0.0838 vs $0.0761, so **+$0.0077 per planning run (+10%)**.

Caveats on the measurement:
- Live web research returns different pages each time, so the venues step mixes the knowledge with research variation.
- The run without the knowledge base happened to get 5,071 cached input tokens; the run with it got none.
- The extra time (171 s vs 129 s) is mostly web-research variation; the retrieval itself is a database query.

## 6. What is still missing (from the knowledge base's own gap check)

- **No board members recorded.** Reviewer suggestions fall back to app roles.
- **Signature events:** attendance, revenue, and net proceeds are not recorded for any of them. One event's official name needs confirmation.
- **Vendors:** contact details are missing for all six; previous costs are missing for three; three vendor names are not recorded.
- **Relationships:** each organization's mission and verified contacts; what the foundation's past work with them involved.
- **Priorities and finance:**
  - no fundraising goal for the year
  - no board-approved budget or spending guideline
  - the foundation's actual cash, revenue, reserves, and restricted funds (the books are demo data)
- **Verification:** 27 of 28 facts are not yet verified by the chair or treasurer.
