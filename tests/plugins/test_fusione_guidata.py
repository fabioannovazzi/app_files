from __future__ import annotations

import importlib
import json
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def api(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/fusione-guidata/scripts"))
    return importlib.import_module("fusione_case")


@pytest.fixture
def case(api, tmp_path):
    root = tmp_path.resolve()
    source = root / "sources"
    source.mkdir()
    (source / "document.txt").write_text("Synthetic source evidence", encoding="utf-8")
    store = api.CaseStore.create(
        root / "case",
        "admin",
        {
            "operation_type": "fusione",
            "objectives": "Synthetic test",
            "jurisdictions": ["IT"],
            "planned_date": "2026-12-01",
            "actual_date": None,
        },
    )
    store.put(
        "alpha",
        "Entity",
        {
            "name": "Synthetic Alpha",
            "legal_form": "synthetic",
            "role": "participant",
            "residence": "IT",
            "accounting_framework": "unreviewed",
            "source_roots": [str(source)],
        },
        scope=["alpha"],
        dependencies=[],
        expected_version=0,
    )
    store.put(
        "beta",
        "Entity",
        {
            "name": "Synthetic Beta",
            "legal_form": "synthetic",
            "role": "participant",
            "residence": "IT",
            "accounting_framework": "unreviewed",
            "source_roots": [str(source)],
        },
        scope=["beta"],
        dependencies=[],
        expected_version=0,
    )
    store.import_evidence(
        "proof",
        "alpha",
        source / "document.txt",
        locator="line 1",
        description="Synthetic evidence",
    )
    return store


def fact_data(**changes):
    return {
        "description": "Synthetic liability",
        "fact_status": "known",
        "value_kind": "decimal",
        "value": "100.00",
        "unit": "EUR",
        "as_of": "2026-09-29",
        **changes,
    }


def add_fact(api, case, object_id="fact", **changes):
    return case.put(
        object_id,
        "Fact",
        fact_data(**changes),
        scope=["alpha"],
        dependencies=[api.reference(case.read("proof"))],
        expected_version=0,
    )


def draft(api, case, object_id, dependencies, scope=None):
    drafts = case.root / "drafts"
    drafts.mkdir(exist_ok=True)
    path = drafts / f"{object_id}.md"
    path.write_text("Synthetic draft version 1", encoding="utf-8")
    return case.artifact(
        object_id,
        path,
        scope=scope or ["alpha"],
        dependencies=dependencies,
        recipient="Reviewer",
    )


def approve(api, case, record, object_id="approval"):
    return case.approve(
        object_id,
        api.reference(record),
        professional_role="Synthetic professional",
        scope_text="Fixture only",
        confirmation="Explicit synthetic test confirmation",
    )


def rule_fixture(api, case, *, review_status="professional_review_pending"):
    source = case.put(
        "source",
        "SourceVersion",
        {
            "title": "Synthetic source",
            "url": "https://example.invalid/source",
            "checked_on": "2026-09-29",
            "access_status": "retrieved",
            "error": None,
            "source_version": "v1",
        },
        scope=["alpha"],
        dependencies=[api.reference(case.read("proof"))],
        expected_version=0,
    )
    return case.put(
        "rule",
        "RuleVersion",
        {
            "statement": "Synthetic rule",
            "citation": "Synthetic section 1",
            "review_status": review_status,
            "published_on": "2026-01-01",
            "effective_from": "2026-01-01",
            "effective_to": None,
            "applicable_from": "2026-01-01",
            "applicable_to": None,
            "transitional_notes": "None for this fixture",
            "scope": "Synthetic test",
            "preconditions": ["Synthetic input"],
            "exceptions": [],
            "test_refs": ["unit-test"],
        },
        scope=["alpha"],
        dependencies=[api.reference(source)],
        expected_version=0,
    )


def test_change_reopens_transitive_dependents_preserving_approved_bytes(api, case):
    fact = add_fact(api, case)
    artifact = draft(api, case, "draft", [api.reference(fact)])
    decision = approve(api, case, artifact)
    draft(api, case, "downstream", [api.reference(artifact)])
    independent = add_fact(api, case, "independent")

    case.put(
        "fact",
        "Fact",
        fact_data(value="150.00"),
        scope=["alpha"],
        dependencies=[api.reference(case.read("proof"))],
        expected_version=1,
    )

    assert case.status("draft")["review_state"] == "needs_review"
    assert case.status("downstream")["issues"] == ["stale_version:fact"]
    assert case.status("independent")["issues"] == []
    assert case.read("independent") == independent
    assert case.read("approval") == decision
    assert case.read("fact", 1)["data"]["value"] == "100.00"
    assert case.document_bytes("draft") == b"Synthetic draft version 1"
    impacts = [
        item["record"]["data"]
        for item in case.report()["records"]
        if item["record"]["kind"] == "ChangeImpact"
    ]
    assert {ref["id"] for ref in impacts[0]["affected"]} == {
        "draft",
        "downstream",
        "approval",
    }


@pytest.mark.parametrize("state", ["unknown", "disputed"])
def test_unresolved_fact_blocks_approval_without_becoming_false(api, case, state):
    fact = add_fact(api, case, fact_status=state, value_kind="boolean", value=None)
    artifact = draft(api, case, "draft", [api.reference(fact)])

    with pytest.raises(api.CaseError, match=state):
        approve(api, case, artifact)

    assert case.read("fact")["data"]["value"] is None


@pytest.mark.parametrize("value", [False, 0, "0.00"])
def test_unknown_fact_rejects_implicit_default_values(api, case, value):
    with pytest.raises(api.CaseError, match="null value"):
        add_fact(api, case, fact_status="unknown", value=value)


@pytest.mark.parametrize(
    "value", [0.1, 1, True, "NaN", "Infinity", "1,00", "1e6", None]
)
def test_money_requires_exact_decimal_strings(api, case, value):
    with pytest.raises(api.CaseError):
        add_fact(api, case, value=value)


@pytest.mark.parametrize(
    "kind,value",
    [
        ("fraction", "2/5"),
        ("date", "2026-09-29"),
        ("boolean", False),
        ("text", "Documented fact"),
    ],
)
def test_supported_fact_types_are_preserved(api, case, kind, value):
    record = add_fact(api, case, value_kind=kind, value=value)

    assert record["data"]["value"] == value
    assert case.status("fact")["issues"] == []


@pytest.mark.parametrize(
    "kind,value",
    [
        ("fraction", "2/0"),
        ("fraction", "0.4"),
        ("date", "2026-02-30"),
        ("date", "20260929"),
        ("boolean", "false"),
        ("text", " "),
        ("number", 2),
    ],
)
def test_invalid_fact_types_are_rejected(api, case, kind, value):
    with pytest.raises(api.CaseError):
        add_fact(api, case, value_kind=kind, value=value)


def test_cross_case_reference_cannot_reuse_matching_ids(api, case, tmp_path):
    other = api.CaseStore.create(
        tmp_path.resolve() / "other", "admin", case.read("operation")["data"]
    )
    foreign = api.reference(other.read("operation"))

    with pytest.raises(api.CaseError, match="Cross-case"):
        case.put(
            "fact",
            "Fact",
            fact_data(),
            scope=["alpha"],
            dependencies=[foreign],
            expected_version=0,
        )


def test_company_grant_does_not_allow_foreign_evidence_or_aggregate_leak(api, case):
    secret = case.import_evidence(
        "beta_proof",
        "beta",
        Path(case.read("beta")["data"]["source_roots"][0]) / "document.txt",
        locator="line 1",
        description="Beta evidence",
    )
    combined = draft(
        api, case, "combined", [api.reference(secret)], scope=["alpha", "beta"]
    )
    case.grant("limited", role="editor", entities=["alpha"])
    limited = api.CaseStore(case.root, "limited")

    with pytest.raises(api.CaseError, match="access"):
        limited.put(
            "fact",
            "Fact",
            fact_data(),
            scope=["alpha"],
            dependencies=[api.reference(secret)],
            expected_version=0,
        )

    assert combined["id"] not in {
        item["record"]["id"] for item in limited.report()["records"]
    }


def test_record_scope_cannot_drop_company_from_dependency(api, case):
    with pytest.raises(api.CaseError, match="retain every"):
        case.put(
            "fact",
            "Fact",
            fact_data(),
            scope=[],
            dependencies=[api.reference(case.read("proof"))],
            expected_version=0,
        )


def test_actor_without_grant_cannot_open_case(api, case):
    with pytest.raises(api.CaseError, match="no access"):
        api.CaseStore(case.root, "unknown_actor")


def test_reader_cannot_write_and_editor_cannot_approve(api, case):
    fact = add_fact(api, case)
    case.grant("reader", role="reader", entities=["alpha"])
    case.grant("editor", role="editor", entities=["alpha"])
    reader = api.CaseStore(case.root, "reader")
    editor = api.CaseStore(case.root, "editor")

    with pytest.raises(api.CaseError, match="read access"):
        reader.put(
            "another",
            "Fact",
            fact_data(),
            scope=["alpha"],
            dependencies=[api.reference(case.read("proof"))],
            expected_version=0,
        )
    with pytest.raises(api.CaseError, match="editor"):
        approve(api, editor, fact)


def test_editor_cannot_change_company_roots_or_grants(api, case):
    case.grant("editor", role="editor", entities=["alpha"])
    editor = api.CaseStore(case.root, "editor")

    with pytest.raises(api.CaseError, match="administrator"):
        editor.put(
            "alpha",
            "Entity",
            case.read("alpha")["data"],
            scope=["alpha"],
            dependencies=[],
            expected_version=1,
        )
    with pytest.raises(api.CaseError, match="administrator"):
        editor.grant("new", role="reader", entities=["alpha"])


def test_candidate_rule_never_becomes_approved_by_validation(api, case):
    rule = rule_fixture(api, case, review_status="candidate")

    with pytest.raises(api.CaseError, match="pending professional review"):
        approve(api, case, rule)

    assert case.status("rule")["review_state"] == "unapproved"


def test_rule_approval_is_exact_scoped_and_allows_dependent_review(api, case):
    rule = rule_fixture(api, case)
    artifact = draft(api, case, "draft", [api.reference(rule)])
    assert case.status("draft")["issues"] == ["rule_unapproved:rule"]

    decision = approve(api, case, rule)

    assert case.status("rule")["review_state"] == "approved_for_defined_scope"
    assert case.status("draft")["issues"] == []
    assert decision["data"]["approved_content"] == rule["data"]
    assert decision["data"]["professional_role"] == "Synthetic professional"
    assert decision["data"]["scope_text"] == "Fixture only"
    assert case.read("rule")["data"]["review_status"] == "professional_review_pending"


def test_failed_source_check_preserves_last_success_and_invalidates_rule(api, case):
    rule = rule_fixture(api, case)
    approve(api, case, rule)
    previous = case.read("source")

    case.put(
        "source",
        "SourceVersion",
        {
            **previous["data"],
            "access_status": "failed",
            "error": "HTTP 503",
            "source_version": "attempt-2",
        },
        scope=["alpha"],
        dependencies=[],
        expected_version=1,
    )

    assert case.status("source")["issues"] == ["source_failed:source"]
    assert case.status("rule")["review_state"] == "needs_review"
    assert case.read("source", 1) == previous


@pytest.mark.parametrize(
    "field,value",
    [
        ("review_status", "approved_for_defined_scope"),
        ("effective_to", "2025-12-31"),
        ("applicable_to", "2025-12-31"),
        ("exceptions", "none"),
        ("published_on", "not a date"),
    ],
)
def test_rule_rejects_fabricated_approval_and_invalid_intervals(
    api, case, field, value
):
    rule = rule_fixture(api, case)

    with pytest.raises(api.CaseError):
        case.put(
            "rule",
            "RuleVersion",
            {**rule["data"], field: value},
            scope=["alpha"],
            dependencies=rule["dependencies"],
            expected_version=1,
        )


def test_stale_approval_and_stale_write_are_rejected(api, case):
    original = add_fact(api, case)
    case.put(
        "fact",
        "Fact",
        fact_data(value="200.00"),
        scope=["alpha"],
        dependencies=original["dependencies"],
        expected_version=1,
    )

    with pytest.raises(api.CaseError, match="stale_version"):
        approve(api, case, original)
    with pytest.raises(api.CaseError, match="Stale write"):
        case.put(
            "fact",
            "Fact",
            fact_data(value="300.00"),
            scope=["alpha"],
            dependencies=original["dependencies"],
            expected_version=1,
        )


def test_cycles_and_changed_reference_hashes_are_rejected(api, case):
    fact = add_fact(api, case)
    artifact = draft(api, case, "draft", [api.reference(fact)])

    with pytest.raises(api.CaseError, match="cycles"):
        case.put(
            "fact",
            "Fact",
            fact_data(),
            scope=["alpha"],
            dependencies=[api.reference(artifact)],
            expected_version=1,
        )
    with pytest.raises(api.CaseError, match="fingerprint"):
        case.put(
            "bad",
            "Fact",
            fact_data(),
            scope=["alpha"],
            dependencies=[{**api.reference(case.read("proof")), "sha256": "0" * 64}],
            expected_version=0,
        )


@pytest.mark.parametrize("kind", ["Evidence", "Artifact", "Decision", "ChangeImpact"])
def test_internal_records_cannot_be_forged_through_generic_writer(api, case, kind):
    with pytest.raises(api.CaseError, match="import, artifact or approval"):
        case.put("forged", kind, {}, scope=[], dependencies=[], expected_version=0)


def test_import_requires_selected_root_and_rejects_symlinks(api, case, tmp_path):
    outside = tmp_path.resolve() / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = Path(case.read("alpha")["data"]["source_roots"][0]) / "link.txt"
    link.symlink_to(outside)

    with pytest.raises(api.CaseError, match="outside"):
        case.import_evidence(
            "outside", "alpha", outside, locator="all", description="outside"
        )
    with pytest.raises(api.CaseError, match="symbolic"):
        case.import_evidence("link", "alpha", link, locator="all", description="link")


def test_document_snapshot_survives_original_file_changes(api, case):
    original = Path(case.read("proof")["data"]["source_path"])

    original.write_text("changed after import", encoding="utf-8")

    assert case.document_bytes("proof") == b"Synthetic source evidence"


def test_blob_corruption_blocks_approval_and_read(api, case):
    fact = add_fact(api, case)
    with sqlite3.connect(case.path) as db:
        db.execute("UPDATE blobs SET content=?", (b"corrupt",))

    with pytest.raises(api.CaseError, match="blob_integrity"):
        approve(api, case, fact)
    with pytest.raises(api.CaseError, match="integrity"):
        case.document_bytes("proof")


def test_storage_rejects_mutation_of_approval_history(api, case):
    fact = add_fact(api, case)
    approve(api, case, fact)

    with (
        sqlite3.connect(case.path) as db,
        pytest.raises(sqlite3.IntegrityError, match="immutable"),
    ):
        db.execute("DELETE FROM records WHERE id='approval'")


def test_reopen_case_preserves_state_and_permissions(api, case):
    fact = add_fact(api, case)

    reopened = api.CaseStore(case.root, "admin")

    assert reopened.read("fact") == fact
    assert reopened.document_bytes("proof") == b"Synthetic source evidence"


def test_unsupported_branch_cannot_be_recorded_as_implemented(api, case):
    with pytest.raises(api.CaseError, match="unsupported"):
        case.put(
            "mlbo",
            "BranchDecision",
            {
                "branch": "MLBO",
                "rationale": "User request",
                "conditions": "Unreviewed",
                "support_status": "implemented",
            },
            scope=[],
            dependencies=[],
            expected_version=0,
        )


def test_demo_persists_before_after_and_negative_control_results(api, tmp_path):
    module = importlib.import_module("fusione_demo")

    result = module.run_demo(tmp_path.resolve() / "demo")

    assert result["passed"] is True
    assert result["failed"] == []
    assert result["checks"]["company_access_denied"] is True
    assert Path(result["before"]["case_report"]).is_file()
    assert Path(result["after"]["model_data_report"]).is_file()


def test_real_case_report_does_not_invent_host_exposure(api, case, tmp_path):
    module = importlib.import_module("fusione_report")

    paths = module.export_report(
        case, tmp_path.resolve() / "report", runtime_profile="anthropic-cowork"
    )

    report = json.loads(
        Path(paths["model_data_report"]).with_suffix(".json").read_text()
    )
    assert report["phases"][0]["outcome"] == "not_measurable"
    assert report["phases"][0]["model_visible"] == []
    assert paths["server_receipt"] == "not_requested"


def test_cli_apply_and_show_use_durable_case(api, case, tmp_path, capsys):
    cli = importlib.import_module("run_fusione")
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "action": "put",
                "object_id": "fact",
                "kind": "Fact",
                "data": fact_data(),
                "scope": ["alpha"],
                "dependencies": [api.reference(case.read("proof"))],
                "expected_version": 0,
            }
        )
    )

    status = cli.main(
        [
            "apply",
            "--case",
            str(case.root),
            "--actor",
            "admin",
            "--request",
            str(request),
        ]
    )

    assert status == 0
    assert json.loads(capsys.readouterr().out)["id"] == "fact"
    assert api.CaseStore(case.root, "admin").read("fact")["data"]["value"] == "100.00"


def test_company_source_roots_cannot_change_meaning_with_working_directory(api, case):
    entity = case.read("alpha")

    with pytest.raises(api.CaseError, match="absolute paths"):
        case.put(
            "alpha",
            "Entity",
            {**entity["data"], "source_roots": ["relative-folder"]},
            scope=["alpha"],
            dependencies=[],
            expected_version=1,
        )
