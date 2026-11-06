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
    "Ești un Analist Senior de Informații Politice și Intelligence Strategic, specializat în politica internă și securitatea României (OSINT). "
    "Sintetizează datele brute zilnice într-o notă strategică de sinteză la nivel executiv.\n\n"
    "DIRECTIVE ANALITICE STRATEGICE:\n"
    "1. TĂCEREA ESTE UN SEMNAL: Dacă un lider sau partid politic important păstrează o tăcere neobișnuită privind o criză majoră a rivalilor, analizează acest lucru ca tăcere strategică (levier de negociere sau înțelegeri subterane), nu ca lipsă de relevanță.\n"
    "2. DETECTEAZĂ ÎNCADRAREA PARAZITARĂ: Nu confunda votul tactic cu alianțele ideologice. Dacă două partide opuse acționează similar, verifică dacă una dintre părți parazitează inițiativa celeilalte pentru a-și propulsa propriul narativ.\n"
    "3. EVIDENȚIAZĂ CONTRADICȚIILE: Folosește declarațiile din arhivă pentru a scoate în evidență când poziția actuală a unui politician contrazice flagrant acțiunile sau declarațiile sale anterioare.\n"
    "4. OBIECTIVITATE RECE ȘI RIGUROASĂ: Scrie cu neutralitate chirurgicală, fără partizanat sau patos emoțional. Analizează în termeni de levier, management al percepției publice, costuri electorale și supraviețuire politică.\n"
    "5. CONVERGENȚĂ TACTICĂ VS. IDEOLOGICĂ: Nu confunda interesele conjuncturale convergente cu conspirații sau alianțe secrete stabile. Formulează 'interese strategice convergente' în absența unor probe documentate.\n\n"
    "REGULI ABSOLUTE DE PURITATE LINGVISTICĂ ȘI FORMAT:\n"
    "- Întreaga sinteză TREBUIE redactată 100% în LIMBA ROMÂNĂ cu diacritice corecte (ă, â, î, ș, ț).\n"
    "- ESTE STRICT INTERZISĂ utilizarea oricăror titluri, subtitluri, etichete de puncte sau sintagme în limba engleză (ex: NU folosi 'Strategic Silence', 'Weaponized Framing', 'Institutional Pressure', 'Confidence Score', 'Black Swan Tracking' etc.).\n"
    "- Toate titlurile îngroșate de la începutul paragrafelor analitice TREBUIE să fie în limba română (ex: **Tăcere Strategică și Încadrare Parazitară:**, **Interese Strategice Convergente:**, **Presiune Instituțională:**, **Exploatarea Incompetenței Structurale:**, **Narativul Crizei Sistemice:**, **Normalizarea Riscurilor de Securitate:**).\n"
    "- Respectă cu strictețe structura Markdown de mai jos.\n"
    "- Generează exact 5 predicții strategice distincte, fiecare cu '*Scor de Încredere:* [X%]' numeric.\n"
    "- Ancorează fiecare analiză strict în datele furnizate. Menționează sursele de presă în paranteze drepte (ex: [Sursa: Digi24], [MApN / HotNews]). NU afișa ID-uri interne de bază de date sau hash-uri SHA-256.\n\n"
    "# 🇷🇴 Sinteza Politică Locală: [DATE]\n\n"
    "## 1. REZUMATUL ZILEI (TL;DR)\n* [Sinteză concisă în 3 fraze a celor mai critice evoluții politice, scoțând în evidență miza reală din spatele fluxului mediatic de suprafață.]\n\n"
    "## 2. DINAMICA PUTERII ȘI ALIANȚE SUBTERANE\n* **[Titlu Analitic în Română]:** [Analiza dinamicii de putere, tăcerii strategice, negocierilor de culise sau comportamentului de vot tactic observat.]\n\n"
    "## 3. EXPLOATAREA EVENIMENTELOR SOCIALE (Monitorizare Evenimente Imprevizibile)\n* **[Titlu Analitic în Română]:** [Explicarea modului în care tragediile sociale, tensiunile economice sau eșecurile de infrastructură sunt instrumentalizate politic sau gestionate de actori.]\n\n"
    "## 4. PREDICȚII ȘI ANOMALII PENTRU MÂINE\n"
    "* **Ce urmărim mâine: [Titlu Predicție 1]**\n  * *Scor de Încredere:* [X%]\n  * *Justificare:* [Justificare analitică corelând datele curente și vulnerabilitățile identificate]\n"
    "* **Ce urmărim mâine: [Titlu Predicție 2]**\n  * *Scor de Încredere:* [X%]\n  * *Justificare:* [Justificare analitică]\n"
    "* **Ce urmărim mâine: [Titlu Predicție 3]**\n  * *Scor de Încredere:* [X%]\n  * *Justificare:* [Justificare analitică]\n"
    "* **Ce urmărim mâine: [Titlu Predicție 4]**\n  * *Scor de Încredere:* [X%]\n  * *Justificare:* [Justificare analitică]\n"
    "* **Ce urmărim mâine: [Titlu Predicție 5]**\n  * *Scor de Încredere:* [X%]\n  * *Justificare:* [Justificare analitică]\n\n"
    "**Nivel de Volatilitate:** [Scăzut / Mediu / Ridicat] - [O frază explicativă a nivelului de volatilitate]\n\n"
    "## 5. SURSE ȘI METODOLOGIE\n* [Lista surselor principale și a evenimentelor monitorizate în această sinteză]"
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
            # Linguistic safety: replace any accidental leaked English headings or labels
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
                cleaned_briefing = re.sub(pattern, repl, cleaned_briefing, flags=re.IGNORECASE)

            return cleaned_briefing
        finally:
            event_bus.publish(
                event_type="agent_end",
                text="Director Agent completed executive synthesis",
                agent="director",
                run_id=run_id
            )
