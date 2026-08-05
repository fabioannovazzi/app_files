from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins" / "bilancio-xbrl-it" / "scripts"


def _load_module(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"bilancio_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


intelligence_runner = _load_module("intelligence_runner")


def test_command_intelligence_runner_uses_json_stdin_and_strict_response() -> None:
    response = {
        "output": {"summary_it": "Esaminare i dati."},
        "model_metadata": {
            "provider": "test",
            "model": "test-model",
            "prompt_template_version": "v1",
        },
    }
    script = (
        "import json,sys; packet=json.load(sys.stdin); "
        "assert packet['task']=='WORKFLOW_GUIDANCE'; "
        f"json.dump({response!r},sys.stdout)"
    )
    runner = intelligence_runner.intelligence_runner_from_json(
        json.dumps([sys.executable, "-c", script])
    )

    result = runner({"task": "WORKFLOW_GUIDANCE"})

    assert result == response


def test_command_intelligence_runner_rejects_nonzero_and_invalid_shape() -> None:
    failing = intelligence_runner.intelligence_runner_from_json(
        json.dumps([sys.executable, "-c", "raise SystemExit(2)"])
    )
    invalid = intelligence_runner.intelligence_runner_from_json(
        json.dumps([sys.executable, "-c", "print('{}')"])
    )

    with pytest.raises(RuntimeError, match="did not complete"):
        failing({"task": "WORKFLOW_GUIDANCE"})
    with pytest.raises(ValueError, match="requires output"):
        invalid({"task": "WORKFLOW_GUIDANCE"})


@pytest.mark.parametrize("raw", [json.dumps("runner"), json.dumps(["runner", 1])])
def test_intelligence_runner_configuration_requires_argument_array(raw: str) -> None:
    with pytest.raises(ValueError, match="array of strings"):
        intelligence_runner.intelligence_runner_from_json(raw)
