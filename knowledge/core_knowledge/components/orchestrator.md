# Master Pipeline & Event Bus Orchestrator

> **Summary:** Technical specification of the MasterPipeline orchestrator, multi-stage execution model, cooperative cancellation token, and thread-safe Event Bus ring buffer.

**Status:** 🟩 Stable  
**Owner role:** Lead Pipeline Engineer (link to [ownership-map.md](../team_and_stakeholders/ownership-map.md))  
**Last updated:** 2026-11-06  

---

## Table of Contents

- [Overview](#overview)
- [MasterPipeline Architecture](#masterpipeline-architecture)
- [Execution Stages & Checkpoints](#execution-stages--checkpoints)
- [Thread-Safe Event Bus & SSE Streaming Broker](#thread-safe-event-bus--sse-streaming-broker)
- [Cooperative Cancellation Token Architecture](#cooperative-cancellation-token-architecture)
- [Public Interface](#public-interface)
- [Component-Specific Decisions & Trade-offs](#component-specific-decisions--trade-offs)
- [Operational Notes](#operational-notes)
- [Appendix: Key Code Locations](#appendix-key-code-locations)

---

## Overview

The orchestrator subsystem ([`src/orchestrator/pipeline.py`](file:///d:/OSINT/src/orchestrator/pipeline.py) and [`src/events.py`](file:///d:/OSINT/src/events.py)) coordinates the end-to-end execution of the OSINT political intelligence workflow. It manages stage transitions, persists state machine records to SQLite, routes live events through an in-memory ring buffer for browser streaming, and provides cooperative cancellation checks across all processing loops.

---

## MasterPipeline Architecture

The `MasterPipeline` class orchestrates ingestion, candidate selection, multi-agent reasoning, and executive report synthesis:

```
[MasterPipeline.run(stage)]
            │
            ├───> Stage 1: INGEST     (RSSScraper -> SQLite raw_articles)
            │
            ├───> Stage 2: SELECT     (NewsSelector -> dossier_for_agent_1.txt)
            │
            ├───> Stage 3: AGENTS     (Agent 1 Extractor -> Agent 2 Archivist -> Agent 3 Red Team)
            │
            └───> Stage 4: SYNTHESIZE (Agent 4 Director -> Agent 5 Copyeditor -> reports/)
```

### Execution State Machine
Every execution generates a timestamped run identifier (`run_YYYYMMDD_HHMMSS_xxxxxx`). At each stage boundary, the pipeline records state transitions into the SQLite table `pipeline_executions`:
- `STARTED`: Stage execution initiated.
- `COMPLETED`: Stage finished successfully with details logged.
- `FAILED`: An unhandled exception was captured and logged.
- `CANCELLED`: Execution was stopped cooperatively via user request.

---

## Execution Stages & Checkpoints

### 1. `stage_ingest(run_id: str) -> int`
- Fetches all configured RSS feeds concurrently via `RSSScraper.fetch_all()`.
- Inserts raw articles into SQLite `raw_articles` with URL deduplication.
- Emits progress events (`progress_pct: 25`).

### 2. `stage_select(run_id, target_date, dossier_path) -> str`
- Validates the target date in `Europe/Bucharest` timezone.
- Filters out non-strategic news using `IntelligenceTaxonomy.is_noise()`.
- Uses LLM selection (or heuristic ranking fallback) to pick the top 10 articles.
- Performs concurrent deep scraping of article bodies via `scrape_full_text()`.
- Uses LLM to compile and save the structured press dossier (`dossier_for_agent_1.txt`).
- Emits progress events (`progress_pct: 50`).

### 3. `stage_agents(run_id, dossier_text, dossier_path) -> Dict[str, Any]`
- Loads the press dossier into memory.
- **Agent 1 (Extractor):** Extracts structured entities, verbatim quotes, and canonical names.
- Checkpoint: verifies `event_bus.is_cancelled()`.
- **Agent 2 (Archivist):** Pre-fetches historical statements from ChromaDB / SQLite, indexes today's events, and scores contradictions ($\ge 0.5$).
- Checkpoint: verifies `event_bus.is_cancelled()`.
- **Agent 3 (Red Team):** Models strategic vulnerabilities, opposing party attacks, and parasitic framing.
- Emits progress events (`progress_pct: 75`).

### 4. `stage_synthesize(run_id, events, anomalies, threats, articles, target_date) -> str`
- **Agent 4 (Director):** Synthesizes multi-agent outputs into a 5-section executive briefing in Romanian with 5 predictive forecasts and confidence scores.
- Checkpoint: verifies `event_bus.is_cancelled()`.
- **Agent 5 (Copyeditor):** Cleans typographical artifacts, corrects Romanian diacritics, and saves the final markdown artifact to `reports/Sinteza_Politica_YYYY-MM-DD.md`.
- Emits completion events (`progress_pct: 100`).

---

## Thread-Safe Event Bus & SSE Streaming Broker

Implemented in [`src/events.py`](file:///d:/OSINT/src/events.py) as `EventBus`:

### Event Data Model
```python
@dataclass
class Event:
    type: str       # 'token' | 'thinking' | 'stage' | 'agent_start' | 'agent_end' | 'log'
    agent: str      # 'pipeline' | 'selector' | 'extractor' | 'archivist' | 'red_team' | 'director' | 'copyeditor'
    run_id: str     # Execution run ID
    seq: int        # Monotonically increasing sequence number
    text: str       # Streamed text or message
    ts: str         # ISO-8601 UTC timestamp
    data: Optional[Dict[str, Any]] = None
```

### In-Memory Ring Buffer & Replay Support
- **Ring Buffer:** Uses `collections.deque(maxlen=2000)` protected by a threading lock. Retains the last 2000 events in memory.
- **SSE Serialization:** Serializes events into standard Server-Sent Events messages:
  ```
  id: 142
  event: thinking
  data: {"type": "thinking", "agent": "director", "seq": 142, "text": "...", "ts": "..."}
  ```
- **Replay Support (`Last-Event-ID`):** When browser clients reconnect after a network disconnect, passing the HTTP header `Last-Event-ID: 141` will automatically replay all missed events starting from sequence 142 onwards.

### Logging Integration (`EventBusLogHandler`)
Standard Python `logging` output is piped directly into the event bus, converting `logger.info()` and `logger.warning()` calls into `type="log"` events for real-time display in the UI console drawer.

---

## Cooperative Cancellation Token Architecture

To halt execution safely without leaving database connections corrupted or threads orphaned:
1. `EventBus` maintains a thread-safe `threading.Event` cancellation flag.
2. When the user clicks **Cancel** in the web dashboard (`POST /api/run/cancel`), the UI calls `event_bus.request_cancellation()`.
3. The orchestrator inspects `event_bus.is_cancelled()` at every major stage transition, worker thread loop, and between LLM calls.
4. If cancelled, the orchestrator raises `InterruptedError`, updates SQLite `pipeline_executions` with status `CANCELLED`, publishes a cancellation notice on SSE, and terminates cleanly.

---

## Public Interface

```python
# Master Pipeline Execution
pipeline = MasterPipeline()
results = pipeline.run(
    stage="all",                    # 'all', 'ingest', 'select', 'agents', 'synthesize'
    target_date="2026-11-06",       # YYYY-MM-DD
    dossier_path="dossier_for_agent_1.txt",
    run_id=None
) -> Dict[str, Any]

# Event Bus Publishing
event_bus.publish(
    event_type="stage",
    text="Ingestion complete",
    agent="pipeline",
    data={"progress_pct": 25}
)

# Cooperative Cancellation
event_bus.request_cancellation()
if event_bus.is_cancelled():
    # Graceful exit
    ...
```

---

## Component-Specific Decisions & Trade-offs

1. **Ring Buffer vs. External Queue (Redis/RabbitMQ):**
   - *Decision:* Implemented an in-memory thread-safe `deque` ring buffer instead of an external message broker.
   - *Rationale:* Preserves zero-dependency local-first architecture; eliminates requirement for external daemon processes.
2. **Cooperative Cancellation vs. Thread Termination:**
   - *Decision:* Used cooperative cancellation checkpoints (`is_cancelled()`) rather than killing threads forcibly (`pthread_kill` / `ctypes`).
   - *Rationale:* Ensures database transactions commit or roll back cleanly, preventing SQLite WAL lock corruption.

---

## Operational Notes

- **CLI Usage:** `python main.py --stage all --date 2026-11-06`
- **Unit Tested:** Pipeline stages, sequence numbering, ring buffer eviction, replay, and cancellation tokens are verified in `tests/unit/test_pipeline.py` and `tests/unit/test_events_bus.py`.

---

## Appendix: Key Code Locations

- `src/orchestrator/pipeline.py` — MasterPipeline execution engine and state machine
- `src/events.py` — EventBus, Event model, and EventBusLogHandler
- `tests/unit/test_pipeline.py` — Pipeline stage unit tests
- `tests/unit/test_events_bus.py` — Event bus ring buffer and cancellation tests

---

_Generated by Kipi — Core-Knowledge Keeper_
