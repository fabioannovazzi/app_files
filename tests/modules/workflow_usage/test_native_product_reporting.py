"""The installed reporting client must deliver and reopen actual signed reports."""

from __future__ import annotations

import importlib
import json
import sys
import urllib.error
from pathlib import Path
from uuid import uuid4

import pytest

from tests.modules.workflow_usage.test_product_parity import PIPELINES, service, stores
from tests.plugins.test_vera_notarized_run_receipt import _report, _Response

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("product", PIPELINES)
def test_native_report_pending_retry_receipt_completion_and_reopen(
    service, tmp_path, monkeypatch, product
):
    client, store, receipts, _, _, _ = service
    scripts = ROOT / "plugins" / product / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    for name in (
        "operational_incidents",
        "workflow_usage",
        "model_data_report",
        "notarized_run_receipt",
        "reporting_product",
    ):
        monkeypatch.delitem(sys.modules, name, raising=False)
    incidents = importlib.import_module("operational_incidents")
    usage = importlib.import_module("workflow_usage")
    reports = importlib.import_module("model_data_report")
    stamps = importlib.import_module("notarized_run_receipt")
    monkeypatch.setenv("MPARANZA_INCIDENT_STATE_DIR", str(tmp_path / "private"))
    monkeypatch.setenv("MPARANZA_INCIDENT_DEVICE_DIR", str(tmp_path / "computer"))
    monkeypatch.setenv("MPARANZA_INCIDENT_HOST", "codex")
    offline = True
    requests = []

    class Transport:
        def open(self, request, timeout):
            if offline:
                raise urllib.error.URLError("Controlled transport interruption")
            path = request.full_url.removeprefix("https://mparanza.com")
            payload = json.loads(request.data) if request.data else None
            requests.append((path, payload))
            response = client.request(request.get_method(), path, json=payload)
            if response.status_code >= 400:
                raise urllib.error.HTTPError(
                    request.full_url, response.status_code, "Rejected", None, None
                )
            return _Response(response)

    monkeypatch.setattr(
        incidents.urllib.request, "build_opener", lambda *_: Transport()
    )
    run_id = str(uuid4())
    usage.start(run_id, PIPELINES[product], sample_kind="agent_test", host="codex")
    retained_start = usage.pending()["events"][0]
    output = tmp_path / "output"
    output.mkdir()
    report = _report(reports, output)
    report_bytes = report.read_bytes()

    assert usage.stamp_report(run_id, report, output)["status"] == "pending"
    request_bytes = (output / "model_data_receipt_request.json").read_bytes()
    assert usage.pending()["events"][0] == retained_start
    offline = False
    assert usage.flush()["queued"] == 0
    stamped = usage.stamp_report(run_id, report, output)
    assert stamped["status"] == "stamped"
    assert (output / "model_data_receipt_request.json").read_bytes() == request_bytes
    usage.record(run_id, "completed")
    usage.record(
        run_id,
        "feedback",
        stars=2,
        comment="Controlled native acceptance",
        feedback_source="synthetic_test",
    )

    projection = store.workflow_inspect(run_id)["run"]
    assert projection["product"] == product
    assert projection["state"] == "completed"
    assert projection["feedback"]["stars"] == 2
    assert len(projection["receipts"]) == 1
    proof = json.loads((output / "model_data_receipt.json").read_text())
    assert receipts.get(proof["receipt_id"]).product == product
    assert (
        stamps.verify_model_data_receipt(
            output / "model_data_receipt.json", report_path=report
        )["status"]
        == "valid"
    )
    sent_before = len(requests)
    assert reports.show_model_data_report(report)
    assert len(requests) == sent_before
    assert report.read_bytes() == report_bytes
    assert product.title() in (output / "model_data_receipt.html").read_text()
    stamp_payload = next(
        payload for path, payload in requests if path == f"/api/{product}/run-receipts"
    )
    assert set(stamp_payload) == {
        "schema_version",
        "receipt_id",
        "plugin_version",
        "report_sha256",
    } | ({"product"} if product != "vera" else set())
    assert usage.flush()["delivered"] == 0
