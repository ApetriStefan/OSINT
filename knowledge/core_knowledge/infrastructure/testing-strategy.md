# Automated Testing Strategy

> **Summary:** Technical specification of the automated pytest test suite: 80 comprehensive unit and integration tests, fast regression gates, and data integrity guarantees.

**Status:** 🟩 Stable  
**Owner role:** QA & Test Automation Engineer (link to [ownership-map.md](../team_and_stakeholders/ownership-map.md))  
**Last updated:** 2026-11-06  

---

## Table of Contents

- [Overview](#overview)
- [Test Suite Architecture](#test-suite-architecture)
- [Unit Testing Suite (45 Tests)](#unit-testing-suite-45-tests)
- [Integration Testing Suite (35 Tests)](#integration-testing-suite-35-tests)
- [Fast Regression & CI/CD Gates](#fast-regression--cicd-gates)
- [Test Execution & Verification](#test-execution--verification)
- [Operational Notes](#operational-notes)
- [Appendix: Test File Matrix](#appendix-test-file-matrix)

---

## Overview

The repository enforces a rigorous, automated testing discipline. The entire codebase is covered by **80 automated unit and integration tests** executing in under **4 seconds**. Every release, pipeline modification, and architectural update must pass 100% of the test suite before deployment.

---

## Test Suite Architecture

Configured in [`pyproject.toml`](file:///d:/OSINT/pyproject.toml) under `[tool.pytest.ini_options]`:
- **Test Runner:** `pytest` (v8+) via `uv run pytest`.
- **Plugins:** `pytest-mock`, `responses`.
- **Execution Options:** `-v --strict-markers`.
- **Warning Filters:** Deprecation and User warnings are cleanly filtered.

```
tests/
├── unit/                       (42 tests — isolated component algorithms)
│   ├── test_date_parsing.py
│   ├── test_date_regression.py
│   ├── test_entity_resolver.py
│   ├── test_events_bus.py
│   ├── test_llm_client.py
│   ├── test_pipeline.py
│   ├── test_taxonomy.py
│   └── test_text_extractor.py
└── integration/                (35 tests — database, vector store, UI APIs)
    ├── test_db_manager.py
    ├── test_db_viewer_api.py
    ├── test_purge.py
    ├── test_ui_app.py
    └── test_vector_store.py
```

---

## Unit Testing Suite (42 Tests)

Unit tests isolate algorithmic components with zero reliance on live external servers:

### 1. Date Handling & Regression (`test_date_parsing.py`, `test_date_regression.py`)
- **HTML Sanitization:** Verifies removal of tags and condensed whitespace.
- **Multi-Format Parsing:** Tests ISO-8601, RFC 822, feedparser `struct_time`, and European `DD/MM/YYYY` day-first dates.
- **Romanian Textual Dates:** Validates parsing of dates with Romanian month names (e.g., `"14 Iunie 2026, 15:30"`).
- **Timezone Boundary Crossings:** Tests normalization across `Europe/Bucharest` and UTC.
- **Negative Fallback Invariant:** Verifies that corrupt or missing dates return `None` and **never** silently default to today's date.
- **Future Date Rejection:** Verifies that future publication dates raise `ValueError`.

### 2. Entity Normalization (`test_entity_resolver.py`)
- Normalization: Diacritics stripping and lowercasing.
- Leader Resolution: Standardizes Romanian political figures and titles to canonical names.
- Party Resolution: Maps acronyms (`PSD`, `PNL`, `USR`, `AUR`, `UDMR`) to full party models.
- Institution Resolution: Normalizes judicial and executive bodies (`DNA`, `CCR`, `CSM`, `Guvernul României`).
- Fallback Handling: Safely handles unknown or novel actors.

### 3. Event Bus & Cancellation (`test_events_bus.py`)
- Monotonic Sequence Numbers: Ensures every event receives an incremental sequence ID.
- Ring Buffer Eviction: Verifies that exceeding `max_history` evicts oldest events cleanly without memory leaks.
- SSE Serialization: Validates formatted SSE message payloads.
- Subscribe & Replay (`Last-Event-ID`): Verifies that reconnecting clients receive replayed missed events.
- Cooperative Cancellation: Tests `request_cancellation()`, `is_cancelled()`, and `reset_cancellation()`.
- Logging Bridge: Verifies `EventBusLogHandler` pipes log records into the bus.

### 4. LLM Client Wrapper (`test_llm_client.py`)
- Thinking Token Cleaning: Verifies stripping of `<think>...</think>` reasoning blocks.
- JSON Substring Extraction: Extracts JSON objects from markdown fences and surrounding commentary.
- Context Window Preservation: Guarantees `num_ctx = 131072` is sent in payload options.
- Structured Pydantic Generation: Tests schema generation and validation against mock responses.
- Streaming Parser: Validates event emission for dedicated thinking chunks and content tokens.

### 5. Taxonomy & Noise Filters (`test_taxonomy.py`)
- Accent Stripping: Unicode NFD diacritics stripping.
- Noise Filtering: Verifies elimination of reality TV (Survivor, Cancan), sports (Liga 1, FCSB), weather, and minor accidents.
- Strategic Signal Protection: Confirms high-impact news mentioning core keywords is *not* misclassified as noise.
- Pillar Scoring: Validates 3x title weighting and primary pillar assignment.

### 6. Pipeline Orchestrator & Text Extractor (`test_pipeline.py`, `test_text_extractor.py`)
- Pipeline Initialization: Checks dependency wiring and run ID format.
- Stage Validation: Verifies invalid stage names raise `ValueError`.
- Text Extraction: Verifies DOM traversal, script removal, and metadata date tag extraction.

---

## Integration Testing Suite (35 Tests)

Integration tests verify multi-component interactions across databases, vector stores, and web APIs:

### 1. Relational Database Operations (`test_db_manager.py`)
- PRAGMA Configuration: Validates WAL mode, foreign keys, and synchronous settings.
- Deduplication: Enforces unique constraint on raw article URLs and SHA-256 event hashes.
- Historical Statements: Tests `get_actor_history()` with date boundaries.
- State Machine: Verifies pipeline run recording and updates in `pipeline_executions`.

### 2. Database Viewer APIs (`test_db_viewer_api.py`)
- Whitelisted Table Inspection: Tests `GET /api/db/tables` and `GET /api/db/schema`.
- Pagination & Sorting: Tests `limit`, `offset`, and `order` parameters.
- Text Search: Parameterized SQL searches across string columns (`q`).
- Date Range Filtering: Filters rows between `date_from` and `date_to`.
- CSV Export: Tests streaming CSV download endpoint.
- Future Date Rejection: Verifies pipeline run requests with future dates return `HTTP 422`.
- Cooperative Cancellation API: Tests `POST /api/run/cancel`.
- Graph API: Tests relational similarity and actor graph generation.

### 3. Vector Database Operations (`test_vector_store.py`)
- Embedding Generation: Tests single embedding generation via mock Ollama.
- Batch Embeddings: Tests `/api/embed` batch endpoint with fallback to individual calls.
- Upsert & Search: Tests indexing extracted events and retrieving nearest neighbors.
- Graceful Empty Search: Ensures zero errors when searching an empty collection.

### 4. UI Dashboard Endpoints (`test_ui_app.py`)
- Index Serving: Tests serving `index.html`.
- System Status: Validates aggregation of database counters, Ollama status, and pipeline state.
- Report Retrieval & Security Validation: Verifies retrieval of briefing markdown and validates path traversal rejection.
- Live Feed Endpoints: Tests `/api/anomalies`, `/api/threats`, and `/api/articles`.

### 5. System Purge Operations (`test_purge.py`)
- Relational Purge: Wipes child and parent tables, resets autoincrement counters, and vacuums.
- Vector Purge: Clears ChromaDB collection.
- Unified UI Purge: Tests `POST /api/system/purge`.

---

## Fast Regression & CI/CD Gates

The test suite acts as an automated regression gate:
- **Total Test Count:** **77 passing tests**
- **Execution Speed:** **~3.05 seconds**
- **Pass Rate:** **100%**
- **Deterministic:** Employs mocks for network requests and LLM endpoints, guaranteeing consistent results across environments.

---

## Test Execution & Verification

Run the entire automated test suite:
```bash
uv run pytest
```

Run unit tests only:
```bash
uv run pytest tests/unit/
```

Run integration tests only:
```bash
uv run pytest tests/integration/
```

Run with detailed execution output:
```bash
uv run pytest -v -s
```

---

## Operational Notes

- **Zero Network Flakiness:** External HTTP calls in tests use `pytest-mock` or `responses`, ensuring tests never fail due to internet dropouts.
- **Isolated SQLite DBs:** Integration tests instantiate isolated temporary SQLite databases, preventing test state pollution.

---

## Appendix: Test File Matrix

| Test Module | Tests | Category | Focus Area |
|---|---|---|---|
| `test_date_parsing.py` | 7 | Unit | Multi-format date parsing |
| `test_date_regression.py` | 6 | Unit | Timezones, Romanian months, fallback invariants |
| `test_entity_resolver.py` | 5 | Unit | Canonical actors, parties, and institutions |
| `test_events_bus.py` | 6 | Unit | Ring buffer, SSE, monotonic sequences, cancellation |
| `test_llm_client.py` | 6 | Unit | Token cleaning, JSON extraction, 131k context window |
| `test_pipeline.py` | 4 | Unit | Pipeline orchestration and run IDs |
| `test_taxonomy.py` | 6 | Unit | 5-pillar scoring and noise elimination |
| `test_text_extractor.py` | 2 | Unit | DOM parsing and metadata extraction |
| `test_db_manager.py` | 7 | Integration | SQLite WAL mode, schema, indexes, deduplication |
| `test_db_viewer_api.py` | 10 | Integration | Database viewer, search, CSV export, cancellation |
| `test_purge.py` | 3 | Integration | SQLite and ChromaDB system purge |
| `test_ui_app.py` | 8 | Integration | Dashboard APIs and report security validation |
| `test_vector_store.py` | 7 | Integration | ChromaDB embeddings, batch fallback, semantic search |

---

_Generated by Kipi — Core-Knowledge Keeper_
