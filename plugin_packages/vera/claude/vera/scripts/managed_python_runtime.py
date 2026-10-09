#!/usr/bin/env python3
"""Vera entrypoint for the shared managed Python runtime."""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import runpy
import sys
import tempfile
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
        if run_index + 1 < len(arguments):
            runtime_selection = _IMPLEMENTATION.select_runtime(
                root, selection.module, selection.requirements
            )
            script = (
                runtime_selection.requirement_root / arguments[run_index + 1]
            ).resolve()
            if not script.is_relative_to(runtime_selection.requirement_root):
                logging.error("Managed runtime script outside module root: %s", script)
                return 2
            if not script.is_file():
                logging.error("Managed runtime script not found: %s", script)
                return 2
    try:
        root = prepare_execution_root(root, selection.module)
    except (OSError, ValueError) as error:
        logging.error("Vera installation verification failed: %s", error)
        return 1
    result = _IMPLEMENTATION.main(root, arguments)
    if result < 0 or result in {137, 247}:
        _report_forced_termination(arguments, result, selection.module)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
