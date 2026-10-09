"""Actual read-only Rating and sealed predecessor evidence, without write bypass."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tests.model_data_helpers import write_no_model_report
from tests.plugins.test_rating_legalita_case import CASE
from tests.plugins.test_vera_client_workflow_filesystem import _load_customer_ledger
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_rating import rating_run  # noqa: F401
from tests.plugins.test_vera_native_workspace import configure

__all__ = []

READ = """
const setup=payload(call('vera_workspace_rating_setup',{work_ref:'fictional-rating'}));
const fields={case_input_id:setup.items[0].id,previous_input_id:'',note:''};
const exact={work_ref:setup.work_ref,revision:setup.revision,source_ref:setup.source_ref};
"""


@pytest.mark.parametrize(
    "rating_run,status",
    [
        ("ready", "ready_for_review"),
        ("partial", "incomplete"),
        ("failed", "not_eligible"),
    ],
    indirect=["rating_run"],
)
def test_rating_actual_read_returns_complete_public_status_privately_without_writes(
    rating_run, status
):
    env, output, _ = rating_run
    result = rpc_program(
        env, READ + "const result=call('vera_workspace_rating_read',{...exact,fields});"
    )
    assert result["_meta"]["workspace"]["record"]["assessment"]["status"] == status
    assert (
        len(
            result["_meta"]["workspace"]["record"]["case"]["snapshots"][-1]["instances"]
        )
        == 41
    )
    assert "Synthetic qualified fact" not in json.dumps(result["content"])
    assert not list(output.iterdir())


@pytest.mark.parametrize("rating_run", ["many"], indirect=True)
def test_rating_actual_whole_read_retains_all_limitations_without_sampling(rating_run):
    env, output, _ = rating_run
    result = rpc_program(
        env,
        READ
        + "const result=payload(call('vera_workspace_rating_read',{...exact,fields}));",
    )
    assert len(result["record"]["case"]["limitations"]) == 91
    assert "Fictional complete limitation 90" in result["report"]
    assert not list(output.iterdir())


@pytest.mark.parametrize("variant", ["valid", "omit_previous", "rewrite_old_snapshot"])
def test_rating_sealed_archive_predecessor_is_required_and_old_snapshots_remain_immutable(
    rating_run, monkeypatch, tmp_path, variant
):
    _, output, binding = rating_run
    ledger = _load_customer_ledger()
    client = Path(binding["client_root"])
    loaded = ledger.load_run(client, binding["engagement_id"], binding["run_id"])
    inputs = loaded["input_manifest"]["inputs"]
    case_path = next(
        Path(loaded["run_root"]) / r["execution_relative_path"]
        for r in inputs
        if Path(r["execution_relative_path"]).suffix == ".json"
    )
    original = json.loads(case_path.read_bytes())
    previous = CASE.assess_case(original, Path(loaded["run_root"]) / "inputs")
    CASE.save_dossier(previous, output)
    declarations = write_no_model_report(output, "rating-legalita", binding["run_id"])
    declarations += [
        {
            "path": previous["record_sha256"] + "/" + name,
            "artifact_id": "fictional-" + name.replace(".", "-"),
            "purpose": "Preserve this fictional prior dossier.",
            "audience": "review",
            "media_type": (
                "application/json" if name.endswith("json") else "text/markdown"
            ),
        }
        for name in ("dossier.json", "dossier.md")
    ]
    ledger.finalize_run(
        client, binding["engagement_id"], binding["run_id"], declarations
    )
    continued = copy.deepcopy(original)
    snapshot = copy.deepcopy(continued["snapshots"][-1])
    snapshot["snapshot_id"] = "OBS-2"
    continued["snapshots"].append(snapshot)
    if variant == "rewrite_old_snapshot":
        continued["snapshots"][0]["conditions"] = ["Retrospective fictional rewrite"]
    source = tmp_path / "fictional-rating-continuation.json"
    source.write_text(json.dumps(continued))
    receipt = ledger.import_document(
        client, binding["client_id"], binding["engagement_id"], source, "source"
    )["receipt"]
    evidence_ids = [
        r["binding_id"]
        for r in inputs
        if Path(r["execution_relative_path"]).suffix != ".json"
    ]
    prepared = ledger.prepare_run(
        client,
        binding["client_id"],
        binding["engagement_id"],
        "rating-legalita",
        "development",
        input_ids=[*evidence_ids, receipt["input_id"]],
        upstream_artifacts=[
            {
                "run_id": binding["run_id"],
                "artifact_id": "fictional-dossier-json",
                "role": "previous_dossier",
            }
        ],
    )
    started = ledger.start_run(
        client, binding["engagement_id"], prepared["run"]["run_id"]
    )
    new_env = configure(
        monkeypatch, tmp_path, [{**binding, "run_id": started["run"]["run_id"]}]
    )
    selection = "''" if variant == "omit_previous" else "setup.predecessors[0].id"
    result = rpc_program(
        new_env,
        READ
        + f"const result=call('vera_workspace_rating_read',{{...exact,fields:{{...fields,previous_input_id:{selection}}}}});",
    )
    if variant == "valid":
        record = result["_meta"]["workspace"]["record"]
        assert record["previous_record_sha256"] == previous["record_sha256"]
        assert record["case"]["snapshots"][:2] == original["snapshots"]
        assert record["case"]["snapshots"][-1]["snapshot_id"] == "OBS-2"
    else:
        assert result["isError"] is True
        assert set(result["_meta"]["workspace"]) == {"error"}
    assert not list(Path(started["output_dir"]).iterdir())
