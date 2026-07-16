#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from modules.add_attributes.attribute_taxonomy import get_attribute_taxonomy

ROOT = Path(__file__).resolve().parents[1]
ACTIVITY_PATH = ROOT / "attribute_activity.json"


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=4), encoding="utf-8")


def main() -> int:
    taxonomy = get_attribute_taxonomy()
    activity = load_json(ACTIVITY_PATH)

    activity_categories = {category["id"]: category for category in activity.get("categories", [])}
    new_categories: list[dict[str, object]] = []

    for category in taxonomy.get("categories", []):
        category_id: str = category.get("id")
        if category_id in activity_categories:
            continue

        attributes = [
            {
                "id": attribute.get("id"),
                "label": attribute.get("label", attribute.get("id")),
                "status": "inactive",
            }
            for attribute in category.get("attributes", [])
        ]

        new_categories.append(
            {
                "id": category_id,
                "label": category.get("label", category_id),
                "attributes": attributes,
            }
        )

    if not new_categories:
        return 0

    activity["categories"].extend(new_categories)
    activity["categories"] = sorted(activity["categories"], key=lambda item: item["id"])
    version = taxonomy.get("version")
    if version:
        activity["version"] = version

    dump_json(ACTIVITY_PATH, activity)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
