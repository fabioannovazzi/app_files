from __future__ import annotations

import hashlib
import importlib.util
import json
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "previdenza-inps"
SCRIPT_PATH = PLUGIN_ROOT / "scripts" / "register_portal_export.py"
SCRIPTS_ROOT = SCRIPT_PATH.parent


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "previdenza_inps_register_portal_export", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_inventory_script() -> ModuleType:
    scripts_path = str(SCRIPTS_ROOT)
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    path = SCRIPTS_ROOT / "inventory_case.py"
    spec = importlib.util.spec_from_file_location(
        "previdenza_inps_portal_export_inventory", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _authority_kwargs() -> dict[str, object]:
    return {
        "source_origin": "https://www.inps.it",
        "authority_actor_id": "ACT-PORTAL-001",
        "authority_actor_role": "authorized_delegate",
        "authority_recorded_at": "2026-07-16T10:15:00+02:00",
        "authority_scope": "Read and export the authorized client's contribution records.",
        "human_authority_basis": "Explicit instruction recorded by the responsible professional.",
        "profile_authority_basis": "Access through the approved professional portal profile.",
        "delegation_authority_basis": "Active client delegation checked before the manual export.",
        "processing_approved_by_id": "REV-DATA-001",
        "processing_approved_by_role": "professional_reviewer",
        "processing_recorded_at": "2026-07-16T10:20:00+02:00",
        "processor_scope": "Local evidence registration and later professional case review.",
        "processing_approval_basis": "Studio processing approval for this bounded client case.",
        "confirm_human_authority": True,
        "confirm_profile_authority": True,
        "confirm_delegation_authority": True,
        "approve_client_data_processing": True,
        "confirm_user_downloaded_files": True,
    }


def _write_pdf(path: Path) -> Path:
    path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n")
    return path


def _register(
    module: ModuleType,
    source_files: list[Path],
    output_dir: Path,
    **overrides: object,
) -> Path:
    options = _authority_kwargs()
    options.update(overrides)
    return module.register_portal_exports(
        source_files,
        output_dir,
        **options,
    )


def test_register_portal_exports_writes_private_minimized_verified_manifest(
    tmp_path: Path,
) -> None:
    module = _load_script()
    sensitive_name = "TSTUSR80A01H501Z_estratto_contributivo.pdf"
    pdf_path = _write_pdf(tmp_path / sensitive_name)
    csv_path = tmp_path / "periodi.csv"
    csv_path.write_text("periodo,importo\n2025-01,100.00\n", encoding="utf-8")
    output_dir = tmp_path / "registered"

    manifest_path = _register(module, [pdf_path, csv_path], output_dir)
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)

    assert manifest_path == output_dir / "manifest.json"
    assert manifest["source_origin"] == "https://www.inps.it"
    assert manifest["authority"]["human_authority_confirmed"] is True
    assert manifest["authority"]["profile_authority_confirmed"] is True
    assert manifest["authority"]["delegation_authority_confirmed"] is True
    assert manifest["processing_approval"]["client_data_processing_approved"] is True
    assert manifest["safety"] == {
        "source_files_user_downloaded": True,
        "network_access_performed": False,
        "portal_automation_performed": False,
        "credentials_collected": False,
        "cookies_collected": False,
        "browser_profile_data_collected": False,
        "submission_performed": False,
    }
    assert sensitive_name not in manifest_text
    assert pdf_path.as_posix() not in manifest_text
    assert (
        manifest["artifacts"][0]["original_name_sha256"]
        == hashlib.sha256(sensitive_name.encode("utf-8")).hexdigest()
    )
    assert manifest["artifacts"][0]["stored_name"].startswith("inps-export-001-")
    assert manifest["artifacts"][0]["stored_name"].endswith(".pdf")
    assert set(path.name for path in output_dir.iterdir()) == {
        "manifest.json",
        manifest["artifacts"][0]["stored_name"],
        manifest["artifacts"][1]["stored_name"],
    }
    assert stat.S_IMODE(output_dir.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600 for path in output_dir.iterdir()
    )
    assert module.verify_portal_export(output_dir) == manifest


@pytest.mark.parametrize(
    ("filename", "content", "expected_suffix", "media_type"),
    (
        ("export.pdf", b"%PDF-1.7\n%%EOF\n", ".pdf", "application/pdf"),
        ("export.csv", b"periodo,importo\n2025,10\n", ".csv", "text/csv"),
        ("export.txt", b"Posizione contributiva disponibile\n", ".txt", "text/plain"),
        ("export.xml", b"<?xml version='1.0'?><record />", ".xml", "application/xml"),
        ("export.png", b"\x89PNG\r\n\x1a\ncontent", ".png", "image/png"),
        ("export.jpeg", b"\xff\xd8\xff\xe0content", ".jpg", "image/jpeg"),
        ("export.tiff", b"II*\x00content", ".tif", "image/tiff"),
    ),
)
def test_register_portal_exports_accepts_bounded_evidence_formats(
    tmp_path: Path,
    filename: str,
    content: bytes,
    expected_suffix: str,
    media_type: str,
) -> None:
    module = _load_script()
    source = tmp_path / filename
    source.write_bytes(content)

    manifest_path = _register(module, [source], tmp_path / f"out-{source.suffix[1:]}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["artifacts"][0]["stored_name"].endswith(expected_suffix)
    assert manifest["artifacts"][0]["media_type"] == media_type


@pytest.mark.parametrize(
    ("origin", "canonical"),
    (
        ("https://inps.it", "https://inps.it"),
        ("https://www.inps.it/", "https://www.inps.it"),
    ),
)
def test_register_portal_exports_accepts_only_canonical_official_host_boundaries(
    tmp_path: Path, origin: str, canonical: str
) -> None:
    module = _load_script()
    source = _write_pdf(tmp_path / "export.pdf")
    output_dir = tmp_path / hashlib.sha256(origin.encode("utf-8")).hexdigest()[:10]

    manifest_path = _register(module, [source], output_dir, source_origin=origin)

    assert (
        json.loads(manifest_path.read_text(encoding="utf-8"))["source_origin"]
        == canonical
    )


@pytest.mark.parametrize(
    "origin",
    (
        "http://www.inps.it",
        "https://inps.it.evil.example",
        "https://evil-inps.it",
        "https://user:secret@inps.it",
        "https://inps.it/portal",
        "https://inps.it?next=portal",
        "https://inps.it:8443",
        "https://servizi.inps.gov.it",
    ),
)
def test_register_portal_exports_rejects_non_exact_or_unsafe_origin(
    tmp_path: Path, origin: str
) -> None:
    module = _load_script()
    source = _write_pdf(tmp_path / "export.pdf")
    output_dir = tmp_path / "registered"

    with pytest.raises(module.PortalExportError):
        _register(module, [source], output_dir, source_origin=origin)

    assert not output_dir.exists()


@pytest.mark.parametrize(
    "confirmation_field",
    (
        "confirm_human_authority",
        "confirm_profile_authority",
        "confirm_delegation_authority",
        "approve_client_data_processing",
        "confirm_user_downloaded_files",
    ),
)
def test_register_portal_exports_requires_each_explicit_confirmation(
    tmp_path: Path, confirmation_field: str
) -> None:
    module = _load_script()
    source = _write_pdf(tmp_path / "export.pdf")
    output_dir = tmp_path / "registered"

    with pytest.raises(module.PortalExportError, match="explicitly confirmed"):
        _register(
            module,
            [source],
            output_dir,
            **{confirmation_field: False},
        )

    assert not output_dir.exists()


@pytest.mark.parametrize(
    ("overrides", "message"),
    (
        ({"authority_actor_id": "Example Client"}, "pseudonymous"),
        ({"processing_approved_by_id": "reviewer@example.com"}, "pseudonymous"),
        ({"authority_recorded_at": "2026-07-16T10:15:00"}, "timezone"),
        ({"processing_recorded_at": "not-a-time"}, "ISO date-time"),
        ({"authority_scope": "short"}, "8-1000"),
    ),
)
def test_register_portal_exports_rejects_unbounded_authority_metadata(
    tmp_path: Path, overrides: dict[str, object], message: str
) -> None:
    module = _load_script()
    source = _write_pdf(tmp_path / "export.pdf")

    with pytest.raises(module.PortalExportError, match=message):
        _register(module, [source], tmp_path / "registered", **overrides)


@pytest.mark.parametrize(
    ("filename", "content"),
    (
        ("portal.html", b"<!doctype html><html></html>"),
        ("network.har", b'{"log": {}}'),
        ("Browser Profile.txt", b"profile state"),
        ("Cookies.txt", b"ordinary text"),
        ("Local Storage.csv", b"key,value\n"),
        ("renamed.txt", b"# Netscape HTTP Cookie File\n.example\tTRUE"),
        ("renamed-har.txt", b'{"log":{"creator":{},"entries":[]}}'),
        ("renamed.xml", b"<!doctype html><html></html>"),
        ("xml-html.xml", b"<?xml version='1.0'?><html></html>"),
        ("fake.pdf", b"not a pdf"),
    ),
)
def test_register_portal_exports_rejects_browser_state_and_disguised_files(
    tmp_path: Path, filename: str, content: bytes
) -> None:
    module = _load_script()
    source = tmp_path / filename
    source.write_bytes(content)
    output_dir = tmp_path / "registered"

    with pytest.raises(module.PortalExportError):
        _register(module, [source], output_dir)

    assert not output_dir.exists()


def test_register_portal_exports_rejects_source_symlink(tmp_path: Path) -> None:
    module = _load_script()
    source = _write_pdf(tmp_path / "export.pdf")
    link = tmp_path / "linked.pdf"
    try:
        link.symlink_to(source)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    with pytest.raises(module.PortalExportError, match="symlink"):
        _register(module, [link], tmp_path / "registered")


def test_register_portal_exports_rejects_output_inside_git_workspace(
    tmp_path: Path,
) -> None:
    module = _load_script()
    source = _write_pdf(tmp_path / "export.pdf")
    forbidden_output = PLUGIN_ROOT / "portal-export-test-must-not-exist"
    assert not forbidden_output.exists()

    with pytest.raises(module.PortalExportError, match="outside"):
        _register(module, [source], forbidden_output)

    assert not forbidden_output.exists()


def test_register_portal_exports_bounds_manifest_artifact_count(tmp_path: Path) -> None:
    module = _load_script()
    source = _write_pdf(tmp_path / "export.pdf")
    output_dir = tmp_path / "registered"

    with pytest.raises(module.PortalExportError, match="at most 999"):
        _register(module, [source] * 1000, output_dir)

    assert not output_dir.exists()


def test_verify_portal_export_rejects_modified_artifact(tmp_path: Path) -> None:
    module = _load_script()
    source = _write_pdf(tmp_path / "export.pdf")
    output_dir = tmp_path / "registered"
    manifest_path = _register(module, [source], output_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact = output_dir / manifest["artifacts"][0]["stored_name"]

    artifact.write_bytes(b"%PDF-1.4\ntampered\n")
    artifact.chmod(0o600)

    with pytest.raises(module.PortalExportError, match="size|hash"):
        module.verify_portal_export(output_dir)


def test_verify_portal_export_rejects_unsafe_manifest_flag(tmp_path: Path) -> None:
    module = _load_script()
    source = _write_pdf(tmp_path / "export.pdf")
    output_dir = tmp_path / "registered"
    manifest_path = _register(module, [source], output_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["safety"]["portal_automation_performed"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    manifest_path.chmod(0o600)

    with pytest.raises(module.PortalExportError, match="unsafe"):
        module.verify_portal_export(output_dir)


def test_verify_portal_export_rejects_malformed_authority_value(tmp_path: Path) -> None:
    module = _load_script()
    source = _write_pdf(tmp_path / "export.pdf")
    output_dir = tmp_path / "registered"
    manifest_path = _register(module, [source], output_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["authority"]["human_actor_role"] = ["authorized_delegate"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    manifest_path.chmod(0o600)

    with pytest.raises(module.PortalExportError, match="role"):
        module.verify_portal_export(output_dir)


def test_verify_portal_export_rejects_unexpected_file_and_broad_permissions(
    tmp_path: Path,
) -> None:
    module = _load_script()
    source = _write_pdf(tmp_path / "export.pdf")
    output_dir = tmp_path / "registered"
    manifest_path = _register(module, [source], output_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact = output_dir / manifest["artifacts"][0]["stored_name"]
    artifact.chmod(0o644)

    with pytest.raises(module.PortalExportError, match="owner-only"):
        module.verify_portal_export(output_dir)

    artifact.chmod(0o600)
    extra = output_dir / "unexpected.txt"
    extra.write_text("unexpected", encoding="utf-8")
    extra.chmod(0o600)
    with pytest.raises(module.PortalExportError, match="unexpected"):
        module.verify_portal_export(output_dir)


def test_cli_register_and_verify_without_portal_or_network_access(
    tmp_path: Path,
) -> None:
    source = _write_pdf(tmp_path / "export.pdf")
    output_dir = tmp_path / "registered"
    register_command = [
        sys.executable,
        str(SCRIPT_PATH),
        "register",
        str(source),
        "--output-dir",
        str(output_dir),
        "--source-origin",
        "https://www.inps.it",
        "--authority-actor-id",
        "ACT-PORTAL-001",
        "--authority-actor-role",
        "authorized_delegate",
        "--authority-recorded-at",
        "2026-07-16T10:15:00+02:00",
        "--authority-scope",
        "Read and export the authorized client contribution records.",
        "--human-authority-basis",
        "Explicit instruction recorded by the responsible professional.",
        "--profile-authority-basis",
        "Access through the approved professional portal profile.",
        "--delegation-authority-basis",
        "Active client delegation checked before the manual export.",
        "--processing-approved-by-id",
        "REV-DATA-001",
        "--processing-approved-by-role",
        "professional_reviewer",
        "--processing-recorded-at",
        "2026-07-16T10:20:00+02:00",
        "--processor-scope",
        "Local evidence registration and later professional case review.",
        "--processing-approval-basis",
        "Studio processing approval for this bounded client case.",
        "--confirm-human-authority",
        "--confirm-profile-authority",
        "--confirm-delegation-authority",
        "--approve-client-data-processing",
        "--confirm-user-downloaded-files",
    ]

    registered = subprocess.run(
        register_command,
        cwd=tmp_path,
        capture_output=True,
        check=False,
        text=True,
    )
    verified = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "verify", str(output_dir)],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        text=True,
    )

    assert registered.returncode == 0, registered.stderr
    assert verified.returncode == 0, verified.stderr
    assert "Verified INPS export" in verified.stderr


def test_inventory_records_verified_export_and_excludes_private_manifest(
    tmp_path: Path,
) -> None:
    module = _load_script()
    sensitive_name = "TSTUSR80A01H501Z_estratto_contributivo.txt"
    source = tmp_path / sensitive_name
    source.write_text(
        "Periodo contributivo 2020-2024\n",
        encoding="utf-8",
    )
    registered_dir = tmp_path / "registered"
    manifest_path = _register(module, [source], registered_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    output_dir = tmp_path / "inventory"
    inventory_module = _load_inventory_script()

    result = inventory_module.main(
        [
            str(registered_dir),
            "--output-dir",
            str(output_dir),
            "--portal-export-manifest",
            str(manifest_path),
            "--no-ocr",
        ]
    )

    assert result == 0
    inventory = json.loads(
        (output_dir / "file_inventory.json").read_text(encoding="utf-8")
    )
    assert {record["relative_path"] for record in inventory["documents"]} == {
        manifest["artifacts"][0]["stored_name"]
    }
    run_intake_text = (output_dir / "run_intake.json").read_text(encoding="utf-8")
    run_intake = json.loads(run_intake_text)
    posture = run_intake["data_posture"]
    assert posture["acquisition_channels_used"] == ["inps_official_user_export"]
    assert posture["external_connectors_used"] == []
    assert posture["network_calls_by_scripts"] is False
    assert posture["portal_export_receipt"]["artifact_count"] == 1
    assert posture["portal_export_receipt"]["source_files_user_downloaded"] is True
    assert sensitive_name not in run_intake_text
    assert source.as_posix() not in run_intake_text


def test_inventory_requires_explicit_manifest_argument_for_registered_export(
    tmp_path: Path,
) -> None:
    module = _load_script()
    source = tmp_path / "export.txt"
    source.write_text("Periodo contributivo 2020-2024\n", encoding="utf-8")
    registered_dir = tmp_path / "registered"
    _register(module, [source], registered_dir)
    output_dir = tmp_path / "inventory"
    inventory_module = _load_inventory_script()

    result = inventory_module.main(
        [str(registered_dir), "--output-dir", str(output_dir), "--no-ocr"]
    )

    assert result == 1
    assert not output_dir.exists()


def test_inventory_rejects_tampered_export_receipt_with_changed_manifest_type(
    tmp_path: Path,
) -> None:
    module = _load_script()
    source = tmp_path / "export.txt"
    source.write_text("Periodo contributivo 2020-2024\n", encoding="utf-8")
    registered_dir = tmp_path / "registered"
    manifest_path = _register(module, [source], registered_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["manifest_type"] = "unrecognized_or_tampered_type"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    manifest_path.chmod(0o600)
    output_dir = tmp_path / "inventory"
    inventory_module = _load_inventory_script()

    result = inventory_module.main(
        [str(registered_dir), "--output-dir", str(output_dir), "--no-ocr"]
    )

    assert result == 1
    assert not output_dir.exists()


def test_inventory_rejects_nested_registered_export_bundle(tmp_path: Path) -> None:
    module = _load_script()
    source = tmp_path / "export.txt"
    source.write_text("Periodo contributivo 2020-2024\n", encoding="utf-8")
    input_dir = tmp_path / "case"
    (input_dir / "nested").mkdir(parents=True)
    _register(module, [source], input_dir / "nested" / "registered")
    output_dir = tmp_path / "inventory"
    inventory_module = _load_inventory_script()

    result = inventory_module.main(
        [str(input_dir), "--output-dir", str(output_dir), "--no-ocr"]
    )

    assert result == 1
    assert not output_dir.exists()


def test_inventory_rejects_orphan_registrar_artifact(tmp_path: Path) -> None:
    input_dir = tmp_path / "partial-registration"
    input_dir.mkdir()
    orphan = input_dir / "inps-export-001-0123456789ab.txt"
    orphan.write_text("partially copied portal export\n", encoding="utf-8")
    output_dir = tmp_path / "inventory"
    inventory_module = _load_inventory_script()

    result = inventory_module.main(
        [str(input_dir), "--output-dir", str(output_dir), "--no-ocr"]
    )

    assert result == 1
    assert not output_dir.exists()


@pytest.mark.parametrize(
    "receipt_name",
    ["portal_export_receipt.json", "inps_portal_export_approval.json"],
)
def test_inventory_rejects_private_export_receipt_like_files(
    tmp_path: Path, receipt_name: str
) -> None:
    input_dir = tmp_path / "case"
    nested = input_dir / "nested"
    nested.mkdir(parents=True)
    (nested / receipt_name).write_text('{"approved": true}', encoding="utf-8")
    output_dir = tmp_path / "inventory"
    inventory_module = _load_inventory_script()

    result = inventory_module.main(
        [str(input_dir), "--output-dir", str(output_dir), "--no-ocr"]
    )

    assert result == 1
    assert not output_dir.exists()


def test_inventory_does_not_blanket_reject_unrelated_generic_manifest(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "case"
    input_dir.mkdir()
    (input_dir / "manifest.json").write_text(
        json.dumps({"manifest_type": "unrelated_local_index", "files": []}),
        encoding="utf-8",
    )
    (input_dir / "evidence.txt").write_text(
        "Ordinary local evidence\n", encoding="utf-8"
    )
    output_dir = tmp_path / "inventory"
    inventory_module = _load_inventory_script()

    result = inventory_module.main(
        [str(input_dir), "--output-dir", str(output_dir), "--no-ocr"]
    )

    assert result == 0
    inventory = json.loads(
        (output_dir / "file_inventory.json").read_text(encoding="utf-8")
    )
    assert {document["relative_path"] for document in inventory["documents"]} == {
        "evidence.txt",
        "manifest.json",
    }


def test_register_error_does_not_disclose_sensitive_source_filename(
    tmp_path: Path,
) -> None:
    module = _load_script()
    sensitive_name = "Example-Client-TSTUSR80A01H501U.pdf"
    source = tmp_path / sensitive_name
    source.write_bytes(b"not a PDF")

    with pytest.raises(module.PortalExportError) as captured:
        _register(module, [source], tmp_path / "registered")

    assert sensitive_name not in str(captured.value)
    assert "TSTUSR80A01H501U" not in str(captured.value)


def test_register_copy_failure_removes_or_marks_partial_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script()
    source = _write_pdf(tmp_path / "official-export.pdf")
    output_dir = tmp_path / "registered"

    def fail_after_partial_copy(
        _plan: object, destination: Path, *, source_index: int
    ) -> None:
        assert source_index == 1
        destination.write_bytes(b"partial")
        raise module.PortalExportError("synthetic copy failure")

    monkeypatch.setattr(module, "_copy_plan", fail_after_partial_copy)

    with pytest.raises(module.PortalExportError, match="synthetic copy failure"):
        _register(module, [source], output_dir)

    if output_dir.exists():
        assert (output_dir / ".registration-incomplete").is_file()
        assert not list(output_dir.glob("inps-export-*"))
