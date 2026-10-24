"""Agent 2: Mission Discovery.

Bounded research: one web search (or labeled synthetic fixtures). Every link
is then fetched to verify it, cross-checked with a keyword alignment score,
and summarized by the model, which can refer only to sources the tools
returned. Findings are saved with their verification status and stated
uncertainty, and the board decides which to keep.
"""

from __future__ import annotations

from ..base import BaseAgent
from ..contracts import AgentName, AgentResult, AgentTask, Finding, SourceRecord
from ..outputs import MissionOutput
from ..registry import MISSION_CLASSIFY
from ..runtime import RunContext, dedupe_sources

INSTRUCTIONS = """Classify and summarize each source for the foundation's mission (mental health awareness,
eating disorder research, community building).
- Use only source_id values from "sources". One finding per useful source; skip irrelevant ones.
- alignment: high / medium / low / none. Consider the keyword cross-check but use judgment.
- date_text: only if the source states a date; else null.
- uncertainty: what is unconfirmed (e.g. link not verified, synthetic fixture, dates unclear, eligibility unknown).
- gaps: what the board should research next."""

DEFAULT_TOPIC = "Eating disorder and mental health nonprofits, research initiatives, and awareness events open to partnership"


class MissionDiscoveryAgent(BaseAgent):
    name = AgentName.MISSION_DISCOVERY

    def execute(self, task: AgentTask, ctx: RunContext) -> AgentResult:
        topic = task.inputs.get("topic") or DEFAULT_TOPIC
        found = self.tool(ctx, "search_web", query=topic, purpose="mission")
        if not found.ok:
            return self.result(task, "failed", found.error or "Search failed.", warnings=[found.error or ""])
        hits = found.data or []
        sources: list[SourceRecord] = []
        prompt_sources = []
        for h in hits[:6]:
            check = self.tool(ctx, "fetch_source", url=h["url"], source_id=h["source_id"])
            src = check.sources[0] if check.sources else SourceRecord(id=h["source_id"], title=h["title"], url=h["url"], verification="unverified")
            src.title = src.title if src.verification == "verified" else h["title"]
            src.published = src.published or h.get("published")
            src.publisher = h.get("publisher")
            sources.append(src)
            keyword = self.tool(ctx, "classify_mission_alignment", text=f"{h['title']} {h['snippet']}").data
            prompt_sources.append({"source_id": h["source_id"], "title": h["title"], "snippet": h["snippet"], "url": h["url"],
                                   "published": src.published, "verification": src.verification,
                                   "keyword_alignment": keyword["keyword_label"], "category_hint": h.get("category_hint")})
        if not prompt_sources:
            return self.result(task, "completed", "The search returned no usable sources.", warnings=found.warnings,
                               next_steps=["Try a more specific research question."])

        out = self.think(ctx, MISSION_CLASSIFY, INSTRUCTIONS, {"request": topic, "sources": prompt_sources}, MissionOutput)
        by_id = {s.id: s for s in sources}
        warnings = list(found.warnings)
        saved: list[dict] = []
        findings: list[Finding] = []
        for f in out.findings:
            src = by_id.get(f.source_id)
            if src is None:
                warnings.append(f"Ignored a finding citing an unknown source ({f.source_id}).")
                continue
            uncertainty = f.uncertainty
            if src.verification == "unverified":
                uncertainty = f"Link could not be verified ({src.note or 'not fetched'}). {uncertainty}"
            row = self.tool(ctx, "save_research_finding", agent=self.name.value, category=f.category, title=src.title,
                            summary=f.summary, source_url=src.url, source_title=src.title, verification_status=src.verification,
                            alignment=f.alignment, uncertainty=uncertainty, published=f.date_text or src.published)
            if not row.ok:
                warnings.append(f"Could not save the finding for {src.title}: {row.error}")
                continue
            saved.append({"id": row.data["id"], "title": src.title, "url": src.url, "category": f.category, "alignment": f.alignment,
                          "verification": src.verification, "summary": f.summary, "date": f.date_text or src.published,
                          "uncertainty": uncertainty, "why_relevant": f.why_relevant})
            findings.append(Finding(claim=f"{src.title}: {f.summary}",
                                    kind="verified_fact" if src.verification == "verified" else "estimate",
                                    source_ids=[f.source_id], confidence="high" if f.alignment == "high" else "medium"))
        verified = sum(1 for s in saved if s["verification"] == "verified")
        return self.result(
            task, "completed", out.summary, findings=findings, sources=dedupe_sources(sources), warnings=warnings,
            assumptions=["Synthetic fixtures, not live web research."] if ctx.research_mode == "synthetic" else
                        [f"{verified} of {len(saved)} links verified by fetching the page just now."],
            next_steps=out.gaps + ["Save the opportunities worth pursuing in Mission Discovery."],
            data={"findings": saved, "topic": topic},
        )
