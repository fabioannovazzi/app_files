"""Versioned ESG evidence foundation inside an existing Studio Archive run.

Fixed rules are used only for exact identities, schema, provenance, hashes and
dependency closure. Framework applicability and professional judgments are
supplied by the reviewer, never inferred here.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import logging
import sys
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
for candidate in (
    ROOT / "vendor/modules",
    ROOT.parent.parent / "vendor/modules",
    ROOT.parent / "_shared/vendor/modules",
):
    if (candidate / "vera_assurance").is_dir():
        sys.path.insert(0, str(candidate))
        break

from jsonschema import Draft202012Validator, FormatChecker  # noqa: E402
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)

__all__ = ["ESGError", "execute", "resume_case", "main"]

WORKFLOW = "esg-reporting-assurance"
MAX_BYTES = 8 * 1024 * 1024
KINDS = {"case", "source", "evidence", "decision", "artifact"}


class ESGError(ValueError):
    """An exact case boundary or provenance invariant was violated."""


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 10000:
        raise ESGError(f"{label} must be nonblank text")
    return value


def _path(root: Path, relative: str) -> Path:
    part = Path(relative)
    if part.is_absolute() or not part.parts or ".." in part.parts or "\\" in relative:
        raise ESGError("Unauthorized relative path")
    result = root / part
    if result.resolve() != result or not result.resolve().is_relative_to(
        root.resolve()
    ):
        raise ESGError("Unauthorized path or symbolic link")
    return result


def _read(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ESGError("Expected a bounded regular JSON file")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ESGError("Expected a JSON object")
    return value


def _write(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            temporary.chmod(0o600)
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _lock(output: Path) -> Iterator[None]:
    path = output / ".esg-write.lock"
    try:
        handle = path.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise ESGError(
            "Another ESG write is pending; inspect the run and retry"
        ) from exc
    try:
        with handle:
            yield
    finally:
        path.unlink(missing_ok=True)


def _context(path: Path, *, reading: bool = False) -> dict[str, Any]:
    context = load_client_engagement_context_file(
        path,
        expected_workflow_id=WORKFLOW,
        allowed_statuses=(
            ("running", "ready_for_review", "completed") if reading else ("running",)
        ),
    )
    if context["schema_version"] != "vera.client_workflow_context.v2":
        raise ESGError("ESG requires the portable Studio Archive v2 context")
    return context


def _latest(state: dict[str, Any], kind: str, identifier: str) -> dict[str, Any]:
    matches = [
        item
        for item in state["objects"]
        if item["kind"] == kind and item["id"] == identifier
    ]
    if not matches:
        raise ESGError("Reference does not exist in this case")
    return matches[-1]


def _ref(state: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    return {
        "client_id": state["client_id"],
        "engagement_id": state["engagement_id"],
        "case_id": state["case_id"],
        **{key: item[key] for key in ("kind", "id", "version", "sha256")},
    }


def _resolve(
    state: dict[str, Any], ref: dict[str, Any], *, current: bool = True
) -> dict[str, Any]:
    for key in ("client_id", "engagement_id", "case_id"):
        if ref.get(key) != state[key]:
            raise ESGError("Reference belongs to another client, engagement or case")
    matches = [item for item in state["objects"] if _ref(state, item) == ref]
    if not matches:
        raise ESGError("Reference version or hash does not exist")
    item = matches[0]
    if current and not _current(state, item):
        raise ESGError("Reference is stale; review the current version")
    return item


def _current(state: dict[str, Any], item: dict[str, Any]) -> bool:
    if _latest(state, item["kind"], item["id"])["sha256"] != item["sha256"]:
        return False
    return all(
        _current(state, _resolve(state, ref, current=False))
        for ref in item["dependencies"]
    )


def _validate_record(kind: str, record: dict[str, Any]) -> None:
    schema = _read(ROOT / "schemas/foundation.schema.json")
    validator = Draft202012Validator(
        {**schema, "$ref": f"#/$defs/{kind}"}, format_checker=FormatChecker()
    )
    errors = sorted(validator.iter_errors(record), key=lambda error: str(error.path))
    if errors:
        raise ESGError(f"Invalid {kind}: {errors[0].message}")
    for key, value in record.items():
        missing_excerpt = (
            kind == "evidence"
            and key == "excerpt"
            and record["observation"]["status"] in {"not_available", "not_applicable"}
        )
        if isinstance(value, str) and not value.strip() and not missing_excerpt:
            raise ESGError(f"{key} cannot be blank")
    if "period" in record and date.fromisoformat(
        record["period"]["start"]
    ) > date.fromisoformat(record["period"]["end"]):
        raise ESGError("Period start must precede end")


def _put(
    state: dict[str, Any],
    kind: str,
    identifier: str,
    record: dict[str, Any],
    dependencies: list[dict[str, Any]],
) -> dict[str, Any]:
    _text(identifier, "id")
    _validate_record(kind, record)
    if any(
        record.get(key, state[key]) != state[key]
        for key in ("client_id", "engagement_id")
    ):
        raise ESGError("Record belongs to another engagement")
    for ref in dependencies:
        _resolve(state, ref)
        if ref["kind"] == kind and ref["id"] == identifier:
            raise ESGError("An object cannot depend on itself")
    # All references point to existing immutable versions: no forward edges or cycles.
    previous = [
        item
        for item in state["objects"]
        if item["kind"] == kind and item["id"] == identifier
    ]
    content = {
        "kind": kind,
        "id": identifier,
        "version": len(previous) + 1,
        "record": record,
        "dependencies": dependencies,
    }
    item = {**content, "sha256": _digest(content)}
    state["objects"].append(item)
    return _ref(state, item)


def _artifact_files(item: dict[str, Any]) -> dict[str, bytes]:
    record = item["record"]
    prefix = "esg-draft-" + item["sha256"]
    markdown = (
        "# " + record["title"] + "\n\n"
        "PARTIAL FOUNDATION DRAFT — not an ESG conformity or assurance conclusion.\n"
        "Validity depends on the current case state; obsolete dependencies invalidate this draft.\n\n"
        + record["content"]
        + "\n\nVersion: "
        + item["sha256"]
        + "\n"
    )
    return {
        prefix + ".md": markdown.encode("utf-8"),
        prefix
        + ".json": (json.dumps(item, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        ),
    }


def _persist_artifacts(output: Path, state: dict[str, Any]) -> None:
    for item in state["objects"]:
        if item["kind"] != "artifact":
            continue
        for name, content in _artifact_files(item).items():
            path = _path(output, name)
            if path.exists():
                if path.read_bytes() != content:
                    raise ESGError("Immutable draft bytes have changed")
            else:
                with path.open("xb") as stream:
                    path.chmod(0o600)
                    stream.write(content)


def _load(context: dict[str, Any]) -> dict[str, Any]:
    output = Path(context["output_dir"])
    state = _read(_path(output, "esg_state.json"))
    if state.get("schema_version") != "vera.esg.foundation.v1" or state.get(
        "sha256"
    ) != _digest({key: value for key, value in state.items() if key != "sha256"}):
        raise ESGError("ESG state integrity mismatch")
    for key in ("client_id", "engagement_id", "run_id"):
        if state[key] != context[key]:
            raise ESGError("ESG state belongs to another run")
    seen = {**state, "objects": []}
    for item in state["objects"]:
        if item["sha256"] != _digest(
            {key: value for key, value in item.items() if key != "sha256"}
        ):
            raise ESGError("Object integrity mismatch")
        _validate_record(item["kind"], item["record"])
        for ref in item["dependencies"]:
            _resolve(seen, ref, current=False)
        seen["objects"].append(item)
        if item["kind"] == "artifact":
            for name, content in _artifact_files(item).items():
                if _path(output, name).read_bytes() != content:
                    raise ESGError("Immutable draft bytes have changed")
        if item["kind"] == "evidence":
            binding = next(
                (
                    entry
                    for entry in context["input_bindings"]
                    if entry["binding_id"] == item["record"]["input_id"]
                ),
                None,
            )
            if binding is None or binding["sha256"] != item["record"]["sha256"]:
                raise ESGError("Historical evidence must remain selected in this run")
    return state


def _summary(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "partial",
        "case_id": state["case_id"],
        "revision": state["revision"],
        "state_sha256": state["sha256"],
        "compliance_claim_enabled": False,
        "objects": [
            {
                "reference": _ref(state, item),
                "current": _current(state, item),
                "record": item["record"],
            }
            for item in state["objects"]
        ],
        "limitations": [
            "Evidence and decisions foundation only",
            "No complete or approved legal catalogue",
            "No ESG conformity or assurance conclusion",
        ],
    }


def resume_case(context_path: Path) -> dict[str, Any]:
    """Recover and verify current and superseded evidence without mutating it."""
    return _summary(_load(_context(context_path, reading=True)))


def _evidence(context: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    binding = next(
        (
            item
            for item in context["input_bindings"]
            if item["binding_id"] == request["input_id"]
        ),
        None,
    )
    if binding is None:
        raise ESGError("Input is not selected in this engagement run")
    path = Path(binding["path"])
    if path.stat().st_size > MAX_BYTES:
        raise ESGError("Evidence input exceeds the 8 MB foundation limit")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != binding["sha256"]:
        raise ESGError("Evidence input hash changed")
    locator = request["locator"]
    if set(locator) == {"row", "column"} and path.suffix.lower() == ".csv":
        row, column = locator["row"], locator["column"]
        if type(row) is not int or row < 1 or not isinstance(column, str):
            raise ESGError("CSV locator requires a positive data row and column name")
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        if (
            not reader.fieldnames
            or len(reader.fieldnames) != len(set(reader.fieldnames))
            or column not in reader.fieldnames
        ):
            raise ESGError(
                "CSV headers are missing, ambiguous or do not contain the column"
            )
        rows = list(reader)
        if (
            row > len(rows)
            or None in rows[row - 1]
            or any(value is None for value in rows[row - 1].values())
        ):
            raise ESGError("CSV locator is outside a rectangular source row")
        excerpt = rows[row - 1][column]
    elif set(locator) == {"line"} and path.suffix.lower() in {".txt", ".md"}:
        lines = content.decode("utf-8-sig").splitlines()
        line = locator["line"]
        if type(line) is not int or not 1 <= line <= len(lines):
            raise ESGError("Text locator is outside source")
        excerpt = lines[line - 1]
    else:
        raise ESGError("Foundation supports CSV cells and UTF-8 text lines only")
    observation = request["observation"]
    _validate_record("observation", observation)
    value = observation["value"]
    if value is not None:
        if value == "-0" or ("." in value and value.endswith("0")):
            raise ESGError("Use canonical decimal strings without trailing zeros")
    if observation["status"] == "observed" and not excerpt.strip():
        raise ESGError("An empty cell cannot support an observed value")
    return {
        "client_id": context["client_id"],
        "engagement_id": context["engagement_id"],
        "input_id": binding["binding_id"],
        "sha256": binding["sha256"],
        "source_relative_path": binding["source_relative_path"],
        "locator": locator,
        "excerpt": excerpt,
        "observation": observation,
    }


def _apply(
    state: dict[str, Any],
    context: dict[str, Any],
    command: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    case_ref = _ref(state, _latest(state, "case", state["case_id"]))
    if command == "bind_evidence":
        record = _evidence(context, request)
        return _put(state, "evidence", request["id"], record, [case_ref])
    if command == "register_source":
        record = request["record"]
        # This tranche never upgrades contributor source metadata into legal approval.
        if record["catalogue_complete"] or record["legal_review_approved"]:
            raise ESGError(
                "Catalogue qualification is not implemented; retain an unapproved seed"
            )
        return _put(state, "source", request["id"], record, [case_ref])
    if command == "record_decision":
        refs = request["dependencies"]
        if not refs:
            raise ESGError("A decision requires exact version dependencies")
        record = request["record"]
        return _put(state, "decision", request["id"], record, [case_ref, *refs])
    if command == "build_deliverables":
        if request["claim"] != "partial_draft":
            raise ESGError(
                "Conformity and assurance claims require qualified catalogues and professional release; unavailable in this tranche"
            )
        refs = request["dependencies"]
        if not refs:
            raise ESGError("An artifact requires exact source or decision dependencies")
        for ref in refs:
            _resolve(state, ref)
        record = {
            "claim": "partial_draft",
            "title": request["title"],
            "audience": "professional",
            "content": request["content"],
            "limitations": [
                "Foundation snapshot; not an ESG report, conformity declaration or assurance opinion"
            ],
        }
        return _put(state, "artifact", request["id"], record, [case_ref, *refs])
    raise ESGError("Unsupported command")


def execute(
    context_path: Path, command: str, request: dict[str, Any]
) -> dict[str, Any]:
    """Apply one idempotent mutation, binding decisions to exact prior versions."""
    _validate_record(command, request)
    context = _context(context_path)
    output = Path(context["output_dir"])
    with _lock(output):
        context = _context(context_path)
        state_path = _path(output, "esg_state.json")
        fingerprint = _digest({"command": command, "request": request})
        if command == "start_case" and not state_path.exists():
            previous = request["previous_context"]
            if previous is not None:
                old_context = _context(Path(previous), reading=True)
                if (
                    any(
                        old_context[key] != context[key]
                        for key in ("client_id", "engagement_id")
                    )
                    or old_context["run_id"] == context["run_id"]
                ):
                    raise ESGError(
                        "Previous case must be a different run in the same engagement"
                    )
                state = copy.deepcopy(_load(old_context))
                if state["case_id"] != request["case_id"]:
                    raise ESGError("Previous case identity differs")
                # Every prior source must stay available for historical verification.
                selected = {
                    item["binding_id"]: item["sha256"]
                    for item in context["input_bindings"]
                }
                for item in state["objects"]:
                    if (
                        item["kind"] == "evidence"
                        and selected.get(item["record"]["input_id"])
                        != item["record"]["sha256"]
                    ):
                        raise ESGError(
                            "Select historical inputs as well as the new version"
                        )
                state["previous_run_id"] = state["run_id"]
                state["run_id"] = context["run_id"]
                state["requests"] = {}
                old_case = _latest(state, "case", state["case_id"])["record"]
                if old_case != request["record"]:
                    _put(state, "case", state["case_id"], request["record"], [])
            else:
                state = {
                    "schema_version": "vera.esg.foundation.v1",
                    "case_id": request["case_id"],
                    "client_id": context["client_id"],
                    "engagement_id": context["engagement_id"],
                    "run_id": context["run_id"],
                    "previous_run_id": None,
                    "revision": 0,
                    "objects": [],
                    "requests": {},
                }
                _put(state, "case", state["case_id"], request["record"], [])
            result = _ref(state, _latest(state, "case", state["case_id"]))
        else:
            state = _load(context)
            previous_request = state["requests"].get(request["idempotency_key"])
            if previous_request is not None:
                if previous_request["sha256"] != fingerprint:
                    raise ESGError("Idempotency key is bound to a different request")
                return {
                    "status": "replayed",
                    "reference": previous_request["result"],
                    "state_sha256": state["sha256"],
                }
            if command == "start_case":
                raise ESGError(
                    "Case already exists; reuse the start key or create a new archive run"
                )
            if request["expected_state_sha256"] != state["sha256"]:
                raise ESGError("State changed; resume and review before writing")
            result = _apply(state, context, command, request)
        state["revision"] += 1
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        state["requests"][request["idempotency_key"]] = {
            "sha256": fingerprint,
            "result": result,
        }
        state.pop("sha256", None)
        state["sha256"] = _digest(state)
        _persist_artifacts(output, state)
        _write(state_path, state)
        return {"status": "saved", "reference": result, "state_sha256": state["sha256"]}


def main(argv: list[str] | None = None) -> int:
    """Expose the foundation in the host's authenticated session without model API keys."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "start_case",
            "bind_evidence",
            "register_source",
            "record_decision",
            "build_deliverables",
            "resume_case",
        ],
    )
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--request", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "resume_case":
            result = resume_case(args.context)
        else:
            if args.request is None:
                raise ESGError("Mutation requires --request")
            result = execute(args.context, args.command, _read(args.request))
        sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        return 0
    except (
        ESGError,
        AssuranceContractError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        KeyError,
    ) as exc:
        logging.error("ESG operation blocked: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
