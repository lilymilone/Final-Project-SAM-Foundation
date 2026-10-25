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
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

MAX_BYTES = 600_000
TIMEOUT_S = 8.0
MAX_REDIRECTS = 3
USER_AGENT = "SAM-SPACE-research/0.2 (nonprofit board tool; educational project)"
DATE_META = ("article:published_time", "og:published_time", "datepublished", "date", "dc.date", "pubdate", "last-modified")


class UnsafeURLError(ValueError):
    pass


def _host_is_public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    return bool(infos) and all(ipaddress.ip_address(info[4][0]).is_global for info in infos)


def check_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"Only http(s) links can be fetched, not {parsed.scheme or 'none'}.")
    if not parsed.hostname:
        raise UnsafeURLError("Link has no host.")
    if parsed.port not in (None, 80, 443):
        raise UnsafeURLError("Only standard web ports are allowed.")
    if not _host_is_public(parsed.hostname):
        raise UnsafeURLError(f"{parsed.hostname} is not a public internet host.")
    return url


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
    client = client or httpx.Client(timeout=TIMEOUT_S, follow_redirects=False, headers={"User-Agent": USER_AGENT})
    try:
        current = check_url(url)
        for _ in range(MAX_REDIRECTS + 1):
            with client.stream("GET", current) as resp:
                if resp.is_redirect and resp.headers.get("location"):
                    current = check_url(urljoin(current, resp.headers["location"]))
                    continue
                body = b""
                for chunk in resp.iter_bytes():
                    body += chunk
                    if len(body) >= MAX_BYTES:
                        break
                status = resp.status_code
                content_type = resp.headers.get("content-type", "")
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
    ok = 200 <= status < 400
    return {
        "url": url,
        "final_url": current,
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
