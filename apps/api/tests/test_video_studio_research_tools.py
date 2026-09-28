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
    assert result["provider"] == "duckduckgo"


def test_search_falls_back_and_reports_process_health(monkeypatch) -> None:
    research_tools._PROVIDER_HEALTH.clear()

    def unavailable(_query: str, _max_results: int, _timeout_seconds: float) -> dict[str, object]:
        raise research_tools.SearchProviderError("rate_limited", "quota exceeded", retryable=True)

    def backup(query: str, _max_results: int, _timeout_seconds: float) -> dict[str, object]:
        return {
            "query": query,
            "sources": [{"url": "https://example.test/source", "title": "Source", "snippet": "Evidence"}],
            "truncated": False,
        }

    providers = [
        research_tools.SearchProvider("primary", unavailable),
        research_tools.SearchProvider("backup", backup),
    ]
    result = research_tools.search_public_web("ecommerce CTV", providers=providers)

    assert result["provider"] == "backup"
    assert result["attempts"] == [
        {"provider": "primary", "status": "failed", "error_code": "rate_limited", "retryable": True},
        {"provider": "backup", "status": "success"},
    ]
    health = research_tools.search_provider_doctor(providers=providers)
    assert health["scope"] == "process"
    by_name = {item["provider"]: item for item in health["providers"]}
    assert by_name["primary"]["status"] == "degraded"
    assert by_name["primary"]["last_error_code"] == "rate_limited"
    assert by_name["backup"]["status"] == "healthy"


def test_search_provider_error_classifies_http_and_timeout() -> None:
    rate_limited = research_tools._classify_search_error(httpx.HTTPStatusError(
        "rate limited",
        request=httpx.Request("GET", "https://search.example.test"),
        response=httpx.Response(429),
    ))
    timed_out = research_tools._classify_search_error(httpx.ReadTimeout("late"))

    assert (rate_limited.code, rate_limited.retryable) == ("rate_limited", True)
    assert (timed_out.code, timed_out.retryable) == ("timeout", True)


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


def test_web_fetch_snapshot_can_record_verified_claim(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path))
    email = "research@example.com"
    project = store.create_project(email, ProjectCreate(name="Research"))
    fetched = {
        "url": "https://brand.example.test/product",
        "status_code": 200,
        "content_type": "text/plain",
        "content": "The battery lasts up to 12 hours under the documented test protocol.",
        "truncated": False,
    }
    monkeypatch.setattr(research_tools, "fetch_public_webpage", lambda *_args, **_kwargs: fetched)

    source = research_tools.execute_research_tool(
        "web_fetch",
        {"url": fetched["url"]},
        email=email,
        project_id=project.id,
        enabled_extensions={"tool-web-fetch", "tool-workspace"},
        extension_configs={},
    )
    evidence = research_tools.execute_research_tool(
        "record_claim_evidence",
        {
            "claim": "The product has up to 12 hours of battery life.",
            "source_url": fetched["url"],
            "content_sha256": source["content_sha256"],
            "excerpt": "The battery lasts up to 12 hours",
            "confidence_status": "supported",
        },
        email=email,
        project_id=project.id,
        enabled_extensions={"tool-workspace"},
        extension_configs={},
    )

    assert evidence["source_url"] == fetched["url"]
    assert evidence["retrieved_at"] == source["retrieved_at"]
    assert evidence["content_sha256"] == source["content_sha256"]
    ledger = research_tools.list_claim_evidence(email, project.id)
    assert ledger["evidence"] == [evidence]


def test_claim_evidence_rejects_excerpt_not_in_server_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path))
    email = "research@example.com"
    project = store.create_project(email, ProjectCreate(name="Research"))
    source = research_tools._persist_source_snapshot(
        email,
        project.id,
        {
            "url": "https://brand.example.test/product",
            "content": "Documented product fact.",
        },
        source_type="webpage",
        provider="direct",
    )

    with pytest.raises(research_tools.ResearchToolError, match="exact excerpt"):
        research_tools.record_claim_evidence(
            email,
            project.id,
            claim="An invented fact",
            source_url=str(source["url"]),
            content_sha256=str(source["content_sha256"]),
            excerpt="Text absent from the source",
            confidence_status="supported",
        )


def test_video_transcript_fetch_parses_youtube_vtt_and_persists_source(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path))
    email = "research@example.com"
    project = store.create_project(email, ProjectCreate(name="Research"))

    def extractor(_url: str, _options: dict[str, object]) -> dict[str, object]:
        return {
            "id": "abc123",
            "webpage_url": "https://www.youtube.com/watch?v=abc123",
            "title": "Product demo",
            "channel": "Brand",
            "subtitles": {
                "en": [{"ext": "vtt", "url": "https://captions.example.test/demo.vtt"}],
            },
            "automatic_captions": {},
        }

    vtt = "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nMeet the new camera.\n\n00:00:02.000 --> 00:00:04.000\nShoot all day.\n"
    transport = httpx.MockTransport(lambda request: httpx.Response(200, request=request, text=vtt))
    with httpx.Client(transport=transport) as client:
        transcript = research_tools.fetch_video_transcript(
            "https://youtu.be/abc123",
            languages=["en"],
            extractor=extractor,
            client=client,
            resolver=_public_resolver,
        )
    saved = research_tools._persist_source_snapshot(
        email,
        project.id,
        transcript,
        source_type="video_transcript",
        provider="yt-dlp",
    )

    assert transcript["platform"] == "youtube"
    assert transcript["language"] == "en"
    assert transcript["is_auto_generated"] is False
    assert transcript["content"] == "Meet the new camera.\nShoot all day."
    assert saved["content_sha256"] == research_tools._sha256_text(str(transcript["content"]))


def test_video_transcript_fetch_rejects_non_allowlisted_platform() -> None:
    with pytest.raises(research_tools.ResearchToolError, match="YouTube and Bilibili"):
        research_tools.fetch_video_transcript(
            "https://example.test/video",
            extractor=lambda *_args: {},
            resolver=_public_resolver,
        )


def test_video_transcript_fetch_parses_bilibili_json() -> None:
    def extractor(_url: str, _options: dict[str, object]) -> dict[str, object]:
        return {
            "id": "BV1TEST",
            "webpage_url": "https://www.bilibili.com/video/BV1TEST",
            "title": "产品介绍",
            "uploader": "品牌",
            "subtitles": {
                "zh-Hans": [{"ext": "json", "url": "https://captions.example.test/bilibili.json"}],
            },
        }

    payload = '{"body":[{"content":"第一句。"},{"content":"第二句。"}]}'
    transport = httpx.MockTransport(lambda request: httpx.Response(200, request=request, text=payload))
    with httpx.Client(transport=transport) as client:
        transcript = research_tools.fetch_video_transcript(
            "https://www.bilibili.com/video/BV1TEST",
            languages=["zh-Hans"],
            extractor=extractor,
            client=client,
            resolver=_public_resolver,
        )

    assert transcript["platform"] == "bilibili"
    assert transcript["channel"] == "品牌"
    assert transcript["content"] == "第一句。\n第二句。"


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

    names = {
        item["name"]
        for item in research_tools.available_research_tools(
            {"tool-web-search", "tool-web-fetch", "tool-video-transcript", "tool-workspace"}
        )
    }
    assert {
        "web_search",
        "web_fetch",
        "search_provider_doctor",
        "video_transcript_fetch",
        "record_claim_evidence",
        "list_claim_evidence",
    } <= names
