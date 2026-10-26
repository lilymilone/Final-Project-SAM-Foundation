# Speed and cost: Faster vs Most thorough (same event plan)

The same Event Studio request (150-guest Manhattan gala, $18,000 maximum budget, practice venues, lessons from past events) run on two model strategies.
Every figure comes from the app's logs (`agent_runs`, `model_usage`). Quality is compared on structural outcomes only. **No person has rated the writing.**

| | Run #46 | Run #48 | Run #49 |
|---|---|---|---|
| Strategy | Most thorough (auto) | Faster (economy) | Faster (economy) |
| How it was started | Event Studio UI | API, same inputs as #46 | Event Studio UI |
| Time (s) | 206 | 135 | 131 |
| Cost (USD) | 0.3468 | 0.0456 | 0.0449 |
| Model calls | 8 | 8 | 8 |
| Models (total latency) | gpt-6-astra × 1 (29 s), gpt-6-luna × 2 (12 s), gpt-6.1-sol × 5 (165 s) | gpt-6-luna × 7 (100 s), gpt-6.1-sol × 1 (36 s) | gpt-6-luna × 7 (95 s), gpt-6.1-sol × 1 (36 s) |
| Venue shortlisted | Chelsea Atelier (synthetic) | Chelsea Atelier (synthetic) | Chelsea Atelier (synthetic) |
| Finance verdict | affordable with conditions | affordable with conditions | affordable with conditions |
| Revision rounds | 1 | 1 | 1 |
| Venue inquiries drafted | 1 | 1 | 1 |
| Verification checks passed | 9/9 | 9/9 | 9/9 |
| Lessons from past events | 10 | 9 | 10 |
| Lessons applied in the recommendation | 7 | 6 | 6 |
| Recommendation headline | Advance Chelsea Atelier for conditional planning—not booking—for the Smile Like Sab Spring Gala. | Advance Chelsea Atelier for conditional planning—not booking; accessibility and the fundraising target remain unresolved. | Advance Chelsea Atelier for conditional planning—not booking—while resolving accessibility and the fundraising shortfall. |

**Result:**
- On the faster strategy the plan finished in about two-thirds of the time (135 s vs 206 s, and 131 s from the UI) at about one-seventh of the cost.
- Both strategies chose the same venue, reached the same finance verdict, revised once, drafted one inquiry, and passed every verification check.
- The faster runs applied slightly fewer lessons (6 vs 7).

**Why the faster strategy is faster:**
- It routes the medium-complexity steps (lessons, venue strategy, the budget narrative) to gpt-6-luna instead of gpt-6.1-sol, and the final recommendation to Sol instead of Astra.
- Measured across all runs: gpt-6-luna averages 8 s per call, gpt-6.1-sol 28 s, and gpt-6-astra 29 s. Smarter models are slower, not faster.

**Default:** Event Studio and the other *Ask the agents* panels now default to **Faster**. **Most thorough** stays one click away, and each run records which strategy it used.
