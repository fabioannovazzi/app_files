from __future__ import annotations

import importlib.util
import json
import stat
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
STUDIO_ARCHIVE_ROOT = ROOT / "plugins" / "studio-archive"
RECORDER_PATH = STUDIO_ARCHIVE_ROOT / "scripts" / "record_agenzia_invoice_flow.py"


def _load_recorder() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "test_agenzia_invoice_flow_recorder_module", RECORDER_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_redact_text_removes_identifiers_and_private_terms() -> None:
    recorder = _load_recorder()

    result = recorder.redact_text(
        "Cliente Alpha SRL RSSMRA85T10A562S 12345678901 "
        "mario@example.com IT60X0542811101000000123456 ordine 987654",
        ("Cliente Alpha SRL",),
    )

    assert "Cliente Alpha SRL" not in result
    assert "RSSMRA85T10A562S" not in result
    assert "12345678901" not in result
    assert "mario@example.com" not in result
    assert "IT60X0542811101000000123456" not in result
    assert "987654" not in result
    assert "<private>" in result
    assert "<tax-id>" in result
    assert "<vat-id>" in result
    assert "<email>" in result
    assert "<iban>" in result


def test_sanitize_url_keeps_only_exact_agenzia_origin_and_path() -> None:
    recorder = _load_recorder()

    result = recorder.sanitize_url(
        "https://ivaservizi.agenziaentrate.gov.it/cons/cons-web/?token=secret#row"
    )

    assert result == "https://ivaservizi.agenziaentrate.gov.it/cons/cons-web/"


def test_sanitize_url_blocks_lookalike_and_non_https_origins() -> None:
    recorder = _load_recorder()

    assert (
        recorder.sanitize_url("https://agenziaentrate.gov.it.example.com/private")
        == "<blocked-origin>"
    )


def test_sanitize_url_redacts_identifiers_in_path() -> None:
    recorder = _load_recorder()

    result = recorder.sanitize_url(
        "https://ivaservizi.agenziaentrate.gov.it/result/12345678901/"
        "job-202608101234567890123456"
    )

    assert "12345678901" not in result
    assert "202608101234567890123456" not in result
    assert "<vat-id>" in result
    assert (
        recorder.sanitize_url("http://ivaservizi.agenziaentrate.gov.it/portale/")
        == "<blocked-origin>"
    )


def test_sanitize_element_drops_values_and_unknown_fields() -> None:
    recorder = _load_recorder()

    result = recorder.sanitize_element(
        {
            "event_type": "change",
            "tag": "input",
            "role": "textbox",
            "label": "Partita IVA 12345678901",
            "value": "12345678901",
            "outer_html": "<input value='12345678901'>",
            "unknown": "secret",
        }
    )

    assert result == {
        "event_type": "change",
        "label": "Partita IVA <vat-id>",
        "role": "textbox",
        "tag": "input",
    }


def test_build_download_record_hashes_name_without_saving_content() -> None:
    recorder = _load_recorder()

    class Download:
        suggested_filename = "IT12345678901_Fatture.zip"

    result = recorder.build_download_record(
        Download(), "https://ivaservizi.agenziaentrate.gov.it/cons/mass-web/result"
    )

    assert result["suffixes"] == [".zip"]
    assert result["content_saved"] is False
    assert "IT12345678901" not in json.dumps(result)
    assert "suggested_filename" not in result
    assert "download_path" not in result


def test_write_recording_creates_owner_only_review_file(tmp_path: Path) -> None:
    recorder = _load_recorder()
    recording = {
        "schema_version": recorder.SCHEMA_VERSION,
        "events": [],
        "snapshots": [],
        "downloads": [],
    }

    target = recorder.write_recording(tmp_path / "private", recording)

    assert json.loads(target.read_text(encoding="utf-8")) == recording
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700


def test_write_recording_rejects_forbidden_capture_fields(tmp_path: Path) -> None:
    recorder = _load_recorder()
    recording = {
        "schema_version": recorder.SCHEMA_VERSION,
        "events": [{"request_headers": {"Authorization": "secret"}}],
    }

    try:
        recorder.write_recording(tmp_path, recording)
    except ValueError as exc:
        assert "request_headers" in str(exc)
    else:
        raise AssertionError("forbidden recording fields were accepted")


def test_write_recording_does_not_overwrite_prior_recording(tmp_path: Path) -> None:
    recorder = _load_recorder()
    output_dir = tmp_path / "private"
    recording = {"schema_version": recorder.SCHEMA_VERSION, "events": []}
    recorder.write_recording(output_dir, recording)

    try:
        recorder.write_recording(output_dir, recording)
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("existing recording was overwritten")


def test_studio_archive_skill_exposes_two_checkpoint_teaching_flow() -> None:
    skill = (STUDIO_ARCHIVE_ROOT / "skills" / "studio-archive" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "Teach Vera the Agenzia invoice-download flow" in skill
    assert "di' a voce oppure scrivi `pronto`" in skill
    assert "va bene anche `ready`" in skill
    assert "di' a voce oppure scrivi\n   `fatto`" in skill
    assert "va bene anche `done`" in skill
    assert "Do not read the JSON into model context" in skill
    assert "requirements-portal-recorder.txt" in skill


def test_studio_archive_manifest_advertises_agenzia_teaching_route() -> None:
    manifest = json.loads(
        (STUDIO_ARCHIVE_ROOT / ".codex-plugin" / "plugin.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["version"] == "0.1.14"
    assert "fatture-e-corrispettivi" in manifest["keywords"]
    assert "playwright" in manifest["keywords"]
    assert any(
        "Mostra a Vera" in prompt for prompt in manifest["interface"]["defaultPrompt"]
    )


def test_studio_archive_privacy_register_covers_agenzia_recording() -> None:
    privacy = json.loads(
        (
            ROOT
            / "plugins"
            / "vera"
            / "privacy"
            / "workstreams"
            / "studio-archive.json"
        ).read_text(encoding="utf-8")
    )
    boundaries = {item["id"]: item for item in privacy["external_boundaries"]}
    classes = {item["id"]: item for item in privacy["model_context"]["classes"]}
    controls = {item["id"]: item for item in privacy["security_controls"]}

    boundary = boundaries["codex-agenzia-invoice-flow-teaching"]
    assert boundary["optional"] is True
    assert boundary["requires_confirmation"] is True
    assert boundary["runtime_profiles"] == ["openai-codex"]
    assert "agenzia-flow-implementation-recording" in classes
    assert "privacy-bounded-agenzia-flow-recording" in controls
