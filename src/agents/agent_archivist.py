"""Agent 2: Political Archivist and Contradiction Detector using Vector Search with SQLite fallback."""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from src.events import event_bus
from src.llm.client import OllamaClient
from src.models.intelligence import ExtractedEvent, HistoricalAnomaly, HistoricalAnomaliesContainer
from src.storage.db_manager import DBManager
from src.storage.vector_store import VectorStore

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_AGENT_2 = (
    "You are an Automated Political Archivist. You will receive:\n"
    "1. 'TODAY_EVENT': A JSON object of a claim or action observed today.\n"
    "2. 'HISTORICAL_CONTEXT': A JSON array of recorded past statements by the same actor.\n"
    "Your job is to detect genuine contradictions, policy reversals, or strategic flip-flops. Write your analysis in English, but keep quotes in Romanian.\n\n"
    "CRITICAL CONTRADICTION SCORING RULES:\n"
    "- 0.0 = COMPLETELY CONSISTENT: Today's statement agrees with, repeats, or maintains the same status as the historical statement. THERE IS NO CONTRADICTION.\n"
    "- 0.1 to 0.4 = MINOR SHIFT: Nuanced evolution, minor timeline adjustment.\n"
    "- 0.5 to 0.8 = SIGNIFICANT CONTRADICTION: Visible policy reversal, broken promise, or conflicting factual assertion.\n"
    "- 0.9 to 1.0 = BLATANT FLIP-FLOP: A direct 180-degree contradiction where the actor completely denies, reverses, or opposes their past recorded stance.\n\n"
    "MANDATORY DECISION LOGIC:\n"
    "1. If today's statement is CONSISTENT with, REPEATS, or CONFIRMS the historical context, contradiction_score MUST BE 0.0 and you MUST return an empty array for anomalies: {\"anomalies\": []}.\n"
    "2. DO NOT flag an event as an anomaly if your own analyst note states that it is consistent or not a contradiction!\n"
    "3. Only output an anomaly if there is a genuine, visible contradiction with contradiction_score >= 0.5.\n"
    "4. Output ONLY valid JSON matching the schema."
)


class ArchivistAgent:
    """Agent 2: Checks today's events against historical statements using ChromaDB and SQLite fallback."""

    def __init__(
        self,
        db_manager: Optional[DBManager] = None,
        vector_store: Optional[VectorStore] = None,
        llm_client: Optional[OllamaClient] = None
    ) -> None:
        self.db_manager = db_manager or DBManager()
        self.vector_store = vector_store or VectorStore()
        self.llm_client = llm_client or OllamaClient()

    def get_historical_context(self, event: ExtractedEvent) -> List[Dict[str, Any]]:
        """Retrieve historical statements for an actor, attempting vector search first with SQLite fallback."""
        actor_name = event.canonical_actor or event.actor
        current_hash = event.event_hash
        current_evidence_clean = event.verbatim_evidence.strip().lower()

        # 1. Attempt semantic search in VectorStore
        try:
            vector_results = self.vector_store.search_events(
                query=f"{actor_name}: {event.action}. {event.verbatim_evidence}",
                n_results=6,
                filter_actor=actor_name
            )
            if vector_results:
                history = []
                for item in vector_results:
                    # Filter out self-match if event is already in vector store
                    if item.get("id") == current_hash:
                        continue
                    meta = item.get("metadata", {})
                    past_stmt = meta.get("verbatim_evidence") or item.get("document", "")
                    if past_stmt.strip().lower() == current_evidence_clean:
                        continue

                    history.append({
                        "date": meta.get("extracted_at", "historical"),
                        "past_statement": past_stmt,
                        "action": meta.get("action", "")
                    })
                if history:
                    logger.info("Found %d historical items via ChromaDB for %s", len(history), actor_name)
                    return history
        except Exception as e:
            logger.warning("Vector search fallback triggered for %s: %s", actor_name, e)

        # 2. Fallback to SQLite historical records
        sql_history = self.db_manager.get_actor_history(actor=actor_name, limit=5)
        logger.info("Found %d historical items via SQLite for %s", len(sql_history), actor_name)
        return sql_history

    def run(
        self,
        events: List[ExtractedEvent],
        run_id: str = ""
    ) -> List[HistoricalAnomaly]:
        """Detect anomalies across all extracted events for today."""
        if not events:
            logger.info("No events provided to Agent 2.")
            return []

        logger.info("Executing Agent 2 (Archivist & Contradiction Detector)...")
        event_bus.publish(
            event_type="agent_start",
            text="Archivist Agent started contradiction analysis",
            agent="archivist",
            run_id=run_id
        )

        all_anomalies: List[HistoricalAnomaly] = []

        # Phase A (Vector Memory): Pre-fetch historical context FIRST (so today's events are not in history)
        event_histories: Dict[int, List[Dict[str, Any]]] = {}
        for idx, event in enumerate(events):
            if event_bus.is_cancelled():
                logger.info("Cancellation requested during Agent 2 vector pre-fetch.")
                break
            event_histories[idx] = self.get_historical_context(event)

        # Batch index today's events into ChromaDB AFTER pre-fetching
        try:
            self.vector_store.add_events(events)
        except Exception as e:
            logger.warning("Could not index today's events into ChromaDB: %s", e)

        def _is_spurious_anomaly(a: HistoricalAnomaly, current_evt: ExtractedEvent) -> bool:
            # Check 1: Past and current statements are identical or mutually contained
            p_clean = re.sub(r"\W+", " ", a.past_statement.strip().lower())
            c_clean = re.sub(r"\W+", " ", a.current_statement.strip().lower())
            e_clean = re.sub(r"\W+", " ", current_evt.verbatim_evidence.strip().lower())
            if p_clean and (p_clean == c_clean or p_clean == e_clean or c_clean in p_clean or p_clean in c_clean):
                logger.info("Discarding spurious anomaly for %s: past and current statement repeat each other.", a.target)
                return True
            # Check 2: Analyst note explicitly declares consistency or lack of contradiction
            note_lower = a.analyst_note.lower()
            spurious_phrases = [
                "rather than a change or contradiction",
                "not a contradiction",
                "no contradiction",
                "consistent reporting",
                "indicates a consistent",
                "consistent with",
                "exactly repeats",
                "merely repeats",
                "no shift in position"
            ]
            if any(phrase in note_lower for phrase in spurious_phrases):
                logger.info("Discarding spurious anomaly for %s: analyst note states consistency: %s", a.target, a.analyst_note)
                return True
            return False

        # Phase B (Inference): Run LLM inference over events using pre-fetched context with gemma-4-e4b
        try:
            for idx, event in enumerate(events):
                if event_bus.is_cancelled():
                    logger.info("Cancellation requested during Agent 2 execution.")
                    break

                history = event_histories.get(idx, [])
                if not history:
                    continue

                user_payload = {
                    "TODAY_EVENT": {
                        "actor": event.canonical_actor or event.actor,
                        "action": event.action,
                        "verbatim_evidence": event.verbatim_evidence,
                        "topic": event.topic
                    },
                    "HISTORICAL_CONTEXT": history
                }

                try:
                    container: HistoricalAnomaliesContainer = self.llm_client.generate_structured(
                        system_prompt=SYSTEM_PROMPT_AGENT_2,
                        user_prompt=json.dumps(user_payload, ensure_ascii=False),
                        response_model=HistoricalAnomaliesContainer,
                        temperature=0.0,
                        agent_name="archivist",
                        run_id=run_id
                    )
                    # Keep only significant contradictions, filtering out spurious/consistent matches
                    significant_anomalies = [
                        a for a in container.anomalies
                        if a.contradiction_score >= 0.5 and not _is_spurious_anomaly(a, event)
                    ]
                    all_anomalies.extend(significant_anomalies)
                except Exception as e:
                    logger.warning("Agent 2 failed for actor %s: %s", event.actor, e)

            if all_anomalies:
                self.db_manager.insert_historical_anomalies(all_anomalies)
                logger.info("Agent 2 identified %d historical anomalies/contradictions.", len(all_anomalies))
            else:
                logger.info("Agent 2 identified 0 significant contradictions.")

            return all_anomalies

            return all_anomalies
        finally:
            event_bus.publish(
                event_type="agent_end",
                text="Archivist Agent completed contradiction analysis",
                agent="archivist",
                run_id=run_id
            )
