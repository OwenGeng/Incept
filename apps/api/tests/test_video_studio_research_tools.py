from __future__ import annotations

from urllib.parse import quote

import httpx
import pytest

from app.video_studio import research_tools, store
from app.video_studio.models import ProjectCreate


def _public_resolver(host: str, _port: object, **_kwargs: object) -> list[tuple[object, ...]]:
    del host
    return [(2, 1, 6, "", ("93.184.216.34", 0))]


def _private_resolver(host: str, _port: object, **_kwargs: object) -> list[tuple[object, ...]]:
    del host
    return [(2, 1, 6, "", ("10.0.0.8", 0))]


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://localhost/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "https://user:password@example.com/",
        "https://example.com:8443/",
        "file:///etc/passwd",
    ],
)
def test_normalized_http_url_rejects_unsafe_targets(url: str) -> None:
    with pytest.raises(research_tools.ResearchToolError):
        research_tools._normalized_http_url(url)


def test_public_url_validation_checks_resolved_addresses() -> None:
    with pytest.raises(research_tools.ResearchToolError, match="private or non-public"):
        research_tools._assert_public_url("https://example.test/source", resolver=_private_resolver)

    assert (
        research_tools._assert_public_url("https://example.test/source#fragment", resolver=_public_resolver)
        == "https://example.test/source"
    )


def test_fetch_public_webpage_extracts_static_text_and_follows_safe_redirects() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.host == "start.example.test":
            return httpx.Response(302, headers={"location": "https://source.example.test/article"})
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<html><head><script>ignore()</script></head><body><h1>Verified title</h1><p>Useful evidence.</p></body></html>",
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = research_tools.fetch_public_webpage(
            "https://start.example.test/redirect",
            client=client,
            resolver=_public_resolver,
        )

    assert requests == [
        "https://start.example.test/redirect",
        "https://source.example.test/article",
    ]
    assert result["url"] == "https://source.example.test/article"
    assert result["content"] == "Verified title\nUseful evidence."
    assert "ignore" not in str(result["content"])
    assert result["truncated"] is False


def test_fetch_public_webpage_rejects_binary_content() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            request=request,
            headers={"content-type": "application/octet-stream"},
            content=b"binary",
        )
    )
    with httpx.Client(transport=transport) as client:
        with pytest.raises(research_tools.ResearchToolError, match="Unsupported webpage content type"):
            research_tools.fetch_public_webpage(
                "https://example.test/file",
                client=client,
                resolver=_public_resolver,
            )


def test_fetch_public_webpage_reports_network_failure_as_tool_error() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        with pytest.raises(research_tools.ResearchToolError, match="Webpage request failed"):
            research_tools.fetch_public_webpage(
                "https://example.test/article",
                client=client,
                resolver=_public_resolver,
            )


def test_search_public_web_parses_titles_snippets_and_direct_urls() -> None:
    target = "https://advertiser.example.test/case-study?q=ctv"
    encoded_target = quote(target, safe="")
    body = f"""
    <html><body>
      <div class="result">
        <a class="result__a" href="//duckduckgo.com/l/?uddg={encoded_target}">CTV <b>case study</b></a>
        <div class="result__snippet">A source-backed campaign summary.</div>
      </div>
    </body></html>
    """
    transport = httpx.MockTransport(lambda request: httpx.Response(200, request=request, text=body))
    with httpx.Client(transport=transport) as client:
        result = research_tools.search_public_web(
            " CTV   ecommerce examples ",
            client=client,
            resolver=_public_resolver,
        )

    assert result["query"] == "CTV ecommerce examples"
    assert result["sources"] == [
        {
            "url": target,
            "title": "CTV case study",
            "snippet": "A source-backed campaign summary.",
        }
    ]


def test_research_artifact_writes_are_scoped_and_versioned(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path))
    email = "research@example.com"
    project = store.create_project(email, ProjectCreate(name="Research"))

    with pytest.raises(research_tools.ResearchToolError, match="not allowed"):
        research_tools.write_research_artifact(
            email,
            project.id,
            "../../outside.md",
            "unsafe",
            expected_sha256=None,
        )

    created = research_tools.write_research_artifact(
        email,
        project.id,
        "research/video-sample-table.md",
        "# Five verified references",
        expected_sha256=None,
    )
    assert created["characters"] == len("# Five verified references")
    read = research_tools.read_research_artifact(email, project.id, "research/video-sample-table.md")
    assert read["content"] == "# Five verified references"
    assert read["sha256"] == created["sha256"]

    with pytest.raises(research_tools.ResearchToolError, match="Read the existing"):
        research_tools.write_research_artifact(
            email,
            project.id,
            "research/video-sample-table.md",
            "# Replacement",
            expected_sha256=None,
        )
    with pytest.raises(research_tools.ResearchToolError, match="changed after"):
        research_tools.write_research_artifact(
            email,
            project.id,
            "research/video-sample-table.md",
            "# Replacement",
            expected_sha256="stale",
        )

    updated = research_tools.write_research_artifact(
        email,
        project.id,
        "research/video-sample-table.md",
        "# Replacement",
        expected_sha256=str(read["sha256"]),
    )
    assert updated["sha256"] != read["sha256"]


def test_tool_execution_requires_its_enabled_extension(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path))
    email = "research@example.com"
    project = store.create_project(email, ProjectCreate(name="Research"))

    with pytest.raises(research_tools.ResearchToolError, match="not enabled"):
        research_tools.execute_research_tool(
            "list_research_artifacts",
            {},
            email=email,
            project_id=project.id,
            enabled_extensions=set(),
            extension_configs={},
        )

    result = research_tools.execute_research_tool(
        "list_research_artifacts",
        {},
        email=email,
        project_id=project.id,
        enabled_extensions={"tool-workspace"},
        extension_configs={},
    )
    assert len(result["artifacts"]) == len(research_tools.ALLOWED_RESEARCH_ARTIFACTS)
