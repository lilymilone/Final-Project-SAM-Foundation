# SAM SPACE roadmap

Items here are **planned, not implemented**. Nothing in this file describes current behavior.

## Microsoft Outlook integration (planned, not implemented)

**Today:**
- SAM SPACE does not connect to Outlook or any mail system.
- Outreach drafts stay inside SAM SPACE (Partnerships & Outreach → *Drafts for Board Review*).
- A board member copies the reviewed text and sends it themselves.

**With a board member's explicit authorization, a future version could:**

1. Read selected incoming Outlook messages (one folder or label the board member chooses, not the whole mailbox).
2. Identify foundation-related tasks, such as a venue's reply with pricing, a sponsor's interest, a charity's request, or a donation note.
3. Route each request to the right specialist through the Orchestrator, with the same structured reports, budgets, and safety screening as today. Message text is treated as untrusted data and screened for injected instructions.
4. Draft context-aware responses, saved for human review exactly like today's outreach drafts.
5. Track requests that need follow-up, and show them in the board's review queue.

**Design commitments for that integration:**

| Commitment | How |
|---|---|
| Least privilege | Microsoft Graph with delegated (per-user) consent and read-only mail scopes for the chosen folder. The tenant admin can see and revoke the consent at any time. |
| No sending, ever | **`Mail.Send` is never requested.** No send, reply, forward, or schedule capability exists in code. The prohibited-action registry already refuses those tool names. |
| Drafts stay drafts | Responses are saved in SAM SPACE for review. Writing them into Outlook's own Drafts folder would need a separate, explicit opt-in (`Mail.ReadWrite`), and is not the default. |
| No financial commitments | A message can trigger analysis and recommendations, never a payment, booking, contract, or donation. Board-review statuses never trigger a transaction. |
| Privacy | Only the selected folder is read. Donor details stay behind the existing role permissions. Message bodies never go to public web research tools. |
| Auditability | Every message read, task created, and draft written is logged in Agent Activity with its source message ID. |
| Off by default | The simulated and manual workflows keep working with no Microsoft account, no Graph credentials, and no extra API keys. |

**Why it is not built yet:**
- It needs a registered Microsoft Entra application, the foundation's tenant consent, and a security review of token storage.
- The board should first use the in-app drafts for a while, to confirm the drafts are useful enough to justify mailbox access.

## Other next steps

- **Real-user pilot:** have board members complete the Impact & Evaluation pilot (Analytics & Safety → Impact & Evaluation).
- **Live contact verification refresh:** re-check a draft's contact page before a board member uses it, in case it has changed since the draft was written.
- **Shared budget store:** move the daily spending cap to a shared store if SAM SPACE ever runs on more than one server process.
