"""Synthetic evidence for LIPE catalog precedence, history and review boundaries."""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[2] / "plugins/lipe"
sys.path.insert(0, str(PLUGIN / "scripts"))
from lipe_catalog import (
    create_catalog,
    dispute,
    history,
    lookup,
    main,
    record,
    resolve_dispute,
    revoke,
)
from lipe_core import ContractError, calculate, read_json


def entry(root: Path, identity: str = "test-entry", scope: str = "STUDIO") -> dict:
    """Write a wholly fictional vendor-code legend, not a reusable real tax rule."""
    source = root / "synthetic-legend.txt"
    source.write_text(
        "SYNTHETIC TEST ONLY. V22 is a fictional taxable sales code. V10 and V23 are additional fictional aliases. No real software or tax opinion.",
        encoding="utf-8",
    )
    review = {
        "status": "CONFIRMED",
        "reviewer": "SYNTHETIC TEST ACTOR",
        "reviewed_on": "2026-10-02",
        "reason": "Fictional automated fixture only; no real professional confirmation.",
    }
    return {
        "schema_version": "lipe.catalog.entry.v1",
        "entry_id": identity,
        "scope": scope,
        "client_id": "client-a" if scope == "CLIENT" else None,
        "software": {"name": "SYNTHETIC", "version": "1"},
        "side": "SALES",
        "code": "V22",
        "description": "Fictional taxable sales alias",
        "tax_class": {
            "treatment": "SALE_TAXABLE",
            "vat_rate": "22.00",
            "vat_nature": None,
            "deductibility": {"mode": "CASE_SPECIFIC", "percent": None},
            "mechanism": "ordinary fictional example",
            "counterparty_regime": None,
            "legal_basis": None,
        },
        "confidence": {
            "value": "0.90",
            "basis": "Declared confidence for a synthetic test only.",
        },
        "valid_from": "2026-01-01",
        "valid_until": None,
        "sources": [
            {
                "source_id": "legend",
                "path": source.name,
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "visibility": (
                    "PUBLIC"
                    if scope == "CENTRAL"
                    else "PRIVATE_CASE" if scope == "CLIENT" else "STUDIO_REFERENCE"
                ),
            }
        ],
        "evidence": [
            {
                "source_id": "legend",
                "page": 1,
                "quote": source.read_text(encoding="utf-8"),
            }
        ],
        "review": review,
        "curator_review": copy.deepcopy(review) if scope == "CENTRAL" else None,
        "disclosure_review": copy.deepcopy(review) if scope == "CENTRAL" else None,
    }


def setup(root: Path) -> Path:
    path = root / "catalog.sqlite3"
    create_catalog(path, "studio-a", "0.80")
    return path


def add(path: Path, value: dict, **kwargs: object) -> dict:
    return record(
        path, value, path.parent, expected_head=history(path)["head_hash"], **kwargs
    )


def find(path: Path, **kwargs: object) -> dict:
    request = {
        "studio_id": "studio-a",
        "client_id": "client-a",
        "software": {"name": "SYNTHETIC", "version": "1"},
        "side": "SALES",
        "code": "V22",
        "on_date": "2026-04-30",
    }
    request.update(kwargs)
    return lookup(path, **request)


def test_client_override_precedes_studio_and_central_without_confirming_current_case(
    tmp_path: Path,
) -> None:
    path = setup(tmp_path)
    central = entry(tmp_path, "central", "CENTRAL")
    studio = entry(tmp_path, "studio")
    studio["tax_class"]["treatment"] = "SALE_NO_OUTPUT_VAT"
    client = entry(tmp_path, "client", "CLIENT")
    client["tax_class"]["treatment"] = "SALE_EXCLUDED"
    add(path, central)
    add(path, studio)
    add(path, client)
    result = find(path)
    assert result["scope"] == "CLIENT"
    assert result["candidate"]["treatment"] == "SALE_EXCLUDED"
    assert result["case_confirmation_required"] is True
    assert result["identity_authenticated"] is False


def test_another_client_receives_studio_meaning_not_foreign_client_override(
    tmp_path: Path,
) -> None:
    path = setup(tmp_path)
    add(path, entry(tmp_path, "client", "CLIENT"))
    studio = entry(tmp_path)
    studio["tax_class"]["treatment"] = "SALE_NO_OUTPUT_VAT"
    add(path, studio)
    result = find(path, client_id="client-b")
    assert result["scope"] == "STUDIO"
    assert result["candidate"]["treatment"] == "SALE_NO_OUTPUT_VAT"


@pytest.mark.parametrize("difference", ["vendor", "version", "side", "code", "date"])
def test_vendor_version_register_code_and_validity_are_exact_scope(
    tmp_path: Path, difference: str
) -> None:
    path = setup(tmp_path)
    add(path, entry(tmp_path))
    request = {
        "vendor": {"software": {"name": "OTHER", "version": "1"}},
        "version": {"software": {"name": "SYNTHETIC", "version": "2"}},
        "side": {"side": "PURCHASES"},
        "code": {"code": "V220"},
        "date": {"on_date": "2025-12-31"},
    }[difference]
    assert find(path, **request)["status"] == "UNKNOWN_CODE"


def test_foreign_studio_identity_is_rejected(tmp_path: Path) -> None:
    path = setup(tmp_path)
    with pytest.raises(ContractError, match="different declared studio"):
        find(path, studio_id="studio-b")


def test_compact_date_cannot_change_catalog_validity_comparison(tmp_path: Path) -> None:
    path = setup(tmp_path)
    add(path, entry(tmp_path))
    with pytest.raises(ContractError, match="YYYY-MM-DD"):
        find(path, on_date="20260430")


@pytest.mark.parametrize(
    "state,expected",
    [("low", "LOW_CONFIDENCE"), ("proposed", "UNCONFIRMED"), ("conflict", "CONFLICT")],
)
def test_uncertain_higher_priority_entry_never_falls_back_to_lower_catalog(
    tmp_path: Path, state: str, expected: str
) -> None:
    path = setup(tmp_path)
    add(path, entry(tmp_path, "central", "CENTRAL"))
    value = entry(tmp_path)
    if state == "low":
        value["confidence"]["value"] = "0.79"
    if state == "proposed":
        value["review"]["status"] = "PROPOSED"
    add(path, value)
    if state == "conflict":
        alternative = entry(tmp_path, "alternative")
        alternative["tax_class"]["treatment"] = "SALE_EXCLUDED"
        add(path, alternative)
    result = find(path)
    assert result["status"] == expected
    assert result["scope"] == "STUDIO"
    assert result["candidate"] is None


def test_same_class_keeps_all_evidence_instead_of_counting_agreement_as_promotion(
    tmp_path: Path,
) -> None:
    path = setup(tmp_path)
    add(path, entry(tmp_path, "one"))
    add(path, entry(tmp_path, "two"))
    add(path, entry(tmp_path, "three"))
    result = find(path)
    assert result["scope"] == "STUDIO"
    assert len(result["alternatives"]) == 3
    assert result["status"] == "CANDIDATE_FOR_CASE_REVIEW"


@pytest.mark.parametrize(
    "fallback,expected",
    [(False, "REVOKED_OVERRIDE"), (True, "CANDIDATE_FOR_CASE_REVIEW")],
)
def test_revocation_only_allows_lower_scope_when_explicitly_decided(
    tmp_path: Path, fallback: bool, expected: str
) -> None:
    path = setup(tmp_path)
    add(path, entry(tmp_path, "central", "CENTRAL"))
    value = entry(tmp_path)
    revision = add(path, value)
    revoke(
        path,
        value["entry_id"],
        value["review"],
        expected_head=history(path)["head_hash"],
        revision=revision["event_hash"],
        allow_fallback=fallback,
    )
    result = find(path)
    assert result["status"] == expected
    assert len(history(path)["events"]) == 3


def test_restore_appends_new_reviewed_revision_without_erasing_revocation(
    tmp_path: Path,
) -> None:
    path = setup(tmp_path)
    value = entry(tmp_path)
    original = add(path, value)
    removed = revoke(
        path,
        value["entry_id"],
        value["review"],
        expected_head=history(path)["head_hash"],
        revision=original["event_hash"],
    )
    restored = add(path, value, supersedes=removed["event_hash"])
    state = history(path)
    assert len(state["events"]) == 3
    assert state["events"][0] == original
    assert state["events"][1] == removed
    assert find(path)["alternatives"][0]["revision_hash"] == restored["event_hash"]


def test_stale_writer_cannot_overwrite_a_concurrent_revision(tmp_path: Path) -> None:
    path = setup(tmp_path)
    old_head = history(path)["head_hash"]
    first = add(path, entry(tmp_path))
    with pytest.raises(ContractError, match="Catalog changed"):
        record(path, entry(tmp_path, "second"), tmp_path, expected_head=old_head)
    assert history(path)["events"] == [first]


def test_revision_requires_exact_current_parent_and_preserves_identity(
    tmp_path: Path,
) -> None:
    path = setup(tmp_path)
    value = entry(tmp_path)
    first = add(path, value)
    value["code"] = "V23"
    with pytest.raises(ContractError, match="cannot change"):
        add(path, value, supersedes=first["event_hash"])
    assert len(history(path)["events"]) == 1


@pytest.mark.parametrize("violation", ["private", "curator", "disclosure"])
def test_central_record_requires_public_sources_and_explicit_curator_disclosure_review(
    tmp_path: Path, violation: str
) -> None:
    path = setup(tmp_path)
    value = entry(tmp_path, scope="CENTRAL")
    if violation == "private":
        value["sources"][0]["visibility"] = "PRIVATE_CASE"
    else:
        value[violation + "_review"] = None
    with pytest.raises(ContractError):
        add(path, value)
    assert history(path)["events"] == []


def test_changed_source_is_rejected_before_catalog_mutation(tmp_path: Path) -> None:
    path = setup(tmp_path)
    value = entry(tmp_path)
    (tmp_path / "synthetic-legend.txt").write_text(
        "Different evidence", encoding="utf-8"
    )
    with pytest.raises(ContractError, match="Source changed"):
        add(path, value)
    assert history(path)["events"] == []


def test_changed_history_fails_integrity_check(tmp_path: Path) -> None:
    path = setup(tmp_path)
    add(path, entry(tmp_path))
    with sqlite3.connect(path) as database:
        database.execute(
            "UPDATE events SET payload=? WHERE sequence=1", ('{"kind":"RECORD"}',)
        )
    with pytest.raises(ContractError, match="integrity"):
        history(path)


def test_cli_persists_private_receipts_and_does_not_replace_catalog(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    output = tmp_path / "init.json"
    assert (
        main(
            [
                "init",
                "--catalog",
                str(path),
                "--studio-id",
                "studio-a",
                "--minimum-confidence",
                "0.80",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["remote_sharing"] is False
    with pytest.raises(FileExistsError):
        create_catalog(path, "studio-b", "0.80")
    assert history(path)["metadata"]["studio_id"] == "studio-a"


def bound_case(path: Path) -> dict:
    """Bind a synthetic, already reviewed case to the exact selected catalog class."""
    case = read_json(PLUGIN / "examples/synthetic-case.json")
    metadata = history(path)["metadata"]
    case["catalog_context"] = {
        "catalog_id": metadata["catalog_id"],
        "studio_id": metadata["studio_id"],
    }
    case["mappings"][0]["catalog_binding"] = find(path, client_id=case["client_id"])[
        "binding"
    ]
    return case


def test_current_catalog_mapping_supports_calculation_without_overwriting_row_deduction(
    tmp_path: Path,
) -> None:
    path = setup(tmp_path)
    add(path, entry(tmp_path))
    case = bound_case(path)
    result = calculate(case, PLUGIN / "examples", path)
    assert result["status"] == "DRAFT_FOR_REVIEW"
    assert result["catalog_review"][0]["status"] == "CURRENT"
    assert result["modules"][0]["rows"]["vp14_debit"] == "110.00"


def test_revoked_catalog_mapping_blocks_a_previously_reviewed_case(
    tmp_path: Path,
) -> None:
    path = setup(tmp_path)
    value = entry(tmp_path)
    revision = add(path, value)
    case = bound_case(path)
    revoke(
        path,
        value["entry_id"],
        value["review"],
        expected_head=history(path)["head_hash"],
        revision=revision["event_hash"],
    )
    result = calculate(case, PLUGIN / "examples", path)
    assert result["modules"] == []
    assert "CATALOG_MAPPING_STALE_OR_UNRESOLVED:SALES:V22" in result["blockers"]


def test_conflicting_meaning_inside_quarter_cannot_hide_behind_matching_endpoints(
    tmp_path: Path,
) -> None:
    path = setup(tmp_path)
    add(path, entry(tmp_path))
    case = bound_case(path)
    conflicting = entry(tmp_path, "mid-quarter-conflict")
    conflicting.update(valid_from="2026-05-15", valid_until="2026-05-20")
    conflicting["tax_class"]["treatment"] = "SALE_EXCLUDED"
    add(path, conflicting)
    result = calculate(case, PLUGIN / "examples", path)
    assert result["status"] == "BLOCKED"
    assert result["catalog_review"][0]["checks"][1]["on_date"] == "2026-05-15"
    assert result["catalog_review"][0]["checks"][1]["status"] == "CONFLICT"


def test_unrelated_catalog_revision_does_not_invalidate_selected_mapping(
    tmp_path: Path,
) -> None:
    path = setup(tmp_path)
    add(path, entry(tmp_path))
    case = bound_case(path)
    another = entry(tmp_path, "another-code")
    another["code"] = "V10"
    add(path, another)
    result = calculate(case, PLUGIN / "examples", path)
    assert result["status"] == "DRAFT_FOR_REVIEW"


def test_missing_live_catalog_blocks_bound_case_instead_of_using_cached_confirmation(
    tmp_path: Path,
) -> None:
    path = setup(tmp_path)
    add(path, entry(tmp_path))
    case = bound_case(path)
    result = calculate(case, PLUGIN / "examples")
    assert result["modules"] == []
    assert result["blockers"] == ["CATALOG_NOT_AVAILABLE"]


def test_case_cannot_use_another_catalog_with_same_studio_label(tmp_path: Path) -> None:
    path = setup(tmp_path)
    add(path, entry(tmp_path))
    case = bound_case(path)
    other = tmp_path / "other.sqlite3"
    create_catalog(other, "studio-a", "0.80")
    with pytest.raises(ContractError, match="does not match"):
        calculate(case, PLUGIN / "examples", other)


def test_explicit_catalog_dispute_blocks_even_a_confirmed_client_override(
    tmp_path: Path,
) -> None:
    path = setup(tmp_path)
    add(path, entry(tmp_path, "central", "CENTRAL"))
    client = entry(tmp_path, "client", "CLIENT")
    add(path, client)
    flag = dispute(
        path,
        client,
        tmp_path,
        client["review"],
        expected_head=history(path)["head_hash"],
    )
    result = find(path)
    assert result["status"] == "CURATOR_DISPUTE_OPEN"
    assert result["candidate"] is None
    assert result["open_disputes"] == [flag["event_hash"]]


def test_curator_resolution_identifies_current_central_revision_and_keeps_prior_conflict(
    tmp_path: Path,
) -> None:
    path = setup(tmp_path)
    value = entry(tmp_path, "central", "CENTRAL")
    selected = add(path, value)
    flag = dispute(
        path, value, tmp_path, value["review"], expected_head=history(path)["head_hash"]
    )
    resolved = resolve_dispute(
        path,
        flag["event_hash"],
        value["curator_review"],
        expected_head=history(path)["head_hash"],
        selected_revision=selected["event_hash"],
    )
    state = history(path)
    assert state["events"][1] == flag
    assert state["events"][2] == resolved
    assert find(path)["status"] == "CANDIDATE_FOR_CASE_REVIEW"


def test_studio_confirmation_cannot_resolve_a_cross_catalog_dispute(
    tmp_path: Path,
) -> None:
    path = setup(tmp_path)
    value = entry(tmp_path)
    selected = add(path, value)
    flag = dispute(
        path, value, tmp_path, value["review"], expected_head=history(path)["head_hash"]
    )
    with pytest.raises(ContractError, match="curator revision"):
        resolve_dispute(
            path,
            flag["event_hash"],
            value["review"],
            expected_head=history(path)["head_hash"],
            selected_revision=selected["event_hash"],
        )
    assert find(path)["status"] == "CURATOR_DISPUTE_OPEN"


def test_unquoted_vendor_code_cannot_be_learned_from_unrelated_evidence(
    tmp_path: Path,
) -> None:
    path = setup(tmp_path)
    value = entry(tmp_path)
    value["code"] = "INVENTED"
    with pytest.raises(ContractError, match="absent from the quoted"):
        add(path, value)
    assert history(path)["events"] == []


def test_catalog_preserves_original_evidence_after_intake_folder_is_removed(
    tmp_path: Path,
) -> None:
    path = setup(tmp_path)
    value = entry(tmp_path)
    revision = add(path, value)
    (tmp_path / "synthetic-legend.txt").unlink()
    result = find(path)
    reference = result["alternatives"][0]["source_objects"][0]
    stored = path.parent / (path.name + ".sources") / reference["object"]
    assert stored.read_text(encoding="utf-8") == value["evidence"][0]["quote"]
    assert result["alternatives"][0]["revision_hash"] == revision["event_hash"]


def test_missing_catalog_evidence_blocks_lookup_instead_of_trusting_saved_class(
    tmp_path: Path,
) -> None:
    path = setup(tmp_path)
    value = entry(tmp_path)
    revision = add(path, value)
    stored = (
        path.parent
        / (path.name + ".sources")
        / revision["event"]["source_objects"][0]["object"]
    )
    stored.unlink()
    with pytest.raises(ContractError, match="missing or changed"):
        find(path)
