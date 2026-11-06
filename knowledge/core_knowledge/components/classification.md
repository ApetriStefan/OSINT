# Classification & Entity Resolution

> **Summary:** Technical specification of the 5-pillar strategic intelligence taxonomy, regular expression noise filters, and canonical Romanian entity resolution engine.

**Status:** 🟩 Stable  
**Owner role:** Classification Specialist (link to [ownership-map.md](../team_and_stakeholders/ownership-map.md))  
**Last updated:** 2026-11-06  

---

## Table of Contents

- [Overview](#overview)
- [The 5-Pillar Strategic Taxonomy](#the-5-pillar-strategic-taxonomy)
- [Weighted Scoring Algorithm](#weighted-scoring-algorithm)
- [Noise Elimination Filters](#noise-elimination-filters)
- [Canonical Entity Resolution](#canonical-entity-resolution)
- [Public Interface](#public-interface)
- [Component-Specific Decisions & Trade-offs](#component-specific-decisions--trade-offs)
- [Operational Notes](#operational-notes)
- [Appendix: Key Code Locations](#appendix-key-code-locations)

---

## Overview

The classification subsystem ([`src/classification/`](file:///d:/OSINT/src/classification/)) ensures that raw media feeds are filtered and categorized before hitting LLM inference stages. It performs three critical operations:
1. **Noise Elimination:** Immediately discards trivial, non-strategic content (sports, showbiz, weather, reality TV).
2. **Pillar Categorization & Prioritization:** Scores articles across five defined strategic intelligence pillars, identifying high-signal events for daily briefings.
3. **Canonical Normalization:** Maps inconsistent entity names, nicknames, and institutional abbreviations across Romanian media outlets to standardized canonical records.

---

## The 5-Pillar Strategic Taxonomy

Implemented in [`src/classification/taxonomy.py`](file:///d:/OSINT/src/classification/taxonomy.py) as `IntelligenceTaxonomy`, the system classifies political and economic reporting into five distinct intelligence domains:

| Pillar Key | Domain Title | Weight | Core Keywords & Conceptual Scope |
|---|---|---|---|
| `domestic_politics` | **Domestic Politics & Governance** | **1.5** | Major party leadership, parliamentary coalitions, motions of no-confidence, cabinet reshuffles, electoral campaigns, presidential administration. |
| `macroeconomy` | **Macroeconomy & Fiscal Policy** | **1.4** | PNRR national recovery funds, fiscal deficits, BNR monetary policy, inflation rates, sovereign debt, public investments, tax reform, ANAF enforcement. |
| `national_security` | **National Security & Defense** | **1.5** | NATO military deployments, Black Sea naval defense, border airspace incursions, MApN procurement, Patriot/F-16 systems, hybrid cyber threats, intelligence services (SRI, SIE). |
| `justice_anticorruption` | **Justice & Anti-Corruption** | **1.3** | DNA and DIICOT prosecutions, judicial appointments, CSM rulings, High Court decisions, constitutional challenges (CCR), legislative corruption probes. |
| `critical_infrastructure` | **Critical Infrastructure & Systemic Crises** | **1.2** | Highway projects (CNAIR), railway transport (CFR), healthcare emergencies, energy grid blackouts, hospital fires, major public sector strikes, TAROM operations. |

---

## Weighted Scoring Algorithm

The taxonomy calculates a numerical relevance score for each article via `IntelligenceTaxonomy.score_article()`:

1. **Diacritics Stripping (`strip_accents`):**
   Normalizes Unicode strings using NFD decomposition, stripping non-spacing combining characters and converting to lowercase. This ensures resilient matching regardless of whether Romanian media uses standard diacritics (`ș`, `ț`, `ă`, `â`, `î`), legacy cedillas, or ASCII characters.
2. **Positional Weighting:**
   - Keyword match in **Title**: Weight = **3.0**
   - Keyword match in **Body / Summary**: Weight = **1.0**
3. **Pillar Weighting:**
   $$\text{Score}_{\text{pillar}} = \left( 3 \times N_{\text{title}} + 1 \times N_{\text{body}} \right) \times W_{\text{pillar}}$$
4. **Primary Pillar Assignment:**
   The article is assigned to the pillar achieving the highest calculated score. If total score exceeds `2.0`, the article is tagged with `[STRATEGIC SIGNAL]` to prioritize it in the press dossier.

---

## Noise Elimination Filters

Romanian news feeds publish high volumes of entertainment, sports, and lifestyle news that deplete LLM tokens and dilute intelligence value. `IntelligenceTaxonomy.is_noise()` enforces strict regex patterns:

### Noise Categories
- **Reality TV & Showbiz:** `\bsurvivor\b`, `\binsula iubirii\b`, `\basia express\b`, `\bchefi la cutite\b`, `\bromanii au talent\b`, `\bvedete\b`, `\bdivort\b`, `\bhoroscop\b`, `\bzodiac\b`, `\bcancan\b`, `\bspynews\b`, `\bmanele\b`, `\bfashion\b`.
- **Sports & Athletics:** `\bfotbal\b`, `\bliga 1\b`, `\bsuperliga\b`, `\bchampions league\b`, `\bfcsb\b`, `\bdinamo\b`, `\brapid\b`, `\bgoluri\b`, `\bmeci\b`, `\bantrenor\b`, `\btransfer\b`, `\btenis\b`, `\bwta\b`, `\batp\b`, `\bsimona halep\b`.
- **Weather & Minor Accidents:** `\bprognoza meteo\b`, `\bcod galben de\b`, `\bcod portocaliu de canicula\b`, `\btamponare\b`, `\baccident rutier usor\b`.

### Strategic Override Protection
To eliminate false positives (e.g., a defense scandal mentioning a former athlete or a premier attending an event), the noise filter will *not* discard an article if it simultaneously contains high-significance national keywords:
`["ciolacu", "premier", "nato", "dna", "pnrr"]`.

---

## Canonical Entity Resolution

News publications refer to the same political actors and institutions using diverse naming conventions, titles, and colloquialisms. The `EntityResolver` ([`src/classification/entity_resolver.py`](file:///d:/OSINT/src/classification/entity_resolver.py)) maps noisy strings to standardized identities:

### Canonical Entity Model
```python
class CanonicalEntity(BaseModel):
    canonical_name: str     # Standardized Romanian name
    entity_type: str        # PERSON, PARTY, INSTITUTION, or OTHER
    party: Optional[str]    # Political party affiliation
    role: Optional[str]     # Primary constitutional or political role
```

### Entity Registry Scope
The resolver maintains an active registry covering key political leaders, major parties, and judicial/executive institutions:
- **Key Political Leaders:** Marcel Ciolacu, Nicolae Ciucă, Ilie Bolojan, Klaus Iohannis, George Simion, Elena Lasconi, Cătălin Drulă, Sorin Grindeanu, Alexandru Rafila, Raluca Turcan, Kelemen Hunor, Diana Șoșoacă, Mircea Geoană, Eugen Tomac, Laura Codruța Kövesi.
- **Political Parties:** PSD, PNL, USR, AUR, UDMR.
- **Constitutional Institutions:** DNA (Direcția Națională Anticorupție), CCR (Curtea Constituțională a României), CSM (Consiliul Superior al Magistraturii), Guvernul României.

### Resolution Logic
1. **Exact Normalized Alias Match:** Compares normalized candidate string against pre-compiled alias lists.
2. **Substring Containment Match:** Resolves informal references (e.g., `"generalul ciuca"` $\to$ `"Nicolae Ciucă"`).
3. **Sanitized Fallback:** If unknown, returns cleaned title-cased name tagged as `PERSON` (multi-word) or `OTHER` (single-word).

---

## Public Interface

```python
# Strip diacritics
clean_text = strip_accents(text: str) -> str

# Evaluate noise
is_noisy = IntelligenceTaxonomy.is_noise(title: str, text: str = "") -> bool

# Score article across pillars
total_score, primary_pillar, pillar_scores = IntelligenceTaxonomy.score_article(
    title: str, summary: str = "", text: str = ""
) -> Tuple[float, Optional[str], Dict[str, float]]

# Resolve entity
canonical_info = EntityResolver.resolve_actor(raw_actor: str) -> CanonicalEntity
```

---

## Component-Specific Decisions & Trade-offs

1. **Deterministic Regex vs. LLM Filtering:**
   - *Decision:* Noise filtering is handled purely via regular expressions rather than an initial LLM triage call.
   - *Rationale:* Eliminates inference latency and saves compute tokens; processes hundreds of articles per second deterministically.
2. **3x Title Weighting:**
   - *Decision:* Title keywords are weighted at 3.0 compared to 1.0 for body keywords.
   - *Rationale:* Romanian news headlines prominently highlight the primary political subject; weighting body text equally caused false matches from incidental mentions.

---

## Operational Notes

- **Diacritics Invariance:** The taxonomy operates completely transparently across Unicode diacritics variants (`ș`/`ş`, `ț`/`ţ`).
- **Regression Tested:** Verified under `tests/unit/test_taxonomy.py` and `tests/unit/test_entity_resolver.py`.

---

## Appendix: Key Code Locations

- `src/classification/taxonomy.py` — IntelligenceTaxonomy class, keyword weights, and noise patterns
- `src/classification/entity_resolver.py` — EntityResolver and canonical registry
- `tests/unit/test_taxonomy.py` — Noise elimination and scoring unit tests
- `tests/unit/test_entity_resolver.py` — Canonical actor and party resolution tests

---

_Generated by Kipi — Core-Knowledge Keeper_
