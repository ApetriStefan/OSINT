"""Agent 5: Romanian Copyeditor and Grammar / Diacritics Corrector."""

import logging
from pathlib import Path
import re
from typing import Optional

from src.events import event_bus
from src.llm.client import OllamaClient
from src.utils_date import get_bucharest_today_str

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_AGENT_5 = (
    "You are an elite proofreader and copyeditor specialized in the Romanian language. "
    "Your sole task is to identify and correct any spelling, diacritics, grammar, syntax, or punctuation mistakes in the provided Romanian text.\n\n"
    "CRITICAL RULES:\n"
    "1. Do not alter, add, or remove any information, predictions, or intelligence analysis.\n"
    "2. Preserve the exact Markdown structure (#, ##, *, bold text, etc.) of the original document.\n"
    "3. Correct common scraped/scanned typos (e.g., 'ășirii' to 'țării', 'ěmi' to 'îmi', 'aparbine' to 'aparține', 'tehnocratele' to 'tehnocrate ale') and ensure natural Romanian flow.\n"
    "4. Return ONLY the finalized, corrected Romanian Markdown text. No conversational intros or outros."
)


class CopyeditorAgent:
    """Agent 5: Proofreads and corrects Romanian grammar, typography, and diacritics in the briefing."""

    def __init__(self, llm_client: Optional[OllamaClient] = None) -> None:
        self.llm_client = llm_client or OllamaClient()

    def run(
        self,
        raw_briefing: str,
        target_date: Optional[str] = None,
        save_file: bool = True,
        run_id: str = "",
        reports_dir: str = "reports"
    ) -> str:
        """Correct Romanian typography and grammar, and write final briefing artifact into reports directory."""
        if not raw_briefing or not raw_briefing.strip():
            raise ValueError("No briefing text provided to Agent 5.")

        logger.info("Executing Agent 5 (Romanian Grammar & Diacritics Copyeditor)...")
        event_bus.publish(
            event_type="agent_start",
            text="Copyeditor Agent started",
            agent="copyeditor",
            run_id=run_id
        )

        try:
            corrected = self.llm_client.generate(
                system_prompt=SYSTEM_PROMPT_AGENT_5,
                user_prompt=raw_briefing,
                temperature=0.0,
                top_p=0.1,
                agent_name="copyeditor",
                run_id=run_id
            )
        finally:
            event_bus.publish(
                event_type="agent_end",
                text="Copyeditor Agent finished",
                agent="copyeditor",
                run_id=run_id
            )

        # Strip any leaked bracketed hex hashes
        corrected = re.sub(
            r"\s*\[[0-9a-fA-F]{16,64}(?:,\s*[0-9a-fA-F]{16,64})*\]",
            "",
            corrected
        )

        date_suffix = target_date or get_bucharest_today_str()
        rep_dir = Path(reports_dir)
        rep_dir.mkdir(parents=True, exist_ok=True)
        report_path = rep_dir / f"Sinteza_Politica_{date_suffix}.md"

        if save_file:
            report_path.write_text(corrected, encoding="utf-8")
            logger.info("Final corrected briefing written to %s", str(report_path))

        return corrected
