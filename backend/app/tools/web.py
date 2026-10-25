"""Bounded public-web access.

fetch_page() is the only code in SAM SPACE that downloads a web page. It
refuses non-HTTP(S) URLs and private, loopback, or link-local hosts (an SSRF
guard). It follows at most 3 redirects, re-checking every hop, stops after
600 KB, and times out after 8 seconds. It extracts only the title,
description, and publication date, which become a SourceRecord. Page text is
never executed, and it reaches a model only inside an "untrusted content"
wrapper.
"""

from __future__ import annotations

import ipaddress
import socket
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urlunparse

import httpx

MAX_BYTES = 600_000
TIMEOUT = httpx.Timeout(connect=5.0, read=8.0, write=5.0, pool=5.0)
DEADLINE_S = 20.0  # total across redirects
MAX_REDIRECTS = 3
USER_AGENT = "SAM-SPACE-research/0.2 (nonprofit board tool; educational project)"
DATE_META = ("article:published_time", "og:published_time", "datepublished", "date", "dc.date", "pubdate", "last-modified")
ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
BLOCKED_HOSTNAMES = ("localhost", "metadata.google.internal", "metadata", "instance-data", "169.254.169.254")


class UnsafeURLError(ValueError):
    pass


def _resolve(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return []
    return sorted({info[4][0] for info in infos})


def _host_is_public(host: str) -> bool:
    addresses = _resolve(host)
    return bool(addresses) and all(ipaddress.ip_address(a).is_global for a in addresses)


def resolve_public(url: str) -> tuple:
    """Validate a URL and resolve its host ONCE. Every address must be public (no loopback, private, link-local,
    cloud-metadata, CGNAT, or reserved ranges). Returns (parsed_url, pinned_ip)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"Only http(s) links can be fetched, not {parsed.scheme or 'none'}.")
    host = (parsed.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeURLError("Link has no host.")
    if parsed.username or parsed.password:
        raise UnsafeURLError("Links with embedded credentials are not fetched.")
    if parsed.port not in (None, 80, 443):
        raise UnsafeURLError("Only standard web ports are allowed.")
    if host in BLOCKED_HOSTNAMES or host.endswith((".internal", ".local", ".localhost")):
        raise UnsafeURLError(f"{host} is not a public internet host.")
    addresses = _resolve(host)
    if not addresses or not all(ipaddress.ip_address(a).is_global for a in addresses):
        raise UnsafeURLError(f"{host} is not a public internet host.")
    return parsed, addresses[0]


def check_url(url: str) -> str:
    resolve_public(url)
    return url


def _pinned(parsed, ip: str) -> tuple[str, dict, dict]:
    """Connect to the IP we validated (so a second DNS answer cannot redirect us: DNS-rebinding protection),
    while sending the real Host header and TLS server name so certificates are still checked for the real host."""
    host = parsed.hostname
    ip_literal = f"[{ip}]" if ":" in ip else ip
    port = f":{parsed.port}" if parsed.port else ""
    target = urlunparse((parsed.scheme, f"{ip_literal}{port}", parsed.path or "/", parsed.params, parsed.query, ""))
    headers = {"Host": host + port}
    extensions = {"sni_hostname": host} if parsed.scheme == "https" else {}
    return target, headers, extensions


class _MetaParser(HTMLParser):
    """Title, meta tags, publication date, and visible text (for checking figures)."""

    MAX_TEXT = 200_000

    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.meta: dict[str, str] = {}
        self.time: str | None = None
        self._in_title = False
        self._skip = 0
        self.text_parts: list[str] = []
        self._text_len = 0

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag in ("script", "style", "noscript", "template"):
            self._skip += 1
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key and a.get("content"):
                self.meta.setdefault(key, a["content"].strip())
        elif tag == "time" and a.get("datetime") and not self.time:
            self.time = a["datetime"]

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in ("script", "style", "noscript", "template") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._in_title and len(self.title) < 300:
            self.title += data
        elif not self._skip and self._text_len < self.MAX_TEXT and data.strip():
            self.text_parts.append(data.strip())
            self._text_len += len(data)


def fetch_page(url: str, *, client: httpx.Client | None = None) -> dict:
    """Fetch one page safely. Returns metadata, never raises for HTTP errors."""
    retrieved = datetime.now(timezone.utc).isoformat(timespec="seconds")
    own_client = client is None
    client = client or httpx.Client(timeout=TIMEOUT, follow_redirects=False, headers={"User-Agent": USER_AGENT})
    deadline = time.monotonic() + DEADLINE_S
    try:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            parsed, ip = resolve_public(current)  # re-validated on every hop
            target, headers, extensions = _pinned(parsed, ip)
            with client.stream("GET", target, headers=headers, extensions=extensions) as resp:
                if resp.is_redirect and resp.headers.get("location"):
                    current = urljoin(current, resp.headers["location"])
                    continue
                status = resp.status_code
                content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                if 200 <= status < 400 and content_type and content_type not in ALLOWED_CONTENT_TYPES:
                    return {"url": url, "final_url": current, "ok": False, "http_status": status, "retrieved_at": retrieved,
                            "error": f"Unsupported content type ({content_type}); only web pages are read.", "blocked": True, "text": ""}
                body = b""
                for chunk in resp.iter_bytes():
                    body += chunk
                    if len(body) >= MAX_BYTES or time.monotonic() > deadline:
                        break
                break
        else:
            return {"url": url, "final_url": current, "ok": False, "http_status": None, "error": "Too many redirects.",
                    "retrieved_at": retrieved}
    except UnsafeURLError as exc:
        return {"url": url, "ok": False, "http_status": None, "error": str(exc), "retrieved_at": retrieved, "blocked": True}
    except httpx.HTTPError as exc:
        return {"url": url, "ok": False, "http_status": None, "error": f"{type(exc).__name__}", "retrieved_at": retrieved}
    finally:
        if own_client:
            client.close()
    return parse_page(url, current, status, content_type, body, retrieved)


def parse_page(url: str, final_url: str, status: int, content_type: str, body: bytes, retrieved: str) -> dict:
    """Parse fetched bytes (text only; nothing is executed). Shared by live fetches and server-side fixtures."""
    meta = {"title": "", "description": None, "published": None}
    text = ""
    if "html" in content_type or body.lstrip()[:15].lower().startswith((b"<!doctype", b"<html")):
        parser = _MetaParser()
        try:
            parser.feed(body.decode("utf-8", errors="ignore"))
        except Exception:
            pass
        meta["title"] = " ".join(parser.title.split()) or parser.meta.get("og:title", "")
        meta["description"] = parser.meta.get("description") or parser.meta.get("og:description")
        meta["published"] = next((parser.meta[k] for k in DATE_META if k in parser.meta), None) or parser.time
        text = " ".join(parser.text_parts)
    elif content_type == "text/plain":
        text = body.decode("utf-8", errors="ignore")[:_MetaParser.MAX_TEXT]
    ok = 200 <= status < 400
    return {
        "url": url,
        "final_url": final_url,
        "ok": ok,
        "http_status": status,
        "title": meta["title"][:300],
        "description": (meta["description"] or "")[:500] or None,
        "published": (meta["published"] or "")[:40] or None,
        "retrieved_at": retrieved,
        "error": None if ok else f"HTTP {status}",
        "text": text if ok else "",
    }


def figures_on_page(text: str, values: list[float]) -> dict[str, bool]:
    """Does each figure appear in the page text? Commas and "$" are ignored, and
    whole numbers must match exactly (so 150 does not match 1500)."""
    import re as _re
    flat = _re.sub(r"(?<=\d),(?=\d{3})", "", text)
    numbers = set(_re.findall(r"\d+(?:\.\d+)?", flat))
    found = {}
    for v in values:
        as_int = str(int(v)) if float(v).is_integer() else None
        found[str(v)] = (as_int in numbers) if as_int else (f"{v:.2f}" in numbers or str(v) in numbers)
    return found


# ── Dates and amounts on fetched pages ──────────────────────────────────────────

_MONTHS = {m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august", "september",
                                        "october", "november", "december"), start=1)}
_MONTH_RX = r"(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\.?"


def dates_in_text(text: str, limit: int = 40) -> list[str]:
    """ISO dates written in the text ("May 9, 2027", "2027-05-09", "5/9/2027")."""
    import re as _re
    from datetime import date as _date
    found: list[str] = []

    def add(y: int, m: int, d: int) -> None:
        try:
            iso = _date(y, m, d).isoformat()
        except ValueError:
            return
        if iso not in found:
            found.append(iso)

    for mon, day, year in _re.findall(_MONTH_RX + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", text, flags=_re.IGNORECASE):
        key = next(k for k in _MONTHS if k.startswith(mon.lower()[:3]))
        add(int(year), _MONTHS[key], int(day))
    for year, month, day in _re.findall(r"\b(\d{4})-(\d{2})-(\d{2})\b", text):
        add(int(year), int(month), int(day))
    for month, day, year in _re.findall(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", text):
        add(int(year), int(month), int(day))
    return found[:limit]


def date_status(claim: str | None, page_dates: list[str]) -> tuple[str, str | None]:
    """Compare a date a search result claims with the dates on the fetched page.
    Returns (status, detail): confirmed | conflicting | unconfirmed | none."""
    from datetime import date as _date
    if not claim:
        return "none", None
    claimed = dates_in_text(claim)
    if not claimed:
        return "unconfirmed", f"The date “{claim}” could not be read as a calendar date."
    if any(c in page_dates for c in claimed):
        return "confirmed", None
    near = [p for p in page_dates for c in claimed if abs((_date.fromisoformat(p) - _date.fromisoformat(c)).days) <= 45]
    if near:
        return "conflicting", f"The search result says {claim}, but the page says {_long_date(near[0])}."
    return "unconfirmed", f"The date {claim} does not appear on the page."


def _long_date(iso: str) -> str:
    from datetime import date as _date
    d = _date.fromisoformat(iso)
    return f"{d:%B} {d.day}, {d.year}"


def money_in_text(text: str, limit: int = 40) -> list[float]:
    import re as _re
    out = []
    for n in _re.findall(r"\$\s?(\d[\d,]*(?:\.\d+)?)", text):
        v = float(n.replace(",", ""))
        if v not in out:
            out.append(v)
    return out[:limit]
