from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = ROOT / "plugins" / "clara" / "scripts"
LINEAGE_PATH = SCRIPTS_ROOT / "advisory_evidence_lineage.py"
CORE_PATH = SCRIPTS_ROOT / "advisor_case_core.py"
WEB_CAPTURE_PATH = SCRIPTS_ROOT / "capture_advisory_web_evidence.py"
REPORTING_CONTRIBUTION_PATH = SCRIPTS_ROOT / "record_reporting_contribution.py"
RECORDED_AT = "2026-08-18T08:00:00+00:00"


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS_ROOT))
    try:
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPTS_ROOT))
    return module


def _lineage() -> Any:
    return _load(LINEAGE_PATH, "clara_advisory_evidence_lineage_test")


def _receipt(
    evidence_id: str,
    *,
    observation: str,
    evidence_type: str = "web_capture",
    capture_status: str = "captured",
    artifact_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": evidence_id,
        "evidence_type": evidence_type,
        "recorded_at": RECORDED_AT,
        "recorded_by": "clara:clara",
        "capture_status": capture_status,
        "source": {
            "material_ids": [],
            "url": "https://example.test/inventory",
            "locator": "captured inventory page",
            "artifact_refs": artifact_refs or [],
        },
        "observation": observation,
        "scope": "The captured page at the recorded time.",
        "limitations": ["A listing count is not total company inventory."],
        "verification": {
            "status": "not_checked",
            "checked_at": "",
            "method": "",
            "notes": [],
        },
        "rechecks_evidence_id": "",
        "supersedes_evidence_id": "",
    }


def _claim(
    claim_id: str,
    statement: str,
    *,
    evidence_ids: list[str] | None = None,
    dependency_ids: list[str] | None = None,
    dependency_mode: str = "none",
    claim_type: str = "observation",
) -> dict[str, Any]:
    evidence_ids = evidence_ids or []
    dependency_ids = dependency_ids or []
    return {
        "id": claim_id,
        "statement": statement,
        "claim_type": claim_type,
        "recorded_at": RECORDED_AT,
        "recorded_by": "clara:clara",
        "provenance": {
            "workflow": "clara:clara",
            "step": "commercial evidence review",
            "artifact": "analysis.md",
            "locator": claim_id,
        },
        "evidence_links": [
            {
                "evidence_id": evidence_id,
                "relationship": "supports",
                "analysis": "The evidence directly records this observation.",
                "proves": statement,
                "does_not_prove": "Any broader population or conclusion.",
            }
            for evidence_id in evidence_ids
        ],
        "dependency": {
            "mode": dependency_mode,
            "claim_ids": dependency_ids,
            "derivation_type": "reasoning" if dependency_ids else "direct",
            "explanation": (
                "The conclusion requires every named premise."
                if dependency_ids
                else "Directly stated or observed."
            ),
            "calculation_evidence_id": "",
        },
        "decision_use": "supporting",
        "uncertainty": [],
        "professional_judgement_required": False,
        "appearances": [],
        "state": "active",
        "supersedes_claim_id": "",
    }


def test_initialize_lineage_creates_empty_structured_registers(tmp_path: Path) -> None:
    lineage = _lineage()

    paths = lineage.initialize_lineage(tmp_path)

    assert json.loads(paths["evidence_register"].read_text())["evidence"] == []
    assert json.loads(paths["claim_register"].read_text())["claims"] == []
    assert lineage.validate_lineage(tmp_path)["valid"] is True
    assert "does not prove that a claim is correct" in paths["evidence_map"].read_text()


def test_initialize_lineage_refuses_to_erase_non_empty_history(tmp_path: Path) -> None:
    lineage = _lineage()
    lineage.initialize_lineage(tmp_path)
    lineage.record_evidence(
        tmp_path,
        [_receipt("ev-history", observation="A retained source observation.")],
    )

    with pytest.raises(lineage.LineageError, match="refusing to overwrite"):
        lineage.initialize_lineage(tmp_path, overwrite=True)

    evidence = json.loads(
        (tmp_path / "advisory_evidence_register.json").read_text(encoding="utf-8")
    )
    assert [item["id"] for item in evidence["evidence"]] == ["ev-history"]


def test_register_distinguishes_thirteen_listings_from_three_hundred_stock(
    tmp_path: Path,
) -> None:
    lineage = _lineage()
    lineage.initialize_lineage(tmp_path)
    listing_receipt = _receipt(
        "ev-web-13",
        observation="Thirteen vehicle listings were visible on the captured page.",
    )
    management_receipt = _receipt(
        "ev-management-300",
        observation="Management stated that the company had 300 vehicles in stock.",
        evidence_type="management_assertion",
        capture_status="assertion_only",
    )
    management_receipt["source"]["url"] = ""

    lineage.record_evidence(tmp_path, [listing_receipt, management_receipt])
    lineage.record_claims(
        tmp_path,
        [
            _claim(
                "cl-visible-13",
                "Thirteen vehicle listings were visible on the captured page.",
                evidence_ids=["ev-web-13"],
            ),
            _claim(
                "cl-management-300",
                "Management stated that the company had 300 vehicles in stock.",
                evidence_ids=["ev-management-300"],
                claim_type="assertion",
            ),
        ],
    )

    claims = json.loads((tmp_path / "advisory_claim_register.json").read_text())
    links = {
        item["id"]: item["evidence_links"][0]["evidence_id"]
        for item in claims["claims"]
    }
    assert links == {
        "cl-visible-13": "ev-web-13",
        "cl-management-300": "ev-management-300",
    }
    assert lineage.validate_lineage(tmp_path)["valid"] is True


def test_all_of_dependency_is_preserved_and_cycle_is_rejected(tmp_path: Path) -> None:
    lineage = _lineage()
    lineage.initialize_lineage(tmp_path)
    evidence_a = _receipt("ev-a", observation="Premise A")
    evidence_b = _receipt("ev-b", observation="Premise B")
    lineage.record_evidence(tmp_path, [evidence_a, evidence_b])
    first = _claim("cl-a", "Premise A", evidence_ids=["ev-a"])
    second = _claim("cl-b", "Premise B", evidence_ids=["ev-b"])
    conclusion = _claim(
        "cl-x",
        "Conclusion X",
        dependency_ids=["cl-a", "cl-b"],
        dependency_mode="all_of",
        claim_type="conclusion",
    )
    lineage.record_claims(tmp_path, [first, second, conclusion])

    assert lineage.validate_lineage(tmp_path)["valid"] is True

    first["dependency"] = {
        "mode": "all_of",
        "claim_ids": ["cl-x"],
        "derivation_type": "reasoning",
        "explanation": "Invalid circular dependency.",
        "calculation_evidence_id": "",
    }
    payload = {"schema_version": "1.0", "claims": [first, second, conclusion]}
    (tmp_path / "advisory_claim_register.json").write_text(json.dumps(payload))

    audit = lineage.validate_lineage(tmp_path)
    assert audit["valid"] is False
    assert any("claim dependency cycle" in error for error in audit["errors"])


def test_artifact_identity_change_is_detected(tmp_path: Path) -> None:
    lineage = _lineage()
    lineage.initialize_lineage(tmp_path)
    snapshot = tmp_path / "source_materials" / "inventory.html"
    snapshot.parent.mkdir()
    snapshot.write_text("13 listings", encoding="utf-8")
    artifact = {
        "path": "source_materials/inventory.html",
        "path_reference": "case_relative",
        "sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        "byte_count": snapshot.stat().st_size,
        "media_type": "text/html",
    }
    lineage.record_evidence(
        tmp_path,
        [_receipt("ev-web-13", observation="13 listings", artifact_refs=[artifact])],
    )
    snapshot.write_text("12 listings", encoding="utf-8")

    audit = lineage.validate_lineage(tmp_path)
    assert audit["valid"] is False
    assert any("sha256 does not match" in error for error in audit["errors"])


def test_quotation_requires_a_captured_transcript_receipt(tmp_path: Path) -> None:
    lineage = _lineage()
    lineage.initialize_lineage(tmp_path)
    assertion = _receipt(
        "ev-speaker-assertion",
        observation="Giovanni believes demand will grow.",
        evidence_type="management_assertion",
        capture_status="assertion_only",
    )
    assertion["source"]["url"] = ""
    lineage.record_evidence(tmp_path, [assertion])
    quote = _claim(
        "cl-quote",
        'Giovanni said, "Demand will grow."',
        evidence_ids=["ev-speaker-assertion"],
        claim_type="quotation",
    )
    quote["dependency"]["derivation_type"] = "quotation"

    with pytest.raises(lineage.LineageError, match="interview_transcript"):
        lineage.record_claims(tmp_path, [quote])

    assert (
        json.loads(
            (tmp_path / "advisory_claim_register.json").read_text(encoding="utf-8")
        )["claims"]
        == []
    )


def test_claim_appearance_is_bound_to_exact_output_bytes(tmp_path: Path) -> None:
    lineage = _lineage()
    lineage.initialize_lineage(tmp_path)
    lineage.record_evidence(
        tmp_path,
        [_receipt("ev-a", observation="Premise A")],
    )
    lineage.record_claims(
        tmp_path,
        [_claim("cl-a", "Premise A", evidence_ids=["ev-a"])],
    )
    deliverable = tmp_path / "memo.md"
    deliverable.write_text("# Recommendation\n\nPremise A\n", encoding="utf-8")
    lineage.bind_claim_appearances(
        tmp_path,
        deliverable,
        [
            {
                "claim_id": "cl-a",
                "locator": "Recommendation",
            }
        ],
        recorded_at=RECORDED_AT,
    )
    deliverable.write_text("# Recommendation\n\nChanged premise\n", encoding="utf-8")

    audit = lineage.validate_lineage(tmp_path)

    assert audit["valid"] is False
    assert any(
        "appearances[0]" in error and "sha256" in error for error in audit["errors"]
    )


def test_case_exchange_deduplicates_output_and_propagates_supersession(
    tmp_path: Path,
) -> None:
    core = _load(CORE_PATH, "clara_advisor_case_core_exchange_lineage_test")
    lineage = _lineage()
    source_case = tmp_path / "source"
    target_case = tmp_path / "target"
    datetime_module = __import__("datetime")
    for case_dir in (source_case, target_case):
        core.initialize_case(
            case_dir,
            client="ClientCo",
            project="CDD",
            objective="Assess inventory",
            audience="Investment committee",
            now=datetime_module.datetime(
                2026, 8, 18, 8, tzinfo=datetime_module.timezone.utc
            ),
        )
    lineage.record_evidence(
        source_case,
        [_receipt("ev-a", observation="Premise A")],
    )
    lineage.record_claims(
        source_case,
        [
            _claim("cl-a", "Premise A", evidence_ids=["ev-a"]),
            _claim("cl-b", "Premise B", evidence_ids=["ev-a"]),
        ],
    )
    memo = source_case / "memo.md"
    memo.write_text("# Memo\n\nPremise A. Premise B.\n", encoding="utf-8")
    lineage.bind_claim_appearances(
        source_case,
        memo,
        [
            {"claim_id": "cl-a", "locator": "Premise A"},
            {"claim_id": "cl-b", "locator": "Premise B"},
        ],
        recorded_at=RECORDED_AT,
    )

    first_export = core.export_case_update(source_case)
    with __import__("zipfile").ZipFile(first_export.package_path) as archive:
        update = json.loads(archive.read("case_update.json"))
        lineage_members = [
            name for name in archive.namelist() if name.startswith("lineage_files/")
        ]
    first_import = core.import_case_update(target_case, first_export.package_path)

    assert first_export.included_file_count == 1
    assert len(update["included_lineage_files"]) == 2
    assert len({item["archive_path"] for item in update["included_lineage_files"]}) == 1
    assert len(lineage_members) == 1
    assert first_import.imported_claim_count == 2
    imported_claims = json.loads(
        (target_case / "advisory_claim_register.json").read_text(encoding="utf-8")
    )["claims"]
    assert len({item["appearances"][0]["artifact"] for item in imported_claims}) == 1

    successor = _claim("cl-a2", "Premise A, revised.", evidence_ids=["ev-a"])
    successor["recorded_at"] = "2026-08-18T09:00:00+00:00"
    successor["supersedes_claim_id"] = "cl-a"
    lineage.record_claims(source_case, [successor])
    revised_memo = source_case / "memo-revised.md"
    revised_memo.write_text("# Memo\n\nPremise B remains in use.\n", encoding="utf-8")
    lineage.bind_claim_appearances(
        source_case,
        revised_memo,
        [{"claim_id": "cl-b", "locator": "Premise B"}],
        recorded_at="2026-08-18T09:30:00+00:00",
    )
    second_export = core.export_case_update(
        source_case,
        now=datetime_module.datetime(
            2026, 8, 18, 10, tzinfo=datetime_module.timezone.utc
        ),
    )
    second_import = core.import_case_update(target_case, second_export.package_path)
    target_claims = json.loads(
        (target_case / "advisory_claim_register.json").read_text(encoding="utf-8")
    )["claims"]
    target_by_id = {item["id"]: item for item in target_claims}

    assert second_import.updated_claim_count == 2
    assert second_import.imported_claim_count == 1
    assert target_by_id["cl-a"]["state"] == "superseded"
    assert target_by_id["cl-a2"]["supersedes_claim_id"] == "cl-a"
    assert len(target_by_id["cl-b"]["appearances"]) == 2
    assert lineage.validate_lineage(target_case)["valid"] is True


def test_reporting_contribution_binds_exact_calculation_artifacts(
    tmp_path: Path,
) -> None:
    core = _load(CORE_PATH, "clara_advisor_case_core_reporting_test")
    reporting = _load(
        REPORTING_CONTRIBUTION_PATH,
        "clara_record_reporting_contribution_test",
    )
    case_dir = tmp_path / "case"
    core.initialize_case(
        case_dir,
        client="ClientCo",
        project="CDD",
        objective="Assess revenue",
        audience="Investment committee",
        now=__import__("datetime").datetime(
            2026, 8, 18, 8, tzinfo=__import__("datetime").timezone.utc
        ),
    )
    run_dir = tmp_path / "reporting-run"
    run_dir.mkdir()
    input_path = tmp_path / "revenue.csv"
    output_path = run_dir / "calculated_revenue.csv"
    recipe_path = run_dir / "used_recipe.json"
    input_path.write_text("month,revenue\nJan,120\n", encoding="utf-8")
    output_path.write_text("metric,value\nrevenue,120\n", encoding="utf-8")
    recipe_path.write_text('{"aggregation":"sum"}\n', encoding="utf-8")

    def artifact_record(path: Path, *, relative: bool = False) -> dict[str, Any]:
        return {
            "path": path.name if relative else str(path.resolve()),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size_bytes": path.stat().st_size,
        }

    output_records = [artifact_record(output_path, relative=True)]
    manifest = {
        "schema_version": "0.2",
        "capability_id": "statement_analysis.table",
        "owner": "clara.reporting-engine",
        "output_dir": str(run_dir.resolve()),
        "runner": {"returncode": 0, "status": "ok"},
        "render_proof": {"status": "not_required_data_only"},
        "evidence": {
            "input": artifact_record(input_path),
            "recipe": artifact_record(recipe_path),
            "outputs": output_records,
            "output_set_sha256": reporting._canonical_json_sha256(output_records),
        },
    }
    manifest_path = run_dir / "render_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    contribution = {
        "evidence": {
            "id": "ev-revenue-calculation",
            "recorded_at": RECORDED_AT,
            "recorded_by": "clara:reporting-engine",
            "material_ids": [],
            "observation": "The prepared dataset sums to revenue of 120.",
            "scope": "The supplied January rows and declared sum recipe.",
            "limitations": ["The calculation does not establish dataset completeness."],
            "method": "Sum the reviewed revenue field over the declared period.",
            "verification_notes": ["Reporting Engine render proof completed."],
        },
        "claim": _claim(
            "cl-revenue-120",
            "Revenue in the supplied January data is 120.",
            evidence_ids=["ev-revenue-calculation"],
            claim_type="calculation",
        ),
        "judgement_entries": [],
    }
    contribution["claim"]["dependency"] = {
        "mode": "none",
        "claim_ids": [],
        "derivation_type": "calculation",
        "explanation": "The value is produced by the declared sum recipe.",
        "calculation_evidence_id": "ev-revenue-calculation",
    }

    result = reporting.record_reporting_contribution(
        case_dir,
        manifest_path,
        contribution,
    )

    assert result["calculation_evidence_id"] == "ev-revenue-calculation"
    evidence = json.loads(
        (case_dir / "advisory_evidence_register.json").read_text(encoding="utf-8")
    )["evidence"][0]
    assert evidence["calculation"]["input_artifact_paths"] == [
        str(input_path.resolve())
    ]
    assert (
        str(output_path.resolve()) in evidence["calculation"]["output_artifact_paths"]
    )
    assert (
        str(manifest_path.resolve())
        in evidence["calculation"]["verification_artifact_paths"]
    )
    assert _lineage().validate_lineage(case_dir)["valid"] is True

    target_case = tmp_path / "target-case"
    core.initialize_case(
        target_case,
        client="ClientCo",
        project="CDD",
        objective="Assess revenue",
        audience="Investment committee",
        now=__import__("datetime").datetime(
            2026, 8, 18, 9, tzinfo=__import__("datetime").timezone.utc
        ),
    )
    exported = core.export_case_update(case_dir)
    first_import = core.import_case_update(target_case, exported.package_path)
    repeated_import = core.import_case_update(target_case, exported.package_path)

    assert first_import.imported_evidence_count == 1
    assert first_import.imported_claim_count == 1
    assert repeated_import.imported_evidence_count == 0
    assert repeated_import.imported_claim_count == 0
    assert repeated_import.skipped_count == 2
    assert _lineage().validate_lineage(target_case)["valid"] is True


def test_reporting_contribution_rejects_tampered_input_without_partial_write(
    tmp_path: Path,
) -> None:
    core = _load(CORE_PATH, "clara_advisor_case_core_reporting_tamper_test")
    reporting = _load(
        REPORTING_CONTRIBUTION_PATH,
        "clara_record_reporting_contribution_tamper_test",
    )
    case_dir = tmp_path / "case"
    core.initialize_case(
        case_dir,
        client="ClientCo",
        project="CDD",
        objective="Assess revenue",
        audience="Investment committee",
        now=__import__("datetime").datetime(
            2026, 8, 18, 8, tzinfo=__import__("datetime").timezone.utc
        ),
    )
    input_path = tmp_path / "input.csv"
    output_path = tmp_path / "output.csv"
    input_path.write_text("value\n1\n", encoding="utf-8")
    output_path.write_text("total\n1\n", encoding="utf-8")
    output_record = {
        "path": str(output_path.resolve()),
        "sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "size_bytes": output_path.stat().st_size,
    }
    manifest = {
        "schema_version": "0.2",
        "capability_id": "period_comparison.table",
        "owner": "clara.reporting-engine",
        "output_dir": str(tmp_path.resolve()),
        "runner": {"returncode": 0},
        "render_proof": {"status": "not_required_data_only"},
        "evidence": {
            "input": {
                "path": str(input_path.resolve()),
                "sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
                "size_bytes": input_path.stat().st_size,
            },
            "recipe": {"kind": "none"},
            "outputs": [output_record],
            "output_set_sha256": reporting._canonical_json_sha256([output_record]),
        },
    }
    manifest_path = tmp_path / "render_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    input_path.write_text("value\n2\n", encoding="utf-8")

    with pytest.raises(reporting.ReportingContributionError, match="do not match"):
        reporting.record_reporting_contribution(
            case_dir,
            manifest_path,
            {"evidence": {}, "claim": {}},
        )

    assert (
        json.loads(
            (case_dir / "advisory_evidence_register.json").read_text(encoding="utf-8")
        )["evidence"]
        == []
    )
    assert (
        json.loads(
            (case_dir / "advisory_claim_register.json").read_text(encoding="utf-8")
        )["claims"]
        == []
    )


def test_case_workspace_blocks_deleting_material_cited_by_evidence(
    tmp_path: Path,
) -> None:
    core = _load(CORE_PATH, "clara_advisor_case_core_lineage_test")
    case_dir = tmp_path / "case"
    core.initialize_case(
        case_dir,
        client="ClientCo",
        project="CDD",
        objective="Assess inventory",
        audience="Investment committee",
        now=__import__("datetime").datetime(
            2026, 8, 18, 8, tzinfo=__import__("datetime").timezone.utc
        ),
    )
    source = tmp_path / "management-note.txt"
    source.write_text("300 vehicles", encoding="utf-8")
    material = core.register_material(
        case_dir, source, summary="Management stock claim"
    )
    receipt = _receipt(
        "ev-management-300",
        observation="Management stated 300 vehicles.",
        evidence_type="management_assertion",
        capture_status="assertion_only",
    )
    receipt["source"]["url"] = ""
    receipt["source"]["material_ids"] = [material["id"]]
    lineage = _lineage()
    lineage.record_evidence(case_dir, [receipt])

    with pytest.raises(core.CaseWorkspaceError, match="cited by ev-management-300"):
        core.delete_materials(case_dir, [material["id"]])


class _Headers:
    def get_content_type(self) -> str:
        return "text/html"

    def get_content_charset(self) -> str:
        return "utf-8"


class _Response:
    status = 200
    headers = _Headers()

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return b"<html><body><p>13 vehicle listings</p><script>ignore</script></body></html>"

    def geturl(self) -> str:
        return "https://example.test/inventory"


class _Opener:
    def __init__(self) -> None:
        self.called = False

    def open(self, _request: Any, *, timeout: float) -> _Response:
        assert timeout == 3.0
        self.called = True
        return _Response()


def test_web_capture_preserves_response_and_explicit_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = _load(WEB_CAPTURE_PATH, "clara_advisory_web_capture_test")
    lineage = _lineage()
    lineage.initialize_lineage(tmp_path)
    monkeypatch.setattr(
        capture.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    opener = _Opener()

    receipt = capture.capture_web_evidence(
        tmp_path,
        url="https://example.test/inventory",
        evidence_id="ev-web-13",
        observation="Thirteen vehicle listings were visible.",
        scope="The captured public page at the capture time.",
        limitations=["This does not establish total company stock."],
        recorded_at=__import__("datetime").datetime(
            2026, 8, 18, 8, tzinfo=__import__("datetime").timezone.utc
        ),
        timeout=3.0,
        opener=opener,
    )

    normalized = tmp_path / "source_materials/web/ev-web-13/normalized.txt"
    assert opener.called is True
    assert normalized.read_text().strip() == "13 vehicle listings"
    assert receipt["observation"] == "Thirteen vehicle listings were visible."
    assert receipt["limitations"] == ["This does not establish total company stock."]
    assert receipt["verification"]["status"] == "identity_verified"
    assert lineage.validate_lineage(tmp_path)["valid"] is True


def test_web_capture_removes_artifacts_when_lineage_commit_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = _load(WEB_CAPTURE_PATH, "clara_advisory_web_capture_rollback_test")
    _lineage().initialize_lineage(tmp_path)
    monkeypatch.setattr(
        capture.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )

    def fail_commit(*_args: Any, **_kwargs: Any) -> None:
        raise capture.LineageError("synthetic commit failure")

    monkeypatch.setattr(capture, "record_evidence", fail_commit)

    with pytest.raises(capture.LineageError, match="synthetic commit failure"):
        capture.capture_web_evidence(
            tmp_path,
            url="https://example.test/inventory",
            evidence_id="ev-web-failed",
            observation="Thirteen vehicle listings were visible.",
            scope="The captured public page at the capture time.",
            recorded_at=__import__("datetime").datetime(
                2026, 8, 18, 8, tzinfo=__import__("datetime").timezone.utc
            ),
            timeout=3.0,
            opener=_Opener(),
        )

    assert not (tmp_path / "source_materials/web/ev-web-failed").exists()


def test_web_capture_rejects_loopback_before_opening(tmp_path: Path) -> None:
    capture = _load(WEB_CAPTURE_PATH, "clara_advisory_web_capture_unsafe_test")
    lineage = _lineage()
    lineage.initialize_lineage(tmp_path)
    opener = _Opener()

    with pytest.raises(capture.UnsafePublicUrlError, match="non-public"):
        capture.capture_web_evidence(
            tmp_path,
            url="http://127.0.0.1/private",
            evidence_id="ev-unsafe",
            observation="Private response.",
            scope="Attempted response.",
            opener=opener,
        )

    assert opener.called is False
