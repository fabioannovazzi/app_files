from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = PLUGIN_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import delivery_manifest
from delivery_manifest import (
    DeliveryValidationError,
    seal_delivery,
    validate_delivery,
)

RUN_ID = "new-client-202607271024100000-30baf3156efc"
STALE_RUN_ID = "new-client-202607271021290000-30baf3156efc"


def _write_private(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def _register_source_files(output_dir: Path) -> None:
    source_dir = output_dir / "source-evidence"
    evidence_register = [
        {
            "evidence_id": f"ev-{index:03d}",
            "local_path": path.relative_to(output_dir).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "status": "available",
        }
        for index, path in enumerate(sorted(source_dir.rglob("*")), start=1)
        if path.is_file()
    ]
    input_path = output_dir / "new_client_input.json"
    _write_private(input_path, json.dumps({"evidence_register": evidence_register}))
    _write_private(
        output_dir / "run_intake.json",
        json.dumps(
            {
                "input": {
                    "sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
                }
            }
        ),
    )


@pytest.fixture
def delivery_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    output_dir = tmp_path / "delivery"
    output_dir.mkdir(mode=0o700)
    _write_private(
        output_dir / "final_artifacts.json",
        json.dumps({"run_id": RUN_ID}),
    )
    _write_private(output_dir / "run_review.md", f"Run ID: `{RUN_ID}`\n")
    _write_private(output_dir / "client_questions.md", "# Client questions\n")

    source_dir = output_dir / "source-evidence"
    source_dir.mkdir(mode=0o700)
    _write_private(
        source_dir / "client-note.txt",
        "Copied source evidence may mention Claude, Codex, OpenAI, or Anthropic.\n",
    )
    _register_source_files(output_dir)
    monkeypatch.setattr(
        delivery_manifest,
        "validate_contract",
        lambda _: {
            "status": "contract_validated_for_professional_review",
            "artifact_count": 15,
        },
    )
    return output_dir


def test_seal_delivery_binds_every_delivered_file(delivery_dir: Path) -> None:
    report = seal_delivery(delivery_dir)

    manifest = json.loads(
        (delivery_dir / "delivery_manifest.json").read_text(encoding="utf-8")
    )
    sealed_paths = {item["path"] for item in manifest["artifacts"]}

    assert report["status"] == "delivery_validated_for_professional_review"
    assert report["artifact_count"] == 6
    assert report["directory_count"] == 2
    assert sealed_paths == {
        "client_questions.md",
        "final_artifacts.json",
        "new_client_input.json",
        "run_review.md",
        "run_intake.json",
        "source-evidence/client-note.txt",
    }
    assert str(delivery_dir) not in json.dumps(manifest)


def test_seal_delivery_binds_nested_file_named_like_manifest(
    delivery_dir: Path,
) -> None:
    nested_dir = delivery_dir / "notes"
    nested_dir.mkdir(mode=0o700)
    _write_private(
        nested_dir / "delivery_manifest.json",
        json.dumps({"note": "Not the root delivery seal."}),
    )

    seal_delivery(delivery_dir)

    manifest = json.loads(
        (delivery_dir / "delivery_manifest.json").read_text(encoding="utf-8")
    )
    sealed_paths = {item["path"] for item in manifest["artifacts"]}
    assert "notes/delivery_manifest.json" in sealed_paths


def test_validate_delivery_rejects_tampered_supplement(
    delivery_dir: Path,
) -> None:
    seal_delivery(delivery_dir)
    _write_private(
        delivery_dir / "client_questions.md",
        "# Client questions\nChanged after sealing.\n",
    )

    with pytest.raises(
        DeliveryValidationError,
        match="Delivery (size|hash) receipt mismatch",
    ):
        validate_delivery(delivery_dir)


def test_seal_delivery_rejects_stale_supplemental_run_id(
    delivery_dir: Path,
) -> None:
    _write_private(
        delivery_dir / "run_review.md",
        f"Run ID: `{STALE_RUN_ID}`\n",
    )

    with pytest.raises(
        DeliveryValidationError,
        match="run IDs that do not match",
    ):
        seal_delivery(delivery_dir)


def test_seal_delivery_rejects_host_name_in_assistant_text(
    delivery_dir: Path,
) -> None:
    _write_private(
        delivery_dir / "client_questions.md",
        "Route beyond Claude: none.\n",
    )

    with pytest.raises(
        DeliveryValidationError,
        match="forbidden host/provider name",
    ):
        seal_delivery(delivery_dir)


def test_seal_delivery_rejects_non_private_file_mode(
    delivery_dir: Path,
) -> None:
    (delivery_dir / "client_questions.md").chmod(0o644)

    with pytest.raises(
        DeliveryValidationError,
        match="File must be mode 0600",
    ):
        seal_delivery(delivery_dir)


def test_seal_delivery_rejects_extensionless_stale_run_id(
    delivery_dir: Path,
) -> None:
    _write_private(delivery_dir / "review-note", f"Run ID: {STALE_RUN_ID}\n")

    with pytest.raises(
        DeliveryValidationError,
        match="run IDs that do not match",
    ):
        seal_delivery(delivery_dir)


def test_seal_delivery_rejects_json_escaped_host_name(
    delivery_dir: Path,
) -> None:
    _write_private(
        delivery_dir / "escaped.json",
        '{"route": "Clau\\u0064e"}',
    )

    with pytest.raises(
        DeliveryValidationError,
        match="forbidden host/provider name",
    ):
        seal_delivery(delivery_dir)


def test_seal_delivery_rejects_json_escaped_stale_run_id(
    delivery_dir: Path,
) -> None:
    escaped_run_id = STALE_RUN_ID.replace("-", "\\u002d")
    _write_private(
        delivery_dir / "escaped.json",
        json.dumps({"run_id": escaped_run_id}),
    )

    with pytest.raises(
        DeliveryValidationError,
        match="run IDs that do not match",
    ):
        seal_delivery(delivery_dir)


def test_seal_delivery_rejects_symlinked_root(
    delivery_dir: Path,
    tmp_path: Path,
) -> None:
    linked_root = tmp_path / "linked-delivery"
    linked_root.symlink_to(delivery_dir, target_is_directory=True)

    with pytest.raises(
        DeliveryValidationError,
        match="symbolic-link component|Delivery root must be a real directory",
    ):
        seal_delivery(linked_root)


def test_seal_delivery_rejects_symlinked_parent_component(
    delivery_dir: Path,
    tmp_path: Path,
) -> None:
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(tmp_path, target_is_directory=True)

    with pytest.raises(
        DeliveryValidationError,
        match="symbolic-link component",
    ):
        seal_delivery(linked_parent / delivery_dir.name)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("schema_version", "9.9", "schema_version"),
        ("status", "complete_and_signed", "status is invalid"),
        ("base_contract_status", "complete", "base_contract_status"),
        ("base_contract_artifact_count", 999, "base_contract_artifact_count"),
    ),
)
def test_validate_delivery_rejects_tampered_manifest_metadata(
    delivery_dir: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    seal_delivery(delivery_dir)
    manifest_path = delivery_dir / "delivery_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[field] = value
    _write_private(manifest_path, json.dumps(manifest))

    with pytest.raises(DeliveryValidationError, match=message):
        validate_delivery(delivery_dir)


def test_seal_delivery_allows_registered_source_filename_with_host_name(
    delivery_dir: Path,
) -> None:
    _write_private(
        delivery_dir / "source-evidence" / "Claude-client-source.txt",
        "Client-supplied source content.\n",
    )
    _register_source_files(delivery_dir)
    _write_private(
        delivery_dir / "case_facts_validated.json",
        json.dumps(
            {
                "evidence_verifications": [
                    {
                        "resolved_path": (
                            "/private/case/source-evidence/" "Claude-client-source.txt"
                        )
                    }
                ]
            }
        ),
    )

    report = seal_delivery(delivery_dir)

    assert report["status"] == "delivery_validated_for_professional_review"


def test_seal_delivery_rejects_unregistered_source_evidence(
    delivery_dir: Path,
) -> None:
    _write_private(
        delivery_dir / "source-evidence" / "unregistered.txt",
        "Not present in the evidence register.\n",
    )

    with pytest.raises(
        DeliveryValidationError,
        match="unregistered copied evidence",
    ):
        seal_delivery(delivery_dir)


def test_seal_delivery_rejects_missing_registered_source_evidence(
    delivery_dir: Path,
) -> None:
    _write_private(
        delivery_dir / "source-evidence" / "retained-note.txt",
        "Retained source evidence.\n",
    )
    _register_source_files(delivery_dir)
    (delivery_dir / "source-evidence" / "client-note.txt").unlink()

    with pytest.raises(
        DeliveryValidationError,
        match="missing copied evidence",
    ):
        seal_delivery(delivery_dir)


def test_seal_delivery_rejects_mutated_input_register_binding(
    delivery_dir: Path,
) -> None:
    input_path = delivery_dir / "new_client_input.json"
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    payload["evidence_register"].append(
        {
            "evidence_id": "ev-unbound",
            "local_path": "source-evidence/unbound.txt",
            "sha256": "0" * 64,
            "status": "available",
        }
    )
    _write_private(input_path, json.dumps(payload))

    with pytest.raises(
        DeliveryValidationError,
        match="sealed run_intake.json input hash",
    ):
        seal_delivery(delivery_dir)


def test_seal_delivery_rejects_source_path_inside_narrative(
    delivery_dir: Path,
) -> None:
    _write_private(
        delivery_dir / "narrative.json",
        json.dumps(
            {
                "path": (
                    "/source-evidence/client-note.txt Claude route " f"{STALE_RUN_ID}"
                )
            }
        ),
    )

    with pytest.raises(
        DeliveryValidationError,
        match="forbidden host/provider name",
    ):
        seal_delivery(delivery_dir)


def test_seal_delivery_rejects_duplicate_json_keys(
    delivery_dir: Path,
) -> None:
    _write_private(
        delivery_dir / "duplicate.json",
        '{"status":"Claude","status":"pending"}',
    )

    with pytest.raises(
        DeliveryValidationError,
        match="duplicate JSON key",
    ):
        seal_delivery(delivery_dir)


def test_validate_delivery_rejects_duplicate_manifest_keys(
    delivery_dir: Path,
) -> None:
    seal_delivery(delivery_dir)
    manifest_path = delivery_dir / "delivery_manifest.json"
    content = manifest_path.read_text(encoding="utf-8")
    content = content.replace(
        '"status": "delivery_sealed_for_professional_review"',
        (
            '"status": "complete_and_signed",\n'
            '  "status": "delivery_sealed_for_professional_review"'
        ),
    )
    _write_private(manifest_path, content)

    with pytest.raises(
        DeliveryValidationError,
        match="duplicate JSON key",
    ):
        validate_delivery(delivery_dir)


def test_seal_delivery_accepts_uppercase_registered_source_hash(
    delivery_dir: Path,
) -> None:
    input_path = delivery_dir / "new_client_input.json"
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    payload["evidence_register"][0]["sha256"] = payload["evidence_register"][0][
        "sha256"
    ].upper()
    _write_private(input_path, json.dumps(payload))
    _write_private(
        delivery_dir / "run_intake.json",
        json.dumps(
            {
                "input": {
                    "sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
                }
            }
        ),
    )

    report = seal_delivery(delivery_dir)

    assert report["status"] == "delivery_validated_for_professional_review"


def test_seal_delivery_rejects_empty_directory(
    delivery_dir: Path,
) -> None:
    (delivery_dir / STALE_RUN_ID).mkdir(mode=0o700)

    with pytest.raises(
        DeliveryValidationError,
        match="empty directory",
    ):
        seal_delivery(delivery_dir)


def test_seal_delivery_reports_malformed_utf8_final_artifacts(
    delivery_dir: Path,
) -> None:
    final_artifacts = delivery_dir / "final_artifacts.json"
    final_artifacts.write_bytes(b"\xff")
    final_artifacts.chmod(0o600)

    with pytest.raises(
        DeliveryValidationError,
        match="not valid UTF-8",
    ):
        seal_delivery(delivery_dir)
