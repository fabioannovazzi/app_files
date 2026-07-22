from __future__ import annotations

import asyncio
import io
import json
import sys
import types
from pathlib import Path
from typing import Any, Dict

import markupsafe
import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

if not hasattr(markupsafe, "soft_unicode"):  # pragma: no cover - compatibility shim
    markupsafe.soft_unicode = lambda value: value  # type: ignore[attr-defined]

if "journal_ingest" not in sys.modules:
    journal_ingest = types.ModuleType("journal_ingest")
    sys.modules["journal_ingest"] = journal_ingest
else:
    journal_ingest = sys.modules["journal_ingest"]

config_module = types.ModuleType("journal_ingest.config")
config_module.get_recipe = lambda *args, **kwargs: None  # type: ignore[attr-defined]
sys.modules["journal_ingest.config"] = config_module

core_module = types.ModuleType("journal_ingest.core")
ParserConfidenceError = type("ParserConfidenceError", (Exception,), {})
ValidationError = type("ValidationError", (Exception,), {})
core_module.ParserConfidenceError = ParserConfidenceError  # type: ignore[attr-defined]
core_module.ValidationError = ValidationError  # type: ignore[attr-defined]
sys.modules["journal_ingest.core"] = core_module

router_module = types.ModuleType("journal_ingest.router")
router_module.Router = type("Router", (), {})  # type: ignore[attr-defined]
sys.modules["journal_ingest.router"] = router_module

if "modules.process_pdf_journal.logic" not in sys.modules:
    logic_stub = types.ModuleType("modules.process_pdf_journal.logic")
    logic_stub.parse_journal = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    logic_stub.parse_journal_any = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    sys.modules["modules.process_pdf_journal.logic"] = logic_stub

if "modules.check_entries.backend" not in sys.modules:
    backend_stub = types.ModuleType("modules.check_entries.backend")

    class _DummySession:  # pragma: no cover - placeholder for API imports
        def __init__(self) -> None:
            self.session_id = "dummy"

    def _stub(*args, **kwargs):  # pragma: no cover - placeholder
        raise NotImplementedError("backend stub invoked")

    backend_stub.CheckEntriesSession = _DummySession  # type: ignore[attr-defined]
    backend_stub.attach_pdfs = _stub  # type: ignore[attr-defined]
    backend_stub.get_pdf_bytes = _stub  # type: ignore[attr-defined]
    backend_stub.infer_mapping = _stub  # type: ignore[attr-defined]
    backend_stub.review_mismatches = _stub  # type: ignore[attr-defined]
    backend_stub.run_checks = _stub  # type: ignore[attr-defined]
    backend_stub.apply_mapping = _stub  # type: ignore[attr-defined]
    backend_stub.store = types.SimpleNamespace(  # type: ignore[attr-defined]
        create_session=_stub,
        save=lambda session: None,
        get=_stub,
    )
    sys.modules["modules.check_entries.backend"] = backend_stub

if "multipart" not in sys.modules:
    multipart_stub = types.ModuleType("multipart")
    multipart_submodule = types.ModuleType("multipart.multipart")

    def _parse_options_header(value: str) -> tuple[str, dict]:
        return value, {}

    multipart_submodule.parse_options_header = _parse_options_header  # type: ignore[attr-defined]
    multipart_stub.multipart = multipart_submodule  # type: ignore[attr-defined]
    multipart_stub.__version__ = "0.0"  # type: ignore[attr-defined]

    sys.modules["multipart"] = multipart_stub
    sys.modules["multipart.multipart"] = multipart_submodule

from starlette.requests import Request

import modules.check_entries.api as api_mod
from modules.check_entries.api import (
    RunJobCreateResponse,
    RunJobStore,
    RunResponse,
    _map_lang_code,
    _resolve_ocr_lang,
)


@pytest.fixture()
def temp_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunJobStore:
    store = RunJobStore(db_path=tmp_path / "jobs.json", ttl_seconds=60)
    # Do not spawn worker threads during unit tests.
    monkeypatch.setattr(store, "_start_worker", lambda *args, **kwargs: None)
    return store


def _job_payload() -> Dict[str, Any]:
    # Minimal payload: RunRequest supplies sensible defaults.
    return {}


def test_resolve_ocr_lang_from_locale() -> None:
    assert _resolve_ocr_lang("en") == "eng"
    assert _resolve_ocr_lang("it") == "ita"
    assert _resolve_ocr_lang("fr") == "fra"
    assert _resolve_ocr_lang("de") == "deu"
    assert _resolve_ocr_lang("es") == "spa"


def test_upload_journal_forwards_spanish_ocr_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}
    dataframe = pl.DataFrame({"movement_number": ["1"]})

    def fake_create_session(filename: str, content: bytes, *, lang: str) -> Any:
        assert filename == "diario.pdf"
        assert content == b"%PDF-spanish"
        captured["lang"] = lang
        return types.SimpleNamespace(
            session_id="spanish-session",
            filename=filename,
            raw_content=content,
            dataframe=dataframe,
            columns=["movement_number"],
            row_count=1,
        )

    monkeypatch.setattr(api_mod.store, "create_session", fake_create_session)
    monkeypatch.setattr(api_mod, "resolve_language", lambda _request: "es")
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/check/upload",
            "query_string": b"lang=es",
            "headers": [],
        }
    )
    upload = api_mod.UploadFile(filename="diario.pdf", file=io.BytesIO(b"%PDF-spanish"))

    response = asyncio.run(api_mod.upload_journal(request, upload))

    assert captured == {"lang": "spa"}
    assert response.session_id == "spanish-session"


@pytest.mark.parametrize("raw", ("spa", "es", "spanish", "español", "espanol"))
def test_map_lang_code_recognizes_spanish_ocr_aliases(raw: str) -> None:
    assert _map_lang_code(raw) == "es"


def test_cancel_job_marks_entry_cancelled(temp_store: RunJobStore) -> None:
    job_id = temp_store.create_job("session-1", _job_payload())
    status = temp_store.cancel_job(job_id)
    assert status == "cancelled"

    job = temp_store.get_job(job_id)
    assert job is not None
    assert job["status"] == "cancelled"
    assert job["error"] == "Automatic check was cancelled."
    assert job["result"] is None


def test_mark_interrupted_jobs_fails_pending_job_and_notifies(
    temp_store: RunJobStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notifications: list[tuple[str, dict[str, str]]] = []
    payload = {"notify_email": "user@example.com", "lang": "eng"}

    monkeypatch.setattr(
        api_mod,
        "notify_failed",
        lambda step, context: notifications.append((step, dict(context))),
    )

    job_id = temp_store.create_job("session-1", payload)
    interrupted_count = temp_store.mark_interrupted_jobs()

    job = temp_store.get_job(job_id)
    assert interrupted_count == 1
    assert job is not None
    assert job["status"] == "failed"
    assert (
        job["error"]
        == "Automatic check interrupted by server restart. Please run it again."
    )
    assert notifications[0][0] == "entries"
    assert notifications[0][1]["notify_email"] == "user@example.com"
    assert notifications[0][1]["notify_lang"] == "en"
    assert f"/check/page?job={job_id}&lang=en" in notifications[0][1]["job_link"]


def test_run_job_does_not_override_cancelled_status(
    temp_store: RunJobStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = temp_store.create_job("session-2", _job_payload())

    called = False

    def fake_execute(
        session_id: str, payload: Any, job_id: str | None = None
    ) -> RunResponse:
        nonlocal called
        called = True
        # Simulate a cancellation triggered while the job is in-flight.
        if job_id:
            temp_store.cancel_job(job_id)
        return RunResponse(
            results=[],
            summary_text="done",
            summary_tables=[],
            error_message=None,
            download_urls={},
            batch_mode=False,
        )

    monkeypatch.setattr("modules.check_entries.api._execute_run", fake_execute)
    temp_store._run_job(job_id, "session-2", _job_payload())

    assert called is True
    job = temp_store.get_job(job_id)
    assert job is not None
    assert job["status"] == "cancelled"
    assert job["result"] is None


def _request_with_lang(lang: str = "en") -> Request:
    return Request(
        {
            "type": "http",
            "headers": [(b"accept-language", lang.encode("utf-8"))],
            "query_string": b"",
        }
    )


def test_run_endpoint_returns_completed_payload_when_job_finishes_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = api_mod.RunRequest()

    class _ImmediateStore:
        def create_job(self, session_id: str, payload_data: Dict[str, Any]) -> str:
            return "job-complete"

        def get_job(self, job_id: str) -> Dict[str, Any]:
            return {
                "job_id": job_id,
                "session_id": "session-1",
                "status": "completed",
                "result": {
                    "results": [],
                    "summary_text": "done",
                    "summary_tables": [],
                    "error_message": None,
                    "download_urls": {},
                    "batch_mode": True,
                },
                "error": None,
            }

    monkeypatch.setattr(api_mod, "_RUN_JOB_STORE", _ImmediateStore())

    response = api_mod.run_checks_endpoint(
        "session-1", payload, _request_with_lang("en"), user=None
    )

    assert isinstance(response, RunResponse)
    assert response.summary_text == "done"


def test_run_endpoint_returns_job_id_when_job_is_still_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = api_mod.RunRequest()

    class _PendingStore:
        def create_job(self, session_id: str, payload_data: Dict[str, Any]) -> str:
            return "job-pending"

        def get_job(self, job_id: str) -> Dict[str, Any]:
            return {
                "job_id": job_id,
                "session_id": "session-1",
                "status": "running",
                "result": None,
                "error": None,
            }

    monkeypatch.setattr(api_mod, "_RUN_JOB_STORE", _PendingStore())
    monkeypatch.setattr(api_mod, "CHECK_ENTRIES_SYNC_WAIT_SECONDS", 0.0)

    response = api_mod.run_checks_endpoint(
        "session-1", payload, _request_with_lang("en"), user=None
    )

    assert hasattr(response, "status_code")
    assert response.status_code == 202
    parsed = RunJobCreateResponse(**json.loads(response.body))
    assert parsed.job_id == "job-pending"


def test_check_entries_page_serves_react_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _fake_template_response(request, template_name, context):  # type: ignore[no-untyped-def]
        captured["request"] = request
        captured["template_name"] = template_name
        captured["context"] = context
        return PlainTextResponse("ok")

    monkeypatch.setattr(api_mod.templates, "TemplateResponse", _fake_template_response)

    app = FastAPI()
    app.include_router(api_mod.site_router)
    client = TestClient(app)

    response = client.get("/check/page?lang=it&job=job-123")

    assert response.status_code == 200
    assert response.text == "ok"
    assert captured["template_name"] == "check_entries_react.html"
    assert isinstance(captured["context"], dict)
    assert captured["context"]["lang"] == "it"
    assert captured["context"]["initial_job_id"] == "job-123"
    assert "asset_version" in captured["context"]
