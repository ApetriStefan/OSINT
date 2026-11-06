# Storage & Memory Architecture

> **Summary:** Technical specification of the persistence and memory tier: SQLite in Write-Ahead Logging (WAL) mode, deterministic event deduplication, and ChromaDB vector store with nomic-embed-text embeddings.

**Status:** 🟩 Stable  
**Owner role:** Data Engineer (link to [ownership-map.md](../team_and_stakeholders/ownership-map.md))  
**Last updated:** 2026-11-06  

---

## Table of Contents

- [Overview](#overview)
- [Relational Tier: SQLite with WAL Mode](#relational-tier-sqlite-with-wal-mode)
- [Database Schema & Table Contracts](#database-schema--table-contracts)
- [Deduplication & Data Integrity](#deduplication--data-integrity)
- [Read-Only Database Viewer Engine](#read-only-database-viewer-engine)
- [Vector Tier: ChromaDB & Local Embeddings](#vector-tier-chromadb--local-embeddings)
- [System Purge & Zero-Artifact Reset](#system-purge--zero-artifact-reset)
- [Component-Specific Decisions & Trade-offs](#component-specific-decisions--trade-offs)
- [Operational Notes](#operational-notes)
- [Appendix: Key Code Locations](#appendix-key-code-locations)

---

## Overview

The storage layer ([`src/storage/`](file:///d:/OSINT/src/storage/)) combines relational ACID storage with high-dimensional vector search to provide complete historical recall for intelligence analysis. Relational state, raw feeds, extracted events, contradictions, and pipeline executions are managed via SQLite in WAL mode, while semantic representations are maintained in ChromaDB using local 768-dimensional embeddings.

---

## Relational Tier: SQLite with WAL Mode

Implemented in [`src/storage/db_manager.py`](file:///d:/OSINT/src/storage/db_manager.py) via `DBManager`:

### Concurrency & WAL Configuration
By default, SQLite locks the entire database during write transactions. To ensure that background pipeline runs do not block the UI dashboard or API readers, all connections enable:
```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;
```
- **Write-Ahead Logging (WAL):** Allows concurrent readers to query tables simultaneously while a writer thread inserts articles or updates stage statuses.
- **Synchronous = NORMAL:** Reduces disk flush overhead while guaranteeing database integrity across process crashes.

### Strict Read-Only Connection Pool
For web queries, table inspections, and CSV exports, `DBManager.get_readonly_connection()` opens connections using SQLite's read-only URI mode:
```python
uri = f"file:{abs_path}?mode=ro"
conn = sqlite3.connect(uri, uri=True, timeout=15.0)
```
This guarantees that UI endpoints can never inadvertently mutate or corrupt operational data.

---

## Database Schema & Table Contracts

```
┌─────────────────┐       ┌──────────────────────┐
│  raw_articles   │◄──────┤   extracted_events   │
│  (link: UNIQUE) │ 1   * │ (event_hash: UNIQUE) │
└─────────────────┘       └──────────────────────┘
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         ▼                                                       ▼
┌──────────────────────┐                               ┌────────────────────┐
│ historical_anomalies │                               │   threat_vectors   │
│ (contradiction score)│                               │ (hostile vectors)  │
└──────────────────────┘                               └────────────────────┘
```

### Table 1: `raw_articles`
Stores raw news articles scraped from RSS feeds:
- `id`: INTEGER PRIMARY KEY AUTOINCREMENT
- `source_name`: TEXT NOT NULL
- `title`: TEXT NOT NULL
- `link`: TEXT UNIQUE NOT NULL
- `summary`: TEXT
- `published_at`: TEXT (ISO-8601 UTC)
- `published_date`: TEXT (Europe/Bucharest YYYY-MM-DD)
- `is_date_estimated`: INTEGER DEFAULT 0
- `scraped_at`: TIMESTAMP DEFAULT CURRENT_TIMESTAMP

### Table 2: `extracted_events`
Stores structured political actions and verbatim quotes extracted by Agent 1:
- `id`: INTEGER PRIMARY KEY AUTOINCREMENT
- `article_id`: INTEGER (FOREIGN KEY referencing `raw_articles(id)` ON DELETE SET NULL)
- `actor`: TEXT NOT NULL
- `canonical_actor`: TEXT
- `action`: TEXT NOT NULL
- `verbatim_evidence`: TEXT NOT NULL
- `topic`: TEXT NOT NULL
- `event_hash`: TEXT (UNIQUE index)
- `extracted_at`: TIMESTAMP DEFAULT CURRENT_TIMESTAMP

### Table 3: `historical_anomalies`
Stores political contradictions and flip-flops identified by Agent 2:
- `id`: INTEGER PRIMARY KEY AUTOINCREMENT
- `anomaly_type`: TEXT NOT NULL
- `target`: TEXT NOT NULL
- `past_statement`: TEXT NOT NULL
- `current_statement`: TEXT NOT NULL
- `contradiction_score`: REAL NOT NULL (0.0 to 1.0)
- `analyst_note`: TEXT NOT NULL
- `detected_at`: TIMESTAMP DEFAULT CURRENT_TIMESTAMP

### Table 4: `threat_vectors`
Stores hostile strategy vectors and parasitic framing identified by Agent 3:
- `id`: INTEGER PRIMARY KEY AUTOINCREMENT
- `threat_type`: TEXT NOT NULL
- `vulnerable_actor`: TEXT NOT NULL
- `exploiting_actor`: TEXT NOT NULL
- `description`: TEXT NOT NULL
- `detected_at`: TIMESTAMP DEFAULT CURRENT_TIMESTAMP

### Table 5: `pipeline_executions`
Auditable state machine tracking pipeline runs:
- `id`: INTEGER PRIMARY KEY AUTOINCREMENT
- `run_id`: TEXT UNIQUE NOT NULL
- `stage`: TEXT NOT NULL
- `status`: TEXT NOT NULL (`STARTED`, `COMPLETED`, `FAILED`, `CANCELLED`)
- `details`: TEXT
- `created_at`: TIMESTAMP DEFAULT CURRENT_TIMESTAMP
- `updated_at`: TIMESTAMP DEFAULT CURRENT_TIMESTAMP

---

## Deduplication & Data Integrity

1. **Raw Article Deduplication:**
   Enforced via `link TEXT UNIQUE NOT NULL`. Ingestion uses `INSERT OR IGNORE`, ensuring identical RSS items are ignored across repeated ingestion runs.
2. **Extracted Event Deduplication:**
   Agent 1 calculates a deterministic SHA-256 hash across canonical actor, action, and verbatim quote. Enforced in SQLite by:
   ```sql
   CREATE UNIQUE INDEX IF NOT EXISTS idx_extracted_events_hash 
   ON extracted_events(event_hash) WHERE event_hash IS NOT NULL;
   ```
3. **Automated Schema Migrations:**
   On startup, `DBManager.init_db()` queries `PRAGMA table_info()` and safely runs non-destructive `ALTER TABLE ADD COLUMN` statements if schema updates are detected.

---

## Read-Only Database Viewer Engine

`DBManager` provides secure, parameterized query handlers consumed by the web UI:
- `get_db_tables()`: Returns whitelisted table names, row counts, and column metadata.
- `get_table_rows()`: Executes paginated SQL queries with configurable limits (capped at 500), ascending/descending sorting, text searching across string columns (`LIKE %q%`), and date range filtering (`date_from`, `date_to`).
- `get_table_row()`: Retrieves a single record by primary key.
- `export_table_csv()`: Streams full table exports as valid CSV strings.
- `get_schema_summary()`: Produces structured JSON descriptions of database tables.

---

## Vector Tier: ChromaDB & Local Embeddings

Implemented in [`src/storage/vector_store.py`](file:///d:/OSINT/src/storage/vector_store.py) via `VectorStore`:

### Vector Engine & Embedding Model
- **Engine:** `chromadb.PersistentClient` storing data in `chroma_db/`.
- **Collection:** `political_events`.
- **Model:** Local Ollama `nomic-embed-text` producing 768-dimensional dense vector embeddings.
- **Batch Embedding Acceleration:** Implements `get_embeddings_batch()`, utilizing Ollama's `/api/embed` endpoint to embed all daily events in a single batch call, falling back to individual `/api/embeddings` calls only if batching is unavailable.

### Semantic Search & Actor Filtering
`VectorStore.search_events()` converts query text into an embedding and performs nearest-neighbor search, supporting metadata filters:
```python
results = self.collection.query(
    query_embeddings=[query_emb],
    n_results=5,
    where={"actor": canonical_actor}
)
```

---

## System Purge & Zero-Artifact Reset

The storage layer supports complete operational purging via `DBManager.purge_all_data()` and `VectorStore.purge()`:
1. Deletes records from SQLite child tables first (`threat_vectors`, `historical_anomalies`, `extracted_events`, `raw_articles`, `pipeline_executions`).
2. Resets `sqlite_sequence` counters.
3. Executes `VACUUM` to reclaim disk space.
4. Deletes and recreates the ChromaDB collection.
5. Deletes generated report files from `reports/`.

---

## Component-Specific Decisions & Trade-offs

1. **Decoupled Embedding Model (`nomic-embed-text`):**
   - *Decision:* Embeddings are computed with `nomic-embed-text` rather than passing the primary LLM (`gemma-4-e4b`) to ChromaDB.
   - *Rationale:* Decoupling avoids Ollama HTTP 500 endpoint errors and significantly accelerates semantic retrieval.
2. **Partial Unique Indexes:**
   - *Decision:* `CREATE UNIQUE INDEX ... WHERE event_hash IS NOT NULL`.
   - *Rationale:* Allows legacy or external rows without hashes while guaranteeing strict deduplication for all new extractions.

---

## Operational Notes

- **Database File:** Located at `political_intel.db` by default (configurable via `.env`).
- **Vector Directory:** Located at `chroma_db/` by default.
- **Integration Tested:** Verified under `tests/integration/test_db_manager.py`, `tests/integration/test_vector_store.py`, and `tests/integration/test_purge.py`.

---

## Appendix: Key Code Locations

- `src/storage/db_manager.py` — SQLite WAL manager, schema definition, and viewer APIs
- `src/storage/vector_store.py` — ChromaDB vector store and nomic-embed-text embedding client
- `tests/integration/test_db_manager.py` — SQLite unit and integration tests
- `tests/integration/test_vector_store.py` — ChromaDB embedding and search tests

---

_Generated by Kipi — Core-Knowledge Keeper_
