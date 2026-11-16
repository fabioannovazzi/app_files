"""Local media handoffs retain bytes and prevent unconfirmed/repeated transmissions."""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def media(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/clara/scripts"))
    spec = importlib.util.spec_from_file_location(
        "test_media_app", ROOT / "plugins/clara/scripts/media_mcp.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    app = module.MediaApp(tmp_path / "state")
    monkeypatch.setattr(app, "prepare_audio", lambda state: Path(state["source"]))
    return app


def selected(media, tmp_path):
    source = tmp_path / "source.wav"
    source.write_bytes(b"synthetic audio fixture")
    result = media.open("transcribe", str(tmp_path), str(source))
    return result["structuredContent"]["session"], source


def test_selection_is_local_and_durable_without_transmission(media, tmp_path):
    session, source = selected(media, tmp_path)
    resumed = type(media)(media.state_root).status(session)
    assert resumed["structuredContent"]["status"] == "ready"
    assert source.read_bytes() == b"synthetic audio fixture"
    assert "synthetic audio fixture" not in json.dumps(resumed)


def test_run_before_panel_confirmation_does_not_call_processor(
    media, tmp_path, monkeypatch
):
    session, _ = selected(media, tmp_path)
    monkeypatch.setattr(
        media, "process", lambda *args: pytest.fail("unexpected transmission")
    )
    with pytest.raises(ValueError, match="not confirmed"):
        media.run(session, str(tmp_path / "missing-cookie"))


def test_missing_authentication_retains_confirmed_file(media, tmp_path):
    session, source = selected(media, tmp_path)
    media.confirm(session)
    result = media.run(session, str(tmp_path / "missing-cookie"))
    assert result["structuredContent"]["status"] == "authentication_required"
    assert source.exists()


def test_changed_selection_requires_new_review_before_processing(media, tmp_path):
    session, source = selected(media, tmp_path)
    source.write_bytes(b"replacement recording")
    with pytest.raises(ValueError, match="changed"):
        media.confirm(session)


def test_duplicate_chunk_retry_preserves_original_recording(media, tmp_path):
    session = media.open("transcribe", str(tmp_path))["structuredContent"]["session"]
    chunk = base64.b64encode(b"abc").decode()
    media.save(session, "recording.wav", 0, chunk, True)
    result = media.save(session, "recording.wav", 0, chunk, True)
    state = json.loads((media.state_root / f"{session}.json").read_text())
    assert Path(state["source"]).read_bytes() == b"abc"
    assert result["structuredContent"]["status"] == "ready"


@pytest.mark.parametrize(
    "name", ["../outside.wav", "a/b.wav", "..\\outside.wav", "payload.exe"]
)
def test_selected_filename_cannot_escape_or_execute(media, tmp_path, name):
    session = media.open("transcribe", str(tmp_path))["structuredContent"]["session"]
    with pytest.raises(ValueError, match="filename"):
        media.save(session, name, 0, "YWJj", True)


def test_out_of_order_chunk_does_not_corrupt_retained_file(media, tmp_path):
    session = media.open("transcribe", str(tmp_path))["structuredContent"]["session"]
    media.save(session, "recording.wav", 0, "YWJj", False)
    with pytest.raises(ValueError, match="in order"):
        media.save(session, "recording.wav", 2, "ZGVm", True)
    assert (
        tmp_path / ".clara-media" / session / "recording.part"
    ).read_bytes() == b"abc"


def test_completed_run_reopens_retained_output_without_retransmission(
    media, tmp_path, monkeypatch
):
    session, _ = selected(media, tmp_path)
    media.confirm(session)
    cookie = tmp_path / "cookie"
    cookie.write_text("session=fictional")
    output = tmp_path / "bundle.json"
    output.write_text('{"transcript":"synthetic"}')
    monkeypatch.setattr(media, "process", lambda *args: output)
    media.run(session, str(cookie))
    monkeypatch.setattr(
        media, "process", lambda *args: pytest.fail("duplicate transmission")
    )
    result = media.run(session, str(cookie))
    assert result["structuredContent"]["status"] == "complete"
    assert result["structuredContent"]["output"] == str(output)


def test_uncertain_remote_result_is_not_automatically_retried(
    media, tmp_path, monkeypatch
):
    session, _ = selected(media, tmp_path)
    media.confirm(session)
    cookie = tmp_path / "cookie"
    cookie.write_text("session=fictional")

    def fail(*args):
        raise OSError("connection lost after submission")

    monkeypatch.setattr(media, "process", fail)
    with pytest.raises(ValueError, match="Retained"):
        media.run(session, str(cookie))
    assert media.status(session)["structuredContent"]["status"] == "needs_review"
    monkeypatch.setattr(
        media, "process", lambda *args: pytest.fail("duplicate transmission")
    )
    with pytest.raises(ValueError, match="needs review"):
        media.run(session, str(cookie))


def test_concurrent_worker_cannot_submit_same_job(media, tmp_path, monkeypatch):
    session, _ = selected(media, tmp_path)
    media.confirm(session)
    (media.state_root / f"{session}.lock").touch()
    monkeypatch.setattr(
        media, "process", lambda *args: pytest.fail("duplicate transmission")
    )
    with pytest.raises(ValueError, match="already running"):
        media.run(session, str(tmp_path / "cookie"))


def test_narration_cannot_skip_existing_approval(media, tmp_path):
    with pytest.raises((OSError, ValueError)):
        media.open("narration", str(tmp_path))
    assert not media.state_root.exists()


def test_ui_resources_are_local_and_expose_confirmation_only_to_app(media):
    tools = {
        tool["name"]: tool for tool in media.dispatch({"method": "tools/list"})["tools"]
    }
    resource = media.dispatch(
        {"method": "resources/read", "params": {"uri": "ui://clara/media-v1.html"}}
    )["contents"][0]
    assert tools["clara_media_confirm"]["_meta"]["ui"]["visibility"] == ["app"]
    assert tools["clara_media_save"]["_meta"]["ui"]["visibility"] == ["app"]
    assert resource["_meta"]["ui"]["csp"]["connectDomains"] == []
    assert "__FONT__" not in resource["text"]


@pytest.mark.parametrize(
    "method,key",
    [
        ("resources/list", "resources"),
        ("resources/templates/list", "resourceTemplates"),
        ("prompts/list", "prompts"),
    ],
)
def test_discovery_supports_native_host_lists(media, method, key):
    assert key in media.dispatch({"method": method})


def test_unknown_session_cannot_select_a_private_file(media):
    with pytest.raises(ValueError, match="Unknown"):
        media.status("../../private-file")


def test_changed_completed_output_is_not_claimed_as_delivered(
    media, tmp_path, monkeypatch
):
    session, _ = selected(media, tmp_path)
    media.confirm(session)
    cookie = tmp_path / "cookie"
    cookie.write_text("session=fictional")
    output = tmp_path / "result.json"
    output.write_text("{}")
    monkeypatch.setattr(media, "process", lambda *args: output)
    media.run(session, str(cookie))
    output.write_text('{"changed":true}')
    with pytest.raises(ValueError, match="output changed"):
        media.run(session, str(cookie))


def test_audio_processor_never_uploads_screen_video_or_case_context(
    media, tmp_path, monkeypatch
):
    from types import SimpleNamespace

    recording = tmp_path / "screen.webm"
    recording.write_bytes(b"private screen")
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio only")
    bundle = tmp_path / "bundle.json"
    bundle.write_text("{}")
    calls = []

    def upload(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(bundle_path=bundle)

    monkeypatch.setitem(
        sys.modules,
        "upload_hosted_audio",
        SimpleNamespace(
            _new_opener=None, bind_session_cookie=None, upload_hosted_audio=upload
        ),
    )
    imported = []
    monkeypatch.setitem(
        sys.modules,
        "import_hosted_voice_bundle_to_folder",
        SimpleNamespace(
            import_hosted_voice_bundle_to_folder=lambda folder, path: imported.append(
                (folder, path)
            )
        ),
    )
    output = media.process(
        {
            "work_dir": str(tmp_path),
            "session": "a" * 32,
            "operation": "deck_feedback",
            "source": str(recording),
            "audio_source": str(audio),
            "language": "en",
        },
        "session=fictional",
    )
    assert calls[0]["audio_path"] == audio
    assert calls[0]["include_case_context"] is False
    assert imported == [(tmp_path, bundle)]
    assert output == bundle


def test_audio_extraction_removes_video_tracks(media, tmp_path):
    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg and ffprobe integration capability unavailable")
    source = tmp_path / "screen.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=32x32:d=0.1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.1",
            "-shortest",
            str(source),
        ],
        check=True,
    )
    output = type(media).prepare_audio(
        {"source": str(source), "work_dir": str(tmp_path), "session": "b" * 32}
    )
    probe = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "json",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(probe.stdout)["streams"] == [{"codec_type": "audio"}]


def test_archive_direct_handoff_is_localized_and_cannot_repeat():
    import subprocess

    result = subprocess.run(
        [
            "node",
            str(ROOT / "tests/plugins/clara_archive_ui.cjs"),
            str(ROOT / "plugins/clara/assets/studio-archive.html"),
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr


def test_protocol_dispatch_calls_saved_session_without_media_bytes(media, tmp_path):
    session, _ = selected(media, tmp_path)
    reply = media.dispatch(
        {
            "method": "tools/call",
            "params": {"name": "clara_media_status", "arguments": {"session": session}},
        }
    )
    assert reply["structuredContent"]["status"] == "ready"
    assert media.dispatch({"method": "ping"}) == {}
    assert (
        media.dispatch(
            {"method": "initialize", "params": {"protocolVersion": "2024-11-05"}}
        )["serverInfo"]["name"]
        == "clara-media"
    )


def test_protocol_rejects_extra_parameters_before_processing(media):
    from jsonschema import ValidationError

    with pytest.raises(ValidationError):
        media.dispatch(
            {
                "method": "tools/call",
                "params": {
                    "name": "clara_media_open",
                    "arguments": {
                        "operation": "transcribe",
                        "work_dir": "/tmp",
                        "secret": "do not leak",
                    },
                },
            }
        )
    with pytest.raises(ValueError, match="Unknown"):
        media.dispatch({"method": "tools/call", "params": {"name": "invented"}})


@pytest.mark.parametrize(
    "arguments",
    [
        ["tests/plugins/clara_media_ui.cjs"],
        [
            "tests/plugins/course_chat_ui.cjs",
            "plugins/clara/vendor/modules/courseware/assets/chat.js",
        ],
    ],
)
def test_native_controls_prevent_duplicate_handoffs_and_handle_missing_capability(
    arguments,
):
    import subprocess

    result = subprocess.run(
        ["node", *arguments], cwd=ROOT, capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
