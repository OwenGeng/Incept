"""Server-owned research tools for the Video workspace agent.

The browser catalog used to advertise search and fetch extensions without a
FastAPI execution path.  This module keeps those capabilities inside the
existing API service, validates every external boundary, and restricts agent
writes to the research deliverables defined by the production handbook.
"""

from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import os
import re
import socket
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, quote_plus, urljoin, urlsplit, urlunsplit

import httpx

from . import store


MAX_WEB_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT_CHARS = 500_000
DEFAULT_FETCH_CHARS = 40_000
DEFAULT_SEARCH_RESULTS = 8
DEFAULT_TRANSCRIPT_CHARS = 40_000
MAX_TRANSCRIPT_BYTES = 2 * 1024 * 1024
PROVIDER_COOLDOWN_SECONDS = 60
EVIDENCE_STATUSES = frozenset({"supported", "uncertain", "contradicted"})
ALLOWED_RESEARCH_ARTIFACTS = frozenset(
    {
        "research/video-sample-table.md",
        "research/creative-synthesis.md",
        "intake/brand-product-asset-manifest.md",
        "intake/source-log.md",
        "production/approved-brief.md",
    }
)
_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata.google.com",
    }
)
_BLOCK_TAGS = frozenset({"script", "style", "head", "noscript", "svg", "template"})
_BREAK_TAGS = frozenset({"article", "br", "div", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "li", "main", "p", "section", "tr"})
_YOUTUBE_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"})
_BILIBILI_HOSTS = frozenset({"bilibili.com", "www.bilibili.com", "m.bilibili.com", "b23.tv"})
_SAFE_TRANSCRIPT_HEADERS = frozenset({"origin", "referer", "user-agent"})
_EVIDENCE_LOCK = threading.RLock()
_PROVIDER_HEALTH_LOCK = threading.RLock()
_PROVIDER_HEALTH: dict[str, dict[str, object]] = {}


class ResearchToolError(ValueError):
    """A user-actionable research tool boundary error."""


class SearchProviderError(ResearchToolError):
    """A classified failure from one search provider."""

    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class SearchProvider:
    name: str
    search: Callable[[str, int, float], dict[str, object]]


def _sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat()


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
        json.dump(value, temporary, ensure_ascii=False, indent=2)
        temporary.write("\n")
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def _source_snapshot_path(email: str, project_id: str, source_url: str, content_sha256: str) -> Path:
    snapshot_id = _sha256_text(f"{source_url}\n{content_sha256}")
    return store.safe_asset_path(store.assets_root(email, project_id), f"research/.sources/{snapshot_id}.json")


def _persist_source_snapshot(
    email: str,
    project_id: str,
    result: dict[str, object],
    *,
    source_type: str,
    provider: str,
) -> dict[str, object]:
    source_url = _normalized_http_url(str(result.get("url", "")))
    content = result.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ResearchToolError("Fetched source did not contain recordable text")
    content_sha256 = _sha256_text(content)
    retrieved_at = str(result.get("retrieved_at") or _iso_now())
    snapshot = {
        "url": source_url,
        "retrieved_at": retrieved_at,
        "content_sha256": content_sha256,
        "source_type": source_type,
        "provider": provider,
        "content": content,
    }
    target = _source_snapshot_path(email, project_id, source_url, content_sha256)
    with _EVIDENCE_LOCK:
        if not target.is_file():
            _write_json_atomic(target, snapshot)
    enriched = dict(result)
    enriched.update({key: value for key, value in snapshot.items() if key != "content"})
    enriched["url"] = source_url
    return enriched


def _evidence_ledger_path(email: str, project_id: str) -> Path:
    return store.safe_asset_path(store.assets_root(email, project_id), "research/evidence-ledger.json")


def list_claim_evidence(email: str, project_id: str) -> dict[str, object]:
    target = _evidence_ledger_path(email, project_id)
    with _EVIDENCE_LOCK:
        if not target.is_file():
            return {"evidence": []}
        try:
            value = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ResearchToolError("The claim evidence ledger could not be read") from error
    evidence = value.get("evidence") if isinstance(value, dict) else None
    if not isinstance(evidence, list):
        raise ResearchToolError("The claim evidence ledger is invalid")
    return {"evidence": evidence}


def record_claim_evidence(
    email: str,
    project_id: str,
    *,
    claim: str,
    source_url: str,
    content_sha256: str,
    excerpt: str,
    confidence_status: str,
) -> dict[str, object]:
    claim = " ".join(claim.split())
    excerpt = excerpt.strip()
    if not 1 <= len(claim) <= 2_000:
        raise ResearchToolError("Claim must contain 1 to 2000 characters")
    if not 1 <= len(excerpt) <= 5_000:
        raise ResearchToolError("Evidence excerpt must contain 1 to 5000 characters")
    if not re.fullmatch(r"[0-9a-f]{64}", content_sha256):
        raise ResearchToolError("content_sha256 must be a lowercase SHA-256 value")
    if confidence_status not in EVIDENCE_STATUSES:
        raise ResearchToolError("confidence_status must be supported, uncertain, or contradicted")
    normalized_url = _normalized_http_url(source_url)
    snapshot_path = _source_snapshot_path(email, project_id, normalized_url, content_sha256)
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ResearchToolError("No server-held source snapshot matches this URL and content hash") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ResearchToolError("The source snapshot could not be verified") from error
    content = snapshot.get("content") if isinstance(snapshot, dict) else None
    if (
        not isinstance(snapshot, dict)
        or snapshot.get("url") != normalized_url
        or snapshot.get("content_sha256") != content_sha256
        or not isinstance(content, str)
        or _sha256_text(content) != content_sha256
    ):
        raise ResearchToolError("The source snapshot failed integrity verification")
    if excerpt not in content:
        raise ResearchToolError("Evidence must be an exact excerpt from the server-held source snapshot")

    evidence_id = _sha256_text(f"{claim}\n{normalized_url}\n{content_sha256}\n{excerpt}\n{confidence_status}")[:24]
    entry = {
        "id": evidence_id,
        "claim": claim,
        "source_url": normalized_url,
        "retrieved_at": snapshot["retrieved_at"],
        "recorded_at": _iso_now(),
        "content_sha256": content_sha256,
        "excerpt": excerpt,
        "excerpt_sha256": _sha256_text(excerpt),
        "confidence_status": confidence_status,
        "source_type": snapshot["source_type"],
        "provider": snapshot["provider"],
    }
    target = _evidence_ledger_path(email, project_id)
    with _EVIDENCE_LOCK:
        current = list_claim_evidence(email, project_id)["evidence"]
        assert isinstance(current, list)
        for existing in current:
            if isinstance(existing, dict) and existing.get("id") == evidence_id:
                return existing
        current.append(entry)
        _write_json_atomic(target, {"version": 1, "evidence": current})
    return entry


def _artifact_path(email: str, project_id: str, relative_path: str) -> Path:
    normalized = relative_path.replace("\\", "/").strip("/")
    if normalized not in ALLOWED_RESEARCH_ARTIFACTS:
        allowed = ", ".join(sorted(ALLOWED_RESEARCH_ARTIFACTS))
        raise ResearchToolError(f"Research artifact path is not allowed. Choose one of: {allowed}")
    return store.safe_asset_path(store.assets_root(email, project_id), normalized)


def list_research_artifacts(email: str, project_id: str) -> dict[str, object]:
    items: list[dict[str, object]] = []
    for relative_path in sorted(ALLOWED_RESEARCH_ARTIFACTS):
        target = _artifact_path(email, project_id, relative_path)
        content = target.read_text(encoding="utf-8") if target.is_file() else ""
        items.append(
            {
                "path": relative_path,
                "exists": target.is_file(),
                "sha256": _sha256_text(content) if target.is_file() else None,
                "characters": len(content),
            }
        )
    return {"artifacts": items}


def read_research_artifact(email: str, project_id: str, relative_path: str) -> dict[str, object]:
    target = _artifact_path(email, project_id, relative_path)
    if not target.is_file():
        return {"path": relative_path, "exists": False, "sha256": None, "content": ""}
    content = target.read_text(encoding="utf-8")
    return {"path": relative_path, "exists": True, "sha256": _sha256_text(content), "content": content}


def write_research_artifact(
    email: str,
    project_id: str,
    relative_path: str,
    content: str,
    *,
    expected_sha256: str | None,
) -> dict[str, object]:
    if not content.strip():
        raise ResearchToolError("Research artifact content cannot be empty")
    if len(content) > MAX_ARTIFACT_CHARS:
        raise ResearchToolError(f"Research artifact cannot exceed {MAX_ARTIFACT_CHARS} characters")
    target = _artifact_path(email, project_id, relative_path)
    current = target.read_text(encoding="utf-8") if target.is_file() else None
    if current is not None:
        current_sha256 = _sha256_text(current)
        if not expected_sha256:
            raise ResearchToolError("Read the existing research artifact before replacing it")
        if expected_sha256 != current_sha256:
            raise ResearchToolError("Research artifact changed after it was read; read it again before replacing it")
    elif expected_sha256:
        raise ResearchToolError("Research artifact does not exist, so expected_sha256 must be omitted")

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as temporary:
        temporary.write(content)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    temporary_path.replace(target)
    saved_sha256 = _sha256_text(content)
    return {"path": relative_path, "exists": True, "sha256": saved_sha256, "characters": len(content)}


def _normalized_http_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
    except ValueError as error:
        raise ResearchToolError("Invalid webpage URL") from error
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ResearchToolError("Only absolute HTTP(S) webpage URLs are supported")
    if parsed.username or parsed.password:
        raise ResearchToolError("Webpage URLs cannot contain a username or password")
    try:
        port = parsed.port
    except ValueError as error:
        raise ResearchToolError("Invalid webpage URL port") from error
    if port not in {None, 80, 443}:
        raise ResearchToolError("Only standard HTTP(S) webpage ports are supported")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in _BLOCKED_HOSTS or hostname.endswith(".local") or hostname.endswith(".internal"):
        raise ResearchToolError("Private or local webpage URLs are not allowed")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ResearchToolError("Private or non-public IP addresses are not allowed")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))


def _assert_public_url(
    value: str,
    *,
    resolver: Callable[..., list[tuple[Any, ...]]] = socket.getaddrinfo,
) -> str:
    normalized = _normalized_http_url(value)
    hostname = urlsplit(normalized).hostname
    assert hostname
    try:
        resolved = resolver(hostname, None, type=socket.SOCK_STREAM)
    except OSError as error:
        raise ResearchToolError(f"Could not resolve webpage host: {hostname}") from error
    if not resolved:
        raise ResearchToolError(f"Could not resolve webpage host: {hostname}")
    for item in resolved:
        try:
            address = ipaddress.ip_address(item[4][0])
        except (ValueError, IndexError):
            raise ResearchToolError("Webpage host resolved to an invalid address") from None
        if not address.is_global:
            raise ResearchToolError("Webpage host resolved to a private or non-public address")
    return normalized


class _ReadableHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._blocked_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in _BLOCK_TAGS:
            self._blocked_depth += 1
        elif not self._blocked_depth and tag in _BREAK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS and self._blocked_depth:
            self._blocked_depth -= 1
        elif not self._blocked_depth and tag in _BREAK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._blocked_depth and data.strip():
            self._parts.append(data)

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self._parts).splitlines()]
        return "\n".join(line for line in lines if line).strip()


def _html_to_text(value: str) -> str:
    parser = _ReadableHtmlParser()
    parser.feed(value)
    parser.close()
    return parser.text()


def fetch_public_webpage(
    url: str,
    *,
    timeout_seconds: float = 20,
    max_chars: int = DEFAULT_FETCH_CHARS,
    client: httpx.Client | None = None,
    resolver: Callable[..., list[tuple[Any, ...]]] = socket.getaddrinfo,
) -> dict[str, object]:
    if not 1_000 <= max_chars <= 100_000:
        raise ResearchToolError("max_chars must be between 1000 and 100000")
    current_url = _assert_public_url(url, resolver=resolver)
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=timeout_seconds,
        follow_redirects=False,
        headers={"User-Agent": "LinglongLab-Research/1.0", "Accept": "text/html,text/plain,application/json,application/xml;q=0.9"},
    )
    try:
        for redirect_count in range(6):
            with active_client.stream("GET", current_url, follow_redirects=False) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location or redirect_count >= 5:
                        raise ResearchToolError("Webpage redirect chain is invalid or too long")
                    current_url = _assert_public_url(urljoin(current_url, location), resolver=resolver)
                    continue
                if response.status_code >= 400:
                    raise ResearchToolError(f"Webpage returned HTTP {response.status_code}")
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if content_type and not (
                    content_type.startswith("text/")
                    or content_type in {"application/json", "application/xml", "application/xhtml+xml"}
                    or content_type.endswith("+json")
                    or content_type.endswith("+xml")
                ):
                    raise ResearchToolError(f"Unsupported webpage content type: {content_type}")
                payload = bytearray()
                truncated_bytes = False
                for chunk in response.iter_bytes():
                    remaining = MAX_WEB_BYTES - len(payload)
                    if remaining <= 0:
                        truncated_bytes = True
                        break
                    payload.extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        truncated_bytes = True
                        break
                encoding = response.encoding or "utf-8"
                decoded = bytes(payload).decode(encoding, errors="replace")
                text = _html_to_text(decoded) if content_type in {"text/html", "application/xhtml+xml"} else decoded.strip()
                truncated = truncated_bytes or len(text) > max_chars
                return {
                    "url": current_url,
                    "status_code": response.status_code,
                    "content_type": content_type or "unknown",
                    "content": text[:max_chars],
                    "truncated": truncated,
                }
    except httpx.RequestError as error:
        raise ResearchToolError(f"Webpage request failed: {error.__class__.__name__}") from error
    finally:
        if owned_client:
            active_client.close()
    raise ResearchToolError("Webpage could not be fetched")


class _SearchHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._anchor_depth = 0
        self._snippet_depth = 0
        self._href = ""
        self._title: list[str] = []
        self._snippet: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        classes = set(attributes.get("class", "").split())
        if tag == "a" and ({"result__a", "result-link"} & classes):
            self._anchor_depth = 1
            self._href = attributes.get("href", "")
            self._title = []
        elif self._anchor_depth:
            self._anchor_depth += 1
        if {"result__snippet", "result-snippet"} & classes:
            self._snippet_depth = 1
            self._snippet = []
        elif self._snippet_depth:
            self._snippet_depth += 1

    def handle_endtag(self, tag: str) -> None:
        del tag
        if self._anchor_depth:
            self._anchor_depth -= 1
            if not self._anchor_depth:
                self.results.append({"url": self._href, "title": " ".join("".join(self._title).split()), "snippet": ""})
        if self._snippet_depth:
            self._snippet_depth -= 1
            if not self._snippet_depth and self.results:
                self.results[-1]["snippet"] = " ".join("".join(self._snippet).split())

    def handle_data(self, data: str) -> None:
        if self._anchor_depth:
            self._title.append(data)
        if self._snippet_depth:
            self._snippet.append(data)


def _direct_search_result_url(value: str) -> str | None:
    if not value:
        return None
    absolute = urljoin("https://duckduckgo.com", html.unescape(value))
    parsed = urlsplit(absolute)
    if parsed.hostname and parsed.hostname.endswith("duckduckgo.com"):
        target = parse_qs(parsed.query).get("uddg", [None])[0]
        if target:
            absolute = target
    try:
        return _normalized_http_url(absolute)
    except ResearchToolError:
        return None


def _classify_search_error(error: BaseException) -> SearchProviderError:
    if isinstance(error, SearchProviderError):
        return error
    if isinstance(error, (httpx.TimeoutException, TimeoutError)):
        return SearchProviderError("timeout", "Search provider timed out", retryable=True)
    if isinstance(error, httpx.HTTPStatusError):
        status_code = error.response.status_code
        if status_code == 429:
            return SearchProviderError("rate_limited", "Search provider rate limited the request", retryable=True)
        if status_code in {401, 403}:
            return SearchProviderError("forbidden", f"Search provider returned HTTP {status_code}", retryable=False)
        if status_code >= 500:
            return SearchProviderError("server_error", f"Search provider returned HTTP {status_code}", retryable=True)
        return SearchProviderError("configuration_error", f"Search provider returned HTTP {status_code}", retryable=False)
    if isinstance(error, httpx.ConnectError):
        return SearchProviderError("network_error", "Search provider connection failed", retryable=True)
    if isinstance(error, httpx.RequestError):
        return SearchProviderError("network_error", f"Search provider request failed: {error.__class__.__name__}", retryable=True)
    if isinstance(error, ResearchToolError):
        cause = error.__cause__
        if isinstance(cause, socket.gaierror) or "resolve" in str(error).lower():
            return SearchProviderError("dns", "Search provider host could not be resolved", retryable=True)
        return SearchProviderError("configuration_error", str(error), retryable=False)
    return SearchProviderError("unexpected_error", f"Search provider failed: {error.__class__.__name__}", retryable=False)


def _search_duckduckgo(
    query: str,
    *,
    max_results: int = DEFAULT_SEARCH_RESULTS,
    timeout_seconds: float = 30,
    client: httpx.Client | None = None,
    resolver: Callable[..., list[tuple[Any, ...]]] = socket.getaddrinfo,
) -> dict[str, object]:
    normalized_query = " ".join(query.split())
    endpoint = _assert_public_url(
        f"https://html.duckduckgo.com/html/?q={quote_plus(normalized_query)}",
        resolver=resolver,
    )
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=timeout_seconds,
        follow_redirects=False,
        headers={"User-Agent": "LinglongLab-Research/1.0", "Accept": "text/html"},
    )
    try:
        response = active_client.get(endpoint)
        response.raise_for_status()
    except Exception as error:
        raise _classify_search_error(error) from error
    finally:
        if owned_client:
            active_client.close()
    parser = _SearchHtmlParser()
    parser.feed(response.text)
    parser.close()
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in parser.results:
        result_url = _direct_search_result_url(item["url"])
        if not result_url or result_url in seen or not item["title"]:
            continue
        seen.add(result_url)
        results.append({"url": result_url, "title": item["title"], "snippet": item["snippet"]})
        if len(results) >= max_results:
            break
    if not results:
        raise SearchProviderError(
            "empty_results",
            "Web search returned no readable results; retry later or provide source URLs directly",
            retryable=True,
        )
    return {"query": normalized_query, "sources": results, "truncated": len(parser.results) > len(results)}


def _default_search_providers(
    *,
    client: httpx.Client | None,
    resolver: Callable[..., list[tuple[Any, ...]]],
) -> list[SearchProvider]:
    return [
        SearchProvider(
            "duckduckgo",
            lambda query, max_results, timeout_seconds: _search_duckduckgo(
                query,
                max_results=max_results,
                timeout_seconds=timeout_seconds,
                client=client,
                resolver=resolver,
            ),
        )
    ]


def _provider_is_degraded(name: str, now: datetime) -> bool:
    with _PROVIDER_HEALTH_LOCK:
        state = _PROVIDER_HEALTH.get(name, {})
        degraded_until = state.get("degraded_until")
    if not isinstance(degraded_until, str):
        return False
    try:
        return datetime.fromisoformat(degraded_until) > now
    except ValueError:
        return False


def _mark_provider_success(name: str, checked_at: datetime) -> None:
    with _PROVIDER_HEALTH_LOCK:
        _PROVIDER_HEALTH[name] = {
            "consecutive_failures": 0,
            "last_checked_at": checked_at.isoformat(),
            "last_success_at": checked_at.isoformat(),
            "last_error_code": None,
            "last_error_message": None,
            "degraded_until": None,
        }


def _mark_provider_failure(name: str, error: SearchProviderError, checked_at: datetime) -> None:
    with _PROVIDER_HEALTH_LOCK:
        previous = _PROVIDER_HEALTH.get(name, {})
        failures = int(previous.get("consecutive_failures", 0)) + 1
        _PROVIDER_HEALTH[name] = {
            "consecutive_failures": failures,
            "last_checked_at": checked_at.isoformat(),
            "last_success_at": previous.get("last_success_at"),
            "last_error_code": error.code,
            "last_error_message": str(error)[:500],
            "degraded_until": (checked_at + timedelta(seconds=PROVIDER_COOLDOWN_SECONDS)).isoformat(),
        }


def search_provider_doctor(*, providers: list[SearchProvider] | None = None) -> dict[str, object]:
    active_providers = providers or _default_search_providers(client=None, resolver=socket.getaddrinfo)
    now = _utc_now()
    statuses: list[dict[str, object]] = []
    with _PROVIDER_HEALTH_LOCK:
        states = {name: dict(value) for name, value in _PROVIDER_HEALTH.items()}
    for provider in active_providers:
        state = states.get(provider.name, {})
        if _provider_is_degraded(provider.name, now):
            status = "degraded"
        elif state.get("last_success_at"):
            status = "healthy"
        else:
            status = "unknown"
        statuses.append(
            {
                "provider": provider.name,
                "status": status,
                "consecutive_failures": int(state.get("consecutive_failures", 0)),
                "last_checked_at": state.get("last_checked_at"),
                "last_success_at": state.get("last_success_at"),
                "last_error_code": state.get("last_error_code"),
                "last_error_message": state.get("last_error_message"),
                "degraded_until": state.get("degraded_until"),
            }
        )
    return {"scope": "process", "checked_at": now.isoformat(), "providers": statuses}


def _normalized_provider_sources(value: object, max_results: int) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("url"), str):
            continue
        try:
            source_url = _normalized_http_url(item["url"])
        except ResearchToolError:
            continue
        title = " ".join(str(item.get("title", "")).split())[:500]
        snippet = " ".join(str(item.get("snippet", "")).split())[:2_000]
        if not title or source_url in seen:
            continue
        seen.add(source_url)
        normalized.append({"url": source_url, "title": title, "snippet": snippet})
        if len(normalized) >= max_results:
            break
    return normalized


def search_public_web(
    query: str,
    *,
    max_results: int = DEFAULT_SEARCH_RESULTS,
    timeout_seconds: float = 30,
    client: httpx.Client | None = None,
    resolver: Callable[..., list[tuple[Any, ...]]] = socket.getaddrinfo,
    providers: list[SearchProvider] | None = None,
) -> dict[str, object]:
    normalized_query = " ".join(query.split())
    if not normalized_query or len(normalized_query) > 500:
        raise ResearchToolError("Search query must contain 1 to 500 characters")
    if not 1 <= max_results <= 20:
        raise ResearchToolError("max_results must be between 1 and 20")
    active_providers = providers or _default_search_providers(client=client, resolver=resolver)
    if not active_providers:
        raise ResearchToolError("No web search providers are configured")
    now = _utc_now()
    eligible = [provider for provider in active_providers if not _provider_is_degraded(provider.name, now)]
    if not eligible:
        eligible = [active_providers[0]]
    attempts: list[dict[str, object]] = []
    last_error: SearchProviderError | None = None
    for provider in eligible:
        checked_at = _utc_now()
        try:
            result = provider.search(normalized_query, max_results, timeout_seconds)
            sources = _normalized_provider_sources(result.get("sources"), max_results)
            if not sources:
                raise SearchProviderError("empty_results", "Search provider returned no readable results", retryable=True)
        except Exception as error:
            classified = _classify_search_error(error)
            _mark_provider_failure(provider.name, classified, checked_at)
            attempts.append(
                {
                    "provider": provider.name,
                    "status": "failed",
                    "error_code": classified.code,
                    "retryable": classified.retryable,
                }
            )
            last_error = classified
            continue
        _mark_provider_success(provider.name, checked_at)
        attempts.append({"provider": provider.name, "status": "success"})
        output = dict(result)
        output["query"] = normalized_query
        output["sources"] = sources
        output["provider"] = provider.name
        output["attempts"] = attempts
        return output
    assert last_error is not None
    raise ResearchToolError(
        f"All web search providers failed ({last_error.code}); retry later or provide source URLs directly"
    ) from last_error


def _video_platform(url: str) -> str:
    hostname = (urlsplit(url).hostname or "").rstrip(".").lower()
    if hostname in _YOUTUBE_HOSTS:
        return "youtube"
    if hostname in _BILIBILI_HOSTS:
        return "bilibili"
    raise ResearchToolError("video_transcript_fetch supports only public YouTube and Bilibili URLs")


def _yt_dlp_extract(url: str, options: dict[str, object]) -> dict[str, object]:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as error:
        raise ResearchToolError("The video transcript provider is not installed") from error
    try:
        with YoutubeDL(options) as downloader:
            result = downloader.extract_info(url, download=False)
    except Exception as error:
        raise ResearchToolError(f"Video transcript metadata request failed: {error.__class__.__name__}") from error
    if not isinstance(result, dict):
        raise ResearchToolError("Video transcript provider returned invalid metadata")
    return result


def _validated_languages(languages: list[str] | None) -> list[str]:
    selected = languages or ["en", "zh-Hans", "zh-Hant", "zh"]
    if not 1 <= len(selected) <= 5:
        raise ResearchToolError("languages must contain between one and five language codes")
    normalized: list[str] = []
    for language in selected:
        if not isinstance(language, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,20}", language):
            raise ResearchToolError("Each transcript language must be a short language code")
        if language not in normalized:
            normalized.append(language)
    return normalized


def _subtitle_track(
    metadata: dict[str, object],
    languages: list[str],
) -> tuple[str, bool, dict[str, object]]:
    format_order = {"vtt": 0, "json3": 1, "srt": 2, "json": 3}
    for field, is_auto in (("subtitles", False), ("automatic_captions", True)):
        collection = metadata.get(field)
        if not isinstance(collection, dict):
            continue
        available = [key for key, value in collection.items() if isinstance(key, str) and isinstance(value, list)]
        for requested in languages:
            matches = [language for language in available if language == requested]
            matches.extend(language for language in available if language not in matches and language.split("-", 1)[0] == requested.split("-", 1)[0])
            for language in matches:
                tracks = collection.get(language)
                assert isinstance(tracks, list)
                candidates = [
                    track
                    for track in tracks
                    if isinstance(track, dict)
                    and isinstance(track.get("url"), str)
                    and str(track.get("ext", "")).lower() in format_order
                ]
                if candidates:
                    candidates.sort(key=lambda item: format_order[str(item.get("ext", "")).lower()])
                    return language, is_auto, candidates[0]
    raise ResearchToolError("No public subtitles are available in the requested languages")


def _parse_timed_text(payload: str, extension: str) -> str:
    if extension in {"json", "json3"}:
        try:
            value = json.loads(payload)
        except json.JSONDecodeError as error:
            raise ResearchToolError("Subtitle provider returned invalid JSON") from error
        parts: list[str] = []
        if isinstance(value, dict) and isinstance(value.get("events"), list):
            for event in value["events"]:
                if not isinstance(event, dict) or not isinstance(event.get("segs"), list):
                    continue
                text = "".join(str(segment.get("utf8", "")) for segment in event["segs"] if isinstance(segment, dict))
                if text.strip():
                    parts.append(text.strip())
        elif isinstance(value, dict) and isinstance(value.get("body"), list):
            parts.extend(
                str(item["content"]).strip()
                for item in value["body"]
                if isinstance(item, dict) and isinstance(item.get("content"), str) and item["content"].strip()
            )
        else:
            raise ResearchToolError("Subtitle JSON did not contain readable transcript text")
        return "\n".join(dict.fromkeys(parts))

    lines: list[str] = []
    timestamp_pattern = re.compile(
        r"^(?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3}\s+-->\s+(?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3}"
    )
    for raw_line in payload.splitlines():
        line = raw_line.strip()
        if (
            not line
            or line == "WEBVTT"
            or line.isdigit()
            or timestamp_pattern.match(line)
            or line.startswith(("NOTE", "STYLE", "REGION", "Kind:", "Language:"))
        ):
            continue
        line = re.sub(r"<[^>]+>", "", html.unescape(line)).strip()
        if line and (not lines or line != lines[-1]):
            lines.append(line)
    transcript = "\n".join(lines)
    if not transcript:
        raise ResearchToolError("Subtitle track did not contain readable transcript text")
    return transcript


def fetch_video_transcript(
    url: str,
    *,
    languages: list[str] | None = None,
    timeout_seconds: float = 30,
    max_chars: int = DEFAULT_TRANSCRIPT_CHARS,
    extractor: Callable[[str, dict[str, object]], dict[str, object]] = _yt_dlp_extract,
    client: httpx.Client | None = None,
    resolver: Callable[..., list[tuple[Any, ...]]] = socket.getaddrinfo,
) -> dict[str, object]:
    if not 1_000 <= max_chars <= 100_000:
        raise ResearchToolError("max_chars must be between 1000 and 100000")
    normalized_url = _assert_public_url(url, resolver=resolver)
    platform = _video_platform(normalized_url)
    requested_languages = _validated_languages(languages)
    options: dict[str, object] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": timeout_seconds,
        "retries": 1,
        "ignoreconfig": True,
    }
    metadata = extractor(normalized_url, options)
    if metadata.get("_type") in {"playlist", "multi_video"} or isinstance(metadata.get("entries"), list):
        raise ResearchToolError("Only one public video transcript can be fetched at a time")
    language, is_auto_generated, track = _subtitle_track(metadata, requested_languages)
    track_url = _assert_public_url(str(track["url"]), resolver=resolver)
    request_headers = {
        str(key): str(value)
        for key, value in (track.get("http_headers") or {}).items()
        if isinstance(key, str) and key.lower() in _SAFE_TRANSCRIPT_HEADERS
    } if isinstance(track.get("http_headers"), dict) else {}
    request_headers.setdefault("User-Agent", "LinglongLab-Research/1.0")
    owned_client = client is None
    active_client = client or httpx.Client(timeout=timeout_seconds, follow_redirects=False)
    try:
        for redirect_count in range(6):
            with active_client.stream("GET", track_url, headers=request_headers, follow_redirects=False) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location or redirect_count >= 5:
                        raise ResearchToolError("Subtitle redirect chain is invalid or too long")
                    track_url = _assert_public_url(urljoin(track_url, location), resolver=resolver)
                    continue
                if response.status_code >= 400:
                    raise ResearchToolError(f"Subtitle provider returned HTTP {response.status_code}")
                payload = bytearray()
                for chunk in response.iter_bytes():
                    remaining = MAX_TRANSCRIPT_BYTES - len(payload)
                    if remaining <= 0:
                        raise ResearchToolError("Subtitle track exceeds the maximum supported size")
                    payload.extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        raise ResearchToolError("Subtitle track exceeds the maximum supported size")
                decoded = bytes(payload).decode(response.encoding or "utf-8", errors="replace")
                break
        else:
            raise ResearchToolError("Subtitle could not be fetched")
    except httpx.RequestError as error:
        raise ResearchToolError(f"Subtitle request failed: {error.__class__.__name__}") from error
    finally:
        if owned_client:
            active_client.close()
    content = _parse_timed_text(decoded, str(track.get("ext", "")).lower())
    canonical_url = _assert_public_url(str(metadata.get("webpage_url") or normalized_url), resolver=resolver)
    if _video_platform(canonical_url) != platform:
        raise ResearchToolError("Video transcript provider returned an unexpected canonical platform URL")
    truncated = len(content) > max_chars
    content = content[:max_chars]
    return {
        "url": canonical_url,
        "platform": platform,
        "video_id": str(metadata.get("id") or ""),
        "title": str(metadata.get("title") or ""),
        "channel": str(metadata.get("channel") or metadata.get("uploader") or ""),
        "language": language,
        "is_auto_generated": is_auto_generated,
        "provider": "yt-dlp",
        "content": content,
        "truncated": truncated,
        "retrieved_at": _iso_now(),
        "content_sha256": _sha256_text(content),
    }


RESEARCH_TOOL_DEFINITIONS: dict[str, dict[str, object]] = {
    "web_search": {
        "description": "Search the public web for current sources. Results are untrusted discovery material and must be cited by URL.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False},
        "extension": "tool-web-search",
    },
    "web_fetch": {
        "description": "Read the static text of one public HTTP(S) webpage. It does not execute JavaScript or bypass access controls.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"], "additionalProperties": False},
        "extension": "tool-web-fetch",
    },
    "search_provider_doctor": {
        "description": "Inspect process-local web search provider health, classified errors and temporary degradation state.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        "extension": "tool-web-search",
    },
    "video_transcript_fetch": {
        "description": "Fetch public subtitles for one YouTube or Bilibili video. Transcript text can support spoken claims but does not prove visual content.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "languages": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 5},
            },
            "required": ["url"],
            "additionalProperties": False,
        },
        "extension": "tool-video-transcript",
    },
    "list_research_artifacts": {
        "description": "List the allowed research deliverables and their versions in the current project.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        "extension": "tool-workspace",
    },
    "read_research_artifact": {
        "description": "Read one research deliverable before using or updating it.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string", "enum": sorted(ALLOWED_RESEARCH_ARTIFACTS)}}, "required": ["path"], "additionalProperties": False},
        "extension": "tool-workspace",
    },
    "write_research_artifact": {
        "description": "Create or safely replace one research deliverable. Existing files require the sha256 returned by read_research_artifact.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "enum": sorted(ALLOWED_RESEARCH_ARTIFACTS)},
                "content": {"type": "string"},
                "expected_sha256": {"type": ["string", "null"]},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
        "extension": "tool-workspace",
    },
    "record_claim_evidence": {
        "description": "Record one factual claim against an exact excerpt from a server-held webpage or transcript snapshot.",
        "parameters": {
            "type": "object",
            "properties": {
                "claim": {"type": "string"},
                "source_url": {"type": "string"},
                "content_sha256": {"type": "string"},
                "excerpt": {"type": "string"},
                "confidence_status": {"type": "string", "enum": sorted(EVIDENCE_STATUSES)},
            },
            "required": ["claim", "source_url", "content_sha256", "excerpt", "confidence_status"],
            "additionalProperties": False,
        },
        "extension": "tool-workspace",
    },
    "list_claim_evidence": {
        "description": "List verified claim-level evidence recorded for the current project.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        "extension": "tool-workspace",
    },
}


def available_research_tools(enabled_extensions: set[str]) -> list[dict[str, object]]:
    return [
        {"name": name, "description": definition["description"], "parameters": definition["parameters"]}
        for name, definition in RESEARCH_TOOL_DEFINITIONS.items()
        if definition["extension"] in enabled_extensions
    ]


def execute_research_tool(
    name: str,
    arguments: dict[str, object],
    *,
    email: str,
    project_id: str,
    enabled_extensions: set[str],
    extension_configs: dict[str, dict[str, Any]],
) -> dict[str, object]:
    definition = RESEARCH_TOOL_DEFINITIONS.get(name)
    if not definition or definition["extension"] not in enabled_extensions:
        raise ResearchToolError(f"Research tool is not enabled: {name}")
    if not isinstance(arguments, dict):
        raise ResearchToolError("Research tool arguments must be an object")
    if name == "web_search":
        if set(arguments) != {"query"} or not isinstance(arguments.get("query"), str):
            raise ResearchToolError("web_search requires only a string query")
        config = extension_configs.get("tool-web-search", {})
        return search_public_web(
            arguments["query"],
            max_results=int(config.get("maxResults", DEFAULT_SEARCH_RESULTS)),
            timeout_seconds=float(config.get("timeoutMs", 30_000)) / 1000,
        )
    if name == "web_fetch":
        if set(arguments) != {"url"} or not isinstance(arguments.get("url"), str):
            raise ResearchToolError("web_fetch requires only a string url")
        config = extension_configs.get("tool-web-fetch", {})
        result = fetch_public_webpage(
            arguments["url"],
            timeout_seconds=float(config.get("timeoutMs", 20_000)) / 1000,
            max_chars=int(config.get("maxChars", DEFAULT_FETCH_CHARS)),
        )
        return _persist_source_snapshot(
            email,
            project_id,
            result,
            source_type="webpage",
            provider="direct",
        )
    if name == "search_provider_doctor":
        if arguments:
            raise ResearchToolError("search_provider_doctor does not accept arguments")
        return search_provider_doctor()
    if name == "video_transcript_fetch":
        if not set(arguments) <= {"url", "languages"} or not isinstance(arguments.get("url"), str):
            raise ResearchToolError("video_transcript_fetch requires a string url and optional languages")
        languages = arguments.get("languages")
        if languages is not None and (
            not isinstance(languages, list) or not all(isinstance(item, str) for item in languages)
        ):
            raise ResearchToolError("video_transcript_fetch languages must be an array of strings")
        config = extension_configs.get("tool-video-transcript", {})
        result = fetch_video_transcript(
            arguments["url"],
            languages=languages,
            timeout_seconds=float(config.get("timeoutMs", 30_000)) / 1000,
            max_chars=int(config.get("maxChars", DEFAULT_TRANSCRIPT_CHARS)),
        )
        return _persist_source_snapshot(
            email,
            project_id,
            result,
            source_type="video_transcript",
            provider="yt-dlp",
        )
    if name == "list_research_artifacts":
        if arguments:
            raise ResearchToolError("list_research_artifacts does not accept arguments")
        return list_research_artifacts(email, project_id)
    if name == "read_research_artifact":
        if set(arguments) != {"path"} or not isinstance(arguments.get("path"), str):
            raise ResearchToolError("read_research_artifact requires only a string path")
        return read_research_artifact(email, project_id, arguments["path"])
    if name == "write_research_artifact":
        if not set(arguments) <= {"path", "content", "expected_sha256"}:
            raise ResearchToolError("write_research_artifact received unsupported arguments")
        if not isinstance(arguments.get("path"), str) or not isinstance(arguments.get("content"), str):
            raise ResearchToolError("write_research_artifact requires string path and content")
        expected = arguments.get("expected_sha256")
        if expected is not None and not isinstance(expected, str):
            raise ResearchToolError("expected_sha256 must be a string or null")
        return write_research_artifact(
            email,
            project_id,
            arguments["path"],
            arguments["content"],
            expected_sha256=expected,
        )
    if name == "record_claim_evidence":
        required = {"claim", "source_url", "content_sha256", "excerpt", "confidence_status"}
        if set(arguments) != required or not all(isinstance(arguments.get(key), str) for key in required):
            raise ResearchToolError("record_claim_evidence requires claim, source_url, content_sha256, excerpt, and confidence_status strings")
        return record_claim_evidence(
            email,
            project_id,
            claim=arguments["claim"],
            source_url=arguments["source_url"],
            content_sha256=arguments["content_sha256"],
            excerpt=arguments["excerpt"],
            confidence_status=arguments["confidence_status"],
        )
    if name == "list_claim_evidence":
        if arguments:
            raise ResearchToolError("list_claim_evidence does not accept arguments")
        return list_claim_evidence(email, project_id)
    raise ResearchToolError(f"Unsupported research tool: {name}")
