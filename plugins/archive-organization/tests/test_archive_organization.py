from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = ROOT / "plugins" / "archive-organization"
STUDIO_SCRIPTS = ROOT / "plugins" / "studio-archive" / "scripts"


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


if str(STUDIO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(STUDIO_SCRIPTS))

ledger = _load_module(
    "archive_organization_test_client_ledger",
    STUDIO_SCRIPTS / "client_ledger.py",
)
drive_adapter = _load_module(
    "google_drive",
    STUDIO_SCRIPTS / "google_drive.py",
)
organizer = _load_module(
    "archive_organization_test_core",
    PLUGIN_ROOT / "scripts" / "archive_organization.py",
)
core = organizer
review_contract = _load_module(
    "archive_organization_review_contract_validator",
    ROOT / "scripts" / "validate_plugin_review_contract.py",
)


class FakeDriveGateway:
    """In-memory Drive v3 boundary with stable IDs and increasing versions."""

    def __init__(self) -> None:
        self._next_folder = 1
        self.files: dict[str, dict[str, object]] = {
            "root_123": self._metadata(
                "root_123",
                "Example Client",
                drive_adapter.DRIVE_FOLDER_MIME_TYPE,
                parents=[],
            ),
            "file_pdf_1": self._metadata(
                "file_pdf_1",
                "Comunicazione 36bis.pdf",
                "application/pdf",
                parents=["root_123"],
                size="21",
                md5Checksum="a" * 32,
                sha256Checksum="b" * 64,
            ),
            "file_doc_1": self._metadata(
                "file_doc_1",
                "Verbale assemblea",
                "application/vnd.google-apps.document",
                parents=["root_123"],
            ),
        }

    @staticmethod
    def _metadata(
        file_id: str,
        name: str,
        mime_type: str,
        *,
        parents: list[str],
        **extra: object,
    ) -> dict[str, object]:
        return {
            "id": file_id,
            "name": name,
            "mimeType": mime_type,
            "parents": parents,
            "driveId": "shared_drive_1",
            "modifiedTime": "2026-08-09T12:00:00Z",
            "version": "1",
            "trashed": False,
            "capabilities": {
                "canEdit": True,
                "canDownload": True,
                "canMoveItemWithinDrive": True,
            },
            **extra,
        }

    def get_file(self, file_id: str) -> dict[str, object]:
        return deepcopy(self.files[file_id])

    def list_children(self, parent_id: str) -> list[dict[str, object]]:
        return [
            deepcopy(item)
            for item in self.files.values()
            if item.get("parents") == [parent_id] and item.get("trashed") is not True
        ]

    def create_folder(self, parent_id: str, name: str) -> dict[str, object]:
        file_id = f"folder_{self._next_folder}"
        self._next_folder += 1
        item = self._metadata(
            file_id,
            name,
            drive_adapter.DRIVE_FOLDER_MIME_TYPE,
            parents=[parent_id],
        )
        self.files[file_id] = item
        return deepcopy(item)

    def move_file(
        self,
        file_id: str,
        *,
        old_parent_id: str,
        new_parent_id: str,
        new_name: str,
    ) -> dict[str, object]:
        item = self.files[file_id]
        assert item["parents"] == [old_parent_id]
        item["parents"] = [new_parent_id]
        item["name"] = new_name
        item["version"] = str(int(str(item["version"])) + 1)
        return deepcopy(item)

    def download_bytes(self, file_id: str) -> bytes:
        return f"Binary evidence for {file_id}".encode()

    def export_bytes(self, file_id: str, mime_type: str) -> bytes:
        assert mime_type == "text/plain"
        return f"Exported Google document evidence for {file_id}".encode()


class _FakeGoogleRequest:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response

    def execute(self) -> dict[str, object]:
        return deepcopy(self.response)


class _FakeGoogleService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def files(self) -> _FakeGoogleService:
        return self

    def list(self, **kwargs: object) -> _FakeGoogleRequest:
        self.calls.append(("list", kwargs))
        return _FakeGoogleRequest({"files": [], "incompleteSearch": False})

    def update(self, **kwargs: object) -> _FakeGoogleRequest:
        self.calls.append(("update", kwargs))
        return _FakeGoogleRequest(
            {
                "id": kwargs["fileId"],
                "name": kwargs["body"]["name"],
                "mimeType": "application/pdf",
                "parents": [kwargs["addParents"]],
                "driveId": "shared_drive_1",
                "size": "1",
                "modifiedTime": "2026-08-09T12:00:00Z",
                "version": "2",
                "trashed": False,
                "capabilities": {
                    "canEdit": True,
                    "canDownload": True,
                    "canMoveItemWithinDrive": True,
                },
            }
        )

    def get_media(self, **kwargs: object) -> _FakeGoogleRequest:
        self.calls.append(("get_media", kwargs))
        return _FakeGoogleRequest({})


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _prepared_run(tmp_path: Path) -> tuple[Path, dict[str, object], dict[str, bytes]]:
    client_root = tmp_path / "Example Client"
    client_root.mkdir()
    original_files = {
        "Comunicazione_36bis_2024.pdf": b"same exact document bytes",
        "inbox/Comunicazione_36bis_copia.pdf": b"same exact document bytes",
        "notes.txt": b"uncertain internal note",
    }
    for relative, content in original_files.items():
        path = client_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    client_id = "client_" + "a" * 24
    ledger.create_client_manifest(client_root, client_id)
    engagement = ledger.create_engagement(client_root, client_id, "Archive cleanup")
    snapshot = ledger.snapshot_client_folder(
        client_root,
        client_id,
        engagement["engagement_id"],
    )
    prepared = ledger.prepare_run(
        client_root,
        client_id,
        engagement["engagement_id"],
        "archive-organization",
        "0.1.0",
        input_ids=[snapshot["input_id"]],
    )
    running = ledger.start_run(
        client_root,
        engagement["engagement_id"],
        prepared["run"]["run_id"],
    )
    return Path(running["context_path"]), snapshot["snapshot"], original_files


def _proposals(
    tmp_path: Path,
    snapshot: dict[str, object],
    *,
    category: str = "ade",
) -> Path:
    rows = []
    for item in snapshot["files"]:
        relative = item["relative_path"]
        if relative == "notes.txt":
            rows.append(
                {
                    "relative_path": relative,
                    "category_id": "da-classificare",
                    "document_type": None,
                    "document_date": None,
                    "entity": None,
                    "reference": None,
                    "practice": None,
                    "confidence": "low",
                    "reason": "The note has no supported filing context.",
                    "probable_duplicate_of": None,
                    "anomalies": ["classification_uncertain"],
                }
            )
        else:
            rows.append(
                {
                    "relative_path": relative,
                    "category_id": category,
                    "document_type": "comunicazione-36-bis",
                    "document_date": "2024-06-14",
                    "entity": "Example-Srl",
                    "reference": None,
                    "practice": "36-bis",
                    "confidence": "high",
                    "reason": "Readable document evidence identifies an AdE 36-bis communication.",
                    "probable_duplicate_of": None,
                    "anomalies": [],
                }
            )
    path = tmp_path / "proposals.json"
    _write_json(
        path,
        {
            "schema_version": "vera.archive_organization_proposals.v1",
            "client_id": snapshot["client_id"],
            "snapshot_sha256": snapshot["content_sha256"],
            "proposals": rows,
        },
    )
    return path


def _prepared_drive_run(
    tmp_path: Path,
) -> tuple[Path, dict[str, object], FakeDriveGateway]:
    client_root = tmp_path / "Drive Client Ledger"
    client_root.mkdir()
    client_id = "client_" + "c" * 24
    ledger.create_client_manifest(client_root, client_id)
    engagement = ledger.create_engagement(client_root, client_id, "Drive cleanup")
    gateway = FakeDriveGateway()
    snapshot = drive_adapter.snapshot_google_drive_folder(
        gateway,
        "root_123",
        client_id,
        engagement["engagement_id"],
    )
    snapshot_path = tmp_path / "drive-snapshot.json"
    _write_json(snapshot_path, snapshot)
    imported = ledger.import_document(
        client_root,
        client_id,
        engagement["engagement_id"],
        snapshot_path,
        "source",
    )
    prepared = ledger.prepare_run(
        client_root,
        client_id,
        engagement["engagement_id"],
        "archive-organization",
        "0.1.0",
        input_ids=[imported["receipt"]["input_id"]],
    )
    running = ledger.start_run(
        client_root,
        engagement["engagement_id"],
        prepared["run"]["run_id"],
    )
    return Path(running["context_path"]), snapshot, gateway


def _review_and_approve(
    context_path: Path,
    tmp_path: Path,
    review_result: dict[str, object],
) -> dict[str, object]:
    review_payload = json.loads(Path(review_result["review_payload_path"]).read_text())
    decisions_path = tmp_path / "decisions.json"
    _write_json(
        decisions_path,
        {
            "reviewer": "collaboratore-example",
            "decision_source": "pytest",
            "decisions": [
                {"item_id": item["id"], "action": "accept"}
                for item in review_payload["items"]
            ],
        },
    )
    saved = organizer.persist_review_decisions(context_path, decisions_path)
    return organizer.compile_approved_plan(
        context_path,
        Path(saved["ui_decisions_path"]),
    )


def test_review_apply_and_rollback_preserve_bytes(tmp_path: Path) -> None:
    context_path, snapshot, original_files = _prepared_run(tmp_path)
    review = core.build_review_package(
        context_path,
        _proposals(tmp_path, snapshot),
    )
    approved = _review_and_approve(context_path, tmp_path, review)
    output_dir = Path(review["output_dir"])
    for artifact_name in (
        "run_intake.json",
        "review_payload.json",
        "ui_decisions.json",
        "final_artifacts.json",
    ):
        assert (output_dir / artifact_name).is_file()
    contract_report = review_contract.validate_contract(output_dir)
    assert contract_report.ok, contract_report.errors

    applied = organizer.apply_approved_plan(
        context_path,
        Path(approved["approved_plan_path"]),
        explicit_approval=True,
    )

    assert applied["status"] == "applied"
    assert applied["applied_count"] == 2
    client_root = context_path.parents[5]
    assert not (client_root / "Comunicazione_36bis_2024.pdf").exists()
    assert (
        client_root / "AdE/2024/36-bis/2024-06-14_comunicazione-36-bis_Example-Srl.pdf"
    ).read_bytes() == original_files["Comunicazione_36bis_2024.pdf"]
    quarantine = list((client_root / "Da_verificare/Duplicati_esatti").rglob("*.pdf"))
    assert len(quarantine) == 1
    assert (
        quarantine[0].read_bytes()
        == original_files["inbox/Comunicazione_36bis_copia.pdf"]
    )
    assert (client_root / "notes.txt").read_bytes() == original_files["notes.txt"]

    rolled_back = organizer.rollback_applied_plan(context_path)

    assert rolled_back["status"] == "rolled_back"
    for relative, content in original_files.items():
        assert (client_root / relative).read_bytes() == content


def test_apply_requires_distinct_explicit_approval(tmp_path: Path) -> None:
    context_path, snapshot, _ = _prepared_run(tmp_path)
    review = organizer.build_review_package(
        context_path,
        _proposals(tmp_path, snapshot),
    )
    approved = _review_and_approve(context_path, tmp_path, review)

    with pytest.raises(
        organizer.ArchiveOrganizationError,
        match="Explicit apply approval",
    ):
        organizer.apply_approved_plan(
            context_path,
            Path(approved["approved_plan_path"]),
            explicit_approval=False,
        )


def test_apply_rejects_approved_plan_that_differs_from_review(tmp_path: Path) -> None:
    context_path, snapshot, _ = _prepared_run(tmp_path)
    review = organizer.build_review_package(
        context_path,
        _proposals(tmp_path, snapshot),
    )
    approved = _review_and_approve(context_path, tmp_path, review)
    approved_path = Path(approved["approved_plan_path"])
    payload = json.loads(approved_path.read_text(encoding="utf-8"))
    moving = next(
        item for item in payload["items"] if item["approved_action"] == "move"
    )
    moving["approved_target_relative_path"] = "Contratti/forged.pdf"
    content = {key: value for key, value in payload.items() if key != "content_sha256"}
    payload["content_sha256"] = hashlib.sha256(
        json.dumps(
            content,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    tampered = tmp_path / "tampered-approved-plan.json"
    _write_json(tampered, payload)

    with pytest.raises(
        organizer.ArchiveOrganizationError,
        match="differs from persisted review decisions",
    ):
        organizer.apply_approved_plan(
            context_path,
            tampered,
            explicit_approval=True,
        )


def test_apply_rejects_source_changed_after_review(tmp_path: Path) -> None:
    context_path, snapshot, _ = _prepared_run(tmp_path)
    review = organizer.build_review_package(
        context_path,
        _proposals(tmp_path, snapshot),
    )
    approved = _review_and_approve(context_path, tmp_path, review)
    client_root = context_path.parents[5]
    changed = client_root / "Comunicazione_36bis_2024.pdf"
    changed.write_bytes(b"changed after professional review")

    with pytest.raises(
        organizer.ArchiveOrganizationError,
        match="Source changed after review",
    ):
        organizer.apply_approved_plan(
            context_path,
            Path(approved["approved_plan_path"]),
            explicit_approval=True,
        )

    assert changed.read_bytes() == b"changed after professional review"
    assert not (client_root / "AdE").exists()


def test_edited_target_rejects_ledger_escape(tmp_path: Path) -> None:
    context_path, snapshot, _ = _prepared_run(tmp_path)
    review = organizer.build_review_package(
        context_path,
        _proposals(tmp_path, snapshot),
    )
    review_payload = json.loads(Path(review["review_payload_path"]).read_text())
    decisions_path = tmp_path / "unsafe-decisions.json"
    _write_json(
        decisions_path,
        {
            "reviewer": "collaboratore-example",
            "decisions": [
                {
                    "item_id": review_payload["items"][0]["id"],
                    "action": "edit",
                    "edit_value": "Vera/unsafe.pdf",
                }
            ],
        },
    )

    with pytest.raises(
        organizer.ArchiveOrganizationError,
        match="cannot target Vera",
    ):
        organizer.persist_review_decisions(context_path, decisions_path)


def test_snapshot_excludes_symlink_and_vera_ledger(tmp_path: Path) -> None:
    client_root = tmp_path / "Client"
    client_root.mkdir()
    source = client_root / "source.txt"
    source.write_text("source", encoding="utf-8")
    link = client_root / "linked.txt"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("symbolic links are unavailable on this filesystem")
    client_id = "client_" + "b" * 24
    ledger.create_client_manifest(client_root, client_id)
    engagement = ledger.create_engagement(client_root, client_id, "Snapshot")

    result = ledger.snapshot_client_folder(
        client_root,
        client_id,
        engagement["engagement_id"],
    )

    assert [item["relative_path"] for item in result["snapshot"]["files"]] == [
        "source.txt"
    ]
    assert result["snapshot"]["excluded"] == [
        {"relative_path": "linked.txt", "reason": "symbolic_link"}
    ]


def test_google_drive_apply_and_rollback_preserve_file_ids(tmp_path: Path) -> None:
    context_path, snapshot, gateway = _prepared_drive_run(tmp_path)
    review = organizer.build_review_package(
        context_path,
        _proposals(tmp_path, snapshot, category="ade"),
    )
    approved = _review_and_approve(context_path, tmp_path, review)

    applied = organizer.apply_approved_plan(
        context_path,
        Path(approved["approved_plan_path"]),
        explicit_approval=True,
        drive_gateway=gateway,
    )

    assert applied["status"] == "applied"
    assert applied["storage_kind"] == "google_drive"
    assert gateway.files["file_pdf_1"]["id"] == "file_pdf_1"
    assert gateway.files["file_pdf_1"]["parents"] != ["root_123"]
    assert gateway.files["file_doc_1"]["parents"] != ["root_123"]

    rolled_back = organizer.rollback_applied_plan(
        context_path,
        drive_gateway=gateway,
    )

    assert rolled_back["status"] == "rolled_back"
    assert gateway.files["file_pdf_1"]["parents"] == ["root_123"]
    assert gateway.files["file_pdf_1"]["name"] == "Comunicazione 36bis.pdf"
    assert gateway.files["file_doc_1"]["parents"] == ["root_123"]
    assert gateway.files["file_doc_1"]["name"] == "Verbale assemblea"


def test_google_drive_apply_rejects_changed_version(tmp_path: Path) -> None:
    context_path, snapshot, gateway = _prepared_drive_run(tmp_path)
    review = organizer.build_review_package(
        context_path,
        _proposals(tmp_path, snapshot, category="ade"),
    )
    approved = _review_and_approve(context_path, tmp_path, review)
    gateway.files["file_pdf_1"]["version"] = "2"

    with pytest.raises(
        organizer.ArchiveOrganizationError,
        match="Google Drive source changed after review",
    ):
        organizer.apply_approved_plan(
            context_path,
            Path(approved["approved_plan_path"]),
            explicit_approval=True,
            drive_gateway=gateway,
        )

    assert gateway.files["file_pdf_1"]["parents"] == ["root_123"]


def test_google_api_gateway_uses_shared_drive_flags_and_parent_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _FakeGoogleService()
    gateway = drive_adapter.GoogleApiDriveGateway(service)
    monkeypatch.setattr(gateway, "_download", lambda request: b"evidence")

    assert gateway.list_children("parent_123") == []
    moved = gateway.move_file(
        "file_123",
        old_parent_id="parent_123",
        new_parent_id="target_123",
        new_name="renamed.pdf",
    )
    assert gateway.download_bytes("file_123") == b"evidence"

    list_call = service.calls[0]
    update_call = service.calls[1]
    download_call = service.calls[2]
    assert list_call[1]["supportsAllDrives"] is True
    assert list_call[1]["includeItemsFromAllDrives"] is True
    assert update_call[1]["supportsAllDrives"] is True
    assert update_call[1]["addParents"] == "target_123"
    assert update_call[1]["removeParents"] == "parent_123"
    assert download_call[1]["supportsAllDrives"] is True
    assert moved["id"] == "file_123"
