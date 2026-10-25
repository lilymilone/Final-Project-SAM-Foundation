"""Save an Event Strategy Packet and its full structured log for the final report.

    python -m backend.scripts.export_packet 10 12

For each run, writes to docs/evidence/event_studio/:
  packet_run_<id>.md    the readable packet
  packet_run_<id>.json  the packet data
  trace_run_<id>.json   every handoff, tool call, and model call (no prompts, no keys)
"""

from __future__ import annotations

import json
import sys

from sqlalchemy import select

from backend.app.core.config import get_settings
from backend.app.core.env import REPO_ROOT
from backend.app.db.database import Database
from backend.app.db.models import AgentHandoff, AgentRun, AgentToolCall, ModelUsage
from backend.app.services.packet import build_packet, packet_markdown


def trace(db: Database, run_id: int) -> dict:
    with db.session() as s:
        run = s.get(AgentRun, run_id)
        steps = s.scalars(select(AgentHandoff).where(AgentHandoff.run_id == run_id).order_by(AgentHandoff.id)).all()
        tools = s.scalars(select(AgentToolCall).where(AgentToolCall.run_id == run_id).order_by(AgentToolCall.id)).all()
        calls = s.scalars(select(ModelUsage).where(ModelUsage.run_id == run_id).order_by(ModelUsage.id)).all()
    return {
        "run": {"id": run.id, "status": run.status, "research_mode": run.research_mode, "strategy": run.strategy, "provider": run.provider,
                "request": run.request_text, "started_at": run.started_at.isoformat(), "duration_ms": run.duration_ms,
                "spent_usd": run.spent_usd, "model_calls": run.model_calls, "error": run.error},
        "handoffs": [{"id": h.id, "step_key": h.step_key, "kind": h.kind, "revision_round": h.revision_round, "from": h.from_agent,
                      "to": h.to_agent, "objective": h.objective, "status": h.status, "duration_ms": h.duration_ms,
                      "constraints": (h.payload or {}).get("constraints", []), "summary": (h.result or {}).get("summary"),
                      "warnings": (h.result or {}).get("warnings", [])} for h in steps],
        "tool_calls": [{"handoff_id": t.handoff_id, "agent": t.agent, "tool": t.tool_name, "allowed": t.allowed, "ok": t.ok,
                        "duration_ms": t.duration_ms, "summary": t.result_summary, "denial": t.denial_reason, "error": t.error} for t in tools],
        "model_calls": [{"handoff_id": c.handoff_id, "agent": c.agent, "task": c.task, "tier": c.requested_tier, "selected_model": c.selected_model,
                         "model_used": c.model_used, "reason": c.selection_reason, "substitution": c.substitution_note, "attempt": c.attempt,
                         "input_tokens": c.input_tokens, "cached_input_tokens": c.cached_input_tokens, "output_tokens": c.output_tokens,
                         "web_search_calls": c.web_search_calls, "cost_usd": c.estimated_cost_usd, "latency_ms": c.latency_ms,
                         "status": c.status} for c in calls],
    }


def main() -> None:
    db = Database(get_settings().database_path)
    out = REPO_ROOT / "docs" / "evidence" / "event_studio"
    out.mkdir(parents=True, exist_ok=True)
    for arg in sys.argv[1:]:
        run_id = int(arg)
        packet = build_packet(db, run_id, 1, True)
        if packet is None:
            print(f"Run #{run_id} not found.")
            continue
        (out / f"packet_run_{run_id}.md").write_text(packet_markdown(packet), encoding="utf-8")
        (out / f"packet_run_{run_id}.json").write_text(json.dumps(packet, indent=2, default=str), encoding="utf-8")
        (out / f"trace_run_{run_id}.json").write_text(json.dumps(trace(db, run_id), indent=2, default=str), encoding="utf-8")
        print(f"Run #{run_id}: wrote packet_run_{run_id}.md/.json and trace_run_{run_id}.json")


if __name__ == "__main__":
    main()
