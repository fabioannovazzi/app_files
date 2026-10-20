"""External updates must not invalidate the worker's packaged isolation policy."""

from __future__ import annotations

import ast
import hashlib
import os
import platform
import re
from pathlib import Path
from typing import Any

import pytest

from tests.plugins.test_journal_bank_reconciliation_plugin import load_semantic_review


def test_product_sources_do_not_reintroduce_external_runtime_pin_constants() -> None:
    """Lint mechanically named release pins across production plugin scripts."""
    root = Path(__file__).resolve().parents[2] / "plugins"
    forbidden = re.compile(
        r"(?:PINNED|EXPECTED|REQUIRED|QUALIFIED)_"
        r"(?:CODEX|DARWIN|MACOS|SANDBOX_EXEC|CAT)_(?:VERSION|SHA256|BUILD)$"
    )
    violations = []
    for path in root.rglob("*.py"):
        if "scripts" not in path.parts or set(path.parts) & {
            "vendor",
            "node_modules",
            "tests",
            "assets",
        }:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            targets = (
                node.targets
                if isinstance(node, ast.Assign)
                else [node.target] if isinstance(node, ast.AnnAssign) else []
            )
            for target in targets:
                if isinstance(target, ast.Name) and forbidden.fullmatch(target.id):
                    violations.append(
                        (str(path.relative_to(root)), node.lineno, target.id)
                    )

    assert violations == []


def test_current_policy_has_no_external_runtime_identity_pins() -> None:
    """Prevent a future release from freezing another developer's installation."""
    semantic = load_semantic_review()
    profile = semantic._resolve_host_profile()

    assert profile.provenance == "runtime_verified"
    assert profile.darwin_build is None
    assert profile.codex_version is None
    assert profile.codex_sha256 is None
    assert profile.sandbox_exec_sha256 is None
    assert profile.canary_sha256 is None
    assert (
        profile.seatbelt_sha256
        == hashlib.sha256(semantic.SEATBELT_PROFILE.encode()).hexdigest()
    )


@pytest.mark.parametrize("payload", [b"updated Codex", b"future system executable"])
def test_updated_executable_is_snapshotted_without_release_allowlist(
    tmp_path: Path, payload: bytes
) -> None:
    semantic = load_semantic_review()
    executable = tmp_path / "runtime"
    executable.write_bytes(payload)
    executable.chmod(0o700)

    binding = semantic._stable_executable_binding(executable, label="runtime")

    assert binding["sha256"] == hashlib.sha256(payload).hexdigest()
    assert binding["byte_count"] == len(payload)


def test_executable_change_during_execution_remains_rejected(tmp_path: Path) -> None:
    semantic = load_semantic_review()
    executable = tmp_path / "runtime"
    executable.write_bytes(b"before")
    executable.chmod(0o700)
    before = semantic._stable_executable_binding(executable, label="runtime")
    executable.write_bytes(b"changed")

    with pytest.raises(ValueError, match="qualified executable"):
        semantic._stable_executable_binding(
            executable, label="runtime", expected_sha256=before["sha256"]
        )


@pytest.mark.parametrize("build", ["26A429", "27B999", "99Z999a"])
def test_new_macos_build_is_observed_without_build_allowlist(
    monkeypatch: pytest.MonkeyPatch, build: str
) -> None:
    semantic = load_semantic_review()
    monkeypatch.setattr(semantic, "_observed_darwin_build", lambda: build)

    assert semantic._darwin_build_version() == build


@pytest.mark.parametrize(
    ("replies", "error"),
    [
        (
            [(0, b"{}"), (0, b"outside data")],
            "did not deny the outside-read canary",
        ),
        (
            [(0, b"{}"), (1, b""), (0, b"codex-cli 9.0.0"), (2, b"unknown argument")],
            "rejected required isolated-worker arguments",
        ),
        ([(1, b"")], "did not permit the exact schema canary"),
        (
            [(0, b"{}"), (1, b""), (1, b"")],
            "could not report its version inside isolation",
        ),
        (
            [(0, b"{}"), (1, b""), (0, b"\xff")],
            "version output is not UTF-8",
        ),
    ],
)
def test_runtime_updates_do_not_bypass_failed_boundary_or_missing_capabilities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replies: list[tuple[int, bytes]],
    error: str,
) -> None:
    semantic = load_semantic_review()
    responses = iter(replies)

    def run(*args: Any, **kwargs: Any) -> dict[str, Any]:
        status, stdout = next(responses)
        return {"return_code": status, "stdout": stdout, "stderr": b""}

    monkeypatch.setattr(semantic, "_run_captured_process", run)
    monkeypatch.setattr(semantic, "_seatbelt_prefix", lambda **kwargs: ["sandbox"])

    with pytest.raises(ValueError, match=error):
        semantic._qualification_canaries(
            semantic_dir=tmp_path,
            profile_path=tmp_path / "policy",
            schema_path=tmp_path / "schema",
            schema_bytes=b"{}",
            capsule=tmp_path,
            state_dir=tmp_path,
            log_dir=tmp_path,
            boundary_inputs={},
            executables={
                "host_profile": semantic._resolve_host_profile(),
                "codex_path": Path("/new/codex"),
            },
        )


def test_missing_runtime_executable_has_a_specific_diagnostic(tmp_path: Path) -> None:
    semantic = load_semantic_review()

    with pytest.raises(ValueError, match="does not exist"):
        semantic._stable_executable_binding(tmp_path / "missing", label="Codex CLI")


@pytest.mark.parametrize(
    "version", ["0.163.0-alpha.10.2", "1.0.0", "99.1.2+new", "next (development)"]
)
def test_new_codex_version_passes_live_boundary_and_capability_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    semantic = load_semantic_review()
    profile = semantic._resolve_host_profile()
    schema = tmp_path / "schema.json"
    schema.write_bytes(b"{}")
    capsule = tmp_path / "capsule"
    capsule.mkdir()
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: Any) -> dict[str, Any]:
        calls.append(command)
        if command[-1] == str(schema):
            return {"return_code": 0, "stdout": b"{}", "stderr": b""}
        if ".luna-outside-canary." in command[-1]:
            return {"return_code": 1, "stdout": b"", "stderr": b"denied"}
        if command[-1] == "--version":
            return {
                "return_code": 0,
                "stdout": f"codex-cli {version}".encode(),
                "stderr": b"",
            }
        return {
            "return_code": 0,
            "stdout": b"Help wording may change; supported flags may be hidden.",
            "stderr": b"",
        }

    monkeypatch.setattr(semantic, "_run_captured_process", run)
    monkeypatch.setattr(semantic, "_seatbelt_prefix", lambda **kwargs: ["sandbox"])

    result = semantic._qualification_canaries(
        semantic_dir=tmp_path,
        profile_path=tmp_path / "seatbelt.sb",
        schema_path=schema,
        schema_bytes=b"{}",
        capsule=capsule,
        state_dir=capsule,
        log_dir=capsule,
        boundary_inputs={},
        executables={"host_profile": profile, "codex_path": Path("/new/codex")},
    )

    assert result["codex_version_inside_boundary"] == f"codex-cli {version}"
    assert result["required_cli_capabilities_available"] is True
    assert len(calls) == 4
    assert calls[-1][-1] == "--help"
    assert "--ignore-user-config" in calls[-1]
    assert "--ignore-rules" in calls[-1]
    assert calls[-1][calls[-1].index("--sandbox") + 1] == "read-only"


@pytest.mark.skipif(
    platform.system() != "Darwin" or os.environ.get("VERA_TEST_NATIVE_RUNTIME") != "1",
    reason="Opt-in native macOS integration requires permission to launch Seatbelt",
)
def test_native_current_runtime_isolation_without_model_or_credentials(
    tmp_path: Path,
) -> None:
    """Exercise current real binaries; never load user auth or call a model."""
    semantic = load_semantic_review()
    codex = os.environ.get("VERA_TEST_CODEX_BIN")
    executables = semantic._qualified_executables(Path(codex) if codex else None)
    capsule = tmp_path / "capsule"
    capsule.mkdir(mode=0o700)
    state = capsule / "state"
    state.mkdir()
    logs = capsule / "logs"
    logs.mkdir()
    schema = capsule / "schema.json"
    schema.write_bytes(b"{}")
    policy = capsule / "seatbelt.sb"
    policy.write_text(semantic.SEATBELT_PROFILE)
    home = tmp_path / "synthetic-home"
    home.mkdir()
    auth = home / "auth.json"
    auth.write_text("{}")
    installation = home / "installation_id"
    installation.write_text("00000000-0000-4000-8000-000000000001")

    result = semantic._qualification_canaries(
        semantic_dir=tmp_path,
        profile_path=policy,
        schema_path=schema,
        schema_bytes=b"{}",
        capsule=capsule,
        state_dir=state,
        log_dir=logs,
        boundary_inputs={
            "codex_home": home,
            "installation_id_path": installation,
            "global_agents_path": home / "AGENTS.md",
            "global_agents_override_path": home / "AGENTS.override.md",
            "auth_path": auth,
        },
        executables=executables,
    )

    assert result["exact_schema_read_succeeded"] is True
    assert result["outside_capsule_read_denied"] is True
    assert result["required_cli_capabilities_available"] is True
    assert result["codex_version_inside_boundary"].startswith("codex-cli ")
