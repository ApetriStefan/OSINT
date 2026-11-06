# Multi-Agent Intelligence System

> **Summary:** Comprehensive specification of the six specialized agents powering the OSINT political intelligence pipeline: Selector, Entity Extractor, Archivist, Red Team, Director, and Copyeditor.

**Status:** 🟩 Stable  
**Owner role:** Agent Architect (link to [ownership-map.md](../team_and_stakeholders/ownership-map.md))  
**Last updated:** 2026-11-06  

---

## Table of Contents

- [Overview](#overview)
- [Agent 0: Strategic News Selector](#agent-0-strategic-news-selector)
- [Agent 1: Structured Entity Extractor](#agent-1-structured-entity-extractor)
- [Agent 2: Historical Archivist & Contradiction Detector](#agent-2-historical-archivist--contradiction-detector)
- [Agent 3: Hostile Political Strategist (Red Team)](#agent-3-hostile-political-strategist-red-team)
- [Agent 4: Executive Intelligence Director](#agent-4-executive-intelligence-director)
- [Agent 5: Romanian Copyeditor & Grammar Proofreader](#agent-5-romanian-copyeditor--grammar-proofreader)
- [Agent Execution Matrix](#agent-execution-matrix)
- [Component-Specific Decisions & Trade-offs](#component-specific-decisions--trade-offs)
- [Operational Notes](#operational-notes)
- [Appendix: Key Code Locations](#appendix-key-code-locations)

---

## Overview

The intelligence pipeline employs an ensemble of six specialized autonomous agents. Rather than relying on a single monolithic prompt, the system separates analytical concerns into discrete, sequential stages:
1. **Selection & Scraping:** Curating the highest-impact daily stories and building a dense, factual dossier.
2. **Extraction:** Parsing unstructured text into typed entities, verifiable actions, and verbatim quotes.
3. **Historical Cross-Referencing:** Verifying today's declarations against long-term memory to expose policy reversals and flip-flops.
4. **Adversarial Modeling:** Simulating opposition maneuvers, asymmetric attacks, and parasitic narrative framing.
5. **Synthesis:** Writing an authoritative executive-level daily intelligence briefing in Romanian.
6. **Linguistic Refinement:** Normalizing diacritics, typography, and analytical prose.

Every agent is backed by local Ollama model instances, guaranteeing complete data sovereignty and zero cloud leakage.

---

## Agent 0: Strategic News Selector

- **Implementation:** [`src/agents/selector.py`](file:///d:/OSINT/src/agents/selector.py)
- **Class:** `NewsSelector`
- **Primary Function:** Filters out noise, scores candidates across strategic intelligence pillars, selects the top 10 articles, executes concurrent deep body scraping, and compiles the consolidated press dossier (`dossier_for_agent_1.txt`).

### Responsibilities
1. **Candidate Preparation:** Queries raw articles for the target date from SQLite, applies regex noise filtering (eliminating sports, showbiz, weather, and trivial accidents), and assigns strategic weights using `IntelligenceTaxonomy`.
2. **Top Article Selection:** Submits scored candidates to the LLM with prompt `SYSTEM_PROMPT_SELECTOR` to identify the 10 most consequential national developments. If LLM selection encounters an issue, automatically falls back to taxonomy score ranking.
3. **Concurrent Deep Scraping:** Spawns a thread pool (up to 5 workers) using `scrape_full_text()` to extract full article bodies and publication metadata.
4. **Consolidated Dossier Generation:** Invokes the LLM with `SYSTEM_PROMPT_DOSSIER` to compile an objective, paragraph-rich Romanian dossier formatting each story under `ȘTIREA [Number]:` with verbatim quotes and source attributions.

### Output Artifact
- Text file: `dossier_for_agent_1.txt` containing formatted, numbered news stories ready for extraction.

---

## Agent 1: Structured Entity Extractor

- **Implementation:** [`src/agents/agent_extractor.py`](file:///d:/OSINT/src/agents/agent_extractor.py)
- **Class:** `EntityExtractorAgent`
- **Primary Function:** Deconstructs the daily press dossier into structured geopolitical events, extracting verifiable actions, verbatim Romanian quotes, and mapping actors to canonical identities.

### Extraction Contract & Schema
The agent enforces strict Pydantic schema validation using `ExtractedEventsContainer`:
```python
class ExtractedEvent(BaseModel):
    actor: str                  # Political actor or institution
    canonical_actor: str        # Resolved canonical identity
    action: str                 # Tactical maneuver or claim (English)
    verbatim_evidence: str      # Exact Romanian quote substring from text
    topic: str                  # Strategic domain / pillar (English)
    source: Optional[str]       # Publishing outlet
    event_hash: Optional[str]   # SHA-256 deduplication hash
```

### Deterministic Event Deduplication
To prevent duplicate records across multiple runs, `ExtractedEvent` calculates an immutable SHA-256 hash across normalized fields:
$$\text{hash} = \text{SHA256}(\text{canonical\_actor} \parallel \text{action} \parallel \text{verbatim\_evidence})$$
Events are inserted into SQLite via `INSERT OR IGNORE`, and unique hashes are enforced by SQLite indexes.

### Canonical Entity Resolution
Extracted actor strings are passed through `EntityResolver.resolve_actor()`, which normalizes diacritics, checks alias registries, and standardizes names (e.g., mapping `"premierul ciolacu"` to `"Marcel Ciolacu"`, `"PSD"` to party entity, etc.).

---

## Agent 2: Historical Archivist & Contradiction Detector

- **Implementation:** [`src/agents/agent_archivist.py`](file:///d:/OSINT/src/agents/agent_archivist.py)
- **Class:** `ArchivistAgent`
- **Primary Function:** Identifies political flip-flops, policy reversals, and broken commitments by comparing today's claims against historical statements stored in vector memory and relational tables.

### Two-Phase Memory Architecture
To avoid self-contradiction bugs where an event is compared against itself, Agent 2 operates in two strictly separated phases:
1. **Phase A (Vector Memory & Pre-fetch):**
   - For every extracted event, performs semantic similarity search in ChromaDB (`n_results=6`) filtered by canonical actor.
   - Falls back to SQLite historical statements (`get_actor_history()`) if vector search yields insufficient history.
   - Only *after* all historical contexts are pre-fetched does Agent 2 batch-index today's events into ChromaDB.
2. **Phase B (Inference & Anomaly Triage):**
   - Submits today's event and pre-fetched historical records to the LLM under `SYSTEM_PROMPT_AGENT_2`.
   - Requires numerical contradiction scoring:
     * `0.0`: Completely consistent (repeats or affirms past stance).
     * `0.1 – 0.4`: Minor rhetorical nuance or timeline adjustment.
     * `0.5 – 0.8`: Significant policy reversal or factual contradiction.
     * `0.9 – 1.0`: Blatant 180-degree flip-flop.
   - Applies automated heuristic filters (`_is_spurious_anomaly()`) to discard false positives where statements merely quote the same event or analyst notes declare consistency.
   - Persists genuine anomalies ($\ge 0.5$) to SQLite `historical_anomalies`.

---

## Agent 3: Hostile Political Strategist (Red Team)

- **Implementation:** [`src/agents/agent_red_team.py`](file:///d:/OSINT/src/agents/agent_red_team.py)
- **Class:** `RedTeamAgent`
- **Primary Function:** Models adversarial geopolitical and electoral dynamics, identifying how rivals can exploit current vulnerabilities.

### Threat Modeling Dimensions
The Red Team agent interrogates the daily events and identified anomalies across three threat vectors:
1. **Vulnerability Assessment:** Which political actor, ministry, or coalition partner is most exposed to scandal, public backlash, or coalition instability?
2. **Narrative Weaponization:** How can an opposition party or hostile foreign actor leverage today's statements or economic indicators tomorrow?
3. **Parasitic Framing:** Is an opposing party hijacking another actor's legislative initiative or tragedy to advance their own agenda?

### Output Schema
Outputs a validated `ThreatVectorsContainer`:
```python
class ThreatVector(BaseModel):
    threat_type: str        # Category: vulnerability, weaponized narrative, parasitic framing
    vulnerable_actor: str   # Actor exposed to risk
    exploiting_actor: str   # Opponent positioned to leverage the opening
    description: str        # Detailed tactical breakdown of the attack vector
```
Validated threat vectors are saved to SQLite `threat_vectors` for radar visualization and relational graph mapping.

---

## Agent 4: Executive Intelligence Director

- **Implementation:** [`src/agents/agent_director.py`](file:///d:/OSINT/src/agents/agent_director.py)
- **Class:** `DirectorAgent`
- **Primary Function:** Synthesizes structured data from Agents 1, 2, and 3 into a high-level, five-section executive briefing written in formal Romanian.

### Analytical Directives
1. **Silence is a Signal:** Treats unexplained silence from major leaders during crises as tactical maneuvering or backdoor deal-making rather than lack of interest.
2. **Parasitic Framing Awareness:** Distinguishes between temporary tactical voting alignments and subterranean ideological coalitions.
3. **Weaponized Contradictions:** Explicitly incorporates recorded flip-flops to explain defensive posturing.
4. **Cold Analytical Objectivity:** Employs dispassionate intelligence tradecraft, focusing on power leverage, perception management, and institutional risk.
5. **Tactical vs. Ideological Convergence:** Avoids conspiracy conjecture by treating rival claims of secret deals as weaponized rhetoric unless corroborated by evidence.

### Document Structure Standard
1. `# 🇷🇴 Sinteza Politică Locală: [Data Naturală]`
2. `## 1. REZUMATUL ZILEI (TL;DR)` — 3 dense, impactful sentences.
3. `## 2. DINAMICA PUTERII ȘI ALIANȚE SUBTERANE` — Analysis of coalition friction, quiet maneuvers, and voting alignments.
4. `## 3. EXPLOATAREA EVENIMENTELOR SOCIALE (Black Swan Tracking)` — Management and exploitation of economic or infrastructure crises.
5. `## 4. PREDICȚII ȘI ANOMALII PENTRU MÂINE` — Exactly 5 forward-looking monitoring items, each with a Title, numerical Confidence Score (0–100%), and analytical Justification, followed by an overall Volatility Level (`Scăzut`, `Mediu`, or `Ridicat`).
6. `## 5. SURSE ȘI METODOLOGIE` — Human-readable list of tracked media sources and institutional events.

---

## Agent 5: Romanian Copyeditor & Grammar Proofreader

- **Implementation:** [`src/agents/agent_copyeditor.py`](file:///d:/OSINT/src/agents/agent_copyeditor.py)
- **Class:** `CopyeditorAgent`
- **Primary Function:** Cleans Romanian typographical errors, standardizes diacritics (`ă`, `â`, `î`, `ș`, `ț`), verifies markdown formatting, and saves the final briefing artifact.

### Quality Invariants
1. **Content Invariance:** Strictly prohibited from altering analytical conclusions, confidence scores, or predictions.
2. **Typography Normalization:** Fixes common OCR and web-scraping artifacts (e.g., converting obsolete characters or malformed diacritics).
3. **Artifact Persistence:** Writes the finalized report to `reports/Sinteza_Politica_YYYY-MM-DD.md` using UTF-8 encoding.

---

## Agent Execution Matrix

| Agent | Input Artifact | Output Artifact | Primary LLM Task | Structured Schema |
|---|---|---|---|---|
| **Selector** | Raw SQLite articles | `dossier_for_agent_1.txt` | Strategic relevance scoring & dense summary | JSON list / Plain text dossier |
| **Agent 1 (Extractor)** | Press dossier | `ExtractedEventsContainer` | Named entity recognition & verbatim quote extraction | `ExtractedEventsContainer` |
| **Agent 2 (Archivist)** | Extracted events + ChromaDB history | `HistoricalAnomaliesContainer` | Contradiction scoring & flip-flop detection | `HistoricalAnomaliesContainer` |
| **Agent 3 (Red Team)** | Extracted events + Anomalies | `ThreatVectorsContainer` | Hostile exploitation & parasitic framing analysis | `ThreatVectorsContainer` |
| **Agent 4 (Director)** | Events, Anomalies, Threats, Articles | Raw Markdown Briefing | Strategic intelligence synthesis in Romanian | Unstructured Markdown |
| **Agent 5 (Copyeditor)**| Raw Markdown Briefing | `reports/Sinteza_Politica_*.md` | Diacritics correction & typography polish | Polished Markdown |

---

## Component-Specific Decisions & Trade-offs

1. **Structured Outputs via Pydantic Schemas:**
   - *Decision:* Agents 1, 2, and 3 use `generate_structured()` with Pydantic JSON schemas passed into Ollama's `format` parameter.
   - *Rationale:* Eliminates JSON decoding failures and guarantees strongly-typed fields.
2. **Separation of Extractor and Archivist:**
   - *Decision:* Agent 1 only parses the current text; Agent 2 is dedicated exclusively to historical memory comparison.
   - *Rationale:* Keeps prompt tokens focused and avoids hallucinations during entity recognition.
3. **Deterministic Hash Invalidation:**
   - *Decision:* Event hashes are recomputed after canonical entity resolution.
   - *Rationale:* Ensures that variations in media spelling of political actors resolve to identical unique keys.

---

## Operational Notes

- **Context Window Guarantee:** All agent calls inherit `num_ctx = 131072`, ensuring full dossiers and historical context never overflow the LLM buffer.
- **Thinking Token Emission:** Ollama's internal thinking tokens (`<think>...</think>`) are parsed and streamed in real-time via the Event Bus for UI transparency.
- **Cancellation Checkpoints:** Between agent executions, the orchestrator checks `event_bus.is_cancelled()` to allow immediate, graceful pipeline halting.

---

## Appendix: Key Code Locations

- `src/agents/selector.py` — Strategic candidate scoring and dossier compiler
- `src/agents/agent_extractor.py` — Entity Extractor agent and canonical entity mapper
- `src/agents/agent_archivist.py` — Archivist agent and vector contradiction detector
- `src/agents/agent_red_team.py` — Red Team hostile strategist agent
- `src/agents/agent_director.py` — Executive Intelligence Director synthesis agent
- `src/agents/agent_copyeditor.py` — Romanian copyeditor and diacritics proofreader
- `src/models/intelligence.py` — Core Pydantic intelligence schemas

---

_Generated by Kipi — Core-Knowledge Keeper_
