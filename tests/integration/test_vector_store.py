"""Integration tests for VectorStore with ChromaDB and nomic-embed-text."""

import pytest
import responses
from unittest.mock import MagicMock

from src.models.intelligence import ExtractedEvent
from src.storage.vector_store import VectorStore


@pytest.fixture
def mock_768_embedding():
    """Return a fixed 768-dimensional float embedding."""
    return [0.01 * (i % 10) for i in range(768)]


def test_vector_store_initialization(tmp_chroma_dir: str):
    """Verify VectorStore initializes persistent ChromaDB collection."""
    store = VectorStore(chroma_path=tmp_chroma_dir, collection_name="test_events")
    assert store.count() == 0


@responses.activate
def test_get_embedding_success(tmp_chroma_dir: str, mock_768_embedding):
    """Verify get_embedding calls Ollama endpoint and returns 768-dim vector."""
    responses.add(
        responses.POST,
        "http://localhost:11434/api/embeddings",
        json={"embedding": mock_768_embedding},
        status=200
    )

    store = VectorStore(chroma_path=tmp_chroma_dir, collection_name="test_events")
    emb = store.get_embedding("Test text for embedding")
    assert emb is not None
    assert len(emb) == 768


@responses.activate
def test_get_embedding_failure(tmp_chroma_dir: str):
    """Verify get_embedding handles network errors gracefully."""
    responses.add(
        responses.POST,
        "http://localhost:11434/api/embeddings",
        status=500
    )

    store = VectorStore(chroma_path=tmp_chroma_dir, collection_name="test_events")
    emb = store.get_embedding("Test failure")
    assert emb is None


def test_add_events_and_search(tmp_chroma_dir: str, sample_events, mock_768_embedding, monkeypatch):
    """Verify adding events and semantic search functionality."""
    store = VectorStore(chroma_path=tmp_chroma_dir, collection_name="test_events")

    # Mock get_embedding to return consistent deterministic embeddings
    monkeypatch.setattr(store, "get_embedding", lambda text: mock_768_embedding)

    added_count = store.add_events(sample_events)
    assert added_count == len(sample_events)
    assert store.count() == len(sample_events)

    # Search without filter
    results = store.search_events(query="tax policy and budget", n_results=2)
    assert len(results) <= 2
    assert "document" in results[0]
    assert "metadata" in results[0]

    # Search with actor filter
    ciolacu_results = store.search_events(
        query="tax freeze",
        n_results=5,
        filter_actor="Marcel Ciolacu"
    )
    for r in ciolacu_results:
        assert r["metadata"]["actor"] == "Marcel Ciolacu"


def test_empty_search_graceful(tmp_chroma_dir: str):
    """Verify searching an empty vector store returns empty list without error."""
    store = VectorStore(chroma_path=tmp_chroma_dir, collection_name="test_empty")
    results = store.search_events(query="anything")
    assert results == []


@responses.activate
def test_get_embeddings_batch_success(tmp_chroma_dir: str, mock_768_embedding):
    """Verify get_embeddings_batch uses /api/embed and returns list of embeddings."""
    responses.add(
        responses.POST,
        "http://localhost:11434/api/embed",
        json={"embeddings": [mock_768_embedding, mock_768_embedding]},
        status=200
    )

    store = VectorStore(chroma_path=tmp_chroma_dir, collection_name="test_batch")
    embs = store.get_embeddings_batch(["Text 1", "Text 2"])
    assert len(embs) == 2
    assert len(embs[0]) == 768
    assert len(embs[1]) == 768


@responses.activate
def test_get_embeddings_batch_fallback(tmp_chroma_dir: str, mock_768_embedding):
    """Verify get_embeddings_batch falls back to individual calls when /api/embed fails."""
    responses.add(
        responses.POST,
        "http://localhost:11434/api/embed",
        status=404
    )
    responses.add(
        responses.POST,
        "http://localhost:11434/api/embeddings",
        json={"embedding": mock_768_embedding},
        status=200
    )

    store = VectorStore(chroma_path=tmp_chroma_dir, collection_name="test_batch_fallback")
    embs = store.get_embeddings_batch(["Single Text"])
    assert len(embs) == 1
    assert len(embs[0]) == 768
