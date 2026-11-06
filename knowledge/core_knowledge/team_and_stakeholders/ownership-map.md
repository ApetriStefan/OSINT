# Ownership Map

> **Status:** 🟩 Production Ready (Updated & Synchronized)  
> **Last Updated:** 2026-11-06  

Who owns which component, process, and system. All other Core-Knowledge files refer here when they need to indicate ownership (using roles + links, not names embedded inline).

| Asset | Type | Primary Owner | Secondary | Notes |
|---|---|---|---|---|
| Master Pipeline (`src/orchestrator/pipeline.py`) | component | Lead Pipeline Engineer | System Architect | Core end-to-end stage orchestration |
| Event Bus & Streaming (`src/events.py`) | component | Lead Pipeline Engineer | UI/UX Full-Stack Engineer | Thread-safe ring buffer and SSE broker |
| Multi-Agent Suite (`src/agents/`) | component | Agent Architect | Machine Learning Engineer | Extractor, Archivist, Red Team, Director, Copyeditor, Selector |
| Classification & Entity Resolver (`src/classification/`) | component | Classification Specialist | Intelligence Analyst | 5-pillar taxonomy & canonical actor resolution |
| Ingestion & Web Scraping (`src/scrapers/`, `src/utils_date.py`) | component | Pipeline Engineer | Data Engineer | RSS scraper, connection pooling, resilient text extraction |
| SQLite Database (`src/storage/db_manager.py`) | data-store | Data Engineer | Pipeline Engineer | Relational storage in WAL mode, schema migrations, deduplication |
| ChromaDB Vector Store (`src/storage/vector_store.py`) | data-store | Machine Learning Engineer | Data Engineer | Vector embeddings via nomic-embed-text |
| LLM Client Engine (`src/llm/client.py`) | component | Machine Learning Engineer | Lead Pipeline Engineer | Ollama client, 131k context window, structured JSON schemas |
| Web UI & Dashboard (`src/ui/`) | system | UI/UX Full-Stack Engineer | Lead Maintainer | FastAPI backend, SSE stream, dark-mode dashboard, DB & graph viewers |
| Testing Suite (`tests/`) | process | QA & Test Automation Engineer | Lead Maintainer | Automated 77-test unit and integration test suite |
| Core-Knowledge Repository Memory (`knowledge/core_knowledge/`) | process | Core-Knowledge Keeper (Kipi) | Lead Maintainer | Authoritative repository documentation |

---

## Conventions

- **Asset types:** `component`, `process`, `system`, `integration`, `data-store`
- One owner per asset (the buck stops here)
- Secondary is optional; used for backup / on-call

---

_Maintained as part of `team_and_stakeholders/`._
