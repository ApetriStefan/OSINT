# Core-Knowledge Index — Romanian OSINT Political Intelligence System

> **Repository:** `d:\OSINT`  
> **Repository Type:** Monolith (Modular Multi-Agent Intelligence System)  
> **Primary Language:** Python 3.10+  
> **Status:** 🟩 Production-Ready & 100% Documented  
> **Last Synchronized:** 2026-11-06  

---

## Mission

The Romanian OSINT Political Intelligence System is a sovereign, local-first intelligence analysis platform designed for national, political, and geopolitical monitoring. It automatically ingests news feeds across major Romanian media outlets, eliminates entertainment and sports noise through a 5-pillar strategic taxonomy, normalizes political actors to canonical identities, models opposition threats and political flip-flops through autonomous multi-agent reasoning, and synthesizes daily executive intelligence briefings streamed in real time to an interactive defense dashboard.

---

## Routing Table

> Fetch this table first. It tells you whether the answer lives here, somewhere else in `core_knowledge/`, or only in code.

| Location | Has answers about | Does NOT have | Read code instead for |
|---|---|---|---|
| [`architecture.md`](architecture.md) | System shape, layer boundaries, data flow, concurrency model, architectural invariants, test statistics | Line-level logic | Actual class/function bodies |
| [`components/`](components/) | Detailed chapters for every major module: agents, classification, scrapers, storage, orchestrator, ui, llm-client | Whole-system diagrams | Unit test specifics |
| [`infrastructure/`](infrastructure/) | Runtime environments, dependencies (`pyproject.toml`), local Ollama setup, testing strategy (77 tests), deployment CLI | Application business logic | Library source files |
| [`processes/`](processes/) | End-to-end intelligence pipeline flow, release and versioning standards, operator runbook and UI usage | Component internal schemas | Step-by-step algorithms |
| [`team_and_stakeholders/`](team_and_stakeholders/) | Contacts, structural team roles, component ownership map | Technical implementation decisions | n/a |

---

## Component Directory Routing

| Chapter | Component Path | Scope & Responsibilities |
|---|---|---|
| [Agents](components/agents.md) | `src/agents/` | NewsSelector, EntityExtractor, Archivist, Red Team, Director, and Copyeditor agent implementations. |
| [Classification](components/classification.md) | `src/classification/` | 5-pillar strategic taxonomy, regex noise filters, and canonical entity resolver for Romanian actors and parties. |
| [Scrapers](components/scrapers.md) | `src/scrapers/`, `src/utils_date.py` | Concurrent RSS feed scraping, connection pooling, DOM text extraction, and Romanian date parsing. |
| [Storage](components/storage.md) | `src/storage/` | SQLite in WAL mode, schema design, event hash deduplication, read-only viewer, and ChromaDB vector store. |
| [Orchestrator](components/orchestrator.md) | `src/orchestrator/`, `src/events.py` | MasterPipeline multi-stage execution, state machine, cooperative cancellation token, and Event Bus ring buffer. |
| [Web UI](components/ui.md) | `src/ui/` | FastAPI backend, SSE live streaming, dark-mode dashboard, DB viewer, and D3.js relational graph. |
| [LLM Client](components/llm-client.md) | `src/llm/` | Ollama client, 131,072 context window guarantee, thinking token streaming, and structured Pydantic JSON parsing. |

---

## Infrastructure & Process Routing

| Chapter | Directory | Scope & Responsibilities |
|---|---|---|
| [Environment & Dependencies](infrastructure/environment-and-dependencies.md) | `infrastructure/` | Python 3.10+, uv runner, local Ollama models (`gemma-4-e4b`, `nomic-embed-text`), SQLite, ChromaDB. |
| [Testing Strategy](infrastructure/testing-strategy.md) | `infrastructure/` | Automated pytest suite: 77 unit & integration tests, fast regression gates (< 4 seconds, 100% pass rate). |
| [Deployment & Operations](infrastructure/deployment.md) | `infrastructure/` | Local-first deployment, operational CLI flags, port bindings (8000, 11434), background worker architecture. |
| [Intelligence Pipeline Flow](processes/intelligence-pipeline-flow.md) | `processes/` | End-to-end 8-step lifecycle: Ingest $\to$ Select $\to$ Extract $\to$ Archive $\to$ Red Team $\to$ Synthesize $\to$ Copyedit $\to$ SSE. |
| [Release & Versioning](processes/release-and-versioning.md) | `processes/` | Branching strategy (`dev` to `main`), quality gates, conventional commits, and semantic versioning. |
| [Operator's Guide](processes/operator-guide.md) | `processes/` | CLI commands, web dashboard navigation, report analysis, database search/filtering/export, system purge. |

---

## Glossary

| Term | Definition |
|---|---|
| **Canonical Entity** | A standardized political figure, party, or institution resolved from noisy news mentions by `EntityResolver`. |
| **Cooperative Cancellation** | Safe pipeline interruption mechanism using `threading.Event` checked across execution loops without corrupting SQLite. |
| **Dossier** | Consolidated, objective plain-text summary document of top 10 daily news stories (`dossier_for_agent_1.txt`). |
| **Event Hash** | Deterministic SHA-256 hash calculated over canonical actor, action, and quote to eliminate duplicate events across runs. |
| **Five-Pillar Taxonomy** | Weighted domain classification: Domestic Politics, Macroeconomy, National Security, Justice, Infrastructure. |
| **Flip-Flop Anomaly** | A detected policy reversal where an actor's current claim contradicts recorded past positions ($\ge 0.5$ score). |
| **Num Ctx Guarantee** | Hard requirement locking the LLM context window to 131,072 tokens to prevent truncation of long dossiers. |
| **Parasitic Framing** | A strategic threat vector where an opposition party hijacks another party's initiative or social crisis. |
| **Ring Buffer** | Fixed-size in-memory queue (2000 events) storing real-time streaming tokens and logs with replay support. |
| **SSE (Server-Sent Events)** | Unidirectional real-time HTTP streaming protocol delivering live LLM tokens and logs to the web dashboard. |
| **WAL Mode** | SQLite Write-Ahead Logging mode (`PRAGMA journal_mode = WAL`) permitting concurrent readers during pipeline writes. |

---

## Coverage Table

| Area | Status | Last Updated | File Count |
|---|---|---|---|
| [`architecture.md`](architecture.md) | 🟩 Complete | 2026-11-06 | 1 |
| [`components/`](components/) | 🟩 Complete | 2026-11-06 | 7 |
| [`infrastructure/`](infrastructure/) | 🟩 Complete | 2026-11-06 | 3 |
| [`processes/`](processes/) | 🟩 Complete | 2026-11-06 | 3 |
| [`team_and_stakeholders/`](team_and_stakeholders/) | 🟩 Complete | 2026-11-06 | 3 |
| **Total Documentation** | **🟩 100% Documented** | **2026-11-06** | **17 Chapters** |

---

## Folder Contracts

> Single source of truth for what belongs in each folder. Read the relevant section before creating or modifying any file.

### `architecture.md`
**Holds:** System shape, data flow, cross-cutting patterns, key trade-offs, concurrency models, testing statistics.  
**Does NOT hold:** Component-level algorithmic details (use `components/`), runbooks (use `processes/`), line-level function bodies.

### `components/`
**Holds:** One file per major module / subsystem (`agents.md`, `classification.md`, `scrapers.md`, `storage.md`, `orchestrator.md`, `ui.md`, `llm-client.md`), each describing responsibilities, boundaries, public interfaces, dependencies, and component-specific decisions.  
**Naming:** `kebab-case.md`.  
**Does NOT hold:** System-wide architecture diagrams (use `architecture.md`), human maintainer names (use `team_and_stakeholders/ownership-map.md`), multi-step operational flows (use `processes/`).

### `infrastructure/`
**Holds:** Runtime environments, deployment procedures, local Ollama configurations, package management with `uv`, CI/CD gates, automated testing strategy, and coding conventions.  
**Does NOT hold:** Application business logic (use `components/`), system design (use `architecture.md`), multi-step workflows (use `processes/`).

### `processes/`
**Holds:** Multi-step operational and development flows spanning tools, roles, and code: intelligence pipeline execution lifecycle, release & versioning standards, operator user manual.  
**Naming:** `kebab-case.md`.  
**Does NOT hold:** Single-step technical setup (use `infrastructure/`), module specifications (use `components/`), personal maintainer notes.

### `team_and_stakeholders/`
**Holds:** THE ONLY place in `core_knowledge/` where personal human names may appear. Required files: `contacts.md`, `team-structure.md`, `ownership-map.md`.  
**Does NOT hold:** Technical decisions (use relevant component file or `architecture.md`).  
**Hard Rule:** Everywhere else in `core_knowledge/`, refer to individuals strictly by ROLE and link here.

### Universal Hard Rules
1. **Human Names Isolation:** Names of real maintainers/developers appear ONLY in `team_and_stakeholders/`. All other Core-Knowledge files reference roles.
2. **Absolute Privacy Boundary:** No document in `core_knowledge/` may link to, quote, cite, or path-mention confidential or unclassified personal scratchpads.

---

## How to Extend This Knowledge Base

- Run Kipi: `/kipi-update-core` or `[UK] Update Core` after making codebase changes.
- Run Kipi: `[CL] Cleanup Knowledge` for periodic maintenance and structure-drift audits.
- Run Kipi: `[CS] Code Scan & Document` for deep repository scanning and chapter authoring.

---

_Maintained by Kipi — Core-Knowledge Keeper. Routing-first design._  
_Structure synchronized: 2026-11-06_
