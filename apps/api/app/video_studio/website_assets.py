"""Bounded, tenant-scoped static website media discovery and import.

Only discoverable public files are imported. No JS execution, credentials, DRM,
stream ripping, or fabricated bestseller rankings. A local copy is not a license.
"""

from __future__ import annotations
from contextlib import nullcontext

import hashlib
import ipaddress
import json
import socket
import tempfile
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Literal
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import BaseModel, Field, ConfigDict

from . import store
from .research_tools import ResearchToolError, _normalized_http_url, _iso_now, _write_json_atomic, _html_to_text
from .workspace_documents import document_lock

MAX_PAGE_BYTES = 8_000_000
MAX_DISCOVERY_BYTES = 32_000_000
MAX_DISCOVERY_PAGES = 12
MAX_DISCOVERY_SECONDS = 90
MAX_ITEMS = 200
MAX_IMAGE_BYTES = 20_000_000
MAX_VIDEO_BYTES = 450_000_000
MAX_BATCH_BYTES = 500_000_000
MAX_BATCH_SECONDS = 90


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()


class WebsiteDiscoverRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    directory: str
    url: str = Field(min_length=1, max_length=2000)


class WebsiteImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    directory: str
    asset_ids: list[str] = Field(min_length=1, max_length=12)


class WebsiteAsset(BaseModel):
    id: str
    kind: Literal["image", "video", "logo", "icon"]
    name: str
    description: str = ""
    source_url: str
    page_url: str
    product_url: str | None = None
    bestseller_evidence: str | None = None
    status: Literal["discovered", "imported", "failed"] = "discovered"
    rights_status: Literal["unverified"] = "unverified"
    path: str | None = None
    workspace_path: str | None = None
    mime_type: str | None = None
    size: int | None = None
    sha256: str | None = None
    error: str | None = None
    discovered_at: str


def _catalog_path(email: str, project_id: str) -> Path:
    return store.safe_asset_path(store.assets_root(email, project_id), "intake/website-assets.json")


def _read_catalog(path: Path) -> list[WebsiteAsset]:
    if not path.exists():
        return []
    if path.stat().st_size > 2_000_000:
        raise ResearchToolError("网站素材目录过大")
    try:
        return [WebsiteAsset.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))["assets"]]
    except (ValueError, KeyError, TypeError) as error:
        raise ResearchToolError("网站素材目录损坏，未覆盖已有内容") from error


def list_website_assets(email: str, project_id: str) -> list[dict[str, Any]]:
    path = _catalog_path(email, project_id)
    with document_lock(path):
        items = _read_catalog(path)
    root = store.assets_root(email, project_id)
    result = []
    for item in items:
        if item.workspace_path and not store.safe_asset_path(root, item.workspace_path).is_file():
            item.status, item.path, item.workspace_path = "discovered", None, None
        result.append(item.model_dump())
    return result


def _pinned_target(raw_url: str, resolver: Callable = socket.getaddrinfo) -> tuple[str, str, str]:
    url = _normalized_http_url(raw_url)
    parsed = urlsplit(url)
    if parsed.scheme != "https":
        raise ResearchToolError("网站素材采集仅支持HTTPS链接")
    try:
        records = resolver(parsed.hostname, 443, type=socket.SOCK_STREAM)
    except OSError as error:
        raise ResearchToolError("无法解析网站地址") from error
    if not records:
        raise ResearchToolError("无法解析网站地址")
    addresses = [ipaddress.ip_address(item[4][0]) for item in records]
    if any(not address.is_global for address in addresses):
        raise ResearchToolError("禁止访问内网或非公开地址")
    return url, str(addresses[0]), str(parsed.hostname)


class PublicMediaTransport(httpx.HTTPTransport):
    """Pin each connection to validated DNS; retain TLS verification and SNI."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        url, address, hostname = _pinned_target(str(request.url))
        headers = request.headers.copy()
        headers["Host"] = hostname
        pinned = httpx.Request(request.method, httpx.URL(url).copy_with(host=address),
            headers=headers, stream=request.stream,
            extensions={**request.extensions, "sni_hostname": hostname})
        return super().handle_request(pinned)


def _client() -> httpx.Client:
    # Different hostnames can resolve to one IP; never reuse a TLS connection
    # authenticated for another hostname after replacing the connection origin.
    return httpx.Client(transport=PublicMediaTransport(limits=httpx.Limits(max_keepalive_connections=0)), trust_env=False, follow_redirects=False,
        timeout=20, headers={"User-Agent": "LinglongLab-WebsiteAssets/1.0"})


class MediaParser(HTMLParser):
    def __init__(self, url: str):
        super().__init__(convert_charrefs=True)
        self.url = url
        self.title = ""
        self.description = ""
        self.media: list[dict[str, Any]] = []
        self.links: list[tuple[str, str]] = []
        self._anchor: tuple[str, list[str]] | None = None
        self._title = False
        self._document_title_seen = False
        self._svg_depth = 0
        self._video = False
        self._script_type: str | None = None
        self._script: list[str] = []
        self._schemas: list[Any] = []
        self._media_by_url: dict[str, dict[str, Any]] = {}
        self._elements: list[tuple[str, bool]] = []

    def add(self, url: Any, kind: str, name: str = "", **details):
        if not isinstance(url, str) or not url.strip():
            return
        try:
            normalized = _normalized_http_url(urljoin(self.url, url.strip()))
        except ResearchToolError:
            return
        if urlsplit(normalized).scheme != "https" or len(normalized) > 2000:
            return
        # Explicit video files only; embedded players/HLS remain source-page links.
        if kind == "video" and not urlsplit(normalized).path.lower().endswith((".mp4", ".webm", ".mov")):
            return
        item = {"source_url": normalized, "kind": kind, "name": name[:300], **details}
        if self._elements and self._elements[-1][1] and '/products/' in urlsplit(self.url).path and kind in {'image','video'}:
            item.setdefault('product_url', self.url)
        previous = self._media_by_url.get(normalized)
        if previous is not None:
            if item.get('product_url') or kind in {'logo', 'icon'}: previous.update(item)
            return
        # Reserve candidate headroom for structured product galleries emitted
        # after navigation thumbnails. The final catalog remains capped at 200.
        if len(self.media) >= MAX_ITEMS * 3:
            if not item.get('product_url'): return
            replace = next((old for old in reversed(self.media) if not old.get('product_url')), None)
            if replace is None: return
            self.media.remove(replace)
            self._media_by_url.pop(replace['source_url'], None)
        self.media.append(item)
        self._media_by_url[normalized] = item

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        marker = (tag + ' ' + a.get('class','') + ' ' + a.get('id','')).lower()
        gallery = any(value in marker for value in ('product-gallery','media-gallery','product-media'))
        if tag not in {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}:
            self._elements.append((tag, gallery or bool(self._elements and self._elements[-1][1])))
        if tag == "svg": self._svg_depth += 1
        if tag == "title" and not self._document_title_seen and not self._svg_depth:
            self._title, self._document_title_seen = True, True
        if tag == "script": self._script_type, self._script = a.get("type", ""), []
        if tag == "a" and a.get("href"):
            self._anchor = (urljoin(self.url, a["href"]), [])
        if tag == "meta":
            key, value = a.get("property", a.get("name", "")), a.get("content", "")
            if key == "og:title": self.title = value[:300]
            if key in {"description", "og:description"}: self.description = value[:1000]
            if key in {"og:image", "og:image:secure_url"}: self.add(value, "image")
            if key in {"og:video", "og:video:secure_url"}: self.add(value, "video")
        if tag == "link" and "icon" in a.get("rel", ""):
            self.add(a.get("href"), "icon", "网站图标")
        if tag == "img":
            name = a.get("alt", "")
            kind = "logo" if "logo" in (name + " " + a.get("class", "")).lower() else "image"
            srcset = a.get("srcset") or a.get("data-srcset") or ""
            choices = [part.strip().split()[0] for part in srcset.split(",") if part.strip()]
            self.add(choices[-1] if choices else a.get("data-src") or a.get("src"), kind, name)
        if tag == "video":
            self._video = True
            name = a.get('title') or a.get('aria-label', '')
            self.add(a.get("src") or a.get('data-src') or a.get('data-poster-src'), "video", name)
            self.add(a.get("poster"), "image", "视频封面")
        if tag == "source" and self._video: self.add(a.get("src") or a.get('data-src'), "video")

    def handle_data(self, data):
        if self._title: self.title = (self.title + data)[:300]
        if self._anchor: self._anchor[1].append(data)
        if self._script_type == "application/ld+json": self._script.append(data)

    def handle_endtag(self, tag):
        for index in range(len(self._elements) - 1, -1, -1):
            if self._elements[index][0] == tag:
                del self._elements[index:]
                break
        if tag == "svg": self._svg_depth = max(0, self._svg_depth - 1)
        if tag == "title": self._title = False
        if tag == "video": self._video = False
        if tag == "a" and self._anchor:
            if len(self.links) < 1000: self.links.append((self._anchor[0], " ".join(self._anchor[1])[:500]))
            self._anchor = None
        if tag == "script":
            if self._script_type == "application/ld+json":
                try: self._schemas.append(json.loads("".join(self._script)))
                except (ValueError, RecursionError): pass
            self._script_type, self._script = None, []

    def structured_media(self):
        def walk(value, product=None, depth=0):
            if depth > 16: return
            if isinstance(value, list):
                for item in value: walk(item, product, depth + 1)
            elif isinstance(value, dict):
                types = value.get("@type", [])
                types = types if isinstance(types, list) else [types]
                if "Product" in types:
                    try: product_url = _normalized_http_url(urljoin(self.url, str(value.get("url") or self.url)))
                    except ResearchToolError: product_url = self.url
                    product = {"name": str(value.get("name", ""))[:300],
                        "description": _html_to_text(str(value.get("description", "")))[:1000], "product_url": product_url}
                    images = value.get("image", [])
                    for image in images if isinstance(images, list) else [images]:
                        self.add(image.get("url") if isinstance(image, dict) else image, "image", **product)
                if "VideoObject" in types:
                    self.add(value.get("contentUrl"), "video", **(product or {"name": str(value.get("name", ""))[:300]}))
                logo = value.get("logo")
                if logo: self.add(logo.get("url") if isinstance(logo, dict) else logo, "logo", "品牌Logo")
                for child in value.values():
                    if isinstance(child, (list, dict)): walk(child, product, depth + 1)
        for schema in self._schemas: walk(schema)


def _fetch_html(url: str, client: httpx.Client, resolver: Callable, *,
                budget: list[int] | None = None, deadline: float | None = None,
                check_cancel: Callable | None = None) -> tuple[str, str]:
    # Validates mock clients too; real transport additionally pins DNS at connect.
    current, _, _ = _pinned_target(url, resolver)
    for _ in range(4):
        if check_cancel: check_cancel()
        if deadline is not None and time.monotonic() >= deadline:
            raise ResearchToolError('素材发现超过90秒采集限制')
        with client.stream("GET", current, follow_redirects=False) as response:
            if response.is_redirect:
                current, _, _ = _pinned_target(urljoin(current, response.headers.get("location", "")), resolver)
                continue
            if response.status_code != 200:
                raise ResearchToolError(f"网站返回HTTP {response.status_code}，未绕过访问限制")
            if response.headers.get("content-type", "").split(";", 1)[0] not in {"text/html", "application/xhtml+xml"}:
                raise ResearchToolError("请输入公开HTML网页地址")
            data = bytearray()
            # Decoded streaming bytes also bound compressed responses.
            # https://www.python-httpx.org/quickstart/#streaming-responses
            for chunk in response.iter_bytes(chunk_size=64 * 1024):
                if check_cancel: check_cancel()
                if deadline is not None and time.monotonic() >= deadline:
                    raise ResearchToolError('素材发现超过90秒采集限制')
                if budget is not None:
                    budget[0] += len(chunk)
                    if budget[0] > MAX_DISCOVERY_BYTES:
                        raise ResearchToolError('素材发现超过32MB总采集限制')
                data.extend(chunk)
                if len(data) > MAX_PAGE_BYTES: raise ResearchToolError("网页超过8MB采集限制")
            return current, data.decode(response.encoding or "utf-8", errors="replace")
    raise ResearchToolError("网页重定向过多")


def discover_website_assets(email: str, project_id: str, url: str, *, client=None, resolver=socket.getaddrinfo,
                            check_cancel: Callable | None = None, mutation_lock: Callable = nullcontext) -> dict:
    path = _catalog_path(email, project_id)  # tenant/project ownership checked before network
    owned = client is None
    client = client or _client()
    queue = [(url, None)]
    visited: set[str] = set()
    found: dict[str, WebsiteAsset] = {}
    warnings = []
    budget = [0]
    deadline = time.monotonic() + MAX_DISCOVERY_SECONDS
    product_seed = '/products/' in urlsplit(url).path
    try:
        while queue and len(visited) < MAX_DISCOVERY_PAGES:
            if check_cancel: check_cancel()
            if budget[0] >= MAX_DISCOVERY_BYTES or time.monotonic() >= deadline:
                warnings.append('素材发现达到总大小或时间限制；已发现素材保留，请按商品页分批继续。')
                break
            candidate, bestseller = queue.pop(0)
            if candidate in visited: continue
            visited.add(candidate)
            try:
                page_url, html = _fetch_html(candidate, client, resolver, budget=budget,
                    deadline=deadline, check_cancel=check_cancel)
                if check_cancel: check_cancel()
                parser = MediaParser(page_url)
                parser.feed(html)
                parser.structured_media()
            except (ResearchToolError, httpx.HTTPError) as error:
                if len(visited) == 1: raise ResearchToolError(str(error)) from error
                warnings.append(f"{candidate}: {error}")
                continue
            for item in parser.media:
                ident = hashlib.sha256(item["source_url"].encode()).hexdigest()[:32]
                asset = WebsiteAsset(id=ident, page_url=page_url, discovered_at=_iso_now(),
                    description=item.pop("description", parser.description), bestseller_evidence=bestseller,
                    **{**item, "name": item["name"] or parser.title or "网站素材"})
                previous = found.get(ident)
                if previous is None or asset.product_url or asset.kind in {"logo", "icon"}: found[ident] = asset
            # Follow only observed same-origin bestseller links/product links, never invented /products.json endpoints.
            if product_seed: continue  # Selected SKU must not expand to navigation's other vehicles.
            follow = []
            for link, label in parser.links:
                if urlsplit(link).netloc != urlsplit(page_url).netloc: continue
                if link in visited or any(queued[0] == link for queued in queue + follow): continue
                if any(token in (link + " " + label).lower() for token in ("best-seller", "bestseller", "best seller", "best-selling", "热销")):
                    follow.append((link, f"官网链接标注：{label or link}"))
                elif bestseller and "/products/" in urlsplit(link).path:
                    follow.append((link, bestseller))
            queue = follow + queue  # Inspect observed bestseller products before other navigation.
        if queue:
            warnings.append('素材发现达到巡查上限；未巡查的页面不代表没有素材，请按商品页继续。')
    finally:
        if owned: client.close()
    with mutation_lock(), document_lock(path):
        existing = {item.id: item for item in _read_catalog(path)}
        # Product galleries and videos outrank generic page imagery and branding.
        ranked = sorted(found.values(), key=lambda item: (not bool(item.product_url or item.kind == 'video'), item.kind != 'video', item.kind in {'logo', 'icon'}))
        for item in ranked[:MAX_ITEMS]:
            ident = item.id
            if ident not in existing: existing[ident] = item
            elif existing[ident].status != "imported": existing[ident] = item
        if len(existing) > MAX_ITEMS:
            warnings.append("项目网站素材最多200项；已有素材保留，未继续添加。")
        _write_json_atomic(path, {"assets": [item.model_dump() for item in list(existing.values())[:MAX_ITEMS]]})
    assets = list_website_assets(email, project_id)
    return {"assets": assets, "pages_inspected": len(visited), "warnings": warnings,
        "media_counts": {kind: sum(item['kind'] == kind for item in assets) for kind in ('image','video','logo','icon')},
        "product_asset_count": sum(bool(item['product_url']) for item in assets),
        "limitations": "仅静态网页公开素材；Best seller标签不等于销量排名；未发现的视频不代表网站没有视频；广告使用权待确认。"}


def _media_format(prefix: bytes) -> tuple[str, str]:
    if prefix.startswith(b"\xff\xd8\xff"): return "image/jpeg", ".jpg"
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"): return "image/png", ".png"
    if prefix.startswith((b"GIF87a", b"GIF89a")): return "image/gif", ".gif"
    if prefix[:4] == b"RIFF" and prefix[8:12] == b"WEBP": return "image/webp", ".webp"
    if prefix.startswith(b"\x00\x00\x01\x00"): return "image/x-icon", ".ico"
    if prefix[4:8] == b"ftyp":
        if b"avif" in prefix[8:32] or b"avis" in prefix[8:32]: return "image/avif", ".avif"
        if prefix[8:12] == b"qt  ": return "video/quicktime", ".mov"
        return "video/mp4", ".mp4"
    if prefix.startswith(b"\x1a\x45\xdf\xa3") and b"webm" in prefix: return "video/webm", ".webm"
    raise ResearchToolError("文件不是支持的图片/视频格式（不导入HTML、SVG或流媒体播放列表）")


def import_website_assets(email: str, project_id: str, asset_ids: list[str], *, client=None, resolver=socket.getaddrinfo,
                          check_cancel: Callable | None = None, mutation_lock: Callable = nullcontext) -> dict:
    if not 1 <= len(asset_ids) <= 12 or not all(isinstance(i, str) and len(i) == 32 for i in asset_ids):
        raise ResearchToolError("每次请选择1–12个已发现的素材")
    catalog = _catalog_path(email, project_id)
    root = store.assets_root(email, project_id)
    with document_lock(catalog):
        lookup = {item.id: item for item in _read_catalog(catalog)}
        if any(ident not in lookup for ident in asset_ids): raise ResearchToolError("只能导入当前项目已发现的素材")
    owned = client is None
    client = client or _client()
    results = []
    total_bytes = 0
    deadline = time.monotonic() + MAX_BATCH_SECONDS
    def save_results():
        with mutation_lock(), document_lock(catalog):
            latest = {item.id: item for item in _read_catalog(catalog)}
            for item in results:
                current = latest.get(item.id)
                if current and current.status == 'imported' and item.status == 'failed':
                    continue
                latest[item.id] = item
            _write_json_atomic(catalog, {'assets':[item.model_dump() for item in latest.values()]})
    try:
        for ident in dict.fromkeys(asset_ids):
            if check_cancel: check_cancel()
            item = lookup[ident]
            if item.workspace_path and store.safe_asset_path(root, item.workspace_path).is_file():
                results.append(item)
                continue
            temporary = None
            try:
                if time.monotonic() >= deadline: raise ResearchToolError("本批采集超时，请分批重试")
                url, _, _ = _pinned_target(item.source_url, resolver)
                max_bytes = MAX_VIDEO_BYTES if item.kind == "video" else MAX_IMAGE_BYTES
                with client.stream("GET", url, follow_redirects=False) as response:
                    if response.status_code != 200: raise ResearchToolError(f"素材返回HTTP {response.status_code}；未跟随重定向或绕过访问限制")
                    size = int(response.headers.get("content-length", "0"))
                    if size > max_bytes or total_bytes + size > MAX_BATCH_BYTES: raise ResearchToolError("素材超过采集大小限制")
                    temp_dir = store.safe_asset_path(root, "library/website")
                    temp_dir.mkdir(parents=True, exist_ok=True)
                    digest, count, prefix = hashlib.sha256(), 0, bytearray()
                    with tempfile.NamedTemporaryFile(dir=temp_dir, prefix=".import-", delete=False) as output:
                        temporary = Path(output.name)
                        for chunk in response.iter_bytes(chunk_size=64 * 1024):
                            if check_cancel: check_cancel()
                            count += len(chunk)
                            total_bytes += len(chunk)
                            if count > max_bytes or total_bytes > MAX_BATCH_BYTES or time.monotonic() >= deadline:
                                raise ResearchToolError("素材超出大小/时间限制，未保存不完整文件")
                            if len(prefix) < 512: prefix.extend(chunk[:512 - len(prefix)])
                            digest.update(chunk)
                            output.write(chunk)
                    mime, extension = _media_format(bytes(prefix))
                    if (item.kind == "video") != mime.startswith("video/"): raise ResearchToolError("素材实际格式与发现类型不符")
                    path = f"website/{ident}{extension}"
                    target = store.safe_asset_path(root, f"library/{path}")
                    with mutation_lock(), document_lock(target):
                        if target.exists():
                            if _file_sha256(target) != digest.hexdigest():
                                raise ResearchToolError("来源文件已变化，未覆盖已有素材")
                        else: temporary.replace(target)
                    item.status, item.path, item.workspace_path = "imported", path, f"library/{path}"
                    item.mime_type, item.size, item.sha256, item.error = mime, count, digest.hexdigest(), None
            except (ResearchToolError, httpx.HTTPError, ValueError, OSError) as error:
                item.status, item.error = "failed", str(error)[:500]
            finally:
                if temporary: temporary.unlink(missing_ok=True)
            results.append(item)
            if check_cancel: check_cancel()
            save_results()
    finally:
        if owned: client.close()
    return {"assets": [item.model_dump() for item in results],
        "imported_count": sum(item.status == "imported" for item in results),
        "failed_count": sum(item.status == "failed" for item in results),
        "display_location": "画布 → 素材库 → 客户网站素材（本地文件位于website文件夹）",
        "rights_notice": "采集仅供制作参考；公开可下载不代表拥有广告使用权，投放前需客户确认。"}
