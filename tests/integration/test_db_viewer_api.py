"""Integration tests for Database Viewer REST APIs and Run Cancellation."""

import pytest
from fastapi.testclient import TestClient

from src.models.article import RawArticle
from src.storage.db_manager import DBManager
from src.ui.app import app


@pytest.fixture
def test_client_seeded():
    """Create test client with pre-seeded raw articles and events."""
    db = DBManager()
    db.init_db()

    art1 = RawArticle(
        source_name="G4Media",
        title="Marcel Ciolacu la Bruxelles despre PNRR",
        link="https://test.ro/ciolacu-bruxelles",
        summary="Premierul Ciolacu a discutat finantarea deficitului.",
        published_at="2026-06-10T10:00:00Z",
        published_date="2026-06-10"
    )
    art2 = RawArticle(
        source_name="HotNews",
        title="Nicolae Ciuca despre legea pensiilor",
        link="https://test.ro/ciuca-pensii",
        summary="Liderul PNL sustine majorarea pensiilor.",
        published_at="2026-06-12T12:00:00Z",
        published_date="2026-06-12"
    )
    art3 = RawArticle(
        source_name="Digi24",
        title="Drone militare identificate la granita",
        link="https://test.ro/drone-nato",
        summary="NATO sporeste prezenta pe flancul estic.",
        published_at="2026-06-15T14:00:00Z",
        published_date="2026-06-15"
    )
    db.insert_raw_articles([art1, art2, art3])

    return TestClient(app)


def test_get_db_tables(test_client_seeded: TestClient):
    """Verify listing of whitelisted database tables with columns and row counts."""
    response = test_client_seeded.get("/api/db/tables")
    assert response.status_code == 200
    tables = response.json()
    assert isinstance(tables, list)

    table_names = [t["name"] for t in tables]
    assert "raw_articles" in table_names
    assert "extracted_events" in table_names
    assert "historical_anomalies" in table_names
    assert "threat_vectors" in table_names
    assert "pipeline_executions" in table_names

    raw_table = next(t for t in tables if t["name"] == "raw_articles")
    assert raw_table["row_count"] >= 3
    col_names = [c["name"] for c in raw_table["columns"]]
    assert "title" in col_names
    assert "published_at" in col_names
    assert "published_date" in col_names


def test_get_db_schema_summary(test_client_seeded: TestClient):
    """Verify schema summary endpoint returns table structures."""
    response = test_client_seeded.get("/api/db/schema")
    assert response.status_code == 200
    schema = response.json()
    assert "raw_articles" in schema
    assert "extracted_events" in schema
    assert schema["raw_articles"]["row_count"] >= 3


def test_get_table_rows_pagination_and_sorting(test_client_seeded: TestClient):
    """Verify limit, offset, and sorting parameters on database viewer."""
    # Limit 2, sort ascending by id
    resp_asc = test_client_seeded.get("/api/db/tables/raw_articles/rows?limit=2&offset=0&sort=id&order=ASC")
    assert resp_asc.status_code == 200
    data_asc = resp_asc.json()
    assert len(data_asc["rows"]) == 2
    assert data_asc["rows"][0]["id"] < data_asc["rows"][1]["id"]

    # Limit 2, sort descending by id
    resp_desc = test_client_seeded.get("/api/db/tables/raw_articles/rows?limit=2&offset=0&sort=id&order=DESC")
    assert resp_desc.status_code == 200
    data_desc = resp_desc.json()
    assert len(data_desc["rows"]) == 2
    assert data_desc["rows"][0]["id"] > data_desc["rows"][1]["id"]


def test_get_table_rows_text_search(test_client_seeded: TestClient):
    """Verify search filter parameter q matching text columns."""
    response = test_client_seeded.get("/api/db/tables/raw_articles/rows?q=Ciolacu")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert any("Ciolacu" in row["title"] for row in data["rows"])


def test_get_table_rows_date_range_filter(test_client_seeded: TestClient):
    """Verify date range filtering (date_from, date_to)."""
    response = test_client_seeded.get(
        "/api/db/tables/raw_articles/rows?date_from=2026-06-11&date_to=2026-06-14"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["rows"][0]["published_date"] == "2026-06-12"


def test_get_table_row_by_id(test_client_seeded: TestClient):
    """Verify fetching individual record by primary key."""
    # First get a valid row id
    rows_resp = test_client_seeded.get("/api/db/tables/raw_articles/rows?limit=1")
    valid_id = rows_resp.json()["rows"][0]["id"]

    resp = test_client_seeded.get(f"/api/db/tables/raw_articles/rows/{valid_id}")
    assert resp.status_code == 200
    row = resp.json()
    assert row["id"] == valid_id

    # Nonexistent row ID returns 404
    resp_missing = test_client_seeded.get("/api/db/tables/raw_articles/rows/999999")
    assert resp_missing.status_code == 404

    # Nonexistent table returns 404
    resp_bad_table = test_client_seeded.get("/api/db/tables/not_a_table/rows/1")
    assert resp_bad_table.status_code == 404


def test_export_table_csv(test_client_seeded: TestClient):
    """Verify table CSV export produces valid CSV with headers and records."""
    response = test_client_seeded.get("/api/db/export/raw_articles.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment; filename=raw_articles.csv" in response.headers.get("content-disposition", "")

    csv_text = response.text
    lines = csv_text.strip().splitlines()
    assert len(lines) >= 4  # Header + 3 rows
    header = lines[0].split(",")
    assert "title" in header
    assert "link" in header
    assert "published_date" in header


def test_cancel_pipeline_endpoint(test_client_seeded: TestClient):
    """Verify POST /api/run/cancel endpoint behavior when idle."""
    response = test_client_seeded.post("/api/run/cancel")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] in ["idle", "cancelling"]


def test_run_pipeline_rejects_future_date_with_422(test_client_seeded: TestClient):
    """Verify POST /api/run validates date and rejects future dates with HTTP 422."""
    resp_future = test_client_seeded.post(
        "/api/run",
        json={"stage": "select", "date": "2099-01-01"}
    )
    assert resp_future.status_code == 422
    assert "future" in resp_future.json()["detail"].lower()

    resp_bad_fmt = test_client_seeded.post(
        "/api/run",
        json={"stage": "select", "date": "14/06/2026"}
    )
    assert resp_bad_fmt.status_code == 422
    assert "invalid date format" in resp_bad_fmt.json()["detail"].lower()


def test_get_db_graph_similarity_and_actors(test_client_seeded: TestClient):
    """Verify Connected Papers graph endpoint GET /api/db/graph."""
    # 1. Similarity mode
    resp_sim = test_client_seeded.get("/api/db/graph?mode=similarity&min_similarity=0.5")
    assert resp_sim.status_code == 200
    data_sim = resp_sim.json()
    assert data_sim["mode"] == "similarity"
    assert "nodes" in data_sim
    assert "edges" in data_sim
    assert "meta" in data_sim

    # 2. Actors & Power mode
    resp_act = test_client_seeded.get("/api/db/graph?mode=actors")
    assert resp_act.status_code == 200
    data_act = resp_act.json()
    assert data_act["mode"] == "actors"
    assert "nodes" in data_act
    assert "edges" in data_act

    # 3. Validation on invalid mode
    resp_inv = test_client_seeded.get("/api/db/graph?mode=invalid_mode")
    assert resp_inv.status_code == 422
