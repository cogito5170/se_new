"""Timestamps. All stored and exported times are UTC ISO 8601 with a trailing 'Z'."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


_ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$"
)
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def is_utc_timestamp(value: object) -> bool:
    return isinstance(value, str) and bool(_TIMESTAMP_RE.match(value))


def is_iso8601(value: object) -> bool:
    return isinstance(value, str) and bool(_ISO_RE.match(value))


def normalize_date(raw: str | None) -> str | None:
    """Return an ISO 8601 string or None if `raw` cannot be parsed.

    Date-only values stay date-only ("2026-03-01"). Values with a time are
    converted to UTC ("2026-03-01T09:30:00Z"). Values with a time but no zone
    are kept as-is (zone unknown, so not converted).
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        try:
            datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            return None
        return text
    iso = text.replace(" ", "T", 1) if re.match(r"^\d{4}-\d{2}-\d{2} \d", text) else text
    if iso.endswith("Z"):
        iso = iso[:-1] + "+00:00"
    iso = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", iso)
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        dt = None
    if dt is None:
        try:  # RFC 2822 (RSS pubDate)
            dt = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            return None
    if dt.tzinfo is None:
        return dt.replace(microsecond=0).isoformat()
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
