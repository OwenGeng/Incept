from __future__ import annotations

import io
import sys
from types import SimpleNamespace

import pytest
from PIL import Image
from psd_tools import PSDImage

from app.incept import store


def _png_bytes() -> bytes:
    image = Image.new("RGB", (2, 3), color=(40, 80, 120))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_psd_upload_is_flattened_to_png_before_it_becomes_an_image_asset() -> None:
    document = PSDImage.new("RGB", (2, 3), color=(1, 2, 3))
    source = io.BytesIO()
    document.save(source)

    content, filename, content_type, analysis = store._maybe_convert_psd(source.getvalue(), "campaign.psd")

    with Image.open(io.BytesIO(content)) as image:
        assert image.format == "PNG"
        assert image.size == (2, 3)
    assert filename == "campaign.png"
    assert content_type == "image/png"
    assert analysis == {
        "source_format": "psd",
        "rasterized_from_psd": True,
        "model_input_mime_type": "image/png",
        "source_width": 2,
        "source_height": 3,
    }


def test_unreadable_psd_is_rejected_instead_of_becoming_model_input(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingPsdImage:
        @staticmethod
        def open(source: io.BytesIO) -> None:
            raise RuntimeError("broken PSD")

    monkeypatch.setitem(sys.modules, "psd_tools", SimpleNamespace(PSDImage=FailingPsdImage))

    with pytest.raises(ValueError, match="could not be converted"):
        store._maybe_convert_psd(b"not a PSD", "broken.psd")


def test_upload_uses_resolved_mime_type_for_storage(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    uploads: list[tuple[bytes, str]] = []
    monkeypatch.setattr(store, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(store, "_upload_bytes_to_gcs", lambda *, content, object_path, content_type: uploads.append((content, content_type)) or "")
    monkeypatch.setattr(store, "_record_asset_storage_status", lambda asset, *, category: None)
    monkeypatch.setattr(store, "upsert_asset", lambda asset: None)

    asset = store.save_uploaded_asset(
        workspace_id="workspace",
        filename="campaign.png",
        content=_png_bytes(),
        asset_role="upload",
        user_id="user",
        content_type="image/png",
    )

    assert asset.type == "image"
    assert (asset.width, asset.height) == (2, 3)
    assert uploads == [(_png_bytes(), "image/png")]


def test_psd_upload_saves_only_the_png_working_copy(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    uploads: list[tuple[bytes, str]] = []
    document = PSDImage.new("RGB", (2, 3), color=(1, 2, 3))
    source = io.BytesIO()
    document.save(source)
    monkeypatch.setattr(store, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(store, "_upload_bytes_to_gcs", lambda *, content, object_path, content_type: uploads.append((content, content_type)) or "")
    monkeypatch.setattr(store, "_record_asset_storage_status", lambda asset, *, category: None)
    monkeypatch.setattr(store, "upsert_asset", lambda asset: None)

    asset = store.save_uploaded_asset(
        workspace_id="workspace",
        filename="campaign.psd",
        content=source.getvalue(),
        asset_role="upload",
        user_id="user",
        content_type="image/vnd.adobe.photoshop",
    )

    assert asset.title == "campaign.png"
    assert asset.preview_url.endswith(".png")
    assert (asset.width, asset.height) == (2, 3)
    assert asset.analysis and asset.analysis["rasterized_from_psd"] is True
    assert uploads[0][0].startswith(b"\x89PNG\r\n\x1a\n")
    assert uploads[0][1] == "image/png"


def test_non_raster_design_files_are_not_resize_eligible_images() -> None:
    assert store._uploaded_asset_type("source.pdf", "application/pdf") == "report"
    assert store._uploaded_asset_type("source.ai", "application/postscript") == "report"
