"""RSS feed scraper utilizing requests.Session with connection pooling and robust date parsing."""

import concurrent.futures
import logging
import re
import time
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlparse
import feedparser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dateutil import parser as dateutil_parser

from src.config import get_settings
from src.models.article import RawArticle
from src.utils_date import parse_published_datetime, get_bucharest_today_str

logger = logging.getLogger(__name__)


def clean_html(raw_html: Optional[str]) -> str:
    """Remove HTML tags and condense multiple whitespace characters."""
    if not raw_html:
        return ""
    clean_regex = re.compile(r"<.*?>")
    clean_text = re.sub(clean_regex, "", raw_html)
    return " ".join(clean_text.split())


def parse_published_date(
    entry_dict: Optional[Dict] = None,
    raw_date_str: Optional[str] = None,
    fallback_date: Optional[str] = None
) -> Optional[str]:
    """Parse publication date into Europe/Bucharest YYYY-MM-DD format.

    Maintains backwards compatibility. If fallback_date is explicitly supplied
    and the date cannot be parsed, returns fallback_date; otherwise returns None
    for unparseable dates.
    """
    _, pub_date_ro, is_est = parse_published_datetime(entry_dict=entry_dict, raw_date_str=raw_date_str)
    if pub_date_ro is not None:
        return pub_date_ro
    return fallback_date


class RSSScraper:
    """Production RSS scraper with session connection pooling, retry policies, and clean models."""

    def __init__(self, feeds: Optional[Dict[str, str]] = None, timeout: Optional[int] = None) -> None:
        settings = get_settings()
        self.feeds = feeds or settings.rss_feeds
        self.timeout = timeout or settings.request_timeout
        self.user_agent = settings.user_agent

        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=20)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update({"User-Agent": self.user_agent})

    def fetch_feed(self, source_name: str, feed_url: str) -> List[RawArticle]:
        """Fetch and parse entries for a single RSS feed."""
        articles: List[RawArticle] = []
        try:
            response = self.session.get(feed_url, timeout=self.timeout)
            if response.status_code != 200:
                logger.warning("Failed to fetch RSS for %s (%s): HTTP %d", source_name, feed_url, response.status_code)
                return []

            parsed_feed = feedparser.parse(response.content)
            for entry in parsed_feed.entries:
                link = entry.get("link", "").strip()
                title = entry.get("title", "").strip()
                if not link or not title:
                    continue

                raw_summary = entry.get("summary") or entry.get("description") or ""
                summary = clean_html(raw_summary)
                pub_at_utc, pub_date_ro, is_est = parse_published_datetime(entry_dict=entry)

                articles.append(
                    RawArticle(
                        source_name=source_name,
                        title=title,
                        link=link,
                        summary=summary,
                        published_at=pub_at_utc,
                        published_date=pub_date_ro,
                        is_date_estimated=is_est
                    )
                )
        except requests.exceptions.Timeout:
            logger.error("Timeout fetching RSS feed from %s", source_name)
        except Exception as e:
            logger.error("Error fetching feed from %s: %s", source_name, e)

        return articles

    def fetch_all(self) -> List[RawArticle]:
        """Scrape all configured RSS feeds concurrently and return collected raw articles."""
        all_articles: List[RawArticle] = []
        if not self.feeds:
            return all_articles

        max_workers = min(len(self.feeds), 10)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_source = {
                executor.submit(self.fetch_feed, source_name, feed_url): source_name
                for source_name, feed_url in self.feeds.items()
            }
            for future in concurrent.futures.as_completed(future_to_source):
                source_name = future_to_source[future]
                try:
                    feed_articles = future.result()
                    logger.info("Fetched %d articles from %s", len(feed_articles), source_name)
                    all_articles.extend(feed_articles)
                except Exception as e:
                    logger.error("Error fetching feed from %s: %s", source_name, e)

        return all_articles
