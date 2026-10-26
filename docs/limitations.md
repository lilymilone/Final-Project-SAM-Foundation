# SAM SPACE: known limitations

What SAM SPACE does not do yet, where it relies on demonstration data, and what the board should keep in mind. Planned work is in [roadmap.md](roadmap.md); security risks that remain are in [evidence/safety/known_vulnerabilities.md](evidence/safety/known_vulnerabilities.md).

## Not yet implemented

| Item | Status |
|---|---|
| **Microsoft Outlook integration** | **Planned, not implemented.** A future version could, with a board member's explicit authorization, read selected incoming messages (read-only Microsoft Graph), route foundation tasks to the agents, and save draft replies for review. It would never request `Mail.Send` and could never send automatically or commit money. Today all drafts stay in SAM SPACE and are copied by hand. See [roadmap.md](roadmap.md). |
| Real-user evaluation | The Impact & Evaluation pilot works, but **no board member has completed it yet**. The dashboard shows *Pilot pending*. No time savings, quality scores, or quotes have been collected. |
| Human quality scores for history comparisons | The three history comparisons count lesson-backed changes in code. No person has scored the plans' quality yet. |
| Live sponsorship draft | The sponsor → sponsorship-inquiry path is verified by automated tests only. Two live sponsor searches (#44, #45) found no business sponsor. |
| Contact re-check before use | A draft's contact was correct on its verification date. There is no automatic re-check before a board member uses it. |
| Shared budget store | The daily spending cap is enforced per server process. Several processes would each enforce it separately. |

## Reliance on demonstration data

- **Synthetic, labeled "Demo" everywhere:** the board members, the foundation's finances, the donors and gifts, and the sample past events (titles end in "(sample)").
  - The foundation's real financial and donor records are deliberately not in the repository.
- **Synthetic research fixtures** (venues and organizations on `example.org`, with `example.org` contact addresses) power the *Controlled demo* mode. These runs use real models on demo data, so their token counts and costs are real, but the organizations are not.
- **Live runs used real public web pages:**
  - #10 and #40: venues
  - #13 and #43: charities and research centers
  - #44: a sponsor search
- **Sample uploads** in `docs/samples/` are fictional documents made for testing.

## External research limitations

**Bounded on purpose.** Per workflow:
- 4 web searches
- 10 page reads for research
- 2 contact pages per outreach draft

A price or capacity counts only if a fetched page shows it; otherwise the venue says "Quote required".

**Search results can miss the request.**
- Runs #44 and #45 asked for Manhattan business sponsors. Both searches returned charities' gala and sponsorship pages, plus a chamber of commerce, but no business that sponsors.
- The Orchestrator now drafts only for sponsor findings when sponsors are asked for (in #45 it correctly drafted nothing), but the search itself does not yet find sponsors.
- A dedicated sponsor-prospecting search, for example local businesses with community-giving programs, would be a new feature.

**Contact details:**
- Some sites publish no email, or keep it on pages SAM SPACE does not read, such as images, scripts, or pages deeper than one link.
- Others ask automated tools not to read them (robots.txt), and SAM SPACE respects that.
- In those cases the draft says *"Contact email not verified — use official contact page."*

**Web pages change.** Every source shows the date it was checked.

**Hosted web search runs inside the model provider.** SAM SPACE re-fetches each link itself, but cannot see everything the search saw.

## Unverified historical information

- Past-event figures imported from documents or conversation are labeled *not verified accounting data* until the treasurer verifies them.
- Values the extraction could not find in the source stay blank, never guessed.
- Board reflections are self-reported. Lessons drawn from them are AI interpretations linked to their evidence; the board reviews, adopts, or dismisses each.
- The history comparisons show that history changed the plans (lesson-backed changes). They do not show that the changed plans raise more money. That needs real events.

## Model availability and cost

- **Models:** gpt-6-luna, gpt-6.1-sol, and gpt-6-astra were checked on 2026-10-24 with the project's OpenAI key. If a model becomes unavailable, the router uses a recorded fallback.
- **Course key:** with only the course Portkey key, every task runs on gpt-6-luna. That is cheaper, but the steps normally given to Sol or Astra (venue strategy, finance narrative, the board recommendation) may be less thorough.
- **Prices:** taken from OpenAI's pricing page on 2026-10-24 and stored in `backend/app/ai/pricing.json`. Cost figures are list-price estimates from token counts, not invoices.
- **Monthly projections** in [evidence/report/tokenomics.md](evidence/report/tokenomics.md) rest on typed-in usage assumptions, labeled as such.

## Remaining security limitations

Summarized from [evidence/safety/known_vulnerabilities.md](evidence/safety/known_vulnerabilities.md):

- Injection screening is pattern-based and can miss a disguised instruction. Layered defenses mean a miss can mislead a recommendation, but cannot send, spend, or reach private data.
- Worst-case cost reservations use a characters-per-token estimate.
- A third-party PDF parser runs in an isolated, time-limited process.
- Compliance and tax summaries can go out of date. Each shows its check date, and legal or tax questions go to a professional.
- **Demo accounts:** the demo password is public in the README by design, for graders. A real deployment must create real accounts (`backend/scripts/create_user.py`) and turn the demo workspace off.
- **No multi-factor sign-in.**
