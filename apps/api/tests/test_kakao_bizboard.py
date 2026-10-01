import base64
import asyncio
import socket
from io import BytesIO

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import settings
from app.routers import kakao

TEMPLATES = list(kakao.LAYOUTS)


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = FastAPI()
    app.include_router(kakao.router)
    return TestClient(
        app,
        headers={"X-Internal-API-Key": settings.internal_api_key},
    )


def _data_url(size: tuple[int, int], color=(40, 120, 200, 255)) -> str:
    buf = BytesIO()
    Image.new("RGBA", size, color).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _object_data_url(canvas: tuple[int, int], obj: tuple[int, int]) -> str:
    img = Image.new("RGBA", canvas, (0, 0, 0, 0))
    img.paste(Image.new("RGBA", obj, (200, 80, 40, 255)), ((canvas[0] - obj[0]) // 2, (canvas[1] - obj[1]) // 2))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _request(template: str, **overrides) -> dict:
    spec = kakao.LAYOUTS[template][True]
    is_object = template in kakao.OBJECT_TEMPLATES
    body = {
        "template": template,
        "thumbnailUrl": _object_data_url((400, 300), (290, 150)) if is_object else _data_url((640, 444)),
        "appIconUrl": _data_url((64, 64), (255, 180, 0, 255)) if spec.app_copy else None,
        "appCopy": "카카오톡 앱에서 확인" if spec.app_copy else "",
        "mainCopy": "새로운 모험이 시작됩니다",
        "subCopy": "지금 사전예약하고 보상 받기" if spec.sub else "",
        "additionalInfo": "",
        "gacha": False,
    }
    return {**body, **overrides}


def _visible(img: Image.Image, box: tuple[int, int, int, int]) -> bool:
    return img.crop(box).getchannel("A").getbbox() is not None


@pytest.mark.parametrize("has_info", [True, False])
@pytest.mark.parametrize("template", TEMPLATES)
def test_renders_960x300_transparent_png_within_size_limit(client, template, has_info):
    response = client.post("/api/v1/kakao/compose-bizboard", json=_request(template, gacha=has_info))

    assert response.status_code == 200, response.text
    assert len(response.content) <= kakao.MAX_OUTPUT_BYTES
    img = Image.open(BytesIO(response.content))
    assert img.size == (960, 300)
    assert img.mode == "RGBA"
    assert img.getpixel((0, 0))[3] == 0
    assert _visible(img, kakao.THUMBNAIL_RECT)
    layout = kakao.LAYOUTS[template][has_info]
    assert _visible(img, (layout.main.x, layout.main.baseline - 40, kakao.TEXT_RIGHT, layout.main.baseline + 5))
    if has_info:
        assert _visible(img, (layout.info.x, layout.info.baseline - 20, kakao.TEXT_RIGHT, layout.info.baseline + 5))
    # Copy never crosses into the thumbnail gap (32px from the thumbnail edge).
    assert not _visible(img, (kakao.TEXT_RIGHT, 0, kakao.THUMBNAIL_RECT[0], 300))


@pytest.mark.parametrize("template", TEMPLATES)
def test_copy_is_recentred_when_there_is_no_additional_info(client, template):
    with_info = kakao.LAYOUTS[template][True]
    without_info = kakao.LAYOUTS[template][False]
    assert without_info.main.baseline > with_info.main.baseline

    response = client.post("/api/v1/kakao/compose-bizboard", json=_request(template))
    img = Image.open(BytesIO(response.content))
    # Nothing is drawn in the (empty) additional-info band of the with-info layout.
    assert not _visible(img, (with_info.info.x, with_info.info.baseline - 3, kakao.TEXT_RIGHT, with_info.info.baseline + 5))


def test_thumbnail_corners_are_rounded(client):
    response = client.post("/api/v1/kakao/compose-bizboard", json=_request(TEMPLATES[0]))
    img = Image.open(BytesIO(response.content))
    left, top, right, bottom = kakao.THUMBNAIL_RECT
    assert img.getpixel((left, top))[3] == 0
    assert img.getpixel((left + 160, top + 111))[3] == 255


def test_gacha_adds_mandatory_notice():
    assert kakao.build_additional_info("", True) == kakao.GACHA_INFO
    assert kakao.build_additional_info("이미지 출처: Moloco", True) == f"{kakao.GACHA_INFO} · 이미지 출처: Moloco"
    assert kakao.build_additional_info(kakao.GACHA_INFO, True) == kakao.GACHA_INFO
    assert kakao.build_additional_info("", False) == ""


@pytest.mark.parametrize(
    ("template", "overrides", "message"),
    [
        ("APP_DOWNLOAD_ONE_LINE_COPY_THUMBNAIL", {"mainCopy": "출시"}, "too short"),
        ("APP_DOWNLOAD_ONE_LINE_COPY_THUMBNAIL", {"mainCopy": "가" * 40}, "too long"),
        ("APP_DOWNLOAD_ONE_LINE_COPY_THUMBNAIL", {"appIconUrl": None}, "App icon is required"),
        ("APP_DOWNLOAD_ONE_LINE_COPY_THUMBNAIL", {"appCopy": "지금 확인하기"}, "must include"),
        ("APP_DOWNLOAD_TWO_LINE_COPY_THUMBNAIL", {"subCopy": "새로운 모험이 시작됩니다"}, "cannot be the same"),
        ("TWO_LINE_COPY_THUMBNAIL", {"subCopy": ""}, "Sub copy is required"),
        ("TWO_LINE_COPY_THUMBNAIL", {"mainCopy": "지금 바로 ☞ 확인"}, "special characters"),
    ],
)
def test_rejects_copy_that_breaks_kakao_rules(client, template, overrides, message):
    response = client.post("/api/v1/kakao/compose-bizboard", json=_request(template, **overrides))

    assert response.status_code == 422
    assert any(message in error for error in response.json()["detail"])


def test_sales_template_does_not_need_app_icon(client):
    response = client.post("/api/v1/kakao/compose-bizboard", json=_request("TWO_LINE_COPY_THUMBNAIL"))

    assert response.status_code == 200, response.text


OBJECT = "APP_DOWNLOAD_ONE_LINE_COPY_OBJECT"


def _render(client, **overrides) -> Image.Image:
    response = client.post("/api/v1/kakao/compose-bizboard", json=_request(OBJECT, **overrides))
    assert response.status_code == 200, response.text
    return Image.open(BytesIO(response.content))


def test_object_is_trimmed_scaled_to_314px_and_vertically_centred(client):
    img = _render(client)
    # 290x150 object (padding trimmed) -> 314x162, centred in 300px height.
    assert img.getchannel("A").crop((kakao.OBJECT_X, 0, 960, 300)).getbbox() == (0, 69, 314, 231)


def test_tall_object_is_centre_cropped_to_full_height(client):
    img = _render(client, thumbnailUrl=_object_data_url((300, 700), (250, 600)))
    assert img.getchannel("A").crop((kakao.OBJECT_X, 0, 960, 300)).getbbox() == (0, 0, 314, 300)


def test_object_rejects_opaque_images(client):
    response = client.post("/api/v1/kakao/compose-bizboard", json=_request(OBJECT, thumbnailUrl=_data_url((400, 300))))
    assert response.status_code == 422
    assert "transparent background" in response.json()["detail"][0]


def test_object_rejects_objects_narrower_than_219px(client):
    response = client.post("/api/v1/kakao/compose-bizboard", json=_request(OBJECT, thumbnailUrl=_object_data_url((400, 300), (150, 150))))
    assert response.status_code == 422
    assert "219px" in response.json()["detail"][0]


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/image.png",
        "https://127.0.0.1/image.png",
        "https://169.254.169.254/computeMetadata/v1/",
        "https://[::1]/image.png",
    ],
)
def test_remote_image_url_rejects_insecure_or_private_targets(url):
    with pytest.raises(ValueError):
        kakao.validate_remote_image_url(url)


def test_remote_image_url_rejects_domains_resolving_to_private_addresses(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.7", 443))],
    )

    with pytest.raises(ValueError):
        kakao.validate_remote_image_url("https://images.example.com/ad.png")


def test_remote_image_fetch_rejects_redirects(monkeypatch):
    monkeypatch.setattr(kakao, "validate_remote_image_url", lambda url: url)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(302, headers={"location": "https://other.example/image.png"})
    )

    async def fetch() -> None:
        async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
            await kakao._fetch_image(client, "https://images.example.com/ad.png")

    with pytest.raises(Exception, match="redirect"):
        asyncio.run(fetch())


def test_remote_image_fetch_rejects_oversized_responses(monkeypatch):
    monkeypatch.setattr(kakao, "validate_remote_image_url", lambda url: url)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-length": str(kakao.MAX_SOURCE_IMAGE_BYTES + 1)},
            content=b"x",
        )
    )

    async def fetch() -> None:
        async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
            await kakao._fetch_image(client, "https://images.example.com/ad.png")

    with pytest.raises(Exception, match="too large"):
        asyncio.run(fetch())


def test_remote_image_fetch_rejects_invalid_content_length(monkeypatch):
    monkeypatch.setattr(kakao, "validate_remote_image_url", lambda url: url)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, headers={"content-length": "not-a-number"}, content=b"x")
    )

    async def fetch() -> None:
        async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
            await kakao._fetch_image(client, "https://images.example.com/ad.png")

    with pytest.raises(Exception, match="invalid content length"):
        asyncio.run(fetch())


def test_source_image_rejects_non_image_bytes():
    with pytest.raises(Exception, match="not a valid image"):
        kakao._open_source_image(b"not an image")
