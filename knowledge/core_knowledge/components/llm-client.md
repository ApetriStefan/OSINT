# LLM Client & Inference Engine

> **Summary:** Technical specification of the Ollama client wrapper, context window guarantee (131,072 tokens), thinking token streaming, and structured Pydantic JSON extraction.

**Status:** 🟩 Stable  
**Owner role:** Machine Learning Engineer (link to [ownership-map.md](../team_and_stakeholders/ownership-map.md))  
**Last updated:** 2026-11-06  

---

## Table of Contents

- [Overview](#overview)
- [Context Window Guarantee (131,072 Tokens)](#context-window-guarantee-131072-tokens)
- [OllamaClient Architecture](#ollamaclient-architecture)
- [Thinking Token Parsing & Live Streaming](#thinking-token-parsing--live-streaming)
- [Structured JSON Generation via Pydantic Schemas](#structured-json-generation-via-pydantic-schemas)
- [Public Interface](#public-interface)
- [Component-Specific Decisions & Trade-offs](#component-specific-decisions--trade-offs)
- [Operational Notes](#operational-notes)
- [Appendix: Key Code Locations](#appendix-key-code-locations)

---

## Overview

The LLM client subsystem ([`src/llm/client.py`](file:///d:/OSINT/src/llm/client.py)) acts as the intelligent inference interface for the entire multi-agent suite. It communicates directly with the local Ollama instance, enforces context window parameters, extracts reasoning streams in real time, guarantees valid JSON responses matching Pydantic models, and executes automated retry backoff during transient inference stalls.

---

## Context Window Guarantee (131,072 Tokens)

A critical architectural invariant of this repository is the absolute guarantee of a **131,072 token context window**:
$$\text{num\_ctx} = 131072$$

### Why 131,072 Tokens are Mandatory
1. **Dossier Density:** The consolidated daily press dossier contains 10 deep full-text articles with extensive political context and verbatim quotations, easily exceeding standard 4k or 8k token windows.
2. **Historical Cross-Referencing:** When Agent 2 compares today's events against multiple historical records, the concatenated prompt requires tens of thousands of tokens.
3. **Multi-Agent Memory Continuity:** Prevents silent truncation, incomplete JSON outputs, and loss of critical national security details.

### Tri-Layer Enforcement
The 131,072 parameter is locked across three distinct levels:
1. **Environment Configuration (`.env`):** `NUM_CTX=131072`
2. **Central Settings (`src/config.py`):** `num_ctx: int = Field(default=131072)`
3. **Payload Construction (`src/llm/client.py`):** Explicitly sent in every Ollama request under `options.num_ctx`:
   ```python
   payload["options"] = {
       "temperature": temp,
       "top_p": p_val,
       "num_ctx": 131072,
       "keep_alive": "30m"
   }
   ```

---

## OllamaClient Architecture

- **Primary Generative Model:** `gemma-4-e4b`
- **Embedding Model:** `nomic-embed-text` (dim=768)
- **Base URL:** `http://localhost:11434` (default)
- **Inference Persistence:** `keep_alive: "30m"` keeps model weights loaded in VRAM, eliminating warm-up latency between sequential pipeline stages.
- **Retry Backoff:** Exponential backoff (`max_retries = 3`, `backoff_factor = 2.0`) catching connection drops or temporary timeouts.

---

## Thinking Token Parsing & Live Streaming

Modern reasoning models emit internal chain-of-thought monologues. The client captures and bifurcates these tokens:

### 1. Dedicated Thinking Tokens (`think: True`)
When Ollama returns native thinking fragments in `chunk["message"]["thinking"]`:
- Streamed directly to `stdout`.
- Published to the event bus as `event_type="thinking"`.
- Routed to the web dashboard's dedicated collapsible thinking drawer.

### 2. Inline `<think>` Tag Separation
If the model emits reasoning blocks directly inside the content body:
- The streaming parser detects `<think>` and `</think>` tags in real-time.
- Automatically transitions event emission between `event_type="thinking"` and `event_type="token"`.

### 3. Final Content Cleaning (`clean_thinking_tokens`)
Before returning the final generated string to calling agents, `clean_thinking_tokens()` strips any remaining `<think>...</think>` blocks, ensuring subsequent parsing receives clean, pure data.

---

## Structured JSON Generation via Pydantic Schemas

To prevent JSON parsing failures and schema drift, `OllamaClient.generate_structured()` uses a two-phase contract:

### Phase 1: Native Schema Enforcement
The Pydantic model's JSON Schema is extracted via `response_model.model_json_schema()` and injected into Ollama's `format` parameter. This forces the model's logits to conform strictly to the specified schema:
```python
container = llm_client.generate_structured(
    system_prompt=SYSTEM_PROMPT_AGENT_1,
    user_prompt=dossier_text,
    response_model=ExtractedEventsContainer,
    temperature=0.0
)
```

### Phase 2: Robust Extraction & Validation
If the raw model output includes markdown code fences (e.g. ` ```json ... ``` `) or introductory commentary, `extract_json_from_text()` extracts the outermost JSON object by scanning for balanced braces `{...}` or brackets `[...]`. The resulting JSON string is then validated and returned as a typed Pydantic instance.

---

## Public Interface

```python
client = OllamaClient(base_url=None, model=None, num_ctx=131072)

# Health verification
is_up = client.is_healthy() -> bool

# Free-form streaming generation
output_text = client.generate(
    system_prompt: str,
    user_prompt: str,
    temperature: Optional[float] = 0.0,
    top_p: Optional[float] = 0.1,
    json_schema: Optional[Union[Dict, str]] = None,
    stream: bool = True,
    agent_name: str = "",
    run_id: str = ""
) -> str

# Typed structured generation
model_instance = client.generate_structured(
    system_prompt: str,
    user_prompt: str,
    response_model: Type[T],
    temperature: Optional[float] = 0.0,
    agent_name: str = "",
    run_id: str = ""
) -> T
```

---

## Component-Specific Decisions & Trade-offs

1. **Deterministic Sampling (`temperature = 0.0`):**
   - *Decision:* Entity extraction, selection, and copyediting use `temperature = 0.0` and `top_p = 0.1`.
   - *Rationale:* Eliminates stochastic variation; guarantees reproducible entity extraction and quote fidelity across runs.
2. **Fallback Pydantic Validation:**
   - *Decision:* If direct `model_validate_json()` fails, the client attempts `json.loads()` followed by `model_validate()`.
   - *Rationale:* Resolves minor Unicode or encoding nuances without throwing runtime exceptions.

---

## Operational Notes

- **Model Verification:** Verified before every run; if Ollama is unreachable, `client.is_healthy()` reports false and the UI displays an actionable warning banner.
- **Unit Tested:** Token cleaning, JSON extraction, 131k context window preservation, and structured generation are verified in `tests/unit/test_llm_client.py`.

---

## Appendix: Key Code Locations

- `src/llm/client.py` — OllamaClient, clean_thinking_tokens, and extract_json_from_text
- `src/config.py` — Central settings enforcing num_ctx=131072
- `tests/unit/test_llm_client.py` — LLM client unit tests

---

_Generated by Kipi — Core-Knowledge Keeper_
