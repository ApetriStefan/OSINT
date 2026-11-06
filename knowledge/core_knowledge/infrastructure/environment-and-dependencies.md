# Environment & Runtime Dependencies

> **Summary:** Technical specification of the runtime environment, Python dependencies, uv package management, local Ollama model ecosystem, and storage engines.

**Status:** 🟩 Stable  
**Owner role:** DevOps / Infrastructure Engineer (link to [ownership-map.md](../team_and_stakeholders/ownership-map.md))  
**Last updated:** 2026-11-06  

---

## Table of Contents

- [Overview](#overview)
- [Runtime Requirements](#runtime-requirements)
- [Package Management with uv](#package-management-with-uv)
- [Core Dependency Breakdown](#core-dependency-breakdown)
- [Local Ollama Model Ecosystem](#local-ollama-model-ecosystem)
- [Storage Engines](#storage-engines)
- [Environment Variables (.env)](#environment-variables-env)
- [Operational Notes](#operational-notes)
- [Appendix: Key Configuration Files](#appendix-key-configuration-files)

---

## Overview

The platform is designed around a **100% local-first, zero-cloud architecture**. It requires zero external SaaS API keys (such as OpenAI, Anthropic, or cloud vector stores), guaranteeing operational sovereignty, data privacy, and resilient offline execution.

---

## Runtime Requirements

| Component | Specification | Verification Command | Notes |
|---|---|---|---|
| **Python** | `>= 3.10.0, < 3.13.0` | `python --version` | Tested on Python 3.10.6 |
| **uv** | Latest | `uv --version` | Fast package resolver and test runner |
| **Ollama** | `>= 0.1.30` | `ollama --version` | Local LLM and embedding server |
| **Operating System** | Windows, Linux, macOS | `systeminfo` / `uname -a` | Cross-platform compatibility |

---

## Package Management with `uv`

The project utilizes Astral's `uv` for lightning-fast dependency resolution, deterministic lockfiles (`uv.lock`), and virtual environment management:

```bash
# Install / sync dependencies into .venv
uv sync

# Run tests
uv run pytest

# Execute application
uv run python main.py --stage all
```

---

## Core Dependency Breakdown

Configured in [`pyproject.toml`](file:///d:/OSINT/pyproject.toml):

| Package | Version | Purpose |
|---|---|---|
| `fastapi` | `>=0.110.0` | High-performance asynchronous web API framework |
| `uvicorn` | `>=0.28.0` | ASGI web server hosting the dashboard and SSE stream |
| `pydantic` | `>=2.7.0` | Schema validation, data parsing, and JSON schema extraction |
| `pydantic-settings` | `>=2.2.0` | Centralized environment variable management via `.env` |
| `chromadb` | `>=0.4.22` | Embedded persistent vector database for semantic recall |
| `feedparser` | `>=6.0.10` | RSS feed parsing and struct_time extraction |
| `beautifulsoup4` | `>=4.12.0` | Resilient HTML DOM extraction and boilerplate stripping |
| `requests` | `>=2.31.0` | HTTP client with session pooling and retry backoff |
| `urllib3` | `>=2.0.0` | Connection pool manager and HTTP adapter |
| `python-dateutil` | `>=2.9.0` | Multi-format European and RFC 822 date parsing |
| `numpy` | `>=1.26.0` | Array manipulation and vector similarity calculations |
| `pytest` | `>=8.0.0` | Automated testing framework |
| `pytest-mock` | `>=3.12.0` | Test double and mock isolation |
| `responses` | `>=0.25.0` | Mocking HTTP responses for deterministic scraper tests |

---

## Local Ollama Model Ecosystem

The system integrates directly with Ollama running locally at `http://localhost:11434`:

### 1. Primary Generative Model: `gemma-4-e4b`
- **Role:** Entity extraction, historical analysis, adversarial modeling, synthesis, and copyediting.
- **Context Window:** Locked at **131,072 tokens** (`num_ctx = 131072`).
- **Characteristics:** High analytical fidelity, native Romanian comprehension, and low hallucination rates.

### 2. Dedicated Embedding Model: `nomic-embed-text`
- **Role:** High-dimensional semantic embeddings for ChromaDB vector retrieval and relational graph clustering.
- **Dimensionality:** 768 dimensions.
- **Decoupling Advantage:** Completely separated from generative calls to prevent VRAM competition and HTTP 500 endpoint errors.

#### Verification Commands:
```bash
# Verify running models
ollama list

# Pull models if missing
ollama pull gemma-4-e4b
ollama pull nomic-embed-text
```

---

## Storage Engines

1. **SQLite (`political_intel.db`):**
   - Built into the standard library (`sqlite3`).
   - Configured with Write-Ahead Logging (`WAL` mode) and foreign keys enabled.
   - Provides relational integrity, event deduplication, and execution tracking.
2. **ChromaDB (`chroma_db/`):**
   - Embedded persistent vector store located in the workspace root.
   - Anonymized telemetry explicitly disabled for privacy.

---

## Environment Variables (`.env`)

Configuration is managed via [`src/config.py`](file:///d:/OSINT/src/config.py) using `Pydantic BaseSettings`, reading from `.env`:

```ini
# Ollama Configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma-4-e4b
OLLAMA_EMBED_MODEL=nomic-embed-text
NUM_CTX=131072

# Sampling Parameters
TEMPERATURE=0.0
TOP_P=0.1

# Storage Paths
DB_PATH=political_intel.db
CHROMA_PATH=chroma_db

# Ingestion Settings
REQUEST_TIMEOUT=15
MAX_SELECTED_ARTICLES=10
```

---

## Operational Notes

- **Offline Mode:** Once models are pulled and Python dependencies installed, the system can run completely isolated from external internet access (using cached local feeds or database archives).
- **Zero Cloud Leakage:** No data, articles, embeddings, or prompts leave the local host.

---

## Appendix: Key Configuration Files

- `pyproject.toml` — Project dependencies and build configuration
- `uv.lock` — Deterministic dependency lockfile
- `.env.example` — Template environment variables file
- `src/config.py` — Centralized settings loader

---

_Generated by Kipi — Core-Knowledge Keeper_
