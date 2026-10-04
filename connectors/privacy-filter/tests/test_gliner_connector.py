from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import io
import json
import socket
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mparanza_privacy_filter.contracts import (
    MODEL_REVISION,
    FilteredDocument,
    FilterError,
)
from mparanza_privacy_filter.engines import GLINER2
from mparanza_privacy_filter.gliner_worker import filter_document
from mparanza_privacy_filter.service import FilterService, Settings

__all__: list[str] = []


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    source, model = tmp_path / "input", tmp_path / "model"
    source.mkdir()
    for name in GLINER2.required_files:
        path = model / "checkpoint" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic test fixture")
    (model / "ready.json").write_text(json.dumps({"model_revision": GLINER2.revision}))
    return Settings(source, tmp_path / "output", model, engine="gliner2")


def span(text: str, start: int, end: int) -> dict:
    return {"text": text[start:end], "start": start, "end": end}


def model_with(entities: dict) -> SimpleNamespace:
    return SimpleNamespace(
        extract_entities_long=lambda *a, **k: {
            "entities": entities,
            "original_text": "never forward me",
        }
    )


def test_repeated_values_and_unicode_are_replaced_at_exact_offsets(
    tmp_path: Path,
) -> None:
    text = "È Anna; Anna scrive."
    path = tmp_path / "example.txt"
    path.write_text(text, encoding="utf-8")
    result = filter_document(
        path, model_with({"person": [span(text, 2, 6), span(text, 8, 12)]})
    )
    assert result == FilteredDocument(
        "È [PERSON]; [PERSON] scrive.", {"person": 2}, len(text)
    )


def test_nested_and_crossing_predictions_cover_the_entire_detected_region(
    tmp_path: Path,
) -> None:
    text = "Anna Maria Rossi works."
    path = tmp_path / "example.txt"
    path.write_text(text)
    result = filter_document(
        path,
        model_with(
            {
                "person": [span(text, 0, 10), span(text, 0, 10)],
                "full_name": [span(text, 5, 16)],
                "first_name": [span(text, 0, 4)],
            }
        ),
    )
    assert result.redacted_text == "[PERSON] works."
    assert result.detection_counts == {"person": 1, "full_name": 1, "first_name": 1}


@pytest.mark.parametrize(
    "entities",
    [
        {"secret raw name": []},
        {"person": "raw"},
        {"person": ["raw"]},
        {"person": [{"start": -1, "end": 4, "text": "Anna"}]},
        {"person": [{"start": 0, "end": 100, "text": "Anna"}]},
        {"person": [{"start": True, "end": 4, "text": "Anna"}]},
        {"person": [{"start": 0, "end": 4, "text": "different"}]},
    ],
)
def test_invalid_predictions_fail_without_returning_originals(
    tmp_path: Path, entities: dict
) -> None:
    path = tmp_path / "example.txt"
    path.write_text("Anna")
    with pytest.raises(FilterError, match="^invalid_model_spans$"):
        filter_document(path, model_with(entities))


def test_missing_entities_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "example.txt"
    path.write_text("Anna")
    model = SimpleNamespace(extract_entities_long=lambda *a, **k: {"text": "Anna"})
    with pytest.raises(FilterError, match="^invalid_model_spans$"):
        filter_document(path, model)


def test_no_predictions_preserve_clean_text(tmp_path: Path) -> None:
    path = tmp_path / "example.txt"
    path.write_text("Quarterly revenue increased.")
    assert (
        filter_document(path, model_with({})).redacted_text
        == "Quarterly revenue increased."
    )


def test_gliner_artifact_records_engine_and_reads_after_restart(
    settings: Settings,
) -> None:
    path = settings.input_root / "example.txt"
    path.write_text("Anna")
    service = FilterService(
        settings, lambda *_: FilteredDocument("[PERSON]", {"person": 1}, 4)
    )
    receipt = service.filter_file("example.txt")
    assert receipt["engine"] == "gliner2"
    assert receipt["model_revision"] == GLINER2.revision
    assert (
        FilterService(settings).read_result(receipt["artifact_id"])["redacted_text"]
        == "[PERSON]"
    )
    assert "Anna" not in json.dumps(receipt)
    assert path.read_text() == "Anna"


def test_gliner_rejects_other_engine_response_labels(settings: Settings) -> None:
    (settings.input_root / "example.txt").write_text("Anna")
    service = FilterService(
        settings,
        lambda *_: FilteredDocument("[PRIVATE_PERSON]", {"private_person": 1}, 4),
    )
    with pytest.raises(FilterError, match="^invalid_worker_response$"):
        service.filter_file("example.txt")


@pytest.mark.parametrize("missing", GLINER2.required_files)
def test_gliner_requires_every_offline_model_asset(
    settings: Settings, missing: str
) -> None:
    (settings.checkpoint / missing).unlink()
    assert not FilterService(settings).status()["model_ready"]


def test_gliner_rejects_openai_preparation_receipt(settings: Settings) -> None:
    (settings.model_root / "ready.json").write_text(
        json.dumps({"model_revision": MODEL_REVISION})
    )
    assert not settings.ready()


def test_unknown_engine_is_rejected_before_processing(settings: Settings) -> None:
    with pytest.raises(FilterError, match="^unsupported_engine$"):
        FilterService(
            Settings(
                settings.input_root,
                settings.output_root,
                settings.model_root,
                engine="unknown",
            )
        )


def test_gliner_stdio_tools_are_distinct_and_errors_are_sanitized(
    settings: Settings,
) -> None:
    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-I",
                "-m",
                "mparanza_privacy_filter.server",
                "--engine",
                "gliner2",
                "--input-dir",
                str(settings.input_root),
                "--output-dir",
                str(settings.output_root),
                "--model-dir",
                str(settings.model_root),
            ],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listing = await session.list_tools()
                status = await session.call_tool("gliner2_pii_status", {})
                failure = await session.call_tool(
                    "gliner2_pii_file", {"path": "secret-client-name.txt"}
                )
                return listing, status, failure

    listing, status, failure = asyncio.run(exercise())
    assert {tool.name for tool in listing.tools} == {
        "gliner2_pii_status",
        "gliner2_pii_file",
        "gliner2_pii_batch",
        "gliner2_pii_read",
    }
    assert json.loads(status.content[0].text)["engine"] == "gliner2"
    assert failure.isError and "secret-client-name" not in failure.model_dump_json()


@pytest.mark.parametrize("operation", ["redact", "network", "error"])
def test_gliner_worker_suppresses_raw_values_and_network(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    from mparanza_privacy_filter import gliner_worker

    path = settings.input_root / "example.txt"
    path.write_text("Anna works.")

    def load(*a, **kwargs):
        assert kwargs["local_files_only"] is True
        if operation == "network":
            with socket.socket() as connection:
                connection.connect(("127.0.0.1", 9))
        if operation == "error":
            raise RuntimeError("Anna original value in an upstream error")
        model = model_with({"person": [span("Anna works.", 0, 4)]})
        model.eval = lambda: None
        return model

    output = io.StringIO()
    monkeypatch.setattr(socket, "socket", socket.socket)
    for name in (
        "HF_HUB_OFFLINE",
        "HF_HUB_DISABLE_TELEMETRY",
        "TRANSFORMERS_OFFLINE",
        "TOKENIZERS_PARALLELISM",
    ):
        monkeypatch.setenv(name, "")
    monkeypatch.setitem(
        sys.modules,
        "gliner2",
        SimpleNamespace(GLiNER2=SimpleNamespace(from_pretrained=load)),
    )
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(
            set_num_threads=lambda _: None, inference_mode=contextlib.nullcontext
        ),
    )
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "path": str(path),
                    "input_root": str(settings.input_root),
                    "checkpoint": str(settings.checkpoint),
                    "device": "cpu",
                }
            )
        ),
    )
    monkeypatch.setattr(sys, "stdout", output)
    gliner_worker.main()
    assert "Anna" not in output.getvalue()
    expected = (
        {
            "redacted_text": "[PERSON] works.",
            "detection_counts": {"person": 1},
            "source_characters": 11,
        }
        if operation == "redact"
        else {"error": "processing_failed"}
    )
    assert json.loads(output.getvalue()) == expected


def test_prepare_gliner_downloads_only_pinned_local_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mparanza_privacy_filter.gliner_prepare import prepare_model

    calls = []

    def download(**kwargs):
        calls.append(kwargs)
        for name in GLINER2.required_files:
            target = kwargs["local_dir"] / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("test")

    monkeypatch.setitem(
        sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=download)
    )
    prepare_model(tmp_path)
    assert calls[0]["revision"] == GLINER2.revision
    assert calls[0]["token"] is False
    assert json.loads((tmp_path / "ready.json").read_text())["engine"] == "gliner2"


def test_prepare_gliner_does_not_mark_incomplete_download_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mparanza_privacy_filter.gliner_prepare import prepare_model

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=lambda **k: None),
    )
    with pytest.raises(RuntimeError, match="model_download_incomplete"):
        prepare_model(tmp_path)
    assert not (tmp_path / "ready.json").exists()


def test_installer_selects_only_gliner_requirements_and_separate_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = importlib.util.spec_from_file_location(
        "privacy_install", Path(__file__).parents[1] / "install.py"
    )
    assert spec and spec.loader
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    source, runtime = tmp_path / "input", tmp_path / "runtime"
    source.mkdir()
    commands = []
    monkeypatch.setattr(
        installer.venv,
        "EnvBuilder",
        lambda **k: SimpleNamespace(create=lambda p: p.mkdir()),
    )
    monkeypatch.setattr(
        installer.subprocess, "run", lambda command, **k: commands.append(command)
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "install.py",
            "--engine",
            "gliner2",
            "--runtime-dir",
            str(runtime),
            "--input-dir",
            str(source),
            "--output-dir",
            str(tmp_path / "output"),
        ],
    )
    installer.main()
    config = tomllib.loads((runtime / "codex-mcp.toml").read_text())
    assert set(config["mcp_servers"]) == {"gliner2_pii"}
    assert config["mcp_servers"]["gliner2_pii"]["args"][-2:] == ["--engine", "gliner2"]
    assert commands[0][5].endswith("requirements-gliner2.txt")
    assert commands[1][3] == "mparanza_privacy_filter.gliner_prepare"
