"""Cloud SQL URL contract tests without any real GCP credentials."""

from __future__ import annotations

import json

import pytest

from app.ai_video.core.database_url import build_cloud_sql_database_url


def test_build_cloud_sql_url_uses_tls_host_outside_cloud_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """A local process uses the secret host instead of an unmounted socket."""
    monkeypatch.delenv("K_SERVICE", raising=False)
    raw = json.dumps({"host": "db.example", "database": "ai_video", "user": "app", "password": "secret"})
    url = build_cloud_sql_database_url(raw)
    assert url.startswith("postgresql+asyncpg://app:***@db.example:5432/ai_video")
    assert "ssl=require" in url


def test_build_cloud_sql_url_rejects_incomplete_secret() -> None:
    """The application must fail before opening a partial production connection."""
    with pytest.raises(RuntimeError, match="password"):
        build_cloud_sql_database_url('{"host":"db.example","database":"ai_video","user":"app"}')
