from __future__ import annotations

"""Exercise coverage failures and source drift with temporary plugin fixtures."""

import json
import tempfile
import unittest
from pathlib import Path

from catalogue import coverage_errors, snapshot

__all__ = ["CatalogueTests"]


def fixture(root: Path) -> dict:
    manifest = root / ".codex-plugin" / "plugin.json"
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({"name": "vera", "version": "test"}))
    for name in ("studio-archive", "business-planning", "vera"):
        skill = root / "skills" / name / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(f"---\nname: {name}\n---\nFixture\n")
    return snapshot(root)


def assessment(inventory: dict, ids: list[str]) -> dict:
    return {
        "catalogue_fingerprint": inventory["catalogue_fingerprint"],
        "target": {"id": "CH-GE", "language": "fr"},
        "rows": [{"function_id": name} for name in ids],
    }


class CatalogueTests(unittest.TestCase):
    def test_complete_inventory_includes_helpers_without_judging_roles(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            inventory = fixture(Path(folder))
            record = assessment(
                inventory, ["vera", "business-planning", "studio-archive"]
            )
            self.assertEqual(coverage_errors(inventory, record), [])

    def test_omitted_existing_function_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            inventory = fixture(Path(folder))
            record = assessment(inventory, ["vera", "studio-archive"])
            self.assertEqual(
                coverage_errors(inventory, record),
                ["Missing entries: business-planning"],
            )

    def test_new_service_cannot_replace_existing_function(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            inventory = fixture(Path(folder))
            record = assessment(inventory, ["vera", "studio-archive", "tax-returns"])
            self.assertEqual(
                coverage_errors(inventory, record),
                [
                    "Missing entries: business-planning",
                    "Entries absent from Vera: tax-returns",
                ],
            )

    def test_duplicate_does_not_count_as_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            inventory = fixture(Path(folder))
            record = assessment(
                inventory,
                ["vera", "studio-archive", "business-planning", "business-planning"],
            )
            self.assertEqual(
                coverage_errors(inventory, record),
                ["Duplicate entries: business-planning"],
            )

    def test_same_language_does_not_require_same_target(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            inventory = fixture(Path(folder))
            record = assessment(
                inventory, ["vera", "studio-archive", "business-planning"]
            )
            record["target"]["id"] = "FR"
            self.assertEqual(coverage_errors(inventory, record), [])

    def test_changed_entrypoint_invalidates_prior_catalogue_identity(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            inventory = fixture(root)
            record = assessment(
                inventory, ["vera", "studio-archive", "business-planning"]
            )
            (root / "skills" / "business-planning" / "SKILL.md").write_text("Changed")
            self.assertEqual(
                coverage_errors(snapshot(root), record),
                ["Assessment is bound to a different catalogue snapshot"],
            )


if __name__ == "__main__":
    unittest.main()
