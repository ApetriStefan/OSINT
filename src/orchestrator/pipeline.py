"""Master pipeline orchestrator managing stages, checkpoints, run tracking, and safe recovery."""

from datetime import datetime
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from src.agents.agent_archivist import ArchivistAgent
from src.agents.agent_copyeditor import CopyeditorAgent
from src.agents.agent_director import DirectorAgent
from src.agents.agent_extractor import EntityExtractorAgent
from src.agents.agent_red_team import RedTeamAgent
from src.agents.selector import NewsSelector
from src.config import get_settings
from src.events import event_bus
from src.llm.client import OllamaClient
from src.models.article import RawArticle, ScrapedArticle
from src.models.intelligence import ExtractedEvent, HistoricalAnomaly, ThreatVector
from src.scrapers.rss_scraper import RSSScraper
from src.storage.db_manager import DBManager
from src.storage.vector_store import VectorStore
from src.utils_date import validate_target_date, get_bucharest_today_str

logger = logging.getLogger(__name__)


class MasterPipeline:
    """Orchestrates end-to-end OSINT intelligence workflow with granular stage control."""

    STAGE_INGEST = "ingest"
    STAGE_SELECT = "select"
    STAGE_AGENTS = "agents"
    STAGE_SYNTHESIZE = "synthesize"
    STAGE_ALL = "all"

    def __init__(
        self,
        db_manager: Optional[DBManager] = None,
        vector_store: Optional[VectorStore] = None,
        llm_client: Optional[OllamaClient] = None
    ) -> None:
        self.db_manager = db_manager or DBManager()
        self.vector_store = vector_store or VectorStore()
        self.llm_client = llm_client or OllamaClient()

        self.scraper = RSSScraper()
        self.selector = NewsSelector(db_manager=self.db_manager, llm_client=self.llm_client)
        self.agent_extractor = EntityExtractorAgent(db_manager=self.db_manager, llm_client=self.llm_client)
        self.agent_archivist = ArchivistAgent(
            db_manager=self.db_manager,
            vector_store=self.vector_store,
            llm_client=self.llm_client
        )
        self.agent_red_team = RedTeamAgent(db_manager=self.db_manager, llm_client=self.llm_client)
        self.agent_director = DirectorAgent(llm_client=self.llm_client)
        self.agent_copyeditor = CopyeditorAgent(llm_client=self.llm_client)

    def generate_run_id(self) -> str:
        """Create a unique execution run ID timestamped for auditing."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_id = uuid.uuid4().hex[:6]
        return f"run_{ts}_{short_id}"

    # ==================== Individual Stages ====================

    def stage_ingest(self, run_id: str) -> int:
        """Stage 1: Fetch all configured RSS feeds and persist new raw articles."""
        if event_bus.is_cancelled():
            logger.info("Pipeline cancelled before INGEST.")
            return 0

        self.db_manager.record_pipeline_execution(run_id, self.STAGE_INGEST, "STARTED")
        event_bus.publish(
            event_type="stage",
            text="Stage INGEST started (Scanning RSS feeds)",
            agent="pipeline",
            run_id=run_id,
            data={"stage": self.STAGE_INGEST, "status": "STARTED", "progress_pct": 10}
        )
        logger.info("[STAGE: INGEST] Scanning RSS feeds...")
        try:
            articles = self.scraper.fetch_all()
            new_count = self.db_manager.insert_raw_articles(articles)
            details = f"Scraped {len(articles)} total, {new_count} newly added."
            self.db_manager.record_pipeline_execution(run_id, self.STAGE_INGEST, "COMPLETED", details)
            event_bus.publish(
                event_type="stage",
                text=f"Stage INGEST completed: {details}",
                agent="pipeline",
                run_id=run_id,
                data={"stage": self.STAGE_INGEST, "status": "COMPLETED", "progress_pct": 25, "new_articles": new_count}
            )
            logger.info("[STAGE: INGEST] %s", details)
            return new_count
        except Exception as e:
            self.db_manager.record_pipeline_execution(run_id, self.STAGE_INGEST, "FAILED", str(e))
            event_bus.publish(
                event_type="stage",
                text=f"Stage INGEST failed: {e}",
                agent="pipeline",
                run_id=run_id,
                data={"stage": self.STAGE_INGEST, "status": "FAILED", "error": str(e)}
            )
            raise

    def stage_select(
        self,
        run_id: str,
        target_date: Optional[str] = None,
        dossier_path: str = "dossier_for_agent_1.txt"
    ) -> str:
        """Stage 2: Select top strategic articles and compile consolidated press dossier."""
        if event_bus.is_cancelled():
            logger.info("Pipeline cancelled before SELECT.")
            return ""

        canonical_date = validate_target_date(target_date)
        self.db_manager.record_pipeline_execution(run_id, self.STAGE_SELECT, "STARTED")
        event_bus.publish(
            event_type="stage",
            text=f"Stage SELECT started for date {canonical_date}",
            agent="pipeline",
            run_id=run_id,
            data={"stage": self.STAGE_SELECT, "status": "STARTED", "progress_pct": 30, "date": canonical_date}
        )
        logger.info("[STAGE: SELECT] Filtering news and generating dossier for %s...", canonical_date)
        try:
            dossier_text, scraped_articles = self.selector.build_dossier(
                target_date=canonical_date,
                output_path=dossier_path,
                run_id=run_id
            )
            self._last_selected_articles = scraped_articles
            details = f"Compiled dossier with {len(scraped_articles)} scraped articles into {dossier_path}."
            self.db_manager.record_pipeline_execution(run_id, self.STAGE_SELECT, "COMPLETED", details)
            event_bus.publish(
                event_type="stage",
                text=f"Stage SELECT completed ({len(scraped_articles)} articles scraped)",
                agent="pipeline",
                run_id=run_id,
                data={"stage": self.STAGE_SELECT, "status": "COMPLETED", "progress_pct": 50, "articles_count": len(scraped_articles)}
            )
            logger.info("[STAGE: SELECT] %s", details)
            return dossier_text
        except Exception as e:
            self.db_manager.record_pipeline_execution(run_id, self.STAGE_SELECT, "FAILED", str(e))
            event_bus.publish(
                event_type="stage",
                text=f"Stage SELECT failed: {e}",
                agent="pipeline",
                run_id=run_id,
                data={"stage": self.STAGE_SELECT, "status": "FAILED", "error": str(e)}
            )
            raise

    def stage_agents(
        self,
        run_id: str,
        dossier_text: Optional[str] = None,
        dossier_path: str = "dossier_for_agent_1.txt"
    ) -> Dict[str, Any]:
        """Stage 3: Run Agent 1 (Extractor), Agent 2 (Archivist), and Agent 3 (Red Team)."""
        if event_bus.is_cancelled():
            logger.info("Pipeline cancelled before AGENTS.")
            return {"events": [], "anomalies": [], "threats": []}

        self.db_manager.record_pipeline_execution(run_id, self.STAGE_AGENTS, "STARTED")
        event_bus.publish(
            event_type="stage",
            text="Stage AGENTS started (Extractor, Archivist, Red Team)",
            agent="pipeline",
            run_id=run_id,
            data={"stage": self.STAGE_AGENTS, "status": "STARTED", "progress_pct": 55}
        )
        logger.info("[STAGE: AGENTS] Running Agent Pipeline (1, 2, 3)...")

        # Fallback to loading existing dossier file if text not passed in memory
        if not dossier_text:
            if os.path.exists(dossier_path):
                with open(dossier_path, "r", encoding="utf-8") as f:
                    dossier_text = f.read()
            else:
                raise FileNotFoundError(f"Dossier file not found: {dossier_path}")

        try:
            # 1. Agent 1: Structured Entity Extractor
            events = self.agent_extractor.run(dossier_text, run_id=run_id)
            event_bus.publish(
                event_type="stage",
                text=f"Agent 1 finished ({len(events)} events extracted)",
                agent="pipeline",
                run_id=run_id,
                data={"stage": self.STAGE_AGENTS, "progress_pct": 65, "events_count": len(events)}
            )

            if event_bus.is_cancelled():
                raise InterruptedError("Pipeline execution cancelled after Agent 1.")

            # 2. Agent 2: Archivist & Anomaly Detector
            anomalies = self.agent_archivist.run(events, run_id=run_id)
            event_bus.publish(
                event_type="stage",
                text=f"Agent 2 finished ({len(anomalies)} anomalies identified)",
                agent="pipeline",
                run_id=run_id,
                data={"stage": self.STAGE_AGENTS, "progress_pct": 70, "anomalies_count": len(anomalies)}
            )

            if event_bus.is_cancelled():
                raise InterruptedError("Pipeline execution cancelled after Agent 2.")

            # 3. Agent 3: Red Team Hostile Strategist
            threats = self.agent_red_team.run(events, anomalies, run_id=run_id)
            event_bus.publish(
                event_type="stage",
                text=f"Agent 3 finished ({len(threats)} threat vectors detected)",
                agent="pipeline",
                run_id=run_id,
                data={"stage": self.STAGE_AGENTS, "progress_pct": 75, "threats_count": len(threats)}
            )

            details = f"Extracted {len(events)} events, {len(anomalies)} anomalies, {len(threats)} threats."
            self.db_manager.record_pipeline_execution(run_id, self.STAGE_AGENTS, "COMPLETED", details)
            event_bus.publish(
                event_type="stage",
                text=f"Stage AGENTS completed: {details}",
                agent="pipeline",
                run_id=run_id,
                data={"stage": self.STAGE_AGENTS, "status": "COMPLETED", "progress_pct": 75}
            )
            logger.info("[STAGE: AGENTS] %s", details)

            return {
                "events": events,
                "anomalies": anomalies,
                "threats": threats
            }
        except Exception as e:
            self.db_manager.record_pipeline_execution(run_id, self.STAGE_AGENTS, "FAILED", str(e))
            event_bus.publish(
                event_type="stage",
                text=f"Stage AGENTS failed: {e}",
                agent="pipeline",
                run_id=run_id,
                data={"stage": self.STAGE_AGENTS, "status": "FAILED", "error": str(e)}
            )
            raise

    def stage_synthesize(
        self,
        run_id: str,
        events: List[ExtractedEvent],
        anomalies: List[HistoricalAnomaly],
        threats: List[ThreatVector],
        articles: Optional[List[ScrapedArticle]] = None,
        target_date: Optional[str] = None
    ) -> str:
        """Stage 4: Run Agent 4 (Director synthesis) and Agent 5 (Romanian copyeditor)."""
        if event_bus.is_cancelled():
            logger.info("Pipeline cancelled before SYNTHESIZE.")
            return ""

        canonical_date = validate_target_date(target_date)
        if articles is None:
            articles = getattr(self, "_last_selected_articles", None)
        if articles is None:
            try:
                db_arts = self.db_manager.get_articles_by_date(canonical_date)
                articles = [
                    ScrapedArticle(
                        title=a["title"],
                        link=a["link"],
                        source=a["source"],
                        published_date=a.get("published_date") or canonical_date,
                        scraped_at=a.get("scraped_at"),
                        content=a.get("content")
                    )
                    for a in db_arts
                ]
            except Exception as e:
                logger.debug("Could not fallback to database articles for synthesis: %s", e)

        self.db_manager.record_pipeline_execution(run_id, self.STAGE_SYNTHESIZE, "STARTED")
        event_bus.publish(
            event_type="stage",
            text=f"Stage SYNTHESIZE started for date {canonical_date}",
            agent="pipeline",
            run_id=run_id,
            data={"stage": self.STAGE_SYNTHESIZE, "status": "STARTED", "progress_pct": 80}
        )
        logger.info("[STAGE: SYNTHESIZE] Generating and proofreading executive briefing...")
        try:
            # Agent 4: Executive Synthesis
            raw_briefing = self.agent_director.run(
                events=events,
                anomalies=anomalies,
                threats=threats,
                articles=articles,
                date_str=canonical_date,
                run_id=run_id
            )
            event_bus.publish(
                event_type="stage",
                text="Agent 4 (Director) finished executive synthesis",
                agent="pipeline",
                run_id=run_id,
                data={"stage": self.STAGE_SYNTHESIZE, "progress_pct": 90}
            )

            if event_bus.is_cancelled():
                raise InterruptedError("Pipeline execution cancelled after Agent 4.")

            # Agent 5: Proofreading & Diacritics into reports/
            final_briefing = self.agent_copyeditor.run(
                raw_briefing=raw_briefing,
                target_date=canonical_date,
                save_file=True,
                run_id=run_id,
                reports_dir="reports"
            )

            details = f"Executive briefing synthesized and written to reports/Sinteza_Politica_{canonical_date}.md"
            self.db_manager.record_pipeline_execution(run_id, self.STAGE_SYNTHESIZE, "COMPLETED", details)
            event_bus.publish(
                event_type="stage",
                text="Stage SYNTHESIZE completed successfully",
                agent="pipeline",
                run_id=run_id,
                data={"stage": self.STAGE_SYNTHESIZE, "status": "COMPLETED", "progress_pct": 100}
            )
            logger.info("[STAGE: SYNTHESIZE] %s", details)
            return final_briefing
        except Exception as e:
            self.db_manager.record_pipeline_execution(run_id, self.STAGE_SYNTHESIZE, "FAILED", str(e))
            event_bus.publish(
                event_type="stage",
                text=f"Stage SYNTHESIZE failed: {e}",
                agent="pipeline",
                run_id=run_id,
                data={"stage": self.STAGE_SYNTHESIZE, "status": "FAILED", "error": str(e)}
            )
            raise

    # ==================== End-to-End Runner ====================

    def run(
        self,
        stage: str = STAGE_ALL,
        target_date: Optional[str] = None,
        dossier_path: str = "dossier_for_agent_1.txt",
        run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute specified stage or complete workflow."""
        canonical_date = validate_target_date(target_date)
        actual_run_id = run_id or self.generate_run_id()
        event_bus.reset_cancellation(run_id=actual_run_id)

        start_time = time.time()
        logger.info("Initializing OSINT Pipeline run: %s (stage: %s, date: %s)", actual_run_id, stage, canonical_date)

        # Initialize SQLite schema and vector store
        self.db_manager.init_db()

        results: Dict[str, Any] = {"run_id": actual_run_id, "stage": stage, "target_date": canonical_date}

        try:
            if stage == self.STAGE_INGEST:
                new_articles = self.stage_ingest(actual_run_id)
                results["new_articles"] = new_articles

            elif stage == self.STAGE_SELECT:
                dossier_text = self.stage_select(actual_run_id, target_date=canonical_date, dossier_path=dossier_path)
                results["dossier_length"] = len(dossier_text)

            elif stage == self.STAGE_AGENTS:
                agent_data = self.stage_agents(actual_run_id, dossier_path=dossier_path)
                results["agent_data"] = agent_data

            elif stage == self.STAGE_SYNTHESIZE:
                agent_data = self.stage_agents(actual_run_id, dossier_path=dossier_path)
                briefing = self.stage_synthesize(
                    run_id=actual_run_id,
                    events=agent_data["events"],
                    anomalies=agent_data["anomalies"],
                    threats=agent_data["threats"],
                    target_date=canonical_date
                )
                results["briefing"] = briefing

            elif stage == self.STAGE_ALL:
                # 1. Ingest
                self.stage_ingest(actual_run_id)
                if event_bus.is_cancelled():
                    raise InterruptedError("Pipeline execution cancelled.")

                # 2. Select
                dossier_text = self.stage_select(actual_run_id, target_date=canonical_date, dossier_path=dossier_path)
                if event_bus.is_cancelled():
                    raise InterruptedError("Pipeline execution cancelled.")

                # 3. Agents (1, 2, 3)
                agent_data = self.stage_agents(actual_run_id, dossier_text=dossier_text)
                if event_bus.is_cancelled():
                    raise InterruptedError("Pipeline execution cancelled.")

                # 4. Synthesize (4, 5)
                briefing = self.stage_synthesize(
                    run_id=actual_run_id,
                    events=agent_data["events"],
                    anomalies=agent_data["anomalies"],
                    threats=agent_data["threats"],
                    articles=getattr(self, "_last_selected_articles", None),
                    target_date=canonical_date
                )
                results["briefing"] = briefing

            else:
                raise ValueError(f"Unknown pipeline stage: {stage}. Expected one of: all, ingest, select, agents, synthesize")

            results["status"] = "completed"
        except InterruptedError as ie:
            logger.info("Pipeline run %s stopped: %s", actual_run_id, ie)
            results["status"] = "cancelled"
            self.db_manager.record_pipeline_execution(actual_run_id, stage, "CANCELLED", str(ie))
        except Exception as e:
            results["status"] = "failed"
            results["error"] = str(e)
            raise

        elapsed = round(time.time() - start_time, 2)
        results["duration_seconds"] = elapsed
        logger.info("Pipeline run %s finished in %s seconds (status: %s).", actual_run_id, elapsed, results.get("status"))
        return results
