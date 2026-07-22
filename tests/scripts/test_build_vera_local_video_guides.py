from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts import build_vera_local_video_guides as renderer
from scripts.build_vera_local_video_guides import partition_narration_scenes


def test_partition_narration_scenes_preserves_complete_sentences() -> None:
    narration = "One. Two. Three. Four. Five. Six."

    scenes = partition_narration_scenes(narration, 6)

    assert scenes == ["One.", "Two.", "Three.", "Four.", "Five.", "Six."]


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
    existing_identities = {
        identity for identity in renderer.EXPECTED_LOCALIZATIONS if identity[2] != "es"
    }
    existing_assets = [
        {
            "module": module,
            "edition": edition,
            "language": language,
            "preserved": f"{module}/{edition}/{language}",
        }
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
        return {
            "module": identity[0],
            "edition": identity[1],
            "language": identity[2],
            "rendered": True,
        }

    monkeypatch.setattr(renderer, "OUTPUT_ROOT", output_root)
    monkeypatch.setattr(renderer, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(renderer, "FRAME_TEMPLATE_PATH", frame_template_path)
    monkeypatch.setattr(renderer, "_required_tool", lambda *_args: "tool")
    monkeypatch.setattr(renderer, "sync_playwright", lambda: FakePlaywright())
    monkeypatch.setattr(renderer, "_build_one_guide", fake_build_one_guide)

    result_path = renderer.build_vera_local_video_guides(languages={"es"})

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
        ["build_vera_local_video_guides.py", "--language", "es", "--language", "fr"],
    )
    monkeypatch.setattr(renderer, "build_vera_local_video_guides", fake_build)

    assert renderer.main() == 0
    assert captured_languages == {"es", "fr"}


def test_unknown_language_filter_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown Vera guide languages"):
        renderer.build_vera_local_video_guides(languages={"xx"})
