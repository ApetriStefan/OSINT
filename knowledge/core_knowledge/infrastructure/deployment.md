# Deployment & Operations Architecture

> **Summary:** Technical specification of the local-first deployment architecture, operational CLI flags, web server bindings, and asynchronous background worker execution.

**Status:** 🟩 Stable  
**Owner role:** Systems & Operations Engineer (link to [ownership-map.md](../team_and_stakeholders/ownership-map.md))  
**Last updated:** 2026-11-06  

---

## Table of Contents

- [Overview](#overview)
- [Local-First Architecture Principles](#local-first-architecture-principles)
- [Operational CLI Reference (`main.py`)](#operational-cli-reference-mainpy)
- [Web Server & Port Configuration](#web-server--port-configuration)
- [Background Worker Architecture](#background-worker-architecture)
- [Operating System Support & Console Hygiene](#operating-system-support--console-hygiene)
- [Operational Notes](#operational-notes)
- [Appendix: Deployment Runbook](#appendix-deployment-runbook)

---

## Overview

The platform is deployed as a self-contained, sovereign software artifact. It runs directly on developer workstations, secure operational laptops, or air-gapped on-premises servers. It avoids complex microservices orchestration (such as Kubernetes or external cloud queues), providing high reliability, instant cold starts, and minimal operational maintenance.

---

## Local-First Architecture Principles

1. **Complete Data Sovereignty:** Ingested articles, extracted political entities, threat assessments, and executive briefings never leave the local machine.
2. **Zero Recurring SaaS Costs:** Operates entirely without external paid LLM APIs or managed vector services.
3. **Resilient Offline Execution:** With Ollama models loaded locally, the system can synthesize intelligence briefings, query historical memory, and analyze dossiers without an active internet connection (relying on pre-scraped or archived data).

---

## Operational CLI Reference (`main.py`)

The unified CLI entrypoint is [`main.py`](file:///d:/OSINT/main.py):

```bash
python main.py [OPTIONS]
```

### Supported CLI Flags

| Flag | Type | Default | Description |
|---|---|---|---|
| `--stage` | Choice | `all` | Pipeline stage to execute: `all`, `ingest`, `select`, `agents`, `synthesize`. |
| `--date` | String | `None` (today) | Target publication date (`YYYY-MM-DD` in `Europe/Bucharest`). Cannot be in the future. |
| `--dossier` | String | `dossier_for_agent_1.txt` | Path for reading or writing the consolidated press summary dossier. |
| `--log-level` | Choice | `INFO` | Logging verbosity level: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `--ui` | Flag | `False` | Launches the interactive executive web dashboard via Uvicorn. |
| `--host` | String | `127.0.0.1` | Network binding host address for the web server. |
| `--port` | Integer | `8000` | Network binding TCP port for the web server. |
| `--reload` | Flag | `False` | Enables auto-reload for local UI and template development. |

### Common Operational Invocations

```bash
# 1. Launch the interactive executive web dashboard
python main.py --ui --port 8000

# 2. Run the complete automated intelligence pipeline headless for today
python main.py --stage all

# 3. Run the complete pipeline for a specific historical date
python main.py --stage all --date 2026-11-05

# 4. Ingest raw RSS feeds only
python main.py --stage ingest

# 5. Filter news and compile dossier only
python main.py --stage select --date 2026-11-06

# 6. Execute multi-agent extraction and analysis on an existing dossier
python main.py --stage agents --dossier dossier_for_agent_1.txt

# 7. Synthesize executive briefing from existing extracted events
python main.py --stage synthesize --date 2026-11-06
```

---

## Web Server & Port Configuration

When launched with `--ui`, `main.py` initializes a `uvicorn` ASGI server hosting the FastAPI application ([`src/ui/app.py`](file:///d:/OSINT/src/ui/app.py)):

### Port Allocations
- **Web Dashboard:** `8000` (configurable via `--port`)
- **Ollama LLM Server:** `11434` (configurable via `OLLAMA_BASE_URL` in `.env`)

### Network Bindings & Security
- By default, the web dashboard binds to loopback interface `127.0.0.1`, preventing unauthorized external network discovery.
- To expose the dashboard across a secure private LAN or VPN, specify `--host 0.0.0.0` or the node's internal network IP.

---

## Background Worker Architecture

To ensure the FastAPI web server remains completely non-blocking during heavy LLM inference:
1. When a user triggers execution via `POST /api/run`, `PipelineStateManager.start_run()` spawns a daemon thread `_execute_worker`.
2. The background thread instantiates `MasterPipeline` and executes the requested stage sequence.
3. The main thread continues serving HTTP requests, responding to `/api/status` polls, and streaming SSE tokens to the browser.
4. If a cancellation signal is dispatched (`POST /api/run/cancel`), the background thread catches `InterruptedError` at the next checkpoint and cleanly terminates without leaving orphaned database locks.

---

## Operating System Support & Console Hygiene

1. **Windows UTF-8 Console Protection:**
   [`main.py`](file:///d:/OSINT/main.py) detects Windows platforms and reconfigures `sys.stdout` and `sys.stderr` to UTF-8 encoding:
   ```python
   if sys.platform.startswith("win"):
       sys.stdout.reconfigure(encoding="utf-8")
       sys.stderr.reconfigure(encoding="utf-8")
   ```
   This prevents crashes when logging Romanian diacritics (`ș`, `ț`, `ă`, `â`, `î`) or emoji status icons in PowerShell or CMD.
2. **Graceful Exit:**
   Intercepts `KeyboardInterrupt` (Ctrl+C), logging clean termination and returning UNIX exit code `130`.

---

## Operational Notes

- **Process Memory Footprint:** The Python process uses ~150–250 MB RAM; Ollama models reside in GPU VRAM (or system RAM for CPU-only nodes).
- **Disk Storage Growth:** Ingested articles and vector embeddings consume roughly 5–15 MB per operational month.

---

## Appendix: Deployment Runbook

### Clean System Setup
```bash
# 1. Clone repository
git clone <repository_url>
cd OSINT

# 2. Sync dependencies with uv
uv sync

# 3. Verify local Ollama is active
ollama list

# 4. Run test suite to verify system integrity
uv run pytest

# 5. Launch web operations dashboard
uv run python main.py --ui --port 8000
```

---

_Generated by Kipi — Core-Knowledge Keeper_
