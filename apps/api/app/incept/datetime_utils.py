"""UTC clock helpers that preserve the application's existing naive-UTC schema."""

from datetime import UTC, datetime


def utcnow_naive() -> datetime:
    """Return UTC without tzinfo for compatibility with persisted model fields."""
    return datetime.now(UTC).replace(tzinfo=None)
