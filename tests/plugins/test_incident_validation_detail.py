"""Schema rejection explains the failed contract without echoing private input."""

from __future__ import annotations

import io
import json
import urllib.error
from uuid import uuid4

from tests.plugins.test_operational_incident_client import client


def test_native_rejection_explains_capture_contract_without_echoing_input(
    tmp_path, monkeypatch
):
    module, _, _ = client(tmp_path, monkeypatch, "vera")
    transport = module._post
    body = json.dumps(
        {
            "detail": [
                {
                    "loc": ["body", "report"],
                    "type": "value_error",
                    "msg": "Value error, Complete capture requires technical evidence",
                    "input": {"private": "DO_NOT_ECHO"},
                    "ctx": {"error": "DO_NOT_ECHO"},
                }
            ]
        }
    ).encode()

    def post(operation, payload):
        if operation != "report":
            return transport(operation, payload)
        raise urllib.error.HTTPError(
            "https://fixture", 422, "Schema", {}, io.BytesIO(body)
        )

    monkeypatch.setattr(module, "_post", post)
    report = {
        "report_id": str(uuid4()),
        "product_version": "0.1.510",
        "host": "codex",
        "platform": "macos",
        "workflow": "journal-bank-reconciliation",
        "stage": "helper:seal_review_receipts.py",
        "capture_state": "complete",
        "diagnostics": [
            {
                "component": "fixture",
                "stage": "write",
                "message": "Write denied",
                "errno": 1,
            }
        ],
    }

    result = module.native_request({"operation": "report", "report": report})

    assert result["delivery"] == "rejected"
    assert result["identifier"] == report["report_id"]
    assert result["validation_errors"] == [
        {
            "location": ["body", "report"],
            "type": "value_error",
            "message": "Complete capture requires error_code or technical_frames; errno alone is insufficient.",
        }
    ]
    assert "DO_NOT_ECHO" not in json.dumps(result)
