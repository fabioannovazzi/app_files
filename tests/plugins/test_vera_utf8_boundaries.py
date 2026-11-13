"""Synthetic Unicode through actual isolated workers, disk and MCP restarts."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import locale
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.plugins.test_native_execution import (  # noqa: E402
    installed,
    native,
    output,
    request,
    write_index,
)

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[2]
TEXT = "Synthetic Łódź → dossier"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def scenario(kind: str, directory: Path) -> None:
    """Run with UTF-8 mode off; production code must own its encodings."""
    if os.environ.get("VERA_REQUIRE_CP1252") == "1":
        assert sys.platform == "win32"
        assert sys.flags.utf8_mode == 0
        assert locale.getencoding().lower() == "cp1252"
        with (directory / "default-encoding.txt").open("w") as stream:
            assert stream.encoding.lower() == "cp1252"
            with pytest.raises(UnicodeEncodeError):
                stream.write(TEXT)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "plugins/vera/scripts"))
    if kind == "bandi":
        from native_bandi import engine

        from tests.plugins.test_bandi_agevolazioni_plugin import _initialized_case

        _, work = _initialized_case(directory)
        target = Path(work["output_dir"]) / "case_intake.json"
        record = json.loads(target.read_text(encoding="utf-8"))
        record["professional_question"] = TEXT
        target.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        before = target.read_bytes()
        result = engine(
            ROOT / "plugins/bandi-agevolazioni",
            {"operation": "read", "context": str(work["context_path"]), "note": TEXT},
        )
        assert result["records"]["case_intake"]["professional_question"] == TEXT
        assert target.read_bytes() == before
    elif kind == "research":
        from tests.plugins.test_legal_tax_research_record import SCRIPT, _bind, _run

        folder = _run(directory)
        path = folder / "research_review.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["cycles"][0]["purpose"] = TEXT
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        module = load("unicode_research", SCRIPT)
        result = _bind(module, folder)
        retained = path.read_bytes()
        assert TEXT.encode("utf-8") in retained
        assert module.verify_research_record(folder) == result
        assert path.read_bytes() == retained
    elif kind == "cowork":
        sys.path.insert(0, str(ROOT / "plugins/passive-invoice-audit/scripts"))
        from audit_core import SemanticReviewPending
        from cowork_worker import run_cowork_chunk

        args = (TEXT, {"type": "object"}, directory, "synthetic", "a" * 64, "low")
        with pytest.raises(SemanticReviewPending):
            run_cowork_chunk(*args)
        saved = directory / "cowork_request.json"
        retained = saved.read_bytes()
        request_data = json.loads(retained)
        assert request_data["prompt"] == TEXT
        response = directory / "cowork_response.json"
        response.write_text(
            json.dumps({"text": TEXT}, ensure_ascii=False), encoding="utf-8"
        )
        (directory / "cowork_worker_record.json").write_text(
            json.dumps(
                {
                    "schema_version": "vera.cowork_worker_record.v1",
                    "request_sha256": request_data["request_sha256"],
                    "agent": request_data["agent"],
                    "requested_model": "haiku",
                    "invocation_id": TEXT,
                    "response_sha256": hashlib.sha256(
                        response.read_bytes()
                    ).hexdigest(),
                    "provenance": "cowork_host_reported",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        result = run_cowork_chunk(*args)
        assert result["response_payload"] == {"text": TEXT}
        assert saved.read_bytes() == retained
    else:
        raise AssertionError(kind)
    sys.stdout.buffer.write(
        json.dumps(
            {
                "scenario": kind,
                "text": TEXT,
                "default_encoding": locale.getencoding(),
                "utf8_mode": sys.flags.utf8_mode,
            },
            ensure_ascii=False,
        ).encode("utf-8")
    )


@pytest.mark.parametrize("kind", ["bandi", "research", "cowork"])
def test_unicode_roundtrip_with_utf8_mode_disabled(kind, tmp_path, record_property):
    directory = tmp_path / "Łódź → synthetic"
    directory.mkdir()
    env = {
        **os.environ,
        "PYTHONUTF8": "0",
        "PYTHONIOENCODING": "cp1252",
        "MPARANZA_INCIDENT_DELIVERY": "local-only",
        "MPARANZA_INCIDENT_STATE_DIR": str(tmp_path / "incidents"),
        "MPARANZA_INCIDENT_DEVICE_DIR": str(tmp_path / "device"),
    }
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-X",
            "utf8=0",
            str(Path(__file__)),
            kind,
            str(directory),
        ],
        capture_output=True,
        encoding="utf-8",
        env=env,
        timeout=90,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    data = json.loads(completed.stdout)
    assert data["text"] == TEXT
    assert data["utf8_mode"] == 0
    record_property("default_encoding", data["default_encoding"])
    record_property("utf8_mode", data["utf8_mode"])


def test_native_unicode_job_reopens_without_rerunning(installed, tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONUTF8", "0")
    monkeypatch.setenv("PYTHONIOENCODING", "cp1252")
    helper = installed / "modules/fixture-component/scripts/check_dependencies.py"
    helper.write_text(
        "import json,sys,time\nfrom pathlib import Path\n"
        "p=Path(sys.argv[1]); p.write_text(p.read_text(encoding='utf-8')+'run\\n' if p.exists() else 'run\\n',encoding='utf-8')\n"
        "time.sleep(0.3)\n"
        "sys.stdout.write(json.dumps({'text':sys.argv[2]},ensure_ascii=False))\n"
        "sys.stderr.write(sys.argv[2])\n",
        encoding="utf-8",
    )
    runtime = installed / "scripts/_managed_python_runtime.py"
    runtime.write_text(
        runtime.read_text(encoding="utf-8").replace(
            "def runtime_environment(target): return dict(os.environ)\n", ""
        ),
        encoding="utf-8",
    )
    write_index(installed)
    counter = tmp_path / "Ł-counter.txt"
    args = request(tmp_path, arguments=[str(counter), TEXT], wait_seconds=0)
    with native(installed, tmp_path) as call:
        started = call(args)
        assert output(started)[0]["state"] == "running"
    with native(installed, tmp_path) as call:
        finished = call(
            {"operation": "status", "job_id": args["job_id"], "wait_seconds": 15}
        )
        resumed = call(args)
    assert output(finished)[0]["state"] == "completed", finished
    assert json.loads(output(finished)[1]["stdout"]) == {"text": TEXT}
    assert output(finished)[1]["stderr"] == TEXT
    assert resumed == finished
    assert counter.read_text(encoding="utf-8") == "run\n"


if __name__ == "__main__":
    scenario(sys.argv[1], Path(sys.argv[2]))
