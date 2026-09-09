from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "plugins/browser-automation/scripts"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def helper(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return load(SCRIPTS / "development_request.py", "development_request")


def request():
    return {
        "schema_version": "browser-development-request/v1",
        "request_id": "teamsystem-purchase",
        "title": "Rendere riutilizzabile la registrazione",
        "process": "TeamSystem ECONS acquisti",
        "objective": "Ripetere il processo insegnato",
        "source_version": "Riferita dall’operatore: 0.1.226",
        "findings": [
            {
                "summary": "L’esempio funziona secondo Francesco",
                "basis": "operator_report",
                "step_ids": [],
            }
        ],
        "requested_work": ["Riprendere le decisioni già salvate"],
        "acceptance_checks": [
            "Un esempio autorizzato produce un risultato controllabile"
        ],
        "gaps": ["Manca il pacchetto tecnico completo"],
        "known_limits": ["Non provato su altri clienti"],
    }


def test_partial_teaching_produces_one_reviewed_zip_without_fake_cr(helper, tmp_path):
    directory = tmp_path / "review"
    prepared = helper.prepare_request(request(), directory)
    assert prepared["archive_created"] is False
    assert "Riferito dall’operatore" in (directory / "RICHIESTA.md").read_text(
        encoding="utf-8"
    )
    archive = helper.export_request(
        directory,
        tmp_path / "request.zip",
        expected_sha256=prepared["review_sha256"],
        approval_id="operator-message-1",
    )
    assert helper.verify_archive(archive) == {
        "request_id": "teamsystem-purchase",
        "integrity_verified": True,
        "sent": False,
        "cr_id": None,
    }
    with ZipFile(archive) as zipped:
        assert set(zipped.namelist()) == {
            "RICHIESTA.md",
            "request.json",
            "sources.json",
            "review-manifest.json",
            "transfer-approval.json",
        }


@pytest.mark.parametrize(
    "mutation", ["edit", "extra", "symlink", "manifest", "no-approval"]
)
def test_export_rejects_unapproved_or_changed_content(helper, tmp_path, mutation):
    directory = tmp_path / "review"
    prepared = helper.prepare_request(request(), directory)
    approval = "operator-message-1"
    if mutation == "edit":
        (directory / "request.json").write_text("{}")
    elif mutation == "extra":
        (directory / "private-invoice.txt").write_text("private")
    elif mutation == "symlink":
        (directory / "extra").symlink_to(directory / "request.json")
    elif mutation == "manifest":
        (directory / "review-manifest.json").write_text("{}")
    else:
        approval = ""
    with pytest.raises(ValueError):
        helper.export_request(
            directory,
            tmp_path / "request.zip",
            expected_sha256=prepared["review_sha256"],
            approval_id=approval,
        )
    assert not (tmp_path / "request.zip").exists()


@pytest.mark.parametrize(
    "key,value",
    [
        ("schema_version", "wrong"),
        ("request_id", "CR 99"),
        ("title", ""),
        ("requested_work", []),
        ("acceptance_checks", []),
        ("gaps", "text"),
        ("findings", [{"summary": "ok", "basis": "verified", "step_ids": []}]),
        ("findings", [{"summary": "ok", "basis": "observed", "step_ids": []}]),
        ("findings", [{"summary": "ok", "basis": "unknown", "step_ids": ["missing"]}]),
        ("findings", [{"summary": "ok", "basis": "unknown", "step_ids": None}]),
        ("findings", [{}]),
        ("findings", "text"),
    ],
)
def test_invalid_or_unsupported_claims_rejected_before_writing(
    helper, tmp_path, key, value
):
    payload = request()
    payload[key] = value
    with pytest.raises(ValueError):
        helper.prepare_request(payload, tmp_path / "review")
    assert not (tmp_path / "review").exists()


def test_checkpoint_projection_excludes_private_teaching_text(helper, tmp_path):
    checkpoint_helper = load(SCRIPTS / "teaching_checkpoint.py", "checkpoint")
    fixture = load(
        ROOT / "tests/test_browser_teaching_checkpoint.py", "checkpoint_fixture"
    )
    state = fixture.payload()
    state["steps"][0]["decision_reason"] = "PRIVATE CLIENT SECRET"
    checkpoint_helper.save_checkpoint(
        tmp_path / "checkpoint", state, expected_revision=0
    )
    payload = request()
    payload["findings"] = [
        {
            "summary": "Account controls appeared",
            "basis": "observed",
            "step_ids": ["choose-account"],
        }
    ]
    helper.prepare_request(
        payload, tmp_path / "review", checkpoint=tmp_path / "checkpoint"
    )
    sources = (tmp_path / "review/sources.json").read_text(encoding="utf-8")
    assert "PRIVATE CLIENT SECRET" not in sources
    assert (
        json.loads(sources)["step_evidence"][0]["capture"]["before_sha256"] == "a" * 64
    )
    assert not (tmp_path / "review/checkpoint").exists()


def test_reported_checkpoint_step_cannot_become_observed(helper, tmp_path):
    checkpoint_helper = load(SCRIPTS / "teaching_checkpoint.py", "checkpoint")
    fixture = load(
        ROOT / "tests/test_browser_teaching_checkpoint.py", "checkpoint_fixture"
    )
    state = fixture.payload()
    state["steps"][0].update(evidence_basis="operator_report", capture=None)
    checkpoint_helper.save_checkpoint(
        tmp_path / "checkpoint", state, expected_revision=0
    )
    payload = request()
    payload["findings"] = [
        {"summary": "Claim", "basis": "observed", "step_ids": ["choose-account"]}
    ]
    with pytest.raises(ValueError, match="promoted"):
        helper.prepare_request(
            payload, tmp_path / "review", checkpoint=tmp_path / "checkpoint"
        )


def test_real_sealed_pack_is_included_and_verified(helper, tmp_path):
    fixture = load(
        ROOT / "tests/test_browser_automation_discovery_pack.py", "pack_fixture"
    )
    pipeline, pack = fixture._modules()
    draft, discovery = fixture._draft_and_discovery(pipeline)
    evidence = fixture._evidence(pipeline, draft, discovery, approved=True)
    source = pack.seal_developer_pack(
        fixture._write_json(tmp_path / "evidence.json", evidence),
        fixture._write_json(tmp_path / "discovery.json", discovery),
        fixture._write_json(tmp_path / "draft.json", draft),
        tmp_path / "packs",
    )
    prepared = helper.prepare_request(
        request(), tmp_path / "review", developer_pack=source
    )
    archive = helper.export_request(
        tmp_path / "review",
        tmp_path / "request.zip",
        expected_sha256=prepared["review_sha256"],
        approval_id="operator-message-1",
    )
    with ZipFile(archive) as zipped:
        assert (
            zipped.read("developer-pack/capability.draft.json")
            == (source / "capability.draft.json").read_bytes()
        )
    assert helper.verify_archive(archive)["sent"] is False


def test_incomplete_pack_does_not_get_exported(helper, tmp_path):
    with pytest.raises(ValueError):
        helper.prepare_request(
            request(), tmp_path / "review", developer_pack=tmp_path / "missing"
        )


@pytest.mark.parametrize(
    "mutation", ["extra", "changed", "missing", "traversal", "approval", "manifest"]
)
def test_archive_tampering_is_detected_without_extraction(helper, tmp_path, mutation):
    prepared = helper.prepare_request(request(), tmp_path / "review")
    archive = helper.export_request(
        tmp_path / "review",
        tmp_path / "ok.zip",
        expected_sha256=prepared["review_sha256"],
        approval_id="operator-message-1",
    )
    with ZipFile(archive) as zipped:
        files = {name: zipped.read(name) for name in zipped.namelist()}
    if mutation == "extra":
        files["extra.txt"] = b"private"
    elif mutation == "changed":
        files["request.json"] = b"{}"
    elif mutation == "missing":
        del files["sources.json"]
    elif mutation == "traversal":
        files["../outside"] = b"private"
    elif mutation == "approval":
        files["transfer-approval.json"] = b"{}"
    else:
        files["review-manifest.json"] = b"{}"
    target = tmp_path / "tampered.zip"
    with ZipFile(target, "w") as zipped:
        for name, data in files.items():
            zipped.writestr(name, data)
    with pytest.raises(ValueError):
        helper.verify_archive(target)


def test_size_limit_applies_before_preparation(helper, tmp_path):
    payload = request()
    payload["gaps"] = ["x" * 6000] * 9
    with pytest.raises(ValueError, match="CR text limit"):
        helper.prepare_request(payload, tmp_path / "review")


def test_cli_prepare_export_verify_and_malformed_file(helper, tmp_path):
    source = tmp_path / "input.json"
    source.write_text(json.dumps(request()))
    directory = tmp_path / "review"
    assert (
        helper.main(["prepare", "--input", str(source), "--output", str(directory)])
        == 0
    )
    manifest = json.loads(
        (directory / "review-manifest.json").read_text(encoding="utf-8")
    )
    archive = tmp_path / "request.zip"
    assert (
        helper.main(
            [
                "export",
                str(directory),
                "--output",
                str(archive),
                "--review-sha256",
                helper.sha256_payload(manifest),
                "--approval-id",
                "operator-message-1",
            ]
        )
        == 0
    )
    assert helper.main(["verify", str(archive)]) == 0
    invalid = tmp_path / "invalid.zip"
    invalid.write_text("not a zip")
    assert helper.main(["verify", str(invalid)]) == 1
