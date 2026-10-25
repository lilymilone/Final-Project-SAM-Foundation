# Agent permission matrix

Generated from `agents/registry.py` (allow-lists), `safety/manager.py` (data scopes), `tools/catalog.py` (tool scopes), and `safety/policy.py` (prohibited actions).

| Agent | Data it may read | Allowed tools (data scope) |
|---|---|---|
| **Orchestrator** | event_plan, general, opportunities | `read_event_plan` (event_plan), `create_event_plan` (event_plan), `evaluate_constraints` (general), `read_opportunities` (opportunities), `select_opportunities` (opportunities), `verify_final_result` (general) |
| **Mission Discovery** | general, public_web, research_findings | `search_web` (public_web), `fetch_source` (public_web), `classify_mission_alignment` (general), `save_research_finding` (research_findings) |
| **Fundraising & Events** | board_lessons, event_plan, general, public_web | `search_venues` (public_web), `fetch_source` (public_web), `save_venue_candidate` (event_plan), `compute_event_model` (event_plan), `get_historical_lessons` (board_lessons), `read_event_plan` (event_plan) |
| **Financial Analysis** | event_plan, financial_records, general | `read_financial_records` (financial_records), `compute_financial_position` (financial_records), `compute_financial_analysis` (financial_records), `recompute_event_model` (general), `check_event_affordability` (general), `read_document_text` (financial_records), `save_extracted_figures` (financial_records) |
| **Donations & Compliance** | donor_records, general | `read_donations` (donor_records), `flag_donation_issues` (donor_records), `read_compliance_items` (donor_records), `create_acknowledgment_drafts` (donor_records), `create_contribution_acknowledgments` (donor_records) |
| **Partnerships & Outreach** | drafts, general, research_findings | `read_saved_findings` (research_findings), `create_outreach_draft` (drafts) |
| **Event Intelligence & Learning** | board_lessons, board_records, general | `read_historical_events` (board_records), `read_board_reflections` (board_records), `compare_event_outcomes` (board_records), `get_historical_lessons` (board_lessons), `save_historical_lesson` (board_records) |

## Never available to any agent

| Tool name | Meaning |
|---|---|
| `send_email` | Send outreach emails |
| `send_donor_communication` | Send donor communications |
| `make_payment` | Make payments |
| `book_venue` | Book venues |
| `purchase_service` | Purchase services |
| `submit_tax_document` | Submit tax documents |
| `publish_announcement` | Publish announcements |
| `commit_foundation_resources` | Commit foundation resources |
| `approve_donation` | Approve charitable donations |
| `disclose_private_data` | Disclose private financial or donor information |
| `send_message` | Send messages on the foundation's behalf |
| `send_direct_message` | Send direct messages |
| `contact_organization` | Contact outside organizations |
| `schedule_outreach` | Schedule outreach |
| `publish_message` | Publish messages |
| `make_commitment` | Make commitments on the foundation's behalf |

- Only the Orchestrator delegates, in code; no agent has a delegation tool.
- No agent has a shell, filesystem, general database, mail, payment, booking, or publishing tool.
- A tool outside an agent's allow-list or data scope is refused in code and logged as a security event.
