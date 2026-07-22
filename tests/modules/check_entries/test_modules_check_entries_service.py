from __future__ import annotations

import types
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from modules.check_entries.constants import BeneficiaryCheckMode


def _df(rows: list[dict[str, Any]] | None = None) -> pl.DataFrame:
    rows = rows or [{"movement_number": "1", "check_status": "ok"}]
    return pl.DataFrame(rows)


def _install_dummy_journal_ingest(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types as _types

    pkg = _types.ModuleType("journal_ingest")
    cfg = _types.ModuleType("journal_ingest.config")
    core = _types.ModuleType("journal_ingest.core")
    router = _types.ModuleType("journal_ingest.router")
    strategies = _types.ModuleType("journal_ingest.strategies")

    def get_recipe(_name: str | None = None):  # pragma: no cover - not used in tests
        return None

    class ParserConfidenceError(Exception):
        pass

    class ValidationError(Exception):
        pass

    class Router:  # pragma: no cover - not used
        def __init__(self, *args, **kwargs) -> None:  # noqa: D401
            ...

    class _Dummy:  # pragma: no cover - placeholders
        pass

    cfg.get_recipe = get_recipe
    core.ParserConfidenceError = ParserConfidenceError
    core.ValidationError = ValidationError
    router.Router = Router
    strategies.JournalStrategyTableArea = _Dummy
    strategies.JournalStrategyTextLayout = _Dummy
    strategies.TablePDFParser = _Dummy
    strategies.TextPDFParser = _Dummy

    monkeypatch.setitem(sys.modules, "journal_ingest", pkg)
    monkeypatch.setitem(sys.modules, "journal_ingest.config", cfg)
    monkeypatch.setitem(sys.modules, "journal_ingest.core", core)
    monkeypatch.setitem(sys.modules, "journal_ingest.router", router)
    monkeypatch.setitem(sys.modules, "journal_ingest.strategies", strategies)

    # Also stub out heavy src.check_statements with only the names used by service
    mod = _types.ModuleType("src.check_statements")

    def _detect_excel_header_polars(_data: bytes) -> int:  # pragma: no cover - not used
        return 0

    def _rebuild_df_with_header(
        _data: bytes, _header_row: int
    ) -> pl.DataFrame:  # pragma: no cover - not used
        return pl.DataFrame()

    mod._detect_excel_header_polars = _detect_excel_header_polars
    mod._rebuild_df_with_header = _rebuild_df_with_header
    monkeypatch.setitem(sys.modules, "src.check_statements", mod)


def test_check_entries_pipeline_uses_mapping_and_passes_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_dummy_journal_ingest(monkeypatch)
    # Arrange: minimal input DataFrame and explicit mapping
    data_in = _df([{"movement_number": "1", "check_status": "ok"}])
    mapping = {"date": "Date", "amount": "Amount"}
    llm_wrapper = object()

    # Capture calls and provide controlled fakes
    captured: dict[str, Any] = {}

    def fake_build_pdf_map(pdf_files):
        # Return a sentinel object to verify pass-through
        return {"123": "PDF_OBJ"}

    def fake_run_automatic_check(df, mapping_arg, pdf_map, llm_wrapper_arg, **kwargs):
        captured["df"] = df
        captured["mapping"] = mapping_arg
        captured["pdf_map"] = pdf_map
        captured["kwargs"] = kwargs
        # Return a distinct DataFrame so we can assert exact identity/contents
        return _df(
            [{"movement_number": "2", "check_status": "mismatch", "explanation": "x"}]
        )

    summary_called: dict[str, Any] = {}

    def fake_summarize_results(llm_wrapper_arg, result_df, lang):
        summary_called["args"] = (llm_wrapper_arg, result_df, lang)
        return "summary ok", {
            "metrics": pl.DataFrame({"metric": ["rows_with_pdf"], "value": [1]})
        }

    # Ensure automatic mapping inference is NOT used when mapping is provided
    def fake_infer_mapping(
        *_args, **_kwargs
    ):  # pragma: no cover - should not be called
        raise AssertionError(
            "_infer_mapping should not be called when mapping is given"
        )

    import modules.check_entries.service as service

    monkeypatch.setattr(service, "build_pdf_map", fake_build_pdf_map)
    monkeypatch.setattr(service, "run_automatic_check", fake_run_automatic_check)
    monkeypatch.setattr(service, "summarize_results", fake_summarize_results)
    monkeypatch.setattr(service, "_infer_mapping", fake_infer_mapping)

    # Dummy inputs for parameters that are forwarded to run_automatic_check
    provider = "p1"
    model = "m1"
    debug = True
    lang = "eng"
    amount_tolerance = 0.5
    date_window = 2
    timing_difference_window = 7
    beneficiary_similarity = 80.0
    beneficiary_check_mode = BeneficiaryCheckMode.EXTRACT_ONLY
    progress_calls: list[tuple[int, int]] = []

    def progress(i: int, n: int) -> None:
        progress_calls.append((i, n))

    def is_cancelled() -> bool:
        return False

    # Act
    result_df, summary_text, metrics, error_message = service.check_entries_pipeline(
        data_in,
        pdf_files=[types.SimpleNamespace(name="move123.pdf")],
        llm_wrapper=llm_wrapper,
        mapping=mapping,
        provider=provider,
        model=model,
        debug=debug,
        lang=lang,
        amount_tolerance=amount_tolerance,
        date_window=date_window,
        timing_difference_window=timing_difference_window,
        beneficiary_similarity=beneficiary_similarity,
        beneficiary_check_mode=beneficiary_check_mode,
        progress=progress,
        is_cancelled=is_cancelled,
    )

    # Assert: pipeline returns the DataFrame from run_automatic_check
    expected_df = _df(
        [{"movement_number": "2", "check_status": "mismatch", "explanation": "x"}]
    )
    assert_frame_equal(result_df, expected_df)

    # Assert: summarize_results output is forwarded intact
    assert summary_text == "summary ok"
    assert set(metrics.keys()) == {"metrics"}
    assert isinstance(metrics["metrics"], pl.DataFrame)
    assert error_message is None

    # Assert: correct arguments flowed into dependencies
    assert_frame_equal(captured["df"], data_in)
    assert captured["mapping"] == mapping
    assert captured["pdf_map"] == {"123": "PDF_OBJ"}
    assert summary_called["args"][0] is llm_wrapper
    assert_frame_equal(summary_called["args"][1], expected_df)
    assert summary_called["args"][2] == lang

    # And verify pass-through keyword parameters
    kwargs = captured["kwargs"]
    assert kwargs["provider"] == provider
    assert kwargs["model"] == model
    assert kwargs["debug"] is True
    assert kwargs["lang"] == lang
    assert kwargs["amount_tolerance"] == amount_tolerance
    assert kwargs["date_window"] == date_window
    assert kwargs["timing_difference_window"] == timing_difference_window
    assert kwargs["beneficiary_similarity"] == beneficiary_similarity
    assert kwargs["beneficiary_check_mode"] == beneficiary_check_mode
    assert kwargs["progress"] is progress
    assert kwargs["is_cancelled"] is is_cancelled


def test_check_entries_pipeline_summary_failure_sets_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_dummy_journal_ingest(monkeypatch)
    # Arrange
    data_in = _df()
    mapping = {"date": "Date"}

    import modules.check_entries.service as service

    monkeypatch.setattr(service, "build_pdf_map", lambda _files: {})
    monkeypatch.setattr(service, "run_automatic_check", lambda *args, **kwargs: _df())

    def boom(*_args, **_kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(service, "summarize_results", boom)

    # Act
    result_df, summary_text, metrics, error_message = service.check_entries_pipeline(
        data_in, pdf_files=[], llm_wrapper=None, mapping=mapping
    )

    # Assert: DataFrame is still returned, but summary fails gracefully
    assert_frame_equal(result_df, _df())
    assert summary_text == ""
    assert metrics == {}
    assert (
        error_message is not None
        and "Could not summarize results" in error_message
        and "boom" in error_message
    )


def test_check_entries_pipeline_accepts_lazyframe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_dummy_journal_ingest(monkeypatch)
    # Arrange: provide a LazyFrame and ensure it is collected to a DataFrame
    base_df = _df([{"movement_number": "7", "check_status": "ok"}])
    data_in = base_df.lazy()
    mapping = {"amount": "Amount"}

    import modules.check_entries.service as service

    captured_df: dict[str, pl.DataFrame] = {}

    def fake_run_automatic_check(df, *args, **kwargs):
        captured_df["df"] = df
        # Return a simple result DF
        return _df([{"movement_number": "7", "check_status": "ok"}])

    monkeypatch.setattr(service, "build_pdf_map", lambda _files: {})
    monkeypatch.setattr(service, "run_automatic_check", fake_run_automatic_check)
    monkeypatch.setattr(
        service,
        "summarize_results",
        lambda *_args, **_kwargs: (
            "done",
            {"metrics": pl.DataFrame({"metric": [], "value": []})},
        ),
    )

    # Act
    result_df, summary_text, metrics, error_message = service.check_entries_pipeline(
        data_in, pdf_files=[], llm_wrapper=None, mapping=mapping
    )

    # Assert: the LazyFrame was collected and passed as a DataFrame
    assert_frame_equal(captured_df["df"], base_df)
    assert_frame_equal(result_df, base_df)
    assert summary_text == "done"
    assert set(metrics.keys()) == {"metrics"}
    assert error_message is None


def test_check_entries_pipeline_uses_spanish_ocr_for_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_dummy_journal_ingest(monkeypatch)
    import modules.check_entries.service as service

    pdf_path = tmp_path / "diario.pdf"
    pdf_path.write_bytes(b"%PDF-spanish-journal")
    captured: dict[str, str] = {}
    parsed_df = _df([{"movement_number": "1", "check_status": "ok"}])

    def fake_parse_journal(content: bytes, *, lang: str) -> pl.DataFrame:
        assert content == b"%PDF-spanish-journal"
        captured["lang"] = lang
        return parsed_df

    monkeypatch.setattr(service, "parse_journal", fake_parse_journal)
    monkeypatch.setattr(service, "build_pdf_map", lambda _files: {})
    monkeypatch.setattr(
        service,
        "run_automatic_check",
        lambda dataframe, *_args, **_kwargs: dataframe,
    )
    monkeypatch.setattr(
        service,
        "summarize_results",
        lambda *_args, **_kwargs: ("resumen", {}),
    )

    result_df, summary_text, _metrics, error_message = service.check_entries_pipeline(
        pdf_path,
        pdf_files=[],
        llm_wrapper=None,
        mapping={"movement_number": "movement_number"},
        lang="es",
    )

    assert captured == {"lang": "spa"}
    assert_frame_equal(result_df, parsed_df)
    assert summary_text == "resumen"
    assert error_message is None
