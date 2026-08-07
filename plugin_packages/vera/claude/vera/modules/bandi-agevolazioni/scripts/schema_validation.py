"""Deterministically enforce the public JSON contracts used by one case run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

__all__ = ["validate_artifact_schema"]

SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "schemas"
ARTIFACT_SCHEMAS = {
    "case_intake": "case_intake.schema.json",
    "source_register": "source_register.schema.json",
    "application_workbench": "application_workbench.schema.json",
    "intelligence_register": "intelligence_register.schema.json",
    "review_log": "review_log.schema.json",
    "run_state": "run_state.schema.json",
    "opportunity_radar": "opportunity_radar.schema.json",
    "opportunity_handoff": "opportunity_handoff.schema.json",
}


def _safe_path(error: Any) -> str:
    """Return a value-free JSON path for one schema error."""

    return ".".join(str(part) for part in error.absolute_path) or "$"


def validate_artifact_schema(
    artifact_name: str,
    payload: dict[str, Any],
) -> list[dict[str, str]]:
    """Return value-free schema issues for mechanically invalid JSON."""

    schema_name = ARTIFACT_SCHEMAS.get(artifact_name)
    if schema_name is None:
        raise ValueError(f"no schema registered for artifact: {artifact_name}")
    schema = json.loads((SCHEMA_ROOT / schema_name).read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            str(error.validator),
        ),
    )
    return [
        {
            "code": "schema_violation",
            "path": f"{artifact_name}.{_safe_path(error)}",
            "message": f"does not satisfy schema rule {error.validator}",
        }
        for error in errors
    ]
