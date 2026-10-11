from contextlib import ExitStack
import hashlib
import subprocess

from PIL import Image
import pytest

from app.video_studio import agent_media, store


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "assets_root", lambda *_: tmp_path)
    return tmp_path


def tiny_video(root):
    path = root / "clip.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=24", "-f", "lavfi", "-i", "sine=frequency=300", "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True, timeout=15)
    return path


def test_image_is_real_content_reduced_without_changing_original(root):
    path = root / "large.png"
    Image.new("RGB", (3000, 2000), "red").save(path)
    before = hashlib.sha256(path.read_bytes()).digest()
    parts, manifest = agent_media.prepare_assets("user", "project", ["large.png"], provider_id="anthropic")
    assert manifest[0]["inspection"] == "attached"
    assert manifest[0]["mode"] == "image"
    assert max(manifest[0]["prepared_dimensions"]) <= 1536
    assert parts[0].inline_data.mime_type in {"image/jpeg", "image/png"}
    assert hashlib.sha256(path.read_bytes()).digest() == before


def test_corrupt_missing_and_path_escape_do_not_pretend_inspection(root):
    (root / "fake.png").write_bytes(b"not image")
    _, manifest = agent_media.prepare_assets("user", "project", ["fake.png", "missing.png", "../outside.png"])
    assert all(item["inspection"] == "metadata-only" and item["reason"] for item in manifest)


def test_non_google_video_uses_timestamped_samples_and_discloses_missing_audio(root):
    source = tiny_video(root)
    before = source.read_bytes()
    parts, manifest = agent_media.prepare_assets("user", "project", [source.name], provider_id="openai")
    entry = manifest[0]
    assert entry["inspection"] == "attached"
    assert entry["mode"] == "sampled-frames"
    assert entry["no_audio"] is True
    assert 2 <= len(entry["timestamps_seconds"]) <= 12
    assert entry["timestamps_seconds"][0] == 0
    assert entry["timestamps_seconds"][-1] > entry["duration_seconds"] * .8
    assert any(part.inline_data for part in parts)
    assert source.read_bytes() == before


def test_google_small_video_keeps_actual_video_and_audio(root):
    source = tiny_video(root)
    parts, manifest = agent_media.prepare_assets("user", "project", [source.name])
    assert manifest[0]["inspection"] == "attached"
    assert manifest[0]["no_audio"] is False
    assert parts[0].inline_data.mime_type == "video/mp4"


def test_cancel_is_not_converted_to_metadata_only(root):
    Image.new("RGB", (1, 1)).save(root / "image.png")
    def cancel():
        raise InterruptedError("cancelled")
    with pytest.raises(InterruptedError):
        agent_media.prepare_assets("user", "project", ["image.png"], check_cancel=cancel)


def test_playlist_disguised_as_video_is_never_given_to_demuxer(root, monkeypatch):
    (root / "playlist.mp4").write_text("#EXTM3U\nfile:///etc/passwd")
    monkeypatch.setattr(agent_media, "_run", lambda *_args, **_kwargs: pytest.fail("unsafe container reached demuxer"))
    _, manifest = agent_media.prepare_assets("user", "project", ["playlist.mp4"])
    assert manifest[0]["inspection"] == "metadata-only"


def test_owned_gcs_reference_is_cleaned_by_lifecycle(root, monkeypatch):
    source = tiny_video(root)
    monkeypatch.setattr(agent_media, "INLINE_VIDEO_BYTES", 1)
    events = []
    class Blob:
        generation = 123
        def upload_from_filename(self, *_args, **kwargs):
            assert kwargs["if_generation_match"] == 0
            events.append("upload")
        def delete(self, **kwargs):
            assert kwargs["if_generation_match"] == 123
            events.append("delete")
    class Bucket:
        iam_configuration = type("IAM", (), {"uniform_bucket_level_access_enabled": True})()
        def reload(self, **_kwargs):
            pass
        def get_iam_policy(self, **_kwargs):
            return {"bindings": []}
        def blob(self, key):
            assert key.startswith("video/agent-inputs/")
            return Blob()
    monkeypatch.setattr(agent_media.vertex_media, "_asset_bucket", lambda: "already-configured")
    monkeypatch.setattr(agent_media.vertex_media, "_gcs_client", lambda: type("Client", (), {"bucket": lambda self, _: Bucket()})())
    with ExitStack() as resources:
        parts, manifest = agent_media.prepare_assets("user", "project", [source.name], resources=resources)
        assert manifest[0]["mode"] == "video-reference"
        assert parts[0].file_data.file_uri.startswith("gs://already-configured/video/agent-inputs/")
        assert events == ["upload"]
    assert events == ["upload", "delete"]


def test_proxy_without_resource_lifecycle_keeps_audio_and_original(root, monkeypatch):
    source = tiny_video(root)
    original = source.read_bytes()
    monkeypatch.setattr(agent_media, "INLINE_VIDEO_BYTES", 1_000_000)
    # Force proxy via a valid source MIME that isn't directly native-MP4.
    original_container = agent_media._container
    monkeypatch.setattr(agent_media, "_container", lambda path: ("video/avi", original_container(path)[1]))
    parts, manifest = agent_media.prepare_assets("user", "project", [source.name])
    assert manifest[0]["mode"] == "video-proxy"
    assert manifest[0]["no_audio"] is False
    assert parts[0].inline_data.mime_type == "video/mp4"
    assert source.read_bytes() == original


def test_source_and_decoded_budgets_have_specific_reasons(root, monkeypatch):
    Image.new("RGB", (10, 10)).save(root / "image.png")
    monkeypatch.setattr(agent_media, "MAX_PIXELS", 50)
    _, manifest = agent_media.prepare_assets("u", "p", ["image.png"])
    assert "40MP" in manifest[0]["reason"]
    monkeypatch.setattr(agent_media, "IMAGE_SOURCE_BYTES", 1)
    _, manifest = agent_media.prepare_assets("u", "p", ["image.png"])
    assert "100MiB" in manifest[0]["reason"]


def test_long_clip_requires_user_selected_range(root, monkeypatch):
    source = tiny_video(root)
    real_run = agent_media._run
    def run(args, **kwargs):
        if "-show_entries" in args:
            return b'{"streams":[{"codec_type":"video","width":160,"height":90}],"format":{"duration":"181"}}'
        return real_run(args, **kwargs)
    monkeypatch.setattr(agent_media, "_run", run)
    parts, manifest = agent_media.prepare_assets("u", "p", [source.name])
    assert not parts
    assert "180秒" in manifest[0]["reason"]


def test_cancel_during_process_terminates_child(root):
    import sys
    def cancel():
        raise InterruptedError("stop")
    with pytest.raises(agent_media._CancelSignal):
        agent_media._run([sys.executable, "-c", "import time; time.sleep(5)"], cancel=cancel)


def test_request_budget_downgrade_does_not_claim_inspection(root, monkeypatch):
    Image.new("RGB", (10, 10)).save(root / "image.png")
    monkeypatch.setitem(agent_media.REQUEST_BYTES, "anthropic", 1)
    parts, manifest = agent_media.prepare_assets("u", "p", ["image.png"], provider_id="anthropic")
    assert not parts
    assert manifest[0]["inspection"] == "metadata-only"
    assert "分批" in manifest[0]["reason"]


@pytest.mark.parametrize("uniform,members", [(False, []), (True, ["allUsers"]), (True, ["allAuthenticatedUsers"])])
def test_gcs_reference_fails_closed_for_unproven_private_bucket(root, monkeypatch, uniform, members):
    source = tiny_video(root)
    monkeypatch.setattr(agent_media, "INLINE_VIDEO_BYTES", 1_000_000)
    # Keep real MP4 but make inline admission smaller than the real video.
    with source.open("ab") as file:
        file.write(b"\x00" * 1_000_000)
    class Bucket:
        iam_configuration = type("IAM", (), {"uniform_bucket_level_access_enabled": uniform})()
        def reload(self, **kwargs): pass
        def get_iam_policy(self, **kwargs): return {"bindings": [{"members": members}]}
        def blob(self, *_): pytest.fail("bucket privacy not established; no upload permitted")
    monkeypatch.setattr(agent_media.vertex_media, "_asset_bucket", lambda: "configured")
    monkeypatch.setattr(agent_media.vertex_media, "_gcs_client", lambda: type("Client", (), {"bucket": lambda self, _: Bucket()})())
    with ExitStack() as resources:
        parts, manifest = agent_media.prepare_assets("u", "p", [source.name], resources=resources)
        assert manifest[0]["mode"] == "video-proxy"
        assert parts[0].inline_data


def test_unconfirmed_upload_cleanup_never_deletes_someone_elses_object():
    class Blob:
        generation = None
        metadata = {"linglonglab-agent-input": "another-run"}
        def reload(self, **kwargs): self.generation = 17
        def delete(self, **kwargs): pytest.fail("different ownership token must not be deleted")
    agent_media._delete_blob(Blob(), "our-run")


def test_cancelled_sampling_removes_analysis_tempfiles(root, monkeypatch):
    source = tiny_video(root)
    real_run = agent_media._run
    paths = []
    def run(args, **kwargs):
        if "-frames:v" in args:
            paths.append(args[-1])
            raise agent_media._CancelSignal(InterruptedError("cancel"))
        return real_run(args, **kwargs)
    monkeypatch.setattr(agent_media, "_run", run)
    with pytest.raises(InterruptedError):
        agent_media.prepare_assets("u", "p", [source.name], provider_id="openai")
    from pathlib import Path
    assert paths and not Path(paths[0]).parent.exists()


def test_subprocess_log_flood_is_bounded():
    import sys
    with pytest.raises(ValueError, match="安全预算"):
        agent_media._run([sys.executable, "-c", "import sys,time; sys.stderr.write('X'*100000); sys.stderr.flush(); time.sleep(2)"], timeout=3)


def test_total_image_count_includes_video_sample_frames(root, monkeypatch):
    for index in range(2):
        Image.new("RGB", (1, 1)).save(root / f"{index}.png")
    monkeypatch.setattr(agent_media, "MAX_REQUEST_IMAGES", 1)
    parts, manifest = agent_media.prepare_assets("u", "p", ["0.png", "1.png"], provider_id="openai")
    assert len(parts) == 1
    assert manifest[1]["inspection"] == "metadata-only"
    assert "图片数量" in manifest[1]["reason"]
    assert agent_media.MAX_REQUEST_IMAGES == 1


def test_video_samples_count_towards_image_limit(root, monkeypatch):
    source = tiny_video(root)
    monkeypatch.setattr(agent_media, "MAX_REQUEST_IMAGES", 1)
    parts, manifest = agent_media.prepare_assets("u", "p", [source.name], provider_id="anthropic")
    assert not parts
    assert "图片数量" in manifest[0]["reason"]


def test_fast_finished_process_cannot_bypass_output_size_limit(root):
    import sys
    output = root / "result.bin"
    with pytest.raises(ValueError, match="输出预算"):
        agent_media._run([sys.executable, "-c", "from pathlib import Path; import sys; Path(sys.argv[1]).write_bytes(b'X'*100)", str(output)], output_files=[(output, 1)])
