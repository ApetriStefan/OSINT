"""Web scraping and article body text extractor."""

import logging
import re
from typing import Optional, Tuple
from bs4 import BeautifulSoup
import requests

from src.config import get_settings

logger = logging.getLogger(__name__)


def extract_metadata_date(soup: BeautifulSoup) -> Optional[str]:
    """Extract published date from article HTML metadata tags."""
    meta_tags = [
        soup.find("meta", attrs={"property": "article:published_time"}),
        soup.find("meta", attrs={"name": "publish-date"}),
        soup.find("meta", attrs={"property": "og:pubdate"}),
        soup.find("meta", attrs={"itemprop": "datePublished"}),
        soup.find("meta", attrs={"name": "pubdate"}),
        soup.find("meta", attrs={"property": "og:article:published_time"}),
    ]
    for tag in meta_tags:
        if tag:
            content = tag.get("content", tag.get("value", ""))
            match = re.search(r"\d{4}-\d{2}-\d{2}", content)
            if match:
                return match.group(0)

    time_tag = soup.find("time", attrs={"datetime": True})
    if time_tag:
        match = re.search(r"\d{4}-\d{2}-\d{2}", time_tag["datetime"])
        if match:
            return match.group(0)
    return None


def extract_article_from_html(html: str, max_chars: int = 8000) -> Tuple[str, Optional[str]]:
    """Clean and extract article paragraphs and publication date from raw HTML string."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove script, style, navigation, footer, and iframe tags
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript"]):
        tag.decompose()

    published_date = extract_metadata_date(soup)

    paragraphs = soup.find_all("p")
    cleaned_paragraphs = []
    for p in paragraphs:
        text = " ".join(p.get_text().split())
        # Filter out cookie disclaimers, tiny UI elements, and ads
        if len(text) > 30 and not any(kw in text.lower() for kw in ["cookie", "politica de confidentialitate", "toate drepturile rezervate"]):
            cleaned_paragraphs.append(text)

    body_text = "\n\n".join(cleaned_paragraphs)[:max_chars]
    return body_text, published_date


def scrape_full_text(
    url: str,
    session: Optional[requests.Session] = None,
    timeout: Optional[int] = None,
    max_chars: int = 8000
) -> Optional[str]:
    """Fetch URL and extract the cleaned article body text."""
    settings = get_settings()
    timeout = timeout or settings.request_timeout
    headers = {"User-Agent": settings.user_agent}

    try:
        if session:
            resp = session.get(url, timeout=timeout)
        else:
            resp = requests.get(url, headers=headers, timeout=timeout)

        if resp.status_code == 200:
            text, _ = extract_article_from_html(resp.text, max_chars=max_chars)
            return text if text.strip() else None
        logger.warning("Failed to scrape %s: HTTP %d", url, resp.status_code)
    except Exception as e:
        logger.warning("Error scraping article %s: %s", url, e)

    return None
