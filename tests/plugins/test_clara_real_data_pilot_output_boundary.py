from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLARA_ROOT = ROOT / "plugins" / "clara"
SCRIPTS_ROOT = CLARA_ROOT / "scripts"


def _load_module(name: str, path: Path) -> Any:
    scripts_path = str(SCRIPTS_ROOT)
    inserted = scripts_path not in sys.path
    if inserted:
        sys.path.insert(0, scripts_path)
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted:
            sys.path.remove(scripts_path)


BOUNDARY = _load_module(
    "clara_real_data_pilot_output_boundary_test",
    SCRIPTS_ROOT / "real_data_pilot_output_boundary.py",
)

ARTIFACT_ROLE = "artifact-0123456789abcdef"
ARTIFACT_RELATIVE_PATH = f"artifacts/{ARTIFACT_ROLE}.bin"


def _fresh_output(tmp_path: Path) -> Path:
    input_path = tmp_path / "input.json"
    input_path.write_text('{"synthetic":true}\n', encoding="utf-8")
    return BOUNDARY.create_fresh_pilot_output_directory(
        tmp_path / "output",
        local_run_root=tmp_path,
        repository_root=ROOT,
        input_paths=[input_path],
    )


def _complete_output(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    output_path = _fresh_output(tmp_path)
    (output_path / "mechanical_errors.json").write_text(
        '{"schema_version":"synthetic-test"}\n',
        encoding="utf-8",
    )
    artifacts_root = output_path / "artifacts"
    artifacts_root.mkdir()
    (artifacts_root / f"{ARTIFACT_ROLE}.bin").write_text(
        '{"synthetic":"prepared"}\n',
        encoding="utf-8",
    )
    return output_path, {
        "mechanical_errors": "mechanical_errors.json",
        ARTIFACT_ROLE: ARTIFACT_RELATIVE_PATH,
    }


def test_output_boundary_creates_fresh_leaf_and_seals_exact_tree(
    tmp_path: Path,
) -> None:
    output_path, expected_roles = _complete_output(tmp_path)

    receipts = BOUNDARY.seal_pilot_output_directory(
        output_path,
        expected_roles=expected_roles,
        local_run_root=tmp_path,
        repository_root=ROOT,
    )

    assert output_path.stat().st_mode & 0o777 == 0o700
    assert [receipt["role"] for receipt in receipts] == [
        ARTIFACT_ROLE,
        "mechanical_errors",
    ]
    assert (
        BOUNDARY.validate_pilot_output_receipts(
            receipts,
            output_path,
            local_run_root=tmp_path,
            repository_root=ROOT,
        )
        == receipts
    )


def test_output_boundary_receipts_are_deterministic(tmp_path: Path) -> None:
    output_path, expected_roles = _complete_output(tmp_path)

    first = BOUNDARY.seal_pilot_output_directory(
        output_path,
        expected_roles=expected_roles,
        local_run_root=tmp_path,
        repository_root=ROOT,
    )
    second = BOUNDARY.seal_pilot_output_directory(
        output_path,
        expected_roles=expected_roles,
        local_run_root=tmp_path,
        repository_root=ROOT,
    )

    assert first == second


def test_output_boundary_refuses_existing_output_without_deleting_it(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "input.json"
    input_path.write_text("{}\n", encoding="utf-8")
    output_path = tmp_path / "output"
    output_path.mkdir()
    marker_path = output_path / "marker.txt"
    original_bytes = b"must remain\n"
    marker_path.write_bytes(original_bytes)

    with pytest.raises(
        BOUNDARY.ContractValidationError,
        match="must not already exist",
    ):
        BOUNDARY.create_fresh_pilot_output_directory(
            output_path,
            local_run_root=tmp_path,
            repository_root=ROOT,
            input_paths=[input_path],
        )

    assert marker_path.read_bytes() == original_bytes


def test_output_boundary_refuses_empty_input_paths(tmp_path: Path) -> None:
    with pytest.raises(
        BOUNDARY.ContractValidationError,
        match="non-empty sequence of existing files",
    ):
        BOUNDARY.create_fresh_pilot_output_directory(
            tmp_path / "output",
            local_run_root=tmp_path,
            repository_root=ROOT,
            input_paths=[],
        )


def test_output_boundary_refuses_unsorted_input_paths(tmp_path: Path) -> None:
    first_input = tmp_path / "a.json"
    second_input = tmp_path / "b.json"
    first_input.write_text("{}\n", encoding="utf-8")
    second_input.write_text("{}\n", encoding="utf-8")

    with pytest.raises(
        BOUNDARY.ContractValidationError,
        match="must be sorted by resolved path",
    ):
        BOUNDARY.create_fresh_pilot_output_directory(
            tmp_path / "output",
            local_run_root=tmp_path,
            repository_root=ROOT,
            input_paths=[second_input, first_input],
        )


def test_output_boundary_refuses_duplicate_resolved_input_paths(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "input.json"
    input_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(
        BOUNDARY.ContractValidationError,
        match="must identify unique resolved files",
    ):
        BOUNDARY.create_fresh_pilot_output_directory(
            tmp_path / "output",
            local_run_root=tmp_path,
            repository_root=ROOT,
            input_paths=[input_path, input_path],
        )


def test_output_boundary_refuses_symlink_alias_input_paths(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "input.json"
    input_path.write_text("{}\n", encoding="utf-8")
    alias_path = tmp_path / "input-alias.json"
    alias_path.symlink_to(input_path)

    with pytest.raises(
        BOUNDARY.ContractValidationError,
        match="must identify unique resolved files",
    ):
        BOUNDARY.create_fresh_pilot_output_directory(
            tmp_path / "output",
            local_run_root=tmp_path,
            repository_root=ROOT,
            input_paths=[input_path, alias_path],
        )


def test_output_boundary_refuses_directory_input_path(tmp_path: Path) -> None:
    input_path = tmp_path / "input"
    input_path.mkdir()

    with pytest.raises(
        BOUNDARY.ContractValidationError,
        match=r"input_paths\[0\] must identify an existing file",
    ):
        BOUNDARY.create_fresh_pilot_output_directory(
            tmp_path / "output",
            local_run_root=tmp_path,
            repository_root=ROOT,
            input_paths=[input_path],
        )


def test_output_boundary_refuses_missing_input_path(tmp_path: Path) -> None:
    with pytest.raises(
        BOUNDARY.ContractValidationError,
        match=r"input_paths\[0\] must identify an existing file",
    ):
        BOUNDARY.create_fresh_pilot_output_directory(
            tmp_path / "output",
            local_run_root=tmp_path,
            repository_root=ROOT,
            input_paths=[tmp_path / "missing.json"],
        )


def test_output_boundary_refuses_noncanonical_or_escaping_role_path(
    tmp_path: Path,
) -> None:
    output_path = _fresh_output(tmp_path)

    with pytest.raises(
        BOUNDARY.ContractValidationError,
        match="canonical relative POSIX path",
    ):
        BOUNDARY.seal_pilot_output_directory(
            output_path,
            expected_roles={"mechanical_errors": "../mechanical_errors.json"},
            local_run_root=tmp_path,
            repository_root=ROOT,
        )


@pytest.mark.parametrize(
    ("expected_roles", "error_match"),
    [
        (
            {
                "mechanical_errors": "mechanical_errors.json",
                "prepared_data": "prepared/data.json",
            },
            "opaque artifact role",
        ),
        (
            {
                "mechanical_errors": "mechanical_errors.json",
                ARTIFACT_ROLE: "prepared/data.json",
            },
            "registered generic path",
        ),
        (
            {"mechanical_errors": "errors.json"},
            "registered generic path",
        ),
    ],
)
def test_output_boundary_refuses_descriptive_roles_or_unregistered_paths(
    tmp_path: Path,
    expected_roles: dict[str, str],
    error_match: str,
) -> None:
    output_path = _fresh_output(tmp_path)

    with pytest.raises(
        BOUNDARY.ContractValidationError,
        match=error_match,
    ):
        BOUNDARY.seal_pilot_output_directory(
            output_path,
            expected_roles=expected_roles,
            local_run_root=tmp_path,
            repository_root=ROOT,
        )


def test_output_boundary_refuses_nonprivate_directory_when_sealing(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "output"
    output_path.mkdir(mode=0o755)
    output_path.chmod(0o755)
    (output_path / "mechanical_errors.json").write_text(
        "{}\n",
        encoding="utf-8",
    )

    with pytest.raises(
        BOUNDARY.ContractValidationError,
        match="must have mode 0700",
    ):
        BOUNDARY.seal_pilot_output_directory(
            output_path,
            expected_roles={"mechanical_errors": "mechanical_errors.json"},
            local_run_root=tmp_path,
            repository_root=ROOT,
        )


def test_output_boundary_refuses_missing_or_extra_output(tmp_path: Path) -> None:
    output_path = _fresh_output(tmp_path)
    (output_path / "unexpected.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(
        BOUNDARY.ContractValidationError,
        match="file set does not match",
    ):
        BOUNDARY.seal_pilot_output_directory(
            output_path,
            expected_roles={"mechanical_errors": "mechanical_errors.json"},
            local_run_root=tmp_path,
            repository_root=ROOT,
        )


def test_output_boundary_refuses_symlink_output(tmp_path: Path) -> None:
    output_path = _fresh_output(tmp_path)
    target_path = tmp_path / "target.json"
    target_path.write_text("{}\n", encoding="utf-8")
    (output_path / "mechanical_errors.json").symlink_to(target_path)

    with pytest.raises(
        BOUNDARY.ContractValidationError,
        match="must not contain symlinks",
    ):
        BOUNDARY.seal_pilot_output_directory(
            output_path,
            expected_roles={"mechanical_errors": "mechanical_errors.json"},
            local_run_root=tmp_path,
            repository_root=ROOT,
        )


def test_output_boundary_refuses_hard_link_output(tmp_path: Path) -> None:
    output_path = _fresh_output(tmp_path)
    target_path = tmp_path / "target.json"
    target_path.write_text("{}\n", encoding="utf-8")
    link_path = output_path / "mechanical_errors.json"
    try:
        link_path.hardlink_to(target_path)

        with pytest.raises(
            BOUNDARY.ContractValidationError,
            match="must not contain hard-linked files",
        ):
            BOUNDARY.seal_pilot_output_directory(
                output_path,
                expected_roles={"mechanical_errors": "mechanical_errors.json"},
                local_run_root=tmp_path,
                repository_root=ROOT,
            )
    finally:
        link_path.unlink(missing_ok=True)


def test_output_boundary_detects_byte_drift_after_sealing(tmp_path: Path) -> None:
    output_path, expected_roles = _complete_output(tmp_path)
    receipts = BOUNDARY.seal_pilot_output_directory(
        output_path,
        expected_roles=expected_roles,
        local_run_root=tmp_path,
        repository_root=ROOT,
    )
    (output_path / ARTIFACT_RELATIVE_PATH).write_text(
        '{"synthetic":"drifted"}\n',
        encoding="utf-8",
    )

    with pytest.raises(
        BOUNDARY.ContractValidationError,
        match="do not match the current output bytes",
    ):
        BOUNDARY.validate_pilot_output_receipts(
            receipts,
            output_path,
            local_run_root=tmp_path,
            repository_root=ROOT,
        )


def test_output_boundary_detects_bytes_mutated_during_sealing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path, expected_roles = _complete_output(tmp_path)
    artifact_path = output_path / ARTIFACT_RELATIVE_PATH
    original_snapshot = BOUNDARY.file_snapshot_beneath
    artifact_was_mutated = False

    def snapshot_then_mutate(path: Path, *, root: Path) -> tuple[int, str]:
        nonlocal artifact_was_mutated
        snapshot = original_snapshot(path, root=root)
        if Path(path) == artifact_path and not artifact_was_mutated:
            artifact_path.write_bytes(b'{"synthetic":"mutated-during-seal"}\n')
            artifact_was_mutated = True
        return snapshot

    monkeypatch.setattr(
        BOUNDARY,
        "file_snapshot_beneath",
        snapshot_then_mutate,
    )

    with pytest.raises(
        BOUNDARY.ContractValidationError,
        match="bytes changed while they were being sealed",
    ):
        BOUNDARY.seal_pilot_output_directory(
            output_path,
            expected_roles=expected_roles,
            local_run_root=tmp_path,
            repository_root=ROOT,
        )

    assert artifact_was_mutated


def test_output_boundary_rejects_unsorted_receipts(tmp_path: Path) -> None:
    output_path, expected_roles = _complete_output(tmp_path)
    receipts = BOUNDARY.seal_pilot_output_directory(
        output_path,
        expected_roles=expected_roles,
        local_run_root=tmp_path,
        repository_root=ROOT,
    )
    receipts.reverse()

    with pytest.raises(
        BOUNDARY.ContractValidationError,
        match="must be sorted by unique role",
    ):
        BOUNDARY.validate_pilot_output_receipts(
            receipts,
            output_path,
            local_run_root=tmp_path,
            repository_root=ROOT,
        )
