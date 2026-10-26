# Foundation Knowledge Base

SAM SPACE's agents know their jobs, but a generic nonprofit assistant does not know *this* foundation: its signature
events, the vendors it has used, the organizations it already knows, who comes to its events, or how it likes to
introduce itself. The Foundation Knowledge Base is where the board records those facts, and every agent consults it.

## Where it is

**Settings → Foundation Knowledge Base** (`/settings/knowledge`).

Ten sections: mission and history, signature events, past fundraisers, vendors and venues, charitable relationships,
community and audience, board structure, fundraising priorities, financial guidelines, and communication preferences.

## What every fact keeps

| Field | Meaning |
|---|---|
| Source | Who or what the fact comes from (a board member, a record, a receipt), with an optional link |
| Contributor, recorded, updated | Who added it and when; who last corrected it |
| Verification | **Verified** (confirmed by the chair or treasurer, or against a record), **Board-reported**, **Approximate**, **Needs confirmation**, or **Sample** |
| Shareable | Whether the fact may appear in an outreach draft (off for costs, internal notes, and anything about people) |
| Our Legacy link | A past fundraiser links to its Our Legacy record instead of copying its figures |

Any board member can add or correct a fact (it is saved as board-reported). Only the chair or treasurer can mark a fact
verified, remove one (it stays visible with the reason, and agents stop seeing it at once), or import a filled-in template.
Board contact details are shown to the chair only and are never sent to a model or a web search.

## How the agents use it

Agents never receive the whole base. A shared, permission-checked tool (`read_foundation_knowledge`) runs in code:

1. At intake, the **Orchestrator** retrieves the facts that bear on the request.
2. When it delegates, it passes each specialist only the fact ids in that specialist's own sections (recorded on the
   handoff as `foundation_passed`).
3. Each specialist retrieves around those ids for its own task (at most 6–8 short facts, ranked by overlap with the
   task), and lists the ids it relied on. Code drops any id it was not given.
4. The final recommendation sees the Orchestrator's facts, and any dollar figure it quotes from them is allowed by the
   verification step only because it is on record.

| Agent | Sections it may draw on | What changes |
|---|---|---|
| Orchestrator | all | Plans with the foundation's history; suggests which board member should review (a suggestion; nothing is assigned) |
| Mission Discovery | mission, relationships, priorities, community | Checks every organization it finds against the relationship directory; a known one is marked "Known to the foundation", never presented as a new discovery |
| Fundraising & Events | signature events, past fundraisers, vendors, community, priorities, finance guidelines | Plans from the foundation's own past events; considers past venues first (live search includes them by name); lists `prior_vendors_considered` |
| Financial Analysis | finance guidelines, priorities, signature events, past fundraisers | Labels each conclusion by kind of figure: demo books, verified history, board estimate, or authorized budget; never treats a past event's cost as available money |
| Donations & Compliance | priorities, relationships, communication, finance guidelines | Follows recorded acknowledgment preferences; legal and tax questions still go to a professional |
| Partnerships & Outreach | mission, relationships, signature events, communication, community, vendors | Introduces the foundation from its facts, adapted to the recipient; acknowledges a recorded relationship accurately; shares only facts marked shareable |
| Event Intelligence | signature events, past fundraisers, vendors, relationships, community | Ties lessons to the foundation's signature events and vendors |

The run page shows **Foundation knowledge used**: which facts the Orchestrator read, which specialist received and
relied on which, and the suggested reviewer. **What an agent would see** on the Knowledge Base page previews a retrieval
for any agent and task without an AI call.

## Privacy

- Real foundation facts live only in the local database. The repository ships a blank template
  (`docs/foundation_knowledge_template.json`) and three labeled samples. A sample stands in only for a section with no
  real facts.
- To load a filled-in template from the command line:
  `python -m backend.scripts.load_foundation_profile path/to/profile.json` (keep the file out of git; `backend/data/`
  is ignored).
- Outreach drafts can contain only facts marked shareable: a draft that quotes an internal cost is rejected by code.
- Board names and contacts from the directory are removed from any outbound web-search query.

## Tests

`tests/test_knowledge.py` (16 tests, invented "(test)" facts, scripted model):
storage and provenance, member and chair permissions, Our Legacy links, template import, samples giving way to real
facts, task-relevant retrieval, and the six behavior tests A–F (gala history, cycling history, a known eating-disorder
organization, outreach accuracy, finance source labeling, and the Orchestrator passing context by section).
