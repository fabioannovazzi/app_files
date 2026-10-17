"""Dependency-free discovery regression runnable on CPython 3.9 and 3.12."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

__all__ = ["DiscoveryRegression"]
ROOT = Path(__file__).resolve().parents[2]


class DiscoveryRegression(unittest.TestCase):
    """Check metadata and symlink semantics using the actual interpreter."""

    def test_discovery_after_new_scope_preserves_sources(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "archive_discovery_regression",
            ROOT / "plugins/studio-archive/scripts/archive_core.py",
        )
        assert spec is not None and spec.loader is not None
        core = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = core
        spec.loader.exec_module(core)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            original = root / "Existing"
            original.mkdir()
            source = original / "source.txt"
            source.write_bytes(b"original source")
            (original / "linked.txt").symlink_to(source)
            old_scopes = core._discover_top_level_scopes(root)
            new_folder = root / "New"
            new_folder.mkdir()
            added = new_folder / "added.txt"
            added.write_bytes(b"new source")
            scopes = core._discover_top_level_scopes(root)
            self.assertNotEqual(old_scopes, scopes)
            config = core.ArchiveConfig(root, scopes, "2026-10-15T00:00:00Z")

            discovered, issues = core._discover_files(config)

            self.assertEqual(
                {item.relative_path for item in discovered},
                {"Existing/source.txt", "New/added.txt"},
            )
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0].relative_path, "Existing/linked.txt")
            self.assertEqual(source.read_bytes(), b"original source")
            self.assertTrue((original / "linked.txt").is_symlink())

    def test_refresh_after_scope_change_allows_import(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "archive_refresh_regression",
            ROOT / "plugins/studio-archive/scripts/archive_core.py",
        )
        assert spec is not None and spec.loader is not None
        core = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = core
        spec.loader.exec_module(core)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            archive = base / "archive"
            client = archive / "Existing"
            client.mkdir(parents=True)
            source = client / "existing.txt"
            source.write_bytes(b"original source")
            state = base / "state"
            try:
                configured = core.configure_archive(archive, state_dir=state)
                core.refresh_archive(state_dir=state)
                registration = core.set_studio_client_identity(
                    configured["scopes"][0]["scope_id"],
                    legal_names=["Existing SRL"],
                    state_dir=state,
                )
                client_id = registration["client"]["client_id"]
                engagement = core.create_studio_client_engagement(
                    client_id, "Runtime regression", state_dir=state
                )["engagement"]
                (client / "linked.txt").symlink_to(source)
                (archive / "New").mkdir()
                (archive / "New/added.txt").write_bytes(b"new source")
                incoming = base / "incoming.txt"
                incoming.write_bytes(b"incoming source")
                imported = core.import_studio_client_document(
                    client_id,
                    incoming,
                    "source",
                    engagement_id=engagement["engagement_id"],
                    state_dir=state,
                )
                self.assertTrue(
                    core.studio_archive_status(state_dir=state)[
                        "index_requires_refresh"
                    ]
                )
                result = core.refresh_archive(state_dir=state)
                repeated = core.import_studio_client_document(
                    client_id,
                    incoming,
                    "source",
                    engagement_id=engagement["engagement_id"],
                    state_dir=state,
                )

                self.assertTrue(result["scope_configuration_changed"])
                self.assertEqual(result["document_count"], 3)
                self.assertEqual(imported["status"], "imported")
                self.assertEqual(repeated["status"], "already_imported")
                self.assertEqual(repeated["input_id"], imported["input_id"])
                self.assertEqual(
                    Path(imported["imported_path"]).read_bytes(), b"incoming source"
                )
                self.assertEqual(source.read_bytes(), b"original source")
                self.assertEqual(incoming.read_bytes(), b"incoming source")
                self.assertTrue((client / "linked.txt").is_symlink())
            finally:
                core._release_state_leases()


if __name__ == "__main__":
    unittest.main()
