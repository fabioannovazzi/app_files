from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from email.message import EmailMessage
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT_ROOT = ROOT / "plugins" / "studio-archive"
ARCHIVE_CORE_PATH = COMPONENT_ROOT / "scripts" / "archive_core.py"
MCP_SERVER_PATH = COMPONENT_ROOT / "mcp" / "server.cjs"


@pytest.fixture(scope="module")
def archive_core() -> ModuleType:
    """Load the component core without changing production import paths."""

    module_name = "test_vera_studio_archive_core"
    spec = importlib.util.spec_from_file_location(module_name, ARCHIVE_CORE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def indexed_archive(
    tmp_path: Path,
    archive_core: ModuleType,
) -> SimpleNamespace:
    """Create a small indexed archive with two client scopes and root material."""

    archive_root = tmp_path / "Studio"
    rossi = archive_root / "Rossi"
    bianchi = archive_root / "Bianchi"
    rossi.mkdir(parents=True)
    bianchi.mkdir()
    source = rossi / "precedente.md"
    source.write_text(
        "Verbale cessione quote\nIl socio approva la cessione delle quote.",
        encoding="utf-8",
    )
    (bianchi / "nota.txt").write_text(
        "Promemoria interno sul ravvedimento operoso.",
        encoding="utf-8",
    )
    (archive_root / "procedura.txt").write_text(
        "Procedura generale dello studio per il controllo documentale.",
        encoding="utf-8",
    )
    state_dir = tmp_path / "private-state"
    archive_core.configure_archive(archive_root, state_dir=state_dir)
    archive_core.refresh_archive(state_dir=state_dir)
    status = archive_core.studio_archive_status(state_dir=state_dir)
    scopes = {item["display_name"]: item["scope_id"] for item in status["scopes"]}
    return SimpleNamespace(
        root=archive_root,
        state=state_dir,
        source=source,
        scopes=scopes,
    )


def _node_executable() -> str:
    node = shutil.which("node")
    if node is not None:
        return node
    candidates = sorted(
        (Path.home() / ".cache" / "codex-runtimes").glob("*/dependencies/node/bin/node")
    )
    if not candidates:
        pytest.skip("The Codex-bundled Node.js runtime is required.")
    return candidates[-1].as_posix()


def _mcp_request(
    payload: dict[str, Any],
    *,
    state_dir: Path,
) -> dict[str, Any]:
    environment = os.environ.copy()
    environment["VERA_STUDIO_ARCHIVE_PYTHON"] = sys.executable
    environment["VERA_STUDIO_ARCHIVE_STATE_DIR"] = str(state_dir)
    completed = subprocess.run(
        [_node_executable(), str(MCP_SERVER_PATH), "--stdio"],
        cwd=COMPONENT_ROOT,
        env=environment,
        input=json.dumps(payload) + "\n",
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )
    responses = [
        json.loads(line) for line in completed.stdout.splitlines() if line.strip()
    ]
    return next(
        response for response in responses if response.get("id") == payload["id"]
    )


def _mcp_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    state_dir: Path,
    request_id: int = 1,
) -> dict[str, Any]:
    response = _mcp_request(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        state_dir=state_dir,
    )
    return response["result"]


def test_status_without_configuration_does_not_create_state(
    tmp_path: Path,
    archive_core: ModuleType,
) -> None:
    state_dir = tmp_path / "absent-state"

    result = archive_core.studio_archive_status(state_dir=state_dir)

    assert result == {
        "configured": False,
        "document_count": 0,
        "chunk_count": 0,
        "last_refresh_at": None,
        "scopes": [],
        "needs_ocr_document_count": 0,
        "partial_document_count": 0,
        "failed_document_count": 0,
        "scan_issue_count": 0,
        "scan_issues": [],
        "scan_issues_truncated": False,
        "document_issue_count": 0,
        "document_issues": [],
        "document_issues_truncated": False,
    }
    assert not state_dir.exists()


def test_configure_rejects_state_inside_source_without_writing_it(
    tmp_path: Path,
    archive_core: ModuleType,
) -> None:
    archive_root = tmp_path / "Studio"
    archive_root.mkdir()
    (archive_root / "Client").mkdir()
    nested_state = archive_root / ".private-index"

    with pytest.raises(
        archive_core.ArchiveError,
        match="must not contain one another",
    ):
        archive_core.configure_archive(archive_root, state_dir=nested_state)

    assert not nested_state.exists()


def test_two_professionals_build_separate_indexes_from_same_archive(
    tmp_path: Path,
    archive_core: ModuleType,
) -> None:
    archive_root = tmp_path / "Shared Studio"
    client_root = archive_root / "Rossi"
    client_root.mkdir(parents=True)
    (client_root / "memo.txt").write_text(
        "Precedente dello studio sulla trasformazione societaria.",
        encoding="utf-8",
    )
    fabio_state = tmp_path / "Fabio private"
    paolo_state = tmp_path / "Paolo private"

    for state_dir in (fabio_state, paolo_state):
        archive_core.configure_archive(archive_root, state_dir=state_dir)
        archive_core.refresh_archive(state_dir=state_dir)

    fabio_status = archive_core.studio_archive_status(state_dir=fabio_state)
    paolo_status = archive_core.studio_archive_status(state_dir=paolo_state)
    assert fabio_status["document_count"] == paolo_status["document_count"] == 1
    assert fabio_status["scopes"] == paolo_status["scopes"]
    assert (fabio_state / "archive.sqlite3").is_file()
    assert (paolo_state / "archive.sqlite3").is_file()
    assert (fabio_state / "archive.sqlite3") != (paolo_state / "archive.sqlite3")
    assert stat.S_IMODE(fabio_state.stat().st_mode) == 0o700
    assert stat.S_IMODE((fabio_state / "archive.sqlite3").stat().st_mode) == 0o600
    assert stat.S_IMODE((fabio_state / "config.json").stat().st_mode) == 0o600


def test_incremental_refresh_skips_unchanged_files(
    indexed_archive: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    result = archive_core.refresh_archive(state_dir=indexed_archive.state)

    assert result["discovered_files"] == 3
    assert result["unchanged_files"] == 3
    assert result["indexed_files"] == 0
    assert result["removed_files"] == 0


def test_repeating_same_configuration_is_idempotent(
    indexed_archive: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    config_path = indexed_archive.state / "config.json"
    before = config_path.read_bytes()

    result = archive_core.configure_archive(
        indexed_archive.root,
        state_dir=indexed_archive.state,
    )

    assert result["index_requires_refresh"] is False
    assert config_path.read_bytes() == before


def test_reconfigure_recovers_after_top_level_scope_is_renamed(
    tmp_path: Path,
    archive_core: ModuleType,
) -> None:
    archive_root = tmp_path / "Studio"
    original_scope = archive_root / "Rossi"
    original_scope.mkdir(parents=True)
    state_dir = tmp_path / "state"
    archive_core.configure_archive(archive_root, state_dir=state_dir)
    original_scope.rename(archive_root / "Rossi-Srl")

    result = archive_core.configure_archive(archive_root, state_dir=state_dir)

    assert [scope["display_name"] for scope in result["scopes"]] == ["Rossi-Srl"]
    assert result["index_requires_refresh"] is True


def test_status_detects_new_top_level_scope_before_refresh(
    indexed_archive: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    new_scope = indexed_archive.root / "Verdi"
    new_scope.mkdir()
    (new_scope / "nota.txt").write_text(
        "Nuova pratica aggiunta dopo la configurazione.",
        encoding="utf-8",
    )

    result = archive_core.studio_archive_status(state_dir=indexed_archive.state)

    assert result["scope_configuration_changed"] is True
    assert result["index_requires_refresh"] is True
    assert {scope["display_name"] for scope in result["scopes"]} == {
        "Bianchi",
        "Rossi",
        "Studio",
        "Verdi",
    }


def test_refresh_adopts_and_indexes_new_top_level_scope(
    indexed_archive: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    new_scope = indexed_archive.root / "Verdi"
    new_scope.mkdir()
    (new_scope / "nota.txt").write_text(
        "Nuova pratica sulla liquidazione societaria.",
        encoding="utf-8",
    )

    result = archive_core.refresh_archive(state_dir=indexed_archive.state)

    assert result["scope_configuration_changed"] is True
    assert result["document_count"] == 4
    assert {scope["display_name"] for scope in result["scopes"]} == {
        "Bianchi",
        "Rossi",
        "Studio",
        "Verdi",
    }


def test_incremental_refresh_reindexes_changed_file(
    indexed_archive: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    indexed_archive.source.write_text(
        "Verbale cessione quote aggiornato\nNuova clausola di prelazione.",
        encoding="utf-8",
    )

    result = archive_core.refresh_archive(state_dir=indexed_archive.state)

    assert result["indexed_files"] == 1
    assert result["unchanged_files"] == 2
    assert result["removed_files"] == 0


def test_refresh_hashes_same_size_same_timestamp_content_changes(
    indexed_archive: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    original = "alpha evidence"
    replacement = "omega evidence"
    assert len(original) == len(replacement)
    indexed_archive.source.write_text(original, encoding="utf-8")
    archive_core.refresh_archive(state_dir=indexed_archive.state)
    metadata = indexed_archive.source.stat()
    indexed_archive.source.write_text(replacement, encoding="utf-8")
    os.utime(
        indexed_archive.source,
        ns=(metadata.st_atime_ns, metadata.st_mtime_ns),
    )

    refresh = archive_core.refresh_archive(state_dir=indexed_archive.state)
    candidates = archive_core.search_archive(
        "omega",
        scope_id=indexed_archive.scopes["Rossi"],
        state_dir=indexed_archive.state,
    )

    assert refresh["indexed_files"] == 1
    assert refresh["unchanged_files"] == 2
    assert candidates["result_count"] == 1


def test_incremental_refresh_removes_deleted_file(
    indexed_archive: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    indexed_archive.source.unlink()

    result = archive_core.refresh_archive(state_dir=indexed_archive.state)

    assert result["removed_files"] == 1
    assert result["document_count"] == 2


def test_refresh_securely_removes_deleted_fts_text(
    tmp_path: Path,
    archive_core: ModuleType,
) -> None:
    archive_root = tmp_path / "Studio"
    client_root = archive_root / "Rossi"
    client_root.mkdir(parents=True)
    source = client_root / "secret.txt"
    unique_text = "supersecretuniqueterm"
    source.write_text(unique_text, encoding="utf-8")
    state_dir = tmp_path / "state"
    archive_core.configure_archive(archive_root, state_dir=state_dir)
    archive_core.refresh_archive(state_dir=state_dir)
    source.unlink()

    result = archive_core.refresh_archive(state_dir=state_dir)

    assert result["removed_files"] == 1
    assert (
        unique_text.encode("utf-8") not in (state_dir / "archive.sqlite3").read_bytes()
    )


def test_search_is_confined_to_exact_scope(
    indexed_archive: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    result = archive_core.search_archive(
        "cessione quote",
        scope_id=indexed_archive.scopes["Bianchi"],
        state_dir=indexed_archive.state,
    )

    assert result["result_count"] == 0
    assert result["scope_id"] == indexed_archive.scopes["Bianchi"]


def test_search_and_open_return_verified_citation(
    indexed_archive: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    candidates = archive_core.search_archive(
        "cessione quote",
        scope_id=indexed_archive.scopes["Rossi"],
        state_dir=indexed_archive.state,
    )
    source_id = candidates["results"][0]["source_id"]

    result = archive_core.open_archive_source(
        source_id,
        state_dir=indexed_archive.state,
    )

    assert result["source_verified"] is True
    assert result["relative_path"] == "Rossi/precedente.md"
    assert result["citation"] == "Rossi/precedente.md, lines 1-2"
    assert "cessione delle quote" in result["fragments"][0]["text"]


def test_open_rejects_source_changed_after_search(
    indexed_archive: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    candidates = archive_core.search_archive(
        "cessione quote",
        scope_id=indexed_archive.scopes["Rossi"],
        state_dir=indexed_archive.state,
    )
    source_id = candidates["results"][0]["source_id"]
    indexed_archive.source.write_text(
        "The source changed after the search result was returned.",
        encoding="utf-8",
    )

    with pytest.raises(
        archive_core.SourceChangedError,
        match="changed after indexing",
    ):
        archive_core.open_archive_source(
            source_id,
            state_dir=indexed_archive.state,
        )


def test_status_search_and_open_leave_database_bytes_unchanged(
    indexed_archive: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    database_path = indexed_archive.state / "archive.sqlite3"
    before = hashlib.sha256(database_path.read_bytes()).hexdigest()
    candidates = archive_core.search_archive(
        "cessione quote",
        scope_id=indexed_archive.scopes["Rossi"],
        state_dir=indexed_archive.state,
    )
    archive_core.open_archive_source(
        candidates["results"][0]["source_id"],
        state_dir=indexed_archive.state,
    )
    status_result = archive_core.studio_archive_status(state_dir=indexed_archive.state)

    after = hashlib.sha256(database_path.read_bytes()).hexdigest()

    assert status_result["configured"]
    assert after == before


def test_root_files_have_a_non_overlapping_scope(
    indexed_archive: SimpleNamespace,
    archive_core: ModuleType,
) -> None:
    root_scope = indexed_archive.scopes["Studio"]

    result = archive_core.search_archive(
        "controllo documentale",
        scope_id=root_scope,
        state_dir=indexed_archive.state,
    )

    assert result["result_count"] == 1
    assert result["results"][0]["relative_path"] == "procedura.txt"


def test_refresh_reports_skipped_paths_and_reasons(
    tmp_path: Path,
    archive_core: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_root = tmp_path / "Studio"
    client_root = archive_root / "Rossi"
    client_root.mkdir(parents=True)
    (client_root / "legacy.msg").write_text("unsupported", encoding="utf-8")
    (client_root / "large.txt").write_text("too large", encoding="utf-8")
    monkeypatch.setattr(archive_core, "MAX_FILE_BYTES", 4)
    state_dir = tmp_path / "state"
    archive_core.configure_archive(archive_root, state_dir=state_dir)

    result = archive_core.refresh_archive(state_dir=state_dir)

    assert result["scan_issue_count"] == 2
    assert result["scan_issues_truncated"] is False
    assert result["scan_issues"] == [
        {
            "scope_id": result["scopes"][0]["scope_id"],
            "relative_path": "Rossi/large.txt",
            "reason": "file_size_limit_exceeded",
            "size_bytes": 9,
        },
        {
            "scope_id": result["scopes"][0]["scope_id"],
            "relative_path": "Rossi/legacy.msg",
            "reason": "unsupported_extension",
            "size_bytes": 11,
        },
    ]


def test_pdf_search_preserves_physical_page_locator(
    tmp_path: Path,
    archive_core: ModuleType,
) -> None:
    fitz = pytest.importorskip("fitz", reason="PyMuPDF creates the test PDF.")
    archive_root = tmp_path / "Studio"
    client_root = archive_root / "Rossi"
    client_root.mkdir(parents=True)
    pdf_path = client_root / "verbale.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "Verbale assemblea: deliberata trasformazione societaria con voto unanime.",
    )
    document.save(pdf_path)
    document.close()
    state_dir = tmp_path / "state"
    archive_core.configure_archive(archive_root, state_dir=state_dir)
    archive_core.refresh_archive(state_dir=state_dir)
    scope_id = archive_core.studio_archive_status(state_dir=state_dir)["scopes"][0][
        "scope_id"
    ]
    candidates = archive_core.search_archive(
        "trasformazione societaria",
        scope_id=scope_id,
        state_dir=state_dir,
    )

    result = archive_core.open_archive_source(
        candidates["results"][0]["source_id"],
        state_dir=state_dir,
    )

    assert result["locator_kind"] == "page"
    assert result["locator_value"] == "1"
    assert result["citation"] == "Rossi/verbale.pdf, p. 1"


def test_short_pdf_exposes_partial_status_and_ocr_limitation(
    tmp_path: Path,
    archive_core: ModuleType,
) -> None:
    fitz = pytest.importorskip("fitz", reason="PyMuPDF creates the test PDF.")
    archive_root = tmp_path / "Studio"
    client_root = archive_root / "Rossi"
    client_root.mkdir(parents=True)
    pdf_path = client_root / "codice.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "VAT123")
    document.save(pdf_path)
    document.close()
    state_dir = tmp_path / "state"
    archive_core.configure_archive(archive_root, state_dir=state_dir)
    archive_core.refresh_archive(state_dir=state_dir)
    scope_id = archive_core.studio_archive_status(state_dir=state_dir)["scopes"][0][
        "scope_id"
    ]

    candidates = archive_core.search_archive(
        "VAT123",
        scope_id=scope_id,
        state_dir=state_dir,
    )
    opened = archive_core.open_archive_source(
        candidates["results"][0]["source_id"],
        state_dir=state_dir,
    )

    assert candidates["results"][0]["document_status"] == "partial"
    assert candidates["results"][0]["needs_ocr"] is True
    assert candidates["results"][0]["limitations"] == ["page_1_no_extractable_text"]
    assert opened["document_status"] == "partial"
    assert opened["needs_ocr"] is True
    assert opened["limitations"] == ["page_1_no_extractable_text"]


def test_empty_ocr_result_does_not_erase_short_native_pdf_text(
    tmp_path: Path,
    archive_core: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fitz = pytest.importorskip("fitz", reason="PyMuPDF creates the test PDF.")
    archive_root = tmp_path / "Studio"
    client_root = archive_root / "Rossi"
    client_root.mkdir(parents=True)
    pdf_path = client_root / "codice.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "VAT123")
    document.save(pdf_path)
    document.close()
    fake_ocr = ModuleType("vera_ocr")
    fake_ocr.extract_text_from_image_bytes = lambda *args, **kwargs: SimpleNamespace(  # type: ignore[attr-defined]
        network_used=False,
        warnings=("no_text_detected",),
        status="ok",
        text="",
    )
    monkeypatch.setitem(sys.modules, "vera_ocr", fake_ocr)
    state_dir = tmp_path / "state"
    archive_core.configure_archive(archive_root, state_dir=state_dir)
    archive_core.refresh_archive(enable_ocr=True, state_dir=state_dir)
    scope_id = archive_core.studio_archive_status(state_dir=state_dir)["scopes"][0][
        "scope_id"
    ]

    result = archive_core.search_archive(
        "VAT123",
        scope_id=scope_id,
        state_dir=state_dir,
    )

    assert result["result_count"] == 1
    assert result["results"][0]["needs_ocr"] is True
    assert "page_1_no_text_detected" in result["results"][0]["limitations"]


def test_context_fragments_each_include_their_own_citation(
    tmp_path: Path,
    archive_core: ModuleType,
) -> None:
    archive_root = tmp_path / "Studio"
    client_root = archive_root / "Rossi"
    client_root.mkdir(parents=True)
    lines = [f"ordinary evidence line {number}" for number in range(1, 121)]
    lines.append("unique closing evidence")
    (client_root / "long.txt").write_text("\n".join(lines), encoding="utf-8")
    state_dir = tmp_path / "state"
    archive_core.configure_archive(archive_root, state_dir=state_dir)
    archive_core.refresh_archive(state_dir=state_dir)
    scope_id = archive_core.studio_archive_status(state_dir=state_dir)["scopes"][0][
        "scope_id"
    ]
    candidates = archive_core.search_archive(
        "unique closing",
        scope_id=scope_id,
        state_dir=state_dir,
    )

    result = archive_core.open_archive_source(
        candidates["results"][0]["source_id"],
        context_chunks=1,
        state_dir=state_dir,
    )

    assert [fragment["citation"] for fragment in result["fragments"]] == [
        "Rossi/long.txt, lines 1-120",
        "Rossi/long.txt, lines 121",
    ]


def test_office_and_email_sources_keep_structural_locators(
    tmp_path: Path,
    archive_core: ModuleType,
) -> None:
    from docx import Document
    from openpyxl import Workbook

    archive_root = tmp_path / "Studio"
    client_root = archive_root / "Rossi"
    client_root.mkdir(parents=True)

    document = Document()
    document.add_paragraph("Mandato professionale per assistenza societaria.")
    document.save(client_root / "mandato.docx")

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Dati"
    worksheet.append(["Voce", "Importo"])
    worksheet.append(["Acconto imposte", 1250])
    workbook.save(client_root / "acconti.xlsx")
    workbook.close()

    message = EmailMessage()
    message["Subject"] = "Conferma assemblea"
    message["From"] = "cliente@example.invalid"
    message["To"] = "studio@example.invalid"
    message.set_content("Confermo la data della delibera assembleare.")
    (client_root / "conferma.eml").write_bytes(message.as_bytes())

    state_dir = tmp_path / "state"
    archive_core.configure_archive(archive_root, state_dir=state_dir)
    archive_core.refresh_archive(state_dir=state_dir)
    scope_id = archive_core.studio_archive_status(state_dir=state_dir)["scopes"][0][
        "scope_id"
    ]

    docx_candidates = archive_core.search_archive(
        "mandato professionale",
        scope_id=scope_id,
        state_dir=state_dir,
    )
    xlsx_candidates = archive_core.search_archive(
        "acconto imposte",
        scope_id=scope_id,
        state_dir=state_dir,
    )
    eml_candidates = archive_core.search_archive(
        "delibera assembleare",
        scope_id=scope_id,
        state_dir=state_dir,
    )
    docx_source = archive_core.open_archive_source(
        docx_candidates["results"][0]["source_id"],
        state_dir=state_dir,
    )
    xlsx_source = archive_core.open_archive_source(
        xlsx_candidates["results"][0]["source_id"],
        state_dir=state_dir,
    )
    eml_source = archive_core.open_archive_source(
        eml_candidates["results"][0]["source_id"],
        state_dir=state_dir,
    )

    assert docx_source["locator_kind"] == "paragraphs"
    assert docx_source["citation"] == "Rossi/mandato.docx, paragraphs 1"
    assert xlsx_source["locator_kind"] == "sheet"
    assert xlsx_source["locator_value"] == "Dati!rows 1-2"
    assert eml_source["locator_kind"] == "message lines"
    assert eml_source["relative_path"] == "Rossi/conferma.eml"


def test_enabling_ocr_retries_unchanged_scan_without_model_download(
    tmp_path: Path,
    archive_core: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_module = pytest.importorskip(
        "PIL.Image",
        reason="Pillow creates the local scan fixture.",
    )
    archive_root = tmp_path / "Studio"
    client_root = archive_root / "Rossi"
    client_root.mkdir(parents=True)
    image_module.new("RGB", (120, 60), color="white").save(
        client_root / "scansione.png"
    )
    state_dir = tmp_path / "state"
    archive_core.configure_archive(archive_root, state_dir=state_dir)
    initial = archive_core.refresh_archive(
        enable_ocr=False,
        state_dir=state_dir,
    )
    calls: list[tuple[str, bool]] = []
    fake_ocr = ModuleType("vera_ocr")

    def extract_text_from_image_bytes(
        image_bytes: bytes,
        *,
        language: str,
        allow_model_download: bool,
    ) -> SimpleNamespace:
        assert image_bytes
        calls.append((language, allow_model_download))
        return SimpleNamespace(
            network_used=False,
            warnings=(),
            status="ok",
            text="Scansione locale della dichiarazione fiscale verificabile.",
        )

    fake_ocr.extract_text_from_image_bytes = extract_text_from_image_bytes  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "vera_ocr", fake_ocr)

    result = archive_core.refresh_archive(
        enable_ocr=True,
        state_dir=state_dir,
    )

    assert initial["needs_ocr_files"] == 1
    assert result["indexed_files"] == 1
    assert result["unchanged_files"] == 0
    assert result["needs_ocr_files"] == 0
    assert calls == [("it", False)]


def test_zero_chunk_document_is_named_in_all_evidence_responses(
    tmp_path: Path,
    archive_core: ModuleType,
) -> None:
    image_module = pytest.importorskip(
        "PIL.Image",
        reason="Pillow creates the local scan fixture.",
    )
    archive_root = tmp_path / "Studio"
    client_root = archive_root / "Rossi"
    client_root.mkdir(parents=True)
    image_module.new("RGB", (120, 60), color="white").save(
        client_root / "scansione.png"
    )
    (client_root / "nota.txt").write_text(
        "Precedente verificabile sul ravvedimento.",
        encoding="utf-8",
    )
    state_dir = tmp_path / "state"
    configured = archive_core.configure_archive(archive_root, state_dir=state_dir)
    scope_id = configured["scopes"][0]["scope_id"]

    refreshed = archive_core.refresh_archive(state_dir=state_dir)
    status = archive_core.studio_archive_status(state_dir=state_dir)
    candidates = archive_core.search_archive(
        "ravvedimento",
        scope_id=scope_id,
        state_dir=state_dir,
    )
    opened = archive_core.open_archive_source(
        candidates["results"][0]["source_id"],
        state_dir=state_dir,
    )

    expected_issue = {
        "scope_id": scope_id,
        "relative_path": "Rossi/scansione.png",
        "document_status": "partial",
        "needs_ocr": True,
        "limitations": ["ocr_disabled"],
        "chunk_count": 0,
    }
    assert refreshed["document_issue_count"] == 1
    assert refreshed["document_issues"] == [expected_issue]
    assert refreshed["document_issues_truncated"] is False
    assert status["document_issue_count"] == 1
    assert status["document_issues"] == [expected_issue]
    assert status["document_issues_truncated"] is False
    assert candidates["document_issue_count"] == 1
    assert candidates["document_issues"] == [expected_issue]
    assert candidates["document_issues_truncated"] is False
    assert opened["document_issue_count"] == 1
    assert opened["document_issues"] == [expected_issue]
    assert opened["document_issues_truncated"] is False


def test_scoped_search_and_open_hide_other_scope_issues(
    tmp_path: Path,
    archive_core: ModuleType,
) -> None:
    archive_root = tmp_path / "Studio"
    bianchi_root = archive_root / "Bianchi"
    rossi_root = archive_root / "Rossi"
    bianchi_root.mkdir(parents=True)
    rossi_root.mkdir()
    (bianchi_root / "nota.txt").write_text(
        "Evidenza Bianchi verificabile.",
        encoding="utf-8",
    )
    (rossi_root / "scansione.png").write_bytes(b"not-decoded-with-ocr-disabled")
    (rossi_root / "legacy.msg").write_text("unsupported", encoding="utf-8")
    state_dir = tmp_path / "state"
    configured = archive_core.configure_archive(archive_root, state_dir=state_dir)
    scopes = {
        scope["display_name"]: scope["scope_id"] for scope in configured["scopes"]
    }
    archive_core.refresh_archive(state_dir=state_dir)

    scoped = archive_core.search_archive(
        "Evidenza Bianchi",
        scope_id=scopes["Bianchi"],
        state_dir=state_dir,
    )
    opened = archive_core.open_archive_source(
        scoped["results"][0]["source_id"],
        state_dir=state_dir,
    )
    studio_wide = archive_core.search_archive(
        "Evidenza Bianchi",
        scope_id="all",
        state_dir=state_dir,
    )

    assert scoped["results"][0]["scope_id"] == scopes["Bianchi"]
    assert scoped["scan_issue_count"] == 0
    assert scoped["scan_issues"] == []
    assert scoped["document_issue_count"] == 0
    assert scoped["document_issues"] == []
    assert opened["scope_id"] == scopes["Bianchi"]
    assert opened["scan_issue_count"] == 0
    assert opened["scan_issues"] == []
    assert opened["document_issue_count"] == 0
    assert opened["document_issues"] == []
    assert studio_wide["scan_issue_count"] == 1
    assert studio_wide["scan_issues"][0]["relative_path"] == "Rossi/legacy.msg"
    assert studio_wide["document_issue_count"] == 1
    assert studio_wide["document_issues"][0]["relative_path"] == "Rossi/scansione.png"


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits are required.")
def test_status_rejects_index_configuration_with_broad_permissions(
    tmp_path: Path,
    archive_core: ModuleType,
) -> None:
    archive_root = tmp_path / "Studio"
    (archive_root / "Rossi").mkdir(parents=True)
    state_dir = tmp_path / "state"
    archive_core.configure_archive(archive_root, state_dir=state_dir)
    (state_dir / "config.json").chmod(0o644)

    with pytest.raises(
        archive_core.ArchiveError,
        match="configuration must not be accessible",
    ):
        archive_core.studio_archive_status(state_dir=state_dir)


def test_symlinked_source_is_not_indexed(
    tmp_path: Path,
    archive_core: ModuleType,
) -> None:
    archive_root = tmp_path / "Studio"
    client_root = archive_root / "Rossi"
    client_root.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("This file must not enter the archive index.", encoding="utf-8")
    linked = client_root / "linked.txt"
    try:
        linked.symlink_to(outside)
    except OSError:
        pytest.skip("Symbolic links are unavailable in this environment.")
    state_dir = tmp_path / "state"
    archive_core.configure_archive(archive_root, state_dir=state_dir)

    result = archive_core.refresh_archive(state_dir=state_dir)

    assert result["document_count"] == 0
    assert result["chunk_count"] == 0
    assert result["scan_issue_count"] == 1
    assert result["scan_issues"] == [
        {
            "scope_id": result["scopes"][0]["scope_id"],
            "relative_path": "Rossi/linked.txt",
            "reason": "symbolic_link_not_followed",
            "size_bytes": None,
        }
    ]


def test_mcp_lists_five_strict_local_tools(tmp_path: Path) -> None:
    response = _mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        },
        state_dir=tmp_path / "state",
    )

    tools = response["result"]["tools"]
    assert {tool["name"] for tool in tools} == {
        "studio_archive_status",
        "configure_studio_archive",
        "refresh_studio_archive",
        "search_studio_archive",
        "open_studio_archive_source",
    }
    assert all(tool["inputSchema"]["additionalProperties"] is False for tool in tools)
    assert all(tool["annotations"]["openWorldHint"] is False for tool in tools)


def test_mcp_rejects_non_object_json_request(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment["VERA_STUDIO_ARCHIVE_PYTHON"] = sys.executable
    environment["VERA_STUDIO_ARCHIVE_STATE_DIR"] = str(tmp_path / "state")

    completed = subprocess.run(
        [_node_executable(), str(MCP_SERVER_PATH), "--stdio"],
        cwd=COMPONENT_ROOT,
        env=environment,
        input="null\n",
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )

    response = json.loads(completed.stdout)
    assert response == {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": -32600, "message": "invalid request"},
    }


def test_mcp_configure_refresh_search_and_open(tmp_path: Path) -> None:
    archive_root = tmp_path / "Shared Studio"
    client_root = archive_root / "Rossi"
    client_root.mkdir(parents=True)
    (client_root / "memo.txt").write_text(
        "Precedente verificato sulla cessione di partecipazioni.",
        encoding="utf-8",
    )
    state_dir = tmp_path / "Fabio private"
    configure = _mcp_tool(
        "configure_studio_archive",
        {"archive_root": str(archive_root)},
        state_dir=state_dir,
    )
    scope_id = configure["structuredContent"]["scopes"][0]["scope_id"]
    refresh = _mcp_tool(
        "refresh_studio_archive",
        {},
        state_dir=state_dir,
    )
    search = _mcp_tool(
        "search_studio_archive",
        {"query": "cessione partecipazioni", "scope_id": scope_id},
        state_dir=state_dir,
    )
    source_id = search["structuredContent"]["results"][0]["source_id"]

    result = _mcp_tool(
        "open_studio_archive_source",
        {"source_id": source_id},
        state_dir=state_dir,
    )

    assert configure["isError"] is False
    assert refresh["structuredContent"]["document_count"] == 1
    assert search["structuredContent"]["result_count"] == 1
    assert result["isError"] is False
    assert result["structuredContent"]["source_verified"] is True
    assert result["structuredContent"]["citation"] == "Rossi/memo.txt, lines 1"


def test_vera_registers_archive_as_embedded_workflow() -> None:
    components = json.loads(
        (ROOT / "plugins" / "vera" / "components.json").read_text(encoding="utf-8")
    )
    vera_mcp = json.loads(
        (ROOT / "plugins" / "vera" / ".mcp.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (ROOT / "plugins" / "vera" / ".codex-plugin" / "plugin.json").read_text(
            encoding="utf-8"
        )
    )

    assert "studio-archive" in components["plugins"]
    assert "studio-archive" not in components["workflow_roles"]
    assert vera_mcp["mcpServers"]["veraStudioArchive"]["args"][-1] == "studio-archive"
    assert manifest["version"] == "0.1.22"
    assert (
        ROOT / "plugins" / "vera" / "skills" / "studio-archive" / "SKILL.md"
    ).is_file()
