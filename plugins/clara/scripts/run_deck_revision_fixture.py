"""Run a Clara deck-revision fixture through the local harness."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from advisor_case_core import CaseWorkspaceError
from analyze_deck_revision_materials import analyze_deck_revision_materials
from apply_deck_revision_plan import apply_deck_revision_plan
from approve_deck_revision_plan import approve_deck_revision_plan
from build_deck_revision_execution_packets import build_deck_revision_execution_packets
from build_deck_revision_execution_plan import build_deck_revision_execution_plan
from build_deck_revision_interpretation_packets import (
    build_deck_revision_interpretation_packets,
)
from build_deck_revision_workbench import build_deck_revision_workbench
from finalize_deck_revision_plan import finalize_deck_revision_plan

__all__ = [
    "DeckRevisionFixtureResult",
    "run_deck_revision_fixture",
    "main",
]

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeckRevisionFixtureResult:
    """Artifacts created by a deck-revision fixture run."""

    fixture_dir: Path
    report_path: Path
    review_path: Path


def _now_iso(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CaseWorkspaceError(f"expected JSON object in {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _resolve_fixture_path(fixture_dir: Path, raw_path: Any, *, label: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise CaseWorkspaceError(f"fixture {label} is missing")
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = fixture_dir / candidate
    return candidate.resolve()


def _optional_fixture_path(fixture_dir: Path, raw_path: Any) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = fixture_dir / candidate
    return candidate.resolve()


def _relative_path(base_dir: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(base_dir.resolve()))
    except ValueError:
        return str(path.resolve())


def _expectation_records(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for key, expected_value in expected.items():
        if key == "change_strategies":
            actual_value = actual.get(key)
        else:
            actual_value = actual.get(key)
        records.append(
            {
                "field": key,
                "expected": expected_value,
                "actual": actual_value,
                "passed": actual_value == expected_value,
            }
        )
    return records


def _render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Deck Revision Fixture Report",
        "",
        f"Status: `{payload['summary']['status']}`",
        "",
        f"- Fixture: `{payload['fixture_dir']}`",
        f"- Case: `{payload['case_dir']}`",
        f"- Voice session: `{payload['voice_session']}`",
        f"- Normalized plan: `{payload['artifacts'].get('normalized_plan')}`",
        f"- Understanding: `{payload['artifacts'].get('understanding')}`",
        f"- Interpretation packets: `{payload['artifacts'].get('interpretation_packets')}`",
        f"- Execution plan: `{payload['artifacts'].get('execution_plan')}`",
        f"- Execution packets: `{payload['artifacts'].get('execution_packets')}`",
        f"- Material needs: `{payload['artifacts'].get('material_needs')}`",
        f"- Corrected deck: `{payload['artifacts'].get('corrected_deck') or 'not produced'}`",
        f"- Verification: `{payload['artifacts'].get('verification') or 'not run'}`",
        f"- Final output review: `{payload['artifacts'].get('output_review') or 'not run'}`",
        "",
    ]
    if payload["expectations"]:
        lines.append("## Expectations")
        lines.append("")
        for record in payload["expectations"]:
            result = "passed" if record["passed"] else "failed"
            lines.append(
                f"- `{record['field']}`: {result} "
                f"(expected `{record['expected']}`, actual `{record['actual']}`)"
            )
        lines.append("")
    return "\n".join(lines)


def run_deck_revision_fixture(
    fixture_dir: Path,
    *,
    config_path: Path | None = None,
    now: datetime | None = None,
) -> DeckRevisionFixtureResult:
    """Run a fixture through workbench, interpretation validation, routing, and verification."""

    fixture_dir = fixture_dir.resolve()
    resolved_config_path = config_path or (fixture_dir / "fixture.json")
    if not resolved_config_path.is_absolute():
        resolved_config_path = fixture_dir / resolved_config_path
    if not resolved_config_path.is_file():
        raise CaseWorkspaceError(f"fixture config is missing: {resolved_config_path}")
    config = _read_json(resolved_config_path)

    case_dir = _resolve_fixture_path(
        fixture_dir, config.get("case_dir"), label="case_dir"
    )
    voice_session = _optional_fixture_path(fixture_dir, config.get("voice_session"))
    changes_json = _resolve_fixture_path(
        fixture_dir, config.get("changes_json"), label="changes_json"
    )

    if bool(config.get("build_workbench", True)):
        build_deck_revision_workbench(
            case_dir,
            voice_session=voice_session,
            now=now,
        )
    interpretation_packets = build_deck_revision_interpretation_packets(
        case_dir,
        voice_session=voice_session,
        now=now,
    )
    finalizer_result = finalize_deck_revision_plan(
        case_dir,
        changes_json,
        voice_session=voice_session,
        now=now,
    )
    execution_result = build_deck_revision_execution_plan(
        case_dir,
        voice_session=voice_session,
        plan_path=finalizer_result.normalized_plan_path,
        now=now,
    )
    execution_packets = build_deck_revision_execution_packets(
        case_dir,
        voice_session=voice_session,
        plan_path=finalizer_result.normalized_plan_path,
        now=now,
    )
    material_result = analyze_deck_revision_materials(
        case_dir,
        voice_session=voice_session,
        plan_path=finalizer_result.normalized_plan_path,
        now=now,
    )

    approval_path: Path | None = None
    apply_result = None
    if bool(config.get("approve", False)):
        approval = approve_deck_revision_plan(
            case_dir,
            voice_session=voice_session,
            plan_path=finalizer_result.normalized_plan_path,
            reviewer=str(config.get("reviewer") or "fixture"),
            understanding_reviewed=bool(config.get("understanding_reviewed", True)),
            now=now,
        )
        approval_path = approval.approval_path
    if bool(config.get("apply", False)):
        apply_result = apply_deck_revision_plan(
            case_dir,
            voice_session=voice_session,
            plan_path=finalizer_result.normalized_plan_path,
            now=now,
            allow_unapproved=not bool(config.get("approve", False)),
        )

    execution_payload = _read_json(execution_result.execution_plan_path)
    material_payload = _read_json(material_result.needs_path)
    apply_payload = (
        _read_json(apply_result.apply_report_path) if apply_result is not None else {}
    )
    verification_payload = (
        _read_json(apply_result.verification_report_path)
        if apply_result is not None
        else {}
    )
    normalized_payload = _read_json(finalizer_result.normalized_plan_path)
    actual = {
        "change_count": len(normalized_payload.get("changes", [])),
        "execution_status": execution_payload.get("summary", {}).get("status"),
        "material_status": material_payload.get("summary", {}).get("status"),
        "apply_status": apply_payload.get("summary", {}).get("status"),
        "final_output_review_status": apply_payload.get("summary", {}).get(
            "final_output_review_status"
        ),
        "verification_status": verification_payload.get("summary", {}).get("status"),
        "change_strategies": [
            change.get("execution_strategy")
            for change in normalized_payload.get("changes", [])
            if isinstance(change, dict)
        ],
    }
    expected = (
        config.get("expected") if isinstance(config.get("expected"), dict) else {}
    )
    expectations = _expectation_records(expected, actual)
    status = (
        "passed"
        if all(record["passed"] for record in expectations)
        else "failed" if expectations else "completed"
    )
    payload: dict[str, Any] = {
        "schema_version": 1,
        "source": "clara_deck_revision_fixture_report",
        "created_at": _now_iso(now),
        "fixture_dir": str(fixture_dir),
        "case_dir": _relative_path(fixture_dir, case_dir),
        "voice_session": _relative_path(fixture_dir, voice_session),
        "changes_json": _relative_path(fixture_dir, changes_json),
        "summary": {
            "status": status,
            **actual,
        },
        "artifacts": {
            "normalized_plan": _relative_path(
                fixture_dir, finalizer_result.normalized_plan_path
            ),
            "changes_review": _relative_path(fixture_dir, finalizer_result.review_path),
            "understanding": _relative_path(
                fixture_dir, finalizer_result.understanding_path
            ),
            "interpretation_packets": _relative_path(
                fixture_dir, interpretation_packets.packet_index_path
            ),
            "interpretation_packets_review": _relative_path(
                fixture_dir, interpretation_packets.review_path
            ),
            "handoff": _relative_path(fixture_dir, finalizer_result.handoff_path),
            "execution_plan": _relative_path(
                fixture_dir, execution_result.execution_plan_path
            ),
            "execution_review": _relative_path(
                fixture_dir, execution_result.review_path
            ),
            "execution_packets": _relative_path(
                fixture_dir, execution_packets.packet_index_path
            ),
            "execution_packets_review": _relative_path(
                fixture_dir, execution_packets.review_path
            ),
            "material_needs": _relative_path(fixture_dir, material_result.needs_path),
            "material_review": _relative_path(fixture_dir, material_result.review_path),
            "approval": _relative_path(fixture_dir, approval_path),
            "corrected_deck": (
                _relative_path(fixture_dir, apply_result.corrected_deck_path)
                if apply_result is not None
                else None
            ),
            "apply_report": (
                _relative_path(fixture_dir, apply_result.apply_report_path)
                if apply_result is not None
                else None
            ),
            "output_review": (
                _relative_path(fixture_dir, apply_result.output_review_path)
                if apply_result is not None
                else None
            ),
            "verification": (
                _relative_path(fixture_dir, apply_result.verification_report_path)
                if apply_result is not None
                else None
            ),
        },
        "expectations": expectations,
    }

    report_path = fixture_dir / "deck_revision_eval_report.json"
    review_path = fixture_dir / "deck_revision_eval_report.md"
    _write_json(report_path, payload)
    review_path.write_text(_render_markdown(payload), encoding="utf-8")
    return DeckRevisionFixtureResult(
        fixture_dir=fixture_dir,
        report_path=report_path,
        review_path=review_path,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a Clara deck-revision fixture through the local harness.",
    )
    parser.add_argument("fixture_dir", type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Fixture config path. Defaults to fixture.json inside the fixture folder.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = run_deck_revision_fixture(args.fixture_dir, config_path=args.config)
    LOGGER.info("wrote deck revision fixture report to %s", result.report_path)
    LOGGER.info("wrote deck revision fixture review to %s", result.review_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
