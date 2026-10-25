"""Financial document intake: validation, private storage, and safe parsing.

  * Only CSV (UTF-8 text) and PDF files are accepted, checked by content, not
    just by extension. CSV up to 2 MB; PDF up to 10 MB and 40 pages.
  * The original filename is reduced to safe display text. The file is stored
    under its SHA-256 hash in a folder for the organization, so names can't
    collide, traverse paths, or be guessed. Re-uploading the same file is detected.
  * CSV parsing is deterministic: every row is validated, and nothing is saved
    unless the whole file is valid. Spreadsheet formulas are neutralized.
  * PDFs are read with pypdf, which only extracts text: embedded JavaScript,
    launch actions, and attachments are never executed (their presence is noted).
    Scanned, image-only, or encrypted PDFs are flagged for manual entry instead
    of being guessed at.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import os
import re
import unicodedata
from pathlib import Path

MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 40
MIN_TEXT_PER_PAGE = 25  # fewer characters than this on every page means "probably scanned"
MAX_ROWS = 2000
MAX_AMOUNT = 100_000_000

DOC_TYPES = {
    "income_statement": "Income statement (statement of activities)",
    "financial_position": "Statement of financial position (balance sheet)",
    "event_budget": "Event budget",
    "donation_summary": "Donation summary",
    "expense_records": "Expense records",
    "cash_flow": "Cash-flow information",
    "ledger": "Monthly ledger",
    "other": "Other financial document",
}
KINDS = ("income", "expense", "reserve", "cash", "budget_income", "budget_expense")
RESTRICTIONS = ("unrestricted", "temporarily_restricted", "permanently_restricted")
PURPOSES = ("operations", "program", "event", "fundraising")
PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
LEDGER_COLUMNS = ("period", "kind", "category", "amount_usd")


class DocumentError(ValueError):
    """A problem the board member can fix (wrong type, too large, invalid rows)."""


# ── Names, types, storage ─────────────────────────────────────────────────────────


def sanitize_filename(name: str | None, fallback: str = "document") -> str:
    """Display-safe filename: no directories, control characters, or odd punctuation; at most 120 characters."""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = unicodedata.normalize("NFKC", base)
    base = re.sub(r"[^\w.\- ()]+", "_", base, flags=re.UNICODE).strip(" ._")
    base = re.sub(r"_{2,}", "_", base)
    if not base:
        base = fallback
    stem, dot, ext = base.rpartition(".")
    if dot and len(ext) <= 5:
        return f"{stem[:110]}.{ext.lower()}"
    return base[:120]


def detect_type(data: bytes, filename: str) -> str:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if data[:5] == b"%PDF-":
        if len(data) > MAX_PDF_BYTES:
            raise DocumentError(f"PDFs can be at most {MAX_PDF_BYTES // (1024 * 1024)} MB.")
        return "pdf"
    if ext == "csv":
        if len(data) > MAX_CSV_BYTES:
            raise DocumentError(f"CSV files can be at most {MAX_CSV_BYTES // (1024 * 1024)} MB.")
        if b"\x00" in data[:4096]:
            raise DocumentError("This file is not plain-text CSV.")
        try:
            data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DocumentError("CSV files must be UTF-8 text (save as “CSV UTF-8”).") from exc
        return "csv"
    if ext == "pdf":
        raise DocumentError("This file is named .pdf but is not a PDF.")
    raise DocumentError("Only CSV and PDF files are accepted. For Excel, save the sheet as CSV first.")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def store(data: bytes, root: Path, organization_id: int, digest: str, file_type: str) -> str:
    folder = root / "finance" / str(int(organization_id))
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{digest}.{file_type}"
    path = folder / name
    if not path.exists():
        path.write_bytes(data)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return name


# ── Amounts ─────────────────────────────────────────────────────────────────────────


def parse_amount(text: str | None) -> float | None:
    """'$1,234.50' -> 1234.5; '(1,200)' -> -1200; '1 200' -> 1200. Anything else -> None. Never guesses."""
    if text is None:
        return None
    t = str(text).strip().replace("−", "-").replace("USD", "").replace("$", "").replace(" ", "").replace(" ", "")
    negative = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    if t.startswith("-"):
        negative, t = True, t[1:]
    if not re.fullmatch(r"\d{1,3}(,\d{3})*(\.\d+)?|\d+(\.\d+)?", t):
        return None
    value = float(t.replace(",", ""))
    if not math.isfinite(value) or value > MAX_AMOUNT:
        return None
    return -value if negative else value


def amount_on_page(original: str, page_text: str) -> bool:
    """Does the amount appear on the page? Every number-like token on the page is parsed the same
    deterministic way and compared by value ($1,234 matches 1234.00)."""
    value = parse_amount(original)
    if value is None:
        return False
    for token in re.findall(r"\(?\$?\s?\d[\d,]*(?:\.\d+)?\)?", page_text):
        found = parse_amount(token.replace(" ", ""))
        if found is not None and abs(abs(found) - abs(value)) < 0.005:
            return True
    return False


# ── CSV (deterministic) ───────────────────────────────────────────────────────────


def parse_ledger_csv(text: str) -> tuple[list[dict], list[str]]:
    """Returns (rows, errors). Columns: period, kind, category, amount_usd; optional restriction, purpose,
    currency, description, period_months, period_label. Nothing is partially accepted."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    headers = {(h or "").strip().lower() for h in (reader.fieldnames or [])}
    if not set(LEDGER_COLUMNS) <= headers:
        return [], [f"The CSV needs these columns: {', '.join(LEDGER_COLUMNS)}."]
    rows, errors = [], []
    for line, raw in enumerate(reader, start=2):
        if len(rows) >= MAX_ROWS:
            errors.append(f"More than {MAX_ROWS} rows; split the file.")
            break
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items() if k is not None}
        if not any(r.values()):
            continue
        problems = []
        category = r.get("category", "").lstrip("=+-@\t")[:80]  # neutralize spreadsheet formulas
        amount = parse_amount(r.get("amount_usd"))
        kind = r.get("kind", "").lower()
        restriction = (r.get("restriction") or "").lower().replace(" ", "_") or None
        purpose = (r.get("purpose") or "").lower() or None
        currency = (r.get("currency") or "USD").upper()
        months = r.get("period_months") or "1"
        if not PERIOD.match(r.get("period", "")):
            problems.append("period must look like 2026-09")
        if kind not in KINDS:
            problems.append(f"kind must be one of {', '.join(KINDS)}")
        if not category:
            problems.append("category is empty")
        if amount is None or amount < 0:
            problems.append("amount_usd must be a positive number (the kind says whether it is income or expense)")
        if restriction and restriction not in RESTRICTIONS:
            problems.append(f"restriction must be one of {', '.join(RESTRICTIONS)} (or blank if not documented)")
        if purpose and purpose not in PURPOSES:
            problems.append(f"purpose must be one of {', '.join(PURPOSES)} (or blank)")
        if currency != "USD":
            problems.append("only USD is supported; convert the amount or enter it manually with a note")
        if not months.isdigit() or not 1 <= int(months) <= 12:
            problems.append("period_months must be 1 to 12")
        if problems:
            errors.append(f"Row {line}: {'; '.join(problems)}")
            continue
        rows.append({"period": r["period"], "kind": kind, "category": category, "amount_usd": round(amount, 2),
                     "original_amount": r.get("amount_usd", "")[:60], "restriction": restriction, "purpose": purpose,
                     "currency": "USD", "description": (r.get("description") or "").lstrip("=+-@\t")[:500],
                     "period_months": int(months), "period_label": (r.get("period_label") or "")[:80] or None, "row": line})
    if not rows and not errors:
        errors.append("The CSV has no data rows.")
    return rows, errors


def duplicate_key(row: dict) -> tuple:
    return (row["period"], row["kind"], row["category"].strip().lower(), round(float(row["amount_usd"]), 2))


# ── PDF (text only, never executed) ────────────────────────────────────────────────


def read_pdf(data: bytes) -> dict:
    """Extract page text with pypdf. Returns {pages, page_count, notes, status} where status is
    readable | unreadable. Never raises for a malformed file; it reports it."""
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    notes: list[str] = []
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            try:
                if not reader.decrypt(""):
                    raise PdfReadError("encrypted")
            except Exception:
                return {"pages": [], "page_count": None, "status": "unreadable",
                        "notes": ["The PDF is password-protected. Export an unprotected copy or enter the figures manually."]}
        root = reader.trailer.get("/Root", {})
        root = root.get_object() if hasattr(root, "get_object") else root
        active = []
        for key, label in (("/OpenAction", "an action that runs on open"), ("/AA", "automatic actions")):
            if key in root:
                active.append(label)
        names = root.get("/Names", {})
        names = names.get_object() if hasattr(names, "get_object") else names
        for key, label in (("/JavaScript", "JavaScript"), ("/EmbeddedFiles", "attached files")):
            if key in names:
                active.append(label)
        if active:
            notes.append(f"The PDF contains {', '.join(active)}. SAM SPACE only reads text, so none of it was run or opened.")
        page_count = len(reader.pages)
        pages = []
        for i, page in enumerate(reader.pages[:MAX_PDF_PAGES]):
            try:
                pages.append((page.extract_text() or "").strip())
            except Exception:
                pages.append("")
                notes.append(f"Page {i + 1} could not be read.")
        if page_count > MAX_PDF_PAGES:
            notes.append(f"Only the first {MAX_PDF_PAGES} of {page_count} pages were read.")
    except Exception as exc:  # malformed or hostile files are reported, never trusted
        return {"pages": [], "page_count": None, "status": "unreadable",
                "notes": [f"The PDF could not be read ({type(exc).__name__}). Enter the figures manually or upload a CSV."]}
    image_only = [i + 1 for i, t in enumerate(pages) if len(t) < MIN_TEXT_PER_PAGE]
    if pages and len(image_only) == len(pages):
        notes.append("No readable text was found. This looks like a scanned image; SAM SPACE does not guess at scanned "
                     "figures. Enter them manually or upload a CSV.")
        return {"pages": pages, "page_count": page_count, "status": "unreadable", "notes": notes}
    if image_only:
        notes.append(f"Pages {', '.join(map(str, image_only[:10]))} have no readable text (possibly scanned). "
                     "Check those pages by hand.")
    return {"pages": pages, "page_count": page_count, "status": "readable", "notes": notes}


PARSE_TIMEOUT_S = 20.0


def read_pdf_isolated(data: bytes, timeout: float = PARSE_TIMEOUT_S) -> dict:
    """Parse a PDF in a separate, short-lived process with a time limit and a minimal environment (no API keys), so a
    hostile or pathological file cannot hang the server, exhaust its memory, or reach any secret. Text only."""
    import json
    import os
    import subprocess
    import sys
    from ..core.env import REPO_ROOT
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(REPO_ROOT), "PYTHONIOENCODING": "utf-8"}
    if os.name == "nt":
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
    try:
        proc = subprocess.run([sys.executable, "-m", "backend.app.services.pdf_worker"], input=data, capture_output=True,
                              timeout=timeout, cwd=str(REPO_ROOT), env=env)
    except subprocess.TimeoutExpired:
        return {"pages": [], "page_count": None, "status": "unreadable",
                "notes": [f"Reading this PDF took longer than {int(timeout)} seconds, so it was stopped. Enter the figures manually."]}
    except OSError:
        return read_pdf(data)  # isolation unavailable: still text-only, never executed
    try:
        return json.loads(proc.stdout.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {"pages": [], "page_count": None, "status": "unreadable",
                "notes": ["The PDF could not be read safely (the parser stopped). Enter the figures manually or upload a CSV."]}
