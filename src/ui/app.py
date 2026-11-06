"""FastAPI Backend Application for RO-INTEL OSINT Platform.

Provides REST APIs, SSE real-time model thinking & token streaming,
read-only Database Viewer APIs, and executive dashboard interface.
"""

import asyncio
from datetime import datetime
import json
import logging
import math
import numpy as np
import os
from pathlib import Path
import threading
from typing import Any, AsyncGenerator, Dict, List, Optional
import urllib.request
import uuid

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.config import get_settings
from src.events import Event, EventBusLogHandler, event_bus
from src.llm.client import OllamaClient
from src.orchestrator.pipeline import MasterPipeline
from src.storage.db_manager import DBManager
from src.storage.vector_store import VectorStore
from src.utils_date import get_bucharest_today_str, validate_target_date

logger = logging.getLogger("src.ui.app")

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"
REPORTS_DIR = BASE_DIR / "reports"

TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Attach event bus logging handler to root logger
_event_log_handler = EventBusLogHandler(event_bus)
_event_log_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
)
logging.getLogger().addHandler(_event_log_handler)

# Backwards compatibility alias
log_broadcaster = event_bus


# ==================== Pipeline Execution State Manager ====================

class PipelineStateManager:
    """Manages active pipeline run execution in a background worker thread."""

    def __init__(self) -> None:
        self.is_running: bool = False
        self.run_id: Optional[str] = None
        self.stage: Optional[str] = None
        self.target_date: Optional[str] = None
        self.started_at: Optional[str] = None
        self.progress_pct: int = 0
        self.status_message: str = "Idle"
        self.last_error: Optional[str] = None
        self._lock = threading.Lock()

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "is_running": self.is_running,
                "run_id": self.run_id,
                "stage": self.stage,
                "target_date": self.target_date,
                "started_at": self.started_at,
                "progress_pct": self.progress_pct,
                "status_message": self.status_message,
                "last_error": self.last_error,
                "is_cancelled": event_bus.is_cancelled(),
            }

    def start_run(
        self,
        stage: str = "all",
        target_date: Optional[str] = None,
        dossier_path: str = "dossier_for_agent_1.txt"
    ) -> str:
        # Validate date parameter before starting
        try:
            canonical_date = validate_target_date(target_date)
        except ValueError as ve:
            raise HTTPException(
                status_code=422,
                detail=str(ve)
            )

        with self._lock:
            if self.is_running:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A pipeline execution is already in progress."
                )
            self.is_running = True
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.run_id = f"run_{ts}_{uuid.uuid4().hex[:6]}"
            self.stage = stage
            self.target_date = canonical_date
            self.started_at = datetime.now().isoformat()
            self.progress_pct = 5
            self.status_message = f"Starting stage '{stage}' for {canonical_date}..."
            self.last_error = None

        thread = threading.Thread(
            target=self._execute_worker,
            args=(self.run_id, stage, canonical_date, dossier_path),
            daemon=True
        )
        thread.start()
        return self.run_id

    def _execute_worker(
        self,
        run_id: str,
        stage: str,
        target_date: str,
        dossier_path: str
    ) -> None:
        logger.info("[UI-EXEC] Pipeline worker initiated for %s (stage: %s, date: %s)", run_id, stage, target_date)
        try:
            with self._lock:
                self.progress_pct = 10
                self.status_message = f"Executing {stage} for {target_date}..."

            pipeline = MasterPipeline()
            results = pipeline.run(
                stage=stage,
                target_date=target_date,
                dossier_path=dossier_path,
                run_id=run_id
            )

            with self._lock:
                self.is_running = False
                if results.get("status") == "cancelled":
                    self.status_message = f"Execution {run_id} was cancelled by user."
                    self.progress_pct = 0
                else:
                    self.progress_pct = 100
                    self.status_message = f"Execution {run_id} completed successfully."

            logger.info("[UI-EXEC] Pipeline worker finished %s (status: %s).", run_id, results.get("status"))
        except InterruptedError:
            with self._lock:
                self.is_running = False
                self.status_message = f"Execution {run_id} was cancelled."
                self.progress_pct = 0
            logger.info("[UI-EXEC] Pipeline worker %s stopped due to cancellation.", run_id)
        except Exception as e:
            logger.exception("[UI-EXEC] Pipeline execution failed: %s", e)
            with self._lock:
                self.is_running = False
                self.last_error = str(e)
                self.status_message = f"Failed: {e}"


pipeline_manager = PipelineStateManager()


# ==================== FastAPI App Setup ====================

app = FastAPI(
    title="RO-INTEL OSINT Platform",
    description="Real-time Non-blocking Romanian Political Intelligence Dashboard & Database Viewer",
    version="1.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
async def startup_event() -> None:
    """Register running event loop with event_bus."""
    event_bus.set_loop(asyncio.get_running_loop())
    logger.info("RO-INTEL OSINT Dashboard API initialized.")


# ==================== Request Schemas ====================

class RunPipelineRequest(BaseModel):
    stage: str = Field(default="all", description="Pipeline stage: all, ingest, select, agents, synthesize")
    date: Optional[str] = Field(default=None, description="Optional target date YYYY-MM-DD (Europe/Bucharest)")
    target_date: Optional[str] = Field(default=None, description="Optional target date alias YYYY-MM-DD (Europe/Bucharest)")
    dossier: str = Field(default="dossier_for_agent_1.txt", description="Dossier output path")


# ==================== Dashboard & Status Endpoints ====================

@app.get("/", response_class=HTMLResponse)
async def serve_index() -> HTMLResponse:
    """Serve the single-page executive intelligence dashboard."""
    index_file = TEMPLATES_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse(
            "<h1>RO-INTEL Platform Loading...</h1><p>Please refresh in a moment while templates initialize.</p>"
        )
    return HTMLResponse(content=index_file.read_text(encoding="utf-8"))


@app.get("/api/status")
async def get_system_status() -> Dict[str, Any]:
    """Retrieve full platform health, database counters, Ollama details, and execution status."""
    settings = get_settings()
    db = DBManager()

    # 1. Database counters
    stats = db.get_dashboard_stats()

    # 2. Ollama Health & Model Verification
    ollama_status = {
        "healthy": False,
        "base_url": settings.ollama_base_url,
        "active_model": settings.ollama_model,
        "embedding_model": settings.ollama_embed_model,
        "num_ctx": settings.num_ctx,
        "available_models": []
    }
    try:
        req = urllib.request.Request(f"{settings.ollama_base_url}/api/tags")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name") for m in data.get("models", [])]
                ollama_status["healthy"] = True
                ollama_status["available_models"] = models
    except Exception as e:
        ollama_status["error"] = str(e)

    # 3. Vector Store Health
    vector_status = {"healthy": False, "count": 0}
    try:
        vstore = VectorStore()
        vector_status["healthy"] = True
        vector_status["count"] = vstore.collection.count()
    except Exception as e:
        vector_status["error"] = str(e)

    # 4. Pipeline Execution State
    exec_state = pipeline_manager.get_state()

    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "today_bucharest": get_bucharest_today_str(),
        "database": stats,
        "ollama": ollama_status,
        "vector_store": vector_status,
        "pipeline": exec_state
    }


# ==================== Database Viewer APIs ====================

@app.get("/api/db/tables")
async def get_db_tables() -> List[Dict[str, Any]]:
    """List all whitelisted tables, row counts, and column metadata (read-only)."""
    db = DBManager()
    return db.get_db_tables()


@app.get("/api/db/schema")
async def get_db_schema() -> Dict[str, Any]:
    """Retrieve database schema summary (read-only)."""
    db = DBManager()
    return db.get_schema_summary()


@app.get("/api/db/tables/{table}/rows")
async def get_table_rows(
    table: str,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    sort: Optional[str] = Query(default=None),
    order: str = Query(default="DESC"),
    q: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None)
) -> Dict[str, Any]:
    """Retrieve paginated, sorted, and filtered rows from a database table (read-only)."""
    db = DBManager()
    try:
        return db.get_table_rows(
            table=table,
            limit=limit,
            offset=offset,
            sort=sort,
            order=order,
            q=q,
            date_from=date_from,
            date_to=date_to
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))


@app.get("/api/db/tables/{table}/rows/{id}")
async def get_table_row(table: str, id: int) -> Dict[str, Any]:
    """Retrieve a single table record by primary key (read-only)."""
    db = DBManager()
    try:
        row = db.get_table_row(table=table, row_id=id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Row ID {id} not found in '{table}'.")
        return row
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))


@app.get("/api/db/export/{table}.csv")
async def export_table_csv(table: str) -> Response:
    """Export all rows from a database table as a CSV download (read-only)."""
    db = DBManager()
    try:
        csv_data = db.export_table_csv(table)
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={table}.csv"}
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))


# ==================== Connected Papers Graph API ====================

def compute_cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two numeric vectors."""
    dot = sum(x * y for x, y in zip(v1, v2))
    norm1 = math.sqrt(sum(x * x for x in v1))
    norm2 = math.sqrt(sum(x * x for x in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


@app.get("/api/db/graph")
async def get_db_graph(
    mode: str = Query(default="similarity", pattern="^(similarity|actors|articles)$"),
    min_similarity: float = Query(default=0.62, ge=0.2, le=0.99),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    limit: int = Query(default=150, ge=10, le=500)
) -> Dict[str, Any]:
    """Return Connected Papers-style relational and semantic graph data."""
    db = DBManager()
    threats = db.get_latest_threats(limit=100)
    anomalies = db.get_latest_anomalies(limit=100)

    # Map threats and anomalies by actor for enrichment
    threat_actor_map: Dict[str, int] = {}
    for t in threats:
        v = (t.get("vulnerable_actor") or "").lower()
        e = (t.get("exploiting_actor") or "").lower()
        if v:
            threat_actor_map[v] = threat_actor_map.get(v, 0) + 1
        if e:
            threat_actor_map[e] = threat_actor_map.get(e, 0) + 1

    anomaly_actor_map: Dict[str, float] = {}
    for a in anomalies:
        tgt = (a.get("target") or "").lower()
        score = float(a.get("contradiction_score") or 0.0)
        if tgt:
            anomaly_actor_map[tgt] = max(anomaly_actor_map.get(tgt, 0.0), score)

    # 1. Similarity mode (ChromaDB + nomic-embed-text)
    if mode == "similarity":
        try:
            vstore = VectorStore()
            chroma_data = vstore.get_all_with_embeddings(limit=limit)
            raw_ids = chroma_data.get("ids")
            emb_ids = raw_ids if (raw_ids is not None and len(raw_ids) > 0) else []
            raw_embs = chroma_data.get("embeddings")
            embeddings = raw_embs if (raw_embs is not None and len(raw_embs) > 0) else []
            raw_meta = chroma_data.get("metadatas")
            metadatas = raw_meta if (raw_meta is not None and len(raw_meta) > 0) else []

            # If ChromaDB has data, build semantic similarity graph
            if len(emb_ids) >= 2 and len(embeddings) >= 2:
                nodes = []
                for i, node_id in enumerate(emb_ids):
                    meta = metadatas[i] if i < len(metadatas) else {}
                    actor = meta.get("actor") or "Unknown"
                    topic = meta.get("topic") or "General"
                    action = meta.get("action") or ""
                    quote = meta.get("verbatim_evidence") or ""
                    ext_at = meta.get("extracted_at") or ""
                    date_str = ext_at[:10] if ext_at else get_bucharest_today_str()

                    actor_lower = actor.lower()
                    nodes.append({
                        "id": str(node_id),
                        "label": f"{actor}: {action[:38]}..." if len(action) > 38 else f"{actor}: {action}",
                        "actor": actor,
                        "topic": topic,
                        "action": action,
                        "quote": quote,
                        "date": date_str,
                        "source": meta.get("source") or "Feed Monitor",
                        "threat_count": threat_actor_map.get(actor_lower, 0),
                        "contradiction_score": anomaly_actor_map.get(actor_lower, 0.0),
                        "kind": "event"
                    })

                # Vectorized similarity calculation via NumPy
                matrix = np.array(embeddings, dtype=np.float32)
                norms = np.linalg.norm(matrix, axis=1, keepdims=True)
                norm_matrix = matrix / np.maximum(norms, 1e-9)
                sim_matrix = np.dot(norm_matrix, norm_matrix.T)

                edges = []
                degree_map = {n["id"]: 0 for n in nodes}
                n_nodes = len(nodes)
                triu_i, triu_j = np.triu_indices(n_nodes, k=1)
                mask = sim_matrix[triu_i, triu_j] >= min_similarity
                for i, j in zip(triu_i[mask], triu_j[mask]):
                    sim = float(sim_matrix[i, j])
                    source_id = nodes[i]["id"]
                    target_id = nodes[j]["id"]
                    edges.append({
                        "source": source_id,
                        "target": target_id,
                        "kind": "similarity",
                        "weight": round(sim, 3),
                        "label": f"{int(round(sim * 100))}% similaritate"
                    })
                    degree_map[source_id] = degree_map.get(source_id, 0) + 1
                    degree_map[target_id] = degree_map.get(target_id, 0) + 1

                for n in nodes:
                    n["weight"] = degree_map.get(n["id"], 0)

                return {
                    "mode": "similarity",
                    "meta": {
                        "node_count": len(nodes),
                        "edge_count": len(edges),
                        "embedding_model": "nomic-embed-text",
                        "min_similarity": min_similarity,
                        "fallback_used": False
                    },
                    "nodes": nodes,
                    "edges": edges
                }
            elif len(emb_ids) == 1:
                meta = metadatas[0] if len(metadatas) > 0 else {}
                actor = meta.get("actor") or "Unknown"
                action = meta.get("action") or ""
                return {
                    "mode": "similarity",
                    "meta": {
                        "node_count": 1,
                        "edge_count": 0,
                        "embedding_model": "nomic-embed-text",
                        "min_similarity": min_similarity,
                        "fallback_used": False
                    },
                    "nodes": [{
                        "id": str(emb_ids[0]),
                        "label": f"{actor}: {action[:38]}..." if len(action) > 38 else f"{actor}: {action}",
                        "actor": actor,
                        "topic": meta.get("topic") or "General",
                        "action": action,
                        "quote": meta.get("verbatim_evidence") or "",
                        "date": get_bucharest_today_str(),
                        "source": meta.get("source") or "Feed Monitor",
                        "threat_count": 0,
                        "contradiction_score": 0.0,
                        "kind": "event",
                        "weight": 1
                    }],
                    "edges": []
                }
            return {
                "mode": "similarity",
                "meta": {
                    "node_count": 0,
                    "edge_count": 0,
                    "embedding_model": "nomic-embed-text",
                    "min_similarity": min_similarity,
                    "fallback_used": True
                },
                "nodes": [],
                "edges": []
            }
        except Exception as e:
            logger.warning("Error computing semantic similarity graph: %s", e)
            return {
                "mode": "similarity",
                "meta": {
                    "node_count": 0,
                    "edge_count": 0,
                    "embedding_model": "nomic-embed-text",
                    "min_similarity": min_similarity,
                    "error": str(e),
                    "fallback_used": True
                },
                "nodes": [],
                "edges": []
            }

    # 2. Actors & Power Vectors Mode
    if mode == "actors":
        events_resp = db.get_table_rows("extracted_events", limit=limit, date_from=date_from, date_to=date_to)
        events_rows = events_resp.get("rows", [])

        actors_set = set()
        topics_set = set()
        actor_topic_pairs = []

        for row in events_rows:
            actor = row.get("canonical_actor") or row.get("actor")
            topic = row.get("topic")
            if actor:
                actors_set.add(actor)
            if topic:
                topics_set.add(topic)
            if actor and topic:
                actor_topic_pairs.append((actor, topic))

        nodes = []
        for a in sorted(actors_set):
            a_lower = a.lower()
            nodes.append({
                "id": f"actor:{a}",
                "label": a,
                "actor": a,
                "kind": "actor",
                "threat_count": threat_actor_map.get(a_lower, 0),
                "contradiction_score": anomaly_actor_map.get(a_lower, 0.0),
                "weight": 2
            })

        for t in sorted(topics_set):
            nodes.append({
                "id": f"topic:{t}",
                "label": t,
                "topic": t,
                "kind": "topic",
                "threat_count": 0,
                "contradiction_score": 0.0,
                "weight": 1
            })

        edges = []
        # Actor - Topic edges
        for a, t in actor_topic_pairs:
            edges.append({
                "source": f"actor:{a}",
                "target": f"topic:{t}",
                "kind": "topic_affinity",
                "weight": 1.0,
                "label": "domeniu de interes"
            })

        # Red Team Threat edges (exploiting -> vulnerable)
        node_id_set = {n["id"] for n in nodes}
        for thr in threats:
            vuln = thr.get("vulnerable_actor")
            expl = thr.get("exploiting_actor")
            if vuln and expl:
                vuln_id = f"actor:{vuln}"
                expl_id = f"actor:{expl}"

                # Ensure threat actors exist as nodes even if not in extracted_events
                if vuln_id not in node_id_set:
                    nodes.append({
                        "id": vuln_id,
                        "label": vuln,
                        "actor": vuln,
                        "kind": "actor",
                        "threat_count": threat_actor_map.get(vuln.lower(), 1),
                        "contradiction_score": anomaly_actor_map.get(vuln.lower(), 0.0),
                        "weight": 2
                    })
                    node_id_set.add(vuln_id)

                if expl_id not in node_id_set:
                    nodes.append({
                        "id": expl_id,
                        "label": expl,
                        "actor": expl,
                        "kind": "actor",
                        "threat_count": threat_actor_map.get(expl.lower(), 0),
                        "contradiction_score": anomaly_actor_map.get(expl.lower(), 0.0),
                        "weight": 2
                    })
                    node_id_set.add(expl_id)

                edges.append({
                    "source": expl_id,
                    "target": vuln_id,
                    "kind": "threat",
                    "weight": 2.0,
                    "label": thr.get("threat_type") or "Vulnerabilitate tactică",
                    "description": thr.get("description") or ""
                })

        return {
            "mode": "actors",
            "meta": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "min_similarity": min_similarity,
                "fallback_used": False
            },
            "nodes": nodes,
            "edges": edges
        }

    # 3. Fallback or Articles Mode
    arts = db.get_latest_articles(limit=min(limit, 80))
    nodes = []
    for art in arts:
        nodes.append({
            "id": f"art:{art.get('id')}",
            "label": (art.get("title") or "")[:40] + "...",
            "title": art.get("title", ""),
            "source": art.get("source", ""),
            "link": art.get("link", ""),
            "date": art.get("published_date") or get_bucharest_today_str(),
            "kind": "article",
            "weight": 1
        })

    edges = []
    for i in range(len(nodes)):
        for j in range(i + 1, min(i + 6, len(nodes))):
            same_source = (nodes[i]["source"] == nodes[j]["source"] and nodes[i]["source"] != "")
            edges.append({
                "source": nodes[i]["id"],
                "target": nodes[j]["id"],
                "kind": "source_cluster" if same_source else "news_flow",
                "weight": 0.7 if same_source else 0.4,
                "label": nodes[i]["source"] if same_source else "flux conex"
            })

    return {
        "mode": mode,
        "meta": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "min_similarity": min_similarity,
            "fallback_used": True
        },
        "nodes": nodes,
        "edges": edges
    }


# ==================== Reports APIs ====================

@app.get("/api/reports")
async def list_reports() -> List[Dict[str, Any]]:
    """List available daily political intelligence briefings from reports/ directory."""
    reports = []
    for file_path in REPORTS_DIR.glob("Sinteza_Politica_*.md"):
        try:
            stat = file_path.stat()
            date_part = file_path.stem.replace("Sinteza_Politica_", "")
            reports.append({
                "filename": file_path.name,
                "date": date_part,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            })
        except Exception:
            pass

    # Also check BASE_DIR for any legacy reports
    for file_path in BASE_DIR.glob("Sinteza_Politica_*.md"):
        try:
            date_part = file_path.stem.replace("Sinteza_Politica_", "")
            if not any(r["filename"] == file_path.name for r in reports):
                stat = file_path.stat()
                reports.append({
                    "filename": file_path.name,
                    "date": date_part,
                    "size_bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                })
        except Exception:
            pass

    reports.sort(key=lambda r: r["date"], reverse=True)
    return reports


@app.get("/api/reports/{filename}")
async def get_report_content(filename: str) -> Dict[str, Any]:
    """Retrieve raw markdown content of a specific political briefing from reports/."""
    if not filename.startswith("Sinteza_Politica_") or not filename.endswith(".md"):
        raise HTTPException(status_code=400, detail="Invalid report filename.")

    # Check reports/ first, then fall back to BASE_DIR
    file_path = (REPORTS_DIR / filename).resolve()
    if not file_path.exists():
        file_path = (BASE_DIR / filename).resolve()

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Report not found.")

    content = file_path.read_text(encoding="utf-8")
    return {
        "filename": filename,
        "content": content
    }


# ==================== Dashboard Metrics & Feeds ====================

@app.get("/api/anomalies")
async def get_anomalies(limit: int = 50) -> List[Dict[str, Any]]:
    """Get detected historical contradictions and political flip-flops."""
    db = DBManager()
    return db.get_latest_anomalies(limit=limit)


@app.get("/api/threats")
async def get_threats(limit: int = 50) -> List[Dict[str, Any]]:
    """Get hostile actor threat vectors identified by Red Team."""
    db = DBManager()
    return db.get_latest_threats(limit=limit)


@app.get("/api/articles")
async def get_articles(limit: int = 30) -> List[Dict[str, Any]]:
    """Get recently ingested raw news articles."""
    db = DBManager()
    return db.get_latest_articles(limit=limit)


@app.get("/api/executions")
async def get_executions(limit: int = 20) -> List[Dict[str, Any]]:
    """Get recent pipeline executions audit log."""
    db = DBManager()
    return db.get_latest_executions(limit=limit)


# ==================== Pipeline Execution Triggers & Cancellation ====================

@app.post("/api/run")
async def trigger_pipeline_run(payload: RunPipelineRequest) -> Dict[str, Any]:
    """Trigger an asynchronous, non-blocking pipeline execution."""
    target_dt = payload.target_date or payload.date
    run_id = pipeline_manager.start_run(
        stage=payload.stage,
        target_date=target_dt,
        dossier_path=payload.dossier
    )
    return {
        "status": "started",
        "run_id": run_id,
        "stage": payload.stage,
        "target_date": pipeline_manager.target_date,
        "message": f"Execution {run_id} initiated asynchronously."
    }


@app.post("/api/run/cancel")
async def cancel_pipeline_run() -> Dict[str, Any]:
    """Request cooperative cancellation of the active pipeline run."""
    if not pipeline_manager.is_running:
        return {
            "status": "idle",
            "message": "No pipeline execution currently in progress."
        }

    event_bus.request_cancellation()
    with pipeline_manager._lock:
        pipeline_manager.status_message = "Cancellation requested..."

    event_bus.publish(
        event_type="stage",
        text="Cancellation signal requested by user",
        agent="pipeline",
        run_id=pipeline_manager.run_id or "",
        data={"status": "CANCELLING"}
    )

    return {
        "status": "cancelling",
        "run_id": pipeline_manager.run_id,
        "message": "Cancellation request dispatched to pipeline."
    }


class PurgeRequest(BaseModel):
    delete_db: bool = Field(True, description="Purge SQLite tables")
    delete_chroma: bool = Field(True, description="Purge ChromaDB vector collection")
    delete_reports: bool = Field(True, description="Purge reports directory")


@app.post("/api/system/purge")
@app.delete("/api/system/purge")
async def purge_system_data(payload: Optional[PurgeRequest] = None) -> Dict[str, Any]:
    """Purge both SQLite & ChromaDB databases and all generated markdown reports."""
    delete_db = payload.delete_db if payload else True
    delete_chroma = payload.delete_chroma if payload else True
    delete_reports = payload.delete_reports if payload else True

    deleted_counts: Dict[str, Any] = {}

    # 1. Purge SQLite
    if delete_db:
        db = DBManager()
        deleted_counts["sqlite"] = db.purge_all_data()

    # 2. Purge ChromaDB
    if delete_chroma:
        try:
            vstore = VectorStore()
            deleted_counts["chromadb_vectors"] = vstore.purge()
        except Exception as e:
            logger.error("Error purging ChromaDB: %s", e)
            deleted_counts["chromadb_vectors"] = 0

    # 3. Purge reports
    if delete_reports:
        deleted_reports = []
        if REPORTS_DIR.exists():
            for report_file in REPORTS_DIR.iterdir():
                if report_file.is_file():
                    try:
                        name = report_file.name
                        report_file.unlink()
                        deleted_reports.append(name)
                    except Exception as e:
                        logger.warning("Error deleting report file %s: %s", report_file, e)
        deleted_counts["reports"] = deleted_reports

    # Clear press dossier file if it exists
    dossier_file = BASE_DIR / "dossier_for_agent_1.txt"
    if dossier_file.exists():
        try:
            dossier_file.unlink()
            deleted_counts["dossier_cleared"] = True
        except Exception:
            pass

    logger.info("System purge executed: %s", deleted_counts)
    return {
        "status": "success",
        "message": "Ambele baze de date (SQLite & ChromaDB) și toate rapoartele au fost șterse cu succes.",
        "details": deleted_counts,
        "timestamp": datetime.now().isoformat()
    }


# ==================== Real-Time Server-Sent Events (SSE) ====================

@app.get("/api/stream")
async def stream_live_events(request: Request) -> StreamingResponse:
    """Stream live model thinking, content tokens, stage transitions, and log events.

    Supports Last-Event-ID header for automatic message replay across reconnects.
    """
    last_event_id_header = request.headers.get("last-event-id")
    last_event_id: Optional[int] = None
    if last_event_id_header and last_event_id_header.isdigit():
        last_event_id = int(last_event_id_header)

    queue = event_bus.subscribe(last_event_id=last_event_id)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # If no Last-Event-ID was supplied, send the last 20 events for context
            if last_event_id is None:
                history = event_bus.get_history(limit=25)
                for ev in history:
                    yield ev.to_sse_message()

            while True:
                if await request.is_disconnected():
                    break
                try:
                    event: Event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield event.to_sse_message()
                except asyncio.TimeoutError:
                    # SSE Keep-alive heartbeat ping
                    yield ": ping\n\n"
        finally:
            event_bus.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.post("/api/test/stream")
async def trigger_test_stream(background_tasks: BackgroundTasks) -> Dict[str, str]:
    """Trigger a quick test streaming generation with thinking tokens for smoke verification."""
    def _run() -> None:
        event_bus.publish(event_type="stage", text="Extracție fapte politice în curs", agent="extractor", run_id="smoke_test_run", data={"stage": "extract", "status": "running"})
        event_bus.publish(event_type="agent_start", text="Agent 1: Extractor Entități inițiat", agent="extractor", run_id="smoke_test_run")
        event_bus.publish(event_type="log", text="Agent 1 a primit dosarul de presă pentru procesare", agent="extractor", run_id="smoke_test_run", data={"level": "INFO"})
        client = OllamaClient()
        client.generate(
            system_prompt="Ești un analist politic senior.",
            user_prompt="Explică pe scurt transparența decizională în administrație și motivează alegerea termenilor.",
            stream=True,
            agent_name="extractor",
            run_id="smoke_test_run"
        )
        event_bus.publish(event_type="agent_end", text="Agent 1 finalizat", agent="extractor", run_id="smoke_test_run", data={"duration_s": 3.4})
        event_bus.publish(event_type="stage", text="Extracție finalizată", agent="extractor", run_id="smoke_test_run", data={"stage": "extract", "status": "completed"})
    background_tasks.add_task(_run)
    return {"status": "started", "message": "Test streaming background task started."}
