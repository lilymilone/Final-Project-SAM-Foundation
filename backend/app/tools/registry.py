"""Tool registry with explicit per-agent permissions.

An agent can call a tool only if all of these hold:
  * the tool is not a prohibited action (safety/policy.py),
  * the tool is on that agent's allow-list (agents/registry.py),
  * the signed-in user's role has the tool's required permission.

Every attempt, allowed or denied, is written to agent_tool_calls with timing
and outcome. Tools marked sensitive (donor and ledger data) log a count-only
summary, never record contents.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..agents.contracts import ToolResult
from ..core.permissions import Permission
from ..db.database import Database
from ..db.models import AgentToolCall
from ..safety.policy import PROHIBITED_ACTIONS


class ToolKind(str, Enum):
    READ = "read"  # read records from the database
    RESEARCH = "research"  # search or fetch public web content (bounded)
    COMPUTE = "compute"  # deterministic Python arithmetic
    DRAFT = "draft"  # create an unsent draft for human review
    SAVE = "save"  # save an internal note/finding inside SAM SPACE


class ProhibitedActionError(PermissionError):
    pass


class ToolPermissionError(PermissionError):
    pass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    kind: ToolKind
    func: Callable[..., Any]
    required_permission: Permission | None = None
    sensitive: bool = False


class ToolRegistry:
    def __init__(self, db: Database | None = None):
        self._tools: dict[str, ToolSpec] = {}
        self._db = db

    def register(self, spec: ToolSpec) -> None:
        if spec.name in PROHIBITED_ACTIONS:
            raise ProhibitedActionError(f"'{spec.name}' is a prohibited action and cannot be registered as a tool.")
        if not isinstance(spec.kind, ToolKind):
            raise ProhibitedActionError(f"Tool '{spec.name}' has no allowed kind.")
        self._tools[spec.name] = spec

    def names(self) -> list[str]:
        return sorted(self._tools)

    def spec(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def call(
        self,
        *,
        agent: str,
        allowed_tools: Iterable[str],
        tool_name: str,
        arguments: dict[str, Any],
        user_permissions: Iterable[Permission],
        run_id: int | None = None,
        handoff_id: int | None = None,
    ) -> Any:
        """Run a tool after permission checks. Returns the tool's own return
        value (usually a ToolResult). Raises on permission problems."""
        log = dict(run_id=run_id, handoff_id=handoff_id, agent=agent, tool_name=tool_name, arguments=arguments)
        if tool_name in PROHIBITED_ACTIONS:
            self._log(**log, allowed=False, denial=f"Prohibited action: {PROHIBITED_ACTIONS[tool_name]}")
            raise ProhibitedActionError(
                f"{PROHIBITED_ACTIONS[tool_name]} is never done by SAM SPACE. A person must do it outside the app."
            )
        if tool_name not in set(allowed_tools):
            self._log(**log, allowed=False, denial="Tool not on this agent's allow-list")
            raise ToolPermissionError(f"Agent '{agent}' is not allowed to use '{tool_name}'.")
        spec = self._tools.get(tool_name)
        if spec is None:
            self._log(**log, allowed=False, denial="Unknown tool")
            raise ToolPermissionError(f"Unknown tool '{tool_name}'.")
        if spec.required_permission and spec.required_permission not in set(user_permissions):
            self._log(**log, allowed=False, denial=f"User lacks {spec.required_permission.value}")
            raise ToolPermissionError(
                f"Your board role does not allow '{tool_name}' (needs {spec.required_permission.value})."
            )

        started = time.perf_counter()
        try:
            result = spec.func(**arguments)
        except Exception as exc:
            duration = int((time.perf_counter() - started) * 1000)
            error = f"{type(exc).__name__}: {str(exc)[:300]}"
            self._log(**log, allowed=True, ok=False, error=error, duration_ms=duration)
            return ToolResult(tool=tool_name, ok=False, error=error, duration_ms=duration)
        duration = int((time.perf_counter() - started) * 1000)
        if isinstance(result, ToolResult):
            result.duration_ms = duration
            ok, summary, error = result.ok, result.summary, result.error
        else:
            ok, summary, error = True, str(result)[:500], None
        if spec.sensitive:
            summary = f"[sensitive: contents not logged] {summary.split('|')[0][:120]}"
        self._log(**log, allowed=True, ok=ok, error=error, summary=summary, duration_ms=duration)
        return result

    def _log(
        self,
        *,
        run_id: int | None,
        handoff_id: int | None,
        agent: str,
        tool_name: str,
        arguments: dict[str, Any],
        allowed: bool,
        denial: str | None = None,
        ok: bool | None = None,
        error: str | None = None,
        summary: str = "",
        duration_ms: int | None = None,
    ) -> None:
        if self._db is None:
            return
        safe_args = {k: v for k, v in arguments.items() if isinstance(v, (str, int, float, bool, type(None)))}
        with self._db.transaction() as session:
            session.add(
                AgentToolCall(
                    run_id=run_id, handoff_id=handoff_id, agent=agent, tool_name=tool_name, arguments=safe_args,
                    allowed=allowed, denial_reason=denial, ok=ok if allowed else False, error=error,
                    result_summary=summary, duration_ms=duration_ms,
                )
            )
