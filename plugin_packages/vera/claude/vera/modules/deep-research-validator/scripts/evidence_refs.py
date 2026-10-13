"""Verify evidence bytes and locators; never infer relevance or legal support."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

__all__ = [
    "read_capture",
    "validate_reference",
    "reference_value",
    "verify_answer_identity",
    "make_reference",
    "main",
]

REFERENCE_KINDS = {
    "source_capture",
    "source_access",
    "fact",
    "scope",
    "calculation",
    "claim",
    "answer",
    "answer_contract",
    "inspection_note",
    "treatment_note",
}


class EvidenceDigestError(ValueError):
    """The retained bytes differ from the expected revision."""


def _file(root: Path, relative: object) -> Path:
    if (
        not isinstance(relative, str)
        or not relative
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
    ):
        raise ValueError("Evidence reference requires a safe relative artifact path")
    candidate = root.resolve()
    for part in Path(relative).parts:
        candidate /= part
        if candidate.is_symlink():
            raise ValueError("Symlink evidence artifact rejected")
    path = candidate.resolve(strict=True)
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Evidence reference escapes its run or is not a file")
    return path


def _checked_bytes(path: Path, expected: object) -> bytes:
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError(f"Evidence digest missing or invalid: {path.name}")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise EvidenceDigestError(f"Evidence artifact digest mismatch: {path.name}")
    return raw


def read_capture(source: dict[str, Any], base: Path | None) -> tuple[str, str, str]:
    """Check retained original and extracted bytes before consuming source text."""
    text_path = source.get("captured_text_path")
    original_path = source.get("captured_original_path")
    scope = str(source.get("capture_scope") or "captured_text")
    if not text_path and not original_path:
        return str(source.get("excerpt") or ""), "inventory_excerpt", "excerpt_only"
    if base is None:
        return "", scope, "capture_base_missing"
    try:
        if original_path:
            _checked_bytes(
                _file(base, original_path), source.get("source_bytes_sha256")
            )
        if not text_path:
            return "", scope, "verified_metadata_only"
        raw = _checked_bytes(
            _file(base, text_path), source.get("extracted_text_sha256")
        )
        return raw.decode("utf-8"), scope, "verified"
    except UnicodeDecodeError:
        return "", scope, "invalid_capture_encoding"
    except FileNotFoundError:
        return "", scope, "capture_missing"
    except EvidenceDigestError:
        return "", scope, "digest_mismatch"
    except ValueError:
        return "", scope, "capture_reference_invalid"
    except OSError:
        return "", scope, "capture_unreadable"


def _pointer(value: Any, pointer: object) -> Any:
    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
        raise ValueError("Evidence JSON pointer must identify an existing value")
    if not pointer:
        return value
    for token in pointer[1:].split("/"):
        if re.search(r"~(?![01])", token):
            raise ValueError("Invalid JSON pointer escape")
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict) and token in value:
            value = value[token]
        elif (
            isinstance(value, list)
            and re.fullmatch(r"0|[1-9][0-9]*", token)
            and int(token) < len(value)
        ):
            value = value[int(token)]
        else:
            raise ValueError("Evidence JSON pointer does not resolve")
    return value


def validate_reference(root: Path, reference: object) -> list[Path]:
    """Resolve a declared reference at its pinned revision, without judging meaning."""
    if (
        not isinstance(reference, dict)
        or not isinstance(reference.get("kind"), str)
        or reference["kind"] not in REFERENCE_KINDS
    ):
        raise ValueError("Unsupported structured evidence reference")
    path = _file(root, reference.get("artifact"))
    raw = _checked_bytes(path, reference.get("sha256"))
    artifacts = [path]
    kind = reference["kind"]
    if kind == "claim":
        identifier = reference.get("claim_index")
        if type(identifier) is not int or identifier < 1:
            raise ValueError("Claim reference requires its actual claim index")
        review = json.loads(raw)
        if not isinstance(review, dict) or not isinstance(review.get("claims"), list):
            raise ValueError("Claim reference requires an actual claims review")
        matches = [
            claim
            for claim in review.get("claims", [])
            if isinstance(claim, dict) and claim.get("claim_index") == identifier
        ]
        if len(matches) != 1:
            raise ValueError("Referenced claim does not exist or is ambiguous")
    elif kind == "source_capture":
        inventory_path = _file(root, reference.get("inventory"))
        inventory_raw = _checked_bytes(
            inventory_path, reference.get("inventory_sha256")
        )
        inventory = json.loads(inventory_raw)
        if not isinstance(inventory, dict) or not isinstance(
            inventory.get("sources"), list
        ):
            raise ValueError("Source reference requires an actual source inventory")
        sources = [
            source
            for source in inventory.get("sources", [])
            if isinstance(source, dict)
            and source.get("source_id") == reference.get("source_id")
        ]
        if len(sources) != 1:
            raise ValueError("Source reference does not resolve uniquely")
        source = sources[0]
        capture_id = reference.get("capture_id")
        candidates = (
            [source]
            if source.get("capture_id") == capture_id
            else [
                item
                for item in source.get("capture_history", [])
                if isinstance(item, dict) and item.get("capture_id") == capture_id
            ]
        )
        if not isinstance(capture_id, str) or not capture_id or len(candidates) != 1:
            raise ValueError("Capture reference does not resolve uniquely")
        capture = candidates[0]
        text, _, integrity = read_capture(capture, inventory_path.parent)
        if (
            integrity != "verified"
            or _file(inventory_path.parent, capture.get("captured_text_path")) != path
        ):
            raise ValueError(
                "Source reference does not identify verified capture bytes"
            )
        artifacts.append(inventory_path)
        if capture.get("captured_original_path"):
            artifacts.append(
                _file(inventory_path.parent, capture["captured_original_path"])
            )
        _span(text, reference)
    elif kind != "answer":
        if "pointer" in reference:
            _pointer(json.loads(raw), reference["pointer"])
        else:
            _span(raw.decode("utf-8"), reference)
    return artifacts


def _span(text: str, reference: dict[str, Any]) -> None:
    start, end = reference.get("start_char"), reference.get("end_char")
    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(text)
    ):
        raise ValueError("Evidence passage locator does not resolve in its capture")
    if "passage" in reference and text[start:end] != reference["passage"]:
        raise ValueError("Evidence passage differs from its pinned locator")


def reference_value(root: Path, reference: dict[str, Any]) -> Any:
    """Read a declared JSON note at its verified revision and actual pointer."""
    validate_reference(root, reference)
    raw = _checked_bytes(
        _file(root, reference.get("artifact")), reference.get("sha256")
    )
    return _pointer(json.loads(raw), reference.get("pointer"))


def verify_answer_identity(answer: Path, review: Path) -> str:
    """A review can accompany only its actual answer, not another saved revision."""
    raw = answer.read_bytes()
    value = json.loads(review.read_bytes())
    recorded = value.get("validated_document") if isinstance(value, dict) else None
    if (
        not isinstance(recorded, str)
        or not recorded.strip()
        or raw.decode("utf-8").strip() != recorded.strip()
    ):
        raise ValueError("The delivered document differs from the reviewed answer")
    return hashlib.sha256(raw).hexdigest()


def make_reference(root: Path, selection: dict[str, Any]) -> dict[str, Any]:
    """Pin hashes for a model-selected existing artifact and locator, without choosing evidence."""
    reference = dict(selection)
    reference["sha256"] = hashlib.sha256(
        _file(root, reference.get("artifact")).read_bytes()
    ).hexdigest()
    if reference.get("kind") == "source_capture":
        reference["inventory_sha256"] = hashlib.sha256(
            _file(root, reference.get("inventory")).read_bytes()
        ).hexdigest()
    validate_reference(root, reference)
    return reference


def main() -> int:
    """Return a verified reference for an explicitly selected artifact; write no run files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    args = parser.parse_args()
    try:
        root = args.output_dir.resolve(strict=True)
        selection = json.loads(args.selection.read_bytes())
        if not isinstance(selection, dict):
            raise ValueError("Reference selection must be an object")
        result = make_reference(root, selection)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
