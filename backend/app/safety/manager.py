"""SafetyManager: the single, deterministic safety layer every workflow runs through.

One instance per workflow (and a lightweight one per API request). It
coordinates the nine controls; the model is never asked whether a rule applies.

  1. Tool permissions        authorize_tool(): prohibited names, allow-list, data scope, user permission
  2. User authorization      authorize_user(): role permissions, checked on the server
  3. Workflow limits         before_handoff(), before_tool_call(), check_duration(): steps, tools, time, loops
  4. Spending limits         the WorkflowBudget reservation (ai/budget.py), sized by these limits
  5. Untrusted content       ingest_untrusted(): screen and wrap external text, record injection attempts
  6. Sensitive data          DATA_SCOPES per agent, redact() for anything logged or shown
  7. Output validation       record_output_rejection() from the verification layer
  8. Source verification     agents/verification.py and services/evidence checks report through record()
  9. Security audit events   record(): a SecurityEvent row, details redacted

Every block raises (or returns a refusal) in code, and leaves a SecurityEvent
the board can review in Analytics & Safety.
"""

from __future__ import annotations

import time
from collections import Counter

from ..ai.router import RoutingDecision
from ..core.permissions import Permission
from .limits import SafetyLimits
from .policy import PROHIBITED_ACTIONS, sanitize_untrusted, wrap_untrusted
from .redact import configured_secrets, redact

# Least-privilege data scopes: what kinds of records each agent's tools may touch. A tool whose scope is not
# listed for an agent is refused even if it were mistakenly added to that agent's allow-list.
DATA_SCOPES: dict[str, frozenset[str]] = {
    "orchestrator": frozenset({"general", "event_plan", "opportunities"}),
    "mission_discovery": frozenset({"general", "public_web", "research_findings"}),
    "fundraising_events": frozenset({"general", "public_web", "event_plan", "board_lessons"}),
    "financial_analysis": frozenset({"general", "financial_records", "event_plan"}),
    "donations_compliance": frozenset({"general", "donor_records"}),
    "partnerships_outreach": frozenset({"general", "research_findings", "drafts"}),
    "event_intelligence": frozenset({"general", "board_records", "board_lessons"}),
}

CATEGORY_LABELS = {
    "tool_denied": "Tool request blocked", "prohibited_action": "Prohibited action blocked", "permission_denied": "Access denied (role)",
    "cross_workspace": "Access denied (another workspace)", "injection_detected": "Prompt injection screened out",
    "budget_limit": "Budget limit reached", "budget_stepdown": "Model stepped down to fit the budget", "loop_limit": "Step or loop limit reached", "time_limit": "Time limit reached",
    "tool_limit": "Tool-call limit reached", "model_restricted": "Model restricted by policy", "upload_rejected": "Upload rejected",
    "url_blocked": "Unsafe URL blocked", "output_rejected": "Output rejected or flagged", "limit_changed": "Safety limit changed",
    "secret_redacted": "Secret redacted",
}


def _clip(text: str, n: int) -> str:
    """Shorten at a word boundary, marking the cut."""
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


class SafetyViolation(PermissionError):
    """A request the safety layer refused."""


class SafetyManager:
    def __init__(self, db, limits: SafetyLimits, *, organization_id: int | None, user_id: int | None = None,
                 run_id: int | None = None, cancel=None) -> None:
        self.db = db
        self.limits = limits
        self.organization_id = organization_id
        self.user_id = user_id
        self.run_id = run_id
        self.cancel = cancel
        self.started = time.monotonic()
        self.handoffs = 0
        self.tool_calls = 0
        self.edges: Counter[tuple[str, str, str]] = Counter()
        self.revisions_by_agent: Counter[str] = Counter()
        self.events_recorded = 0

    # 9 ── security audit events ────────────────────────────────────────────────────────

    def record(self, category: str, detail: str, *, severity: str = "medium", agent: str | None = None, defense: str = "") -> None:
        from ..db.models import SecurityEvent
        try:
            with self.db.transaction() as s:
                s.add(SecurityEvent(organization_id=self.organization_id, user_id=self.user_id, run_id=self.run_id, category=category,
                                    severity=severity, agent=agent, defense=defense[:80],
                                    detail=redact(detail, configured_secrets())[:1000]))
            self.events_recorded += 1
        except Exception:  # an audit failure must never crash or unblock anything
            pass

    # 1 ── tool permissions ─────────────────────────────────────────────────────────────

    def authorize_tool(self, *, agent: str, tool_name: str, allowed_tools, tool_scope: str | None, required_permission,
                       user_permissions) -> str | None:
        """Return None if allowed, else the reason. Order: prohibited name, allow-list, data scope, user permission."""
        if tool_name in PROHIBITED_ACTIONS:
            reason = f"Prohibited action: {PROHIBITED_ACTIONS[tool_name]}"
            self.record("prohibited_action", f"{agent} requested “{tool_name}”. {reason}. No such tool exists.", severity="high",
                        agent=agent, defense="Prohibited-action registry")
            return reason
        if tool_name not in set(allowed_tools):
            reason = "Tool not on this agent's allow-list"
            self.record("tool_denied", f"{agent} requested “{tool_name}”, which is not on its allow-list.", severity="high",
                        agent=agent, defense="Per-agent tool allow-list")
            return reason
        if tool_scope and tool_scope not in DATA_SCOPES.get(agent, frozenset({"general"})):
            reason = f"Data scope “{tool_scope}” is outside this agent's access"
            self.record("tool_denied", f"{agent} requested “{tool_name}” ({tool_scope} data), outside its data scope.", severity="high",
                        agent=agent, defense="Least-privilege data scopes")
            return reason
        if required_permission and required_permission not in set(user_permissions):
            reason = f"User lacks {required_permission.value}"
            self.record("permission_denied", f"{agent} needed “{required_permission.value}” for “{tool_name}”; the board member's "
                        "role does not have it.", severity="low", agent=agent, defense="Role permissions")
            return reason
        return None

    # 2 ── user authorization ───────────────────────────────────────────────────────────

    @staticmethod
    def authorize_user(permissions, permission: Permission) -> bool:
        return permission in set(permissions)

    # 3 ── workflow limits ──────────────────────────────────────────────────────────────

    def check_duration(self) -> None:
        from ..agents.runtime import RunStopped
        if self.cancel is not None and self.cancel.is_set():
            raise RunStopped("Stopped by a board member.")
        elapsed = time.monotonic() - self.started
        if elapsed > self.limits.max_workflow_seconds:
            msg = f"Stopped: the workflow ran longer than its {self.limits.max_workflow_seconds}-second limit."
            self.record("time_limit", msg, defense="Workflow duration limit")
            raise RunStopped(msg)

    def before_handoff(self, from_agent: str, to_agent: str, step_key: str, kind: str) -> None:
        """Bounded execution graph: total steps, repeated edges, and revision ping-pong all stop in code."""
        from ..agents.runtime import RunStopped
        self.check_duration()
        if self.handoffs >= self.limits.max_handoffs:
            msg = f"Stopped: reached the limit of {self.limits.max_handoffs} handoffs for one run."
            self.record("loop_limit", msg, defense="Orchestrator step limit")
            raise RunStopped(msg)
        base_step = step_key.split("_revision_")[0].split("_fix")[0]
        edge = (from_agent, to_agent, base_step)
        if kind == "revision":
            self.revisions_by_agent[to_agent] += 1
            if self.revisions_by_agent[to_agent] > max(1, self.limits.max_revisions) + 1:
                msg = (f"Stopped: {to_agent.replace('_', ' ')} was asked to revise {self.revisions_by_agent[to_agent]} times, "
                       f"more than the {self.limits.max_revisions}-round limit allows. A circular revision loop was cut off.")
                self.record("loop_limit", msg, agent=to_agent, defense="Revision limit and loop detector")
                raise RunStopped(msg)
        self.edges[edge] += 1
        if self.edges[edge] > self.limits.max_revisions + 2:
            msg = f"Stopped: the same handoff ({from_agent} → {to_agent}, {base_step}) repeated {self.edges[edge]} times."
            self.record("loop_limit", msg, agent=to_agent, defense="Loop detector")
            raise RunStopped(msg)
        self.handoffs += 1

    def before_tool_call(self, agent: str, tool_name: str) -> None:
        from ..agents.runtime import RunStopped
        self.check_duration()
        self.tool_calls += 1
        if self.tool_calls > self.limits.max_tool_calls:
            msg = f"Stopped: reached the limit of {self.limits.max_tool_calls} tool calls for one run."
            self.record("tool_limit", msg, agent=agent, defense="Tool-call limit")
            raise RunStopped(msg)

    # 4 ── spending (sizes the budget; the reservation itself lives in WorkflowBudget) ─────

    def new_budget(self):
        from ..ai.budget import WorkflowBudget
        return WorkflowBudget(limit_usd=self.limits.workflow_budget_usd, max_calls=self.limits.max_model_calls)

    def on_routing(self, agent: str, decision: RoutingDecision) -> None:
        """Record when policy (not the task) decided the model: the Portkey lock or a budget step-down."""
        if decision.provider == "portkey" and decision.requested_tier != "fast":
            self.record("model_restricted", f"{agent} needed the {decision.requested_tier} tier; the course Portkey key is locked to "
                        f"{decision.model}, so no other model was attempted.", severity="info", agent=agent, defense="Portkey Luna-only lock")
        elif decision.tier != decision.requested_tier and "budget" in decision.reason.lower():
            self.record("budget_stepdown", f"{agent}: the {decision.requested_tier} tier could not fit the remaining budget, so "
                        f"{decision.model} was used instead. {decision.reason[-200:]}", severity="info", agent=agent,
                        defense="Budget-aware routing")

    def on_stop(self, reason: str) -> None:
        low = reason.lower()
        category = ("budget_limit" if "budget" in low or "model calls" in low else "time_limit" if "second" in low else
                    "tool_limit" if "tool calls" in low else "loop_limit" if "handoff" in low or "revise" in low or "repeated" in low else None)
        if category:
            self.record(category, f"Workflow stopped: {reason}", defense="Workflow limits", severity="medium")

    # 5 ── untrusted content ─────────────────────────────────────────────────────────────

    def ingest_untrusted(self, text: str | None, source: str, *, agent: str | None = None, max_chars: int = 2200) -> tuple[str, list[str]]:
        """Screen external text: remove instruction-like sentences, record the attempt, and return text that is
        only ever placed in a labeled data field (never in instructions)."""
        clean, flags = sanitize_untrusted(text or "")
        if flags:
            more = f" and {len(flags) - 3} more" if len(flags) > 3 else ""
            self.record("injection_detected", f"Instruction-like text in {source} was removed before any model saw it: "
                        + "; ".join(f"“{_clip(f, 80)}”" for f in flags[:3]) + more, severity="high", agent=agent,
                        defense="Untrusted-content screening")
        return clean[:max_chars], flags

    @staticmethod
    def as_data(text: str, source: str, max_chars: int = 2200) -> str:
        return wrap_untrusted(text, source, max_chars=max_chars)

    # 6 ── sensitive data ────────────────────────────────────────────────────────────────

    @staticmethod
    def redact(text: str | None) -> str:
        return redact(text, configured_secrets())

    # 7 + 8 ── output and source validation ──────────────────────────────────────────────

    def record_output_rejection(self, agent: str, what: str) -> None:
        self.record("output_rejected", what, severity="medium", agent=agent, defense="Output validation")


def request_safety(db, organization_id: int | None, user_id: int | None) -> SafetyManager:
    """A SafetyManager for an API request (no workflow): used to record events from routes."""
    from ..core.config import get_settings
    from .limits import effective_limits
    return SafetyManager(db, effective_limits(get_settings()), organization_id=organization_id, user_id=user_id)
