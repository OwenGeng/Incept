"""The approved customer campaign profile is the technical acceptance contract."""

import pytest

from app.video_studio.creative_specs import check_moloco_ctv_metadata, moloco_ctv_instructions, moloco_ctv_profile


def probe(duration="60", fps="24/1", width=1280, height=720):
    return {"streams": [{"codec_type": "video", "width": width, "height": height,
                         "avg_frame_rate": fps}], "format": {"duration": duration}}


def test_confirmed_customer_profile_does_not_require_another_spec_approval():
    profile = moloco_ctv_profile()
    assert profile["approval_status"] == "customer_configuration_confirmed"
    assert profile["max_file_bytes"] == 450_000_000
    assert profile["accepted_resolutions"] == [[1920, 1080], [1280, 720]]
    assert profile["duration_seconds"] == {"minimum": 6, "maximum": 180, "recommended": [15, 30, 60]}
    assert not profile["warnings"]
    assert "<=50 MB" not in moloco_ctv_instructions()
    assert "require exchange confirmation" not in moloco_ctv_instructions()


def test_60_seconds_at_450_decimal_mb_passes_without_obsolete_ctv_warnings():
    result = check_moloco_ctv_metadata(probe(), size=450_000_000, is_mp4=True)
    assert result["status"] == "technical_pass"
    assert result["technical_checks_passed"] is True
    assert result["warnings"] == []
    # Technical conformance does not prove advertising rights or platform approval.
    assert result["approved_for_delivery"] is False
    assert result["approval_checks"] == {"advertising_rights": "unverified", "platform_review": "unverified"}


@pytest.mark.parametrize("duration", ["6", "15", "30", "60", "180"])
def test_entire_approved_duration_range_is_accepted(duration):
    result = check_moloco_ctv_metadata(probe(duration), size=80_000_000, is_mp4=True)
    assert result["status"] == "technical_pass"
    assert not any("50MB" in warning or "15/30秒" in warning for warning in result["warnings"])


@pytest.mark.parametrize("metadata,size,is_mp4", [
    (probe("5.99"), 1, True), (probe("180.01"), 1, True),
    (probe(fps="23/1"), 1, True), (probe(width=640, height=360), 1, True),
    (probe(), 450_000_001, True), (probe(), 1, False),
])
def test_out_of_profile_media_remains_invalid(metadata, size, is_mp4):
    result = check_moloco_ctv_metadata(metadata, size=size, is_mp4=is_mp4)
    assert result["status"] == "invalid"
    assert result["technical_checks_passed"] is False
    assert result["errors"]


def test_profile_return_is_isolated_from_consumer_edits():
    profile = moloco_ctv_profile()
    profile["accepted_resolutions"].clear()
    assert len(moloco_ctv_profile()["accepted_resolutions"]) == 2
