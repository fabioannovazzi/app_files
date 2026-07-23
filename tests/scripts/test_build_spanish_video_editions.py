from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import pytest

from scripts import build_spanish_video_editions as builder


def test_default_source_root_is_derived_from_repository_root() -> None:
    assert builder.REPO_VIDEO_PILOT_SOURCE_ROOT == (
        builder.REPO_ROOT / "outputs" / "video-pilots"
    )
    assert "/Users/fabio/" not in str(builder.REPO_VIDEO_PILOT_SOURCE_ROOT)
    expected_default = Path(
        os.environ.get(
            "MPARANZA_VIDEO_PILOT_SOURCE_ROOT",
            str(builder.REPO_VIDEO_PILOT_SOURCE_ROOT),
        )
    )
    assert builder.DEFAULT_SOURCE_ROOT == expected_default


def test_load_openai_api_key_accepts_established_secrets_format(
    tmp_path: Path,
) -> None:
    secret_file = tmp_path / "secrets.local.toml"
    expected_key = "sk-test-established-secret-value"
    secret_file.write_text(
        f"unrelated = value\nopenAiKey = {expected_key}\n",
        encoding="utf-8",
    )

    assert builder._load_openai_api_key(secret_file) == expected_key


def _asset(source_key: str) -> builder.SourceAsset:
    return builder.SourceAsset(
        source_key=source_key,
        target_key=builder._target_key(source_key),
        product=source_key.split("-", 1)[0],
        base_scene_id=source_key[:-3],
        narration=f"Source narration for {source_key}.",
        instructions="Speak naturally in English.",
        title=f"Source title for {source_key}",
        scene_weights=(1.0, 1.0, 1.0, 1.0, 1.0, 1.0),
    )


def _inventory(source_key: str) -> builder.SceneTextInventory:
    return builder.SceneTextInventory(
        text_sources=(f"Heading {source_key}", f"Body {source_key}"),
        generated_sources={"FIT TO QUESTION": ".analysis-option.selected"},
    )


def _raw_translation(
    asset: builder.SourceAsset,
    inventory: builder.SceneTextInventory,
) -> dict[str, Any]:
    return {
        "sourceKey": asset.source_key,
        "targetKey": asset.target_key,
        "narration": f"Narración en español para {asset.target_key}.",
        "instructions": "Habla en español natural, con calma y claridad.",
        "title": f"Título en español para {asset.target_key}",
        "onScreenReplacements": [
            {"source": source, "spanish": f"ES · {source}"}
            for source in inventory.all_sources
        ],
    }


def _all_assets_and_inventories() -> tuple[
    tuple[builder.SourceAsset, ...],
    dict[str, builder.SceneTextInventory],
]:
    assets = tuple(_asset(key) for key in builder.SPANISH_SOURCE_KEYS)
    inventories = {asset.source_key: _inventory(asset.source_key) for asset in assets}
    return assets, inventories


def test_spanish_source_keys_are_the_exact_24_english_fallbacks() -> None:
    assert builder.SPANISH_SOURCE_KEYS == (
        "clara-advisory-document-en",
        "clara-attribute-reporting-en",
        "clara-beautify-deck-en",
        "clara-brand-fit-en",
        "clara-claim-basis-en",
        "clara-deck-correction-en",
        "clara-en",
        "clara-html-deck-en",
        "clara-interview-en",
        "clara-reporting-en",
        "clara-retailer-signals-en",
        "clara-transcribe-en",
        "vera-avviso-intake-en",
        "vera-concordato-en",
        "vera-dati-fiscali-en",
        "vera-deep-research-validator-en",
        "vera-email-cliente-en",
        "vera-general-en",
        "vera-journal-bank-en",
        "vera-open-items-en",
        "vera-previdenza-en",
        "vera-prompt-optimizer-en",
        "vera-registro-sari-en",
        "vera-report-builder-en",
    )
    assert builder.EXCLUDED_SPANISH_SOURCE_KEYS == {"vera-client-intake-en"}
    assert len(builder.SPANISH_SOURCE_KEYS) == 24
    assert "vera-client-intake-en" not in builder.SPANISH_SOURCE_KEYS


def test_source_coverage_requires_the_24_plus_explicit_exclusion() -> None:
    expected = set(builder.SPANISH_SOURCE_KEYS) | set(
        builder.EXCLUDED_SPANISH_SOURCE_KEYS
    )
    mapping = {key: {} for key in expected}

    builder._validate_source_key_coverage(mapping, mapping, mapping)

    incomplete = dict(mapping)
    incomplete.pop("clara-en")
    with pytest.raises(ValueError, match="missing=.*clara-en"):
        builder._validate_source_key_coverage(incomplete, mapping, mapping)


def test_load_source_catalog_uses_configurable_established_source_root(
    tmp_path: Path,
) -> None:
    english_keys = set(builder.SPANISH_SOURCE_KEYS) | set(
        builder.EXCLUDED_SPANISH_SOURCE_KEYS
    )
    narrations = {
        key: {
            "voice": "legacy-value-is-ignored",
            "input": f"Narration for {key}.",
            "instructions": "Source delivery instructions.",
        }
        for key in english_keys
    }
    videos = {
        key: {
            "scenes": [f"{key}-{index}.png" for index in range(6)],
            "weights": [1, 1, 1, 1, 1, 1],
            "title": f"Title for {key}",
        }
        for key in english_keys
    }
    scene_sets = {
        key: {
            "base": key[:-3],
            "output": key,
            "translations": {},
        }
        for key in english_keys
    }
    (tmp_path / "generate_narration.py").write_text(
        f"NARRATIONS = {narrations!r}\n",
        encoding="utf-8",
    )
    (tmp_path / "render_videos.py").write_text(
        f"VIDEOS = {videos!r}\n",
        encoding="utf-8",
    )
    (tmp_path / "render_scenes.py").write_text(
        f"SCENE_SETS = {scene_sets!r}\n",
        encoding="utf-8",
    )
    (tmp_path / "scene_localizations.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "scenes.html").write_text("<html></html>\n", encoding="utf-8")

    assets = builder.load_source_catalog(tmp_path)

    assert tuple(asset.source_key for asset in assets) == builder.SPANISH_SOURCE_KEYS
    assert all(asset.target_key.endswith("-es") for asset in assets)
    assert all(asset.scene_weights == (1.0,) * 6 for asset in assets)


def test_validate_translation_item_requires_complete_on_screen_map() -> None:
    asset = _asset("clara-en")
    inventory = _inventory(asset.source_key)

    normalized = builder.validate_translation_item(
        asset,
        inventory,
        _raw_translation(asset, inventory),
    )

    assert tuple(normalized["onScreen"]) == inventory.all_sources
    assert normalized["generatedTextSources"] == ["FIT TO QUESTION"]

    incomplete = _raw_translation(asset, inventory)
    incomplete["onScreenReplacements"].pop()
    with pytest.raises(ValueError, match="Incomplete on-screen map"):
        builder.validate_translation_item(asset, inventory, incomplete)


def test_translation_bundle_caches_each_validated_asset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    assets, inventories = _all_assets_and_inventories()
    requests: list[str] = []

    def fake_request(
        asset: builder.SourceAsset,
        inventory: builder.SceneTextInventory,
        _api_key: str,
        model: str,
    ) -> dict[str, Any]:
        assert model == "gpt-5.4-mini"
        requests.append(asset.source_key)
        return _raw_translation(asset, inventory)

    cache_path = tmp_path / "translation-bundle.json"
    first = builder.build_translation_bundle(
        assets=assets,
        inventories=inventories,
        api_key="test-key",
        cache_path=cache_path,
        request_translation=fake_request,
    )

    assert len(requests) == 24
    assert first["complete"] is True
    assert first["assetCount"] == 24

    requests.clear()

    def fail_if_requested(
        _asset_value: builder.SourceAsset,
        _inventory_value: builder.SceneTextInventory,
        _api_key: str,
        _model: str,
    ) -> dict[str, Any]:
        pytest.fail("Fingerprint-matched translations must be reused")

    second = builder.build_translation_bundle(
        assets=assets,
        inventories=inventories,
        api_key="test-key",
        cache_path=cache_path,
        request_translation=fail_if_requested,
    )

    assert requests == []
    assert second["complete"] is True
    assert set(second["items"]) == {asset.target_key for asset in assets}


def test_translation_checkpoint_preserves_valid_future_items_after_interruption(
    tmp_path: Path,
) -> None:
    assets, inventories = _all_assets_and_inventories()
    cache_path = tmp_path / "translation-bundle.json"

    def initial_request(
        asset: builder.SourceAsset,
        inventory: builder.SceneTextInventory,
        _api_key: str,
        _model: str,
    ) -> dict[str, Any]:
        return _raw_translation(asset, inventory)

    builder.build_translation_bundle(
        assets=assets,
        inventories=inventories,
        api_key="test-key",
        cache_path=cache_path,
        request_translation=initial_request,
    )
    cached = json.loads(cache_path.read_text(encoding="utf-8"))
    first_target = assets[0].target_key
    second_target = assets[1].target_key
    final_target = assets[-1].target_key
    cached["items"][first_target]["sourceFingerprint"] = "stale"
    cached["items"][second_target]["sourceFingerprint"] = "stale"
    cache_path.write_text(json.dumps(cached), encoding="utf-8")
    refreshed: list[str] = []

    def interrupted_request(
        asset: builder.SourceAsset,
        inventory: builder.SceneTextInventory,
        _api_key: str,
        _model: str,
    ) -> dict[str, Any]:
        refreshed.append(asset.target_key)
        if len(refreshed) == 2:
            raise RuntimeError("simulated interruption")
        return _raw_translation(asset, inventory)

    with pytest.raises(RuntimeError, match="simulated interruption"):
        builder.build_translation_bundle(
            assets=assets,
            inventories=inventories,
            api_key="test-key",
            cache_path=cache_path,
            request_translation=interrupted_request,
        )

    checkpoint = json.loads(cache_path.read_text(encoding="utf-8"))
    assert refreshed == [first_target, second_target]
    assert first_target in checkpoint["items"]
    assert final_target in checkpoint["items"]


def test_translation_request_uses_gpt54_mini_responses_json_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = _asset("clara-en")
    inventory = _inventory(asset.source_key)
    translation = _raw_translation(asset, inventory)
    captured: dict[str, Any] = {}

    def fake_request_bytes(
        request: object,
        *,
        operation: str,
        timeout_seconds: int = builder.REQUEST_TIMEOUT_SECONDS,
    ) -> bytes:
        captured["request"] = request
        captured["operation"] = operation
        captured["timeout"] = timeout_seconds
        response = {
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(translation, ensure_ascii=False),
                        }
                    ]
                }
            ]
        }
        return json.dumps(response).encode("utf-8")

    monkeypatch.setattr(builder, "_request_bytes", fake_request_bytes)

    result = builder._request_translation(
        asset,
        inventory,
        "test-key",
        "gpt-5.4-mini",
    )

    request = captured["request"]
    payload = json.loads(request.data.decode("utf-8"))
    assert request.full_url == builder.OPENAI_RESPONSES_ENDPOINT
    assert payload["model"] == "gpt-5.4-mini"
    assert payload["text"]["format"]["type"] == "json_schema"
    assert payload["text"]["format"]["strict"] is True
    assert payload["text"]["format"]["schema"]["properties"]["onScreenReplacements"][
        "minItems"
    ] == len(inventory.all_sources)
    assert result == translation


def test_spanish_tts_payload_uses_cedar_from_central_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}
    translation = {
        "targetKey": "clara-es",
        "narration": "Narración de prueba.",
        "instructions": "Habla con naturalidad.",
    }

    def fake_request_bytes(
        request: object,
        *,
        operation: str,
        timeout_seconds: int = builder.REQUEST_TIMEOUT_SECONDS,
    ) -> bytes:
        captured["request"] = request
        captured["operation"] = operation
        captured["timeout"] = timeout_seconds
        return b"RIFF-test"

    monkeypatch.setattr(builder, "_request_bytes", fake_request_bytes)
    output_path = tmp_path / "narration.wav"

    builder._synthesize_narration(
        api_key="test-key",
        translation=translation,
        output_path=output_path,
    )

    request = captured["request"]
    payload = json.loads(request.data.decode("utf-8"))
    assert payload["model"] == builder.OPENAI_VIDEO_TTS_MODEL
    assert payload["voice"] == "cedar"
    assert output_path.read_bytes() == b"RIFF-test"


def test_upload_description_derives_voice_label_from_central_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = _asset("clara-en")
    translation = _raw_translation(asset, _inventory(asset.source_key))
    requested_languages: list[str] = []

    def fake_voice_policy(language: str) -> str:
        requested_languages.append(language)
        return "marin"

    monkeypatch.setattr(builder, "video_voice_for_language", fake_voice_policy)

    description = builder._upload_description(asset, translation)

    assert requested_languages == ["es"]
    assert "usando la voz Marin." in description
    assert "Cedar" not in description


def test_request_bytes_retries_429_and_5xx_without_leaking_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    delays: list[float] = []
    secret = "secret-key-value"
    request = builder.urllib.request.Request(
        builder.OPENAI_RESPONSES_ENDPOINT,
        data=b'{"private":"source material"}',
        headers={"Authorization": f"Bearer {secret}"},
    )

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"recovered"

    def flaky_urlopen(_request: object, *, timeout: int) -> FakeResponse:
        nonlocal attempts
        attempts += 1
        assert timeout == builder.REQUEST_TIMEOUT_SECONDS
        if attempts < 3:
            raise HTTPError(
                builder.OPENAI_RESPONSES_ENDPOINT,
                429 if attempts == 1 else 503,
                "transient",
                hdrs=None,
                fp=None,
            )
        return FakeResponse()

    monkeypatch.setattr(builder.urllib.request, "urlopen", flaky_urlopen)
    monkeypatch.setattr(builder.time, "sleep", delays.append)

    result = builder._request_bytes(request, operation="test translation")

    assert result == b"recovered"
    assert attempts == 3
    assert delays == [1.0, 2.0]
    assert secret not in repr(result)


def test_write_captions_creates_vtt_without_transcript_file(tmp_path: Path) -> None:
    captions_path = tmp_path / "captions.vtt"

    cue_count = builder._write_captions(
        captions_path,
        "Primera frase. Segunda frase con más detalle.",
        8.0,
    )

    assert cue_count == 2
    assert captions_path.read_text(encoding="utf-8").startswith("WEBVTT\n")
    assert not list(tmp_path.glob("*transcript*"))


def test_matching_render_checkpoint_is_reused_and_changed_input_is_rejected(
    tmp_path: Path,
) -> None:
    asset = _asset("clara-en")
    translation = _raw_translation(asset, _inventory(asset.source_key))
    fingerprint = builder._render_fingerprint(asset, translation)
    asset_dir = tmp_path / "assets" / asset.target_key
    asset_dir.mkdir(parents=True)
    files: dict[str, dict[str, object]] = {}
    for key, filename, mime_type in (
        ("video", "guide.mp4", "video/mp4"),
        ("thumbnail", "thumbnail.png", "image/png"),
        ("captions", "captions.vtt", "text/vtt"),
    ):
        path = asset_dir / filename
        path.write_bytes(filename.encode("utf-8"))
        files[key] = builder._artifact_record(path, tmp_path, mime_type)
    entry = {
        "sourceKey": asset.source_key,
        "key": asset.target_key,
        "language": "es",
        "privacyStatus": "unlisted",
        "renderFingerprint": fingerprint,
        "voice": {
            "name": "cedar",
            "model": builder.OPENAI_VIDEO_TTS_MODEL,
        },
        "files": files,
    }
    builder._write_json_atomic(asset_dir / "asset.json", entry)

    reused = builder._load_valid_render_checkpoint(
        output_root=tmp_path,
        asset=asset,
        render_fingerprint=fingerprint,
    )
    stale = builder._load_valid_render_checkpoint(
        output_root=tmp_path,
        asset=asset,
        render_fingerprint="different",
    )

    assert reused == entry
    assert stale is None


def test_youtube_manifest_is_unlisted_complete_and_has_no_transcript_surface(
    tmp_path: Path,
) -> None:
    entries = [
        {
            "sourceKey": source_key,
            "key": builder._target_key(source_key),
            "language": "es",
            "privacyStatus": "unlisted",
        }
        for source_key in builder.SPANISH_SOURCE_KEYS
    ]

    manifest_path = builder._write_upload_manifest(
        output_root=tmp_path,
        entries=entries,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    serialized = json.dumps(manifest).lower()
    assert manifest["publicationTarget"] == "youtube"
    assert manifest["privacyStatus"] == "unlisted"
    assert manifest["assetCount"] == 24
    assert manifest["voicePolicy"]["name"] == "cedar"
    assert "transcript" not in serialized
