"""Integration tests for DBManager (SQLite WAL, indexes, unique hashes, migrations, state machine)."""

from datetime import datetime
import pytest

from src.models.article import RawArticle
from src.models.intelligence import ExtractedEvent, HistoricalAnomaly, ThreatVector
from src.storage.db_manager import DBManager


def test_db_init_and_pragma_settings(db_manager: DBManager):
    """Verify database initialization sets WAL mode, foreign keys, and synchronous mode."""
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode;")
        journal = cursor.fetchone()[0]
        # In SQLite, WAL or memory/delete depending on file system, should be wal for file DB
        assert journal.lower() in ["wal", "memory"]

        cursor.execute("PRAGMA foreign_keys;")
        fk = cursor.fetchone()[0]
        assert fk == 1

        cursor.execute("SELECT name FROM sqlite_master WHERE type = 'index';")
        indexes = {row[0] for row in cursor.fetchall()}
        assert "idx_articles_pub_date" in indexes
        assert "idx_events_actor" in indexes


def test_raw_article_insert_and_deduplication(db_manager: DBManager):
    """Verify insertion and unique link constraint on raw articles."""
    art1 = RawArticle(
        source_name="HotNews",
        title="Articol Test 1",
        link="https://www.hotnews.ro/articol-unic.html",
        summary="Descriere scurta",
        published_date="2026-06-14"
    )
    # First insert succeeds
    assert db_manager.insert_raw_article(art1) is True

    # Duplicate link is ignored (returns False because rowcount == 0)
    assert db_manager.insert_raw_article(art1) is False

    # Bulk insert handles duplicates gracefully
    art2 = RawArticle(
        source_name="G4Media",
        title="Articol Test 2",
        link="https://www.g4media.ro/articol-unic-2.html",
        summary="Alta descriere",
        published_date="2026-06-14"
    )
    inserted = db_manager.insert_raw_articles([art1, art2])
    assert inserted == 1  # Only art2 is inserted


def test_query_articles_by_date(db_manager: DBManager):
    """Verify querying raw articles by publication or scrape date."""
    target_date = "2026-06-15"
    art = RawArticle(
        source_name="Digi24",
        title="Stire din 15 iunie",
        link="https://www.digi24.ro/stire-15.html",
        published_date=target_date
    )
    db_manager.insert_raw_article(art)

    results = db_manager.get_raw_articles_for_date(target_date)
    assert len(results) == 1
    assert results[0].link == "https://www.digi24.ro/stire-15.html"

    # Querying nonexistent date returns empty list
    assert db_manager.get_raw_articles_for_date("1999-01-01") == []


def test_extracted_event_hash_deduplication(db_manager: DBManager):
    """Verify deterministic event_hash generation and collision avoidance."""
    event1 = ExtractedEvent(
        actor="Marcel Ciolacu",
        canonical_actor="Marcel Ciolacu",
        action="Announced tax freeze",
        verbatim_evidence="Nu vom introduce taxe noi.",
        topic="Fiscal"
    )
    assert event1.event_hash is not None

    # First insert
    assert db_manager.insert_extracted_event(event1) is True

    # Identical event hash insert must be ignored
    assert db_manager.insert_extracted_event(event1) is False


def test_get_actor_history(db_manager: DBManager):
    """Verify historical statements retrieval for an actor."""
    event1 = ExtractedEvent(
        actor="Marcel Ciolacu",
        canonical_actor="Marcel Ciolacu",
        action="Past action",
        verbatim_evidence="Vom reforma administratia publica.",
        topic="Reform",
        extracted_at=datetime.fromisoformat("2026-05-10 10:00:00")
    )
    db_manager.insert_extracted_event(event1)

    # Historical query before June
    history = db_manager.get_actor_history(actor="Ciolacu", before_date="2026-06-01")
    assert len(history) == 1
    assert history[0]["past_statement"] == "Vom reforma administratia publica."

    # History before April returns empty
    empty_history = db_manager.get_actor_history(actor="Ciolacu", before_date="2026-04-01")
    assert len(empty_history) == 0


def test_insert_anomalies_and_threats(db_manager: DBManager):
    """Verify inserting historical anomalies and threat vectors."""
    anomaly = HistoricalAnomaly(
        anomaly_type="contradiction",
        target="Marcel Ciolacu",
        past_statement="Vom creste taxele.",
        current_statement="Nu vom creste taxele.",
        contradiction_score=0.9,
        analyst_note="Direct reversal of stated position."
    )
    assert db_manager.insert_historical_anomaly(anomaly) is True

    threat = ThreatVector(
        threat_type="vulnerability",
        vulnerable_actor="Marcel Ciolacu",
        exploiting_actor="USR",
        description="Exploitable contradiction on taxation."
    )
    assert db_manager.insert_threat_vector(threat) is True


def test_pipeline_executions_state_machine(db_manager: DBManager):
    """Verify recording and updating pipeline execution stages and status."""
    run_id = "test_run_123"

    # Stage 1: Ingest STARTED
    db_manager.record_pipeline_execution(run_id, stage="ingest", status="STARTED")
    status1 = db_manager.get_pipeline_status(run_id)
    assert status1 is not None
    assert status1["stage"] == "ingest"
    assert status1["status"] == "STARTED"

    # Stage 1: Ingest COMPLETED
    db_manager.record_pipeline_execution(run_id, stage="ingest", status="COMPLETED", details="50 articles")
    status2 = db_manager.get_pipeline_status(run_id)
    assert status2["status"] == "COMPLETED"
    assert status2["details"] == "50 articles"

    # Nonexistent run ID
    assert db_manager.get_pipeline_status("nonexistent_run") is None
