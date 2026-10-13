#!/usr/bin/env python3
"""Vera entrypoint for the shared managed Python runtime."""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import runpy
import shutil
import sqlite3
import sys
import tempfile
import traceback
from contextlib import redirect_stderr
from pathlib import Path

__all__ = ["main"]

prepare_execution_root = runpy.run_path(
    str(Path(__file__).with_name("verified_execution.py"))
)["prepare_execution_root"]


def _implementation_path() -> Path:
    return Path(__file__).with_name("_managed_python_runtime.py")


def _load_implementation():
    path = _implementation_path()
    spec = importlib.util.spec_from_file_location("vera_managed_python_runtime", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load managed Python runtime: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_IMPLEMENTATION = _load_implementation()
activate_runtime = _IMPLEMENTATION.activate_runtime
dependency_target = _IMPLEMENTATION.dependency_target
ensure_runtime = _IMPLEMENTATION.ensure_runtime
plugin_data_dir = _IMPLEMENTATION.plugin_data_dir
requirements_fingerprint = _IMPLEMENTATION.requirements_fingerprint
runtime_environment = _IMPLEMENTATION.runtime_environment
runtime_key = _IMPLEMENTATION.runtime_key
runtime_python = _IMPLEMENTATION.runtime_python
select_runtime = _IMPLEMENTATION.select_runtime


def _report_forced_termination(
    arguments: list[str], returncode: int, module: str | None
) -> None:
    """Persist a killed worker diagnostic only inside its declared client-run output."""
    message = (
        f"Vera worker was forcibly terminated (exit {returncode}). "
        "Memory exhaustion is a possible cause; this exit code alone does not prove it. "
        "No successful result is confirmed."
    )
    logging.error("WORKER_FORCIBLY_TERMINATED: %s", message)
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--client-engagement", type=Path)
    options, _ = parser.parse_known_args(arguments)
    if options.output_dir is None or options.client_engagement is None:
        return
    try:
        context = json.loads(options.client_engagement.read_text(encoding="utf-8"))
        if not isinstance(context, dict) or context.get("workflow_id") != module:
            return
        root = Path(context["output_dir"]).resolve()
        output = options.output_dir.resolve()
        if output not in {root, root / "normalization", root / "sample"}:
            return
        output.mkdir(parents=True, exist_ok=True)
        diagnostic = {
            "schema_version": "vera.execution_failure.v1",
            "failure_kind": "forced_termination",
            "exit_code": returncode,
            "workflow_id": module,
            "run_id": context["run_id"],
            "memory_exhaustion_confirmed": False,
            "message": message,
        }
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output,
            prefix=".execution-failure-",
            delete=False,
        ) as handle:
            json.dump(diagnostic, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            temporary = Path(handle.name)
        temporary.replace(output / "execution_failure.json")
    except (OSError, ValueError, KeyError) as error:
        logging.error("Could not save forced-termination diagnostic: %s", error)


def _execute_with_diagnostics(
    root: Path, arguments: list[str]
) -> tuple[int, Path | None]:
    """Spool stderr to disk without capturing or buffering professional stdout."""
    from operational_incidents import diagnostic_directory

    try:
        handle = tempfile.NamedTemporaryFile(
            mode="w+",
            encoding="utf-8",
            errors="replace",
            dir=diagnostic_directory(),
            suffix=".stderr",
            delete=False,
        )
    except (OSError, ValueError, sqlite3.Error):
        logging.warning(
            "Technical stderr retention unavailable; preserve the observed host tool error through the incident connector."
        )
        return _IMPLEMENTATION.main(root, arguments), None
    path = Path(handle.name)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    handler = logging.StreamHandler(handle)
    _IMPLEMENTATION.LOGGER.addHandler(handler)
    result = None
    try:
        with handle:
            try:
                with redirect_stderr(handle):
                    result = _IMPLEMENTATION.main(root, arguments, stderr=handle)
            except SystemExit as error:
                result = (
                    error.code
                    if isinstance(error.code, int)
                    else (0 if error.code is None else 1)
                )
            except (OSError, ValueError, RuntimeError):
                traceback.print_exc(file=handle)
                result = 1
            finally:
                _IMPLEMENTATION.LOGGER.removeHandler(handler)
            handle.flush()
            handle.seek(0)
            shutil.copyfileobj(handle, sys.stderr, length=16384)
    finally:
        _IMPLEMENTATION.LOGGER.removeHandler(handler)
        if result is None:
            path.unlink(missing_ok=True)
    if result == 0:
        path.unlink()
        return result, None
    return result, path


def _independent_failure(stage: str, module: str | None, error_type: str) -> None:
    """Route pre-execution failures without running an unverified incident helper."""
    logging.error(
        "VERA_REMOTE_INCIDENT_REQUIRED: workflow=%s stage=%s error_type=%s. "
        "Use the saved veraIncidents connector to report the complete observed technical error. "
        "Do not run an altered plugin helper to report its own integrity failure.",
        module or "unknown",
        stage,
        error_type,
    )


def main(argv: list[str] | None = None) -> int:
    """Run Vera's managed runtime CLI."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    # Only runtime options before its subcommand select the component. A helper
    # may itself have an unrelated --module option in its remaining arguments.
    prefix = arguments
    for index, argument in enumerate(arguments):
        if argument in {"run", "install", "status"}:
            prefix = arguments[:index]
            break
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--module")
    parser.add_argument("--requirements", action="append")
    selection, _ = parser.parse_known_args(prefix)
    root = Path(__file__).absolute().parents[1]
    # Reject an invalid entrypoint before provisioning, with an exact boundary
    # diagnostic rather than conflating an outside script with a missing file.
    if "run" in arguments:
        run_index = arguments.index("run")
        if run_index + 1 >= len(arguments):
            logging.error("Managed runtime run requires a published helper entrypoint")
            _independent_failure(
                "execution-startup", selection.module, "MissingEntrypoint"
            )
            return 2
        if run_index + 1 < len(arguments):
            runtime_selection = _IMPLEMENTATION.select_runtime(
                root, selection.module, selection.requirements
            )
            script = (
                runtime_selection.requirement_root / arguments[run_index + 1]
            ).resolve()
            if not script.is_relative_to(runtime_selection.requirement_root):
                logging.error("Managed runtime script outside module root: %s", script)
                _independent_failure(
                    "execution-startup", selection.module, "InvalidEntrypoint"
                )
                return 2
            if not script.is_file():
                logging.error("Managed runtime script not found: %s", script)
                _independent_failure(
                    "execution-startup", selection.module, "MissingEntrypoint"
                )
                return 2
    try:
        root = prepare_execution_root(root, selection.module)
    except (OSError, ValueError) as error:
        logging.error("Vera installation verification failed: %s", error)
        _independent_failure(
            "installation-preparation", selection.module, type(error).__name__
        )
        return 1
    error_path = None
    if "run" in arguments and selection.module:
        result, error_path = _execute_with_diagnostics(root, arguments)
    else:
        result = _IMPLEMENTATION.main(root, arguments)
    if "run" in arguments and selection.module:
        from operational_incidents import (
            record_success,
            report_failure,
            retain_diagnostic,
        )

        operation = Path(arguments[arguments.index("run") + 1]).name
        if result == 0:
            try:
                record_success(selection.module, operation)
            except (OSError, ValueError, KeyError, sqlite3.Error):
                logging.warning(
                    "Incident recovery receipt pending; professional output is preserved."
                )
        else:
            receipt = report_failure(
                selection.module,
                f"helper:{operation}",
                f"Verified helper exited with status {result}. Professional stdout is excluded; add the technical error chain through the incident connector.",
                error_type="HelperExit",
                exit_code=result,
                measurements={
                    "diagnostic_review_pending": error_path is not None,
                    "stderr_bytes": (
                        error_path.stat().st_size if error_path is not None else 0
                    ),
                },
            )
            if error_path is not None:
                try:
                    pointer = retain_diagnostic(error_path, receipt)
                    logging.error(
                        "VERA_TECHNICAL_EVIDENCE: %s. Automatically read the retained stderr locally, review complete relevant technical diagnostics without unrelated private/client content, then use vera_incident_report with evidence_for_report_id from its report before concluding diagnosis is blocked. Raw stderr is not uploaded.",
                        pointer,
                    )
                except (OSError, ValueError, KeyError):
                    logging.warning(
                        "Retained helper stderr is at %s; metadata could not be saved. Use the independent incident connector for the observed error.",
                        error_path,
                    )
    if result < 0 or result in {137, 247}:
        _report_forced_termination(arguments, result, selection.module)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
