"""Shared time helper for domain entities."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return the current moment as a timezone-aware UTC datetime."""
    return datetime.now(UTC)
