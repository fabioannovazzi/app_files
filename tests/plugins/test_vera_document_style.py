"""Exercise private approval lifecycles and real Studio Archive draft bindings."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "plugins/vera/scripts/document_style.py"


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


style = load_module("test_vera_document_style_helper", SCRIPT)


def proposal(instruction: str = "Present facts before objections.") -> dict[str, Any]:
    return {
        "scope": "Responses of this selected type only.",
        "conventions": [
            {
                "kind": "structure",
                "instruction": instruction,
                "source_id": "E1",
                "locator": "Opening paragraph",
                "reason": "Observed in the selected example.",
            }
        ],
        "excluded_case_content": "Do not reuse prior facts or legal conclusions.",
    }


def teaching(tmp_path: Path) -> tuple[Path, Path, str, dict[str, Any]]:
    workspace = tmp_path / "personal-style"
    style.initialize(workspace, "Professional A")
    example = tmp_path / "example.md"
    example.write_text("PRIVATE OLD CASE 123: facts, followed by objections.")
    session = style.prepare(
        workspace, "response", "Selected response", "it", [example]
    )["payload"]["session_id"]
    proposed = style.propose(workspace, session, proposal())
    return workspace, example, session, proposed


def approved(tmp_path: Path) -> tuple[Path, Path]:
    workspace, example, session, proposed = teaching(tmp_path)
    style.approve(workspace, session, proposed["sha256"], "Professional A", True)
    return workspace, example


def case_run(tmp_path: Path) -> tuple[Path, Path]:
    ledger = load_module(
        "test_style_client_ledger",
        ROOT / "plugins/studio-archive/scripts/client_ledger.py",
    )
    client = tmp_path / "client"
    client.mkdir(parents=True)
    client_id = "client_111111111111111111111111"
    ledger.create_client_manifest(client, client_id)
    engagement = ledger.create_engagement(client, client_id, "New case")
    source = tmp_path / "current-case.txt"
    source.write_text("New case evidence only.")
    imported = ledger.import_document(
        client, client_id, engagement["engagement_id"], source, "source"
    )
    prepared = ledger.prepare_run(
        client,
        client_id,
        engagement["engagement_id"],
        "prompt-optimizer",
        "test-version",
        input_ids=[imported["receipt"]["input_id"]],
    )
    running = ledger.start_run(
        client, engagement["engagement_id"], prepared["run"]["run_id"]
    )
    return Path(running["context"]["context_path"]), Path(running["output_dir"])


def assessment(status: str = "conforms") -> dict[str, Any]:
    return {
        "style_application": {"status": status, "reason": "Facts precede objections."},
        "case_facts_and_authorities": {
            "status": "conforms",
            "reason": "Draft uses only supplied new-case facts; no legal claims.",
        },
        "no_prior_case_carryover": {
            "status": "conforms",
            "reason": "Old case 123 does not appear in the new draft.",
        },
    }


def test_unapproved_proposal_is_not_an_active_profile(tmp_path: Path) -> None:
    workspace, example, session, _ = teaching(tmp_path)

    result = style.list_profiles(workspace)

    assert result == []
    assert (workspace / "sessions" / session / "proposal.md").is_file()
    assert example.read_text().startswith("PRIVATE OLD CASE")


def test_approved_profile_survives_helper_reinstallation(tmp_path: Path) -> None:
    workspace, _ = approved(tmp_path)
    replacement = tmp_path / "replacement.py"
    shutil.copyfile(SCRIPT, replacement)
    updated = load_module("test_reinstalled_style", replacement)

    result = updated.list_profiles(workspace)

    assert result == [
        {
            "profile_id": "response",
            "document_type": "Selected response",
            "language": "it",
            "version": 1,
            "active": True,
        }
    ]


def test_two_workspaces_do_not_share_preferences(tmp_path: Path) -> None:
    workspace, _ = approved(tmp_path)
    other = tmp_path / "other"
    style.initialize(other, "Professional B")

    result = style.list_profiles(other)

    assert result == []
    assert style.list_profiles(workspace)[0]["version"] == 1


@pytest.mark.parametrize("confirmation,digest", [(False, "correct"), (True, "wrong")])
def test_approval_requires_confirmation_of_exact_proposal(
    tmp_path: Path, confirmation: bool, digest: str
) -> None:
    workspace, _, session, proposed = teaching(tmp_path)
    selected = proposed["sha256"] if digest == "correct" else "wrong"

    with pytest.raises(ValueError, match="approval|changed"):
        style.approve(workspace, session, selected, "Professional A", confirmation)


def test_revised_proposal_invalidates_previously_displayed_digest(
    tmp_path: Path,
) -> None:
    workspace, _, session, proposed = teaching(tmp_path)
    style.propose(workspace, session, proposal("Use shorter paragraphs."))

    with pytest.raises(ValueError, match="changed"):
        style.approve(workspace, session, proposed["sha256"], "Professional A", True)


def test_parallel_teaching_session_cannot_overwrite_new_approval(
    tmp_path: Path,
) -> None:
    workspace, example, session, proposed = teaching(tmp_path)
    other = style.prepare(workspace, "response", "Selected response", "it", [example])[
        "payload"
    ]["session_id"]
    competing = style.propose(workspace, other, proposal("Use shorter paragraphs."))
    style.approve(workspace, session, proposed["sha256"], "Professional A", True)

    with pytest.raises(ValueError, match="Stale"):
        style.approve(workspace, other, competing["sha256"], "Professional A", True)


def test_correction_creates_new_revision_and_preserves_original(tmp_path: Path) -> None:
    workspace, example = approved(tmp_path)
    first = (workspace / "profiles/response/v0001.json").read_bytes()
    session = style.prepare(
        workspace, "response", "Selected response", "it", [example]
    )["payload"]["session_id"]
    changed = style.propose(workspace, session, proposal("Use short paragraphs."))

    result = style.approve(
        workspace, session, changed["sha256"], "Professional A", True
    )

    assert result["payload"]["version"] == 2
    assert (workspace / "profiles/response/v0001.json").read_bytes() == first


@pytest.mark.parametrize(
    "field,value",
    [("kind", "legal_position"), ("source_id", "missing"), ("reason", "")],
)
def test_proposal_rejects_invalid_mechanical_evidence_shape(
    tmp_path: Path, field: str, value: str
) -> None:
    workspace, _, session, _ = teaching(tmp_path)
    candidate = proposal()
    candidate["conventions"][0][field] = value

    with pytest.raises(ValueError):
        style.propose(workspace, session, candidate)


def test_modified_selected_snapshot_blocks_approval(tmp_path: Path) -> None:
    workspace, _, session, proposed = teaching(tmp_path)
    (workspace / "sessions" / session / "examples/E1.md").write_text("Changed")

    with pytest.raises(ValueError, match="example changed"):
        style.approve(workspace, session, proposed["sha256"], "Professional A", True)


def test_workspace_rejects_unannounced_move(tmp_path: Path) -> None:
    workspace, _ = approved(tmp_path)
    moved = tmp_path / "moved"
    workspace.rename(moved)

    with pytest.raises(ValueError, match="moved"):
        style.list_profiles(moved)


def test_workspace_rejects_plugin_location(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    (plugin / ".codex-plugin").mkdir(parents=True)

    with pytest.raises(ValueError, match="outside"):
        style.initialize(plugin / "style", "Professional")


def test_workspace_does_not_adopt_nonempty_directory(tmp_path: Path) -> None:
    (tmp_path / "existing.txt").write_text("Existing work")

    with pytest.raises(ValueError, match="empty"):
        style.initialize(tmp_path, "Professional")


def test_symlink_example_is_rejected(tmp_path: Path) -> None:
    workspace, example = approved(tmp_path)
    link = tmp_path / "link.md"
    link.symlink_to(example)

    with pytest.raises(ValueError, match="Symlink"):
        style.prepare(workspace, "response", "Selected response", "it", [link])


def test_busy_workspace_does_not_remove_other_writer_lock(tmp_path: Path) -> None:
    workspace, example = approved(tmp_path)
    lock = workspace / ".writer-lock"
    lock.mkdir()

    with pytest.raises(ValueError, match="busy"):
        style.prepare(workspace, "response", "Selected response", "it", [example])
    assert lock.is_dir()


def test_real_managed_case_receives_only_approved_instructions(tmp_path: Path) -> None:
    workspace, _ = approved(tmp_path)
    context, output = case_run(tmp_path)

    result = style.attach(
        workspace, "response", context, output, "Selected response", "it"
    )

    assert result["payload"]["version"] == 1
    assert result["payload"]["conventions"] == [
        {"kind": "structure", "instruction": "Present facts before objections."}
    ]
    assert "PRIVATE OLD CASE" not in json.dumps(result)
    assert "locator" not in json.dumps(result)
    assert not (output / "examples").exists()


@pytest.mark.parametrize(
    "document_type,language",
    [("Different response", "it"), ("Selected response", "en")],
)
def test_wrong_document_type_or_language_cannot_reuse_profile(
    tmp_path: Path, document_type: str, language: str
) -> None:
    workspace, _ = approved(tmp_path)
    context, output = case_run(tmp_path)

    with pytest.raises(ValueError, match="does not match"):
        style.attach(workspace, "response", context, output, document_type, language)


def test_disabled_profile_cannot_be_attached(tmp_path: Path) -> None:
    workspace, _ = approved(tmp_path)
    style.disable(workspace, "response", "Professional A", True)
    context, output = case_run(tmp_path)

    with pytest.raises(ValueError, match="No active"):
        style.attach(workspace, "response", context, output, "Selected response", "it")
    assert (workspace / "profiles/response/v0001.json").is_file()


def test_profile_copy_from_another_workspace_is_rejected(tmp_path: Path) -> None:
    workspace, _ = approved(tmp_path)
    other = tmp_path / "other"
    style.initialize(other, "Professional B")
    shutil.copytree(workspace / "profiles", other / "profiles")
    context, output = case_run(tmp_path)

    with pytest.raises(ValueError, match="another workspace"):
        style.attach(other, "response", context, output, "Selected response", "it")


def test_review_verification_detects_post_review_edit(tmp_path: Path) -> None:
    workspace, _ = approved(tmp_path)
    context, output = case_run(tmp_path)
    style.attach(workspace, "response", context, output, "Selected response", "it")
    draft = output / "answer.md"
    draft.write_text("New case facts. Objections.")
    style.record_review(context, output, draft, assessment())
    draft.write_text("Changed after review.")

    with pytest.raises(ValueError, match="changed"):
        style.verify_review(context, output)


def test_unresolved_review_is_saved_but_not_verified(tmp_path: Path) -> None:
    workspace, _ = approved(tmp_path)
    context, output = case_run(tmp_path)
    style.attach(workspace, "response", context, output, "Selected response", "it")
    draft = output / "answer.md"
    draft.write_text("New case facts. Objections.")
    style.record_review(context, output, draft, assessment("needs_review"))

    with pytest.raises(ValueError, match="still needs"):
        style.verify_review(context, output)


def test_cross_client_style_binding_is_rejected(tmp_path: Path) -> None:
    workspace, _ = approved(tmp_path)
    context, output = case_run(tmp_path / "first")
    style.attach(workspace, "response", context, output, "Selected response", "it")
    other_context, other_output = case_run(tmp_path / "second")
    shutil.copyfile(
        output / "document_style.json", other_output / "document_style.json"
    )
    draft = other_output / "answer.md"
    draft.write_text("Other case")

    with pytest.raises(ValueError, match="another case"):
        style.record_review(other_context, other_output, draft, assessment())


def test_cli_teaching_through_verified_draft(tmp_path: Path) -> None:
    workspace = tmp_path / "style"
    assert (
        style.main(["init", "--workspace", str(workspace), "--owner", "Professional"])
        == 0
    )
    example = tmp_path / "example.md"
    example.write_text("Facts. Objections.")
    common = ["--workspace", str(workspace)]
    assert (
        style.main(
            [
                "prepare",
                *common,
                "--profile",
                "response",
                "--document-type",
                "Selected response",
                "--example",
                str(example),
            ]
        )
        == 0
    )
    session = next((workspace / "sessions").iterdir()).name
    candidate = tmp_path / "candidate.json"
    candidate.write_text(json.dumps(proposal()))
    assert (
        style.main(
            ["propose", *common, "--session", session, "--input", str(candidate)]
        )
        == 0
    )
    proposed = json.loads(
        (workspace / "sessions" / session / "proposal.json").read_text()
    )
    assert (
        style.main(
            [
                "approve",
                *common,
                "--session",
                session,
                "--proposal-sha256",
                proposed["sha256"],
                "--reviewer",
                "Professional",
                "--confirmed-by-user",
            ]
        )
        == 0
    )
    assert style.main(["list", *common]) == 0
    context, output = case_run(tmp_path)
    run_args = ["--client-engagement", str(context), "--output-dir", str(output)]
    assert (
        style.main(
            [
                "attach",
                *common,
                *run_args,
                "--profile",
                "response",
                "--document-type",
                "Selected response",
            ]
        )
        == 0
    )
    draft = output / "answer.md"
    draft.write_text("New facts. Objections.")
    review = output / "assessment.json"
    review.write_text(json.dumps(assessment()))
    assert (
        style.main(
            ["review", *run_args, "--document", str(draft), "--input", str(review)]
        )
        == 0
    )
    assert style.main(["verify", *run_args]) == 0
    assert (
        style.main(
            [
                "disable",
                *common,
                "--profile",
                "response",
                "--reviewer",
                "Professional",
                "--confirmed-by-user",
            ]
        )
        == 0
    )
    assert (
        style.main(
            [
                "attach",
                *common,
                *run_args,
                "--profile",
                "response",
                "--document-type",
                "Selected response",
            ]
        )
        == 1
    )


def test_cli_requires_arguments() -> None:
    with pytest.raises(SystemExit, match="2"):
        style.main(["init"])


def test_teaching_cannot_live_in_a_client_folder(tmp_path: Path) -> None:
    _, output = case_run(tmp_path)

    with pytest.raises(ValueError, match="outside"):
        style.initialize(output / "personal-style", "Professional")


def test_repeated_attach_preserves_the_same_snapshot(tmp_path: Path) -> None:
    workspace, _ = approved(tmp_path)
    context, output = case_run(tmp_path)
    first = style.attach(
        workspace, "response", context, output, "Selected response", "it"
    )

    result = style.attach(
        workspace, "response", context, output, "Selected response", "it"
    )

    assert result == first


def test_new_profile_revision_does_not_overwrite_existing_case(tmp_path: Path) -> None:
    workspace, example = approved(tmp_path)
    context, output = case_run(tmp_path)
    style.attach(workspace, "response", context, output, "Selected response", "it")
    session = style.prepare(
        workspace, "response", "Selected response", "it", [example]
    )["payload"]["session_id"]
    changed = style.propose(workspace, session, proposal("Short paragraphs."))
    style.approve(workspace, session, changed["sha256"], "Professional A", True)

    with pytest.raises(ValueError, match="already bound"):
        style.attach(workspace, "response", context, output, "Selected response", "it")
    assert (
        json.loads((output / "document_style.json").read_text())["payload"]["version"]
        == 1
    )


@pytest.mark.parametrize(
    "archive_name",
    ["vera-plugin.zip", "vera-chatgpt-upload.zip", "vera-claude-plugin.zip"],
)
def test_packaged_helper_attaches_with_its_own_vendored_runtime(
    tmp_path: Path, archive_name: str
) -> None:
    workspace, _ = approved(tmp_path)
    context, output = case_run(tmp_path)
    installation = tmp_path / "installation"
    with ZipFile(ROOT / "plugin_packages/vera" / archive_name) as archive:
        script_name = next(
            name
            for name in archive.namelist()
            if name.endswith("scripts/document_style.py")
        )
        prefix = script_name.removesuffix("scripts/document_style.py")
        for name in archive.namelist():
            if name.endswith("/"):
                continue
            relative = name.removeprefix(prefix)
            if relative == "scripts/document_style.py" or relative.startswith(
                "vendor/modules/vera_assurance/"
            ):
                target = installation / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))

    result = subprocess.run(
        [
            sys.executable,
            str(installation / "scripts/document_style.py"),
            "attach",
            "--workspace",
            str(workspace),
            "--profile",
            "response",
            "--client-engagement",
            str(context),
            "--output-dir",
            str(output),
            "--document-type",
            "Selected response",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (
        json.loads((output / "document_style.json").read_text())["payload"]["version"]
        == 1
    )
