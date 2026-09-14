"""Require current editorial reviews and fresh native execution checks.

Hashes and JUnit identities are mechanically verifiable. They cannot establish
teaching quality: a named reviewer records that judgment separately, per locale.
This command never creates or refreshes review attestations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re

# JUnit DTD/entity declarations are rejected before parsing.
import xml.etree.ElementTree as ET  # nosec B405
from datetime import datetime
from pathlib import Path
from typing import Any

__all__ = ["verify", "main"]

ROOT = Path(__file__).resolve().parents[2]
REVIEW_SCHEMA = "mparanza.teaching_release_review.v1"
EDITORIAL_FIELDS = (
    "purpose_and_first_use",
    "inputs_and_request",
    "execution_and_checkpoints",
    "deliverable_and_next_action",
    "practice_and_repeat",
    "language_and_pacing",
)


def _read(path: Path, root: Path) -> dict[str, Any]:
    if (
        path.is_symlink()
        or not path.is_file()
        or not path.resolve().is_relative_to(root.resolve())
    ):
        raise ValueError(f"Missing or foreign release evidence: {path}")
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError(f"Expected an object: {path}")
    return result


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing review explanation: {label}")
    return value


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"Invalid SHA-256: {label}")
    return value


def _cases(junit: Path) -> dict[str, dict[str, str]]:
    """Read successful cases only; reject ambiguous or unsuccessful test runs."""
    raw = junit.read_bytes()
    # CI emits UTF-8. Decode before screening so UTF-16 cannot hide declarations.
    xml = raw.decode("utf-8-sig")
    if "\x00" in xml or "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
        raise ValueError("JUnit must not contain DTD or entity declarations")
    document = ET.fromstring(xml)  # nosec B314
    if document.tag not in {"testsuites", "testsuite"}:
        raise ValueError("Expected a JUnit test suite")
    if (
        next(document.iter("failure"), None) is not None
        or next(document.iter("error"), None) is not None
    ):
        raise ValueError("Native teaching execution suite has failures or errors")
    cases: dict[str, dict[str, str]] = {}
    for case in document.iter("testcase"):
        identity = f"{case.get('classname', '')}::{case.get('name', '')}"
        if identity in cases:
            raise ValueError(f"Ambiguous JUnit test case: {identity}")
        properties: dict[str, str] = {}
        for item in case.findall("properties/property"):
            name = item.get("name", "")
            if name in properties:
                raise ValueError(f"Duplicate JUnit property: {identity}/{name}")
            properties[name] = item.get("value", "")
        if case.find("skipped") is not None:
            properties["teaching_skipped"] = "true"
        cases[identity] = properties
    if not cases:
        raise ValueError("No native execution test cases were recorded")
    return cases


def _review_locale(
    value: Any, key: str, language: str, digest: str, cases: dict[str, dict[str, str]]
) -> None:
    if not isinstance(value, dict) or value.get("verdict") != "accepted":
        raise ValueError(f"Teaching review is not accepted: {key}/{language}")
    editorial = value.get("editorial", {})
    if not isinstance(editorial, dict):
        raise ValueError(f"Missing editorial review: {key}/{language}")
    for field in EDITORIAL_FIELDS:
        _text(editorial.get(field), f"{key}/{language}/{field}")
    identities = []
    for phase in ("demo", "practice"):
        execution = value.get(phase)
        if not isinstance(execution, dict):
            raise ValueError(f"Missing execution review: {key}/{language}/{phase}")
        identity = _text(execution.get("test_case"), "test_case")
        identities.append(identity)
        actual = cases.get(identity, {})
        expected = f"{key}/{language}/{phase}"
        if (
            actual.get("teaching_kit") != expected
            or actual.get("teaching_course_sha256") != digest
            or actual.get("teaching_skipped") == "true"
        ):
            raise ValueError(f"Missing, skipped or stale native execution: {expected}")
        _text(execution.get("result_review"), f"{expected}/result_review")
        artifacts = execution.get("reviewed_artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise ValueError(f"No actual output artifacts reviewed: {expected}")
        names = set()
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                raise ValueError(f"Invalid reviewed artifact: {expected}")
            name = _text(artifact.get("name"), "artifact name")
            if (
                Path(name).name != name
                or name in {".", ".."}
                or "\\" in name
                or name in names
            ):
                raise ValueError(f"Use unique output basenames: {expected}")
            names.add(name)
            _sha(artifact.get("sha256"), f"{expected}/{name}")
    if len(set(identities)) != 2:
        raise ValueError(
            f"Demo and practice need distinct executions: {key}/{language}"
        )


def verify(*, root: Path, reviews: Path, junit: Path) -> dict[str, int]:
    """Check every compiled kit; run the complete compiler check first in CI."""
    cases = _cases(junit)
    kit_count = locale_count = 0
    expected_reviews = set()
    for product in ("vera", "clara", "lucia"):
        assets = root / "plugins" / product / "assets/courses"
        index = _read(assets / "index.json", root)
        if index.get("product") != product or not index.get("courses"):
            raise ValueError(f"Missing own-product teaching catalogue: {product}")
        for workflow, entry in index["courses"].items():
            if not re.fullmatch(r"[a-z0-9-]+", workflow):
                raise ValueError("Invalid workflow identity")
            key = f"{product}/{workflow}"
            path = assets / workflow / "course.json"
            course = _read(path, root)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if (
                entry.get("sha256") != digest
                or course.get("product") != product
                or course.get("workflow") != workflow
            ):
                raise ValueError(f"Stale or foreign compiled kit: {key}")
            review_path = reviews / product / f"{workflow}.json"
            expected_reviews.add(review_path.resolve())
            review = _read(review_path, reviews)
            if (
                review.get("schema") != REVIEW_SCHEMA
                or review.get("workflow") != workflow
                or review.get("product") != product
            ):
                raise ValueError(f"Invalid editorial review identity: {key}")
            if review.get("course_sha256") != digest:
                raise ValueError(f"Editorial review needs refresh: {key}")
            _text(review.get("reviewer"), f"{key}/reviewer")
            datetime.fromisoformat(
                _text(review.get("reviewed_at"), f"{key}/reviewed_at")
            )
            languages = review.get("languages")
            if not isinstance(languages, dict) or set(languages) != set(
                course["supported_languages"]
            ):
                raise ValueError(f"Editorial language coverage differs: {key}")
            for language, value in languages.items():
                _review_locale(value, key, language, digest, cases)
                locale_count += 1
            kit_count += 1
    if {path.resolve() for path in reviews.rglob("*.json")} != expected_reviews:
        raise ValueError("Release reviews include retired or foreign workflows")
    return {"reviewed_kits": kit_count, "reviewed_locales": locale_count}


def main() -> int:
    """Verify supplied evidence without manufacturing an accepted review."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument(
        "--reviews", type=Path, default=Path(__file__).parent / "release_reviews"
    )
    args = parser.parse_args()
    print(
        json.dumps(verify(root=ROOT, reviews=args.reviews, junit=args.junit), indent=2)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
