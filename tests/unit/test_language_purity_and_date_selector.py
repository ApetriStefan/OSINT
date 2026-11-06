"""Tests for language purity in executive briefing and strict date filtering in NewsSelector."""

from unittest.mock import MagicMock
import pytest

from src.agents.agent_copyeditor import CopyeditorAgent
from src.agents.agent_director import DirectorAgent
from src.agents.selector import NewsSelector
from src.models.article import RawArticle
from src.models.intelligence import ExtractedEvent, ThreatVector


def test_news_selector_explicit_date_does_not_silently_fallback(monkeypatch):
    """Verify that NewsSelector returns an empty candidate list if an explicitly requested date has 0 articles."""
    mock_db = MagicMock()
    mock_db.get_raw_articles_for_date.return_value = []
    # If fallback were called, it would return dummy recent articles
    mock_db.get_recent_articles.return_value = [
        RawArticle(
            id=1,
            source_name="Digi24",
            title="Recent Article",
            link="http://test",
            published_date="2026-11-06"
        )
    ]

    selector = NewsSelector(db_manager=mock_db, llm_client=MagicMock())

    # 1. Explicit past date with 0 articles -> must return [] without calling get_recent_articles
    candidates = selector.prepare_candidates(target_date="2026-06-13")
    assert candidates == []
    mock_db.get_recent_articles.assert_not_called()

    # 2. None target date (auto run) -> may call get_recent_articles as fallback
    candidates_auto = selector.prepare_candidates(target_date=None)
    mock_db.get_recent_articles.assert_called_once_with(days=2)
    assert len(candidates_auto) == 1


def test_director_agent_replaces_english_headers_with_romanian():
    """Verify that DirectorAgent post-processing replaces leaked English bullet titles and labels."""
    mock_llm = MagicMock()
    raw_output = (
        "# 🇷🇴 Sinteza Politică Locală: [DATE]\n\n"
        "## 2. DINAMICA PUTERII ȘI ALIANȚE SUBTERANE\n"
        "* **Strategic Silence & Weaponized Framing:** PSD a ales un risc calculat.\n"
        "* **Convergent Strategic Interests:** Există o convergență tactică.\n"
        "* **Institutional Pressure:** PNL folosește acuzațiile.\n\n"
        "## 3. EXPLOATAREA EVENIMENTELOR SOCIALE (Black Swan Tracking)\n"
        "* **Weaponizing Incompetence:** Paralizarea proiectului de drone.\n"
        "* **Systemic Crisis Narrative:** Tema provocărilor digitale.\n"
        "* **Security Normalization:** Confirmarea riscurilor.\n\n"
        "## 4. PREDICȚII ȘI ANOMALII PENTRU MÂINE\n"
        "* **Ce urmărim mâine: Test Predicție**\n"
        "  * *Confidence Score:* 85%\n"
        "  * *Justificare:* Test\n"
    )
    mock_llm.generate.return_value = raw_output

    director = DirectorAgent(llm_client=mock_llm)
    event = ExtractedEvent(
        article_id=1,
        actor="PSD",
        action="action",
        verbatim_evidence="declaratie",
        topic="Politics"
    )

    result = director.run(events=[event], anomalies=[], threats=[], date_str="2026-11-06")

    # Assert all English headers are cleanly translated
    assert "Strategic Silence & Weaponized Framing" not in result
    assert "Tăcere Strategică și Încadrare Parazitară" in result
    assert "Convergent Strategic Interests" not in result
    assert "Interese Strategice Convergente" in result
    assert "Institutional Pressure" not in result
    assert "Presiune Instituțională" in result
    assert "Weaponizing Incompetence" not in result
    assert "Exploatarea Incompetenței Structurale" in result
    assert "Confidence Score" not in result
    assert "Scor de Încredere" in result
    assert "Black Swan Tracking" not in result
    assert "Monitorizare Evenimente Imprevizibile" in result


def test_copyeditor_harmonizes_residual_english_terms(tmp_path):
    """Verify CopyeditorAgent ensures 100% Romanian output even if English terms pass through."""
    mock_llm = MagicMock()
    # Mock LLM returning text with an accidental English label
    mock_llm.generate.return_value = (
        "## 4. PREDICȚII\n"
        "* **Ce urmărim mâine: Test**\n"
        "  * *Confidence Score:* 90%\n"
        "  * *Justificare:* Analiză\n"
        "* **Systemic Crisis Narrative:** Discurs politic."
    )

    copyeditor = CopyeditorAgent(llm_client=mock_llm)
    res = copyeditor.run(
        raw_briefing="input",
        target_date="2026-11-06",
        save_file=False,
        reports_dir=str(tmp_path)
    )

    assert "Confidence Score" not in res
    assert "Scor de Încredere" in res
    assert "Systemic Crisis Narrative" not in res
    assert "Narativul Crizei Sistemice" in res
