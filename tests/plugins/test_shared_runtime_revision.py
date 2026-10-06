"""A release must distinguish changed recipes from already installed policies."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "runtime_revision_gate", ROOT / "scripts/check_shared_runtime_revision.py"
)
assert SPEC and SPEC.loader
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


def policy_case(root: Path, revision: int = 6) -> dict[str, bytes]:
    old = {}
    for product in gate.PRODUCTS:
        for name in gate.FILES:
            content = (
                f"POLICY_REVISION = {revision}\n".encode()
                if name == gate.BACKEND
                else b"# previous recipe\n"
            )
            relative = f"plugins/{product}/{name}"
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            old[relative] = content
    return old


@pytest.mark.parametrize("filename", gate.FILES)
def test_changed_runtime_files_require_new_revision(tmp_path, filename):
    old = policy_case(tmp_path)
    for product in gate.PRODUCTS:
        with (tmp_path / f"plugins/{product}/{filename}").open("ab") as handle:
            handle.write(b"# changed\n")

    with pytest.raises(ValueError, match="without increasing"):
        gate.verify_policy(tmp_path, old.__getitem__)


def test_coordinated_upgrade_accepts_new_recipe(tmp_path):
    old = policy_case(tmp_path)
    policy_case(tmp_path, revision=7)
    for product in gate.PRODUCTS:
        (tmp_path / f"plugins/{product}/requirements-shared-core.txt").write_bytes(
            b"tzdata>=2024.1\n"
        )

    assert gate.verify_policy(tmp_path, old.__getitem__) == 7


def test_unchanged_release_does_not_need_revision_bump(tmp_path):
    old = policy_case(tmp_path)

    assert gate.verify_policy(tmp_path, old.__getitem__) == 6


def test_product_drift_is_rejected(tmp_path):
    policy_case(tmp_path)
    (tmp_path / "plugins/clara/requirements-shared-core.txt").write_bytes(b"drift\n")

    with pytest.raises(ValueError, match="differs from Vera"):
        gate.verify_policy(tmp_path)


def test_revision_downgrade_is_rejected(tmp_path):
    old = policy_case(tmp_path, revision=7)
    policy_case(tmp_path, revision=6)

    with pytest.raises(ValueError, match="cannot decrease"):
        gate.verify_policy(tmp_path, old.__getitem__)
