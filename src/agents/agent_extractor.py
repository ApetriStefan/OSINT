"""Agent 1: Structured Information and Entity Extractor with canonical resolution."""

import logging
from typing import List, Optional

from src.classification.entity_resolver import EntityResolver
from src.events import event_bus
from src.llm.client import OllamaClient
from src.models.intelligence import ExtractedEvent, ExtractedEventsContainer
from src.storage.db_manager import DBManager

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_AGENT_1 = (
    "You are an elite OSINT Information Extractor specialized in the Romanian geopolitical, economic, and social landscape. "
    "Your task is to extract key events, declarations, and actions that have the potential to influence political dynamics, "
    "national security, economic stability, public policy, or public sentiment in Romania.\n\n"
    "You must extract:\n"
    "1. Core political actions, claims, and declarations by politicians or parties.\n"
    "2. Major economic, financial, and regulatory events.\n"
    "3. National security, defense, and border developments.\n"
    "4. Significant social, humanitarian, or systemic crises.\n\n"
    "RULES:\n"
    "1. Do not translate the quotes. The 'verbatim_evidence' MUST be an exact, copy-pasted substring from the Romanian text.\n"
    "2. All other fields (topic, action, actor) must be written in English.\n"
    "3. If provided in the article header (e.g. '(Sursa: Digi24 - 2026-11-06)'), record the publication name in the 'source' field.\n"
    "4. If no event is present, output an empty array for extracted_events.\n"
    "5. Output ONLY valid JSON matching the schema."
)


class EntityExtractorAgent:
    """Agent 1: Extracts structured political actions and verbatim evidence with canonical entity mapping."""

    def __init__(
        self,
        db_manager: Optional[DBManager] = None,
        llm_client: Optional[OllamaClient] = None
    ) -> None:
        self.db_manager = db_manager or DBManager()
        self.llm_client = llm_client or OllamaClient()

    def run(self, dossier_text: str, run_id: str = "") -> List[ExtractedEvent]:
        """Extract events from the dossier, resolve actors canonically, and persist to database."""
        if not dossier_text or not dossier_text.strip():
            logger.warning("Empty dossier provided to Agent 1.")
            return []

        logger.info("Executing Agent 1 (Entity Extractor)...")
        event_bus.publish(
            event_type="agent_start",
            text="Entity Extractor Agent started",
            agent="extractor",
            run_id=run_id
        )

        try:
            container: ExtractedEventsContainer = self.llm_client.generate_structured(
                system_prompt=SYSTEM_PROMPT_AGENT_1,
                user_prompt=f"DOSSIER TEXT:\n{dossier_text}",
                response_model=ExtractedEventsContainer,
                temperature=0.0,
                agent_name="extractor",
                run_id=run_id
            )

            resolved_events: List[ExtractedEvent] = []
            for event in container.extracted_events:
                # Canonical actor resolution
                canonical_info = EntityResolver.resolve_actor(event.actor)
                event.canonical_actor = canonical_info.canonical_name
                # Re-trigger hash calculation to account for canonical actor
                event.compute_hash()
                resolved_events.append(event)

            if resolved_events:
                inserted_count = self.db_manager.insert_extracted_events(resolved_events)
                logger.info("Agent 1 extracted %d events (%d new saved to database).", len(resolved_events), inserted_count)
            else:
                logger.info("Agent 1 extracted 0 events.")

            return resolved_events
        finally:
            event_bus.publish(
                event_type="agent_end",
                text="Entity Extractor Agent completed",
                agent="extractor",
                run_id=run_id
            )
