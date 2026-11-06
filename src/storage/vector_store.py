"""Vector store module using ChromaDB and Ollama nomic-embed-text embeddings."""

import logging
from typing import Any, Dict, List, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
import requests

from src.config import get_settings
from src.models.intelligence import ExtractedEvent

logger = logging.getLogger(__name__)


class VectorStore:
    """Vector database interface backed by ChromaDB and nomic-embed-text embeddings."""

    def __init__(
        self,
        chroma_path: Optional[str] = None,
        collection_name: str = "political_events",
        ollama_base_url: Optional[str] = None,
        embed_model: Optional[str] = None,
    ) -> None:
        settings = get_settings()
        self.chroma_path = chroma_path or settings.chroma_path
        self.collection_name = collection_name
        self.ollama_base_url = ollama_base_url or settings.ollama_base_url
        self.embed_model = embed_model or settings.ollama_embed_model

        self.client = chromadb.PersistentClient(
            path=self.chroma_path,
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(name=self.collection_name)
        self.session = requests.Session()

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Compute 768-dimensional embedding vector via Ollama nomic-embed-text."""
        if not text.strip():
            return None
        url = f"{self.ollama_base_url.rstrip('/')}/api/embeddings"
        payload = {
            "model": self.embed_model,
            "prompt": text
        }
        try:
            response = self.session.post(url, json=payload, timeout=15)
            if response.status_code == 200:
                data = response.json()
                return data.get("embedding")
            logger.warning("Ollama embeddings returned status %d: %s", response.status_code, response.text)
        except Exception as e:
            logger.warning("Failed to generate embedding for text '%s...': %s", text[:40], e)
        return None

    def get_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Compute 768-dimensional embeddings in batch via Ollama /api/embed with fallback."""
        if not texts:
            return []

        # 1. Attempt batch API (/api/embed)
        url = f"{self.ollama_base_url.rstrip('/')}/api/embed"
        payload = {
            "model": self.embed_model,
            "input": texts
        }
        try:
            response = self.session.post(url, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                embs = data.get("embeddings")
                if embs and len(embs) == len(texts):
                    return embs
            logger.warning("/api/embed returned status %d, falling back to individual calls", response.status_code)
        except Exception as e:
            logger.warning("/api/embed batch endpoint failed (%s), falling back to individual calls", e)

        # 2. Fallback to individual calls
        return [self.get_embedding(t) for t in texts]

    def add_events(self, events: List[ExtractedEvent]) -> int:
        """Embed and upsert extracted events into ChromaDB in one batched call."""
        if not events:
            return 0

        ids: List[str] = []
        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []

        for idx, event in enumerate(events):
            doc_id = event.event_hash or f"evt_{idx}_{int(event.extracted_at.timestamp()) if event.extracted_at else idx}"
            actor_name = event.canonical_actor or event.actor
            doc_text = f"Actor: {actor_name}. Subiect: {event.topic}. Acțiune: {event.action}. Citat: {event.verbatim_evidence}"

            ids.append(doc_id)
            documents.append(doc_text)
            metadatas.append({
                "actor": actor_name,
                "raw_actor": event.actor,
                "topic": event.topic,
                "action": event.action,
                "verbatim_evidence": event.verbatim_evidence[:500],
                "extracted_at": str(event.extracted_at) if event.extracted_at else ""
            })

        # Fetch all embeddings in a single batched call
        embeddings = self.get_embeddings_batch(documents)

        valid_ids: List[str] = []
        valid_documents: List[str] = []
        valid_embeddings: List[List[float]] = []
        valid_metadatas: List[Dict[str, Any]] = []

        for doc_id, doc, emb, meta in zip(ids, documents, embeddings, metadatas):
            if emb:
                valid_ids.append(doc_id)
                valid_documents.append(doc)
                valid_embeddings.append(emb)
                valid_metadatas.append(meta)

        if valid_ids:
            self.collection.upsert(
                ids=valid_ids,
                documents=valid_documents,
                embeddings=valid_embeddings,
                metadatas=valid_metadatas
            )
            return len(valid_ids)
        return 0

    def search_events(
        self,
        query: str,
        n_results: int = 5,
        filter_actor: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Perform semantic search across stored events with optional actor filtering."""
        if self.collection.count() == 0:
            return []

        query_emb = self.get_embedding(query)
        if not query_emb:
            return []

        where_filter = None
        if filter_actor:
            where_filter = {"actor": filter_actor}

        try:
            results = self.collection.query(
                query_embeddings=[query_emb],
                n_results=min(n_results, self.collection.count()),
                where=where_filter
            )
            
            output: List[Dict[str, Any]] = []
            if results and results.get("ids") and len(results["ids"]) > 0:
                ret_ids = results["ids"][0]
                ret_docs = results["documents"][0] if results.get("documents") else []
                ret_metas = results["metadatas"][0] if results.get("metadatas") else []
                ret_dists = results["distances"][0] if results.get("distances") else []

                for i, doc_id in enumerate(ret_ids):
                    output.append({
                        "id": doc_id,
                        "document": ret_docs[i] if i < len(ret_docs) else "",
                        "metadata": ret_metas[i] if i < len(ret_metas) else {},
                        "distance": ret_dists[i] if i < len(ret_dists) else 0.0
                    })
            return output
        except Exception as e:
            logger.warning("Vector search error in ChromaDB: %s", e)
            return []

    def get_all_with_embeddings(self, limit: int = 300) -> Dict[str, Any]:
        """Fetch stored documents with embeddings and metadatas."""
        try:
            cnt = self.collection.count()
            if cnt == 0:
                return {"ids": [], "embeddings": [], "documents": [], "metadatas": []}
            return self.collection.get(
                limit=min(limit, cnt),
                include=["embeddings", "documents", "metadatas"]
            )
        except Exception as e:
            logger.warning("Failed to fetch all embeddings from Chroma: %s", e)
            return {"ids": [], "embeddings": [], "documents": [], "metadatas": []}

    def count(self) -> int:
        """Return total number of embedded documents."""
        try:
            return self.collection.count()
        except Exception:
            return 0

    def purge(self) -> int:
        """Purge all vectors and reset the ChromaDB collection."""
        try:
            cnt = self.collection.count()
        except Exception:
            cnt = 0
        try:
            self.client.delete_collection(name=self.collection_name)
        except Exception as e:
            logger.warning("Error deleting Chroma collection: %s", e)
        self.collection = self.client.get_or_create_collection(name=self.collection_name)
        return cnt

