"""Unit tests for RSS scraper date parsing and HTML cleaning."""

import time
from datetime import datetime
import pytest

from src.scrapers.rss_scraper import parse_published_date, clean_html


def test_clean_html():
    """Verify HTML tag stripping and whitespace normalization."""
    raw = "<p>Aceasta este o <b>știre</b> de test &nbsp; cu <i>diacritice</i>.</p>"
    cleaned = clean_html(raw)
    assert "<" not in cleaned
    assert ">" not in cleaned
    assert "Aceasta este o știre de test &nbsp; cu diacritice." == cleaned

    # Empty and None input handling
    assert clean_html(None) == ""
    assert clean_html("") == ""


def test_parse_iso_date_string():
    """Verify ISO 8601 date parsing."""
    date_str = "2026-06-14T15:30:00+03:00"
    parsed = parse_published_date(raw_date_str=date_str)
    assert parsed == "2026-06-14"

    raw_date = "2025-11-20"
    assert parse_published_date(raw_date_str=raw_date) == "2025-11-20"


def test_parse_feedparser_struct_time():
    """Verify feedparser time struct extraction."""
    st = time.strptime("2026-08-25 10:00:00", "%Y-%m-%d %H:%M:%S")
    entry = {"published_parsed": st}
    assert parse_published_date(entry_dict=entry) == "2026-08-25"

    entry_updated = {"updated_parsed": st}
    assert parse_published_date(entry_dict=entry_updated) == "2026-08-25"


def test_parse_rfc822_date_string():
    """Verify RFC 822 / email formatted dates."""
    rfc_date = "Mon, 15 Jun 2026 09:20:00 +0300"
    parsed = parse_published_date(raw_date_str=rfc_date)
    assert parsed == "2026-06-15"

    rfc_date_gmt = "Wed, 04 Mar 2026 18:45:12 GMT"
    parsed_gmt = parse_published_date(raw_date_str=rfc_date_gmt)
    assert parsed_gmt == "2026-03-04"


def test_parse_romanian_text_date():
    """Verify parsing Romanian natural language dates."""
    ro_dates = [
        ("14 Iunie 2026", "2026-06-14"),
        ("1 Ianuarie 2026", "2026-01-01"),
        ("28 Februarie 2026", "2026-02-28"),
        ("15 mai 2026", "2026-05-15"),
        ("31 Decembrie 2025", "2025-12-31"),
        ("09 Octombrie 2026", "2026-10-09")
    ]
    for raw_str, expected in ro_dates:
        assert parse_published_date(raw_date_str=raw_str) == expected


def test_parse_date_fallback():
    """Verify fallback when date is missing or invalid."""
    fallback = "2026-01-01"
    assert parse_published_date(raw_date_str="invalid-garbage-date", fallback_date=fallback) == fallback
    assert parse_published_date(entry_dict={}, raw_date_str="", fallback_date=fallback) == fallback

    # Never silently substitute today when no fallback is provided: must return None
    assert parse_published_date(raw_date_str="") is None
    assert parse_published_date(raw_date_str="garbage-non-date") is None


def test_european_date_parsing_dayfirst():
    """Verify European DD/MM/YYYY and DD.MM.YYYY dates parse dayfirst to prevent November from becoming June."""
    from src.utils_date import parse_published_datetime, format_romanian_date

    # 06/11/2026 is 6 November 2026, NOT 11 June 2026
    _, date_str, is_est = parse_published_datetime(raw_date_str="06/11/2026")
    assert date_str == "2026-11-06"
    assert is_est is False

    _, date_dot, is_est_dot = parse_published_datetime(raw_date_str="06.11.2026 14:30")
    assert date_dot == "2026-11-06"
    assert is_est_dot is False

    # format_romanian_date helper
    assert format_romanian_date("2026-11-06") == "6 Noiembrie 2026"
    assert format_romanian_date("2026-06-11") == "11 Iunie 2026"
