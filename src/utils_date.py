"""Canonical date handling, timezone normalization, and validation utilities.

All date operations are anchored to Europe/Bucharest for day-bucketing and
ISO-8601 UTC for precise timestamps.
"""

from datetime import datetime, timezone
import logging
import re
import time
from typing import Dict, Optional, Tuple, Union
from zoneinfo import ZoneInfo
from dateutil import parser as dateutil_parser

logger = logging.getLogger(__name__)

# Canonical timezones
RO_TZ = ZoneInfo("Europe/Bucharest")
UTC_TZ = timezone.utc

RO_MONTHS_MAP: Dict[str, int] = {
    "ianuarie": 1, "ian": 1,
    "februarie": 2, "feb": 2,
    "martie": 3, "mar": 3,
    "aprilie": 4, "apr": 4,
    "mai": 5,
    "iunie": 6, "iun": 6,
    "iulie": 7, "iul": 7,
    "august": 8, "aug": 8,
    "septembrie": 9, "sep": 9, "sept": 9,
    "octombrie": 10, "oct": 10,
    "noiembrie": 11, "noi": 11,
    "decembrie": 12, "dec": 12,
}


def get_bucharest_now() -> datetime:
    """Return current datetime in Europe/Bucharest timezone."""
    return datetime.now(RO_TZ)


def get_bucharest_today_str() -> str:
    """Return today's date formatted as YYYY-MM-DD in Europe/Bucharest."""
    return get_bucharest_now().strftime("%Y-%m-%d")


def format_romanian_date(dt_or_str: Optional[Union[datetime, str]] = None) -> str:
    """Format datetime or ISO/European date string into Romanian text (e.g. '6 Noiembrie 2026')."""
    if dt_or_str is None:
        dt = get_bucharest_now()
    elif isinstance(dt_or_str, datetime):
        dt = dt_or_str
    elif isinstance(dt_or_str, str):
        clean = dt_or_str.strip()
        parsed = None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y"):
            try:
                parsed = datetime.strptime(clean, fmt)
                break
            except ValueError:
                continue
        if not parsed:
            try:
                parsed = dateutil_parser.parse(clean, dayfirst=True)
            except Exception:
                parsed = get_bucharest_now()
        dt = parsed
    else:
        dt = get_bucharest_now()

    ro_month_names = {
        1: "Ianuarie", 2: "Februarie", 3: "Martie", 4: "Aprilie",
        5: "Mai", 6: "Iunie", 7: "Iulie", 8: "August",
        9: "Septembrie", 10: "Octombrie", 11: "Noiembrie", 12: "Decembrie"
    }
    return f"{dt.day} {ro_month_names.get(dt.month, '')} {dt.year}"


def get_utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC_TZ).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_published_datetime(
    entry_dict: Optional[Dict] = None,
    raw_date_str: Optional[str] = None
) -> Tuple[Optional[str], Optional[str], bool]:
    """Parse publication date into canonical ISO-8601 UTC and Europe/Bucharest date.

    Returns:
        Tuple of (published_at_utc, published_date_bucharest, is_estimated)
        If unparseable or missing, returns (None, None, True).
        Never silently substitutes today's date.
    """
    # 1. Try feedparser parsed struct_time (feedparser always converts to UTC tuple)
    if entry_dict:
        parsed_time = entry_dict.get("published_parsed") or entry_dict.get("updated_parsed")
        if parsed_time:
            try:
                dt_utc = datetime(*parsed_time[:6], tzinfo=UTC_TZ)
                published_at = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
                published_date = dt_utc.astimezone(RO_TZ).strftime("%Y-%m-%d")
                return published_at, published_date, False
            except Exception as e:
                logger.debug("Failed parsing struct_time: %s", e)

    candidate = raw_date_str
    if not candidate and entry_dict:
        candidate = entry_dict.get("published") or entry_dict.get("updated")

    if not candidate or not str(candidate).strip():
        return None, None, True

    candidate_str = str(candidate).strip()

    # 2. Check for Romanian textual date, e.g., '14 Iunie 2026' or '14 Iunie 2026, 15:30'
    ro_match = re.search(
        r"(\d{1,2})\s+([a-zA-ZăâîșțĂÂÎȘȚ]+)\s+(\d{4})(?:[,\s]+(\d{1,2}):(\d{2}))?",
        candidate_str
    )
    if ro_match:
        day = int(ro_match.group(1))
        month_word = ro_match.group(2).lower()
        year = int(ro_match.group(3))
        hour = int(ro_match.group(4)) if ro_match.group(4) else 0
        minute = int(ro_match.group(5)) if ro_match.group(5) else 0

        if month_word in RO_MONTHS_MAP:
            month = RO_MONTHS_MAP[month_word]
            try:
                dt_ro = datetime(year, month, day, hour, minute, tzinfo=RO_TZ)
                published_at = dt_ro.astimezone(UTC_TZ).strftime("%Y-%m-%dT%H:%M:%SZ")
                published_date = dt_ro.strftime("%Y-%m-%d")
                return published_at, published_date, False
            except Exception:
                pass

    # 3. Check for exact ISO YYYY-MM-DD match without timezone
    iso_ymd = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", candidate_str)
    if iso_ymd:
        year, month, day = int(iso_ymd.group(1)), int(iso_ymd.group(2)), int(iso_ymd.group(3))
        try:
            dt_ro = datetime(year, month, day, 0, 0, tzinfo=RO_TZ)
            published_at = dt_ro.astimezone(UTC_TZ).strftime("%Y-%m-%dT%H:%M:%SZ")
            published_date = f"{year:04d}-{month:02d}-{day:02d}"
            return published_at, published_date, False
        except Exception:
            pass

    # 4. General parser (handles RFC 822, ISO 8601 with tz, European DD/MM/YYYY, etc.)
    try:
        # If candidate starts with 4-digit year (e.g. 2026-11-06), year is first.
        # Otherwise for European news dates (e.g. 06/11/2026 or 06.11.2026), ensure dayfirst=True.
        if re.match(r"^\d{4}[-/.]", candidate_str):
            dt = dateutil_parser.parse(candidate_str, yearfirst=True, dayfirst=False)
        else:
            dt = dateutil_parser.parse(candidate_str, dayfirst=True)

        if dt.tzinfo is None:
            # Naive timestamp from Romanian media: assume Europe/Bucharest
            dt = dt.replace(tzinfo=RO_TZ)
        dt_utc = dt.astimezone(UTC_TZ)
        published_at = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        published_date = dt.astimezone(RO_TZ).strftime("%Y-%m-%d")
        return published_at, published_date, False
    except Exception as e:
        logger.debug("dateutil failed to parse '%s': %s", candidate_str, e)

    # If unparseable, return None + is_estimated=True
    return None, None, True


def validate_target_date(date_str: Optional[str]) -> str:
    """Validate that a date parameter is valid YYYY-MM-DD and not in the future.

    If None, returns today's date in Europe/Bucharest.
    Raises ValueError with descriptive message for invalid or future dates.
    """
    today_str = get_bucharest_today_str()
    if not date_str or not date_str.strip():
        return today_str

    clean_str = date_str.strip()
    try:
        parsed_dt = datetime.strptime(clean_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"Invalid date format: '{clean_str}'. Expected format is YYYY-MM-DD.")

    today_date = get_bucharest_now().date()
    if parsed_dt > today_date:
        raise ValueError(
            f"Target date '{clean_str}' cannot be in the future. "
            f"Current date in Europe/Bucharest is {today_str}."
        )

    return clean_str
