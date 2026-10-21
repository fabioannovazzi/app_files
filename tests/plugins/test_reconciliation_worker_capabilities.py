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

    @contextmanager
    def selector():
        yield SimpleNamespace(register=lambda *_: None, select=lambda _: [True])

    monkeypatch.setattr(capabilities.subprocess, "Popen", start)
    monkeypatch.setattr(capabilities.selectors, "DefaultSelector", selector)
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
