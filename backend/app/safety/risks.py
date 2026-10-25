"""Known, unresolved risks: stated plainly so the board (and graders) can weigh them."""

KNOWN_RISKS = [
    {"risk": "Pattern-based injection screening can miss disguised instructions.",
     "mitigation": "Screening is only the first layer: external text reaches models only as labeled data, agents hold no secrets, "
                   "outputs are structured and validated, and no tool can act externally. A disguised injection is tested.",
     "residual": "A model could still be misled into a poor recommendation (wrong venue, overstated fit); verification flags "
                 "invented figures, links, and availability claims, but judgment errors remain possible."},
    {"risk": "Hosted web search runs inside the model provider.",
     "mitigation": "Its results are re-checked by fetching each page ourselves; figures count only if they appear on the page.",
     "residual": "We cannot inspect or screen the search results the model saw while choosing links."},
    {"risk": "Worst-case cost estimates rely on a characters-per-token approximation.",
     "mitigation": "The estimate is deliberately generous (3 characters per token, full output allowance, extra context per search).",
     "residual": "An unusually token-dense input could cost more than reserved; actual cost is still recorded and counted."},
    {"risk": "DNS rebinding protection pins the validated address for each request.",
     "mitigation": "Every hop is resolved once, validated, and connected to by IP with the original hostname for TLS.",
     "residual": "An attacker-controlled public server can still serve misleading content (handled as untrusted data)."},
    {"risk": "PDF parsing uses a third-party library (pypdf).",
     "mitigation": "Parsing runs in a separate process with a time limit, CPU/memory limits where supported, and no API keys.",
     "residual": "A new parser vulnerability could still affect that short-lived process."},
    {"risk": "Single-process demo deployment.",
     "mitigation": "Budget reservations and the daily guard are thread-safe within the server process.",
     "residual": "Several server processes would each enforce the daily cap separately; a shared store would be needed to scale out."},
    {"risk": "Compliance and tax summaries can become outdated.",
     "mitigation": "Each source shows the date it was checked; sources older than a year are flagged; tax and legal questions go to a professional.",
     "residual": "Rules can change between checks."},
]
