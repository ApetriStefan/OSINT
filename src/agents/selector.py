"""Selector agent and press summary dossier generator."""

import concurrent.futures
import json
import logging
import os
from datetime import datetime
from typing import List, Optional, Tuple

import requests

from src.classification.taxonomy import IntelligenceTaxonomy
from src.config import get_settings
from src.events import event_bus
from src.llm.client import OllamaClient
from src.models.article import RawArticle, ScrapedArticle, SelectedArticle
from src.scrapers.text_extractor import scrape_full_text
from src.storage.db_manager import DBManager
from src.utils_date import get_bucharest_today_str, validate_target_date

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_SELECTOR = (
    "You are a Senior Intelligence Director. Analyze the following list of raw daily news articles from Romania. "
    "Select exactly 10 articles that represent the highest strategic importance: DOMESTIC POLITICS, MACROECONOMY, "
    "NATIONAL SECURITY, or SEVERE SYSTEMIC CRISES, AS WELL AS 1 OR 2 BIG NEWS FROM OTHER SUBJECTS THAT ARE OF NATIONAL IMPORTANCE.\n\n"
    "CRITICAL RULES:\n"
    "1. You MUST completely IGNORE and FILTER OUT any articles about: Reality TV shows, showbiz, weather forecasts, "
    "sports, minor accidents, or generic international news that doesn't involve Romania.\n"
    "2. Prioritize articles marked with [STRATEGIC SIGNAL] as they contain highly relevant domestic intelligence elements.\n"
    "Output your selection STRICTLY as a JSON array containing objects with keys: 'title', 'link', 'source'."
)

SYSTEM_PROMPT_DOSSIER = (
    "You are a Master OSINT Journalist and Analyst. Read the full scraped text of the selected news articles "
    "and generate a comprehensive, highly detailed news summary dossier in Romanian.\n\n"
    "You MUST strictly follow this exact plain-text format for each article, separating them with double newlines:\n\n"
    "ȘTIREA [Number]: [CLEAN TITLE HERE - DO NOT BOLD, DO NOT USE # OR ANY MARKDOWN AT ALL]\n"
    "[Write a comprehensive, deep, and highly informative narrative summary in Romanian. This summary must "
    "preserve the political context, key figures, critical facts, and include direct verbatim Romanian quotes from "
    "the provided text. Keep it strictly professional, objective, and analytical. Write at least 2-3 detailed paragraphs for each story to ensure deep coverage.]\n"
    "(Sursa: [Source Name] - [Current Date])\n\n"
    "CRITICAL FORMAT RULES:\n"
    "1. Do not use any markdown headers (such as #, ##, ###) or bold any words inside the title line or text.\n"
    "2. Do not write any conversational intros or outros. Start directly with 'ȘTIREA 1:'.\n"
    "3. Keep Romanian quotes completely verbatim."
)


class NewsSelector:
    """Filters, scores, selects strategic articles, and compiles the consolidated press dossier."""

    def __init__(
        self,
        db_manager: Optional[DBManager] = None,
        llm_client: Optional[OllamaClient] = None
    ) -> None:
        self.db_manager = db_manager or DBManager()
        self.llm_client = llm_client or OllamaClient()

    def prepare_candidates(self, target_date: Optional[str] = None) -> List[dict]:
        """Fetch articles for the target date, filter noise, and score using taxonomy."""
        date_str = validate_target_date(target_date)
        articles = self.db_manager.get_raw_articles_for_date(date_str)
        if not articles:
            # Fallback to recent articles if today's date has 0
            articles = self.db_manager.get_recent_articles(days=2)

        candidates = []
        for art in articles:
            # Noise filter
            if IntelligenceTaxonomy.is_noise(art.title, art.summary or ""):
                continue

            score, pillar, _ = IntelligenceTaxonomy.score_article(
                title=art.title,
                summary=art.summary or ""
            )
            is_strat = score > 2.0

            candidates.append({
                "title": f"{'[STRATEGIC SIGNAL] ' if is_strat else ''}{art.title}",
                "clean_title": art.title,
                "source": art.source_name,
                "summary": (art.summary[:150] + "...") if art.summary else "",
                "link": art.link,
                "is_strategic": is_strat,
                "score": score,
                "pillar": pillar
            })

        # Sort highest strategic priority first
        candidates.sort(key=lambda x: (x["is_strategic"], x["score"]), reverse=True)
        return candidates

    def select_top_articles(
        self,
        candidates: List[dict],
        max_count: int = 10,
        run_id: str = ""
    ) -> List[dict]:
        """Use LLM to select top articles from candidates with heuristic fallback."""
        if not candidates:
            return []

        # Send candidates to LLM
        prompt_input = [
            {"title": c["title"], "source": c["source"], "summary": c["summary"], "link": c["link"]}
            for c in candidates[:40]  # Cap input to top 40 candidates
        ]

        try:
            raw_response = self.llm_client.generate(
                system_prompt=SYSTEM_PROMPT_SELECTOR,
                user_prompt=f"Identify top strategic news: {json.dumps(prompt_input, ensure_ascii=False)}",
                json_schema="json",
                temperature=0.0,
                agent_name="selector",
                run_id=run_id
            )
            parsed = json.loads(raw_response)
            if isinstance(parsed, dict) and "selected_articles" in parsed:
                selected = parsed["selected_articles"]
            elif isinstance(parsed, list):
                selected = parsed
            else:
                selected = list(parsed.values())[0] if parsed else []

            if isinstance(selected, list) and len(selected) > 0:
                return selected[:max_count]
        except Exception as e:
            logger.warning("LLM selection failed (%s). Falling back to taxonomy rank.", e)

        # Fallback to top scored candidates
        return [
            {"title": c["clean_title"], "source": c["source"], "link": c["link"]}
            for c in candidates[:max_count]
        ]

    def build_dossier(
        self,
        target_date: Optional[str] = None,
        output_path: str = "dossier_for_agent_1.txt",
        run_id: str = ""
    ) -> Tuple[str, List[ScrapedArticle]]:
        """Run full selection and compilation pipeline to generate press dossier."""
        logger.info("Preparing article candidates...")
        event_bus.publish(
            event_type="agent_start",
            text="Selector Agent started preparing article candidates",
            agent="selector",
            run_id=run_id
        )

        try:
            candidates = self.prepare_candidates(target_date)
            if not candidates:
                raise RuntimeError("No raw articles found to process for dossier.")

            logger.info("Selecting top %d strategic articles...", get_settings().max_selected_articles)
            selected_meta = self.select_top_articles(
                candidates,
                max_count=get_settings().max_selected_articles,
                run_id=run_id
            )

            session = requests.Session()
            session.headers.update({"User-Agent": get_settings().user_agent})

            def _scrape_worker(idx_item: Tuple[int, dict]) -> Optional[Tuple[int, ScrapedArticle]]:
                if event_bus.is_cancelled():
                    return None
                idx, item = idx_item
                title = item.get("title", "").replace("[STRATEGIC SIGNAL] ", "").strip()
                link = item.get("link", "").strip()
                source = item.get("source", "").strip()

                logger.info("Scraping full text (%d/%d): %s", idx + 1, len(selected_meta), title[:50])
                full_text = scrape_full_text(link, session=session)
                if full_text:
                    return (
                        idx,
                        ScrapedArticle(
                            title=title,
                            source=source,
                            link=link,
                            full_text=full_text
                        )
                    )
                return None

            max_workers = min(5, len(selected_meta)) if selected_meta else 1
            indexed_results: List[Tuple[int, ScrapedArticle]] = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(_scrape_worker, (i, it))
                    for i, it in enumerate(selected_meta)
                ]
                for fut in concurrent.futures.as_completed(futures):
                    res = fut.result()
                    if res:
                        indexed_results.append(res)

            indexed_results.sort(key=lambda x: x[0])
            scraped_package: List[ScrapedArticle] = [art for _, art in indexed_results]

            if not scraped_package:
                raise RuntimeError("Could not retrieve full text for any selected articles.")

            # Compile dossier using LLM
            payload_data = [
                {"title": s.title, "source": s.source, "full_text": s.full_text}
                for s in scraped_package
            ]
            logger.info("Generating comprehensive consolidated dossier with LLM...")
            dossier_text = self.llm_client.generate(
                system_prompt=SYSTEM_PROMPT_DOSSIER,
                user_prompt=json.dumps(payload_data, ensure_ascii=False),
                temperature=0.0,
                agent_name="selector",
                run_id=run_id
            )

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(dossier_text)

            logger.info("Dossier generated successfully and saved to %s", output_path)
            return dossier_text, scraped_package
        finally:
            event_bus.publish(
                event_type="agent_end",
                text="Selector Agent completed dossier generation",
                agent="selector",
                run_id=run_id
            )
