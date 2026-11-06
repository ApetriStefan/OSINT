"""Regression tests for date normalization, timezone boundaries, and date validation."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pytest

from src.models.article import RawArticle
from src.storage.db_manager import DBManager
from src.utils_date import (
    RO_TZ,
    UTC_TZ,
    get_bucharest_now,
    get_bucharest_today_str,
    parse_published_datetime,
    validate_target_date,
)


def test_timezone_boundary_crossing():
    """Verify that a late-night UTC timestamp crosses into the next day in Europe/Bucharest (UTC+2 / UTC+3)."""
    # 22:30 UTC on June 14th is 01:30 on June 15th in Bucharest (EEST = UTC+3)
    utc_str = "2026-06-14T22:30:00Z"
    pub_at, pub_date, is_est = parse_published_datetime(raw_date_str=utc_str)

    assert is_est is False
    assert pub_at == "2026-06-14T22:30:00Z"
    assert pub_date == "2026-06-15", "Expected June 15 in Europe/Bucharest for 22:30 UTC on June 14"


def test_rfc822_with_offsets():
    """Verify parsing RFC 822 / 2822 dates with varied positive and negative timezone offsets."""
    # Offset +0300 (EEST)
    rfc_pos = "Sun, 14 Jun 2026 23:45:00 +0300"
    pub_at, pub_date, is_est = parse_published_datetime(raw_date_str=rfc_pos)
    assert is_est is False
    assert pub_at == "2026-06-14T20:45:00Z"
    assert pub_date == "2026-06-14"

    # Negative offset -0400 (EDT): 23:45 EDT is 03:45 UTC next day, 06:45 next day in Bucharest
    rfc_neg = "Sun, 14 Jun 2026 23:45:00 -0400"
    pub_at, pub_date, is_est = parse_published_datetime(raw_date_str=rfc_neg)
    assert is_est is False
    assert pub_at == "2026-06-15T03:45:00Z"
    assert pub_date == "2026-06-15"


def test_romanian_text_dates_with_and_without_time():
    """Verify Romanian textual dates are correctly anchored to Europe/Bucharest."""
    # Date with time
    dt_with_time = "14 Iunie 2026, 14:30"
    pub_at, pub_date, is_est = parse_published_datetime(raw_date_str=dt_with_time)
    assert is_est is False
    assert pub_date == "2026-06-14"
    assert pub_at.startswith("2026-06-14T")

    # Date only
    dt_only = "28 Februarie 2026"
    pub_at, pub_date, is_est = parse_published_datetime(raw_date_str=dt_only)
    assert is_est is False
    assert pub_date == "2026-02-28"


def test_missing_and_corrupt_dates_do_not_default_to_today():
    """Verify missing or corrupt dates return None and flag is_estimated=True (no silent substitution)."""
    cases = [None, "", "   ", "not-a-valid-date", "2026-99-99", "ieri la pranz"]
    for case in cases:
        pub_at, pub_date, is_est = parse_published_datetime(raw_date_str=case)
        assert pub_at is None, f"Expected None pub_at for {case}"
        assert pub_date is None, f"Expected None pub_date for {case}"
        assert is_est is True, f"Expected is_est=True for {case}"


def test_validate_target_date_semantics():
    """Verify validation of API/CLI date parameter."""
    today_ro = get_bucharest_today_str()

    # None or empty string resolves to today in Europe/Bucharest
    assert validate_target_date(None) == today_ro
    assert validate_target_date("") == today_ro
    assert validate_target_date("   ") == today_ro

    # Past valid date
    assert validate_target_date("2026-01-15") == "2026-01-15"

    # Future date rejected with ValueError
    future_date = (get_bucharest_now() + timedelta(days=5)).strftime("%Y-%m-%d")
    with pytest.raises(ValueError, match="cannot be in the future"):
        validate_target_date(future_date)

    # Malformed formats rejected
    with pytest.raises(ValueError, match="Invalid date format"):
        validate_target_date("15/06/2026")
    with pytest.raises(ValueError, match="Invalid date format"):
        validate_target_date("2026-13-45")


def test_db_date_filtering_select_stage(db_manager: DBManager):
    """Verify that database queries strictly filter by Europe/Bucharest date and handle NULL dates."""
    target_date = "2026-06-14"

    art_target = RawArticle(
        source_name="HotNews",
        title="Articol Target",
        link="https://test.ro/target",
        published_at="2026-06-14T10:00:00Z",
        published_date=target_date,
        is_date_estimated=False
    )
    art_other_day = RawArticle(
        source_name="G4Media",
        title="Articol Alta Zi",
        link="https://test.ro/other",
        published_at="2026-06-15T10:00:00Z",
        published_date="2026-06-15",
        is_date_estimated=False
    )
    art_no_date = RawArticle(
        source_name="Digi24",
        title="Articol Fara Data",
        link="https://test.ro/nodate",
        published_at=None,
        published_date=None,
        is_date_estimated=True
    )

    db_manager.insert_raw_articles([art_target, art_other_day, art_no_date])

    # Query target date
    results = db_manager.get_raw_articles_for_date(target_date)
    assert len(results) == 1
    assert results[0].link == "https://test.ro/target"
    assert results[0].published_date == target_date
    assert results[0].is_date_estimated is False
