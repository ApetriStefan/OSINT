"""Unit tests for MasterPipeline stage controls, run_id generation, and checkpoints."""

import pytest
from unittest.mock import MagicMock

from src.orchestrator.pipeline import MasterPipeline
from src.storage.db_manager import DBManager


def test_master_pipeline_initialization(db_manager: DBManager):
    """Verify MasterPipeline instantiates with default managers."""
    pipeline = MasterPipeline(db_manager=db_manager)
    assert pipeline.db_manager == db_manager
    assert pipeline.STAGE_ALL == "all"
    assert pipeline.STAGE_INGEST == "ingest"
    assert pipeline.STAGE_SELECT == "select"
    assert pipeline.STAGE_AGENTS == "agents"
    assert pipeline.STAGE_SYNTHESIZE == "synthesize"


def test_generate_run_id():
    """Verify run_id contains date prefix and unique identifier."""
    pipeline = MasterPipeline()
    run_id1 = pipeline.generate_run_id()
    run_id2 = pipeline.generate_run_id()
    assert run_id1.startswith("run_")
    assert run_id1 != run_id2


def test_invalid_stage_raises_value_error(db_manager: DBManager):
    """Verify invalid stage input raises ValueError."""
    pipeline = MasterPipeline(db_manager=db_manager)
    with pytest.raises(ValueError, match="Unknown pipeline stage"):
        pipeline.run(stage="invalid_stage")


def test_stage_ingest_orchestration(db_manager: DBManager, monkeypatch, sample_raw_articles):
    """Verify stage_ingest calls scraper and inserts into database."""
    pipeline = MasterPipeline(db_manager=db_manager)
    monkeypatch.setattr(pipeline.scraper, "fetch_all", lambda: sample_raw_articles)

    run_id = pipeline.generate_run_id()
    new_count = pipeline.stage_ingest(run_id)
    assert new_count == len(sample_raw_articles)

    # Check execution checkpoint was logged
    status = db_manager.get_pipeline_status(run_id)
    assert status["status"] == "COMPLETED"
    assert "Scraped" in status["details"]
