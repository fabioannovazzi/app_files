import polars as pl
import pytest

import modules.add_attributes.column_inference as ci


def test_infer_column_roles_happy_path_excludes_numeric_and_maps(monkeypatch):
    # Arrange: tiny dataset with one numeric column that must be excluded
    df = pl.DataFrame(
        {
            "product": ["A", "B", None, "A"],
            "category": ["Electronics", "Furniture", "Electronics", "Furniture"],
            "subcategory": ["Laptops", "Chairs", "Laptops", "Tables"],
            "price": [10.0, 20.0, 30.0, 40.0],
        }
    )
    lf = df.lazy()

    # Minimal config required by the function
    monkeypatch.setattr(ci, "get_naming_params", lambda: {"inferColumnQuery": "inferColumnQuery"})

    captured: list[tuple[str, str, str]] = []

    def fake_run_step_json(llm_wrapper, step, system_prompt, user_prompt, **kwargs):
        captured.append((step, system_prompt, user_prompt))
        return [
            {
                "product_column": "product",
                "category_column": "category",
                "subcategory_column": "subcategory",
                "extra": "ignored",
            }
        ]

    monkeypatch.setattr(ci, "run_step_json", fake_run_step_json)

    # Act
    result = ci.infer_column_roles(object(), lf)

    # Assert: only expected keys are returned and numeric column excluded from prompt
    assert result == {
        "product_column": "product",
        "category_column": "category",
        "subcategory_column": "subcategory",
    }
    assert len(captured) == 1
    step, system_prompt, user_prompt = captured[0]
    assert step == "inferColumnQuery"
    assert "You are a data expert" in system_prompt
    assert "- product " in user_prompt and "- category " in user_prompt and "- subcategory " in user_prompt
    assert "price" not in user_prompt  # numeric column should be filtered out


def test_infer_column_roles_non_dict_response_yields_none_values(monkeypatch):
    # Arrange
    lf = pl.DataFrame({"product": ["A"]}).lazy()
    monkeypatch.setattr(ci, "get_naming_params", lambda: {"inferColumnQuery": "inferColumnQuery"})
    monkeypatch.setattr(
        ci, "run_step_json", lambda *a, **k: ["not-a-dict"]  # malformed LLM response
    )

    # Act
    result = ci.infer_column_roles(object(), lf)

    # Assert
    assert result == {
        "product_column": None,
        "category_column": None,
        "subcategory_column": None,
    }


def test_infer_column_roles_handles_dtype_exception_and_calls_ui_error(monkeypatch):
    # Arrange: build a simple LazyFrame
    lf = pl.DataFrame({"title": ["A", "B"], "badcol": [1, 2]}).lazy()

    # Bad dtype whose is_numeric() raises
    class BadDtype:
        def is_numeric(self):  # noqa: D401 - simple stub
            raise RuntimeError("boom")

    # Return a schema containing the problematic dtype for the LazyFrame; for DataFrames return empty
    def fake_get_schema_and_column_names(obj):
        if isinstance(obj, pl.LazyFrame):
            return ["title", "badcol"], {"title": pl.Utf8, "badcol": BadDtype()}
        # For collected sample DataFrames, a minimal no-schema response is fine
        return list(getattr(obj, "columns", [])), None

    monkeypatch.setattr(ci, "get_naming_params", lambda: {"inferColumnQuery": "inferColumnQuery"})
    monkeypatch.setattr(ci, "get_schema_and_column_names", fake_get_schema_and_column_names)

    errors: list[str] = []

    def fake_error(msg):
        errors.append(str(msg))

    monkeypatch.setattr(ci.ui, "error", fake_error)

    def fake_run_step_json(llm_wrapper, step, system_prompt, user_prompt, **kwargs):
        return [
            {
                "product_column": "title",
                "category_column": None,
                "subcategory_column": None,
            }
        ]

    monkeypatch.setattr(ci, "run_step_json", fake_run_step_json)

    # Act
    result = ci.infer_column_roles(object(), lf)

    # Assert: ui.error called once and result returned
    assert len(errors) == 1
    assert "inferring column data types" in errors[0]
    assert result == {
        "product_column": "title",
        "category_column": None,
        "subcategory_column": None,
    }
