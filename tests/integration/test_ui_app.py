"""Integration tests for the OSINT real-time Web Dashboard and API endpoints."""

from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from src.ui.app import app, pipeline_manager, log_broadcaster, REPORTS_DIR


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create a FastAPI test client with an isolated temp reports directory.

    Never touches the real reports/ directory, so tests cannot pollute user data.
    """
    import src.ui.app as ui_app

    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "Sinteza_Politica_2026-07-18.md").write_text(
        "# Sinteza Politică Locală: 18 Iulie 2026\n\n## 1. REZUMATUL ZILEI\n* Test briefing.",
        encoding="utf-8",
    )
    monkeypatch.setattr(ui_app, "REPORTS_DIR", reports)
    monkeypatch.setattr(ui_app, "BASE_DIR", tmp_path)
    return TestClient(app)


def test_serve_index_endpoint(client):
    """Test root dashboard endpoint serves HTML."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_get_system_status(client):
    """Test system status endpoint returns DB metrics, Ollama ctx=131072, and pipeline state."""
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert "database" in data
    assert "total_articles" in data["database"]
    assert "total_events" in data["database"]

    assert "ollama" in data
    # Critical user requirement: num_ctx must be preserved at 131072
    assert data["ollama"]["num_ctx"] == 131072
    assert data["ollama"]["active_model"] == "gemma-4-e4b"
    assert data["ollama"]["embedding_model"] == "nomic-embed-text"

    assert "vector_store" in data
    assert "pipeline" in data
    assert "is_running" in data["pipeline"]


def test_list_reports(client):
    """Test listing of daily political synthesis reports."""
    response = client.get("/api/reports")
    assert response.status_code == 200
    reports = response.json()
    assert isinstance(reports, list)
    assert len(reports) > 0

    first = reports[0]
    assert "filename" in first
    assert "date" in first
    assert "size_bytes" in first
    assert first["filename"].startswith("Sinteza_Politica_")


def test_get_report_content_success(client):
    """Test fetching existing briefing markdown content."""
    response = client.get("/api/reports/Sinteza_Politica_2026-07-18.md")
    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "Sinteza_Politica_2026-07-18.md"
    assert "Sinteza Politică Locală: 18 Iulie 2026" in data["content"]


def test_get_report_content_security_validation(client):
    """Test directory traversal and invalid filename protection."""
    # Invalid filename format
    resp_bad_name = client.get("/api/reports/passwords.txt")
    assert resp_bad_name.status_code == 400

    # Non-existent report
    resp_missing = client.get("/api/reports/Sinteza_Politica_1999-01-01.md")
    assert resp_missing.status_code == 404


def test_get_anomalies_and_threats(client):
    """Test retrieving anomalies and threat vectors."""
    resp_anom = client.get("/api/anomalies?limit=10")
    assert resp_anom.status_code == 200
    assert isinstance(resp_anom.json(), list)

    resp_threats = client.get("/api/threats?limit=10")
    assert resp_threats.status_code == 200
    threats = resp_threats.json()
    assert isinstance(threats, list)
    if len(threats) > 0:
        assert "threat_type" in threats[0]
        assert "vulnerable_actor" in threats[0]


def test_get_articles_and_executions(client):
    """Test retrieving raw articles and pipeline execution history."""
    resp_articles = client.get("/api/articles?limit=5")
    assert resp_articles.status_code == 200
    assert isinstance(resp_articles.json(), list)

    resp_exec = client.get("/api/executions?limit=5")
    assert resp_exec.status_code == 200
    assert isinstance(resp_exec.json(), list)


def test_pipeline_run_background_trigger(client):
    """Test asynchronous non-blocking trigger of pipeline."""
    # Ensure pipeline manager is idle before test
    pipeline_manager.is_running = False

    with patch.object(pipeline_manager, "_execute_worker") as mock_worker:
        response = client.post(
            "/api/run",
            json={"stage": "ingest", "dossier": "test_dossier.txt"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"
        assert "run_id" in data

        # Conflict check when pipeline is marked as running
        pipeline_manager.is_running = True
        conflict_resp = client.post("/api/run", json={"stage": "all"})
        assert conflict_resp.status_code == 409

        # Cleanup state
        pipeline_manager.is_running = False
