"""Isolated document parsing: run as a separate, short-lived process.

    python -m backend.app.services.pdf_worker [pdf|xlsx] < file

Reads the file from stdin and prints the parse result as JSON. The parent
passes a minimal environment (no API keys) and a wall-clock timeout; here we
also cap CPU time and memory where the operating system supports it. Files
are only read for text and cell values, never executed (no macros, no
formulas are evaluated: spreadsheets give their saved values).
"""

from __future__ import annotations

import json
import sys


def _limit_resources() -> None:
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
        try:
            resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024))
        except (ValueError, OSError):
            pass  # not supported on every OS (e.g. macOS)
    except ImportError:
        pass  # Windows: the parent's timeout still applies


def main() -> None:
    _limit_resources()
    kind = sys.argv[1] if len(sys.argv) > 1 else "pdf"
    data = sys.stdin.buffer.read()
    if kind == "xlsx":
        from backend.app.services.legacy_sources import read_xlsx
        sys.stdout.write(json.dumps(read_xlsx(data)))
    else:
        from backend.app.services.documents import read_pdf
        sys.stdout.write(json.dumps(read_pdf(data)))


if __name__ == "__main__":
    main()
