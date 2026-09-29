"""Enforce the published local JSON shapes before consuming case fields.

Schema validation is mechanical: it enforces an explicit interchange contract,
not economic suitability, evidence quality or professional review acceptance.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from valuation_engine import ValuationError

__all__ = ["validate_case", "validate_selected_method"]


@lru_cache(maxsize=1)
def _validators() -> tuple[Draft202012Validator, Draft202012Validator]:
    schema = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "references/valuation-case.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    checker = FormatChecker(formats=["date"])
    return (
        Draft202012Validator(schema, format_checker=checker),
        Draft202012Validator(
            {"$ref": "#/$defs/selectedMethod", "$defs": schema["$defs"]},
            format_checker=checker,
        ),
    )


def _validate(value: Any, validator: Draft202012Validator, label: str) -> None:
    error = next(validator.iter_errors(value), None)
    if error is not None:
        path = "/" + "/".join(
            str(part).replace("~", "~0").replace("/", "~1")
            for part in error.absolute_path
        )
        # Do not echo private field values through jsonschema's full message.
        raise ValuationError(f"Invalid {label} at {path}: schema {error.validator}")


def validate_case(case: Any) -> None:
    """Reject malformed case structure before opening any nested source files."""
    _validate(case, _validators()[0], "valuation case")


def validate_selected_method(method: dict) -> None:
    """Reject one method payload inside the caller's partial-workpaper boundary."""
    _validate(method, _validators()[1], "selected method")
