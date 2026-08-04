from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from typing import Any

import pytest

from tests.plugins._financial_analysis_test_loader import (
    load_financial_analysis_scripts,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = ROOT / "plugins" / "financial-analysis" / "scripts"
FINANCIAL_SCRIPTS = load_financial_analysis_scripts(SCRIPT_ROOT)
kernel = FINANCIAL_SCRIPTS.kernel
fdd_runner = FINANCIAL_SCRIPTS.fdd_runner
pack_runner = FINANCIAL_SCRIPTS.pack_runner

FIXTURES = runpy.run_path(
    str(ROOT / "tests" / "plugins" / "test_vera_fdd_machinery.py")
)


def _case_bundle(
    tmp_path: Path,
    *,
    reported_ebitda: str = "1000",
) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    context = FIXTURES["_context"](tmp_path)
    case = FIXTURES["_build_case"](
        context,
        pack_id="quality_of_earnings",
        inputs=FIXTURES["_qoe_inputs"](reported=reported_ebitda),
    )
    bundle_path = tmp_path / "case.json"
    bundle_path.write_text(
        json.dumps(FIXTURES["_bundle"](case), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return bundle_path, tmp_path / "source.txt"


def _output_names(output_dir: Path) -> set[str]:
    return {path.name for path in output_dir.iterdir()}


def test_fdd_success_is_deterministic_and_delivers_complete_receipts(
    tmp_path: Path,
) -> None:
    bundle_path, _ = _case_bundle(tmp_path)
    case_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    first = pack_runner.run_pack(
        pack_id="quality_of_earnings",
        case_path=bundle_path,
        output_dir=first_dir,
    )
    second = pack_runner.run_pack(
        pack_id="quality_of_earnings",
        case_path=bundle_path,
        output_dir=second_dir,
    )

    expected_implementations = {
        "scripts/managed_case_inputs.py",
        "scripts/prepare_fdd_case.py",
        "scripts/preparation_contract_kernel.py",
        "scripts/run_pack.py",
        "scripts/validate_case_contracts.py",
        "modules/vera_assurance/__init__.py",
        "modules/vera_assurance/contracts.py",
        "modules/vera_assurance/decisions.py",
        "modules/vera_assurance/envelope.py",
        "modules/vera_assurance/money.py",
        "modules/vera_assurance/relationships.py",
        "modules/vera_assurance/serialization.py",
        "modules/vera_financial_analysis/__init__.py",
        "modules/vera_financial_analysis/contracts.py",
        "modules/vera_financial_analysis/fdd.py",
        "modules/vera_financial_analysis/registry.py",
    }
    assert first == second
    assert first["schema_version"] == "vera.financial_analysis_pack_execution.v3"
    assert first["case_sha256"] == case_sha256
    assert {
        item["path"] for item in first["implementation_files"]
    } == expected_implementations
    assert all(item["byte_count"] > 0 for item in first["implementation_files"])
    assert "financial_analysis_contract_audit.json" in _output_names(first_dir)
    assert {item["path"] for item in first["output_artifacts"]} == _output_names(
        first_dir
    ) - {"pack_execution_receipt.json"}
    for name in _output_names(first_dir):
        assert (first_dir / name).read_bytes() == (second_dir / name).read_bytes()


def test_fdd_reconciliation_and_manifest_ids_include_case_freshness(
    tmp_path: Path,
) -> None:
    first_bundle, _ = _case_bundle(
        tmp_path / "first-case",
        reported_ebitda="1000",
    )
    second_bundle, _ = _case_bundle(
        tmp_path / "second-case",
        reported_ebitda="1001",
    )
    first_output = tmp_path / "first-output"
    second_output = tmp_path / "second-output"

    pack_runner.run_pack(
        pack_id="quality_of_earnings",
        case_path=first_bundle,
        output_dir=first_output,
    )
    pack_runner.run_pack(
        pack_id="quality_of_earnings",
        case_path=second_bundle,
        output_dir=second_output,
    )
    first_reconciliation = json.loads(
        (first_output / "reconciliation.json").read_text(encoding="utf-8")
    )
    second_reconciliation = json.loads(
        (second_output / "reconciliation.json").read_text(encoding="utf-8")
    )
    first_manifest = json.loads(
        (first_output / "prepared_evidence_manifest.json").read_text(encoding="utf-8")
    )
    second_manifest = json.loads(
        (second_output / "prepared_evidence_manifest.json").read_text(encoding="utf-8")
    )
    first_result = json.loads(
        (first_output / "fdd_result.json").read_text(encoding="utf-8")
    )

    assert (
        first_reconciliation["reconciliation_id"]
        != second_reconciliation["reconciliation_id"]
    )
    assert first_manifest["manifest_id"] != second_manifest["manifest_id"]
    assert first_result["case_sha256"] in first_reconciliation["reconciliation_id"]
    assert first_result["case_sha256"] in first_manifest["manifest_id"]


def test_fdd_runner_rejects_late_unregistered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle_path, _ = _case_bundle(tmp_path)
    output_dir = tmp_path / "output"
    original_spec = pack_runner.PACKS["quality_of_earnings"]

    def runner_with_extra_output(
        case_path: Path,
        requested_output_dir: Path,
        *,
        output_boundary: kernel.PinnedDirectory | None = None,
    ) -> dict[str, Any]:
        assert output_boundary is not None
        result = original_spec.runner(
            case_path,
            requested_output_dir,
            output_boundary=output_boundary,
        )
        output_boundary.write_json_exclusive(
            "unregistered_extra.json",
            {"unexpected": True},
        )
        return result

    monkeypatch.setitem(
        pack_runner.PACKS,
        "quality_of_earnings",
        original_spec._replace(runner=runner_with_extra_output),
    )

    with pytest.raises(pack_runner.PackRunError, match="unsupported entry"):
        pack_runner.run_pack(
            pack_id="quality_of_earnings",
            case_path=bundle_path,
            output_dir=output_dir,
        )

    assert _output_names(output_dir) == set()


def test_fdd_output_directory_substitution_cannot_redirect_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle_path, _ = _case_bundle(tmp_path)
    output_dir = tmp_path / "output"
    substituted_target = tmp_path / "substituted-target"
    substituted_target.mkdir()
    original_mkdir = Path.mkdir

    def substitute_output_with_symlink(
        path: Path,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        if path == output_dir.absolute():
            path.symlink_to(substituted_target, target_is_directory=True)
            return
        original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", substitute_output_with_symlink)

    with pytest.raises(ValueError, match="pin output directory"):
        pack_runner.run_pack(
            pack_id="quality_of_earnings",
            case_path=bundle_path,
            output_dir=output_dir,
        )

    assert output_dir.is_symlink()
    assert _output_names(substituted_target) == set()


def test_fdd_case_path_substitution_cannot_redirect_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle_path, _ = _case_bundle(tmp_path)
    output_dir = tmp_path / "output"
    original_bundle = tmp_path / "original-case.json"
    substituted_bundle = tmp_path / "substituted-case.json"
    substituted_bundle.write_bytes(bundle_path.read_bytes())
    original_snapshot = pack_runner.file_snapshot_beneath
    substituted = False

    def substitute_case_then_snapshot(
        path: Path,
        *,
        root: Path,
    ) -> tuple[int, str]:
        nonlocal substituted
        if path == bundle_path.absolute() and not substituted:
            bundle_path.rename(original_bundle)
            bundle_path.symlink_to(substituted_bundle)
            substituted = True
        return original_snapshot(path, root=root)

    monkeypatch.setattr(
        pack_runner,
        "file_snapshot_beneath",
        substitute_case_then_snapshot,
    )

    with pytest.raises(ValueError, match="safely open file"):
        pack_runner.run_pack(
            pack_id="quality_of_earnings",
            case_path=bundle_path,
            output_dir=output_dir,
        )

    assert _output_names(output_dir) == set()


def test_fdd_case_change_after_execution_fails_and_cleans_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle_path, _ = _case_bundle(tmp_path)
    output_dir = tmp_path / "output"
    original_output_receipts = pack_runner._output_receipts

    def mutate_case_then_snapshot(
        output_boundary: kernel.PinnedDirectory,
        *,
        track: bool,
    ) -> list[dict[str, Any]]:
        bundle_path.write_text('{"changed":"after execution"}\n', encoding="utf-8")
        return original_output_receipts(output_boundary, track=track)

    monkeypatch.setattr(
        pack_runner,
        "_output_receipts",
        mutate_case_then_snapshot,
    )

    with pytest.raises(pack_runner.PackRunError, match="case file changed"):
        pack_runner.run_pack(
            pack_id="quality_of_earnings",
            case_path=bundle_path,
            output_dir=output_dir,
        )

    assert _output_names(output_dir) == set()


def test_fdd_implementation_change_after_execution_fails_and_cleans_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle_path, _ = _case_bundle(tmp_path)
    output_dir = tmp_path / "output"
    mutable_implementation = tmp_path / "mutable_implementation.py"
    mutable_implementation.write_text("VERSION = 1\n", encoding="utf-8")
    original_spec = pack_runner.PACKS["quality_of_earnings"]
    monkeypatch.setitem(
        pack_runner.PACKS,
        "quality_of_earnings",
        original_spec._replace(
            implementation_files=(
                *original_spec.implementation_files[:-1],
                mutable_implementation,
            )
        ),
    )
    original_output_receipts = pack_runner._output_receipts

    def mutate_implementation_then_snapshot(
        output_boundary: kernel.PinnedDirectory,
        *,
        track: bool,
    ) -> list[dict[str, Any]]:
        mutable_implementation.write_text("VERSION = 2\n", encoding="utf-8")
        return original_output_receipts(output_boundary, track=track)

    monkeypatch.setattr(
        pack_runner,
        "_output_receipts",
        mutate_implementation_then_snapshot,
    )

    with pytest.raises(pack_runner.PackRunError, match="implementation files changed"):
        pack_runner.run_pack(
            pack_id="quality_of_earnings",
            case_path=bundle_path,
            output_dir=output_dir,
        )

    assert _output_names(output_dir) == set()


def test_fdd_source_change_during_execution_fails_and_cleans_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle_path, source_path = _case_bundle(tmp_path)
    output_dir = tmp_path / "output"
    original_execute = fdd_runner.execute_fdd_case
    changed = False

    def mutate_source_then_execute(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal changed
        if not changed:
            source_path.write_text("changed during execution\n", encoding="utf-8")
            changed = True
        return original_execute(*args, **kwargs)

    monkeypatch.setattr(
        fdd_runner,
        "execute_fdd_case",
        mutate_source_then_execute,
    )

    with pytest.raises(ValueError, match="source .* changed during execution"):
        pack_runner.run_pack(
            pack_id="quality_of_earnings",
            case_path=bundle_path,
            output_dir=output_dir,
        )

    assert _output_names(output_dir) == set()


def test_fdd_target_symlink_race_never_overwrites_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle_path, source_path = _case_bundle(tmp_path)
    output_dir = tmp_path / "output"
    original_source = source_path.read_bytes()
    original_write = kernel.PinnedDirectory.write_json_exclusive
    injected = False

    def inject_symlink_then_write(
        boundary: kernel.PinnedDirectory,
        name: str,
        value: dict[str, Any],
    ) -> None:
        nonlocal injected
        if name == "fdd_result.json" and not injected:
            (boundary.path / name).symlink_to(source_path)
            injected = True
        original_write(boundary, name, value)

    monkeypatch.setattr(
        kernel.PinnedDirectory,
        "write_json_exclusive",
        inject_symlink_then_write,
    )

    with pytest.raises(ValueError, match="exclusively create"):
        pack_runner.run_pack(
            pack_id="quality_of_earnings",
            case_path=bundle_path,
            output_dir=output_dir,
        )

    assert source_path.read_bytes() == original_source
    assert _output_names(output_dir) == {"fdd_result.json"}
    assert (output_dir / "fdd_result.json").is_symlink()


def test_fdd_partial_write_failure_removes_created_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle_path, _ = _case_bundle(tmp_path)
    output_dir = tmp_path / "output"
    original_write = kernel.PinnedDirectory.write_json_exclusive

    def fail_second_output(
        boundary: kernel.PinnedDirectory,
        name: str,
        value: dict[str, Any],
    ) -> None:
        if name == "fdd_metrics.json":
            raise OSError("simulated write failure")
        original_write(boundary, name, value)

    monkeypatch.setattr(
        kernel.PinnedDirectory,
        "write_json_exclusive",
        fail_second_output,
    )

    with pytest.raises(OSError, match="simulated write failure"):
        pack_runner.run_pack(
            pack_id="quality_of_earnings",
            case_path=bundle_path,
            output_dir=output_dir,
        )

    assert _output_names(output_dir) == set()
