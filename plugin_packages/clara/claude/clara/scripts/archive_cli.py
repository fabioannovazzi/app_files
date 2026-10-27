"""Record a bound Vera command's actual stdout before releasing it to its caller."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from archive_emit import _run_roots, bind_output, selected_run
from archive_reporting import record_send
from archive_reporting_failure import REPORTING_ERRORS, reporting_failure

__all__ = ["run_command", "run_entrypoint"]


def run_entrypoint(main: Any, component_file: Path) -> int | None:
    """Make direct Vera CLI invocation use the same owned sending boundary."""
    if (
        os.environ.get("VERA_REPORTING_INTERNAL") == "1"
        or os.environ.get("VERA_REPORTING_CAPTURED") == "1"
    ):
        return main()
    component = component_file.resolve().parents[1].name
    try:
        roots = _run_roots(sys.argv[1:])
    except REPORTING_ERRORS as error:
        reporting_failure(component, sys.argv[1:], error, stage="bind")
    else:
        if not roots:
            return main()
    product_root = Path(__file__).resolve().parents[1]
    return run_command(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            "import runpy,sys; from pathlib import Path; "
            "script=Path(sys.argv[1]); sys.path.insert(0,str(script.parent)); "
            "sys.argv=sys.argv[1:]; runpy.run_path(str(script),run_name='__main__')",
            str(component_file.resolve()),
            *sys.argv[1:],
        ],
        plugin_root=product_root,
        component=component,
        arguments=[str(component_file), *sys.argv[1:]],
        check=False,
    ).returncode


def run_command(
    command: list[str],
    *,
    plugin_root: Path,
    component: str,
    arguments: list[str],
    **options: Any,
) -> subprocess.CompletedProcess:
    """Hand the code lease to the child before a launcher can be terminated."""
    from verified_execution import acquire_execution_lease

    roots = _run_roots(arguments)
    contexts = [root / "context.json" for root in roots] if len(roots) == 1 else []
    lease = acquire_execution_lease(plugin_root)
    try:
        _checkpoint(contexts, plugin_root)
        if lease is not None:
            options["pass_fds"] = tuple(
                dict.fromkeys((*options.get("pass_fds", ()), lease))
            )
        return _run_command(
            command,
            plugin_root=plugin_root,
            component=component,
            arguments=arguments,
            **options,
        )
    finally:
        _checkpoint(contexts, plugin_root)
        if lease is not None:
            os.close(lease)


def _checkpoint(contexts: list[Path], plugin_root: Path) -> None:
    """Preserve completed stages around helpers without making backup a new gate."""
    if not contexts:
        return
    for vendor in (
        plugin_root / "vendor/modules",
        plugin_root.parent / "_shared/vendor/modules",
    ):
        if (vendor / "vera_assurance").is_dir():
            if str(vendor) not in sys.path:
                sys.path.insert(0, str(vendor))
            break
    try:
        from vera_assurance.recovery import checkpoint_run

        for context in contexts:
            checkpoint_run(context)
    except (*REPORTING_ERRORS, ImportError) as error:
        logging.getLogger(__name__).warning(
            "Work remains available; its recovery checkpoint could not refresh (%s). Retain this job and retry the checkpoint.",
            type(error).__name__,
        )


def _run_command(
    command: list[str],
    *,
    plugin_root: Path,
    component: str,
    arguments: list[str],
    **options: Any,
) -> subprocess.CompletedProcess:
    """Measure producer bytes and deliver work even if its record cannot be saved."""
    manifest = next(
        (
            plugin_root / name
            for name in (
                ".codex-plugin/plugin.json",
                ".claude-plugin/plugin.json",
            )
            if (plugin_root / name).is_file()
        ),
        None,
    )
    if (
        os.environ.get("VERA_REPORTING_INTERNAL") == "1"
        or manifest is None
        or json.loads(manifest.read_text())["name"] != "vera"
    ):
        return subprocess.run(command, **options)
    options["env"] = {**options.get("env", os.environ), "VERA_REPORTING_CAPTURED": "1"}
    try:
        binding = bind_output(component, arguments)
        if binding is None and selected_run(component, arguments) is not None:
            raise ValueError("The selected reporting collection is closed")
    except REPORTING_ERRORS as error:
        reporting_failure(component, arguments, error, stage="bind")
        binding = None
    if binding is None:
        return subprocess.run(command, **options)
    root = Path(binding["run_root"])
    destination = options.pop("stderr", None)
    if arguments and (component, Path(arguments[0]).name) in {
        ("management-control-pack", "preview_report.py"),
        ("open-item-reconciliation", "review_server.py"),
    }:
        return _stream_preview(command, root, binding, component, destination, options)
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        completed = subprocess.run(command, stdout=stdout, stderr=stderr, **options)
        stdout.seek(0)
        stderr.seek(0)
        out, err = stdout.read(), stderr.read()
        # Installed CLI helpers return UTF-8 text. Never replace undecodable bytes
        # and then claim the replacement is the exact outgoing payload.
        try:
            payload = {"stdout": out.decode("utf-8")}
            if destination is None:
                payload["stderr"] = err.decode("utf-8")
            # Pin the reporting revision; a concurrent closure must not rewrite
            # its sealed report. A delivery gap is separate from the work outcome.
            record_send(
                root,
                payload,
                channel="cli:" + component,
                request=arguments,
                expected_revision=binding["report_revision"],
            )
        except REPORTING_ERRORS as error:
            reporting_failure(component, arguments, error, stage="delivery", root=root)
        sys.stdout.buffer.write(out)
        sys.stdout.buffer.flush()
        if destination is None:
            sys.stderr.buffer.write(err)
            sys.stderr.buffer.flush()
        else:
            destination.flush()
            if hasattr(destination, "buffer"):
                destination.buffer.write(err)
                destination.buffer.flush()
            else:
                destination.write(err)
                destination.flush()
        return completed


def _stream_preview(command, root, binding, component, destination, options):
    """Release a local preview server's startup URL without waiting for shutdown."""
    options.pop("check", None)
    with subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options
    ) as child:

        def transfer(stream, name):
            for line in iter(stream.readline, b""):
                if name == "stderr" and destination is not None:
                    destination.flush()
                    target = (
                        destination.buffer
                        if hasattr(destination, "buffer")
                        else destination
                    )
                    target.write(line)
                    target.flush()
                    continue
                try:
                    payload = (
                        {"stdout": line.decode("utf-8")}
                        if name == "stdout"
                        else {"stdout": "", "stderr": line.decode("utf-8")}
                    )
                    record_send(
                        root,
                        payload,
                        channel="cli:" + component,
                        expected_revision=binding["report_revision"],
                    )
                except REPORTING_ERRORS as error:
                    reporting_failure(
                        component, [], error, stage="preview_delivery", root=root
                    )
                target = sys.stdout if name == "stdout" else sys.stderr
                target.buffer.write(line)
                target.buffer.flush()
            return True

        with ThreadPoolExecutor(max_workers=2) as workers:
            stdout = workers.submit(transfer, child.stdout, "stdout")
            stderr = workers.submit(transfer, child.stderr, "stderr")
            stdout.result()
            stderr.result()
        code = child.wait()
    return subprocess.CompletedProcess(command, code)
