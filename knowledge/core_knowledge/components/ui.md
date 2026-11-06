# Executive Web UI & Live Stream Layer

> **Summary:** Architectural specification of the FastAPI web backend, real-time Server-Sent Events (SSE) streaming broker, executive dark-mode dashboard, read-only Database Viewer, and Connected Papers relational graph.

**Status:** 🟩 Stable  
**Owner role:** UI/UX Full-Stack Engineer (link to [ownership-map.md](../team_and_stakeholders/ownership-map.md))  
**Last updated:** 2026-11-06  

---

## Table of Contents

- [Overview](#overview)
- [FastAPI Backend Architecture](#fastapi-backend-architecture)
- [Real-Time SSE Streaming Broker](#real-time-sse-streaming-broker)
- [Executive Dashboard User Interface](#executive-dashboard-user-interface)
- [Read-Only Database Viewer & CSV Export](#read-only-database-viewer--csv-export)
- [Relational & Semantic Graph Engine](#relational--semantic-graph-engine)
- [Security Controls & Input Validation](#security-controls--input-validation)
- [Component-Specific Decisions & Trade-offs](#component-specific-decisions--trade-offs)
- [Operational Notes](#operational-notes)
- [Appendix: Key Code Locations](#appendix-key-code-locations)

---

## Overview

The executive user interface layer ([`src/ui/app.py`](file:///d:/OSINT/src/ui/app.py) and [`src/ui/templates/index.html`](file:///d:/OSINT/src/ui/templates/index.html)) provides an interactive, non-blocking operational dashboard for intelligence analysts and decision-makers. It enables users to trigger and monitor pipeline executions in real time, view LLM internal thinking streams token-by-token, inspect contradictions and hostile threat vectors, explore relational actor networks via D3.js, and audit the complete underlying SQLite database through an integrated viewer.

---

## FastAPI Backend Architecture

Implemented in [`src/ui/app.py`](file:///d:/OSINT/src/ui/app.py):

### Background Worker Threading (`PipelineStateManager`)
Pipeline runs are CPU- and GPU-intensive tasks that take several minutes. To keep the web server 100% responsive:
- Pipeline execution is dispatched to a background daemon thread (`_execute_worker`).
- `PipelineStateManager` acts as a concurrency gate: if a run is already active, triggering a second run immediately returns `HTTP 409 Conflict`.
- Live progress percentage and status messages are tracked thread-safely and exposed via `GET /api/status`.

### REST API Endpoints Overview
| Endpoint | Method | Description |
|---|---|---|
| `/` | `GET` | Serves the single-page executive intelligence dashboard. |
| `/api/status` | `GET` | Health status, database counters, Ollama model verification, and active pipeline state. |
| `/api/stream` | `GET` | Server-Sent Events (SSE) stream for live tokens, thinking processes, and logs. |
| `/api/run` | `POST` | Asynchronously initiates a pipeline run with date and stage parameters. |
| `/api/run/cancel` | `POST` | Requests cooperative cancellation of the running pipeline. |
| `/api/reports` | `GET` | Lists available synthesized daily intelligence briefings. |
| `/api/reports/{filename}` | `GET` | Retrieves raw markdown content of a specific briefing. |
| `/api/anomalies` | `GET` | Returns detected historical contradictions and flip-flops. |
| `/api/threats` | `GET` | Returns tactical threat vectors identified by the Red Team. |
| `/api/articles` | `GET` | Returns recently ingested raw news articles. |
| `/api/executions` | `GET` | Returns audit history of pipeline execution runs. |
| `/api/db/tables` | `GET` | Lists all database tables, row counts, and column schemas. |
| `/api/db/schema` | `GET` | Returns structured database schema summary. |
| `/api/db/tables/{table}/rows` | `GET` | Paginated, sorted, and filtered database table rows (max limit 500). |
| `/api/db/tables/{table}/rows/{id}` | `GET` | Retrieves a single record by primary key. |
| `/api/db/export/{table}.csv` | `GET` | Streams table data as a downloadable CSV attachment. |
| `/api/db/graph` | `GET` | Relational and semantic network graph data (similarity, actors, articles). |
| `/api/system/purge` | `POST` / `DELETE` | Purges SQLite, ChromaDB vectors, generated reports, and clears dossiers. |

---

## Real-Time SSE Streaming Broker

Endpoint: `GET /api/stream`

### Streaming Architecture
- Clients open a standard `EventSource` connection to `/api/stream`.
- The connection subscribes to an asynchronous queue registered with the global `event_bus`.
- As Ollama generates tokens and thinking blocks, the client receives them instantly as SSE events:
  ```
  id: 204
  event: token
  data: {"type": "token", "agent": "director", "seq": 204, "text": "...", "ts": "2026-11-06T19:00:00Z"}
  ```
- **Replay Support:** If the browser disconnects and reconnects with `Last-Event-ID: 203`, the stream automatically replays all missed events starting from sequence 204.
- **Keep-Alive Heartbeat:** If the stream is idle for 15 seconds, it emits a `: ping\n\n` heartbeat to prevent browser and proxy timeout drops.

---

## Executive Dashboard User Interface

- **Template:** [`src/ui/templates/index.html`](file:///d:/OSINT/src/ui/templates/index.html)
- **Styling:** Tailwind CSS with dark-mode defense intelligence theme (`#0b0f19` slate background).
- **Typography:**
  - `Inter`: General UI, executive summaries, headings, and tables.
  - `JetBrains Mono`: Code blocks, SQL statements, database IDs, and LLM thinking streams.

### Interactive Views & Views Navigation
1. **Prezentare Generală (Overview):** Metrics cards (Total Articles, Events, Contradictions, Threats), rapid action triggers, and recent intelligence activity.
2. **Execuție Live (Live Execution):** Active stage progress bar (0–100%), real-time token stream, dedicated expandable LLM thinking drawer, and cancel button.
3. **Sinteze Politice (Political Briefings):** Date-based report browser rendering full executive briefings via Marked.js and DOMPurify with print-friendly layout.
4. **Hartă Relațională (Relational Graph):** Force-directed D3.js network graph visualizing connections between political actors, topics, and threats.
5. **Bază de Date (Database Viewer):** Direct data inspection tool with search, pagination, and CSV download.
6. **Amenințări & Anomalii (Threats & Contradictions):** Detailed analytical cards displaying past vs. present quotes, contradiction scores, and red team vectors.
7. **Istoric Rulări (Run History):** Complete audit log of all pipeline execution runs, stages, and durations.

---

## Read-Only Database Viewer & CSV Export

Analysts can inspect underlying data without leaving the browser:
- **Search & Filtering:** Real-time text search across all string columns using parameterized SQL `LIKE %q%` queries, combined with optional `date_from` and `date_to` range filtering.
- **Pagination & Sorting:** Configurable page size (10 to 500 rows) with column-level ascending/descending sort.
- **One-Click CSV Export:** Generates streaming CSV downloads directly from SQLite via `export_table_csv()`.
- **Strict Read-Only Enforcement:** Uses SQLite URI `mode=ro` connections; arbitrary SQL execution is strictly disallowed.

---

## Relational & Semantic Graph Engine

Endpoint: `GET /api/db/graph`

The platform generates interactive network graphs inspired by Connected Papers:
1. **Mode `similarity`:** Calculates pairwise cosine similarity across 768-dimensional ChromaDB embeddings (`min_similarity` threshold defaults to 0.62) to discover clusters of related geopolitical events.
2. **Mode `actors`:** Maps bipartite relationships between political leaders and strategic topics, enriched with directed Red Team threat edges (exploiting actor $\to$ vulnerable actor).
3. **Mode `articles`:** Clusters ingested news articles by publishing source and temporal proximity.
4. **Interactive D3.js Visualization:** Supports node dragging, zooming, panning, hover tooltips, and click-to-filter mechanics.

---

## Security Controls & Input Validation

1. **Path Traversal Protection:**
   The report viewer strictly validates filenames:
   - Must match `^Sinteza_Politica_.*\.md$`
   - Must resolve within `reports/` directory
   - Attempts to access `../` or arbitrary system paths immediately raise `HTTP 400` or `HTTP 404`.
2. **Table Whitelist Enforcement:**
   Database viewer endpoints query `sqlite_master` for actual table names. Unrecognized table names raise `HTTP 404`, eliminating SQL injection risks.
3. **Future Date Validation:**
   Execution triggers check publication dates against current Bucharest time, rejecting future dates with `HTTP 422 Unprocessable Entity`.
4. **Read-Only SQLite Connections:**
   Read operations use dedicated `file:path?mode=ro` connections, preventing any unauthorized data mutation from viewer endpoints.

---

## Component-Specific Decisions & Trade-offs

1. **Single-Page Application (SPA) with Vanilla JS & Tailwind:**
   - *Decision:* Implemented as a clean SPA using Vanilla JS and Tailwind CSS without heavy frontend build tools (Vite, React, Webpack).
   - *Rationale:* Eliminates Node.js build dependencies at runtime; runs immediately via Python and Uvicorn with zero compilation steps.
2. **Client-Side Markdown Sanitization:**
   - *Decision:* Raw markdown reports are parsed via Marked.js and purified via DOMPurify in the browser.
   - *Rationale:* Protects against XSS attacks from scraped article content while preserving rich markdown styling.

---

## Operational Notes

- **Launch Command:** `python main.py --ui --port 8000`
- **Port & Host Defaults:** `127.0.0.1:8000` (configurable via `--host` and `--port` CLI flags).
- **Integration Tested:** Verified under `tests/integration/test_ui_app.py` and `tests/integration/test_db_viewer_api.py`.

---

## Appendix: Key Code Locations

- `src/ui/app.py` — FastAPI application, API routers, and state manager
- `src/ui/templates/index.html` — Single-page dashboard interface and D3.js graph visualizer
- `src/ui/static/css/styles.css` — Custom defense styling and scrollbar overrides
- `src/ui/static/js/app.js` — Client-side application logic and SSE listener
- `tests/integration/test_ui_app.py` — UI endpoint integration tests
- `tests/integration/test_db_viewer_api.py` — Database viewer API integration tests

---

_Generated by Kipi — Core-Knowledge Keeper_
