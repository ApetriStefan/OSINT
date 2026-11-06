"""Agent 4: Executive Political Intelligence Synthesis and Predictive Director."""

from datetime import datetime
import json
import logging
import re
from typing import List, Optional, Union

from src.events import event_bus
from src.llm.client import OllamaClient
from src.models.article import ScrapedArticle
from src.models.intelligence import ExtractedEvent, HistoricalAnomaly, ThreatVector
from src.utils_date import format_romanian_date, get_bucharest_today_str

logger = logging.getLogger(__name__)


def get_romanian_date(dt_or_str: Optional[Union[datetime, str]] = None) -> str:
    """Format datetime or date string into natural Romanian text (e.g. '6 Noiembrie 2026')."""
    return format_romanian_date(dt_or_str)


SYSTEM_PROMPT_AGENT_4 = (
    "You are a Senior Political Intelligence Analyst specialized in Romanian domestic politics and Open Source Intelligence (OSINT). "
    "Synthesize raw daily data into an executive-level political intelligence briefing.\n\n"
    "CORE ANALYTICAL DIRECTIVES:\n"
    "1. SILENCE IS A SIGNAL: If a major political actor is unusually silent about a major crisis involving their rivals, analyze this as strategic silence (e.g., negotiation leverage or backdoor deals), not as insignificance.\n"
    "2. DETECT PARASITIC FRAMING: Do not mistake tactical voting for ideological alliances. If two opposing parties vote together, verify if one party is parazitizing the other's initiative to push their own narrative.\n"
    "3. WEAPONIZE CONTRADICTIONS: Look at historical quotes provided in the anomalies. Highlight when a politician's current defense directly violates their past statements.\n"
    "4. BE UNBIASED AND COLD: Write with absolute objectivity. Avoid emotional language. Speak in terms of leverage, public perception management, risk, and political survival.\n"
    "5. TACTICAL VS. IDEOLOGICAL CONVERGENCE: Do not mistake separate, convergent tactical behaviors for coordinated subterranean alliances. If opposing parties act similarly, frame it as 'convergent strategic interests' rather than a coordinated secret coalition, unless there is concrete supporting evidence. Always treat backdoor deals described by rivals as strategic narratives or weaponized framing, not as objective facts.\n\n"
    "OUTPUT CONSTRAINTS:\n"
    "- Write entirely in ROMANIAN.\n"
    "- Follow exactly the Markdown structure provided below.\n"
    "- Generate exactly 5 predictions with numerical Confidence Scores.\n"
    "- Ground all analysis strictly in the provided facts. When citing sources, use readable publication or actor names in brackets (e.g. [Sursa: Digi24], [MApN / HotNews]). NEVER output database IDs, hashes, or technical keys.\n\n"
    "# 🇷🇴 Sinteza Politică Locală: [DATE]\n\n"
    "## 1. REZUMATUL ZILEI (TL;DR)\n* [Provide a concise, 3-sentence summary of the most critical political developments, highlighting the underlying reality behind surface news.]\n\n"
    "## 2. DINAMICA PUTERII ȘI ALIANȚE SUBTERANE\n* [Analyze power dynamics, strategic silence, backdoor negotiations, or tactical voting behavior identified in the data.]\n\n"
    "## 3. EXPLOATAREA EVENIMENTELOR SOCIALE (Black Swan Tracking)\n* [Explain how social tragedies, economic strains, or infrastructure failures are being weaponized or managed by different actors.]\n\n"
    "## 4. PREDICȚII ȘI ANOMALII PENTRU MÂINE\n"
    "* **Ce urmărim mâine: [Prediction Title 1]**\n  * *Confidence Score:* [X%]\n  * *Justificare:* [Analytical justification linking raw data and vulnerabilities to this outcome]\n"
    "* **Ce urmărim mâine: [Prediction Title 2]**\n  * *Confidence Score:* [X%]\n  * *Justificare:* [Analytical justification]\n"
    "* **Ce urmărim mâine: [Prediction Title 3]**\n  * *Confidence Score:* [X%]\n  * *Justificare:* [Analytical justification]\n"
    "* **Ce urmărim mâine: [Prediction Title 4]**\n  * *Confidence Score:* [X%]\n  * *Justificare:* [Analytical justification]\n"
    "* **Ce urmărim mâine: [Prediction Title 5]**\n  * *Confidence Score:* [X%]\n  * *Justificare:* [Analytical justification]\n\n"
    "**Nivel de Volatilitate:** [Scăzut / Mediu / Ridicat] - [1-sentence explanation of volatility rating]\n\n"
    "## 5. SURSE ȘI METODOLOGIE\n* [List the primary sources and events tracked in this briefing]"
)


class DirectorAgent:
    """Agent 4: Synthesizes multi-agent intelligence outputs into an executive briefing."""

    def __init__(self, llm_client: Optional[OllamaClient] = None) -> None:
        self.llm_client = llm_client or OllamaClient()

    def run(
        self,
        events: List[ExtractedEvent],
        anomalies: List[HistoricalAnomaly],
        threats: List[ThreatVector],
        articles: Optional[List[ScrapedArticle]] = None,
        date_str: Optional[str] = None,
        run_id: str = ""
    ) -> str:
        """Generate the final executive synthesis in Romanian."""
        if not events:
            raise RuntimeError("Cannot synthesize briefing without extracted events.")

        today_ro = get_romanian_date(date_str)
        logger.info("Executing Agent 4 (Executive Intelligence Director) for %s (%s)...", date_str or "today", today_ro)
        event_bus.publish(
            event_type="agent_start",
            text="Director Agent started executive synthesis",
            agent="director",
            run_id=run_id
        )

        def _clean_event(e: ExtractedEvent) -> dict:
            d = e.model_dump(mode="json")
            for k in ("id", "event_hash", "article_id", "extracted_at"):
                d.pop(k, None)
            return d

        def _clean_anomaly(a: HistoricalAnomaly) -> dict:
            d = a.model_dump(mode="json")
            for k in ("id", "anomaly_hash", "detected_at"):
                d.pop(k, None)
            return d

        def _clean_threat(t: ThreatVector) -> dict:
            d = t.model_dump(mode="json")
            for k in ("id", "threat_hash", "detected_at"):
                d.pop(k, None)
            return d

        payload = {
            "current_date": date_str or get_bucharest_today_str(),
            "agent_1_extracted_events": [_clean_event(e) for e in events],
            "agent_2_anomalies": [_clean_anomaly(a) for a in anomalies],
            "agent_3_threat_vectors": [_clean_threat(t) for t in threats],
            "sources_tracked": [
                {"title": a.title, "source": a.source, "link": a.link}
                for a in (articles or [])
            ]
        }

        prompt_sys = SYSTEM_PROMPT_AGENT_4.replace("[DATE]", today_ro)

        try:
            raw_briefing = self.llm_client.generate(
                system_prompt=prompt_sys,
                user_prompt=json.dumps(payload, ensure_ascii=False),
                temperature=0.0,
                top_p=0.1,
                agent_name="director",
                run_id=run_id
            )
            # Post-processing: strip any leaked bracketed hex hashes
            cleaned_briefing = re.sub(
                r"\s*\[[0-9a-fA-F]{16,64}(?:,\s*[0-9a-fA-F]{16,64})*\]",
                "",
                raw_briefing
            )
            # Ensure literal [DATE] or [Data de azi] placeholders are replaced
            cleaned_briefing = re.sub(
                r"\[(?:DATE|Data de azi|Data)\]",
                today_ro,
                cleaned_briefing,
                flags=re.IGNORECASE
            )
            return cleaned_briefing
        finally:
            event_bus.publish(
                event_type="agent_end",
                text="Director Agent completed executive synthesis",
                agent="director",
                run_id=run_id
            )
