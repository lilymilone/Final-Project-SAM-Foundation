"""Isolated PDF text extraction: run as a separate, short-lived process.

    python -m backend.app.services.pdf_worker < file.pdf

Reads the PDF from stdin and prints the parse result as JSON. The parent
passes a minimal environment (no API keys) and a wall-clock timeout; here we
also cap CPU time and memory where the operating system supports it. The
file is only read for text, never executed.
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
    data = sys.stdin.buffer.read()
    from backend.app.services.documents import read_pdf
    sys.stdout.write(json.dumps(read_pdf(data)))


if __name__ == "__main__":
    main()
