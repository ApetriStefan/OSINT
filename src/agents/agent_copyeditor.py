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
    "Ești un redactor și corector de elită, specializat în limba română și analiza de intelligence politic. "
    "Sarcina ta exclusivă este să corectezi ortografia, diacriticele, gramatica, sintaxa și puritatea lingvistică a textului furnizat.\n\n"
    "REGULI CRITICE:\n"
    "1. Nu altera, adăuga sau elimina fapte, predicții sau substanța analizei de informații.\n"
    "2. Păstrează cu strictețe structura Markdown (#, ##, *, text îngroșat etc.) a documentului original.\n"
    "3. Corectează erorile tipice de scanare/OCR (ex: 'ășirii' -> 'țării', 'ěmi' -> 'îmi', 'aparbine' -> 'aparține') și asigură un flux narativ natural în limba română cu diacritice complete (ă, â, î, ș, ț).\n"
    "4. PURITATE LINGVISTICĂ: Dacă textul conține titluri de secțiuni, etichete îngroșate la început de paragraf (bullet headers) sau concepte rămase în limba engleză (ex: 'Confidence Score', 'Strategic Silence', 'Weaponized Framing', 'Institutional Pressure', 'Weaponizing Incompetence', 'Systemic Crisis Narrative', 'Security Normalization', 'Black Swan'), tradu-le și armonizează-le OBLIGATORIU în limba română elegantă și profesională (ex: 'Scor de Încredere', 'Tăcere Strategică', 'Încadrare Parazitară', 'Presiune Instituțională', 'Exploatarea Incompetenței Structurale', 'Narativul Crizei Sistemice', 'Normalizarea Riscurilor de Securitate', 'Eveniment Imprevizibil').\n"
    "5. Returnează DOAR textul final corectat în format Markdown românesc. Fără introduceri sau concluzii conversaționale."
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

        # Linguistic harmonization: replace any residual leaked English labels or headings
        english_to_romanian_map = [
            (r"\bConfidence Score\b", "Scor de Încredere"),
            (r"\bStrategic Silence & Weaponized Framing\b", "Tăcere Strategică și Încadrare Parazitară"),
            (r"\bStrategic Silence\b", "Tăcere Strategică"),
            (r"\bWeaponized Framing\b", "Încadrare Parazitară"),
            (r"\bConvergent Strategic Interests\b", "Interese Strategice Convergente"),
            (r"\bInstitutional Pressure\b", "Presiune Instituțională"),
            (r"\bWeaponizing Incompetence\b", "Exploatarea Incompetenței Structurale"),
            (r"\bSystemic Crisis Narrative\b", "Narativul Crizei Sistemice"),
            (r"\bSecurity Normalization\b", "Normalizarea Riscurilor de Securitate"),
            (r"\bBlack Swan Tracking\b", "Monitorizare Evenimente Imprevizibile"),
            (r"\bBlack Swan\b", "Eveniment Imprevizibil"),
            (r"\bElectoral Legitimacy Attack\b", "Atac la Legitimitatea Electorală"),
            (r"\bElectoral Vulnerability\b", "Vulnerabilitate Electorală"),
            (r"\bSystemic Competence Crisis\b", "Criză de Competență Sistemică"),
            (r"\bPolitical Instability\b", "Instabilitate Politică"),
        ]
        for pattern, repl in english_to_romanian_map:
            corrected = re.sub(pattern, repl, corrected, flags=re.IGNORECASE)

        date_suffix = target_date or get_bucharest_today_str()
        rep_dir = Path(reports_dir)
        rep_dir.mkdir(parents=True, exist_ok=True)
        report_path = rep_dir / f"Sinteza_Politica_{date_suffix}.md"

        if save_file:
            report_path.write_text(corrected, encoding="utf-8")
            logger.info("Final corrected briefing written to %s", str(report_path))

        return corrected
