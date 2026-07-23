from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

from scripts import build_vera_youtube_video_guides as renderer
from scripts.build_vera_youtube_video_guides import partition_narration_scenes


def _valid_manifest_entry(
    *,
    output_root: Path,
    module: str,
    edition: str,
    language: str,
) -> dict[str, Any]:
    output_dir = output_root / module / edition / language
    output_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict[str, object]] = {}
    for key, filename, mime_type in (
        ("video", "guide.mp4", "video/mp4"),
        ("poster", "poster.jpg", "image/jpeg"),
        ("captions", "captions.vtt", "text/vtt"),
    ):
        path = output_dir / filename
        path.write_bytes(f"{module}/{edition}/{language}/{filename}".encode())
        files[key] = renderer._artifact_record(path, mime_type)
    return {
        "module": module,
        "edition": edition,
        "language": language,
        "status": "youtube_ready",
        "voice": {
            "name": renderer.video_voice_for_language(language),
            "model": renderer.OPENAI_VIDEO_TTS_MODEL,
        },
        "files": files,
    }


def test_load_openai_api_key_accepts_established_secrets_format(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    secret_file = tmp_path / "secrets.local.toml"
    expected_key = "sk-test-established-secret-value"
    secret_file.write_text(
        f"unrelated = value\nopenAiKey = {expected_key}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MPARANZA_SECRETS_FILE", str(secret_file))

    assert renderer._load_openai_api_key() == expected_key


def test_partition_narration_scenes_preserves_complete_sentences() -> None:
    narration = "One. Two. Three. Four. Five. Six."

    scenes = partition_narration_scenes(narration, 6)

    assert scenes == ["One.", "Two.", "Three.", "Four.", "Five.", "Six."]


def test_captions_use_natural_pause_time_without_exceeding_reading_rate(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "captions.vtt"
    narration_parts = [f"{'a' * 60}.", f"{'b' * 60}."]

    cue_count = renderer._write_captions(
        output_path,
        narration_parts,
        [4.8, 4.8],
        0.9,
    )

    assert cue_count == 2
    captions = output_path.read_text(encoding="utf-8")
    assert captions.startswith("WEBVTT\n")
    assert "00:00:00.800 --> 00:00:04.350" in captions
    assert "00:00:05.250 --> 00:00:08.800" in captions
    assert "00:00:04.350 --> 00:00:05.250" not in captions


def test_matching_asset_checkpoint_is_reused_and_changed_input_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "rendered"
    monkeypatch.setattr(renderer, "OUTPUT_ROOT", output_root)
    concept = {
        "conceptId": "example",
        "module": "new-client",
        "edition": "core",
        "scope": "core",
        "jurisdiction": None,
        "targetDurationSeconds": 10,
        "scenes": ["one", "two"],
        "pageTargets": ["/example"],
    }
    localization = {"title": "Example", "narration": "One. Two."}
    fingerprint = renderer._build_input_sha256(
        concept=concept,
        language="en",
        localization=localization,
        frame_template="/*__FRAME_DATA__*/",
    )
    output_dir = output_root / "new-client" / "core" / "en"
    output_dir.mkdir(parents=True)
    files: dict[str, dict[str, object]] = {}
    for name, mime_type in (
        ("guide.mp4", "video/mp4"),
        ("poster.jpg", "image/jpeg"),
        ("captions.vtt", "text/vtt"),
    ):
        path = output_dir / name
        path.write_bytes(name.encode("utf-8"))
        key = {"guide.mp4": "video", "poster.jpg": "poster"}.get(name, "captions")
        files[key] = renderer._artifact_record(path, mime_type)
    entry = {
        "module": "new-client",
        "edition": "core",
        "language": "en",
        "status": "youtube_ready",
        "buildInputSha256": fingerprint,
        "voice": {
            "name": "cedar",
            "model": renderer.OPENAI_VIDEO_TTS_MODEL,
        },
        "files": files,
    }
    renderer._write_checkpoint(entry)

    reused = renderer._load_valid_checkpoint(
        concept=concept,
        language="en",
        build_input_sha256=fingerprint,
    )
    stale = renderer._load_valid_checkpoint(
        concept=concept,
        language="en",
        build_input_sha256="different",
    )

    assert reused == entry
    assert stale is None


@pytest.mark.parametrize(
    "narration",
    (
        "One. Two. Three. Four. Five.",
        "One. Two. Three. Four. Five. Six",
    ),
)
def test_partition_narration_scenes_without_six_complete_sentences_raises(
    narration: str,
) -> None:
    with pytest.raises(ValueError, match="complete sentence|terminal punctuation"):
        partition_narration_scenes(narration, 6)


def test_language_filter_preserves_existing_manifest_entries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "rendered"
    manifest_path = output_root / "manifest.json"
    frame_template_path = tmp_path / "guide-frame.html"
    output_root.mkdir()
    frame_template_path.write_text("/*__FRAME_DATA__*/", encoding="utf-8")
    monkeypatch.setattr(renderer, "OUTPUT_ROOT", output_root)
    existing_identities = {
        identity for identity in renderer.EXPECTED_LOCALIZATIONS if identity[2] != "es"
    }
    existing_assets = [
        _valid_manifest_entry(
            output_root=output_root,
            module=module,
            edition=edition,
            language=language,
        )
        for module, edition, language in sorted(existing_identities)
    ]
    manifest_path.write_text(
        json.dumps({"assets": existing_assets}),
        encoding="utf-8",
    )
    rendered_identities: list[tuple[str, str, str]] = []

    class FakePage:
        def on(self, _event: str, _callback: object) -> None:
            return None

    class FakeBrowser:
        def new_page(self, **_kwargs: object) -> FakePage:
            return FakePage()

        def close(self) -> None:
            return None

    class FakeChromium:
        def launch(self, *, headless: bool) -> FakeBrowser:
            assert headless is True
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

        def __enter__(self) -> FakePlaywright:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def fake_build_one_guide(
        *,
        concept: dict[str, object],
        language: str,
        **_kwargs: object,
    ) -> dict[str, object]:
        identity = (str(concept["module"]), str(concept["edition"]), language)
        rendered_identities.append(identity)
        return _valid_manifest_entry(
            output_root=output_root,
            module=identity[0],
            edition=identity[1],
            language=identity[2],
        )

    monkeypatch.setattr(renderer, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(renderer, "FRAME_TEMPLATE_PATH", frame_template_path)
    monkeypatch.setattr(renderer, "_load_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(renderer, "_required_tool", lambda *_args: "tool")
    monkeypatch.setattr(renderer, "sync_playwright", lambda: FakePlaywright())
    monkeypatch.setattr(renderer, "_build_one_guide", fake_build_one_guide)

    result_path = renderer.build_vera_youtube_video_guides(languages={"es"})

    result = json.loads(result_path.read_text(encoding="utf-8"))
    expected_spanish = {
        identity for identity in renderer.EXPECTED_LOCALIZATIONS if identity[2] == "es"
    }
    assert set(rendered_identities) == expected_spanish
    assert result["assetCount"] == len(renderer.EXPECTED_LOCALIZATIONS)
    result_by_identity = {
        (asset["module"], asset["edition"], asset["language"]): asset
        for asset in result["assets"]
    }
    for existing_asset in existing_assets:
        identity = (
            existing_asset["module"],
            existing_asset["edition"],
            existing_asset["language"],
        )
        assert result_by_identity[identity] == existing_asset


@pytest.mark.parametrize(
    ("mutation", "error_match"),
    (
        (lambda entry: entry.update(status="local_rendered"), "status is invalid"),
        (
            lambda entry: entry["voice"].update(name="alloy"),
            "voice is invalid",
        ),
        (
            lambda entry: entry["voice"].update(model="legacy-tts"),
            "voice is invalid",
        ),
        (
            lambda entry: entry["files"].update(transcript=entry["files"]["captions"]),
            "transcript schema",
        ),
        (
            lambda entry: entry["files"]["captions"].update(extra="schema-leak"),
            "captions schema is invalid",
        ),
    ),
)
def test_final_manifest_entry_rejects_wrong_voice_or_leaky_schema(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], None],
    error_match: str,
) -> None:
    output_root = tmp_path / "rendered"
    monkeypatch.setattr(renderer, "OUTPUT_ROOT", output_root)
    identity = ("new-client", "core", "en")
    entry = _valid_manifest_entry(
        output_root=output_root,
        module=identity[0],
        edition=identity[1],
        language=identity[2],
    )
    invalid_entry = copy.deepcopy(entry)
    mutation(invalid_entry)

    with pytest.raises(ValueError, match=error_match):
        renderer._validate_youtube_ready_manifest_entry(
            invalid_entry,
            expected_identity=identity,
        )


def test_main_forwards_repeated_language_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_languages: set[str] | None = None

    def fake_build(
        _modules: set[str] | None,
        _editions: set[str] | None,
        *,
        languages: set[str] | None,
        captions_only: bool,
    ) -> Path:
        nonlocal captured_languages
        captured_languages = languages
        assert captions_only is False
        return Path("manifest.json")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_vera_youtube_video_guides.py",
            "--language",
            "es",
            "--language",
            "fr",
        ],
    )
    monkeypatch.setattr(renderer, "build_vera_youtube_video_guides", fake_build)

    assert renderer.main() == 0
    assert captured_languages == {"es", "fr"}


def test_unknown_language_filter_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown Vera guide languages"):
        renderer.build_vera_youtube_video_guides(languages={"xx"})


def test_unsupported_language_is_rejected_before_api_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_if_requested(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Unsupported languages must fail before an API request")

    monkeypatch.setattr(renderer.urllib.request, "urlopen", fail_if_requested)

    with pytest.raises(ValueError, match="Unsupported video language"):
        renderer._request_openai_speech(
            api_key="test-key",
            language="xx",
            text="Test narration.",
            output_path=tmp_path / "speech.wav",
        )
