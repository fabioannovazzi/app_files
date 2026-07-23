"""Build the missing Spanish editions of the established Clara and Vera videos."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import runpy
import shutil

# Fixed local media tools are invoked with argument lists and without a shell.
import subprocess  # nosec B404
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from playwright.sync_api import Browser, Page, sync_playwright

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.utilities import config as utilities_config
from scripts.video_voice_policy import (
    OPENAI_VIDEO_TTS_MODEL,
    video_voice_for_language,
)

__all__ = [
    "EXCLUDED_SPANISH_SOURCE_KEYS",
    "SPANISH_SOURCE_KEYS",
    "SceneTextInventory",
    "SourceAsset",
    "build_spanish_video_editions",
    "load_source_catalog",
    "main",
    "validate_translation_item",
]

LOGGER = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_VIDEO_PILOT_SOURCE_ROOT = REPO_ROOT / "outputs" / "video-pilots"
DEFAULT_SOURCE_ROOT = Path(
    os.environ.get(
        "MPARANZA_VIDEO_PILOT_SOURCE_ROOT",
        str(REPO_VIDEO_PILOT_SOURCE_ROOT),
    )
)
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "outputs" / "spanish-video-editions"
DEFAULT_SECRET_FILE = Path(
    os.environ.get(
        "MPARANZA_SECRETS_FILE",
        str(REPO_ROOT / ".secrets" / "secrets.local.toml"),
    )
)

OPENAI_RESPONSES_ENDPOINT = "https://api.openai.com/v1/responses"
OPENAI_SPEECH_ENDPOINT = "https://api.openai.com/v1/audio/speech"
TARGET_LANGUAGE = "es"
TRANSLATION_PROMPT_VERSION = "spanish-video-editions-v1"
TRANSLATION_CACHE_SCHEMA_VERSION = "1.0.0"
UPLOAD_MANIFEST_SCHEMA_VERSION = "1.0.0"
MAX_REQUEST_ATTEMPTS = 4
RETRY_BASE_SECONDS = 1.0
RETRY_MAX_SECONDS = 8.0
REQUEST_TIMEOUT_SECONDS = 300

FRAME_WIDTH = 1920
FRAME_HEIGHT = 1080
FRAME_RATE = 30
SCENE_COUNT = 6
TRANSITION_SECONDS = 0.65
LEAD_SILENCE_SECONDS = 0.75
TAIL_SILENCE_SECONDS = 1.25
CAPTION_MAX_CHARACTERS = 84

EXCLUDED_SPANISH_SOURCE_KEYS = frozenset({"vera-client-intake-en"})
SPANISH_SOURCE_KEYS = (
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

# These labels are rendered with CSS pseudo-elements, so the DOM text walker
# cannot discover or replace them. The selector is stored without ``::after``.
GENERATED_TEXT_SELECTORS = {
    "CAMPIONE": ".journal-row.selected",
    "USEFUL THREAD": ".thread-question.useful",
    "FIT TO QUESTION": ".analysis-option.selected",
}


@dataclass(frozen=True)
class SourceAsset:
    """One established English master that needs a Spanish edition."""

    source_key: str
    target_key: str
    product: str
    base_scene_id: str
    narration: str
    instructions: str
    title: str
    scene_weights: tuple[float, ...]


@dataclass(frozen=True)
class SceneTextInventory:
    """Exact replaceable text discovered across one six-scene storyboard."""

    text_sources: tuple[str, ...]
    generated_sources: Mapping[str, str]

    @property
    def all_sources(self) -> tuple[str, ...]:
        """Return every DOM and CSS-generated source string once, in order."""

        return self.text_sources + tuple(self.generated_sources)


TranslationRequester = Callable[
    [SourceAsset, SceneTextInventory, str, str],
    dict[str, Any],
]


def _translation_model() -> str:
    """Return the centrally configured GPT-5.4 mini model identifier."""

    return utilities_config.get_naming_params()["gpt54Mini"]


def _target_key(source_key: str) -> str:
    """Return the Spanish key paired to an English source key."""

    if not source_key.endswith("-en"):
        raise ValueError(f"Spanish source key must end in '-en': {source_key!r}")
    return f"{source_key[:-3]}-es"


def _load_mapping_from_python(path: Path, variable_name: str) -> dict[str, Any]:
    """Load one established top-level mapping without invoking its CLI."""

    if not path.is_file():
        raise FileNotFoundError(f"Required pilot source is missing: {path}")
    namespace = runpy.run_path(
        str(path),
        run_name=f"_mparanza_{path.stem}_source",
    )
    value = namespace.get(variable_name)
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, dict) for key, item in value.items()
    ):
        raise ValueError(f"{path.name} does not define a valid {variable_name} mapping")
    return value


def _validate_source_key_coverage(
    narrations: Mapping[str, Any],
    videos: Mapping[str, Any],
    scene_sets: Mapping[str, Any],
) -> None:
    """Require the exact 25 established English masters and selected 24."""

    expected_english_keys = set(SPANISH_SOURCE_KEYS) | set(EXCLUDED_SPANISH_SOURCE_KEYS)
    if len(SPANISH_SOURCE_KEYS) != 24 or len(set(SPANISH_SOURCE_KEYS)) != 24:
        raise ValueError("The Spanish edition source list must contain 24 unique keys")
    if set(SPANISH_SOURCE_KEYS) & set(EXCLUDED_SPANISH_SOURCE_KEYS):
        raise ValueError(
            "Excluded source keys cannot appear in the Spanish source list"
        )

    for label, mapping in (
        ("narrations", narrations),
        ("videos", videos),
        ("scene sets", scene_sets),
    ):
        english_keys = {key for key in mapping if key.endswith("-en")}
        if english_keys != expected_english_keys:
            missing = sorted(expected_english_keys - english_keys)
            unexpected = sorted(english_keys - expected_english_keys)
            raise ValueError(
                f"Unexpected English {label} coverage; "
                f"missing={missing!r}, unexpected={unexpected!r}"
            )


def load_source_catalog(source_root: Path) -> tuple[SourceAsset, ...]:
    """Load and validate the exact 24 source masters from the pilot workspace."""

    source_root = source_root.resolve()
    narrations = _load_mapping_from_python(
        source_root / "generate_narration.py",
        "NARRATIONS",
    )
    videos = _load_mapping_from_python(
        source_root / "render_videos.py",
        "VIDEOS",
    )
    scene_sets = _load_mapping_from_python(
        source_root / "render_scenes.py",
        "SCENE_SETS",
    )
    for required_name in ("scene_localizations.json", "scenes.html"):
        required_path = source_root / required_name
        if not required_path.is_file():
            raise FileNotFoundError(
                f"Required pilot source is missing: {required_path}"
            )

    _validate_source_key_coverage(narrations, videos, scene_sets)
    assets: list[SourceAsset] = []
    for source_key in SPANISH_SOURCE_KEYS:
        narration = narrations[source_key]
        video = videos[source_key]
        scene_set = scene_sets[source_key]
        scene_names = video.get("scenes")
        weights = video.get("weights")
        if not isinstance(scene_names, list) or len(scene_names) != SCENE_COUNT:
            raise ValueError(f"{source_key} must define exactly six source scenes")
        if (
            not isinstance(weights, list)
            or len(weights) != SCENE_COUNT
            or any(
                not isinstance(value, (int, float)) or value <= 0 for value in weights
            )
        ):
            raise ValueError(f"{source_key} must define six positive scene weights")

        values = {
            "narration": narration.get("input"),
            "instructions": narration.get("instructions"),
            "title": video.get("title"),
            "base_scene_id": scene_set.get("base"),
        }
        if any(
            not isinstance(value, str) or not value.strip() for value in values.values()
        ):
            raise ValueError(
                f"{source_key} has incomplete source text or scene metadata"
            )
        assets.append(
            SourceAsset(
                source_key=source_key,
                target_key=_target_key(source_key),
                product=source_key.split("-", 1)[0],
                base_scene_id=str(values["base_scene_id"]).strip(),
                narration=str(values["narration"]).strip(),
                instructions=str(values["instructions"]).strip(),
                title=str(values["title"]).strip(),
                scene_weights=tuple(float(value) for value in weights),
            )
        )

    if len(assets) != 24 or {asset.source_key for asset in assets} != set(
        SPANISH_SOURCE_KEYS
    ):
        raise ValueError("The loaded Spanish source catalog is not complete")
    return tuple(assets)


def _prepare_storyboard_page(page: Page, source_root: Path) -> None:
    """Load the established storyboard and wait for fonts and images."""

    page.goto((source_root / "scenes.html").as_uri(), wait_until="load")
    page.wait_for_function(
        "Array.from(document.images).every((image) => image.complete)"
    )
    page.locator("body").evaluate("""
        root => Promise.all(
          Array.from(root.querySelectorAll("img"))
            .map(image => image.decode().catch(() => {}))
        )
        """)
    page.evaluate("document.fonts.ready")


def collect_scene_text_inventory(
    page: Page,
    source_root: Path,
    asset: SourceAsset,
) -> SceneTextInventory:
    """Discover every replaceable text node and generated label for one master."""

    _prepare_storyboard_page(page, source_root)
    scene_ids = [f"{asset.base_scene_id}-{index}" for index in range(SCENE_COUNT)]
    scene_texts = page.evaluate(
        """
        sceneIds => sceneIds.map(sceneId => {
          const scene = document.getElementById(sceneId);
          if (!scene) return null;
          const walker = document.createTreeWalker(scene, NodeFilter.SHOW_TEXT);
          const values = [];
          let node;
          while ((node = walker.nextNode())) {
            const value = node.nodeValue.trim();
            if (value) values.push(value);
          }
          return values;
        })
        """,
        scene_ids,
    )
    if (
        not isinstance(scene_texts, list)
        or len(scene_texts) != SCENE_COUNT
        or any(not isinstance(values, list) for values in scene_texts)
    ):
        raise ValueError(
            f"Could not find all six storyboard scenes for {asset.source_key}"
        )

    text_sources: list[str] = []
    seen: set[str] = set()
    for values in scene_texts:
        for value in values:
            if not isinstance(value, str):
                raise ValueError(f"Unexpected storyboard text for {asset.source_key}")
            clean = value.strip()
            if clean and clean not in seen:
                seen.add(clean)
                text_sources.append(clean)
    if not text_sources:
        raise ValueError(f"No storyboard text found for {asset.source_key}")

    generated_sources: dict[str, str] = {}
    for source, selector in GENERATED_TEXT_SELECTORS.items():
        scoped_selectors = ", ".join(
            f"#{scene_id} {selector}" for scene_id in scene_ids
        )
        if page.locator(scoped_selectors).count():
            generated_sources[source] = selector

    return SceneTextInventory(
        text_sources=tuple(text_sources),
        generated_sources=generated_sources,
    )


def collect_catalog_scene_text(
    source_root: Path,
    assets: Sequence[SourceAsset],
) -> dict[str, SceneTextInventory]:
    """Collect exact scene text for all 24 assets in one browser session."""

    inventories: dict[str, SceneTextInventory] = {}
    with sync_playwright() as playwright:
        browser: Browser = playwright.chromium.launch(
            headless=True,
            args=["--allow-file-access-from-files"],
        )
        page = browser.new_page(
            viewport={"width": 2080, "height": 1240},
            device_scale_factor=1,
        )
        try:
            for asset in assets:
                inventories[asset.source_key] = collect_scene_text_inventory(
                    page,
                    source_root,
                    asset,
                )
        finally:
            browser.close()
    if set(inventories) != set(SPANISH_SOURCE_KEYS):
        raise ValueError("Scene text inventory does not cover all 24 source masters")
    return inventories


def _source_fingerprint(
    asset: SourceAsset,
    inventory: SceneTextInventory,
    translation_model: str,
) -> str:
    """Hash every source value that can affect a cached translation."""

    payload = {
        "promptVersion": TRANSLATION_PROMPT_VERSION,
        "translationModel": translation_model,
        "sourceKey": asset.source_key,
        "targetKey": asset.target_key,
        "product": asset.product,
        "baseSceneId": asset.base_scene_id,
        "narration": asset.narration,
        "instructions": asset.instructions,
        "title": asset.title,
        "sceneText": list(inventory.text_sources),
        "generatedText": dict(inventory.generated_sources),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _translation_response_format(
    asset: SourceAsset,
    inventory: SceneTextInventory,
) -> dict[str, Any]:
    """Return the strict Responses JSON schema for one Spanish translation."""

    replacement_count = len(inventory.all_sources)
    return {
        "type": "json_schema",
        "name": "spanish_video_translation",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "sourceKey",
                "targetKey",
                "narration",
                "instructions",
                "title",
                "onScreenReplacements",
            ],
            "properties": {
                "sourceKey": {
                    "type": "string",
                    "enum": [asset.source_key],
                },
                "targetKey": {
                    "type": "string",
                    "enum": [asset.target_key],
                },
                "narration": {"type": "string", "minLength": 1},
                "instructions": {"type": "string", "minLength": 1},
                "title": {"type": "string", "minLength": 1},
                "onScreenReplacements": {
                    "type": "array",
                    "minItems": replacement_count,
                    "maxItems": replacement_count,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["source", "spanish"],
                        "properties": {
                            "source": {"type": "string", "minLength": 1},
                            "spanish": {"type": "string", "minLength": 1},
                        },
                    },
                },
            },
        },
    }


def _translation_prompt(
    asset: SourceAsset,
    inventory: SceneTextInventory,
) -> str:
    """Return source-complete translation material for one Spanish edition."""

    payload = {
        "sourceKey": asset.source_key,
        "targetKey": asset.target_key,
        "product": asset.product.title(),
        "narration": asset.narration,
        "deliveryInstructions": asset.instructions,
        "videoTitle": asset.title,
        "onScreenSourceStrings": list(inventory.all_sources),
    }
    return "\n\n".join(
        [
            (
                "Create the Spanish edition of this professional Mparanza video. "
                "Translate the narration into natural spoken Spanish and rewrite the "
                "delivery instructions in Spanish for a calm, intelligent, "
                "conversational professional voice. Translate the title into concise "
                "natural Spanish and keep it at no more than 100 characters."
            ),
            (
                "Return exactly one onScreenReplacements row for every supplied source "
                "string, preserving each source string byte-for-byte in the source "
                "field and preserving the supplied order. Translate visible prose "
                "naturally and concisely. Keep product names, identifiers, code, "
                "numbers, and symbols unchanged when translation would be wrong. "
                "Do not omit, merge, split, invent, or rename source strings."
            ),
            (
                "Keep the meaning and evidence boundaries of the source. Do not add "
                "claims, warnings, slogans, calls to action, or marketing language."
            ),
            json.dumps(payload, ensure_ascii=False, indent=2),
        ]
    )


def _response_output_text(response_payload: Mapping[str, Any]) -> str:
    """Extract the first Responses API output-text block."""

    direct = response_payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    output = response_payload.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if (
                    isinstance(part, dict)
                    and part.get("type") == "output_text"
                    and isinstance(part.get("text"), str)
                    and part["text"].strip()
                ):
                    return part["text"]
    raise RuntimeError("Translation response did not contain output text")


def _request_bytes(
    request: urllib.request.Request,
    *,
    operation: str,
    timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
) -> bytes:
    """Perform one secret-safe OpenAI request with bounded transient retries."""

    for attempt in range(1, MAX_REQUEST_ATTEMPTS + 1):
        retry_error: BaseException
        retry_reason: str
        try:
            # Both request constructors use fixed HTTPS OpenAI endpoints.
            with urllib.request.urlopen(  # nosec B310
                request,
                timeout=timeout_seconds,
            ) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code != 429 and not 500 <= exc.code < 600:
                raise RuntimeError(
                    f"{operation} was rejected with HTTP {exc.code}"
                ) from exc
            retry_error = exc
            retry_reason = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError) as exc:
            retry_error = exc
            retry_reason = "a transient network error"

        if attempt == MAX_REQUEST_ATTEMPTS:
            raise RuntimeError(
                f"{operation} failed after {MAX_REQUEST_ATTEMPTS} attempts "
                f"due to {retry_reason}"
            ) from retry_error
        delay_seconds = min(
            RETRY_BASE_SECONDS * (2 ** (attempt - 1)),
            RETRY_MAX_SECONDS,
        )
        LOGGER.warning(
            "Retrying %s after %s (attempt %d/%d, %.1fs backoff)",
            operation,
            retry_reason,
            attempt,
            MAX_REQUEST_ATTEMPTS,
            delay_seconds,
        )
        time.sleep(delay_seconds)
    raise AssertionError("Unreachable request retry state")


def _request_translation(
    asset: SourceAsset,
    inventory: SceneTextInventory,
    api_key: str,
    translation_model: str,
) -> dict[str, Any]:
    """Request one complete Spanish translation in strict JSON mode."""

    body = json.dumps(
        {
            "model": translation_model,
            "store": False,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "You are a senior native-Spanish editor for restrained, "
                        "professional product education. Return only the requested "
                        "strict JSON object."
                    ),
                },
                {
                    "role": "user",
                    "content": _translation_prompt(asset, inventory),
                },
            ],
            "text": {
                "format": _translation_response_format(asset, inventory),
            },
            "max_output_tokens": 20_000,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        OPENAI_RESPONSES_ENDPOINT,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "OpenAI-Safety-Identifier": "mparanza-spanish-video-editions",
        },
        method="POST",
    )
    response_bytes = _request_bytes(
        request,
        operation=f"Spanish translation for {asset.source_key}",
    )
    try:
        response_payload = json.loads(response_bytes.decode("utf-8"))
        output_payload = json.loads(_response_output_text(response_payload))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Spanish translation for {asset.source_key} returned invalid JSON"
        ) from exc
    if not isinstance(output_payload, dict):
        raise RuntimeError(
            f"Spanish translation for {asset.source_key} was not a JSON object"
        )
    return output_payload


def validate_translation_item(
    asset: SourceAsset,
    inventory: SceneTextInventory,
    item: Mapping[str, Any],
    *,
    source_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Normalize and require complete source-string coverage for one translation."""

    if item.get("sourceKey") != asset.source_key:
        raise ValueError(f"Translation source key mismatch for {asset.source_key}")
    if item.get("targetKey") != asset.target_key:
        raise ValueError(f"Translation target key mismatch for {asset.source_key}")
    if (
        source_fingerprint is not None
        and item.get("sourceFingerprint") != source_fingerprint
    ):
        raise ValueError(
            f"Translation source fingerprint changed for {asset.source_key}"
        )

    text_values: dict[str, str] = {}
    for field in ("narration", "instructions", "title"):
        value = item.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"Translation field {field!r} is empty for {asset.source_key}"
            )
        text_values[field] = value.strip()
    if len(text_values["title"]) > 100:
        raise ValueError(f"Spanish YouTube title is too long for {asset.source_key}")

    on_screen = item.get("onScreen")
    if on_screen is None:
        rows = item.get("onScreenReplacements")
        if not isinstance(rows, list):
            raise ValueError(
                f"Translation replacements are missing for {asset.source_key}"
            )
        on_screen = {}
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("source"), str)
                or not isinstance(row.get("spanish"), str)
                or not row["spanish"].strip()
            ):
                raise ValueError(
                    f"Invalid on-screen replacement for {asset.source_key}"
                )
            source = row["source"]
            if source in on_screen:
                raise ValueError(
                    f"Duplicate on-screen source {source!r} for {asset.source_key}"
                )
            on_screen[source] = row["spanish"].strip()
    if not isinstance(on_screen, dict) or not all(
        isinstance(source, str) and isinstance(spanish, str) and spanish.strip()
        for source, spanish in on_screen.items()
    ):
        raise ValueError(f"Invalid on-screen map for {asset.source_key}")

    expected_sources = set(inventory.all_sources)
    actual_sources = set(on_screen)
    if actual_sources != expected_sources:
        missing = sorted(expected_sources - actual_sources)
        unexpected = sorted(actual_sources - expected_sources)
        raise ValueError(
            f"Incomplete on-screen map for {asset.source_key}; "
            f"missing={missing!r}, unexpected={unexpected!r}"
        )

    normalized = {
        "sourceKey": asset.source_key,
        "targetKey": asset.target_key,
        "narration": text_values["narration"],
        "instructions": text_values["instructions"],
        "title": text_values["title"],
        "onScreen": {
            source: str(on_screen[source]).strip() for source in inventory.all_sources
        },
        "generatedTextSources": list(inventory.generated_sources),
    }
    if source_fingerprint is not None:
        normalized["sourceFingerprint"] = source_fingerprint
    return normalized


def _write_json_atomic(path: Path, payload: Any) -> None:
    """Write JSON atomically so interrupted batches retain the last valid cache."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _load_translation_cache(path: Path) -> dict[str, Any]:
    """Load a prior translation cache, or return an empty cache."""

    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def build_translation_bundle(
    *,
    assets: Sequence[SourceAsset],
    inventories: Mapping[str, SceneTextInventory],
    api_key: str,
    cache_path: Path,
    request_translation: TranslationRequester = _request_translation,
) -> dict[str, Any]:
    """Translate all 24 editions, reusing only fingerprint-matched cached items."""

    translation_model = _translation_model()
    existing = _load_translation_cache(cache_path)
    existing_items = existing.get("items")
    if not isinstance(existing_items, dict):
        existing_items = {}

    fingerprints = {
        asset.source_key: _source_fingerprint(
            asset,
            inventories[asset.source_key],
            translation_model,
        )
        for asset in assets
    }
    validated_cached: dict[str, dict[str, Any]] = {}
    for asset in assets:
        cached = existing_items.get(asset.target_key)
        if not isinstance(cached, dict):
            continue
        try:
            validated_cached[asset.target_key] = validate_translation_item(
                asset,
                inventories[asset.source_key],
                cached,
                source_fingerprint=fingerprints[asset.source_key],
            )
        except ValueError:
            LOGGER.info("Refreshing stale Spanish translation for %s", asset.source_key)

    items: dict[str, dict[str, Any]] = {}
    for asset in assets:
        inventory = inventories[asset.source_key]
        fingerprint = fingerprints[asset.source_key]
        cached = validated_cached.get(asset.target_key)
        if cached is not None:
            items[asset.target_key] = cached
            LOGGER.info("Reusing cached Spanish translation for %s", asset.source_key)
            continue

        for validation_attempt in range(1, 4):
            LOGGER.info("Translating Spanish edition %s", asset.source_key)
            raw_item = dict(
                request_translation(
                    asset,
                    inventory,
                    api_key,
                    translation_model,
                )
            )
            raw_item["sourceFingerprint"] = fingerprint
            try:
                items[asset.target_key] = validate_translation_item(
                    asset,
                    inventory,
                    raw_item,
                    source_fingerprint=fingerprint,
                )
                break
            except ValueError:
                if validation_attempt == 3:
                    raise
                LOGGER.warning(
                    "Retrying structurally invalid Spanish translation for %s "
                    "(attempt %d/3)",
                    asset.source_key,
                    validation_attempt + 1,
                )
        checkpoint_items = dict(validated_cached)
        checkpoint_items.update(items)
        checkpoint = {
            "schemaVersion": TRANSLATION_CACHE_SCHEMA_VERSION,
            "promptVersion": TRANSLATION_PROMPT_VERSION,
            "translationModel": translation_model,
            "generatedAt": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "assetCount": len(checkpoint_items),
            "complete": False,
            "items": checkpoint_items,
        }
        _write_json_atomic(cache_path, checkpoint)

    expected_targets = {_target_key(key) for key in SPANISH_SOURCE_KEYS}
    if set(items) != expected_targets or len(items) != 24:
        raise ValueError("Spanish translation bundle does not cover all 24 editions")
    bundle = {
        "schemaVersion": TRANSLATION_CACHE_SCHEMA_VERSION,
        "promptVersion": TRANSLATION_PROMPT_VERSION,
        "translationModel": translation_model,
        "generatedAt": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "assetCount": len(items),
        "complete": True,
        "sourceKeys": list(SPANISH_SOURCE_KEYS),
        "targetKeys": [_target_key(key) for key in SPANISH_SOURCE_KEYS],
        "items": items,
    }
    _write_json_atomic(cache_path, bundle)
    return bundle


def _load_openai_api_key(secret_file: Path) -> str:
    """Load the established key without exposing it in logs or arguments."""

    text = secret_file.read_text(encoding="utf-8")
    match = re.search(r"(?m)^\s*openAiKey\s*=\s*(.+?)\s*$", text)
    api_key = match.group(1).strip().strip('"').strip("'") if match else ""
    if len(api_key) < 20:
        raise RuntimeError(
            f"openAiKey is missing from the configured secrets file: {secret_file}"
        )
    return api_key


def _required_tool(name: str, *fallbacks: str) -> str:
    """Return one media executable or raise a precise build error."""

    resolved = shutil.which(name)
    if resolved:
        return resolved
    for fallback in fallbacks:
        candidate = Path(fallback)
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError(f"Required executable not found: {name}")


def _run(
    command: Sequence[str],
    *,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run one controlled local media command."""

    LOGGER.debug("Running %s", " ".join(command))
    return subprocess.run(  # nosec B603
        list(command),
        check=True,
        capture_output=capture_output,
        text=True,
    )


def _sha256(path: Path) -> str:
    """Return the SHA-256 digest of one generated artifact."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _artifact_record(
    path: Path,
    output_root: Path,
    mime_type: str,
) -> dict[str, Any]:
    """Describe one upload artifact with a portable output-relative path."""

    return {
        "path": path.relative_to(output_root).as_posix(),
        "mimeType": mime_type,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _render_fingerprint(
    asset: SourceAsset,
    translation: Mapping[str, Any],
) -> str:
    """Hash every input that can materially change one Spanish upload asset."""

    payload = {
        "schemaVersion": "1.0.0",
        "asset": {
            "sourceKey": asset.source_key,
            "targetKey": asset.target_key,
            "baseSceneId": asset.base_scene_id,
            "sceneWeights": asset.scene_weights,
        },
        "translation": translation,
        "voice": video_voice_for_language(TARGET_LANGUAGE),
        "ttsModel": OPENAI_VIDEO_TTS_MODEL,
        "render": {
            "width": FRAME_WIDTH,
            "height": FRAME_HEIGHT,
            "frameRate": FRAME_RATE,
            "transitionSeconds": TRANSITION_SECONDS,
            "leadSilenceSeconds": LEAD_SILENCE_SECONDS,
            "tailSilenceSeconds": TAIL_SILENCE_SECONDS,
            "captionMaxCharacters": CAPTION_MAX_CHARACTERS,
        },
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _load_valid_render_checkpoint(
    *,
    output_root: Path,
    asset: SourceAsset,
    render_fingerprint: str,
) -> dict[str, Any] | None:
    """Reuse only a complete checkpoint whose source and artifact hashes match."""

    checkpoint_path = output_root / "assets" / asset.target_key / "asset.json"
    if not checkpoint_path.is_file():
        return None
    try:
        entry = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        entry.get("sourceKey") != asset.source_key
        or entry.get("key") != asset.target_key
        or entry.get("renderFingerprint") != render_fingerprint
        or entry.get("language") != TARGET_LANGUAGE
        or entry.get("privacyStatus") != "unlisted"
        or entry.get("voice", {}).get("name")
        != video_voice_for_language(TARGET_LANGUAGE)
        or entry.get("voice", {}).get("model") != OPENAI_VIDEO_TTS_MODEL
    ):
        return None
    files = entry.get("files")
    if not isinstance(files, dict) or set(files) != {
        "video",
        "thumbnail",
        "captions",
    }:
        return None
    for artifact in files.values():
        if not isinstance(artifact, dict):
            return None
        relative_path = artifact.get("path")
        expected_sha256 = artifact.get("sha256")
        if not isinstance(relative_path, str) or not isinstance(expected_sha256, str):
            return None
        path = output_root / relative_path
        if not path.is_file() or _sha256(path) != expected_sha256:
            return None
    return entry


def _audio_duration(ffprobe: str, path: Path) -> float:
    """Read a positive audio duration through ffprobe."""

    result = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
    )
    duration = float(result.stdout.strip())
    if duration <= 0:
        raise ValueError(f"Invalid narration duration for {path}")
    return duration


def _synthesize_narration(
    *,
    api_key: str,
    translation: Mapping[str, Any],
    output_path: Path,
) -> None:
    """Generate Spanish narration with the centrally approved voice."""

    voice = video_voice_for_language(TARGET_LANGUAGE)
    body = json.dumps(
        {
            "model": OPENAI_VIDEO_TTS_MODEL,
            "voice": voice,
            "input": translation["narration"],
            "instructions": translation["instructions"],
            "response_format": "wav",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        OPENAI_SPEECH_ENDPOINT,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    speech_bytes = _request_bytes(
        request,
        operation=f"Spanish narration for {translation['targetKey']}",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(".wav.tmp")
    temporary_path.write_bytes(speech_bytes)
    temporary_path.replace(output_path)


def _render_spanish_scenes(
    *,
    page: Page,
    source_root: Path,
    asset: SourceAsset,
    inventory: SceneTextInventory,
    translation: Mapping[str, Any],
    output_dir: Path,
) -> list[Path]:
    """Render six Spanish 1080p storyboard frames with complete replacements."""

    actual_inventory = collect_scene_text_inventory(page, source_root, asset)
    if actual_inventory != inventory:
        raise ValueError(f"Storyboard text changed during build for {asset.source_key}")
    replacements = translation["onScreen"]
    replacement_hits = page.evaluate(
        """
        values => {
          const hits = {};
          const walker = document.createTreeWalker(
            document.body,
            NodeFilter.SHOW_TEXT
          );
          let node;
          while ((node = walker.nextNode())) {
            const source = node.nodeValue.trim();
            if (Object.prototype.hasOwnProperty.call(values, source)) {
              node.nodeValue = node.nodeValue.replace(source, values[source]);
              hits[source] = (hits[source] || 0) + 1;
            }
          }
          return hits;
        }
        """,
        replacements,
    )
    if not isinstance(replacement_hits, dict):
        raise ValueError(
            f"Could not verify storyboard replacements for {asset.source_key}"
        )
    missing_dom_sources = set(inventory.text_sources) - set(replacement_hits)
    if missing_dom_sources:
        raise ValueError(
            f"Spanish storyboard replacement missed source text for "
            f"{asset.source_key}: {sorted(missing_dom_sources)!r}"
        )

    css_rules = []
    for source, selector in inventory.generated_sources.items():
        spanish = replacements[source]
        css_rules.append(
            f".localized-es {selector}::after "
            f"{{ content: {json.dumps(spanish, ensure_ascii=False)} !important; }}"
        )
    if css_rules:
        page.add_style_tag(content="\n".join(css_rules))

    frame_dir = output_dir / "scenes"
    frame_dir.mkdir(parents=True, exist_ok=True)
    frame_paths: list[Path] = []
    for index in range(SCENE_COUNT):
        scene_id = f"{asset.base_scene_id}-{index}"
        locator = page.locator(f"#{scene_id}")
        locator.evaluate("node => node.classList.add('localized-es')")
        page.locator(".scene").evaluate_all(
            """
            (nodes, activeId) => nodes.forEach(node => {
              node.style.display = node.id === activeId ? "" : "none";
            })
            """,
            scene_id,
        )
        page.evaluate("""
            () => {
              window.scrollTo(0, 0);
              document.documentElement.scrollLeft = 0;
              document.body.scrollLeft = 0;
            }
            """)
        page.wait_for_timeout(200)
        bounding_box = locator.bounding_box()
        if (
            bounding_box is None
            or round(bounding_box["width"]) != FRAME_WIDTH
            or round(bounding_box["height"]) != FRAME_HEIGHT
        ):
            raise ValueError(
                f"Unexpected storyboard dimensions for {asset.source_key} scene {index}"
            )
        layout = locator.evaluate("""
            node => ({
              clientWidth: node.clientWidth,
              clientHeight: node.clientHeight,
              scrollWidth: node.scrollWidth,
              scrollHeight: node.scrollHeight
            })
            """)
        if (
            layout["scrollWidth"] > layout["clientWidth"] + 1
            or layout["scrollHeight"] > layout["clientHeight"] + 1
        ):
            raise ValueError(
                f"Spanish storyboard content overflows {asset.source_key} scene {index}"
            )
        frame_path = frame_dir / f"{asset.target_key}-{index}.png"
        locator.screenshot(path=str(frame_path), animations="disabled")
        frame_paths.append(frame_path)
    if len(frame_paths) != SCENE_COUNT or any(
        not path.is_file() or path.stat().st_size == 0 for path in frame_paths
    ):
        raise ValueError(
            f"Spanish scene rendering is incomplete for {asset.source_key}"
        )
    return frame_paths


def _render_video(
    *,
    ffmpeg: str,
    narration_path: Path,
    narration_duration: float,
    frame_paths: Sequence[Path],
    scene_weights: Sequence[float],
    title: str,
    output_path: Path,
) -> float:
    """Render one Spanish MP4 using the established camera and fade treatment."""

    target_duration = LEAD_SILENCE_SECONDS + narration_duration + TAIL_SILENCE_SECONDS
    weighted_total = target_duration + TRANSITION_SECONDS * (SCENE_COUNT - 1)
    durations = [
        weighted_total * weight / sum(scene_weights) for weight in scene_weights
    ]
    command = [ffmpeg, "-y", "-v", "error"]
    for frame_path in frame_paths:
        command.extend(["-i", str(frame_path)])
    command.extend(["-i", str(narration_path)])

    filters: list[str] = []
    for index, duration in enumerate(durations):
        frame_count = max(1, round(duration * FRAME_RATE))
        x_expression = "iw/2-(iw/zoom/2)" if index % 2 == 0 else "iw-iw/zoom"
        filters.append(
            f"[{index}:v]scale=2304:1296,"
            f"zoompan=z='min(zoom+0.00032,1.035)':x='{x_expression}':"
            f"y='ih/2-(ih/zoom/2)':d={frame_count}:"
            f"s={FRAME_WIDTH}x{FRAME_HEIGHT}:fps={FRAME_RATE},"
            f"trim=duration={duration:.3f},setpts=PTS-STARTPTS,"
            f"format=yuv420p[v{index}]"
        )

    previous = "v0"
    elapsed = durations[0]
    for index in range(1, SCENE_COUNT):
        offset = elapsed - TRANSITION_SECONDS * index
        output_label = f"vx{index}"
        filters.append(
            f"[{previous}][v{index}]"
            f"xfade=transition=fade:duration={TRANSITION_SECONDS:.3f}:"
            f"offset={offset:.3f}[{output_label}]"
        )
        previous = output_label
        elapsed += durations[index]
    filters.append(f"[{previous}]format=yuv420p[vout]")

    lead_ms = round(LEAD_SILENCE_SECONDS * 1000)
    filters.append(
        f"[{SCENE_COUNT}:a]loudnorm=I=-16:TP=-1.5:LRA=7:dual_mono=true,"
        f"aresample=48000,pan=stereo|c0=c0|c1=c0,"
        f"adelay={lead_ms}|{lead_ms},apad,"
        f"atrim=duration={target_duration:.3f},"
        f"afade=t=out:st={target_duration - 0.5:.3f}:d=0.5[aout]"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-metadata",
            f"title={title}",
            "-shortest",
            str(output_path),
        ]
    )
    _run(command)
    return target_duration


def _vtt_timestamp(seconds: float) -> str:
    """Format seconds as a WebVTT timestamp."""

    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"


def _caption_chunks(narration: str) -> list[str]:
    """Split Spanish narration into readable caption-sized chunks."""

    sentences = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", narration.strip())
        if part.strip()
    ]
    chunks: list[str] = []
    for sentence in sentences:
        words = sentence.split()
        current: list[str] = []
        for word in words:
            candidate = " ".join([*current, word])
            if current and len(candidate) > CAPTION_MAX_CHARACTERS:
                chunks.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            chunks.append(" ".join(current))
    if not chunks:
        raise ValueError("Spanish narration cannot produce empty captions")
    return chunks


def _write_captions(
    path: Path,
    narration: str,
    narration_duration: float,
) -> int:
    """Write proportional Spanish WebVTT cues as the only text-sidecar asset."""

    chunks = _caption_chunks(narration)
    weights = [max(1, len(chunk)) for chunk in chunks]
    total_weight = sum(weights)
    elapsed_weight = 0
    lines = ["WEBVTT", ""]
    for index, (chunk, weight) in enumerate(zip(chunks, weights, strict=True), 1):
        start = LEAD_SILENCE_SECONDS + (
            narration_duration * elapsed_weight / total_weight
        )
        elapsed_weight += weight
        end = LEAD_SILENCE_SECONDS + (
            narration_duration * elapsed_weight / total_weight
        )
        lines.extend(
            [
                str(index),
                f"{_vtt_timestamp(start)} --> {_vtt_timestamp(end)}",
                chunk,
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return len(chunks)


def _validate_video(
    *,
    ffprobe: str,
    video_path: Path,
    expected_duration: float,
) -> dict[str, Any]:
    """Validate the upload master codecs, dimensions, and duration."""

    result = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            (
                "stream=codec_type,codec_name,width,height,pix_fmt,"
                "sample_rate,channels:format=duration"
            ),
            "-of",
            "json",
            str(video_path),
        ],
        capture_output=True,
    )
    payload = json.loads(result.stdout)
    streams = payload.get("streams", [])
    video = next(
        (stream for stream in streams if stream.get("codec_type") == "video"),
        None,
    )
    audio = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"),
        None,
    )
    if not isinstance(video, dict) or not isinstance(audio, dict):
        raise ValueError(f"Spanish master is missing video or audio: {video_path}")
    duration = float(payload["format"]["duration"])
    if abs(duration - expected_duration) > 0.35:
        raise ValueError(f"Spanish master duration drifted for {video_path}")
    expected_video = {
        "codec_name": "h264",
        "width": FRAME_WIDTH,
        "height": FRAME_HEIGHT,
        "pix_fmt": "yuv420p",
    }
    if any(video.get(key) != value for key, value in expected_video.items()):
        raise ValueError(f"Spanish master video format is invalid: {video_path}")
    if audio.get("codec_name") != "aac" or audio.get("sample_rate") != "48000":
        raise ValueError(f"Spanish master audio format is invalid: {video_path}")
    return {
        "durationSeconds": round(duration, 3),
        "width": video["width"],
        "height": video["height"],
        "videoCodec": video["codec_name"],
        "pixelFormat": video["pix_fmt"],
        "audioCodec": audio["codec_name"],
        "audioSampleRate": int(audio["sample_rate"]),
        "audioChannels": audio["channels"],
    }


def _upload_description(asset: SourceAsset, translation: Mapping[str, Any]) -> str:
    """Return restrained Spanish YouTube metadata with the TTS disclosure."""

    voice_label = video_voice_for_language(TARGET_LANGUAGE).title()
    return "\n\n".join(
        [
            str(translation["narration"]),
            (
                "Narración generada con un modelo de texto a voz de OpenAI "
                f"usando la voz {voice_label}. Los ejemplos son ilustrativos "
                "y no contienen datos de clientes."
            ),
            f"#{asset.product.title()} #Codex #OpenAI",
        ]
    )


def _render_all_assets(
    *,
    source_root: Path,
    output_root: Path,
    assets: Sequence[SourceAsset],
    inventories: Mapping[str, SceneTextInventory],
    translation_bundle: Mapping[str, Any],
    api_key: str,
) -> list[dict[str, Any]]:
    """Render and validate all 24 Spanish upload packages."""

    ffmpeg = _required_tool("ffmpeg", "/opt/homebrew/bin/ffmpeg")
    ffprobe = _required_tool("ffprobe", "/opt/homebrew/bin/ffprobe")
    entries: list[dict[str, Any]] = []
    translations = translation_bundle["items"]

    with sync_playwright() as playwright:
        browser: Browser = playwright.chromium.launch(
            headless=True,
            args=["--allow-file-access-from-files"],
        )
        page = browser.new_page(
            viewport={"width": 2080, "height": 1240},
            device_scale_factor=1,
        )
        try:
            for order, asset in enumerate(assets):
                translation = translations[asset.target_key]
                render_fingerprint = _render_fingerprint(asset, translation)
                checkpoint = _load_valid_render_checkpoint(
                    output_root=output_root,
                    asset=asset,
                    render_fingerprint=render_fingerprint,
                )
                if checkpoint is not None:
                    LOGGER.info("Reusing Spanish edition %s", asset.target_key)
                    entries.append(checkpoint)
                    continue
                LOGGER.info("Rendering Spanish edition %s", asset.target_key)
                asset_dir = output_root / "assets" / asset.target_key
                narration_path = asset_dir / "narration.wav"
                _synthesize_narration(
                    api_key=api_key,
                    translation=translation,
                    output_path=narration_path,
                )
                narration_duration = _audio_duration(ffprobe, narration_path)
                frame_paths = _render_spanish_scenes(
                    page=page,
                    source_root=source_root,
                    asset=asset,
                    inventory=inventories[asset.source_key],
                    translation=translation,
                    output_dir=asset_dir,
                )
                video_path = asset_dir / f"{asset.target_key}.mp4"
                target_duration = _render_video(
                    ffmpeg=ffmpeg,
                    narration_path=narration_path,
                    narration_duration=narration_duration,
                    frame_paths=frame_paths,
                    scene_weights=asset.scene_weights,
                    title=translation["title"],
                    output_path=video_path,
                )
                thumbnail_path = asset_dir / f"{asset.target_key}-thumbnail.png"
                shutil.copyfile(frame_paths[0], thumbnail_path)
                captions_path = asset_dir / f"{asset.target_key}.vtt"
                cue_count = _write_captions(
                    captions_path,
                    translation["narration"],
                    narration_duration,
                )
                media = _validate_video(
                    ffprobe=ffprobe,
                    video_path=video_path,
                    expected_duration=target_duration,
                )
                upload_title = str(translation["title"]).replace(" — ", " | ")
                if len(upload_title) > 100:
                    raise ValueError(
                        f"Spanish YouTube title is too long for {asset.target_key}"
                    )
                entry = {
                    "order": order,
                    "sourceKey": asset.source_key,
                    "key": asset.target_key,
                    "product": asset.product,
                    "language": TARGET_LANGUAGE,
                    "title": upload_title,
                    "description": _upload_description(asset, translation),
                    "privacyStatus": "unlisted",
                    "madeForKids": False,
                    "renderFingerprint": render_fingerprint,
                    "voice": {
                        "name": video_voice_for_language(TARGET_LANGUAGE),
                        "model": OPENAI_VIDEO_TTS_MODEL,
                    },
                    "captionLanguage": TARGET_LANGUAGE,
                    "captionName": "Español",
                    "cueCount": cue_count,
                    "files": {
                        "video": _artifact_record(
                            video_path,
                            output_root,
                            "video/mp4",
                        ),
                        "thumbnail": _artifact_record(
                            thumbnail_path,
                            output_root,
                            "image/png",
                        ),
                        "captions": _artifact_record(
                            captions_path,
                            output_root,
                            "text/vtt",
                        ),
                    },
                    "media": media,
                }
                _write_json_atomic(asset_dir / "asset.json", entry)
                entries.append(entry)
        finally:
            browser.close()

    if len(entries) != 24 or {entry["sourceKey"] for entry in entries} != set(
        SPANISH_SOURCE_KEYS
    ):
        raise ValueError("Rendered Spanish upload packages are incomplete")
    return entries


def _write_upload_manifest(
    *,
    output_root: Path,
    entries: Sequence[Mapping[str, Any]],
) -> Path:
    """Write the complete YouTube-only upload manifest."""

    expected_targets = [_target_key(key) for key in SPANISH_SOURCE_KEYS]
    actual_targets = [str(entry.get("key")) for entry in entries]
    if len(entries) != 24 or actual_targets != expected_targets:
        raise ValueError("YouTube upload manifest must contain the ordered 24 editions")
    manifest = {
        "schemaVersion": UPLOAD_MANIFEST_SCHEMA_VERSION,
        "generatedAt": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "publicationTarget": "youtube",
        "privacyStatus": "unlisted",
        "language": TARGET_LANGUAGE,
        "assetCount": len(entries),
        "sourceKeys": list(SPANISH_SOURCE_KEYS),
        "targetKeys": expected_targets,
        "voicePolicy": {
            "name": video_voice_for_language(TARGET_LANGUAGE),
            "model": OPENAI_VIDEO_TTS_MODEL,
        },
        "assets": list(entries),
    }
    manifest_path = output_root / "youtube-upload-manifest.json"
    _write_json_atomic(manifest_path, manifest)
    return manifest_path


def build_spanish_video_editions(
    *,
    source_root: Path = DEFAULT_SOURCE_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    secret_file: Path = DEFAULT_SECRET_FILE,
    translations_only: bool = False,
) -> Path:
    """Build translations and optionally all Spanish YouTube upload assets."""

    source_root = source_root.resolve()
    output_root = output_root.resolve()
    assets = load_source_catalog(source_root)
    inventories = collect_catalog_scene_text(source_root, assets)
    api_key = _load_openai_api_key(secret_file.resolve())
    cache_path = output_root / "translation-bundle.json"
    translation_bundle = build_translation_bundle(
        assets=assets,
        inventories=inventories,
        api_key=api_key,
        cache_path=cache_path,
    )
    if translations_only:
        return cache_path
    entries = _render_all_assets(
        source_root=source_root,
        output_root=output_root,
        assets=assets,
        inventories=inventories,
        translation_bundle=translation_bundle,
        api_key=api_key,
    )
    return _write_upload_manifest(output_root=output_root, entries=entries)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Build the 24 missing Spanish Clara and Vera YouTube editions."),
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=DEFAULT_SOURCE_ROOT,
        help="Established ignored video-pilots source directory.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Ignored output directory for Spanish editions.",
    )
    parser.add_argument(
        "--secrets-file",
        type=Path,
        default=DEFAULT_SECRET_FILE,
        help="Established local secrets file containing openAiKey.",
    )
    parser.add_argument(
        "--translations-only",
        action="store_true",
        help="Create or validate the cached Spanish translation bundle only.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show subprocess-level diagnostic detail.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the Spanish edition builder."""

    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    result_path = build_spanish_video_editions(
        source_root=args.source_root,
        output_root=args.output_root,
        secret_file=args.secrets_file,
        translations_only=args.translations_only,
    )
    LOGGER.info("Wrote %s", result_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
