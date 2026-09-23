"""Shared Application Default Credentials helpers for Vertex adapters."""

from __future__ import annotations


def adc_access_token() -> str:
    """Return a fresh Cloud Platform OAuth token from Application Default Credentials."""
    try:
        import google.auth
        from google.auth.transport.requests import Request
    except ImportError as exc:  # pragma: no cover - installed transitively by google-genai
        raise RuntimeError("google-auth must be installed to enable Vertex generation") from exc
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(Request())
    token = str(credentials.token or "").strip()
    if not token:
        raise RuntimeError("Vertex ADC did not provide an access token")
    return token
