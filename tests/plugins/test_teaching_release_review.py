"""Release evidence must bind exact kits, locales and distinct native runs."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "teaching_release", ROOT / "scripts/course_materials/verify_release.py"
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def evidence(tmp_path):
    """Synthetic contract evidence, never a review of a shipped teaching kit."""
    root, reviews = tmp_path / "repo", tmp_path / "reviews"
    suite = ET.Element("testsuite")
    for product in ("vera", "clara", "lucia"):
        assets = root / f"plugins/{product}/assets/courses"
        path = assets / "example/course.json"
        write_json(
            path,
            {"product": product, "workflow": "example", "supported_languages": ["it"]},
        )
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        write_json(
            assets / "index.json",
            {"product": product, "courses": {"example": {"sha256": digest}}},
        )
        locale = {
            "verdict": "accepted",
            "editorial": {
                field: "Synthetic explanation for contract test."
                for field in release.EDITORIAL_FIELDS
            },
        }
        for phase in ("demo", "practice"):
            name = f"test_run[{product}-it-{phase}]"
            case = ET.SubElement(
                suite, "testcase", classname="tests.example", name=name
            )
            properties = ET.SubElement(case, "properties")
            ET.SubElement(
                properties,
                "property",
                name="teaching_kit",
                value=f"{product}/example/it/{phase}",
            )
            ET.SubElement(
                properties, "property", name="teaching_course_sha256", value=digest
            )
            locale[phase] = {
                "test_case": f"tests.example::{name}",
                "result_review": "Synthetic artifact review for gate test only.",
                "reviewed_artifacts": [{"name": "report.html", "sha256": "a" * 64}],
            }
        write_json(
            reviews / product / "example.json",
            {
                "schema": release.REVIEW_SCHEMA,
                "product": product,
                "workflow": "example",
                "course_sha256": digest,
                "reviewer": "Synthetic fixture",
                "reviewed_at": "2026-09-14T12:00:00+00:00",
                "languages": {"it": locale},
            },
        )
    junit = tmp_path / "native.xml"
    ET.ElementTree(suite).write(junit)
    return {"root": root, "reviews": reviews, "junit": junit}


def change_review(evidence, mutate):
    path = evidence["reviews"] / "vera/example.json"
    value = json.loads(path.read_text())
    mutate(value)
    write_json(path, value)


def test_exact_reviews_and_successful_native_runs_are_accepted(evidence):
    assert release.verify(**evidence) == {"reviewed_kits": 3, "reviewed_locales": 3}


@pytest.fixture
def retained_evidence(evidence):
    root = evidence["root"]
    original = {
        "schema": "mparanza.course.v1",
        "product": "vera",
        "workflow": "example",
        "supported_languages": ["it"],
        "locales": {"it": {"title": "Published fixture"}},
        "sources": [],
    }
    snapshot = root / "scripts/course_materials/published/vera/example/course.json"
    write_json(snapshot, original)
    retained = {
        "course_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        "published_version": "0.1.1",
    }
    write_json(
        root / "scripts/course_materials/release_plan.json",
        {"retained": {"vera/example": retained}},
    )
    current = {
        **original,
        "sources": [{"path": "current.py"}],
        "retained_from": retained,
    }
    course = root / "plugins/vera/assets/courses/example/course.json"
    write_json(course, current)
    write_json(
        course.parent.parent / "index.json",
        {
            "product": "vera",
            "courses": {
                "example": {"sha256": hashlib.sha256(course.read_bytes()).hexdigest()}
            },
        },
    )
    (evidence["reviews"] / "vera/example.json").unlink()
    return evidence, course, snapshot


def test_retained_lesson_keeps_published_content_without_new_review(retained_evidence):
    evidence, _, _ = retained_evidence
    assert release.verify(**evidence) == {"reviewed_kits": 2, "reviewed_locales": 2}


@pytest.mark.parametrize("change", ["course", "snapshot", "unlisted"])
def test_retained_lesson_rejects_changed_or_unlisted_content(retained_evidence, change):
    evidence, course, snapshot = retained_evidence
    if change == "unlisted":
        write_json(
            evidence["root"] / "scripts/course_materials/release_plan.json",
            {"retained": {}},
        )
    else:
        target = course if change == "course" else snapshot
        payload = json.loads(target.read_text())
        payload["locales"]["it"]["title"] = "Changed fixture"
        write_json(target, payload)
        if change == "course":
            write_json(
                course.parent.parent / "index.json",
                {
                    "product": "vera",
                    "courses": {
                        "example": {
                            "sha256": hashlib.sha256(course.read_bytes()).hexdigest()
                        }
                    },
                },
            )
    with pytest.raises(ValueError, match="[Rr]etained"):
        release.verify(**evidence)


def test_refreshing_compiled_hash_does_not_refresh_editorial_review(evidence):
    assets = evidence["root"] / "plugins/vera/assets/courses"
    path = assets / "example/course.json"
    path.write_text(path.read_text() + "\n")
    index = json.loads((assets / "index.json").read_text())
    index["courses"]["example"]["sha256"] = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()
    write_json(assets / "index.json", index)
    with pytest.raises(ValueError, match="Editorial review needs refresh"):
        release.verify(**evidence)


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("schema", "unknown", "identity"),
        ("product", "clara", "identity"),
        ("workflow", "foreign", "identity"),
        ("reviewer", "", "explanation"),
        ("reviewed_at", "unknown", "isoformat"),
        ("languages", {}, "language coverage"),
    ],
)
def test_invalid_review_metadata_blocks_release(evidence, field, value, message):
    change_review(evidence, lambda review: review.update({field: value}))
    with pytest.raises(ValueError, match=message):
        release.verify(**evidence)


@pytest.mark.parametrize("field", release.EDITORIAL_FIELDS)
def test_every_first_use_review_dimension_needs_an_explanation(evidence, field):
    change_review(
        evidence, lambda review: review["languages"]["it"]["editorial"].pop(field)
    )
    with pytest.raises(ValueError, match="Missing review explanation"):
        release.verify(**evidence)


@pytest.mark.parametrize("verdict", ["pending", "rejected", "unable_to_determine"])
def test_unaccepted_editorial_review_blocks_release(evidence, verdict):
    change_review(
        evidence, lambda review: review["languages"]["it"].update(verdict=verdict)
    )
    with pytest.raises(ValueError, match="not accepted"):
        release.verify(**evidence)


@pytest.mark.parametrize(
    "mutation,message",
    [
        (
            lambda phase: phase.update(test_case="tests.example::missing"),
            "native execution",
        ),
        (lambda phase: phase.update(result_review=""), "explanation"),
        (lambda phase: phase.update(reviewed_artifacts=[]), "output artifacts"),
        (
            lambda phase: phase["reviewed_artifacts"][0].update(name="../foreign.html"),
            "basenames",
        ),
        (lambda phase: phase["reviewed_artifacts"][0].update(sha256="bad"), "SHA-256"),
    ],
)
def test_unreviewed_or_unexecuted_output_blocks_release(evidence, mutation, message):
    change_review(
        evidence, lambda review: mutation(review["languages"]["it"]["practice"])
    )
    with pytest.raises(ValueError, match=message):
        release.verify(**evidence)


@pytest.mark.parametrize(
    "status,message",
    [
        ("failure", "failures or errors"),
        ("error", "failures or errors"),
        ("skipped", "native execution"),
    ],
)
def test_unsuccessful_native_execution_cannot_count(evidence, status, message):
    tree = ET.parse(evidence["junit"])
    ET.SubElement(tree.find("testcase"), status)
    tree.write(evidence["junit"])
    with pytest.raises(ValueError, match=message):
        release.verify(**evidence)


@pytest.mark.parametrize("property_name", ["teaching_kit", "teaching_course_sha256"])
def test_native_run_must_target_exact_phase_and_course(evidence, property_name):
    tree = ET.parse(evidence["junit"])
    tree.find(f"testcase/properties/property[@name='{property_name}']").set(
        "value", "stale"
    )
    tree.write(evidence["junit"])
    with pytest.raises(ValueError, match="stale native execution"):
        release.verify(**evidence)


def test_missing_review_cannot_be_replaced_with_compiler_success(evidence):
    (evidence["reviews"] / "vera/example.json").unlink()
    with pytest.raises(ValueError, match="Missing or foreign"):
        release.verify(**evidence)


def test_duplicate_junit_case_is_not_accepted(evidence):
    tree = ET.parse(evidence["junit"])
    tree.getroot().append(tree.find("testcase"))
    tree.write(evidence["junit"])
    with pytest.raises(ValueError, match="Ambiguous"):
        release.verify(**evidence)


def test_xml_entities_are_rejected(evidence):
    evidence["junit"].write_text(
        '<!DOCTYPE testsuite [<!ENTITY a "payload">]><testsuite/>'
    )
    with pytest.raises(ValueError, match="DTD or entity"):
        release.verify(**evidence)


def test_utf16_cannot_hide_xml_entity_declarations(evidence):
    evidence["junit"].write_bytes(
        '<!DOCTYPE testsuite [<!ENTITY a "payload">]><testsuite/>'.encode("utf-16")
    )
    with pytest.raises((ValueError, UnicodeDecodeError)):
        release.verify(**evidence)


def test_retired_workflow_review_is_rejected(evidence):
    write_json(evidence["reviews"] / "vera/retired.json", {})
    with pytest.raises(ValueError, match="retired or foreign"):
        release.verify(**evidence)
