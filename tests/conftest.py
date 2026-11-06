"""Pytest fixtures for unit and integration testing."""

import os
import shutil
import tempfile
from datetime import datetime
from typing import Generator, List
import pytest

from src.models.article import RawArticle, ScrapedArticle
from src.models.intelligence import ExtractedEvent, HistoricalAnomaly, ThreatVector
from src.storage.db_manager import DBManager
from src.storage.vector_store import VectorStore


@pytest.fixture(autouse=True)
def isolate_runtime_state(tmp_path, monkeypatch) -> None:
    """Redirect default SQLite/Chroma paths to a temp dir for EVERY test.

    Prevents tests that call DBManager()/VectorStore() with defaults from writing
    fixture data into the user's real political_intel.db or chroma_db/.
    """
    from src.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "test_intel.db"))
    monkeypatch.setattr(settings, "chroma_path", str(tmp_path / "chroma"))


@pytest.fixture
def tmp_db_path() -> Generator[str, None, None]:
    """Provide a temporary SQLite database file path."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


@pytest.fixture
def db_manager(tmp_db_path: str) -> DBManager:
    """Provide an initialized DBManager using temporary SQLite database."""
    manager = DBManager(db_path=tmp_db_path)
    manager.init_db()
    return manager


@pytest.fixture
def tmp_chroma_dir() -> Generator[str, None, None]:
    """Provide a temporary directory for ChromaDB."""
    tmp_dir = tempfile.mkdtemp(prefix="chroma_test_")
    yield tmp_dir
    shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture
def sample_raw_articles() -> List[RawArticle]:
    """Provide sample raw articles representing Romanian news."""
    return [
        RawArticle(
            source_name="G4Media",
            title="Marcel Ciolacu anunță noi negocieri în coaliție pentru deficitul bugetar",
            link="https://www.g4media.ro/articol-1.html",
            summary="Premierul Ciolacu a declarat că guvernul nu va crește taxele.",
            published_date="2026-06-14"
        ),
        RawArticle(
            source_name="Digi24",
            title="Drone rusești căzute lângă frontiera României: Reacția MApN și a NATO",
            link="https://www.digi24.ro/articol-2.html",
            summary="Forțele aeriene române au ridicat avioane F-16 pentru monitorizare.",
            published_date="2026-06-14"
        ),
        RawArticle(
            source_name="HotNews",
            title="DNA face percheziții într-un dosar de corupție privind fonduri PNRR",
            link="https://www.hotnews.ro/articol-3.html",
            summary="Procurorii investighează licitații trucate pentru infrastructură.",
            published_date="2026-06-14"
        ),
        RawArticle(
            source_name="Tabloid",
            title="Scandal la Insula Iubirii: Ce concurent a părăsit emisiunea",
            link="https://www.tabloid.ro/articol-noise.html",
            summary="Momente de tensiune maximă în reality show.",
            published_date="2026-06-14"
        )
    ]


@pytest.fixture
def sample_events() -> List[ExtractedEvent]:
    """Provide sample extracted events with verbatim evidence."""
    return [
        ExtractedEvent(
            actor="Marcel Ciolacu",
            canonical_actor="Marcel Ciolacu",
            action="Pledged that the government will not introduce new taxes in 2026",
            verbatim_evidence="Nu vom crește taxele și impozitele în acest an, este o linie roșie pentru PSD.",
            topic="Fiscal Policy"
        ),
        ExtractedEvent(
            actor="Elena Lasconi",
            canonical_actor="Elena Lasconi",
            action="Criticized government spending and requested public audit of PNRR funds",
            verbatim_evidence="Cerem guvernului să publice lista tuturor contractelor finanțate prin PNRR.",
            topic="Domestic Politics"
        ),
        ExtractedEvent(
            actor="George Simion",
            canonical_actor="George Simion",
            action="Demanded urgent motion against minister over border security measures",
            verbatim_evidence="Depunem moțiune simplă împotriva ministrului Apărării.",
            topic="National Security"
        )
    ]


@pytest.fixture
def sample_anomalies() -> List[HistoricalAnomaly]:
    """Provide sample historical anomalies."""
    return [
        HistoricalAnomaly(
            anomaly_type="contradiction",
            target="Marcel Ciolacu",
            past_statement="Vom elimina toate facilitățile fiscale pentru a reduce deficitul.",
            current_statement="Nu vom crește taxele și impozitele în acest an.",
            contradiction_score=0.85,
            analyst_note="Direct reversal from previous pledge to eliminate fiscal exemptions."
        )
    ]


@pytest.fixture
def sample_threats() -> List[ThreatVector]:
    """Provide sample threat vectors."""
    return [
        ThreatVector(
            threat_type="vulnerability",
            vulnerable_actor="Marcel Ciolacu",
            exploiting_actor="USR",
            description="Opposing party can weaponize contradictory fiscal pledges during the autumn parliamentary session."
        )
    ]
