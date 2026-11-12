"""Current-harness selection regressions; no provider or native host is called."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = (
    Path(__file__).resolve().parents[2]
    / "plugins/journal-bank-reconciliation/scripts/worker_capabilities.py"
)


@pytest.fixture
def capabilities(monkeypatch):
    spec = importlib.util.spec_from_file_location("tested_worker_capabilities", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module, "shutil", SimpleNamespace(which=lambda _: "/runtime/codex")
    )
    return module


def catalog(model="gpt-6-luna", effort="high"):
    return {
        "runtime": "observed-newer-runtime",
        "models": [
            {"model": model, "supportedReasoningEfforts": [{"reasoningEffort": effort}]}
        ],
    }


def test_selects_current_advertised_model_and_records_discovery(
    capabilities, monkeypatch
):
    monkeypatch.setattr(capabilities, "_catalog", lambda _: catalog())
    selection = capabilities.select_worker("open-item-reconciliation")
    assert selection["model"] == "gpt-6-luna"
    assert selection["reasoning_effort"] == "high"
    assert selection["discovery"]["runtime"] == "observed-newer-runtime"
    assert selection["quality_claim"] == "requires_representative_validation"


def test_configured_non_luna_model_is_supported_when_harness_advertises_it(
    capabilities, monkeypatch
):
    policy = {
        "host": "codex",
        "candidates": {
            "codex": [
                {
                    "model": "another-economy-model",
                    "effort": "medium",
                    "cost_class": "low",
                }
            ]
        },
    }
    fake_path = SimpleNamespace(
        with_name=lambda _: SimpleNamespace(read_text=lambda: json.dumps(policy))
    )
    monkeypatch.setattr(capabilities, "Path", lambda _: fake_path)
    monkeypatch.setattr(
        capabilities, "_catalog", lambda _: catalog("another-economy-model", "medium")
    )
    selection = capabilities.select_worker("journal-bank-reconciliation")
    assert selection["model"] == "another-economy-model"
    assert selection["reasoning_effort"] == "medium"


@pytest.mark.parametrize(
    "model,effort", [("expensive-other-model", "high"), ("gpt-6-luna", "low")]
)
def test_missing_suitable_model_or_effort_has_explicit_failure(
    capabilities, monkeypatch, model, effort
):
    monkeypatch.setattr(capabilities, "_catalog", lambda _: catalog(model, effort))
    with pytest.raises(
        capabilities.UnsupportedWorkerCapability, match="no configured low-cost"
    ):
        capabilities.select_worker("open-item-reconciliation")


@pytest.mark.parametrize("host", ["cowork", "antigravity"])
def test_unverified_host_does_not_silently_use_codex_or_invent_a_worker(
    capabilities, monkeypatch, host
):
    monkeypatch.setattr(
        capabilities,
        "_catalog",
        lambda _: pytest.fail("Cross-host fallback is forbidden"),
    )
    selection = capabilities.select_worker("open-item-reconciliation", host=host)
    assert selection["host"] == host
    assert selection["discovery"]["status"] == "requires_parent_observation"
    assert selection["reasoning_effort"] == "host_default"


def test_replay_preserves_selection_without_querying_changed_catalog(
    capabilities, monkeypatch
):
    monkeypatch.setattr(capabilities, "_catalog", lambda _: catalog())
    selection = capabilities.select_worker("open-item-reconciliation")
    monkeypatch.setattr(
        capabilities,
        "_catalog",
        lambda _: pytest.fail("Replay cannot replace the original selection"),
    )
    assert capabilities.validate_selection(
        selection, "open-item-reconciliation", None
    ) == ("gpt-6-luna", "high", selection)


def test_modified_selection_is_rejected(capabilities, monkeypatch):
    monkeypatch.setattr(capabilities, "_catalog", lambda _: catalog())
    selection = capabilities.select_worker("open-item-reconciliation")
    selection["model"] = "different-model"
    with pytest.raises(ValueError, match="digest"):
        capabilities.validate_selection(selection, "open-item-reconciliation", None)


@pytest.mark.parametrize(
    "response, message",
    [
        ({"data": [], "nextCursor": "next"}, "bounded discovery page"),
        ({"error": {"message": "denied"}}, "model/list failed"),
        (None, "exited or exceeded"),
    ],
)
def test_catalog_protocol_reports_missing_bounded_capability(
    capabilities, monkeypatch, response, message
):
    from contextlib import contextmanager
    from io import BytesIO

    chunks = [b'{"id":1,"result":{"userAgent":"current-runtime"}}\n']
    if response is not None:
        payload = (
            {"id": 2, **response}
            if "error" in response
            else {"id": 2, "result": response}
        )
        chunks.append(json.dumps(payload).encode() + b"\n")
    chunks.append(b"")
    chunks = iter(chunks)
    process = SimpleNamespace(
        stdin=BytesIO(),
        stdout=SimpleNamespace(fileno=lambda: 1),
        terminate=lambda: None,
        wait=lambda **_: 0,
    )

    @contextmanager
    def start(*args, **kwargs):
        yield process

    monkeypatch.setattr(capabilities.subprocess, "Popen", start)
    monkeypatch.setattr(
        capabilities, "os", SimpleNamespace(read=lambda *_: next(chunks))
    )
    with pytest.raises(capabilities.UnsupportedWorkerCapability, match=message):
        capabilities.select_worker("open-item-reconciliation")


def test_absent_native_executable_is_explicit(capabilities):
    capabilities.shutil.which = lambda _: None
    with pytest.raises(
        capabilities.UnsupportedWorkerCapability, match="CLI is missing"
    ):
        capabilities.select_worker("open-item-reconciliation")


@pytest.mark.parametrize(
    "field,value",
    [("host", "cowork"), ("model", "--invalid"), ("reasoning_effort", "infinite")],
)
def test_invalid_retained_configuration_cannot_launch(
    capabilities, monkeypatch, field, value
):
    monkeypatch.setattr(capabilities, "_catalog", lambda _: catalog())
    selection = capabilities.select_worker("open-item-reconciliation")
    selection.pop("content_sha256")
    selection[field] = value
    selection["content_sha256"] = capabilities._digest(selection)
    with pytest.raises(ValueError):
        capabilities.validate_selection(selection, "open-item-reconciliation", None)


def test_selection_reads_real_pipes_without_socket_selectors(capabilities, monkeypatch):
    """Windows pipes cannot be polled with socket selectors (WinError 10038)."""
    import selectors
    import subprocess
    import sys

    original_popen = subprocess.Popen
    response = json.dumps(catalog())
    script = """
import json, sys
catalog = json.loads(sys.argv[1])
for line in sys.stdin:
    request = json.loads(line)
    if "id" not in request:
        continue
    result = {"userAgent": catalog["runtime"]} if request["method"] == "initialize" else {"data": catalog["models"]}
    print(json.dumps({"id": request["id"], "result": result}), flush=True)
"""

    def start(*args, **kwargs):
        return original_popen([sys.executable, "-u", "-c", script, response], **kwargs)

    def unsupported_selector(*args, **kwargs):
        raise OSError(10038, "Socket operation on a non-socket")

    monkeypatch.setattr(capabilities.subprocess, "Popen", start)
    monkeypatch.setattr(selectors, "DefaultSelector", unsupported_selector)

    selected = capabilities.select_worker("open-item-reconciliation")

    assert selected["model"] == catalog()["models"][0]["model"]


def test_bank_reconciliation_uses_terra_without_changing_open_items(
    capabilities, monkeypatch
):
    monkeypatch.setattr(
        capabilities,
        "_catalog",
        lambda _: {
            "runtime": "fixture",
            "models": catalog()["models"] + catalog("gpt-6.1-terra")["models"],
        },
    )
    selected = capabilities.select_worker("journal-bank-reconciliation")
    assert selected["model"] == "gpt-6.1-terra"
    assert selected["cost_class"] == "standard"
    assert (
        capabilities.validate_selection(selected, "journal-bank-reconciliation", None)[
            0
        ]
        == "gpt-6.1-terra"
    )
    assert (
        capabilities.select_worker("open-item-reconciliation")["model"] == "gpt-6-luna"
    )


def test_bank_reconciliation_does_not_fall_back_to_luna(capabilities, monkeypatch):
    monkeypatch.setattr(capabilities, "_catalog", lambda _: catalog())
    with pytest.raises(capabilities.UnsupportedWorkerCapability):
        capabilities.select_worker("journal-bank-reconciliation")
