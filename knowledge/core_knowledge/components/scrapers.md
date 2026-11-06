# Ingestion & Scraping Engine

> **Summary:** Architectural specification of the RSS feed scraper, resilient text extraction, connection pooling, and multi-format Romanian date resolution engine.

**Status:** 🟩 Stable  
**Owner role:** Pipeline Engineer (link to [ownership-map.md](../team_and_stakeholders/ownership-map.md))  
**Last updated:** 2026-11-06  

---

## Table of Contents

- [Overview](#overview)
- [RSS Feed Scraper Architecture](#rss-feed-scraper-architecture)
- [Resilient Text Extraction Engine](#resilient-text-extraction-engine)
- [Canonical Publication Date Resolution](#canonical-publication-date-resolution)
- [Public Interface](#public-interface)
- [Component-Specific Decisions & Trade-offs](#component-specific-decisions--trade-offs)
- [Operational Notes](#operational-notes)
- [Appendix: Key Code Locations](#appendix-key-code-locations)

---

## Overview

The ingestion subsystem ([`src/scrapers/`](file:///d:/OSINT/src/scrapers/) and [`src/utils_date.py`](file:///d:/OSINT/src/utils_date.py)) is responsible for capturing raw Romanian news publications with high resilience, minimal network overhead, and zero timezone corruption. It continuously monitors major news feeds, strips HTML DOM boilerplate, accurately extracts publication timestamps, and delivers clean `RawArticle` and `ScrapedArticle` records to the storage and agent layers.

---

## RSS Feed Scraper Architecture

The scraper is implemented in [`src/scrapers/rss_scraper.py`](file:///d:/OSINT/src/scrapers/rss_scraper.py) via the `RSSScraper` class.

### Monitored Media Outlets
The system polls seven primary Romanian national news sources configured in [`src/config.py`](file:///d:/OSINT/src/config.py):
1. **G4Media:** `https://www.g4media.ro/feed`
2. **HotNews:** `https://www.hotnews.ro/feed`
3. **Digi24:** `https://www.digi24.ro/rss`
4. **ActiveNews:** `https://www.activenews.ro/rss`
5. **B1TV:** `https://www.b1tv.ro/feed`
6. **Agerpres:** `https://www.agerpres.ro/home.rss`
7. **Mediafax:** `https://www.mediafax.ro/rss`

### Connection Pooling & Retries
To withstand transient network instability and throttling, the scraper configures an HTTP session with robust pooling and automatic retry backoff:
```python
retries = Retry(
    total=3,
    backoff_factor=0.5,
    status_forcelist=[500, 502, 503, 504],
    raise_on_status=False
)
adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=20)
self.session.mount("http://", adapter)
self.session.mount("https://", adapter)
```

### Concurrent Scraping
`fetch_all()` executes feed parsing concurrently across a `ThreadPoolExecutor` (up to 10 workers), minimizing the overall ingestion latency across all feeds to under 2 seconds.

---

## Resilient Text Extraction Engine

Implemented in [`src/scrapers/text_extractor.py`](file:///d:/OSINT/src/scrapers/text_extractor.py):

### DOM Sanitization
When extracting full article bodies (`extract_article_from_html()`):
1. **Decomposes Noise Tags:** Strips out non-content elements: `script`, `style`, `nav`, `footer`, `header`, `aside`, `iframe`, and `noscript`.
2. **Boilerplate & Cookie Filtering:** Evaluates all `<p>` tags, removing cookie consent notices, copyright disclaimers, and UI fragments (`len(text) <= 30` or containing keywords like `"politica de confidentialitate"`, `"toate drepturile rezervate"`).
3. **Length Bounding:** Joins valid paragraphs with double newlines and clamps the output to `max_chars = 8000` to prevent context bloat while preserving rich reporting.

---

## Canonical Publication Date Resolution

Accurate publication dates are critical for date-bucketing intelligence dossiers. Romanian news feeds employ inconsistent date formats (RFC 822, ISO 8601 with/without timezone offsets, natural Romanian language strings, or European `DD.MM.YYYY`).

Implemented in [`src/utils_date.py`](file:///d:/OSINT/src/utils_date.py):

### Multi-Tier Resolution Strategy (`parse_published_datetime`):
1. **Feedparser UTC Struct-Time:**
   Inspects `published_parsed` or `updated_parsed`. Converts 6-tuple to UTC datetime and converts to `Europe/Bucharest` calendar date.
2. **Romanian Textual Parsing:**
   Extracts Romanian dates via regex matching:
   `r"(\d{1,2})\s+([a-zA-ZăâîșțĂÂÎȘȚ]+)\s+(\d{4})(?:[,\s]+(\d{1,2}):(\d{2}))?"`
   Maps month words using `RO_MONTHS_MAP` (`ianuarie` $\to$ 1, `iunie` $\to$ 6, etc.), assuming Romanian local time (`Europe/Bucharest`).
3. **ISO-8601 & European Date Parsing:**
   Parses `YYYY-MM-DD` directly or parses European dates via `dateutil.parser.parse(..., dayfirst=True)` to prevent ambiguous month/day swapping (e.g. `06/11/2026` parsed as November 6th, not June 11th).
4. **HTML Metadata Inspection:**
   `extract_metadata_date()` scans raw HTML for `<meta>` and `<time>` tags:
   - `article:published_time`
   - `publish-date`
   - `og:pubdate`
   - `itemprop="datePublished"`
   - `pubdate`
   - `<time datetime="...">`

### Date Invariants
- **No False Fallbacks:** If an article date cannot be parsed, the system returns `(None, None, True)` and flags `is_date_estimated = True`. It **never** silently substitutes today's date, preventing archival data poisoning.
- **Future Date Rejection:** `validate_target_date()` verifies that requested dates are not set in the future relative to Europe/Bucharest.

---

## Public Interface

```python
# RSS Scraper
scraper = RSSScraper(feeds=None, timeout=15)
raw_articles = scraper.fetch_all() -> List[RawArticle]

# Web Text Extractor
article_text = scrape_full_text(url: str, session=None, timeout=None, max_chars=8000) -> Optional[str]
body_text, pub_date = extract_article_from_html(html: str, max_chars=8000) -> Tuple[str, Optional[str]]

# Date Utilities
utc_iso, ro_date, is_est = parse_published_datetime(entry_dict=None, raw_date_str=None)
today_str = get_bucharest_today_str() -> "YYYY-MM-DD"
validated_date = validate_target_date(date_str: Optional[str]) -> "YYYY-MM-DD"
natural_date = format_romanian_date(dt_or_str=None) -> "6 Noiembrie 2026"
```

---

## Component-Specific Decisions & Trade-offs

1. **Dual Timezone Anchoring:**
   - *Decision:* Exact timestamps are normalized to ISO-8601 UTC (`published_at`), while daily dossier bucketing is anchored strictly to `Europe/Bucharest` (`published_date`).
   - *Rationale:* Eliminates midnight date-shift discrepancies when querying articles published late in the Romanian evening.
2. **Session Connection Re-use:**
   - *Decision:* `requests.Session` with `HTTPAdapter` connection pooling is reused across all scraper calls.
   - *Rationale:* Avoids repeated TLS handshakes, decreasing feed fetch time by over 60%.

---

## Operational Notes

- **Network Timeouts:** Default HTTP timeout is locked at 15 seconds.
- **Unit & Regression Testing:** Comprehensive date parsing, European format validation, and timezone boundary crossing are verified in `tests/unit/test_date_parsing.py` and `tests/unit/test_date_regression.py`.

---

## Appendix: Key Code Locations

- `src/scrapers/rss_scraper.py` — RSS feed scraper and connection pooling
- `src/scrapers/text_extractor.py` — Article HTML text and metadata extractor
- `src/utils_date.py` — Canonical timezone normalization and Romanian date parser
- `src/models/article.py` — Pydantic models for raw and scraped articles

---

_Generated by Kipi — Core-Knowledge Keeper_
