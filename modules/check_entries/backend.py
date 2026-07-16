from __future__ import annotations

import io
import logging
import pickle
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional, Tuple

import polars as pl
from cryptography.fernet import Fernet

from modules.check_entries.constants import BeneficiaryCheckMode
from modules.check_entries.utils import hide_line_numbers
from modules.utilities.config import select_provider
from modules.llm.llm_call_wrapper import LLMCallWrapper
from modules.check_entries.pdf_matching import build_pdf_map
from modules.process_excel.logic import _suggest_header_row, _unique_column_names
from modules.process_pdf_journal.logic import parse_journal
try:
    from modules.utilities.fastexcel import suppress_fastexcel_dtype_warnings
except Exception:  # pragma: no cover - fallback when helper is unavailable

    @contextmanager
    def suppress_fastexcel_dtype_warnings() -> Iterable[None]:
        """Fallback context manager used when fastexcel helper is missing."""

        logger = logging.getLogger("fastexcel.types.dtype")
        previous_level = logger.level
        logger.setLevel(logging.ERROR)
        try:
            yield
        finally:
            logger.setLevel(previous_level)
from src.check_entries_review import merge_review_feedback, pdf_bytes_for
from src.check_entries.run import (
    CheckEntriesRunContext,
    CheckEntriesRunParams,
    run_check_entries,
)
from src.check_statements import (
    _detect_excel_header_polars as detect_excel_header_polars,
)
from src.check_statements import _rebuild_df_with_header as rebuild_df_with_header



LOGGER = logging.getLogger(__name__)
SESSION_STORAGE_DIR = Path("tmp") / "check_entries_sessions"


class StoredPDF:
    """Encrypted PDF stored in-session; decrypted lazily when accessed."""

    def __init__(self, name: str, ciphertext: bytes, key: str):
        self.name = name
        self._ciphertext = ciphertext
        self._key = key
        self._buffer: io.BytesIO | None = None

    def _ensure_buffer(self) -> io.BytesIO:
        if self._buffer is None:
            fernet = Fernet(self._key.encode("utf-8"))
            plaintext = fernet.decrypt(self._ciphertext)
            self._buffer = io.BytesIO(plaintext)
        return self._buffer

    def read(self) -> bytes:
        buf = self._ensure_buffer()
        return buf.read()

    def getvalue(self) -> bytes:
        buf = self._ensure_buffer()
        pos = buf.tell()
        buf.seek(0)
        data = buf.read()
        buf.seek(pos)
        return data

    def seek(self, position: int) -> None:
        buf = self._ensure_buffer()
        buf.seek(position)

    def reset(self) -> None:
        self._buffer = None

    def __getstate__(self) -> Dict[str, Any]:
        state = self.__dict__.copy()
        state["_buffer"] = None
        return state


@dataclass
class CheckRunOutput:
    result_df: pl.DataFrame
    summary_text: str
    summary_tables: Dict[str, pl.DataFrame]
    excel_bytes: bytes
    error_message: Optional[str]
    review_status: Dict[str, str] = field(default_factory=dict)
    review_reason: Dict[str, str] = field(default_factory=dict)
    batch_mode: bool = False


@dataclass
class CheckEntriesSession:
    session_id: str
    filename: str
    raw_content: bytes
    dataframe: pl.DataFrame
    columns: List[str]
    row_count: int
    mapping: Dict[str, Optional[str]] = field(default_factory=dict)
    pdf_files: List[StoredPDF] = field(default_factory=list)
    pdf_map: Dict[str, StoredPDF] = field(default_factory=dict)
    output: Optional[CheckRunOutput] = None
    pdf_key: str = field(default_factory=lambda: Fernet.generate_key().decode("utf-8"))


class CheckEntriesStore:
    def __init__(self, storage_dir: Path | None = None) -> None:
        self._sessions: Dict[str, CheckEntriesSession] = {}
        self._storage_dir = storage_dir or SESSION_STORAGE_DIR
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def create_session(self, filename: str, content: bytes) -> CheckEntriesSession:
        df = _load_dataframe_from_bytes(filename, content)
        columns = list(df.columns)
        session_id = uuid.uuid4().hex
        session = CheckEntriesSession(
            session_id=session_id,
            filename=filename,
            raw_content=content,
            dataframe=df,
            columns=columns,
            row_count=df.height,
        )
        self._sessions[session_id] = session
        self._persist(session)
        return session

    def get(self, session_id: str) -> CheckEntriesSession:
        session = self._sessions.get(session_id)
        if session is not None:
            return session
        session = self._load_from_disk(session_id)
        if session is not None:
            self._sessions[session_id] = session
            return session
        raise KeyError(f"Unknown session id {session_id}")

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        path = self._session_path(session_id)
        if path.exists():
            path.unlink()

    def save(self, session: CheckEntriesSession) -> None:
        self._sessions[session.session_id] = session
        self._persist(session)

    def _session_path(self, session_id: str) -> Path:
        return self._storage_dir / f"{session_id}.pkl"

    def _persist(self, session: CheckEntriesSession) -> None:
        path = self._session_path(session.session_id)
        tmp_path = path.with_suffix(".tmp")
        with tmp_path.open("wb") as handle:
            pickle.dump(session, handle)
        tmp_path.replace(path)

    def _load_from_disk(self, session_id: str) -> Optional[CheckEntriesSession]:
        path = self._session_path(session_id)
        if not path.exists():
            return None
        try:
            with path.open("rb") as handle:
                session: CheckEntriesSession = pickle.load(handle)
                if not getattr(session, "pdf_key", None):
                    session.pdf_key = Fernet.generate_key().decode("utf-8")
                fernet = Fernet(session.pdf_key.encode("utf-8"))
                rebuilt: Dict[str, StoredPDF] = {}
                for name, pdf in session.pdf_map.items():
                    ciphertext = getattr(pdf, "_ciphertext", None)
                    if ciphertext is None:
                        # Legacy session storing plaintext buffer
                        if hasattr(pdf, "getvalue"):
                            plaintext = pdf.getvalue()
                        else:
                            plaintext = bytes(pdf.read())
                        ciphertext = fernet.encrypt(plaintext)
                    rebuilt[name] = StoredPDF(name, ciphertext, session.pdf_key)
                session.pdf_map = rebuilt
                session.pdf_files = list(session.pdf_map.values())
                return session
        except Exception as exc:  # noqa: BLE001 - best effort
            LOGGER.warning("Failed to load check entries session %s: %s", session_id, exc)
            try:
                path.unlink()
            except OSError:
                pass
            return None


store = CheckEntriesStore()


def _load_dataframe_from_bytes(filename: str, content: bytes) -> pl.DataFrame:
    suffix = filename.lower().rsplit(".", 1)[-1]
    if suffix in {"xlsx", "xls"}:
        header_row = detect_excel_header_polars(content)
        if header_row is None:
            with suppress_fastexcel_dtype_warnings():
                raw = pl.read_excel(io.BytesIO(content), has_header=False)
            header_row = _suggest_header_row(raw)
            header_vals = [str(x) for x in raw.row(header_row)]
            header = _unique_column_names(header_vals)
            df = raw.slice(offset=header_row + 1)
            df.columns = header
            return df
        return rebuild_df_with_header(content, header_row)
    if suffix == "csv":
        raw_df = pl.read_csv(io.BytesIO(content), has_header=False)
        header_row = _suggest_header_row(raw_df)
        header_vals = [str(x) for x in raw_df.row(header_row)]
        header = _unique_column_names(header_vals)
        df = raw_df.slice(offset=header_row + 1)
        df.columns = header
        return df
    if suffix == "pdf":
        return parse_journal(content)
    header_row = detect_excel_header_polars(content)
    if header_row is None:
        raise ValueError("Could not detect header row automatically")
    return rebuild_df_with_header(content, header_row)


def _table_preview(df: pl.DataFrame, limit: int = 20) -> Dict[str, Any]:  # noqa: D401
    sample = df.head(limit)
    return {
        "columns": sample.columns,
        "rows": [[_repr_cell(value) for value in row] for row in sample.rows()],
    }


def _repr_cell(value: Any) -> Any:
    if isinstance(value, (str, int, float)) or value is None:
        return value
    if isinstance(value, bool):
        return value
    return str(value)


def attach_pdfs(session: CheckEntriesSession, files: List[Tuple[str, bytes]]) -> None:
    if not session.pdf_map:
        session.pdf_map = {}
    fernet = Fernet(session.pdf_key.encode("utf-8"))
    for name, data in files:
        ciphertext = fernet.encrypt(data)
        session.pdf_map[name] = StoredPDF(name, ciphertext, session.pdf_key)
    session.pdf_files = list(session.pdf_map.values())
    store.save(session)


def infer_mapping(session: CheckEntriesSession) -> Dict[str, Optional[str]]:
    llm_wrapper = _build_llm_wrapper()
    inferred = _infer_mapping(llm_wrapper, session.dataframe)
    session.mapping = {k: (v or None) for k, v in inferred.items()}
    store.save(session)
    return session.mapping


def _infer_mapping(llm_wrapper, df: pl.DataFrame) -> Dict[str, Optional[str]]:
    from modules.llm.function_calls import function_specs, mapping_examples
    from modules.llm.random_entries_queries import infer_column_mapping
    from modules.process_excel.logic import _as_dict

    examples = mapping_examples()
    specs = function_specs()
    inferred = infer_column_mapping(llm_wrapper, df, examples, specs)
    return _as_dict(inferred.get("fields", {}))


def apply_mapping(session: CheckEntriesSession, mapping: Dict[str, Optional[str]]) -> None:
    mapping = {k: (v or None) for k, v in mapping.items()}
    _validate_mapping(mapping)
    session.mapping = mapping
    store.save(session)


def _validate_mapping(mapping: Dict[str, Optional[str]]) -> None:
    if not mapping.get("movement_number"):
        raise ValueError("Mapping must include movement_number")
    has_amount = bool(mapping.get("amount"))
    has_debit_credit = bool(mapping.get("debit_amount")) and bool(mapping.get("credit_amount"))
    if not (has_amount or has_debit_credit):
        raise ValueError("Map either amount or debit/credit columns")


def run_checks(
    session: CheckEntriesSession,
    params: Dict[str, Any],
) -> CheckRunOutput:
    mapping = session.mapping
    if not mapping:
        raise ValueError("Map the journal columns before running checks")
    if not session.pdf_files:
        LOGGER.warning("Running check_entries session %s without supporting PDFs.", session.session_id)

    llm_wrapper = _build_llm_wrapper()
    provider_config = select_provider("checkEntriesQuery")
    provider = provider_config.get("provider")
    model = provider_config.get("model")
    llm_wrapper.provider = provider
    llm_wrapper.model = model

    run_result = run_check_entries(
        CheckEntriesRunContext(
            data=session.dataframe,
            pdf_files=session.pdf_files,
            llm_wrapper=llm_wrapper,
            provider=provider,
            model=model,
        ),
        CheckEntriesRunParams(
            mapping=mapping,
            debug=bool(params.get("debug")),
            lang=str(params.get("lang", "eng")),
            amount_tolerance=float(params.get("amount_tolerance", 0.0)),
            date_window=int(params.get("date_window", 0)),
            timing_difference_window=_parse_optional_int(params.get("timing_difference_window")),
            beneficiary_similarity=float(params.get("beneficiary_similarity", 0.0)),
            beneficiary_check_mode=_parse_beneficiary_mode(params.get("beneficiary_check_mode")),
        ),
    )

    result_df = run_result.result_df
    summary_text = run_result.summary_text
    summary_tables = dict(run_result.summary_metrics)
    error_message = run_result.error_message
    batch_mode_used = False
    if "llm_batch" in result_df.columns:
        try:
            batch_mode_used = bool(result_df.get_column("llm_batch").any())
        except Exception:
            batch_mode_used = False
    excel_bytes = run_result.excel_bytes
    output = CheckRunOutput(
        result_df=result_df,
        summary_text=summary_text,
        summary_tables=summary_tables,
        excel_bytes=excel_bytes,
        error_message=error_message,
        batch_mode=batch_mode_used,
    )
    session.output = output
    store.save(session)
    return output


def _build_excel_payload(
    result_df: pl.DataFrame, summary_tables: Dict[str, pl.DataFrame]
) -> bytes:
    with io.BytesIO() as buffer:
        sheets = {"results": hide_line_numbers(result_df)}
        sheets.update(summary_tables)
        from modules.utils.polars_excel_writer import write_polars_excel

        write_polars_excel(sheets, buffer)
        return buffer.getvalue()


def review_mismatches(
    session: CheckEntriesSession,
    status: Dict[str, str],
    reasons: Dict[str, str],
) -> CheckRunOutput:
    if not session.output:
        raise ValueError("Run checks before submitting a review")

    updated_df = merge_review_feedback(session.output.result_df, status, reasons)
    excel_bytes = _build_excel_payload(updated_df, session.output.summary_tables)
    session.output = CheckRunOutput(
        result_df=updated_df,
        summary_text=session.output.summary_text,
        summary_tables=session.output.summary_tables,
        excel_bytes=excel_bytes,
        error_message=session.output.error_message,
        review_status=status,
        review_reason=reasons,
        batch_mode=session.output.batch_mode,
    )
    store.save(session)
    return session.output


def get_pdf_bytes(session: CheckEntriesSession, movement: str) -> Tuple[bytes | None, str]:
    pdf_map = build_pdf_map(session.pdf_files)
    return pdf_bytes_for(movement, pdf_map)


def _build_llm_wrapper() -> LLMCallWrapper:
    return LLMCallWrapper(mode="replay")


def _parse_optional_int(value: Any) -> Optional[int]:
    if value is None or value == "" or value == "null":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_beneficiary_mode(value: Any) -> BeneficiaryCheckMode:
    try:
        if isinstance(value, BeneficiaryCheckMode):
            return value
        if value:
            return BeneficiaryCheckMode(str(value))
    except ValueError:
        LOGGER.warning("Unknown beneficiary check mode '%s', defaulting to COMPARE", value)
    return BeneficiaryCheckMode.COMPARE
