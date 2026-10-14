"""Exercise mechanical research closure without assigning legal judgments."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from zipfile import ZipFile

import pytest

from tests.plugins.test_deep_research_validator_plugin import (
    _answer_contract,
    _claim_review,
    _claims_review,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "plugins/deep-research-validator/scripts/research_record.py"


@pytest.fixture
def research_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("research_record_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(root: Path, *, limited: bool = False) -> Path:
    root.mkdir(exist_ok=True)
    record = {
        "schema_version": "2.0",
        "method": "shared_agentic_legal_tax_research",
        "cycles": [
            {
                "id": "cycle-1",
                "purpose": "Check the condition governing the exemption.",
                "issue_ids": ["issue-1"],
                "findings": "The supplied provision conditions the exemption on test X.",
                "validation": "The draft omitted condition X; restore it.",
                "challenge": "The authority could deny entitlement if test X is unmet.",
            }
        ],
        "issues": [
            {
                "id": "issue-1",
                "question": "Does the evidence establish test X?",
                "status": "evidence_limited" if limited else "qualified",
                "cycle_ids": ["cycle-1"],
                "treatment": "The answer now makes entitlement conditional on test X.",
                "treatment_type": "qualification",
                "evidence": [],
                "effects": [],
                "dependencies": [],
                "dependency_review": "The answer remains conditional; there are no dependent claims.",
                "limits": ["Test X requires evidence from the client."],
            }
        ],
        "completion": {
            "status": "evidence_limited" if limited else "complete",
            "coverage_review": "The only contracted issue is treated conditionally.",
            "stopping_rationale": "Further available sources cannot establish client facts.",
            "limits": ["Missing client evidence."] if limited else [],
        },
    }
    (root / "answer.md").write_text("Entitlement requires test X.\n")
    (root / "answer_contract.json").write_text(
        json.dumps(_answer_contract(generation_route="codex_direct"))
    )
    (root / "claims_review.json").write_text(
        json.dumps(
            _claims_review(
                [_claim_review("Entitlement requires test X.")],
                validated_document="Entitlement requires test X.",
            )
        )
    )
    (root / "research_record.md").write_text("Examined the supplied provision.\n")
    (root / "source.txt").write_text("Entitlement requires test X.\n")
    (root / "document_inventory.json").write_text(
        json.dumps({"character_count": 28, "urls": []})
    )
    (root / "source_inventory.json").write_text(
        json.dumps({"sources": [{"source_id": "source-001", "status": "available"}]})
    )
    record["answer_revision_sha256"] = hashlib.sha256(
        (root / "answer.md").read_bytes()
    ).hexdigest()
    record["issues"][0]["evidence"] = [
        {
            "kind": "fact",
            "artifact": "source.txt",
            "sha256": hashlib.sha256((root / "source.txt").read_bytes()).hexdigest(),
            "start_char": 0,
            "end_char": len((root / "source.txt").read_text()),
        }
    ]
    record["issues"][0]["effects"] = [
        {
            "kind": "claim",
            "artifact": "claims_review.json",
            "sha256": hashlib.sha256(
                (root / "claims_review.json").read_bytes()
            ).hexdigest(),
            "claim_index": 1,
        }
    ]
    (root / "research_review.json").write_text(json.dumps(record))
    return root


def _bind(module: ModuleType, root: Path) -> dict[str, object]:
    return module.bind_research_record(
        root,
        answer="answer.md",
        answer_contract="answer_contract.json",
        review="claims_review.json",
        sources=["source.txt"],
    )


@pytest.mark.parametrize("limited", [False, True])
def test_bind_preserves_declared_limit_without_certifying_semantic_quality(
    tmp_path: Path, research_module: ModuleType, limited: bool
) -> None:
    root = _run(tmp_path, limited=limited)

    result = _bind(research_module, root)

    assert result == {
        "record_integrity": "verified",
        "declared_research_status": "evidence_limited" if limited else "complete",
        "semantic_quality": "not_certified_by_helper",
        "artifact_count": 7,
    }


@pytest.mark.parametrize(
    "artifact",
    [
        "answer.md",
        "answer_contract.json",
        "claims_review.json",
        "research_record.md",
        "source.txt",
    ],
)
def test_verify_rejects_change_to_an_artifact_after_review(
    tmp_path: Path, research_module: ModuleType, artifact: str
) -> None:
    root = _run(tmp_path)
    _bind(research_module, root)
    (root / artifact).write_text("Changed after review.")

    with pytest.raises(ValueError, match="Research artifact changed"):
        research_module.verify_research_record(root)


def test_verify_rejects_changed_stopping_rationale_without_rebinding(
    tmp_path: Path, research_module: ModuleType
) -> None:
    root = _run(tmp_path)
    _bind(research_module, root)
    path = root / "research_review.json"
    record = json.loads(path.read_text())
    record["completion"]["stopping_rationale"] = "A newly asserted reason."
    path.write_text(json.dumps(record))

    with pytest.raises(ValueError, match="Research record changed"):
        research_module.verify_research_record(root)


@pytest.mark.parametrize(
    ("section", "field", "value", "error"),
    [
        ("issues", "status", "open", "Open research issue"),
        ("issues", "status", "invented_status", "Invalid declared issue status"),
        ("issues", "treatment", "", "Missing research explanation"),
        ("issues", "limits", [], "Declared issue limits missing"),
        ("issues", "cycle_ids", ["missing-cycle"], "Unresolved issue cycle"),
        ("cycles", "issue_ids", ["missing-issue"], "Unresolved cycle issue"),
        ("cycles", "validation", "", "Missing research explanation"),
        ("cycles", "challenge", "", "Missing research explanation"),
        ("completion", "status", "interrupted", "in progress or interrupted"),
        ("completion", "status", "in_progress", "in progress or interrupted"),
        ("completion", "coverage_review", "", "Missing research explanation"),
    ],
)
def test_bind_rejects_unresolved_or_incomplete_declared_work_without_writing(
    tmp_path: Path,
    research_module: ModuleType,
    section: str,
    field: str,
    value: object,
    error: str,
) -> None:
    root = _run(tmp_path)
    path = root / "research_review.json"
    record = json.loads(path.read_text())
    target = record[section] if section == "completion" else record[section][0]
    target[field] = value
    path.write_text(json.dumps(record))
    before = path.read_bytes()

    with pytest.raises(ValueError, match=error):
        _bind(research_module, root)

    assert path.read_bytes() == before


def test_bind_rejects_declared_complete_research_with_evidence_limited_issue(
    tmp_path: Path, research_module: ModuleType
) -> None:
    root = _run(tmp_path, limited=True)
    path = root / "research_review.json"
    record = json.loads(path.read_text())
    record["completion"]["status"] = "complete"
    path.write_text(json.dumps(record))

    with pytest.raises(ValueError, match="conflicts with complete research"):
        _bind(research_module, root)


@pytest.mark.parametrize("section", ["cycles", "issues"])
def test_bind_rejects_duplicate_identifiers(
    tmp_path: Path, research_module: ModuleType, section: str
) -> None:
    root = _run(tmp_path)
    path = root / "research_review.json"
    record = json.loads(path.read_text())
    record[section].append(record[section][0])
    path.write_text(json.dumps(record))

    with pytest.raises(ValueError, match="Duplicate research identifier"):
        _bind(research_module, root)


@pytest.mark.parametrize("source", ["../outside.txt", "/tmp/outside.txt"])
def test_bind_rejects_source_outside_review_run(
    tmp_path: Path, research_module: ModuleType, source: str
) -> None:
    root = _run(tmp_path)

    with pytest.raises(ValueError, match="Invalid research artifact path"):
        research_module.bind_research_record(
            root,
            answer="answer.md",
            answer_contract="answer_contract.json",
            review="claims_review.json",
            sources=[source],
        )


def test_bind_rejects_symlink_source_without_modifying_record(
    tmp_path: Path, research_module: ModuleType
) -> None:
    root = _run(tmp_path / "run")
    outside = tmp_path / "outside.txt"
    outside.write_text("Outside case data.")
    (root / "source.txt").unlink()
    (root / "source.txt").symlink_to(outside)
    before = (root / "research_review.json").read_bytes()

    with pytest.raises(ValueError, match="Symlink research artifact rejected"):
        _bind(research_module, root)

    assert (root / "research_review.json").read_bytes() == before


def test_verify_is_read_only(tmp_path: Path, research_module: ModuleType) -> None:
    root = _run(tmp_path)
    _bind(research_module, root)
    before = {path.name: path.read_bytes() for path in root.iterdir()}

    research_module.verify_research_record(root)

    assert {path.name: path.read_bytes() for path in root.iterdir()} == before


def test_bind_rejects_omitted_cycle_from_issue_history(
    tmp_path: Path, research_module: ModuleType
) -> None:
    root = _run(tmp_path)
    path = root / "research_review.json"
    record = json.loads(path.read_text())
    second = dict(record["cycles"][0], id="final-review-feedback")
    record["cycles"].append(second)
    path.write_text(json.dumps(record))

    with pytest.raises(ValueError, match="Cycle treatment missing from issue history"):
        _bind(research_module, root)


@pytest.mark.parametrize(
    "role", ["answer", "answer_contract", "review", "research_log"]
)
def test_verify_rejects_missing_required_artifact_binding(
    tmp_path: Path, research_module: ModuleType, role: str
) -> None:
    root = _run(tmp_path)
    _bind(research_module, root)
    path = root / "research_review.json"
    record = json.loads(path.read_text())
    record["binding"]["artifacts"] = [
        item for item in record["binding"]["artifacts"] if item["role"] != role
    ]
    path.write_text(json.dumps(record))

    with pytest.raises(ValueError, match="Required research artifact role missing"):
        research_module.verify_research_record(root)


@pytest.mark.parametrize("action", ["bind", "verify"])
def test_cli_uses_managed_workflow_context_before_inspecting_or_writing_artifacts(
    tmp_path: Path,
    research_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    root = _run(tmp_path)
    if action == "verify":
        _bind(research_module, root)
    checks: list[dict[str, object]] = []

    def check_context(path: Path, **kwargs: object) -> None:
        assert path == root / "context.json"
        checks.append(kwargs)

    monkeypatch.setattr(
        research_module, "load_client_engagement_context_file", check_context
    )
    arguments = [
        str(SCRIPT),
        action,
        "--output-dir",
        str(root),
        "--client-engagement",
        str(root / "context.json"),
    ]
    if action == "bind":
        arguments += [
            "--answer",
            "answer.md",
            "--answer-contract",
            "answer_contract.json",
            "--review",
            "claims_review.json",
            "--source-file",
            "source.txt",
        ]
    monkeypatch.setattr(sys, "argv", arguments)

    result = research_module.main()

    assert result == 0
    assert checks == [
        {
            "expected_workflow_id": "deep-research-validator",
            "input_paths": [root / "research_review.json"],
            "output_dir": root,
            "allowed_statuses": (
                ("running",)
                if action == "bind"
                else ("running", "ready_for_review", "completed")
            ),
        }
    ]


def test_cli_context_rejection_does_not_write_binding(
    tmp_path: Path, research_module: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _run(tmp_path)
    path = root / "research_review.json"
    before = path.read_bytes()

    def reject_context(*args: object, **kwargs: object) -> None:
        raise ValueError("Context belongs to another engagement")

    monkeypatch.setattr(
        research_module, "load_client_engagement_context_file", reject_context
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "bind",
            "--output-dir",
            str(root),
            "--client-engagement",
            str(root / "context.json"),
            "--answer",
            "answer.md",
            "--answer-contract",
            "answer_contract.json",
            "--review",
            "claims_review.json",
        ],
    )

    with pytest.raises(SystemExit) as error:
        research_module.main()

    assert error.value.code == 2
    assert path.read_bytes() == before


@pytest.mark.parametrize("product", ["vera", "lucia"])
@pytest.mark.parametrize("host", ["plugin", "chatgpt-upload", "claude-plugin"])
def test_packaged_research_helper_loads_without_checkout_dependencies(
    tmp_path: Path, product: str, host: str
) -> None:
    archive_path = ROOT / "plugin_packages" / product / f"{product}-{host}.zip"
    with ZipFile(archive_path) as archive:
        archive.extractall(tmp_path)
    matches = list(
        tmp_path.glob("**/modules/deep-research-validator/scripts/research_record.py")
    )
    assert len(matches) == 1

    result = subprocess.run(
        [sys.executable, str(matches[0]), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--client-engagement" in result.stdout


@pytest.mark.parametrize(
    "field,value",
    [
        ("evidence", []),
        ("evidence", ["invented source"]),
        ("effects", []),
        ("dependencies", ["missing-issue"]),
        ("dependencies", ["issue-1"]),
        ("dependency_review", ""),
        ("treatment_type", "invented"),
    ],
)
def test_closure_rejects_missing_traceability_before_writing(
    tmp_path, research_module, field, value
):
    root = _run(tmp_path)
    path = root / "research_review.json"
    record = json.loads(path.read_text())
    record["issues"][0][field] = value
    path.write_text(json.dumps(record))
    before = path.read_bytes()
    with pytest.raises(ValueError):
        _bind(research_module, root)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "change",
    [
        "invented_claim",
        "old_effect",
        "old_answer",
        "unreviewed_answer",
        "unsupported_without_checks",
    ],
)
def test_closure_rejects_invalid_current_answer_treatment(
    tmp_path, research_module, change
):
    root = _run(tmp_path)
    path = root / "research_review.json"
    record = json.loads(path.read_text())
    if change == "invented_claim":
        record["issues"][0]["effects"][0]["claim_index"] = 99
    elif change == "old_effect":
        record["issues"][0]["effects"][0]["sha256"] = "0" * 64
    elif change == "old_answer":
        record["answer_revision_sha256"] = "0" * 64
    elif change == "unreviewed_answer":
        (root / "answer.md").write_text("A different conclusion.")
    else:
        review_path = root / "claims_review.json"
        review = json.loads(review_path.read_text())
        review["claims"][0]["source_checks"] = []
        review_path.write_text(json.dumps(review))
        record["issues"][0]["effects"][0]["sha256"] = hashlib.sha256(
            review_path.read_bytes()
        ).hexdigest()
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError):
        _bind(research_module, root)
    assert "binding" not in json.loads(path.read_text())
