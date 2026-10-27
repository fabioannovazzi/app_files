"""Authored files stay in their selected run and retry without replacing evidence."""

from __future__ import annotations

import errno
import json
from pathlib import Path

import pytest

from tests.plugins.test_journal_bank_review_receipts import _case, _load_customer_ledger


def test_sampling_normalizer_consumes_archive_saved_recipe(tmp_path):
    from tests.plugins.test_journal_sampling_plugin import (
        _approve_suggested_recipe,
    )
    from tests.plugins.test_journal_sampling_plugin import (
        _load_customer_ledger as sampling_ledger,
    )
    from tests.plugins.test_journal_sampling_plugin import (
        _running_customer_output,
        _save_workbook,
        load_core,
    )

    source = tmp_path / "journal.xlsx"
    _save_workbook(
        source,
        [
            ["Data", "Conto", "Descrizione conto", "Descrizione", "Dare", "Avere"],
            ["2025-01-01", "1000", "Cash", "Opening", 100, None],
            ["2025-01-02", "2000", "Revenue", "Sale", None, 100],
        ],
    )
    context_path, output = _running_customer_output(tmp_path, source_path=source)
    core = load_core()
    context = core.load_client_engagement_context(context_path)
    bound = Path(context["input_bindings"][0]["path"])
    normalization = output / "normalization"
    core.inspect_path(bound, normalization, client_engagement=context)
    suggested = normalization / "suggested_recipe.json"
    original = suggested.read_bytes()
    reviewed = tmp_path / "reviewed.json"
    reviewed.write_bytes(original)
    _approve_suggested_recipe(reviewed)
    run = json.loads((output.parent / "run.json").read_text())
    saved = sampling_ledger().write_run_artifact(
        tmp_path / "Journal Customer",
        run["engagement_id"],
        run["run_id"],
        "reviewed_recipe.json",
        reviewed.read_text(),
    )

    core.normalize_path(
        bound, normalization, Path(saved["path"]), client_engagement=context
    )

    replay = core.replay_normalization_from_provenance(
        normalization / "normalized_journal.csv"
    )
    assert replay["status"] == "passed"
    assert suggested.read_bytes() == original
    assert Path(saved["path"]).read_bytes() == reviewed.read_bytes()


def test_denied_artifact_publication_can_retry_same_run(tmp_path, monkeypatch):
    case = _case(tmp_path)
    ledger = _load_customer_ledger()
    run = case["run"]
    root = tmp_path / "client"
    original = (Path(case["run_root"]) / "run.json").read_bytes()
    real_replace = ledger.os.replace

    def denied(*args, **kwargs):
        raise PermissionError(errno.EPERM, "fixture denied publication")

    monkeypatch.setattr(ledger.os, "replace", denied)
    with pytest.raises(PermissionError, match="fixture denied"):
        ledger.write_run_artifact(
            root, run["engagement_id"], run["run_id"], "draft.md", "Draft"
        )
    assert list((Path(case["output_dir"]) / "authored").iterdir()) == []

    monkeypatch.setattr(ledger.os, "replace", real_replace)
    result = ledger.write_run_artifact(
        root, run["engagement_id"], run["run_id"], "draft.md", "Draft"
    )
    assert result["run_id"] == run["run_id"]
    assert Path(result["path"]).read_text() == "Draft"
    assert (Path(case["run_root"]) / "run.json").read_bytes() == original


@pytest.mark.parametrize("content, expected", [("Draft", True), ("Changed", False)])
def test_authored_retry_preserves_existing_bytes(tmp_path, content, expected):
    case = _case(tmp_path)
    ledger = _load_customer_ledger()
    args = (
        tmp_path / "client",
        case["run"]["engagement_id"],
        case["run"]["run_id"],
        "draft.md",
    )
    saved = ledger.write_run_artifact(*args, "Draft")
    if expected:
        result = ledger.write_run_artifact(*args, content)
        assert result["replayed"] is True
        assert result["sha256"] == saved["sha256"]
    else:
        with pytest.raises(ledger.LedgerError, match="different bytes"):
            ledger.write_run_artifact(*args, content)
    assert Path(saved["path"]).read_text() == "Draft"


@pytest.mark.parametrize(
    "name", ["../run.json", "/outside-archive", "nested/file", ".."]
)
def test_authored_name_cannot_escape_owned_namespace(tmp_path, name):
    ledger = _load_customer_ledger()
    with pytest.raises(ledger.LedgerError, match="single filename"):
        ledger.write_run_artifact(tmp_path, "unused", "unused", name, "data")


def test_authored_namespace_cannot_redirect_to_sources(tmp_path):
    case = _case(tmp_path)
    ledger = _load_customer_ledger()
    (Path(case["output_dir"]) / "authored").symlink_to(tmp_path / "client")
    with pytest.raises(ledger.LedgerError, match="real directory"):
        ledger.write_run_artifact(
            tmp_path / "client",
            case["run"]["engagement_id"],
            case["run"]["run_id"],
            "draft.md",
            "data",
        )


def test_authored_writer_rejects_terminal_run(tmp_path):
    case = _case(tmp_path)
    ledger = _load_customer_ledger()
    args = (tmp_path / "client", case["run"]["engagement_id"], case["run"]["run_id"])
    ledger.cancel_run(*args)
    with pytest.raises(ledger.LedgerError, match="running run"):
        ledger.write_run_artifact(*args, "draft.md", "data")
