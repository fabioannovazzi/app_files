from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _module(relative: str):
    spec = importlib.util.spec_from_file_location(Path(relative).stem, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def contract_module():
    return _module("plugins/_shared/privacy-runtime/scripts/privacy_contract.py")


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def installation(tmp_path: Path, contract_module):
    root = tmp_path / "lucia"
    entry = {
        "source": "product",
        "role": "workflow",
        "skills": ["controllo-documento"],
        "components": [],
        "workflow_ids": ["controllo-documento"],
        "public_pages": [],
    }
    _write(root / ".codex-plugin/plugin.json", {"name": "lucia", "version": "0.1.122"})
    _write(
        root / "privacy/registry.json",
        {
            "schema_version": 1,
            "product": "lucia",
            "workstreams": {"controllo-documento": entry},
            "services": [],
            "developer_skills": ["privacy-surface-review"],
        },
    )
    _write(
        root / "privacy/workstreams/controllo-documento.json",
        {
            "workstream": "controllo-documento",
            "service_ids": [],
            "runtime_profiles": ["openai-codex"],
            "model_context": {
                "classes": [{"content": "Selected text, comments and revisions."}]
            },
            "review": {"source_fingerprint": "1" * 64},
        },
    )
    _write(
        root / "privacy/runtime-profiles.json", {"profiles": [{"id": "openai-codex"}]}
    )
    document = contract_module.contract_document(root, "controllo-documento")
    raw = contract_module.canonical_bytes(document)
    digest = hashlib.sha256(raw).hexdigest()
    _write(root / "privacy/contracts/controllo-documento.json", document)
    _write(
        root / "privacy/contracts/index.json",
        {
            "product": "lucia",
            "contracts": {"controllo-documento": digest},
            "installed_contracts": {"controllo-documento": digest},
        },
    )
    (root / "scripts").mkdir()
    (root / "scripts/privacy_contract.py").write_bytes(
        (
            ROOT / "plugins/_shared/privacy-runtime/scripts/privacy_contract.py"
        ).read_bytes()
    )
    return root


def _request() -> dict:
    return {
        "schema_version": 1,
        "workflow_id": "controllo-documento",
        "run_id": "synthetic-contract-review",
        "runtime_profile": "openai-codex",
        "language": "it",
        "created_at": "2026-10-18T12:00:00+02:00",
        "professional_purpose": "Verificare un documento sintetico.",
        "phases": [
            {
                "phase_id": "proofreading",
                "purpose": "Leggere il testo selezionato.",
                "outcome": "not_measurable",
                "evidence_basis": "not_measurable",
                "source_extent": [],
                "locally_processed": [],
                "model_visible": [],
                "remained_local": [],
                "reason": "Il conteggio esatto del contesto non è disponibile.",
                "evidence_files": [],
            }
        ],
        "improvement_assessment": {"status": "not_assessed", "candidates": []},
    }


def test_run_binds_product_contract_without_inventing_observations(
    installation: Path, tmp_path: Path
):
    report_module = _module("plugins/_shared/reporting-runtime/model_data_report.py")
    request = _request()

    report, markdown = report_module.build_model_data_report(
        request, evidence_root=tmp_path, product_root=installation
    )

    assert report["schema_version"] == 2
    assert report["privacy_contract"]["product"] == "lucia"
    assert report["phases"] == request["phases"]
    assert report["contract_review"]["status"] == "not_assessed"
    assert "non verificato" in markdown
    assert report_module.validate_model_data_report(report) == report


def test_changed_runtime_profile_cannot_reuse_an_unchanged_contract(
    installation: Path, contract_module
):
    _write(
        installation / "privacy/runtime-profiles.json",
        {"profiles": [{"id": "openai-codex", "local_only": True}]},
    )

    with pytest.raises(
        contract_module.PrivacyContractError, match="dependencies changed"
    ):
        contract_module.bind_run(installation, "controllo-documento", "openai-codex")


def test_foreign_product_cannot_claim_a_contract(installation: Path, contract_module):
    _write(
        installation / ".codex-plugin/plugin.json",
        {"name": "clara", "version": "0.1.299"},
    )

    with pytest.raises(
        contract_module.PrivacyContractError, match="product does not match"
    ):
        contract_module.bind_run(installation, "controllo-documento", "openai-codex")


def test_unregistered_host_remains_explicitly_unreviewed(
    installation: Path, contract_module
):
    binding = contract_module.bind_run(
        installation, "controllo-documento", "other-host"
    )

    assert binding["status"] == "runtime_not_reviewed"


def test_semantic_divergence_is_preserved_in_the_readable_report(
    installation: Path, tmp_path: Path
):
    report_module = _module("plugins/_shared/reporting-runtime/model_data_report.py")
    request = _request()
    request["contract_review"] = {
        "status": "divergence",
        "phase_ids": ["proofreading"],
        "reason": "È stato letto anche un allegato fuori dal perimetro descritto.",
    }

    report, markdown = report_module.build_model_data_report(
        request, evidence_root=tmp_path, product_root=installation
    )

    assert report["contract_review"] == request["contract_review"]
    assert "differenze rilevate" in markdown
    assert "allegato fuori dal perimetro" in markdown


def test_contract_comparison_cannot_claim_unreviewed_phases(
    installation: Path, tmp_path: Path
):
    report_module = _module("plugins/_shared/reporting-runtime/model_data_report.py")
    request = _request()
    request["contract_review"] = {
        "status": "consistent",
        "phase_ids": [],
        "reason": "Controllo dichiarato senza fasi.",
    }

    with pytest.raises(report_module.ModelDataReportError, match="all actual phases"):
        report_module.build_model_data_report(
            request, evidence_root=tmp_path, product_root=installation
        )


def test_old_and_bound_reports_reopen_without_the_original_installation(
    installation: Path, tmp_path: Path
):
    report_module = _module("plugins/_shared/reporting-runtime/model_data_report.py")
    old_report, _ = report_module.build_model_data_report(
        _request(), evidence_root=tmp_path
    )
    bound_report, _ = report_module.build_model_data_report(
        _request(), evidence_root=tmp_path, product_root=installation
    )
    _write(installation / "privacy/contracts/index.json", {"product": "changed"})

    old_result = report_module.validate_model_data_report(copy.deepcopy(old_report))
    bound_result = report_module.validate_model_data_report(copy.deepcopy(bound_report))

    assert old_result == old_report
    assert old_result["schema_version"] == 1
    assert bound_result == bound_report


@pytest.mark.parametrize(
    "mutation, message",
    [
        ("missing-alias", "exactly one"),
        ("foreign-contract", "foreign identity"),
        ("wrong-index", "match its index"),
        ("missing-contract", "Cannot read"),
        ("outside-contract", "symlink"),
    ],
)
def test_run_rejects_missing_or_foreign_contract_evidence(
    installation, contract_module, mutation, message
):
    workflow = "controllo-documento"
    contract_path = installation / "privacy/contracts/controllo-documento.json"
    if mutation == "missing-alias":
        workflow = "unregistered"
    elif mutation == "foreign-contract":
        payload = json.loads(contract_path.read_text())
        payload["product"] = "clara"
        _write(contract_path, payload)
    elif mutation == "wrong-index":
        index = installation / "privacy/contracts/index.json"
        payload = json.loads(index.read_text())
        payload["contracts"][workflow] = "0" * 64
        _write(index, payload)
    elif mutation == "missing-contract":
        contract_path.unlink()
    elif mutation == "outside-contract":
        outside = installation.parent / "outside.json"
        outside.write_bytes(contract_path.read_bytes())
        contract_path.unlink()
        contract_path.symlink_to(outside)

    with pytest.raises(contract_module.PrivacyContractError, match=message):
        contract_module.bind_run(installation, workflow, "openai-codex")


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
def test_public_contracts_and_runtime_use_the_same_review(product, contract_module):
    root = ROOT / "plugins" / product
    registry = json.loads((root / "privacy/registry.json").read_text())
    public = json.loads(
        (ROOT / f"static/shared/privacy-contracts/{product}.json").read_text()
    )
    index = json.loads((root / "privacy/contracts/index.json").read_text())
    for name, entry in registry["workstreams"].items():
        document = contract_module.contract_document(root, name)
        digest = hashlib.sha256(contract_module.canonical_bytes(document)).hexdigest()
        assert index["contracts"][name] == digest
        for page in entry["public_pages"]:
            assert (ROOT / page["path"]).is_file()
            assert public["pages"][page["page_id"]]["contract_sha256"] == digest
            assert (
                public["pages"][page["page_id"]]["copy"]
                == document["manifest"]["public_explanations"][page["page_id"]]["copy"]
            )
    assert (
        "studio-archive"
        not in json.loads((root / "usage/pipelines.json").read_text())["pipelines"]
    )


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
def test_every_public_function_link_has_a_product_specific_privacy_owner(product):
    product_page = ROOT / f"static/shared/{product}/index.html"
    registry = json.loads(
        (ROOT / f"plugins/{product}/privacy/registry.json").read_text()
    )
    registered = {
        str((ROOT / page["path"]).resolve())
        for entry in registry["workstreams"].values()
        for page in entry["public_pages"]
    }
    hrefs = re.findall(
        r'<a class="(?:module-row|function-link)"[^>]+href="([^"]+)"',
        product_page.read_text(),
    )
    linked = {
        str((product_page.parent / urlsplit(href).path).resolve()) for href in hrefs
    }
    assert linked <= registered


def test_host_specific_package_cannot_claim_another_host_review(
    installation, contract_module
):
    manifest_path = installation / "privacy/workstreams/controllo-documento.json"
    manifest = json.loads(manifest_path.read_text())
    index_path = installation / "privacy/contracts/index.json"
    index = json.loads(index_path.read_text())
    manifest["source_contract_sha256"] = index["contracts"]["controllo-documento"]
    manifest["packaged_for_runtime"] = "anthropic-cowork"
    _write(manifest_path, manifest)
    index["installed_contracts"]["controllo-documento"] = hashlib.sha256(
        contract_module.canonical_bytes(
            contract_module.contract_document(installation, "controllo-documento")
        )
    ).hexdigest()
    _write(index_path, index)

    binding = contract_module.bind_run(
        installation, "controllo-documento", "openai-codex"
    )

    assert binding["status"] == "runtime_not_reviewed"


def test_package_rejects_an_unreviewed_missing_helper(tmp_path, monkeypatch):
    from zipfile import ZipFile

    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    from project_product_privacy import project_privacy

    archive_path = ROOT / "plugin_packages/lucia/lucia-claude-plugin.zip"
    with ZipFile(archive_path) as archive:
        entries = {
            name: archive.read(name)
            for name in archive.namelist()
            if not name.endswith("/")
        }
    del entries["scripts/legal_proofreading.py"]

    with pytest.raises(ValueError, match="omissions differ"):
        project_privacy(entries, "lucia", host="anthropic-cowork", source_root=ROOT)


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
def test_every_user_workflow_has_a_public_explanation(product):
    registry = json.loads(
        (ROOT / "plugins" / product / "privacy/registry.json").read_text()
    )
    missing = [
        name
        for name, entry in registry["workstreams"].items()
        if entry["role"] == "workflow" and not entry["public_pages"]
    ]
    assert missing == []
