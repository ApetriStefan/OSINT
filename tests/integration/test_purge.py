"""Integration tests for the system purge functionality (SQLite, ChromaDB, and reports)."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from src.storage.db_manager import DBManager
from src.storage.vector_store import VectorStore
from src.ui.app import app


def test_db_manager_purge_all_data(tmp_path):
    """Verify DBManager.purge_all_data cleans all tables and resets sequence."""
    test_db = str(tmp_path / "test_purge.db")
    db = DBManager(db_path=test_db)

    # Insert dummy data
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO raw_articles (source_name, title, link, published_date, summary) "
            "VALUES ('Feed', 'Title', 'http://link', '2026-11-06', 'Content')"
        )
        conn.execute(
            "INSERT INTO extracted_events (article_id, actor, action, topic, verbatim_evidence, event_hash) "
            "VALUES (1, 'PSD', 'Action', 'Politics', 'Quote', 'hash2')"
        )
        conn.execute(
            "INSERT INTO pipeline_executions (run_id, stage, status) VALUES ('run_test', 'all', 'COMPLETED')"
        )

    # Verify counts > 0
    assert db.get_dashboard_stats()["total_articles"] == 1
    assert db.get_dashboard_stats()["total_events"] == 1

    # Execute purge
    purged = db.purge_all_data()
    assert purged["raw_articles"] == 1
    assert purged["extracted_events"] == 1
    assert purged["pipeline_executions"] == 1

    # Verify all tables are empty
    stats = db.get_dashboard_stats()
    assert stats["total_articles"] == 0
    assert stats["total_events"] == 0
    assert stats["total_anomalies"] == 0
    assert stats["total_threats"] == 0


def test_vector_store_purge(tmp_path):
    """Verify VectorStore.purge deletes all collections and recreates cleanly."""
    chroma_dir = str(tmp_path / "chroma_purge_test")
    vstore = VectorStore(chroma_path=chroma_dir, collection_name="test_purge_collection")
    assert vstore.count() == 0

    # Purge on empty
    cnt = vstore.purge()
    assert cnt == 0
    assert vstore.count() == 0


def test_ui_api_system_purge_endpoint(tmp_path, monkeypatch):
    """Verify /api/system/purge endpoint works via API client."""
    import src.ui.app as ui_app

    test_db = str(tmp_path / "ui_purge_test.db")
    test_reports = tmp_path / "reports"
    test_reports.mkdir(parents=True, exist_ok=True)
    (test_reports / "test_report.md").write_text("# Test Report", encoding="utf-8")

    db = DBManager(db_path=test_db)
    monkeypatch.setattr(ui_app, "REPORTS_DIR", test_reports)
    monkeypatch.setattr(ui_app, "BASE_DIR", tmp_path)

    with patch("src.ui.app.DBManager", return_value=db):
        with patch.object(ui_app, "VectorStore") as mock_vstore_cls:
            mock_vstore = MagicMock()
            mock_vstore.purge.return_value = 5
            mock_vstore_cls.return_value = mock_vstore

            client = TestClient(app)
            response = client.post("/api/system/purge", json={"delete_db": True, "delete_chroma": True, "delete_reports": True})
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "test_report.md" in data["details"]["reports"]
            assert data["details"]["chromadb_vectors"] == 5

            # Ensure report file was actually deleted
            assert not (test_reports / "test_report.md").exists()
