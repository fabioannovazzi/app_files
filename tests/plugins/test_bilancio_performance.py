from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "bilancio-xbrl-it"
SCRIPTS = PLUGIN_ROOT / "scripts"
RULE_PACK = PLUGIN_ROOT / "rulepacks" / "it" / "statutory-forms-2026.1.json"


def _load_benchmark():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    path = SCRIPTS / "benchmark_performance.py"
    spec = importlib.util.spec_from_file_location("bilancio_performance", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


benchmark = _load_benchmark()


def test_performance_benchmark_records_reproducible_target_evidence(
    tmp_path: Path,
) -> None:
    output = tmp_path / "benchmark"

    result = benchmark.run_benchmark(output, RULE_PACK, row_count=100)

    manifest_path = output / "performance-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert result["status"] == "PASS"
    assert result["row_count"] == 100
    assert result["deterministic_recompute"] is True
    assert manifest["status"] == "PASS"
    assert (
        result["manifest_sha256"]
        == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    )
    assert set(result["targets"]) == {
        "parse_20k",
        "statement_recompute",
        "local_validation",
    }
    assert all(item["status"] == "PASS" for item in result["targets"].values())


def test_mapping_batch_audit_reuses_exact_post_mutation_hash(tmp_path: Path) -> None:
    output = tmp_path / "benchmark"
    benchmark.run_benchmark(output, RULE_PACK, row_count=100)
    case = json.loads((output / "case" / "case.json").read_text(encoding="utf-8"))

    mapping_events = [
        event for event in case["audit_events"] if event["action"] == "mapping_accepted"
    ]

    assert len(mapping_events) == 100
    assert len({event["after_hash"] for event in mapping_events}) == 1
    assert mapping_events[0]["before_hash"] is not None
    assert all(event["before_hash"] is None for event in mapping_events[1:])


@pytest.mark.parametrize("row_count", [1, 3, 20_002])
def test_performance_benchmark_rejects_unsupported_row_count(
    tmp_path: Path, row_count: int
) -> None:
    with pytest.raises(ValueError, match="row_count"):
        benchmark.run_benchmark(tmp_path / "benchmark", RULE_PACK, row_count=row_count)


def test_performance_benchmark_refuses_nonempty_output(tmp_path: Path) -> None:
    output = tmp_path / "benchmark"
    output.mkdir()
    (output / "existing.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="must be empty"):
        benchmark.run_benchmark(output, RULE_PACK, row_count=100)
