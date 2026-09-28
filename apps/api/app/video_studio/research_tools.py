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
import os
import socket
import tempfile
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


class ResearchToolError(ValueError):
    """A user-actionable research tool boundary error."""


def _sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


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


def search_public_web(
    query: str,
    *,
    max_results: int = DEFAULT_SEARCH_RESULTS,
    timeout_seconds: float = 30,
    client: httpx.Client | None = None,
    resolver: Callable[..., list[tuple[Any, ...]]] = socket.getaddrinfo,
) -> dict[str, object]:
    normalized_query = " ".join(query.split())
    if not normalized_query or len(normalized_query) > 500:
        raise ResearchToolError("Search query must contain 1 to 500 characters")
    if not 1 <= max_results <= 20:
        raise ResearchToolError("max_results must be between 1 and 20")
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
    finally:
        if owned_client:
            active_client.close()
    if response.status_code >= 400:
        raise ResearchToolError(f"Web search returned HTTP {response.status_code}")
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
        raise ResearchToolError("Web search returned no readable results; retry later or provide source URLs directly")
    return {"query": normalized_query, "sources": results, "truncated": len(parser.results) > len(results)}


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
        return fetch_public_webpage(
            arguments["url"],
            timeout_seconds=float(config.get("timeoutMs", 20_000)) / 1000,
            max_chars=int(config.get("maxChars", DEFAULT_FETCH_CHARS)),
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
    raise ResearchToolError(f"Unsupported research tool: {name}")
