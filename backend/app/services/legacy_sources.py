"""Our Legacy source files: what may be uploaded, how each type is read, and where it is kept.

Supported: PDF (text only), CSV, XLSX (saved cell values; macros and formulas are never run), plain-text notes
(.txt/.md), and JPG/PNG photographs. The type is decided by the file's contents, not its name. PDFs and
spreadsheets are parsed in a separate, resource-limited process without API keys. Photos are stored with the
event but never read for numbers: SAM SPACE does not infer fundraising figures from photographs.

Extracted text is untrusted. It is screened for injected instructions whenever it is used, and it reaches a model
only as labeled data.
"""

from __future__ import annotations

import csv
import io
import os
import zipfile
from datetime import date, datetime
from pathlib import Path

from .documents import DocumentError, read_pdf_isolated, sanitize_filename, sha256

MB = 1024 * 1024
MAX_BYTES = {"pdf": 10 * MB, "csv": 2 * MB, "xlsx": 5 * MB, "text": 1 * MB, "image": 5 * MB}
MAX_FILES_PER_IMPORT = 8
MAX_TEXT_CHARS = 60_000  # stored per document
MAX_SHEETS, MAX_SHEET_ROWS, MAX_SHEET_COLS = 6, 400, 30
MAX_CSV_ROWS = 400
ZIP_MAX_MEMBERS, ZIP_MAX_TOTAL, ZIP_MAX_MEMBER = 300, 60 * MB, 30 * MB
CONTENT_TYPES = {"pdf": "application/pdf", "csv": "text/csv", "text": "text/plain",
                 "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
SUPPORTED = "PDF, CSV, XLSX, JPG or PNG photos, and .txt or .md notes"


def detect(data: bytes, filename: str) -> tuple[str, str]:
    """(file_type, content_type) from the file's contents; the name's extension only disambiguates text formats."""
    name = sanitize_filename(filename)
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    if not data:
        raise DocumentError("The file is empty.")
    if data[:5] == b"%PDF-":
        kind, ctype = "pdf", CONTENT_TYPES["pdf"]
    elif data[:8] == b"\x89PNG\r\n\x1a\n":
        kind, ctype = "image", "image/png"
    elif data[:3] == b"\xff\xd8\xff":
        kind, ctype = "image", "image/jpeg"
    elif data[:4] == b"PK\x03\x04":
        if ext in ("xlsm", "xlsb", "xls"):
            raise DocumentError("Macro-enabled or older Excel files are not accepted. Save the sheet as .xlsx (or CSV).")
        if ext != "xlsx":
            raise DocumentError(f"This looks like a compressed archive. Supported files: {SUPPORTED}.")
        try:  # a real workbook, checked without unpacking anything
            names = set(zipfile.ZipFile(io.BytesIO(data)).namelist())
        except zipfile.BadZipFile as exc:
            raise DocumentError("This file is named .xlsx but is not an Excel workbook.") from exc
        if "xl/workbook.xml" not in names:
            raise DocumentError("This file is named .xlsx but is not an Excel workbook.")
        if any(n.lower().endswith("vbaproject.bin") for n in names):
            raise DocumentError("The workbook contains macros. Save it as a plain .xlsx without macros.")
        kind, ctype = "xlsx", CONTENT_TYPES["xlsx"]
    elif data[:2] == b"MZ" or data[:4] == b"\x7fELF" or data[:4] in (b"\xca\xfe\xba\xbe", b"\xcf\xfa\xed\xfe"):
        raise DocumentError("Programs cannot be uploaded.")
    elif ext in ("csv", "txt", "md"):
        if b"\x00" in data[:4096]:
            raise DocumentError("This file is not plain text.")
        try:
            data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DocumentError("Text and CSV files must be UTF-8 (save as “CSV UTF-8” or plain text).") from exc
        head = data[:512].lstrip().lower()
        if head.startswith((b"<!doctype html", b"<html", b"<svg", b"<script")):
            raise DocumentError("Web pages and scripts cannot be uploaded as notes.")
        kind = "csv" if ext == "csv" else "text"
        ctype = CONTENT_TYPES[kind]
    else:
        if ext == "pdf":
            raise DocumentError("This file is named .pdf but is not a PDF.")
        if ext in ("jpg", "jpeg", "png"):
            raise DocumentError("This file is named as a photo but is not a JPG or PNG image.")
        raise DocumentError(f"Unsupported file. Supported files: {SUPPORTED}.")
    if len(data) > MAX_BYTES[kind]:
        raise DocumentError(f"{kind.upper() if kind != 'image' else 'Photos'} can be at most {MAX_BYTES[kind] // MB} MB.")
    return kind, ctype


def store(data: bytes, root: Path, organization_id: int, file_type: str) -> tuple[str, str]:
    """Write the original file to the workspace's private folder under a hash name. Returns (stored_name, sha256)."""
    digest = sha256(data)
    folder = root / "legacy" / str(int(organization_id))
    folder.mkdir(parents=True, exist_ok=True)
    ext = {"pdf": "pdf", "csv": "csv", "xlsx": "xlsx", "text": "txt", "image": "img"}[file_type]
    name = f"{digest}.{ext}"
    path = folder / name
    if not path.exists():
        path.write_bytes(data)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return name, digest


def stored_path(root: Path, organization_id: int, stored_name: str) -> Path | None:
    folder = (root / "legacy" / str(int(organization_id))).resolve()
    path = (folder / stored_name).resolve()
    return path if folder in path.parents and path.is_file() else None


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat() if (v.hour, v.minute, v.second) == (0, 0, 0) else v.isoformat(sep=" ", timespec="minutes")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return " ".join(str(v).split())[:300]


def read_xlsx(data: bytes) -> dict:
    """Saved cell values only. Checks the archive first (size, member count, no macros, no DTDs)."""
    notes: list[str] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        infos = zf.infolist()
        if len(infos) > ZIP_MAX_MEMBERS or sum(i.file_size for i in infos) > ZIP_MAX_TOTAL or any(i.file_size > ZIP_MAX_MEMBER for i in infos):
            return {"status": "unreadable", "text": "", "notes": ["The spreadsheet expands to an unsafe size, so it was not opened."]}
        names = {i.filename for i in infos}
        if "xl/workbook.xml" not in names:
            return {"status": "unreadable", "text": "", "notes": ["This is not an Excel workbook."]}
        if any(n.lower().endswith("vbaproject.bin") for n in names):
            return {"status": "unreadable", "text": "", "notes": ["The workbook contains macros, so it was not opened. Save it as a plain .xlsx."]}
        for i in infos:
            if i.filename.endswith((".xml", ".rels")) and b"<!DOCTYPE" in zf.read(i)[:2048].upper():
                return {"status": "unreadable", "text": "", "notes": ["The workbook contains a document-type declaration, so it was not opened."]}
        if any(n.startswith("xl/externalLinks/") for n in names):
            notes.append("The workbook links to other files; those links were ignored.")
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        parts = []
        for ws in wb.worksheets[:MAX_SHEETS]:
            rows = []
            for row in ws.iter_rows(max_row=MAX_SHEET_ROWS, max_col=MAX_SHEET_COLS, values_only=True):
                cells = [_cell(v) for v in row]
                if any(cells):
                    rows.append(" | ".join(cells).rstrip(" |"))
            if rows:
                parts.append(f"[Sheet: {ws.title}]\n" + "\n".join(rows))
            if ws.max_row and ws.max_row > MAX_SHEET_ROWS:
                notes.append(f"Only the first {MAX_SHEET_ROWS} rows of sheet “{ws.title}” were read.")
        if len(wb.worksheets) > MAX_SHEETS:
            notes.append(f"Only the first {MAX_SHEETS} sheets were read.")
        wb.close()
    except Exception as exc:  # malformed or hostile files are reported, never trusted
        return {"status": "unreadable", "text": "", "notes": [f"The spreadsheet could not be read ({type(exc).__name__})."]}
    text = "\n\n".join(parts)
    if not text.strip():
        return {"status": "unreadable", "text": "", "notes": notes + ["The spreadsheet has no values."]}
    notes.append("Spreadsheet values are the saved results; formulas were not recalculated and macros never run.")
    return {"status": "readable", "text": text[:MAX_TEXT_CHARS], "notes": notes}


def read_xlsx_isolated(data: bytes, timeout: float = 20.0) -> dict:
    import json
    import subprocess
    import sys
    from ..core.env import REPO_ROOT
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(REPO_ROOT), "PYTHONIOENCODING": "utf-8"}
    if os.name == "nt":
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
    try:
        proc = subprocess.run([sys.executable, "-m", "backend.app.services.pdf_worker", "xlsx"], input=data, capture_output=True,
                              timeout=timeout, cwd=str(REPO_ROOT), env=env)
    except subprocess.TimeoutExpired:
        return {"status": "unreadable", "text": "", "notes": [f"Reading the spreadsheet took longer than {int(timeout)} seconds, so it was stopped."]}
    except OSError:
        return read_xlsx(data)
    try:
        return json.loads(proc.stdout.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {"status": "unreadable", "text": "", "notes": ["The spreadsheet could not be read safely (the parser stopped)."]}


def read_source(data: bytes, file_type: str) -> dict:
    """{status: readable|unreadable|photo, text, notes}. Text is untrusted and capped."""
    if file_type == "image":
        return {"status": "photo", "text": "", "notes": ["Kept as a photograph of the event. SAM SPACE does not read text or "
                                                         "numbers from photos, so no figures come from this file."]}
    if file_type == "pdf":
        parsed = read_pdf_isolated(data)
        pages = parsed.get("pages") or []
        text = "\n\n".join(f"[Page {i + 1}]\n{t}" for i, t in enumerate(pages) if t.strip())
        status = "readable" if parsed.get("status") == "readable" and text.strip() else "unreadable"
        return {"status": status, "text": text[:MAX_TEXT_CHARS], "notes": parsed.get("notes") or []}
    if file_type == "xlsx":
        return read_xlsx_isolated(data)
    decoded = data.decode("utf-8-sig", errors="replace")
    if file_type == "csv":
        rows, notes = [], []
        try:
            for i, row in enumerate(csv.reader(io.StringIO(decoded))):
                if i >= MAX_CSV_ROWS:
                    notes.append(f"Only the first {MAX_CSV_ROWS} rows were read.")
                    break
                cells = [" ".join(c.split())[:300] for c in row[:MAX_SHEET_COLS]]
                if any(cells):
                    rows.append(" | ".join(cells))
        except csv.Error as exc:
            return {"status": "unreadable", "text": "", "notes": [f"The CSV could not be read ({exc})."]}
        text = "\n".join(rows)
        return {"status": "readable" if text.strip() else "unreadable", "text": text[:MAX_TEXT_CHARS], "notes": notes}
    text = decoded.strip()
    return {"status": "readable" if text else "unreadable", "text": text[:MAX_TEXT_CHARS],
            "notes": ["Only the first 60,000 characters were kept."] if len(text) > MAX_TEXT_CHARS else []}
