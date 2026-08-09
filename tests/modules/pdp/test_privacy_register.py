from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from modules.pdp.privacy_register import get_public_privacy_register

ROOT = Path(__file__).resolve().parents[3]


def _manifest_ids(directory: Path, key: str) -> set[str]:
    return {
        str(json.loads(path.read_text(encoding="utf-8"))[key])
        for path in directory.glob("*.json")
    }


def _all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for child in value.values() for key in _all_keys(child)
        }
    if isinstance(value, (list, tuple)):
        return {key for child in value for key in _all_keys(child)}
    return set()


def test_public_register_covers_every_canonical_workflow_and_service() -> None:
    register = get_public_privacy_register("en")

    workflows = {
        item["name"]: {workflow["id"] for workflow in item["workflows"]}
        for item in register["products"]
    }
    services: dict[str, set[str]] = {"Vera": set(), "Clara": set()}
    for service in register["services"]:
        services[service["product"]].add(service["service_id"])

    assert workflows["Vera"] == _manifest_ids(
        ROOT / "plugins" / "vera" / "privacy" / "workstreams", "workstream"
    )
    assert workflows["Clara"] == _manifest_ids(
        ROOT / "plugins" / "clara" / "privacy" / "workflows", "workflow"
    )
    assert services["Vera"] == _manifest_ids(
        ROOT / "plugins" / "vera" / "privacy" / "services", "service_id"
    )
    assert services["Clara"] == _manifest_ids(
        ROOT / "plugins" / "clara" / "privacy" / "hosted-services", "service_id"
    )


def test_public_register_omits_internal_manifest_implementation_fields() -> None:
    register = get_public_privacy_register("it")

    forbidden = {
        "controls",
        "governed_paths",
        "governed_repository_paths",
        "implemented_by",
        "on_violation",
        "security_controls",
        "source_fingerprint",
    }

    assert forbidden.isdisjoint(_all_keys(register))


def test_italian_register_explains_function_and_mparanza_boundaries() -> None:
    register = get_public_privacy_register("it")
    workflows = {
        workflow["id"]: workflow
        for product in register["products"]
        for workflow in product["workflows"]
    }

    journal_sampling = workflows["journal-sampling"]
    attribute_reporting = workflows["attribute-reporting"]

    assert journal_sampling["name"] == "Campionamento delle registrazioni contabili"
    assert journal_sampling["model_classes"]
    assert journal_sampling["service_ids"] == []
    assert attribute_reporting["service_ids"] == ["clara-retail-data"]
    assert attribute_reporting["service_names"] == [
        "Mparanza Retail Data and Mapping Service"
    ]
    retail_data = next(
        service
        for service in register["services"]
        if service["id"] == "clara-retail-data"
    )
    assert retail_data["data_sent"]
    assert retail_data["data_returned"]


def test_public_data_handling_template_exposes_searchable_privacy_register() -> None:
    template = (ROOT / "templates" / "data_handling.html").read_text(encoding="utf-8")

    assert 'id="function-register"' in template
    assert '{% set register_copy = privacy_register["copy"] %}' in template
    assert 'id="privacy-register-search"' in template
    assert 'aria-live="polite"' in template
    assert 'id="service-{{ service.id }}"' in template
    assert "/static/js/privacy-register.js" in template
    assert "governed_paths" not in template
    assert "source_fingerprint" not in template


def test_privacy_register_interactions_use_native_disclosure_controls() -> None:
    template = (ROOT / "templates" / "data_handling.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "js" / "privacy-register.js").read_text(
        encoding="utf-8"
    )

    assert "<details" in template
    assert "<summary>" in template
    assert 'label for="privacy-register-search"' in template
    assert "data-privacy-register-entry" in template
    assert 'addEventListener("input", update)' in script
    assert 'a[href^="#service-"]' in script
    assert "HTMLDetailsElement" in script
