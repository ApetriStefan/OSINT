# Team Structure

> **Status:** 🟩 Production Ready  
> **Last Updated:** 2026-11-06  

Teams, reporting lines, and areas of responsibility for this project.

## Teams

- **Intelligence Operations & Core Engineering:** Oversees feed ingestion, scraper resilience, database storage, multi-agent reasoning, web UI development, and daily executive synthesis.

## Reporting lines

- Single maintainer structure led by the Project Lead & Maintainer (see [contacts.md](contacts.md)).

## Areas of responsibility

- **Pipeline & Feed Management:** RSS endpoints, connection pooling, and Romanian date parsing.
- **Model Orchestration:** Local Ollama model integration, 131,072 context window guarantee, and multi-agent prompting.
- **Data & Vector Storage:** SQLite in WAL mode and ChromaDB vector search with nomic-embed-text.
- **Executive UI/UX:** FastAPI web backend, real-time SSE streaming, dark-mode dashboard, DB viewer, and D3.js relational graph.
- **Repository Architecture & Memory:** BMad Method and Kipi Core-Knowledge maintenance.

---

_Maintained as part of `team_and_stakeholders/`. Names belong here, not in technical knowledge files._
