from __future__ import annotations

import asyncio
import importlib.util
import io
import json
import socket
import subprocess
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mparanza_privacy_filter import extract
from mparanza_privacy_filter.contracts import (
    MODEL_REVISION,
    FilteredDocument,
    FilterError,
)
from mparanza_privacy_filter.server import create_server
from mparanza_privacy_filter.service import FilterService, Settings, run_worker
from mparanza_privacy_filter.worker import filter_document
from pypdf import PdfWriter
from reportlab.pdfgen.canvas import Canvas

__all__: list[str] = []


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    source = tmp_path / "inputs"
    source.mkdir()
    model = tmp_path / "model"
    checkpoint = model / "checkpoint" / "original"
    checkpoint.mkdir(parents=True)
    (checkpoint / "config.json").write_text("{}")
    (checkpoint / "model.safetensors").write_bytes(b"test fixture only")
    (model / "tokenizer").mkdir()
    (model / "tokenizer" / "cache").write_bytes(b"fixture")
    (model / "ready.json").write_text(json.dumps({"model_revision": MODEL_REVISION}))
    return Settings(source, tmp_path / "outputs", model)


def fake_backend(path: Path, settings: Settings) -> FilteredDocument:
    return FilteredDocument("[PRIVATE_PERSON] works here.", {"private_person": 1}, 23)


def fake_model(text: str, *, warning: str | None = None) -> SimpleNamespace:
    span = SimpleNamespace(
        label="private_person", start=0, end=5, text="Alice", placeholder="Alice"
    )
    # Poison upstream convenience fields: neither may be copied into our result.
    result = SimpleNamespace(
        text=text, warning=warning, detected_spans=[span], redacted_text="Alice"
    )
    return SimpleNamespace(redact=lambda value: result)


@pytest.mark.parametrize("suffix", [".txt", ".md", ".markdown"])
def test_extract_utf8_and_bom(tmp_path: Path, suffix: str) -> None:
    path = tmp_path / ("text" + suffix)
    path.write_bytes(b"\xef\xbb\xbf" + "Città Zürich\nNext line".encode())
    assert extract.extract_text(path) == "Città Zürich\nNext line"


def test_docx_extracts_tables_headers_notes_comments_and_deleted_text(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source.docx"
    prefix = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "word/document.xml",
            prefix
            + "<w:p><w:t>Body</w:t></w:p><w:tbl><w:tr><w:tc><w:p><w:t>Table</w:t></w:p></w:tc></w:tr></w:tbl><w:p><w:delText>Deleted</w:delText></w:p></w:document>",
        )
        archive.writestr(
            "word/header1.xml", prefix + "<w:p><w:t>Header</w:t></w:p></w:document>"
        )
        archive.writestr(
            "word/footnotes.xml", prefix + "<w:p><w:t>Note</w:t></w:p></w:document>"
        )
        archive.writestr(
            "word/comments.xml", prefix + "<w:p><w:t>Comment</w:t></w:p></w:document>"
        )
    assert extract.extract_text(path).split() == [
        "Body",
        "Table",
        "Deleted",
        "Comment",
        "Note",
        "Header",
    ]


def test_pdf_extracts_text_without_layout(tmp_path: Path) -> None:
    path = tmp_path / "source.pdf"
    canvas = Canvas(str(path))
    canvas.drawString(50, 700, "Alice works here.")
    canvas.save()
    assert "Alice works here." in extract.extract_text(path)


@pytest.mark.parametrize("encrypted", [False, True])
def test_pdf_rejects_unreadable_pages_or_encryption(
    tmp_path: Path, encrypted: bool
) -> None:
    path = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    if encrypted:
        writer.encrypt("fixture-only")
    writer.write(path)
    code = (
        "encrypted_pdf" if encrypted else "pdf_page_without_text_requires_review_or_ocr"
    )
    with pytest.raises(FilterError, match=code):
        extract.extract_text(path)


@pytest.mark.parametrize(
    "content,code",
    [("", "empty_document"), (" ", "empty_document"), ("long", "text_too_large")],
)
def test_extraction_rejects_empty_or_oversize_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: str, code: str
) -> None:
    path = tmp_path / "source.txt"
    path.write_text(content)
    monkeypatch.setattr(extract, "MAX_CHARACTERS", 2)
    with pytest.raises(FilterError, match=code):
        extract.extract_text(path)


def test_extraction_rejects_oversize_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "source.txt"
    path.write_text("long")
    monkeypatch.setattr(extract, "MAX_BYTES", 2)
    with pytest.raises(FilterError, match="file_too_large"):
        extract.extract_text(path)


def test_model_values_and_upstream_output_are_excluded(tmp_path: Path) -> None:
    path = tmp_path / "source.txt"
    text = "Alice works here."
    path.write_text(text)
    result = filter_document(path, fake_model(text))
    assert result == FilteredDocument(
        "[PRIVATE_PERSON] works here.", {"private_person": 1}, len(text)
    )


def test_tokenizer_warning_blocks_output(tmp_path: Path) -> None:
    path = tmp_path / "source.txt"
    path.write_text("Alice")
    with pytest.raises(FilterError, match="tokenizer_roundtrip_mismatch"):
        filter_document(path, fake_model("Alice", warning="raw sensitive warning"))


def test_invalid_model_span_blocks_output(tmp_path: Path) -> None:
    path = tmp_path / "source.txt"
    path.write_text("Hi")
    with pytest.raises(FilterError, match="invalid_model_spans"):
        filter_document(path, fake_model("Hi"))


def test_no_detections_preserves_text_without_claiming_anonymity(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source.txt"
    path.write_text("Quarterly report.")
    model = SimpleNamespace(
        redact=lambda _: SimpleNamespace(
            text="Quarterly report.", warning=None, detected_spans=[]
        )
    )
    assert filter_document(path, model).redacted_text == "Quarterly report."


def test_saved_results_are_sanitized_and_survive_restart(settings: Settings) -> None:
    original = settings.input_root / "Alice.txt"
    original.write_text("Alice original secret")
    service = FilterService(settings, fake_backend)
    result = service.filter_file("Alice.txt")
    reader = FilterService(settings, fake_backend)
    assert (
        reader.read_result(result["artifact_id"])["redacted_text"]
        == "[PRIVATE_PERSON] works here."
    )
    assert "Alice" not in json.dumps(result)
    assert (
        "Alice" not in (Path(result["output_path"]).parent / "receipt.json").read_text()
    )
    assert original.read_text() == "Alice original secret"
    assert Path(result["output_path"]).read_text() == "[PRIVATE_PERSON] works here."


def test_result_pagination(settings: Settings) -> None:
    (settings.input_root / "a.txt").write_text("Alice")
    service = FilterService(settings, fake_backend)
    receipt = service.filter_file("a.txt")
    assert service.read_result(receipt["artifact_id"], offset=17, limit=5) == {
        "artifact_id": receipt["artifact_id"],
        "redacted_text": "works",
        "total_characters": 28,
        "next_offset": 22,
    }


def test_read_detects_modified_artifact(settings: Settings) -> None:
    (settings.input_root / "a.txt").write_text("Alice")
    service = FilterService(settings, fake_backend)
    receipt = service.filter_file("a.txt")
    Path(receipt["output_path"]).write_text("replaced with raw content")
    with pytest.raises(FilterError, match="artifact_integrity_failed"):
        service.read_result(receipt["artifact_id"])


@pytest.mark.parametrize(
    "path,code",
    [
        ("../outside.txt", "outside_input_directory"),
        ("missing.txt", "file_access_failed"),
        (".", "not_a_file"),
        ("bad.exe", "unsupported_format"),
    ],
)
def test_file_access_is_bounded(settings: Settings, path: str, code: str) -> None:
    (settings.input_root.parent / "outside.txt").write_text("outside")
    (settings.input_root / "bad.exe").write_text("not supported")
    with pytest.raises(FilterError, match=code):
        FilterService(settings, fake_backend).filter_file(path)


def test_symlink_escape_is_rejected(settings: Settings) -> None:
    outside = settings.input_root.parent / "outside.txt"
    outside.write_text("outside")
    (settings.input_root / "link.txt").symlink_to(outside)
    with pytest.raises(FilterError, match="outside_input_directory"):
        FilterService(settings, fake_backend).filter_file("link.txt")


def test_missing_model_never_starts_worker(settings: Settings) -> None:
    (settings.model_root / "ready.json").unlink()
    service = FilterService(
        settings, lambda *_: pytest.fail("inference must not start")
    )
    assert service.status()["model_ready"] is False
    with pytest.raises(FilterError, match="model_not_prepared"):
        service.filter_file("a.txt")


def test_wrong_model_revision_is_not_ready(settings: Settings) -> None:
    (settings.model_root / "ready.json").write_text('{"model_revision":"wrong"}')
    assert settings.ready() is False


def test_batch_reports_partial_failure_without_source_paths(settings: Settings) -> None:
    (settings.input_root / "Alice.txt").write_text("Alice")
    result = FilterService(settings, fake_backend).filter_batch(
        ["Alice.txt", "missing-secret.txt"]
    )
    assert result["results"][0]["ok"] is True
    assert result["results"][1] == {
        "index": 1,
        "ok": False,
        "error": "file_access_failed",
    }
    assert "Alice" not in json.dumps(result)
    assert "missing-secret" not in json.dumps(result)


@pytest.mark.parametrize("count", [0, 6])
def test_batch_size_is_bounded(settings: Settings, count: int) -> None:
    with pytest.raises(FilterError, match="batch_requires_one_to_five_files"):
        FilterService(settings).filter_batch(["a.txt"] * count)


@pytest.mark.parametrize(
    "artifact_id,offset,limit,code",
    [
        ("../secret", 0, 10, "invalid_artifact_id"),
        ("a" * 32, -1, 10, "invalid_read_range"),
        ("a" * 32, 0, 16001, "invalid_read_range"),
        ("a" * 32, 0, 10, "artifact_unavailable"),
    ],
)
def test_result_reads_are_bounded(
    settings: Settings, artifact_id: str, offset: int, limit: int, code: str
) -> None:
    with pytest.raises(FilterError, match=code):
        FilterService(settings).read_result(artifact_id, offset, limit)


@pytest.mark.parametrize(
    "payload",
    [
        {"text": "original", "detected_spans": ["secret"]},
        {
            "redacted_text": "safe",
            "detection_counts": {"original secret": 1},
            "source_characters": 8,
        },
        {"error": "original content in error"},
        {"error": []},
    ],
)
def test_worker_response_cannot_smuggle_source_fields(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, payload: dict
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(payload)),
    )
    with pytest.raises(FilterError) as caught:
        run_worker(settings.input_root / "a.txt", settings)
    assert "original" not in str(caught.value)
    assert "secret" not in str(caught.value)


def test_worker_timeout_is_safe(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("raw source", 600, output="original text")

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(FilterError, match="^processing_timeout$"):
        run_worker(settings.input_root / "a.txt", settings)


def test_stdio_server_lists_four_tools_and_sanitizes_errors(settings: Settings) -> None:
    async def exercise():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[
                "-I",
                "-m",
                "mparanza_privacy_filter.server",
                "--input-dir",
                str(settings.input_root),
                "--output-dir",
                str(settings.output_root),
                "--model-dir",
                str(settings.model_root),
            ],
        )
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listing = await session.list_tools()
                status = await session.call_tool("privacy_filter_status", {})
                failure = await session.call_tool(
                    "privacy_filter_file", {"path": "missing-sensitive-name.txt"}
                )
                return listing, status, failure

    listing, status, failure = asyncio.run(exercise())
    assert {tool.name for tool in listing.tools} == {
        "privacy_filter_status",
        "privacy_filter_file",
        "privacy_filter_batch",
        "privacy_filter_read",
    }
    assert status.isError is False
    assert failure.isError is True
    assert "missing-sensitive-name" not in failure.model_dump_json()


def test_mcp_filtered_response_contains_only_safe_artifact(settings: Settings) -> None:
    (settings.input_root / "Alice.txt").write_text("Alice")
    server = create_server(FilterService(settings, fake_backend))
    response = asyncio.run(
        server.call_tool("privacy_filter_file", {"path": "Alice.txt"})
    )
    assert "Alice" not in repr(response)
    assert "artifact_id" in repr(response)


def test_installer_config_quotes_paths_as_valid_toml(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "privacy_install", Path(__file__).parents[1] / "install.py"
    )
    assert spec and spec.loader
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    config = tomllib.loads(
        installer.config_text(
            tmp_path / "python",
            tmp_path / 'input "quoted"',
            tmp_path / "output",
            tmp_path / "model",
        )
    )
    assert config["mcp_servers"]["privacy_filter"]["args"][4] == str(
        tmp_path / 'input "quoted"'
    )


@pytest.mark.parametrize("operation", ["redact", "upstream_error", "network_attempt"])
def test_worker_entrypoint_suppresses_raw_errors_and_network(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    from mparanza_privacy_filter import worker

    path = settings.input_root / "source.txt"
    path.write_text("Alice works here.")

    def model_factory(**kwargs):
        if operation == "upstream_error":
            raise RuntimeError("Alice source data in upstream exception")
        if operation == "network_attempt":
            with socket.socket() as connection:
                connection.connect(("127.0.0.1", 9))
        return fake_model("Alice works here.")

    output = io.StringIO()
    monkeypatch.setattr(socket, "socket", socket.socket)
    for name in (
        "HF_HUB_OFFLINE",
        "HF_HUB_DISABLE_TELEMETRY",
        "OPF_TORCH_COMPILE",
        "TIKTOKEN_CACHE_DIR",
    ):
        monkeypatch.setenv(name, "")
    monkeypatch.setitem(sys.modules, "opf", SimpleNamespace(OPF=model_factory))
    monkeypatch.setitem(
        sys.modules, "torch", SimpleNamespace(set_num_threads=lambda _: None)
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
                    "tokenizer_cache": str(settings.tokenizer_cache),
                    "device": "cpu",
                }
            )
        ),
    )
    monkeypatch.setattr(sys, "stdout", output)
    worker.main()
    assert "Alice" not in output.getvalue()
    expected = (
        {
            "redacted_text": "[PRIVATE_PERSON] works here.",
            "detection_counts": {"private_person": 1},
            "source_characters": 17,
        }
        if operation == "redact"
        else {"error": "processing_failed"}
    )
    assert json.loads(output.getvalue()) == expected


def test_prepare_downloads_pinned_model_and_warms_tokenizer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mparanza_privacy_filter.prepare import prepare_model

    calls = []

    def download(**kwargs):
        calls.append(kwargs)
        checkpoint = Path(kwargs["local_dir"]) / "original"
        checkpoint.mkdir(parents=True)
        (checkpoint / "config.json").write_text('{"encoding":"o200k_base"}')

    encodings = []
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", "")
    monkeypatch.setitem(
        sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=download)
    )
    monkeypatch.setitem(
        sys.modules,
        "tiktoken",
        SimpleNamespace(get_encoding=lambda name: encodings.append(name)),
    )
    prepare_model(tmp_path / "model")
    assert calls[0]["repo_id"] == "openai/privacy-filter"
    assert calls[0]["revision"] == MODEL_REVISION
    assert calls[0]["allow_patterns"] == ["original/*"]
    assert calls[0]["token"] is False
    assert encodings == ["o200k_base"]
    assert (
        json.loads((tmp_path / "model" / "ready.json").read_text())["model_revision"]
        == MODEL_REVISION
    )


@pytest.mark.parametrize(
    "tool,arguments",
    [
        ("privacy_filter_read", {"artifact_id": "../raw"}),
        ("privacy_filter_batch", {"paths": []}),
    ],
)
def test_mcp_reports_safe_errors(
    settings: Settings, tool: str, arguments: dict
) -> None:
    from mcp.server.fastmcp.exceptions import ToolError

    server = create_server(FilterService(settings, fake_backend))
    with pytest.raises(ToolError):
        asyncio.run(server.call_tool(tool, arguments))


def test_mcp_batch_and_read_roundtrip(settings: Settings) -> None:
    (settings.input_root / "a.txt").write_text("Alice")
    service = FilterService(settings, fake_backend)
    artifact = service.filter_file("a.txt")
    server = create_server(service)
    response = asyncio.run(
        server.call_tool(
            "privacy_filter_read", {"artifact_id": artifact["artifact_id"]}
        )
    )
    assert "[PRIVATE_PERSON]" in repr(response)
    assert "Alice" not in repr(response)
