from __future__ import annotations

import base64
import importlib
import json
import re
import stat
import sys
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.run_receipts import api
from modules.run_receipts.signing import RunReceiptSigner, canonical_receipt_bytes
from modules.run_receipts.store import RunReceiptStore

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins" / "vera" / "scripts"
PLUGIN_ROOT = ROOT / "plugins" / "vera"


class _Response:
    def __init__(self, response: Any) -> None:
        self._response = response

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, amount: int = -1) -> bytes:
        return bytes(self._response.content[:amount])


def _modules(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Any]:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    sys.modules.pop("model_data_report", None)
    sys.modules.pop("notarized_run_receipt", None)
    report_module = importlib.import_module("model_data_report")
    receipt_module = importlib.import_module("notarized_run_receipt")
    return report_module, receipt_module


def _report(report_module: Any, output: Path) -> Path:
    request = {
        "schema_version": 1,
        "workflow_id": "concordato-plan-review",
        "run_id": "run_89abcdef0123456789abcdef",
        "runtime_profile": "openai-codex",
        "language": "it",
        "created_at": "2026-08-27T10:00:00+00:00",
        "professional_purpose": "Rivedere il piano completo della società locale.",
        "phases": [
            {
                "phase_id": "semantic-review",
                "purpose": "Leggere il piano completo.",
                "outcome": "full_context_required",
                "evidence_basis": "workflow_receipt",
                "source_extent": [
                    {
                        "unit": "files",
                        "quantity": 1,
                        "label": "piano selezionato",
                        "basis": "measured",
                    }
                ],
                "locally_processed": [
                    {
                        "unit": "files",
                        "quantity": 1,
                        "label": "fonte locale",
                        "basis": "measured",
                    }
                ],
                "model_visible": [
                    {
                        "unit": "pages",
                        "quantity": 84,
                        "label": "pagine complete",
                        "basis": "measured",
                    }
                ],
                "remained_local": [],
                "reason": "Le sezioni dovevano essere lette insieme.",
                "evidence_files": [],
            }
        ],
        "improvement_assessment": {"status": "not_assessed", "candidates": []},
    }
    report, _markdown = report_module.build_model_data_report(
        request, evidence_root=output
    )
    path = output / "model_data_report.json"
    path.write_bytes(receipt_canonical(report))
    return path


def receipt_canonical(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _opener(tmp_path: Path) -> tuple[Any, RunReceiptStore]:
    store = RunReceiptStore(sqlite_path=tmp_path / "server.sqlite3")
    signer = RunReceiptSigner(private_key=Ed25519PrivateKey.generate())
    app = FastAPI()
    app.include_router(api.site_router)
    app.include_router(api.api_router)
    app.dependency_overrides[api.get_run_receipt_store] = lambda: store
    app.dependency_overrides[api.get_run_receipt_signer] = lambda: signer
    app.dependency_overrides[api.get_run_receipt_rate_limiter] = (
        lambda: api.RunReceiptRateLimiter()
    )
    client = TestClient(app)

    def open_request(request: Any, *, timeout: float) -> _Response:
        assert timeout == 10.0
        path = request.full_url.replace("https://mparanza.com", "", 1)
        headers = dict(request.header_items())
        if request.get_method() == "POST":
            response = client.post(path, content=request.data, headers=headers)
        else:
            response = client.get(path, headers=headers)
        return _Response(response)

    return open_request, store


def test_end_to_end_stamps_exports_and_verifies_without_sending_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_module, receipt_module = _modules(monkeypatch)
    report_path = _report(report_module, tmp_path)
    opener, store = _opener(tmp_path)

    stamped = receipt_module.stamp_model_data_report(
        report_path,
        output_dir=tmp_path,
        plugin_root=PLUGIN_ROOT,
        opener=opener,
    )
    verified = receipt_module.verify_model_data_receipt(
        Path(stamped["receipt_path"]),
        report_path=report_path,
        opener=opener,
    )
    request = json.loads(
        (tmp_path / "model_data_receipt_request.json").read_text(encoding="utf-8")
    )
    server_record = store.get(request["receipt_id"])

    assert verified["status"] == "valid"
    assert set(request) == {
        "schema_version",
        "receipt_id",
        "plugin_version",
        "report_sha256",
    }
    assert "concordato-plan-review" not in json.dumps(request)
    assert "società locale" not in json.dumps(request)
    assert server_record is not None
    assert not hasattr(server_record, "report")
    html_text = (tmp_path / "model_data_receipt.html").read_text(encoding="utf-8")
    receipt = json.loads(
        (tmp_path / "model_data_receipt.json").read_text(encoding="utf-8")
    )
    embedded_report = re.search(
        r'<script id="embedded-report" type="application/octet-stream">([^<]+)</script>',
        html_text,
    )
    embedded_signature_payload = re.search(
        r'<script id="signed-receipt" type="application/octet-stream">([^<]+)</script>',
        html_text,
    )
    assert embedded_report is not None
    assert embedded_signature_payload is not None
    assert base64.b64decode(embedded_report.group(1)) == report_path.read_bytes()
    signed_payload = base64.b64decode(embedded_signature_payload.group(1))
    assert signed_payload == canonical_receipt_bytes(server_record.signed_payload)
    public_key = Ed25519PublicKey.from_public_bytes(
        base64.urlsafe_b64decode(
            receipt["public_key"] + "=" * (-len(receipt["public_key"]) % 4)
        )
    )
    public_key.verify(
        base64.urlsafe_b64decode(
            receipt["signature"] + "=" * (-len(receipt["signature"]) % 4)
        ),
        signed_payload,
    )
    assert "Rivedere il piano completo della società locale" in html_text
    assert "Stampa o salva in PDF" in html_text
    assert "Non prova" in html_text


def test_disabled_setting_makes_no_network_call_and_enable_is_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_module, receipt_module = _modules(monkeypatch)
    report_path = _report(report_module, tmp_path)
    plugin_data = tmp_path / "plugin-data"

    disabled = receipt_module.stamp_model_data_report_if_enabled(
        report_path,
        output_dir=tmp_path,
        plugin_root=PLUGIN_ROOT,
        plugin_data=plugin_data,
    )
    settings_path = receipt_module._write_settings(
        enabled=True, plugin_data=plugin_data
    )

    assert disabled == {"status": "disabled"}
    assert not (tmp_path / "model_data_receipt_request.json").exists()
    assert stat.S_IMODE(settings_path.stat().st_mode) == 0o600
    assert receipt_module.firm_receipts_enabled(plugin_data) is True


def test_enable_cli_requires_explicit_boundary_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _report_module, receipt_module = _modules(monkeypatch)
    plugin_data = tmp_path / "plugin-data"

    refused = receipt_module.main(
        ["settings", "enable", "--plugin-data", str(plugin_data)]
    )
    accepted = receipt_module.main(
        [
            "settings",
            "enable",
            "--plugin-data",
            str(plugin_data),
            "--confirm-minimal-server-record",
        ]
    )

    assert refused == 2
    assert accepted == 0
    assert receipt_module.firm_receipts_enabled(plugin_data) is True


def test_failed_stamp_keeps_same_minimal_request_for_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_module, receipt_module = _modules(monkeypatch)
    report_path = _report(report_module, tmp_path)

    def unavailable(_request: object, *, timeout: float) -> object:
        del timeout
        raise OSError("synthetic outage")

    with pytest.raises(
        receipt_module.NotarizedRunReceiptError, match="service is unavailable"
    ):
        receipt_module.stamp_model_data_report(
            report_path,
            output_dir=tmp_path,
            plugin_root=PLUGIN_ROOT,
            opener=unavailable,
        )
    first_request = (tmp_path / "model_data_receipt_request.json").read_bytes()
    with pytest.raises(receipt_module.NotarizedRunReceiptError):
        receipt_module.stamp_model_data_report(
            report_path,
            output_dir=tmp_path,
            plugin_root=PLUGIN_ROOT,
            opener=unavailable,
        )

    assert (tmp_path / "model_data_receipt_request.json").read_bytes() == first_request
