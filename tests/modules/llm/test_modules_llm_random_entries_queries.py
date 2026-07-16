import polars as pl
import pytest

from modules.llm.random_entries_queries import (
    clean_header_row_result,
    infer_header_row,
    infer_column_mapping,
)


@pytest.mark.parametrize(
    "resp, expected",
    [
        ("2", 2),  # golden path
        ("-1", None),  # boundary: negative -> None
        ("no digits here", None),  # invalid input -> None
    ],
)
def test_clean_header_row_result_parametrized(resp, expected):
    assert clean_header_row_result(resp) == expected


def test_infer_header_row_uses_llm_index(monkeypatch):
    # Arrange
    df = pl.DataFrame({"A": ["Data", "x", "y"], "B": ["B", "c", "d"]})

    # Stub naming params and LLM text call
    monkeypatch.setattr(
        "modules.llm.random_entries_queries.get_naming_params",
        lambda: {"randomMovementsQuery": "randomMovementsQuery"},
    )

    def stub_run_step_text(llm_wrapper, step, system, prompt, **kwargs):
        return ["1"]  # header row index suggested by LLM

    monkeypatch.setattr(
        "modules.llm.random_entries_queries.run_step_text", stub_run_step_text
    )

    # Act
    out = infer_header_row(object(), df)

    # Assert
    assert out == 1


def test_infer_header_row_clamps_to_bounds(monkeypatch):
    # Arrange: only 3 rows -> last valid index is 2
    df = pl.DataFrame({"A": ["h", "x", "y"], "B": ["b", "c", "d"]})

    monkeypatch.setattr(
        "modules.llm.random_entries_queries.get_naming_params",
        lambda: {"randomMovementsQuery": "randomMovementsQuery"},
    )

    def stub_run_step_text(llm_wrapper, step, system, prompt, **kwargs):
        return ["10"]  # out-of-range index

    monkeypatch.setattr(
        "modules.llm.random_entries_queries.run_step_text", stub_run_step_text
    )

    # Act
    out = infer_header_row(object(), df)

    # Assert: clamped to last row index
    assert out == 2


def test_infer_header_row_on_error_returns_zero_and_reports(monkeypatch):
    # Arrange
    df = pl.DataFrame({"A": ["h", "x"], "B": ["b", "c"]})
    errors: list[str] = []

    monkeypatch.setattr(
        "modules.llm.random_entries_queries.get_naming_params",
        lambda: {"randomMovementsQuery": "randomMovementsQuery"},
    )

    def stub_run_step_text_raises(*args, **kwargs):  # noqa: ANN001
        raise RuntimeError("LLM failure")

    monkeypatch.setattr(
        "modules.llm.random_entries_queries.run_step_text", stub_run_step_text_raises
    )

    # Stub UI error reporter to capture calls without UI
    def stub_error(msg):  # noqa: ANN001
        errors.append(str(msg))

    monkeypatch.setattr("modules.llm.random_entries_queries.ui.error", stub_error)

    # Act
    out = infer_header_row(object(), df)

    # Assert
    assert out == 0
    assert len(errors) == 1


def test_infer_column_mapping_returns_llm_json(monkeypatch):
    # Arrange
    df = pl.DataFrame({"Date": ["2024-01-01"], "Amount": [100]})
    examples = "Example mapping"
    specs = {"name": "map_journal_columns", "parameters": {"type": "object"}}
    expected = {"date": 0, "debit": 1}

    monkeypatch.setattr(
        "modules.llm.random_entries_queries.get_naming_params",
        lambda: {"inferColumnQuery": "inferColumnQuery"},
    )

    def stub_run_step_json(llm_wrapper, step, system, prompt, **kwargs):
        return [expected]

    monkeypatch.setattr(
        "modules.llm.random_entries_queries.run_step_json", stub_run_step_json
    )

    # Act
    out = infer_column_mapping(object(), df, examples, specs)

    # Assert
    assert out == expected


def test_infer_column_mapping_on_error_returns_empty_and_reports(monkeypatch):
    # Arrange
    df = pl.DataFrame({"Date": ["2024-01-01"], "Amount": [100]})
    specs = {"name": "map_journal_columns", "parameters": {"type": "object"}}
    errors: list[str] = []

    monkeypatch.setattr(
        "modules.llm.random_entries_queries.get_naming_params",
        lambda: {"inferColumnQuery": "inferColumnQuery"},
    )

    def stub_run_step_json_raises(*args, **kwargs):  # noqa: ANN001
        raise RuntimeError("LLM failure")

    monkeypatch.setattr(
        "modules.llm.random_entries_queries.run_step_json", stub_run_step_json_raises
    )

    def stub_error(msg):  # noqa: ANN001
        errors.append(str(msg))

    monkeypatch.setattr("modules.llm.random_entries_queries.ui.error", stub_error)

    # Act
    out = infer_column_mapping(object(), df, "", specs)

    # Assert
    assert out == {}
    assert len(errors) == 1
