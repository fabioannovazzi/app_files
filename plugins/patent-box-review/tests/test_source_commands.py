"""Host source commands retain real local receipts across the CLI boundary."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from patent_box import source_acquisition as acquisition
from patent_box.source_transport import PublicResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_source_acquisition import document_scan, plan, review

ROOT = Path(__file__).resolve().parents[1]


def cli() -> Any:
    spec = importlib.util.spec_from_file_location(
        "patent_box_source_commands_test", ROOT / "scripts/patent_box_sources.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save(path: Path, data: Any) -> Path:
    path.write_text(json.dumps(data))
    return path


def invoke(module: Any, args: list[str], capsys: Any) -> dict[str, Any]:
    assert module.main(args) == 0
    return json.loads(capsys.readouterr().out)


def test_open_cli_creates_bound_scan_and_acquire_cli_preserves_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    command = cli()
    p = save(tmp_path / "plan.json", plan("https://institution.example/document"))
    scan = invoke(
        command, ["open", "--plan", str(p), "--output-root", str(tmp_path)], capsys
    )
    fetch = lambda url, **kwargs: PublicResponse(
        url, "text/html; charset=utf-8", b"<p>Observed document</p>"
    )
    monkeypatch.setattr(
        command,
        "acquire",
        lambda *args, **kwargs: acquisition.acquire(*args, fetcher=fetch, **kwargs),
    )

    receipt = invoke(
        command,
        [
            "acquire",
            "--scan",
            scan["directory"],
            "--scope-id",
            "PUBLIC",
            "--url",
            "https://institution.example/document",
            "--kind",
            "DOCUMENT",
        ],
        capsys,
    )

    assert receipt["original_sha256"] is not None
    assert (
        Path(scan["directory"]) / "receipts" / f"{receipt['receipt_id']}.json"
    ).is_file()


def test_attach_text_cli_preserves_extractor_identity_then_finish_freezes_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    command = cli()
    root = Path(
        acquisition.open_scan(plan("https://institution.example/document"), tmp_path)[
            "directory"
        ]
    )
    receipt = acquisition.acquire(
        root,
        scope_id="PUBLIC",
        url="https://institution.example/document",
        kind="DOCUMENT",
        fetcher=lambda url, **kw: PublicResponse(
            url, "application/pdf", b"%PDF synthetic text extraction fixture"
        ),
    )
    text = tmp_path / "text.txt"
    text.write_text("Host-extracted fixture text")
    attached = invoke(
        command,
        [
            "attach-text",
            "--scan",
            str(root),
            "--receipt-id",
            receipt["receipt_id"],
            "--text",
            str(text),
            "--extractor",
            "fixture.v1",
        ],
        capsys,
    )
    approval = save(tmp_path / "review.json", review(receipt))

    final = invoke(
        command, ["finish", "--scan", str(root), "--review", str(approval)], capsys
    )

    assert final["snapshot"]["coverage"] == "COMPLETE_DECLARED_SCOPE"
    assert final["source_activation"] == "NONE"
    assert attached["extractor"] == "fixture.v1"
    assert (root / "final.json").is_file()


def test_compare_and_private_impact_cli_keep_approved_version(
    tmp_path: Path, capsys: Any
) -> None:
    command = cli()
    before = document_scan(tmp_path, b"<p>Before</p>")
    after = document_scan(tmp_path, b"<p>After</p>")
    comparison = invoke(
        command, ["compare", "--before", str(before), "--after", str(after)], capsys
    )
    case_index = {
        "schema_version": "1.0",
        "cases": [
            {
                "case_id": "opaque.test",
                "regime": "NEW",
                "state": "APPROVED",
                "period_start": "2025-01-01",
                "period_end": "2025-12-31",
                "rule_ids": ["PB.COST"],
                "approved_hash": "a" * 64,
            }
        ],
    }
    source = save(tmp_path / "private-index.json", case_index)
    original = source.read_bytes()
    target = tmp_path / "private-queue.json"

    queue = invoke(
        command,
        [
            "impact",
            "--before",
            str(before),
            "--after",
            str(after),
            "--private-case-index",
            str(source),
            "--private-output",
            str(target),
        ],
        capsys,
    )

    assert comparison["events"]
    assert queue["items"][0]["action"] == "PROPOSE_REOPEN"
    assert source.read_bytes() == original
    assert target.is_file()


def test_impact_cli_rejects_private_case_index_inside_public_scan(
    tmp_path: Path, capsys: Any
) -> None:
    command = cli()
    before = document_scan(tmp_path, b"<p>Before</p>")
    after = document_scan(tmp_path, b"<p>After</p>")

    # The repository import-isolation fixture can reload the package between tests.
    # Bind the expected exception to the actual CLI instance under test.
    with pytest.raises(command.ContractError, match="outside public"):
        command.main(
            [
                "impact",
                "--before",
                str(before),
                "--after",
                str(after),
                "--private-case-index",
                str(after / "client.json"),
                "--private-output",
                str(tmp_path / "queue.json"),
            ]
        )


@pytest.mark.parametrize("value", [[], None, "not an object"])
def test_open_cli_rejects_non_object_plan(tmp_path: Path, value: Any) -> None:
    path = save(tmp_path / "invalid.json", value)
    command = cli()

    with pytest.raises(command.ContractError, match="Expected an object"):
        command.main(["open", "--plan", str(path), "--output-root", str(tmp_path)])


def test_monitor_cli_retains_default_off_state_and_failed_host_attempt(
    tmp_path, capsys
):
    command = cli()
    private = tmp_path / "private-service"
    research = save(
        tmp_path / "monitor-plan.json", plan("https://institution.example/document")
    )
    config = invoke(
        command,
        [
            "monitor-configure",
            "--private-root",
            str(private),
            "--public-root",
            str(tmp_path / "public"),
            "--owner",
            "Synthetic owner",
            "--plan",
            str(research),
        ],
        capsys,
    )
    request = invoke(
        command,
        [
            "monitor-begin",
            "--private-root",
            str(private),
            "--plan",
            str(research),
            "--trigger",
            "OPEN_CASE",
        ],
        capsys,
    )
    failed = invoke(
        command,
        [
            "monitor-fail",
            "--private-root",
            str(private),
            "--job-id",
            request["job_id"],
            "--reason",
            "Synthetic unavailable host",
        ],
        capsys,
    )
    state = invoke(command, ["monitor-status", "--private-root", str(private)], capsys)
    assert config["initial_schedule_enabled"] is False
    assert failed["notification_required"] is True
    assert state["schedule_active"] is False
    assert state["pending_jobs"] == []
