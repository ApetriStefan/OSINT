"""Agent 3: Hostile Political Strategist (Red Teamer) detecting tactical threat vectors."""

import json
import logging
from typing import List, Optional

from src.events import event_bus
from src.llm.client import OllamaClient
from src.models.intelligence import ExtractedEvent, HistoricalAnomaly, ThreatVector, ThreatVectorsContainer
from src.storage.db_manager import DBManager

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_AGENT_3 = (
    "Ești un strateg politic ostil (Red Teamer) specializat în scenarii de atac și exploatare a vulnerabilităților politice din România.\n"
    "Vei primi datele structurate JSON ale evenimentelor politice de azi și anomaliile/contradicțiile identificate.\n"
    "Sarcina ta este să identifici 'Vectori de Amenințare' (Threat Vectors). Analizează datele și determină:\n"
    "1. Cine este cel mai vulnerabil politic în acest moment?\n"
    "2. Cum poate o tabără sau un partid advers să exploateze și să instrumentalizeze aceste evenimente mâine?\n"
    "3. Folosește cineva 'Încadrare Narativă Parazitară' (preluarea temei altei formațiuni pentru a-și promova propria agendă)?\n\n"
    "Redactează analiza exclusiv în limba română profesională. Folosește etichete de amenințare în limba română (ex: 'Vulnerabilitate de Securitate Națională', 'Exploatarea Incompetenței Structurale', 'Atac la Legitimitatea Electorală', 'Încadrare Narativă Parazitară', 'Instabilitate Politică și Dezinformare').\n"
    "Generează DOAR JSON valid conform schemei cerute."
)


class RedTeamAgent:
    """Agent 3: Identifies strategic vulnerabilities, asymmetric attacks, and parasitic framing opportunities."""

    def __init__(
        self,
        db_manager: Optional[DBManager] = None,
        llm_client: Optional[OllamaClient] = None
    ) -> None:
        self.db_manager = db_manager or DBManager()
        self.llm_client = llm_client or OllamaClient()

    def run(
        self,
        events: List[ExtractedEvent],
        anomalies: List[HistoricalAnomaly],
        run_id: str = ""
    ) -> List[ThreatVector]:
        """Analyze events and contradictions to detect actionable political threat vectors."""
        if not events:
            logger.info("No events available for Agent 3.")
            return []

        logger.info("Executing Agent 3 (Red Team Strategist)...")
        event_bus.publish(
            event_type="agent_start",
            text="Red Team Agent started threat vector analysis",
            agent="red_team",
            run_id=run_id
        )

        payload = {
            "agent_1_extracted_events": [e.model_dump(mode="json") for e in events],
            "agent_2_anomalies": [a.model_dump(mode="json") for a in anomalies]
        }

        try:
            container: ThreatVectorsContainer = self.llm_client.generate_structured(
                system_prompt=SYSTEM_PROMPT_AGENT_3,
                user_prompt=json.dumps(payload, ensure_ascii=False),
                response_model=ThreatVectorsContainer,
                temperature=0.2,
                top_p=0.5,
                agent_name="red_team",
                run_id=run_id
            )
            threats = container.threat_vectors
            if threats:
                self.db_manager.insert_threat_vectors(threats)
                logger.info("Agent 3 identified %d threat vectors.", len(threats))
            return threats
        except Exception as e:
            logger.error("Agent 3 failed: %s", e)
            return []
        finally:
            event_bus.publish(
                event_type="agent_end",
                text="Red Team Agent completed threat vector analysis",
                agent="red_team",
                run_id=run_id
            )
