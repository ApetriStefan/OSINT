# Intelligence Operator's Manual & Runbook

> **Summary:** Comprehensive user manual and operational runbook: CLI commands, Web Dashboard navigation, report analysis, database search/filtering/export, system purge, and troubleshooting.

**Status:** 🟩 Stable  
**Owner role:** Intelligence Operations Analyst (link to [ownership-map.md](../team_and_stakeholders/ownership-map.md))  
**Last updated:** 2026-11-06  

---

## Table of Contents

- [Overview](#overview)
- [Command Line Operations (CLI)](#command-line-operations-cli)
- [Executive Web Dashboard Guide](#executive-web-dashboard-guide)
- [Working with Intelligence Briefings](#working-with-intelligence-briefings)
- [Using the Database Viewer & Data Export](#using-the-database-viewer--data-export)
- [Exploring the Connected Papers Relational Graph](#exploring-the-connected-papers-relational-graph)
- [System Purge & Maintenance Operations](#system-purge--maintenance-operations)
- [Troubleshooting & Diagnostics](#troubleshooting--diagnostics)
- [Appendix: Standard Daily Operating Procedure (SOP)](#appendix-standard-daily-operating-procedure-sop)

---

## Overview

The Romanian OSINT Political Intelligence System is designed for dual-mode operation: headless automated scheduling via the Command Line Interface (CLI) and interactive visual analysis via the Executive Web Dashboard. This manual provides clear instructions for operating both interfaces.

---

## Command Line Operations (CLI)

The CLI runner is located at [`main.py`](file:///d:/OSINT/main.py).

### 1. Launching the Web Dashboard
```bash
python main.py --ui --port 8000
```
Starts the FastAPI web server on `http://127.0.0.1:8000`.

### 2. Running the Full Daily Pipeline Headless
```bash
python main.py --stage all
```
Executes all stages in sequence (Ingest $\to$ Select $\to$ Agents $\to$ Synthesize) for today's date in `Europe/Bucharest`.

### 3. Running for a Historical Date
```bash
python main.py --stage all --date 2026-11-05
```
Processes articles matching the specified date.

### 4. Running Individual Pipeline Stages
```bash
# Ingest raw RSS feeds only
python main.py --stage ingest

# Select articles and compile press dossier only
python main.py --stage select --date 2026-11-06

# Run Agent 1 (Extractor), Agent 2 (Archivist), and Agent 3 (Red Team)
python main.py --stage agents --dossier dossier_for_agent_1.txt

# Run Agent 4 (Director) and Agent 5 (Copyeditor) to produce final briefing
python main.py --stage synthesize --date 2026-11-06
```

### 5. Running the Automated Test Suite
```bash
uv run pytest
```
Executes all 77 unit and integration tests.

---

## Executive Web Dashboard Guide

Open `http://127.0.0.1:8000` in any modern web browser.

### Navigation Sidebar
- **Prezentare Generală (Overview):** Summary metrics cards (Total Articles, Extracted Events, Anomalies, Threats), quick-start action buttons, and platform health status.
- **Execuție Live (Live Execution):** Execution trigger form, progress bar (0–100%), live markdown token stream, expandable LLM thinking drawer, and cancellation controls.
- **Sinteze Politice (Political Briefings):** Date-based report browser rendering full executive briefings.
- **Hartă Relațională (Relational Graph):** Force-directed D3.js network graph connecting political actors, topics, and threat vectors.
- **Bază de Date (Database Viewer):** Direct data inspection tool with real-time text search, date filtering, pagination, and CSV download.
- **Amenințări & Anomalii (Threats & Contradictions):** Split cards displaying past vs. present quotes with contradiction scores and Red Team vectors.
- **Istoric Rulări (Run History):** Audit table of previous pipeline executions, statuses, and run IDs.

---

## Working with Intelligence Briefings

Briefings are stored in markdown format under `reports/` (e.g. `reports/Sinteza_Politica_2026-11-06.md`).

### Viewing Briefings
1. In the sidebar, click **Sinteze Politice**.
2. Select a briefing from the list of dates on the left.
3. The briefing renders in the main pane with formal formatting, including:
   - Section 1: TL;DR (Executive Summary)
   - Section 2: Power Dynamics and Covert Alliances
   - Section 3: Social & Infrastructure Crisis Exploitation
   - Section 4: Exactly 5 Predictions for Tomorrow with Confidence Scores and Volatility rating
   - Section 5: Tracked Sources & Methodology

### Printing / Exporting to PDF
- Click the **Tipărire / PDF** button at the top-right of the briefing view.
- The interface automatically hides navigation sidebars and headers, producing a clean, professional PDF document via the browser's print dialog.

---

## Using the Database Viewer & Data Export

Click **Bază de Date** in the sidebar to open the data audit tool.

### Inspecting Tables
- Click any table tab at the top:
  * `raw_articles` (Ingested news articles)
  * `extracted_events` (Structured political maneuvers and quotes)
  * `historical_anomalies` (Detected flip-flops and contradiction scores)
  * `threat_vectors` (Tactical opposition threats)
  * `pipeline_executions` (Execution run state machine)

### Searching & Filtering
1. **Full-Text Search (`q`):** Enter any keyword in the search box (e.g. `"Ciolacu"`, `"PNRR"`, `"deficit"`) to search across all text columns.
2. **Date Range Filter:** Use the `De la` (From) and `Până la` (To) date pickers to restrict results.
3. **Sorting:** Click any column header to toggle ascending or descending order.
4. **Pagination:** Use the bottom pagination controls (10, 50, 100 rows per page).

### Exporting Data to CSV
- Click the **Exportă CSV** button above the table.
- Streams a complete, unpaginated CSV export of the active table directly to your downloads folder.

---

## Exploring the Connected Papers Relational Graph

Click **Hartă Relațională** in the sidebar to explore the interactive visual graph.

### Graph Modes
1. **Mod Similaritate (Semantic Similarity):**
   - Nodes represent extracted geopolitical events.
   - Edges connect events with cosine similarity $\ge 0.62$ in ChromaDB vector space.
   - Reveals latent thematic clusters across different media outlets.
2. **Mod Actori & Amenințări (Actors & Threats):**
   - Nodes represent political figures, parties, and institutions.
   - Red directed edges represent hostile Red Team threat vectors (pointing from exploiting actor to vulnerable target).
3. **Mod Flux Articole (News Flow):**
   - Visualizes temporal clustering across media publications.

### Graph Interaction Controls
- **Zoom / Pan:** Use mouse wheel to zoom in/out; click and drag canvas to pan.
- **Node Dragging:** Drag any node to rearrange the force-directed layout.
- **Hover Inspection:** Hover over any node or edge to inspect full entity details, verbatim quotes, or threat descriptions.

---

## System Purge & Maintenance Operations

To reset the database, purge vector collections, or remove outdated briefings:

### Purging via Web UI
1. In the sidebar, click the red **Purjare Date Sistem** button.
2. A confirmation modal will appear detailing what will be deleted:
   - All rows from SQLite child and parent tables (`threat_vectors`, `historical_anomalies`, `extracted_events`, `raw_articles`, `pipeline_executions`).
   - All vector embeddings in ChromaDB collection `political_events`.
   - All generated briefing files in `reports/`.
   - The active press dossier (`dossier_for_agent_1.txt`).
3. Click **Confirmă Purjarea** to execute.

### Purging via API
```bash
curl -X POST http://127.0.0.1:8000/api/system/purge \
     -H "Content-Type: application/json" \
     -d '{"delete_db": true, "delete_chroma": true, "delete_reports": true}'
```

---

## Troubleshooting & Diagnostics

### 1. Ollama Connection Refused
- **Symptom:** UI displays red banner *"Ollama Inaccesibil"* or CLI logs `ConnectionRefusedError`.
- **Resolution:**
  1. Verify Ollama is running: `ollama list`
  2. If not running, start Ollama: `ollama serve`
  3. Verify base URL in `.env`: `OLLAMA_BASE_URL=http://localhost:11434`

### 2. Missing Model Weights
- **Symptom:** Logs report `model 'gemma-4-e4b' not found` or `nomic-embed-text not found`.
- **Resolution:**
  ```bash
  ollama pull gemma-4-e4b
  ollama pull nomic-embed-text
  ```

### 3. Pipeline Run Already in Progress (HTTP 409)
- **Symptom:** Clicking **Rulează** returns error: *"A pipeline execution is already in progress"*.
- **Resolution:**
  1. Check **Execuție Live** tab to see the active run.
  2. If the previous run was aborted unexpectedly, click **Anulează Execuția** to reset the worker flag.

### 4. Database Locked Error (`sqlite3.OperationalError: database is locked`)
- **Symptom:** SQLite throws lock timeout during writes.
- **Resolution:**
  - WAL mode resolves concurrent lock conflicts automatically.
  - Verify that external SQLite GUI tools (DB Browser, DBeaver) do not hold uncommitted write transactions open.

---

## Appendix: Standard Daily Operating Procedure (SOP)

1. **Morning Ingestion (07:30):**
   ```bash
   python main.py --stage all
   ```
2. **Review & Analysis (08:00):**
   - Open `http://127.0.0.1:8000`
   - Navigate to **Sinteze Politice** and read `Sinteza_Politica_[Azi].md`.
   - Review **Amenințări & Anomalii** to evaluate political contradictions.
   - Inspect **Hartă Relațională** to identify emergent coalition friction.
3. **Dissemination (08:30):**
   - Click **Tipărire / PDF** to export executive briefing.

---

_Generated by Kipi — Core-Knowledge Keeper_
