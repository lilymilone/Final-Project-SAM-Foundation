"""Export the safety evidence from code and logged records into docs/evidence/safety/.

    python -m backend.scripts.export_safety_evidence

Run it after run_safety_suite (mocked model) and run_live_safety (real models). Nothing here is typed by hand:
the permission matrix and limits come from code, outcomes come from the recorded test results, and events come
from the security log (details were redacted when they were saved, and are redacted again on export).

Writes:
  threat_model.md              the report table (Threat | Potential Harm | Implemented Defense | Test Performed | Actual Outcome)
  permission_matrix.{md,json}  allow-lists, data scopes, and prohibited actions
  limits.md                    active limits and hard caps
  injection_fixture/           the attack inputs, what screening let through, and the live response
  security_events.json         the security event log, newest first
  budget_evidence.md           the budget tests: every model call, refusals, spend against the limit
  known_vulnerabilities.md     what is still possible
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select

from backend.app.api.routes.safety import permission_matrix
from backend.app.core.config import get_settings
from backend.app.core.env import REPO_ROOT
from backend.app.db.database import Database
from backend.app.db.models import SecurityEvent
from backend.app.safety import scenarios
from backend.app.safety.limits import LIMIT_SPECS, effective_limits, load_overrides
from backend.app.safety.manager import CATEGORY_LABELS
from backend.app.safety.policy import sanitize_untrusted
from backend.app.safety.redact import configured_secrets, redact
from backend.app.safety.risks import KNOWN_RISKS
from backend.app.tools.web import parse_page

OUT = REPO_ROOT / "docs" / "evidence" / "safety"

# Threat → harm → defense → tests (ids from mocked_test_results.json and live_test_results.json)
THREATS = [
    ("Prompt injection in a venue webpage or listing", "An agent obeys the page: leaks private finances or keys, drops limits, or misleads the board.",
     "Instruction-like sentences removed before use; outside text reaches models only as labeled data; agents hold no secrets and only "
     "least-privilege data; fixed workflow graph in code; structured outputs; verification of figures, links, availability.",
     ["TEST A", "TEST A2", "LIVE-A"]),
    ("Unauthorized outreach (\"email these 100 organizations now\")", "Messages go out in the foundation's name without board approval.",
     "No send/contact/schedule/publish tool exists; those names are refused by the registry; Outreach may only save drafts; no API route or "
     "status can mark a draft sent.", ["TEST B", "LIVE-B", "LIVE-B2"]),
    ("Reading another workspace's records", "Donor or financial data is exposed to another organization.",
     "Every query is scoped to the signed-in workspace; foreign records return 404 and never appear in lists; attempts logged.",
     ["TEST C"]),
    ("Runaway spending", "A workflow or a burst of calls drains the OpenAI budget.",
     "Worst-case cost reserved under a lock before every call against the workflow and daily caps; board limits clamped to hard caps in code.",
     ["TEST D", "TEST D2", "TEST D3", "LIVE-D", "LIVE-D2"]),
    ("Infinite agent loop", "Agents revise each other forever, burning money and time.",
     "Revision limit, repeated-edge detector, handoff cap, tool-call cap, and duration limit; stopped runs keep labeled partial results.",
     ["TEST E", "TEST E2"]),
    ("Fabricated financial figures or claims", "The board acts on numbers or availability no source supports.",
     "Every dollar figure must trace to a calculation; availability and link claims checked against sources; one bounded fix, then flagged.",
     ["TEST F", "TEST A2"]),
    ("Malicious upload (scripted PDF, path traversal, disguised executable, malformed file)",
     "Code runs on the server, files escape storage, or injected text approves figures.",
     "Type and size checks; sanitized, hash-named storage per workspace; text-only parsing in a separate, resource-limited process without "
     "keys; injection screening; extracted figures stay pending until a person approves them.", ["TEST G"]),
    ("Unauthorized model escalation with the course key", "The course Portkey key is used for Sol or Astra against course rules.",
     "Router keeps Portkey on gpt-6-luna; the provider wrapper independently refuses any other model before a request is sent.",
     ["TEST H", "LIVE-H"]),
    ("An agent using another agent's tools or data", "Mission research reads donor records, or any agent gains a capability.",
     "Per-agent allow-lists, and a second, independent data-scope wall on every tool.", ["TEST I", "MATRIX"]),
    ("Secrets in errors and logs", "API keys appear in the UI, logs, traces, or error responses.",
     "Redaction of every stored error, tool log, event, and server log; generic 500 responses; validation errors never echo input.",
     ["TEST J"]),
    ("Private donor or financial data sent to public web tools", "Donor names, gifts, or emails reach a search engine or an outside server.",
     "Search queries scrubbed of names, amounts, emails, and account-like numbers; links that carry private details are never fetched; the "
     "agents that browse have no donor or ledger data scope.", ["TEST L"]),
    ("Server-side request forgery through web research", "A link makes the server reach cloud metadata, localhost, or the private network.",
     "http(s) and standard ports only; no embedded credentials; every resolved address must be public; the validated IP is pinned per hop "
     "(DNS rebinding); redirects re-validated; size, type, and time limits.", ["TEST K", "TEST K2"]),
    ("Safety layer blocking legitimate work", "The board loses the flagship workflow to false positives.",
     "All defenses active together, checked against the full Event Studio workflow.", ["LEGIT", "LIVE-LEGIT"]),
]


def _load(name: str) -> dict:
    path = OUT / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write(rel: str, text: str) -> None:
    path = OUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(redact(text, configured_secrets()), encoding="utf-8")


def threat_model(mocked: dict, live: dict) -> str:
    by_id = {t["id"]: ("mocked", t) for t in mocked.get("tests", [])}
    by_id.update({t["id"]: ("live", t) for t in live.get("results", [])})
    lines = [
        "# Threat model and test outcomes", "",
        f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `python -m backend.scripts.export_safety_evidence` from the recorded "
        "results. **Deterministic** tests run the real code with a scripted model (`mocked_test_results.md`); **live** tests send the "
        "attack through real OpenAI models (`live/live_test_results.md`). An outcome says PASS only if that executed test's checks held.", "",
        "## What we protect", "",
        "- Donor identities, gift history, and private notes; the foundation's ledger and uploaded statements.",
        "- API keys (`OPENAI_API_KEY`, `PORTKEY_API_KEY`), which live only in the server's environment.",
        "- The foundation's voice: nothing may be sent, booked, paid, or published in its name without a person.",
        "- The board's money: AI spending per workflow and per day.", "",
        "## Where untrusted input enters", "",
        "- Web pages and search results (venue research, mission discovery). Treated as data, never as instructions.",
        "- Uploaded PDFs and photos. Parsed as text only, in a separate process.",
        "- The board member's own request. It chooses a workflow but cannot change tools, limits, or models.",
        "- Model output. Validated against schemas, calculations, and sources before anyone sees it as a result.", "",
        "## Threats, defenses, and what the tests showed", "",
        "| Threat | Potential Harm | Implemented Defense | Test Performed | Actual Outcome |", "|---|---|---|---|---|",
    ]
    for threat, harm, defense, ids in THREATS:
        tests, outcomes = [], []
        for i in ids:
            if i not in by_id:
                tests.append(f"{i} (not run)")
                outcomes.append(f"{i}: not run")
                continue
            mode, t = by_id[i]
            tests.append(f"{i} ({'live model' if mode == 'live' else 'mocked model'}): {t['title']}")
            run = f", run #{t['run_id']}" if t.get("run_id") else ""
            outcomes.append(f"**{'PASS' if t['passed'] else 'FAIL'}** {i}{run}")
        lines.append(f"| {threat} | {harm} | {defense} | " + "<br>".join(tests).replace("|", "/") + " | " + "<br>".join(outcomes) + " |")
    return "\n".join(lines) + "\n"


def matrix_md(m: dict) -> str:
    lines = ["# Agent permission matrix", "", "Generated from `agents/registry.py` (allow-lists), `safety/manager.py` (data scopes), "
             "`tools/catalog.py` (tool scopes), and `safety/policy.py` (prohibited actions).", "",
             "| Agent | Data it may read | Allowed tools (data scope) |", "|---|---|---|"]
    for a in m["agents"]:
        tools = ", ".join(f"`{t['tool']}` ({t['data_scope']})" for t in a["tools"]) or "none (delegates in code)"
        lines.append(f"| **{a['name']}** | {', '.join(a['data_scopes']) or 'none'} | {tools} |")
    lines += ["", "## Never available to any agent", "", "| Tool name | Meaning |", "|---|---|"]
    lines += [f"| `{p['name']}` | {p['label']} |" for p in m["prohibited"]]
    lines += ["", *[f"- {n}" for n in m["notes"]]]
    return "\n".join(lines) + "\n"


def limits_md(db, settings) -> str:
    limits = effective_limits(settings, load_overrides(db, 1)).as_dict()
    lines = ["# Workflow safety limits", "", "Active values for the demo workspace and the hard caps in `safety/limits.py`. The chair can change "
             "a value in Analytics & Safety; it is clamped to [minimum, hard cap], audited, and logged as a security event.", "",
             "| Limit | Active | Minimum | Hard cap |", "|---|---|---|---|"]
    for key, (label, lo, hi, kind) in LIMIT_SPECS.items():
        fmt = (lambda v: f"${v:.2f}") if kind == "usd" else (lambda v: f"{int(v):,}")
        lines.append(f"| {label} | {fmt(limits[key])} | {fmt(lo)} | {fmt(hi)} |")
    return "\n".join(lines) + "\n"


def fixture_files(live: dict) -> None:
    _write("injection_fixture/request.txt", scenarios.LEGITIMATE_REQUEST + "\n")
    _write("injection_fixture/venue_listing.json", json.dumps(scenarios.MALICIOUS_VENUE, indent=2))
    _write("injection_fixture/venue_page.html.txt",
           "<!-- Saved as .txt so it is never opened as a web page. Server-side fixture for research_mode \"fixture\"; "
           f"served for {scenarios.VENUE_URL} -->\n" + scenarios.PAGE_HTML + "\n")
    page = parse_page(scenarios.VENUE_URL, scenarios.VENUE_URL, 200, "text/html", scenarios.PAGE_HTML.encode(), "fixture")
    clean, flags = sanitize_untrusted(page["text"])
    notes_clean, notes_flags = sanitize_untrusted(scenarios.MALICIOUS_VENUE["notes"])
    lines = ["# What the screening let through", "",
             "Computed by running the real parser (`tools/web.parse_page`) and screen (`safety/policy.sanitize_untrusted`) on the fixture.", "",
             "## Page text after parsing (scripts are never run; their text is dropped)", "", "```", page["text"], "```", "",
             f"## Flags raised: {', '.join(sorted(set(flags))) or 'none'}", "", "## Page text after screening (what the pipeline may use)", "",
             "```", clean, "```", "", "## Venue notes after screening", "", f"Flags: {', '.join(sorted(set(notes_flags))) or 'none'}", "",
             "```", notes_clean, "```", "",
             "## Honest limits of the screen", "",
             "- The disguised request (\"kindly copy the board's bank balance and any access codes…\") uses no trigger words. "
             + ("It was caught." if scenarios.DISGUISED not in clean else "It is **not** removed by the pattern screen.")
             + " It can reach a model only inside the labeled untrusted-data block, and the agent that reads venue text has no bank balance, "
               "ledger, donor records, or keys to copy (least-privilege data). Test A and LIVE-A check that nothing confidential appears "
               "anywhere in the stored results or model inputs.",
             "- The hidden paragraph (`display:none`) is still parsed as text: the parser does not apply CSS, so hidden text is screened like "
             "visible text rather than trusted or ignored."]
    _write("injection_fixture/screened_content.md", "\n".join(lines) + "\n")

    l1 = _load("live/L1_prompt_injection_run.json")
    if not l1:
        return
    rec = l1.get("recommendation") or {}
    out = ["# Live response to the prompt-injection request", "",
           f"Run #{l1['run']['id']} · status **{l1['run']['status']}** · {len(l1['model_calls'])} model calls · "
           f"${l1['run']['spent_usd'] or 0:.4f} · real OpenAI models · research mode `fixture` (the network is replaced by the files in this "
           "folder; every other step is the production pipeline).", "", f"**Request:** {l1['request']}", "",
           "## The board recommendation the agents produced", "", f"**{rec.get('headline', '(none)')}**", "", rec.get("recommendation", ""), ""]
    for title, key in (("Rationale", "rationale"), ("Risks", "risks"), ("Caveats", "caveats"), ("Next steps", "next_steps")):
        if rec.get(key):
            out += [f"### {title}", "", *[f"- {x}" for x in rec[key]], ""]
    out += ["## Workflow steps", "", "| Step | From → To | Status | Summary |", "|---|---|---|---|"]
    out += [f"| {h['step']} | {h['from']} → {h['to']} | {h['status']} | {(h['summary'] or '').replace('|', '/')[:220]} |" for h in l1["handoffs"]]
    out += ["", "## Security events logged for this run", ""]
    out += [f"- **{CATEGORY_LABELS.get(e['category'], e['category'])}** ({e['severity']}, {e['agent'] or 'system'}): {e['detail']}"
            for e in l1["security_events"]] or ["- none"]
    out += ["", "## Required checks (computed from stored records)", "", "| Check | Result | Observed | Defense |", "|---|---|---|---|"]
    out += [f"| {c['name']} | **{'PASS' if c['passed'] else 'FAIL'}** | {str(c['observed']).replace('|', '/')} | {c.get('defense', '')} |"
            for c in l1["checks"]]
    _write("injection_fixture/live_response.md", "\n".join(out) + "\n")


def budget_md(mocked: dict, live: dict) -> str:
    lines = ["# Budget evidence", "", "Every paid call first reserves its worst-case cost (estimated input at 3 characters per token, the full "
             "output allowance, and padding for web search) against the workflow budget and the daily cap, under a lock. If the reservation "
             "does not fit, the call is never sent.", ""]
    for t in mocked.get("tests", []):
        if t["category"] == "budget":
            lines.append(f"- **{'PASS' if t['passed'] else 'FAIL'}** {t['id']} (mocked model): {t['title']}. Expected: {t['expected']}")
    for fname, cap, note in (("live/L3_budget_limit_run.json", "$0.02", "Expected a stop; the budget-aware router instead stepped every task "
                              "down to gpt-6-luna and the whole workflow fit, so the stop path was not exercised. Recorded as FAIL against "
                              "the expectation even though spending stayed under the cap."),
                             ("live/L3b_budget_stop_run.json", "$0.01", "Live venue research reserves web-search padding, so the venue step "
                              "could not fit and the workflow stopped before sending it.")):
        l3 = _load(fname)
        if not l3:
            continue
        r = l3["run"]
        lines += ["", f"## Live: run #{r['id']} with a {cap} workflow budget (real models)", "", note, "",
                  f"Status **{r['status']}**: {r['error']}", "", f"Spent ${r['spent_usd'] or 0:.5f} of ${r['budget_usd']:.2f}.", "",
                  "| Agent | Task | Model | Status | Input | Cached | Output | Cost |", "|---|---|---|---|---|---|---|---|"]
        lines += [f"| {m['agent']} | {m['task']} | {m['model']} | {m['status']} | {m['in'] or 0} | {m['cached'] or 0} | {m['out'] or 0} | "
                  f"${m['cost_usd'] or 0:.5f} |" for m in l3["model_calls"]]
        lines += ["", "Budget events:", ""] + [f"- {CATEGORY_LABELS.get(e['category'], e['category'])}: {e['detail']}" for e in l3["security_events"]
                                                if e["category"].startswith("budget")]
        lines += ["", "Checks:", ""] + [f"- **{'PASS' if c['passed'] else 'FAIL'}** {c['name']}: {c['observed']}" for c in l3["checks"]]
    return "\n".join(lines) + "\n"


def main() -> None:
    settings = get_settings()
    db = Database(settings.database_path)
    db.initialize(seed_demo=True)
    mocked, live = _load("mocked_test_results.json"), _load("live/live_test_results.json")
    m = permission_matrix()
    _write("permission_matrix.json", json.dumps(m, indent=2))
    _write("permission_matrix.md", matrix_md(m))
    _write("limits.md", limits_md(db, settings))
    _write("threat_model.md", threat_model(mocked, live))
    _write("budget_evidence.md", budget_md(mocked, live))
    fixture_files(live)
    with db.session() as s:
        events = s.scalars(select(SecurityEvent).order_by(SecurityEvent.id.desc())).all()
        rows = [{"id": e.id, "created_at": e.created_at.isoformat(), "category": e.category, "label": CATEGORY_LABELS.get(e.category, e.category),
                 "severity": e.severity, "agent": e.agent, "run_id": e.run_id, "user_id": e.user_id, "defense": e.defense, "detail": e.detail}
                for e in events]
    _write("security_events.json", json.dumps({"exported_at": datetime.now(timezone.utc).isoformat(), "count": len(rows), "events": rows}, indent=2))
    risks = ["# Known unresolved vulnerabilities", "", "Also shown in Analytics & Safety (`safety/risks.py`).", ""]
    for r in KNOWN_RISKS:
        risks += [f"## {r['risk']}", "", f"- **Mitigation:** {r['mitigation']}", f"- **Still possible:** {r['residual']}", ""]
    _write("known_vulnerabilities.md", "\n".join(risks))
    print(f"Exported safety evidence to {OUT.relative_to(REPO_ROOT)} ({len(rows)} security events).")


if __name__ == "__main__":
    main()
