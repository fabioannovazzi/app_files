from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # Python <3.11 compatibility
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal

from email.utils import parseaddr

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from modules.auth.dependencies import maybe_current_user
from modules.auth.session import AuthenticatedUser
from modules.check_entries.backend import (
    CheckEntriesSession,
    apply_mapping,
    attach_pdfs,
    get_pdf_bytes,
    infer_mapping,
    review_mismatches,
    run_checks,
    store,
)
from modules.check_entries.constants import BeneficiaryCheckMode
from modules.notifications.notifier import notify_failed, notify_finished
from modules.pdp.language import get_navigation_label, get_page_copy, resolve_language
from modules.utilities.cache import get_cache_dir
from modules.utilities.json_record_store import JsonRecordStore

templates = Jinja2Templates(directory="templates")
router = APIRouter(prefix="/check", tags=["check entries"])
site_router = APIRouter(prefix="/check")

LOGGER = logging.getLogger(__name__)
CHECK_ENTRIES_BASE_URL = os.getenv(
    "CHECK_ENTRIES_BASE_URL", "https://mparanza.com"
).rstrip("/")
CHECK_ENTRIES_SYNC_WAIT_SECONDS = max(
    0.0,
    float(os.getenv("CHECK_ENTRIES_SYNC_WAIT_SECONDS", "15")),
)
CHECK_ENTRIES_SYNC_POLL_SECONDS = max(
    0.05,
    float(os.getenv("CHECK_ENTRIES_SYNC_POLL_SECONDS", "0.25")),
)


class RunJobStore:
    def __init__(
        self, ttl_seconds: int = 172800, db_path: str | Path | None = None
    ) -> None:
        self._ttl = ttl_seconds
        if db_path is None:
            cache_dir = get_cache_dir("check_entries_jobs")
            self._store_path = Path(cache_dir) / "jobs.json"
        else:
            self._store_path = Path(db_path)
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        self._store = JsonRecordStore(self._store_path)
        self._lock = threading.Lock()

    def create_job(self, session_id: str, payload: Dict[str, Any]) -> str:
        job_id = uuid.uuid4().hex
        now = time.time()
        notification_context = self._notification_context(job_id, payload)
        with self._lock:
            self._cleanup_locked(now)
            self._store.upsert(
                job_id,
                {
                    "job_id": job_id,
                    "session_id": session_id,
                    "status": "pending",
                    "result": "",
                    "error": None,
                    "runner_pid": None,
                    "notification_context": notification_context,
                    "created_at": now,
                    "updated_at": now,
                },
            )
        self._start_worker(job_id, session_id, payload)
        return job_id

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        row = self._store.get(job_id)
        if row is None:
            return None
        if row["status"] == "running" and self._is_stale_runner(row["runner_pid"]):
            self._mark_interrupted(job_id, row["notification_context"])
            row = self._store.get(job_id)
            if row is None:
                return None
        result_payload = row["result"] or ""
        parsed_result = None
        if result_payload:
            try:
                parsed_result = json.loads(result_payload)
            except json.JSONDecodeError:
                parsed_result = None
        return {
            "job_id": row["job_id"],
            "session_id": row["session_id"],
            "status": row["status"],
            "result": parsed_result,
            "error": row["error"],
        }

    def _get_status(self, job_id: str) -> Optional[str]:
        row = self._store.get(job_id)
        if row is None:
            return None
        return str(row.get("status") or "")

    def cancel_job(self, job_id: str) -> Optional[str]:
        with self._lock:
            row = self._store.get(job_id)
            if row is None:
                return None
            status = str(row.get("status") or "")
            if status in {"completed", "failed", "cancelled"}:
                return status
            self._store.upsert(
                job_id,
                {
                    **row,
                    "status": "cancelled",
                    "result": "",
                    "error": "Automatic check was cancelled.",
                    "runner_pid": None,
                    "updated_at": time.time(),
                },
            )
        return "cancelled"

    def clear(self) -> None:
        self._store.clear()

    def _start_worker(
        self, job_id: str, session_id: str, payload: Dict[str, Any]
    ) -> None:
        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, session_id, payload),
            daemon=True,
        )
        thread.start()

    def _run_job(self, job_id: str, session_id: str, payload: Dict[str, Any]) -> None:
        try:
            run_payload = RunRequest(**payload)
            self._update(job_id, status="running")
            if self._get_status(job_id) == "cancelled":
                return
            response = _execute_run(session_id, run_payload, job_id=job_id)
            if self._get_status(job_id) == "cancelled":
                return
        except ValueError as exc:
            if self._get_status(job_id) == "cancelled":
                return
            message = str(exc) or "Automatic check failed."
            self._update(job_id, status="failed", error=message)
            return
        except HTTPException as exc:  # reuse existing helper logic
            if self._get_status(job_id) == "cancelled":
                return
            message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            self._update(
                job_id, status="failed", error=message or "Automatic check failed."
            )
            return
        except Exception:
            if self._get_status(job_id) == "cancelled":
                return
            logging.exception("Check Entries job %s failed", job_id)
            self._update(
                job_id,
                status="failed",
                error="Automatic check failed. Please try again.",
            )
            return
        self._update(job_id, status="completed", result=response)

    @staticmethod
    def _is_stale_runner(runner_pid: object) -> bool:
        try:
            pid = int(runner_pid)
        except (TypeError, ValueError):
            return True
        if pid == os.getpid():
            return False
        if pid <= 0:
            return True
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        except OSError:
            return True
        return False

    @staticmethod
    def _notification_context(job_id: str, payload: Dict[str, Any]) -> Dict[str, str]:
        notify_lang = _map_lang_code(str(payload.get("lang") or "eng"))
        notify_email = _clean_email(
            str(payload.get("notify_email") or "")
            if payload.get("notify_email") is not None
            else None
        )
        context: Dict[str, str] = {
            "notify_email": notify_email or "",
            "notify_lang": notify_lang,
        }
        link = _build_job_link(job_id, notify_lang)
        if link:
            context["job_link"] = link
        return context

    @staticmethod
    def _parse_notification_context(raw_context: object) -> Dict[str, str]:
        if not raw_context:
            return {}
        if isinstance(raw_context, dict):
            return {str(key): str(value) for key, value in raw_context.items()}
        try:
            parsed = json.loads(str(raw_context))
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, dict):
            return {}
        return {str(key): str(value) for key, value in parsed.items()}

    def _notify_failed_from_context(self, raw_context: object) -> None:
        context = self._parse_notification_context(raw_context)
        if context.get("notify_email"):
            notify_failed("entries", context)

    def _mark_interrupted(self, job_id: str, raw_context: object) -> None:
        self._update(
            job_id,
            status="failed",
            error="Automatic check interrupted by server restart. Please run it again.",
        )
        self._notify_failed_from_context(raw_context)

    def mark_interrupted_jobs(self) -> int:
        """Fail jobs left pending/running by a previous server process."""

        with self._lock:
            rows = [
                row
                for row in self._store.all()
                if str(row.get("status") or "") in {"pending", "running"}
            ]
        for row in rows:
            self._mark_interrupted(row["job_id"], row["notification_context"])
        return len(rows)

    def _update(
        self,
        job_id: str,
        *,
        status: str,
        result: Optional[RunResponse] = None,
        error: Optional[str] = None,
    ) -> None:
        payload = ""
        if result is not None:
            payload = json.dumps(result.model_dump())
        runner_pid = os.getpid() if status == "running" else None
        row = self._store.get(job_id)
        if row is None:
            return
        if status in {"completed", "failed", "cancelled"}:
            runner_pid = None
        elif status != "running":
            runner_pid = row.get("runner_pid")
        self._store.upsert(
            job_id,
            {
                **row,
                "status": status,
                "result": payload,
                "error": error,
                "runner_pid": runner_pid,
                "updated_at": time.time(),
            },
        )

    def _cleanup_locked(self, now: float) -> None:
        cutoff = now - self._ttl
        self._store.delete_where(lambda row: float(row.get("updated_at") or 0) < cutoff)


_RUN_JOB_STORE = RunJobStore()


def _static_asset_version(path: Path) -> str:
    try:
        return str(int(path.stat().st_mtime))
    except OSError:
        return str(int(time.time()))


def _build_job_link(job_id: str, lang: str) -> str:
    if not job_id:
        return ""
    base = CHECK_ENTRIES_BASE_URL or ""
    if not base:
        return ""
    lang_code = lang or "en"
    return f"{base}/check/page?job={job_id}&lang={lang_code}"


def _build_job_response(job: Dict[str, Any]) -> RunJobStatusResponse:
    result_payload = job.get("result")
    result_obj = RunResponse(**result_payload) if result_payload else None
    status = job.get("status", "pending")
    if status not in {"pending", "running", "completed", "failed", "cancelled"}:
        status = "pending"
    session_id = job.get("session_id", "")
    return RunJobStatusResponse(
        job_id=job.get("job_id", ""),
        session_id=session_id,
        status=status,
        result=result_obj,
        error=job.get("error"),
    )


class TablePreview(BaseModel):
    columns: List[str]
    rows: List[List[Any]]


class UploadResponse(BaseModel):
    session_id: str
    filename: str
    preview: TablePreview
    columns: List[str]
    row_count: int


class MappingRequest(BaseModel):
    mapping: Dict[str, Optional[str]]


class MappingResponse(BaseModel):
    mapping: Dict[str, Optional[str]]


class RunRequest(BaseModel):
    lang: str = Field("eng", description="OCR language (eng/ita/fra/deu/spa)")
    debug: bool = False
    amount_tolerance: float = 1.0
    date_window: int = 3
    timing_difference_window: Optional[int] = 5
    beneficiary_similarity: float = 70.0
    beneficiary_check_mode: BeneficiaryCheckMode = BeneficiaryCheckMode.COMPARE
    notify_email: Optional[str] = Field(
        None, description="Optional email for notifications"
    )


def _ensure_notify_email(
    payload: RunRequest, user: AuthenticatedUser | None
) -> RunRequest:
    """Return a copy of ``payload`` with notify_email populated when missing."""

    if payload.notify_email:
        return payload
    if user and user.email:
        return payload.model_copy(update={"notify_email": user.email})
    return payload


class ResultRow(BaseModel):
    data: Dict[str, Any]


class SummaryTable(BaseModel):
    name: str
    columns: List[str]
    rows: List[List[Any]]


class RunResponse(BaseModel):
    results: List[Dict[str, Any]]
    summary_text: str
    summary_tables: List[SummaryTable]
    error_message: Optional[str]
    download_urls: Dict[str, str]
    batch_mode: bool = False


class RunJobCreateResponse(BaseModel):
    job_id: str


class RunJobStatusResponse(BaseModel):
    job_id: str
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    session_id: str
    result: Optional[RunResponse] = None
    error: Optional[str] = None


class ReviewItem(BaseModel):
    movement: str
    status: str
    reason: Optional[str] = None


class ReviewRequest(BaseModel):
    decisions: List[ReviewItem]


@site_router.get("/page", include_in_schema=False)
def check_entries_page(
    request: Request,
    job: Optional[str] = Query(None),
) -> Any:
    lang = resolve_language(request)
    page_label = get_navigation_label(lang, "/check/page")
    user = maybe_current_user(request)
    return templates.TemplateResponse(
        request,
        "check_entries_react.html",
        {
            "initial_job_id": job or "",
            "lang": lang,
            "page_label": page_label,
            "copy": get_page_copy("check_entries", lang),
            "user_email": user.email if user else "",
            "asset_version": _static_asset_version(
                Path("static/js/check-entries-react.js")
            ),
        },
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_journal(
    request: Request,
    file: UploadFile = File(...),
) -> UploadResponse:
    content = await file.read()
    try:
        session = store.create_session(
            file.filename,
            content,
            lang=_resolve_ocr_lang(resolve_language(request)),
        )
    except Exception as exc:  # pragma: no cover - surfaced to client
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    preview = _dataframe_preview(session)
    return UploadResponse(
        session_id=session.session_id,
        filename=session.filename,
        preview=TablePreview(columns=preview["columns"], rows=preview["rows"]),
        columns=session.columns,
        row_count=session.row_count,
    )


@router.post("/session/{session_id}/mapping/auto", response_model=MappingResponse)
def auto_mapping(
    session_id: str,
) -> MappingResponse:
    session = _session(session_id)
    try:
        mapping = infer_mapping(session)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MappingResponse(mapping=mapping)


@router.post("/session/{session_id}/mapping")
def submit_mapping(
    session_id: str,
    payload: MappingRequest,
) -> MappingResponse:
    session = _session(session_id)
    try:
        apply_mapping(session, payload.mapping)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MappingResponse(mapping=session.mapping)


@router.post("/session/{session_id}/pdfs")
async def upload_pdfs(
    session_id: str,
    files: List[UploadFile] = File(...),
) -> Dict[str, Any]:
    session = _session(session_id)
    pdf_payload = []
    for upload in files:
        pdf_payload.append((upload.filename, await upload.read()))
    attach_pdfs(session, pdf_payload)
    return {"count": len(session.pdf_files)}


@router.post(
    "/session/{session_id}/run",
    response_model=RunResponse | RunJobCreateResponse,
)
def run_checks_endpoint(
    session_id: str,
    payload: RunRequest,
    request: Request,
    user: AuthenticatedUser | None = Depends(maybe_current_user),
) -> RunResponse | RunJobCreateResponse:
    payload = payload.model_copy(
        update={
            "lang": _resolve_ocr_lang(resolve_language(request), fallback=payload.lang)
        }
    )
    payload = _ensure_notify_email(payload, user)
    job_id = _RUN_JOB_STORE.create_job(session_id, payload.model_dump())
    deadline = time.perf_counter() + CHECK_ENTRIES_SYNC_WAIT_SECONDS
    while time.perf_counter() < deadline:
        job = _RUN_JOB_STORE.get_job(job_id)
        if not job:
            break
        current_status = job.get("status", "pending")
        if current_status == "completed":
            result_payload = job.get("result")
            if not result_payload:
                raise HTTPException(
                    status_code=500, detail="Run completed without a result payload."
                )
            return RunResponse(**result_payload)
        if current_status == "failed":
            raise HTTPException(
                status_code=400, detail=job.get("error") or "Automatic check failed."
            )
        if current_status == "cancelled":
            raise HTTPException(
                status_code=409, detail="Automatic check was cancelled."
            )
        time.sleep(CHECK_ENTRIES_SYNC_POLL_SECONDS)

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=RunJobCreateResponse(job_id=job_id).model_dump(),
    )


@router.post("/session/{session_id}/run/jobs", response_model=RunJobCreateResponse)
def enqueue_run_job(
    session_id: str,
    payload: RunRequest,
    request: Request,
    user: AuthenticatedUser | None = Depends(maybe_current_user),
) -> RunJobCreateResponse:
    payload = payload.model_copy(
        update={
            "lang": _resolve_ocr_lang(resolve_language(request), fallback=payload.lang)
        }
    )
    payload = _ensure_notify_email(payload, user)
    job_id = _RUN_JOB_STORE.create_job(session_id, payload.model_dump())
    return RunJobCreateResponse(job_id=job_id)


@router.get(
    "/session/{session_id}/run/jobs/{job_id}", response_model=RunJobStatusResponse
)
def fetch_run_job(
    session_id: str,
    job_id: str,
) -> RunJobStatusResponse:
    job = _RUN_JOB_STORE.get_job(job_id)
    if not job or job["session_id"] != session_id:
        raise HTTPException(status_code=404, detail="Run job not found.")
    return _build_job_response(job)


@router.get("/run/jobs/{job_id}", response_model=RunJobStatusResponse)
def fetch_run_job_by_id(job_id: str) -> RunJobStatusResponse:
    job = _RUN_JOB_STORE.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Run job not found.")
    return _build_job_response(job)


@router.delete(
    "/session/{session_id}/run/jobs/{job_id}", response_model=RunJobStatusResponse
)
def cancel_run_job(
    session_id: str,
    job_id: str,
) -> RunJobStatusResponse:
    job = _RUN_JOB_STORE.get_job(job_id)
    if not job or job["session_id"] != session_id:
        raise HTTPException(status_code=404, detail="Run job not found.")
    status = _RUN_JOB_STORE.cancel_job(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Run job not found.")
    refreshed = _RUN_JOB_STORE.get_job(job_id)
    if not refreshed:
        raise HTTPException(status_code=404, detail="Run job not found.")
    return _build_job_response(refreshed)


@router.delete("/run/jobs/{job_id}", response_model=RunJobStatusResponse)
def cancel_run_job_by_id(job_id: str) -> RunJobStatusResponse:
    job = _RUN_JOB_STORE.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Run job not found.")
    status = _RUN_JOB_STORE.cancel_job(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Run job not found.")
    refreshed = _RUN_JOB_STORE.get_job(job_id)
    if not refreshed:
        raise HTTPException(status_code=404, detail="Run job not found.")
    return _build_job_response(refreshed)


@router.post("/session/{session_id}/review", response_model=RunResponse)
def review_endpoint(
    session_id: str,
    payload: ReviewRequest,
) -> RunResponse:
    session = _session(session_id)
    status_map = {item.movement: item.status for item in payload.decisions}
    reason_map = {item.movement: item.reason or "" for item in payload.decisions}
    try:
        output = review_mismatches(session, status_map, reason_map)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize_output(session, output)


@router.get("/session/{session_id}/download")
def download_artifact(
    session_id: str,
    artifact: str = Query(..., regex="^(excel|summary)$"),
) -> Response:
    session = _session(session_id)
    if not session.output:
        raise HTTPException(status_code=404, detail="No results available")
    if artifact == "excel":
        return Response(
            content=session.output.excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="check_results.xlsx"'
            },
        )
    return Response(
        content=session.output.summary_text.encode("utf-8"),
        media_type="text/plain",
        headers={"Content-Disposition": 'attachment; filename="check_summary.txt"'},
    )


@router.get("/session/{session_id}/pdf")
def download_pdf(
    session_id: str,
    movement: str = Query(...),
    token: str = Query(..., description="Session download token"),
) -> Response:
    session = _session(session_id)
    if not token or token.strip() != session.pdf_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid download token."
        )
    pdf_bytes, name = get_pdf_bytes(session, movement)
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="PDF not found for this movement")
    filename = name or f"{movement}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _session(session_id: str) -> CheckEntriesSession:
    try:
        return store.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _dataframe_preview(session: CheckEntriesSession) -> Dict[str, Any]:
    sample = session.dataframe.head(20)
    return {
        "columns": sample.columns,
        "rows": [[_serialize_value(value) for value in row] for row in sample.rows()],
    }


def _serialize_output(session: CheckEntriesSession, output) -> RunResponse:
    rows = [_prepare_row(record) for record in output.result_df.to_dicts()]  # type: ignore[attr-defined]
    summary_tables = [
        SummaryTable(
            name=name,
            columns=df.columns,
            rows=[[_serialize_value(value) for value in row] for row in df.rows()],
        )
        for name, df in output.summary_tables.items()
    ]
    return RunResponse(
        results=rows,
        summary_text=output.summary_text,
        summary_tables=summary_tables,
        error_message=output.error_message,
        download_urls={
            "excel": f"/check/session/{session.session_id}/download?artifact=excel",
            "summary": f"/check/session/{session.session_id}/download?artifact=summary",
            "pdf": f"/check/session/{session.session_id}/pdf?token={session.pdf_key}",
        },
        batch_mode=output.batch_mode,
    )


def _clean_email(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    address = value.strip()
    if not address:
        return None
    parsed = parseaddr(address)[1]
    if parsed and "@" in parsed:
        return parsed
    LOGGER.warning("Ignoring invalid email address '%s'", address)
    return None


_OCR_TO_LOCALE = {
    "eng": "en",
    "en": "en",
    "english": "en",
    "ita": "it",
    "it": "it",
    "italian": "it",
    "italiano": "it",
    "fra": "fr",
    "fr": "fr",
    "french": "fr",
    "français": "fr",
    "francais": "fr",
    "deu": "de",
    "de": "de",
    "german": "de",
    "deutsch": "de",
    "spa": "es",
    "es": "es",
    "spanish": "es",
    "español": "es",
    "espanol": "es",
}


_OCR_LANG_BY_LOCALE = {
    "en": "eng",
    "it": "ita",
    "fr": "fra",
    "de": "deu",
    "es": "spa",
}


def _resolve_ocr_lang(locale: Optional[str], *, fallback: str = "eng") -> str:
    if not locale:
        return fallback
    return _OCR_LANG_BY_LOCALE.get(locale.strip().lower(), fallback)


def _map_lang_code(raw: Optional[str]) -> str:
    if not raw:
        return "en"
    return _OCR_TO_LOCALE.get(raw.strip().lower(), "en")


def _prepare_row(record: Dict[str, Any]) -> Dict[str, Any]:
    prepared: Dict[str, Any] = {}
    for key, value in record.items():
        if hasattr(value, "to_list"):
            try:
                prepared[key] = value.to_list()
                continue
            except Exception:
                pass
        elif isinstance(value, list):
            prepared[key] = [_serialize_nested(item) for item in value]
        else:
            prepared[key] = _serialize_value(value)
    return prepared


def _serialize_nested(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    return _serialize_value(value)


def _execute_run(
    session_id: str, payload: RunRequest, job_id: Optional[str] = None
) -> RunResponse:
    session = _session(session_id)
    notify_email = _clean_email(payload.notify_email)
    notify_lang = _map_lang_code(payload.lang)
    notify_context: Dict[str, str] = {
        "notify_email": notify_email or "",
        "notify_lang": notify_lang,
    }
    if job_id:
        link = _build_job_link(job_id, notify_lang)
        if link:
            notify_context["job_link"] = link
    start_time = time.perf_counter()
    if not session.mapping:
        notify_failed("entries", notify_context)
        raise ValueError("Submit column mapping before running checks")
    try:
        output = run_checks(session, payload.dict())
    except ValueError as exc:
        notify_failed("entries", notify_context)
        raise
    except Exception as exc:  # pragma: no cover
        notify_failed("entries", notify_context)
        raise
    LOGGER.info(
        "Check entries job completed; session=%s job=%s email=%s batch=%s",
        session_id,
        job_id or "",
        notify_email or "",
        output.batch_mode,
    )
    notify_finished(time.perf_counter() - start_time, "entries", notify_context)
    return _serialize_output(session, output)


def _serialize_value(value: Any) -> Any:
    if isinstance(value, (str, int, float)) or value is None:
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    return str(value)
