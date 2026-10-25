# Known unresolved vulnerabilities

Also shown in Analytics & Safety (`safety/risks.py`).

## Pattern-based injection screening can miss disguised instructions.

- **Mitigation:** Screening is only the first layer: external text reaches models only as labeled data, agents hold no secrets, outputs are structured and validated, and no tool can act externally. A disguised injection is tested.
- **Still possible:** A model could still be misled into a poor recommendation (wrong venue, overstated fit); verification flags invented figures, links, and availability claims, but judgment errors remain possible.

## Hosted web search runs inside the model provider.

- **Mitigation:** Its results are re-checked by fetching each page ourselves; figures count only if they appear on the page.
- **Still possible:** We cannot inspect or screen the search results the model saw while choosing links.

## Worst-case cost estimates rely on a characters-per-token approximation.

- **Mitigation:** The estimate is deliberately generous (3 characters per token, full output allowance, extra context per search).
- **Still possible:** An unusually token-dense input could cost more than reserved; actual cost is still recorded and counted.

## DNS rebinding protection pins the validated address for each request.

- **Mitigation:** Every hop is resolved once, validated, and connected to by IP with the original hostname for TLS.
- **Still possible:** An attacker-controlled public server can still serve misleading content (handled as untrusted data).

## PDF parsing uses a third-party library (pypdf).

- **Mitigation:** Parsing runs in a separate process with a time limit, CPU/memory limits where supported, and no API keys.
- **Still possible:** A new parser vulnerability could still affect that short-lived process.

## Single-process demo deployment.

- **Mitigation:** Budget reservations and the daily guard are thread-safe within the server process.
- **Still possible:** Several server processes would each enforce the daily cap separately; a shared store would be needed to scale out.

## Compliance and tax summaries can become outdated.

- **Mitigation:** Each source shows the date it was checked; sources older than a year are flagged; tax and legal questions go to a professional.
- **Still possible:** Rules can change between checks.
