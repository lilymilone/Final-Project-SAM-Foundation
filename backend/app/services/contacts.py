"""Public contact research for outreach drafts: official sources only, never invented.

The order of preference follows the board's rules: the organization's official website, its official contact page, a
publicly listed general-inquiry address, a listed partnership or development contact, and finally the official contact
form. An email address is accepted only if it literally appears on a page of the organization's own website (same
domain). Nothing is guessed: no email patterns, no employee names, no phone numbers. robots.txt is respected, and pages
are fetched through the same SSRF-safe, size- and time-limited fetcher as all other research.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

NOT_VERIFIED = "Contact email not verified — use official contact page."
EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
CONTACT_WORDS = ("contact", "partner", "sponsor", "private-event", "events", "inquir", "enquir", "book", "get-involved", "donate",
                 "support", "giving", "about")
PREFERRED_LOCAL = {
    "venue": ("events", "privateevents", "private-events", "sales", "booking", "bookings", "info", "contact", "hello"),
    "sponsor": ("partnerships", "partners", "sponsorship", "community", "marketing", "info", "contact", "hello"),
    "default": ("partnerships", "partners", "development", "giving", "info", "contact", "hello", "support"),
}
SKIP_LOCAL = ("noreply", "no-reply", "donotreply", "privacy", "unsubscribe", "abuse", "webmaster", "careers", "jobs", "press", "media")


def _site_domain(host: str) -> str:
    parts = (host or "").lower().removeprefix("www.").split(".")
    return ".".join(parts[-3:]) if len(parts) >= 3 and parts[-2] in ("co", "org", "com", "ac") and len(parts[-1]) == 2 else ".".join(parts[-2:])


def _same_site(url: str, domain: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == domain or host.endswith("." + domain)


def empty(name: str, note: str | None = None) -> dict:
    return {"organization": name, "department": None, "email": None, "contact_page_url": None, "source_url": None, "verified_at": None,
            "status": "not_found", "confidence": "none", "display": NOT_VERIFIED, "notes": [note] if note else []}


def pick_email(candidates: list[str], domain: str, kind: str) -> str | None:
    ok = []
    for e in dict.fromkeys(x.strip().strip(".").lower() for x in candidates):
        local, _, dom = e.partition("@")
        if not dom or not (dom == domain or dom.endswith("." + domain)) or any(s in local for s in SKIP_LOCAL):
            continue
        ok.append(e)
    prefs = PREFERRED_LOCAL.get(kind, PREFERRED_LOCAL["default"])
    ok.sort(key=lambda e: next((i for i, p in enumerate(prefs) if e.split("@")[0].replace(".", "") == p.replace("-", "")), len(prefs)))
    return ok[0] if ok else None


def find_contact_live(name: str, website: str | None, kind: str, *, fetch, robots_ok, max_pages: int = 3) -> dict:
    """fetch(url) -> parsed page dict (tools/web.fetch_page); robots_ok(url) -> bool. Returns a contact record."""
    if not website or not website.startswith(("http://", "https://")):
        return empty(name, "No official website is known for this organization.")
    parsed = urlparse(website)
    domain = _site_domain(parsed.hostname or "")
    root = f"{parsed.scheme}://{parsed.netloc}/"
    queue, seen, pages, notes = [website, root], set(), [], []
    while queue and len(pages) < max_pages:
        url = queue.pop(0)
        if url in seen or not _same_site(url, domain):
            continue
        seen.add(url)
        if not robots_ok(url):
            notes.append(f"robots.txt asks automated tools not to read {urlparse(url).path or '/'}, so it was not read.")
            continue
        page = fetch(url)
        if not page.get("ok"):
            if "limit" in (page.get("error") or ""):
                notes.append(f"Stopped after {len(pages)} page(s): {page['error']}. Other contact pages were not checked.")
                break
            notes.append(f"Could not read {url} ({page.get('error') or 'error'}).")
            continue
        pages.append(page)
        ranked = []
        for link in page.get("links") or []:
            href, text = link["href"], (link.get("text") or "").lower()
            if not _same_site(href, domain) or href in seen:
                continue
            score = next((i for i, w in enumerate(CONTACT_WORDS) if w in href.lower() or w.replace("-", " ") in text), None)
            if score is not None:
                ranked.append((score, href.split("#")[0].split("?")[0]))  # no tracking parameters
        queue += [h for _, h in sorted(ranked)[:4] if h not in queue]
    record = empty(name)
    record["notes"] = notes
    best, best_page = None, None
    for page in pages:  # official pages only; an address counts only if it is literally on one of them
        email = pick_email((page.get("mailtos") or []) + EMAIL.findall(page.get("text") or ""), domain, kind)
        if email and best is None:
            best, best_page = email, page
    contact_page = next((p for p in pages if "contact" in (p.get("final_url") or p["url"]).lower()), None) or \
        next((p for p in pages if p.get("has_form")), None)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if contact_page:
        record["contact_page_url"] = contact_page.get("final_url") or contact_page["url"]
    if best:
        local = best.split("@")[0]
        record.update(email=best, source_url=best_page.get("final_url") or best_page["url"], verified_at=best_page.get("retrieved_at") or now,
                      status="verified_email", confidence="high" if local in ("events", "partnerships", "development", "sponsorship") else "medium",
                      department={"events": "Events team", "partnerships": "Partnerships", "development": "Development",
                                  "sponsorship": "Sponsorship"}.get(local), display=best)
    elif contact_page:
        record.update(source_url=record["contact_page_url"], verified_at=contact_page.get("retrieved_at") or now, status="contact_page_only",
                      confidence="medium", display=NOT_VERIFIED)
    elif pages:
        record.update(contact_page_url=pages[0].get("final_url") or pages[0]["url"], source_url=pages[0].get("final_url") or pages[0]["url"],
                      verified_at=pages[0].get("retrieved_at") or now, status="website_only", confidence="low", display=NOT_VERIFIED)
        record["notes"].append("No contact page or public email was found; the official website is listed instead.")
    return record


def synthetic_contact(name: str, fixture: dict | None) -> dict:
    """Contact records for the labeled demo fixtures (example.org). Never presented as real."""
    c = (fixture or {}).get("contact")
    if not c:
        return {**empty(name, "The synthetic listing has no contact details."), "status": "not_found"}
    out = empty(name)
    out.update(email=c.get("email"), department=c.get("department"), contact_page_url=c.get("contact_page"),
               source_url=c.get("contact_page") or c.get("source"), verified_at=None,
               status="synthetic_email" if c.get("email") else "synthetic_contact_page", confidence="synthetic",
               display=(f"{c['email']} (synthetic demo contact)" if c.get("email") else NOT_VERIFIED),
               notes=["Synthetic demo contact on example.org; not a real address."])
    return out
