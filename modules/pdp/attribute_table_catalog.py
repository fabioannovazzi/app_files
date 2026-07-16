from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

__all__ = [
    "AttributeTableCatalog",
    "AttributeTableCatalogCapability",
    "load_attribute_table_catalog",
]


@dataclass(frozen=True, slots=True)
class AttributeTableCatalogCapability:
    capability_id: str
    table_template: str
    description: str
    use_when: str
    avoid_when: str
    required_parameters: tuple[str, ...]
    optional_parameters: tuple[str, ...]
    source_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AttributeTableCatalog:
    schema_version: str
    purpose: str
    execution_contract: Mapping[str, Any]
    capabilities: Mapping[str, AttributeTableCatalogCapability]


def _catalog_path() -> Path:
    return Path(__file__).resolve().with_name("attribute_table_catalog.json")


def _string_tuple(raw: Any, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"{field_name} must be a list.")
    values = tuple(str(value).strip() for value in raw if str(value).strip())
    if not values:
        raise ValueError(f"{field_name} must be non-empty.")
    return values


def _required_text(raw: Mapping[str, Any], key: str) -> str:
    value = str(raw.get(key) or "").strip()
    if not value:
        raise ValueError(f"Attribute table catalog capability is missing {key}.")
    return value


def load_attribute_table_catalog(
    path: Path | None = None,
) -> AttributeTableCatalog:
    payload = json.loads((path or _catalog_path()).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Attribute table catalog must be a JSON object.")
    raw_execution_contract = payload.get("execution_contract")
    if not isinstance(raw_execution_contract, dict):
        raise ValueError("Attribute table catalog execution_contract is required.")
    _string_tuple(
        raw_execution_contract.get("required_parameters"),
        field_name="execution_contract.required_parameters",
    )
    raw_capabilities = payload.get("capabilities")
    if not isinstance(raw_capabilities, list):
        raise ValueError("Attribute table catalog capabilities must be a list.")

    capabilities: dict[str, AttributeTableCatalogCapability] = {}
    for index, raw_capability in enumerate(raw_capabilities):
        if not isinstance(raw_capability, dict):
            raise ValueError(f"Capability at index {index} must be an object.")
        capability = AttributeTableCatalogCapability(
            capability_id=_required_text(raw_capability, "capability_id"),
            table_template=_required_text(raw_capability, "table_template"),
            description=_required_text(raw_capability, "description"),
            use_when=_required_text(raw_capability, "use_when"),
            avoid_when=_required_text(raw_capability, "avoid_when"),
            required_parameters=_string_tuple(
                raw_capability.get("required_parameters"),
                field_name=f"{raw_capability.get('capability_id')}.required_parameters",
            ),
            optional_parameters=tuple(
                str(value).strip()
                for value in raw_capability.get("optional_parameters", [])
                if str(value).strip()
            ),
            source_files=_string_tuple(
                raw_capability.get("source_files"),
                field_name=f"{raw_capability.get('capability_id')}.source_files",
            ),
        )
        if capability.capability_id in capabilities:
            raise ValueError(
                f"Duplicate attribute table capability_id: {capability.capability_id}"
            )
        capabilities[capability.capability_id] = capability
    return AttributeTableCatalog(
        schema_version=str(payload.get("schema_version") or "1.0"),
        purpose=str(payload.get("purpose") or "").strip(),
        execution_contract=dict(raw_execution_contract),
        capabilities=capabilities,
    )
