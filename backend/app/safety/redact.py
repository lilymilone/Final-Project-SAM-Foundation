"""Secret redaction for errors, logs, events, and anything shown to a user.

Applied to model-call errors, tool errors, run errors, and security events.
Patterns catch common credential shapes; the configured key values are also
removed by exact match, so even an unusual key format never leaks.
"""

from __future__ import annotations

import re

PATTERNS = [
    re.compile(r"sk-(?:proj-|live-|test-)?[A-Za-z0-9_\-]{12,}"),  # OpenAI-style keys
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{12,}"),
    re.compile(r"(?i)\b(api[_-]?key|x-portkey-api-key|authorization|password|secret|token)\b(\s*[:=]\s*|\"\s*:\s*\")[^\s\"',;]{6,}"),
    re.compile(r"(?i)\bpk-[A-Za-z0-9_\-]{12,}"),
]
REDACTED = "[REDACTED]"


def redact(text: str | None, secrets: tuple[str, ...] | list[str] = ()) -> str:
    if not text:
        return text or ""
    out = str(text)
    for s in secrets:
        if s and len(s) >= 6:
            out = out.replace(s, REDACTED)
    for rx in PATTERNS:
        out = rx.sub(lambda m: (m.group(1) + m.group(2) + REDACTED) if m.lastindex and m.lastindex >= 2 else REDACTED, out)
    return out


def configured_secrets() -> tuple[str, ...]:
    """The live key values from the environment and settings (never logged themselves)."""
    import os
    from ..core.config import get_settings
    values = [os.environ.get(k, "") for k in ("OPENAI_API_KEY", "PORTKEY_API_KEY", "DEMO_PASSWORD", "SESSION_SECRET")]
    try:
        st = get_settings()
        values += [getattr(st, "openai_api_key", "") or "", getattr(st, "portkey_api_key", "") or ""]
    except Exception:
        pass
    return tuple(v for v in values if v)
