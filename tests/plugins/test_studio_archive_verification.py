"""Verification uses public receipt readers, never guessed raw-ledger fields."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "plugins/studio-archive/scripts"


@pytest.fixture
def verification(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "input_verification", SCRIPTS / "input_verification.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def case(tmp_path, verification):
    root = tmp_path / "client"
    root.mkdir()
    ledger = verification.ledger
    client = ledger.create_client_manifest(root, "client_" + "1" * 24)
    cid = client["client_id"]
    eid = ledger.create_engagement(root, cid, "Synthetic verification")["engagement_id"]
    original = tmp_path / "note.md"
    original.write_bytes(b"Unapproved synthetic note. Payment evidence missing.\n")
    saved = ledger.import_document(root, cid, eid, original, "support")
    return root, cid, eid, saved["receipt"]


def baseline(receipt):
    return {key: receipt[key] for key in ("input_id", "content_sha256")}


def tree_bytes(root):
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_verifies_raw_receipts_without_hydrated_fields_and_preserves_every_file(
    verification, case
):
    root, cid, eid, receipt = case
    raw = json.loads((Path(receipt["path"]).parent / "receipt.json").read_text())
    before = tree_bytes(root)

    result = verification.verify_inputs(
        root,
        cid,
        eid,
        [receipt["input_id"]],
        expected_receipts=[baseline(receipt)],
        require_exact_input_set=True,
    )

    assert "relative_path" not in raw
    assert "imports" not in json.loads(
        (root / "Vera/engagements" / eid / "engagement.json").read_text()
    )
    assert result["verified"] is True
    assert result["input_set_matches"] is True
    assert result["inputs"][0]["receipt"] == receipt
    assert result["inputs"][0]["expected_receipt_matches"] is True
    assert result["source_archive_mutated"] is False
    assert result["document_contents_returned"] is False
    assert tree_bytes(root) == before


def test_without_baseline_does_not_claim_historical_preservation(verification, case):
    root, cid, eid, receipt = case

    result = verification.verify_inputs(root, cid, eid, [receipt["input_id"]])

    assert result["verified"] is True
    assert result["expected_receipts_checked"] is False
    assert result["inputs"][0]["expected_receipt_matches"] is None
    assert result["input_set_matches"] is None
    assert result["current_input_ids"] is None


@pytest.mark.parametrize(
    "damage", ["bytes", "missing_file", "receipt", "missing_receipt", "symlink"]
)
def test_reports_damaged_selected_input_without_repair(
    verification, case, tmp_path, damage
):
    root, cid, eid, receipt = case
    path = Path(receipt["path"])
    raw = path.parent / "receipt.json"
    if damage == "bytes":
        path.write_bytes(b"Changed controlled evidence")
    elif damage == "missing_file":
        path.unlink()
    elif damage == "receipt":
        data = json.loads(raw.read_text())
        data["role"] = "source"
        raw.write_text(json.dumps(data))
    elif damage == "missing_receipt":
        raw.unlink()
    else:
        outside = tmp_path / "outside.txt"
        outside.write_bytes(path.read_bytes())
        path.unlink()
        try:
            path.symlink_to(outside)
        except OSError:
            pytest.skip("Host does not permit creating symlinks")
    before = tree_bytes(root)

    result = verification.verify_inputs(
        root, cid, eid, [receipt["input_id"]], require_exact_input_set=True
    )

    assert result["status"] == "blocked"
    assert result["verified"] is False
    assert result["inputs"][0]["status"] == "failed"
    assert "receipt" not in result["inputs"][0]
    assert result["failures"][0]["code"] == "input_verification_failed"
    assert result["input_set_matches"] is False
    assert tree_bytes(root) == before


def test_wrong_baseline_is_not_accepted_as_preserved(verification, case):
    root, cid, eid, receipt = case
    expected = baseline(receipt) | {"content_sha256": "0" * 64}

    result = verification.verify_inputs(
        root, cid, eid, [receipt["input_id"]], expected_receipts=[expected]
    )

    assert result["verified"] is False
    assert result["inputs"][0]["controlled_bytes_match_receipt"] is True
    assert result["inputs"][0]["expected_receipt_matches"] is False
    assert result["failures"][0]["code"] == "expected_receipt_mismatch"


def test_exact_set_rejects_unselected_additional_input(verification, case, tmp_path):
    root, cid, eid, receipt = case
    new = tmp_path / "new.md"
    new.write_bytes(b"Separate continuation. No new bank evidence.")
    added = verification.ledger.import_document(root, cid, eid, new, "support")

    result = verification.verify_inputs(
        root, cid, eid, [receipt["input_id"]], require_exact_input_set=True
    )

    assert result["verified"] is False
    assert result["inputs"][0]["status"] == "verified"
    assert result["failures"][0]["code"] == "input_set_mismatch"
    assert result["failures"][0]["additional_input_ids"] == [
        added["receipt"]["input_id"]
    ]


def test_exact_set_reports_absent_selected_input(verification, case):
    root, cid, eid, receipt = case
    missing = "input_" + "0" * 24

    result = verification.verify_inputs(
        root, cid, eid, [receipt["input_id"], missing], require_exact_input_set=True
    )

    assert result["verified"] is False
    assert result["inputs"][0]["status"] == "verified"
    assert result["failures"][-1]["missing_input_ids"] == [missing]


def test_same_name_changed_note_and_exact_retry_keep_distinct_identity(
    verification, case, tmp_path
):
    root, cid, eid, first = case
    second_dir = tmp_path / "continuation"
    second_dir.mkdir()
    second = second_dir / "note.md"
    second.write_bytes(b"Version two; bank evidence is still missing.")
    imported = verification.ledger.import_document(root, cid, eid, second, "support")
    repeated = verification.ledger.import_document(root, cid, eid, second, "support")
    current = imported["receipt"]
    before = tree_bytes(root)

    result = verification.verify_inputs(
        root,
        cid,
        eid,
        [first["input_id"], current["input_id"]],
        expected_receipts=[baseline(first), baseline(current)],
        require_exact_input_set=True,
    )

    assert repeated["status"] == "already_imported"
    assert repeated["receipt"]["input_id"] == current["input_id"]
    assert current["input_id"] != first["input_id"]
    assert result["verified"] is True
    assert result["selected_input_count"] == 2
    assert result["inputs"][0]["receipt"]["original_name"] == current["original_name"]
    assert (
        hashlib.sha256(Path(first["path"]).read_bytes()).hexdigest() == first["sha256"]
    )
    assert tree_bytes(root) == before


@pytest.mark.parametrize(
    "selection", [None, [], "input_abc", ["bad"], ["input_" + "0" * 24] * 2, [None]]
)
def test_rejects_invalid_selection(verification, case, selection):
    root, cid, eid, _ = case
    with pytest.raises(verification.ledger.LedgerError, match="distinct exact"):
        verification.verify_inputs(root, cid, eid, selection)


@pytest.mark.parametrize(
    "expected", [[], {}, [None], [{"input_id": "foreign", "content_sha256": "0" * 64}]]
)
def test_rejects_incomplete_or_foreign_baseline(verification, case, expected):
    root, cid, eid, receipt = case
    with pytest.raises(verification.ledger.LedgerError, match="Expected receipts"):
        verification.verify_inputs(
            root, cid, eid, [receipt["input_id"]], expected_receipts=expected
        )


def test_rejects_foreign_client_and_nonboolean_scope(verification, case):
    root, _, eid, receipt = case
    with pytest.raises(verification.ledger.LedgerError, match="another client"):
        verification.verify_inputs(
            root, "client_" + "0" * 24, eid, [receipt["input_id"]]
        )
    with pytest.raises(verification.ledger.LedgerError, match="must be boolean"):
        verification.verify_inputs(
            root,
            "client_" + "0" * 24,
            eid,
            [receipt["input_id"]],
            require_exact_input_set="true",
        )


def test_refuses_receipt_changed_between_supported_reads(
    verification, case, monkeypatch
):
    root, cid, eid, receipt = case
    native = verification.ledger.load_input_receipt

    def changed(*args, **kwargs):
        result = native(*args, **kwargs)
        return (
            result | {"imported_names": ["changed.md"]}
            if kwargs.get("verify_bytes") is False
            else result
        )

    monkeypatch.setattr(verification.ledger, "load_input_receipt", changed)
    result = verification.verify_inputs(root, cid, eid, [receipt["input_id"]])

    assert result["verified"] is False
    assert "changed during verification" in result["failures"][0]["message"]
