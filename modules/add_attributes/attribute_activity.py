from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

HERE = Path(__file__).resolve().parent
APP_ROOT = HERE.parent.parent
ACTIVITY_CONFIG_PATH = APP_ROOT / "attribute_activity.json"
ACTIVITY_CONFIG_TEMPLATE_PATH = APP_ROOT / "attribute_activity.example.json"

LOGGER = logging.getLogger(__name__)

__all__ = [
    "get_attribute_activity_config",
    "get_active_attribute_ids_for_category",
    "is_attribute_active",
]


def get_attribute_activity_config() -> Dict[str, Any]:
    """Load the attribute activity configuration from disk."""

    config_path = ACTIVITY_CONFIG_PATH
    if not config_path.is_file():
        if ACTIVITY_CONFIG_TEMPLATE_PATH.is_file():
            LOGGER.info(
                "Using attribute activity template at %s", ACTIVITY_CONFIG_TEMPLATE_PATH
            )
            config_path = ACTIVITY_CONFIG_TEMPLATE_PATH
        else:
            raise FileNotFoundError(
                f"Attribute activity configuration not found: {ACTIVITY_CONFIG_PATH}"
            )

    try:
        with config_path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:  # pragma: no cover - invalid JSON
        raise ValueError(f"Invalid JSON in {ACTIVITY_CONFIG_PATH}") from exc


def _normalise(value: Any) -> str:
    return str(value).strip().lower()


def _iter_categories(config: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    categories = config.get("categories", [])
    if isinstance(categories, list):
        for category in categories:
            if isinstance(category, dict):
                yield category


def get_active_attribute_ids_for_category(
    category_id: str, config: Dict[str, Any] | None = None
) -> Tuple[set[str], bool]:
    """Return active attribute IDs and a flag indicating config presence."""

    if config is None:
        try:
            config = get_attribute_activity_config()
        except (FileNotFoundError, ValueError):  # pragma: no cover - defensive
            LOGGER.warning("Attribute activity configuration unavailable; defaulting to active")
            return set(), False

    category_id_normalised = _normalise(category_id)
    for category in _iter_categories(config):
        if _normalise(category.get("id")) != category_id_normalised:
            continue

        attributes = category.get("attributes", [])
        active: set[str] = set()
        if isinstance(attributes, list):
            for attribute in attributes:
                if not isinstance(attribute, dict):
                    continue
                attr_id = attribute.get("id")
                if not attr_id:
                    continue
                status = attribute.get("status", "active")
                status_norm = _normalise(status)
                is_active = status_norm in {"active", "true", "1", "yes"}
                if is_active:
                    active.add(str(attr_id).strip())
        return active, True

    return set(), False


def is_attribute_active(
    category_id: str, attribute_id: str, config: Dict[str, Any] | None = None
) -> bool:
    """Return ``True`` if ``attribute_id`` should be queried for ``category_id``."""

    active_ids, category_found = get_active_attribute_ids_for_category(category_id, config)
    if not category_found:
        return True
    return attribute_id in active_ids
