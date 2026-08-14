from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
VERA_ROOT = ROOT / "plugins" / "vera"
VALIDATOR = (
    VERA_ROOT
    / "skills"
    / "privacy-surface-review"
    / "scripts"
    / "validate_privacy_surfaces.py"
)
CONTEXT_POLICY = "real_case_data_may_enter_selected_runtime_model_context"
RUNTIME_PROFILE_IDS = ["openai-codex", "anthropic-cowork"]
ACCOUNT_BOUNDARY = {
    "selected_by": "firm_or_user",
    "vera_runtime_enforcement": "none",
    "review_timing": "before_professional_use_and_when_account_or_terms_change",
    "review_items": [
        "account_or_workspace_plan",
        "model_training_data_controls",
        "retention_and_deletion_controls",
    ],
    "per_case_record_required": False,
}
PUBLIC_PROCESS_PAGE_CONTRACT = (
    VERA_ROOT / "skills" / "vera" / "references" / "public-process-page-contract.md"
)


def _validator_module():
    spec = importlib.util.spec_from_file_location("vera_privacy_validator", VALIDATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifests() -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((VERA_ROOT / "privacy" / "workstreams").glob("*.json"))
    ]


def _service_manifests() -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((VERA_ROOT / "privacy" / "services").glob("*.json"))
    ]


def _runtime_profiles() -> list[dict[str, Any]]:
    payload = json.loads(
        (VERA_ROOT / "privacy" / "runtime-profiles.json").read_text(encoding="utf-8")
    )
    return payload["profiles"]


def test_vera_privacy_register_covers_current_workstreams_and_is_fresh() -> None:
    validator = _validator_module()

    errors = validator.validate_privacy_surfaces(VERA_ROOT)

    assert errors == []


def test_vera_privacy_manifests_match_the_published_schema() -> None:
    schema = json.loads(
        (VERA_ROOT / "privacy" / "privacy-surface.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = jsonschema.Draft202012Validator(schema)
    errors = {
        str(manifest["workstream"]): [
            error.message for error in validator.iter_errors(manifest)
        ]
        for manifest in _manifests()
    }

    assert errors
    assert all(not manifest_errors for manifest_errors in errors.values()), errors


def test_vera_runtime_profiles_match_the_published_schema() -> None:
    schema = json.loads(
        (VERA_ROOT / "privacy" / "runtime-profiles.schema.json").read_text(
            encoding="utf-8"
        )
    )
    payload = json.loads(
        (VERA_ROOT / "privacy" / "runtime-profiles.json").read_text(encoding="utf-8")
    )
    validator = jsonschema.Draft202012Validator(schema)

    errors = [error.message for error in validator.iter_errors(payload)]

    assert errors == []


def test_vera_shared_service_manifests_match_the_published_schema() -> None:
    schema = json.loads(
        (VERA_ROOT / "privacy" / "service-boundary.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = jsonschema.Draft202012Validator(schema)
    errors = {
        str(manifest["service_id"]): [
            error.message for error in validator.iter_errors(manifest)
        ]
        for manifest in _service_manifests()
    }

    assert errors
    assert all(not manifest_errors for manifest_errors in errors.values()), errors


def test_vera_shared_services_separate_runtime_update_and_feedback() -> None:
    manifests = {manifest["service_id"]: manifest for manifest in _service_manifests()}

    assert set(manifests) == {
        "managed-python-runtime",
        "plugin-update-check",
        "plugin-feedback",
    }
    runtime_boundaries = manifests["managed-python-runtime"]["external_boundaries"]
    assert [boundary["id"] for boundary in runtime_boundaries] == [
        "declared-core-dependency-retrieval"
    ]
    assert runtime_boundaries[0]["activation"] == "automatic_on_first_use"
    assert runtime_boundaries[0]["requires_confirmation"] is False
    update_boundaries = manifests["plugin-update-check"]["external_boundaries"]
    assert [boundary["id"] for boundary in update_boundaries] == [
        "automatic-version-check"
    ]
    assert update_boundaries[0]["activation"] == "automatic_session_start"
    feedback_boundaries = manifests["plugin-feedback"]["external_boundaries"]
    assert [boundary["id"] for boundary in feedback_boundaries] == [
        "automatic-feedback-status-poll",
        "approved-text-feedback-submission",
        "approved-follow-up-evidence",
        "approved-improvement-interview",
    ]
    assert feedback_boundaries[0]["activation"] == ("automatic_after_prior_submission")
    assert all(
        boundary["activation"] == "explicit_user_choice"
        and boundary["optional"] is True
        and boundary["requires_confirmation"] is True
        for boundary in feedback_boundaries[1:]
    )


def test_vera_security_controls_exclude_architecture_and_policy_labels() -> None:
    ceremonial_ids = {
        "draft-status",
        "local-file-processing",
        "local-mechanical-checks",
        "local-reconciliation",
        "local-report-build",
        "local-sampling",
        "no-external-data-path",
        "no-model-api-in-scripts",
        "no-retroactive-anonymisation-claim",
    }

    for manifest in _manifests():
        control_ids = {row["id"] for row in manifest["security_controls"]}
        assert not control_ids & ceremonial_ids


def test_vera_privacy_contract_allows_real_case_data_without_minimum_classifier() -> (
    None
):
    forbidden_fields = {
        "commercialista_notice",
        "data_flow",
        "full_source_expected",
        "minimum_necessary",
        "residual_risks",
        "semantic_reasoning_required",
    }

    for manifest in _manifests():
        assert manifest["schema_version"] == 3
        assert manifest["runtime_profiles"] == RUNTIME_PROFILE_IDS
        model_context = manifest["model_context"]
        assert model_context["policy"] == CONTEXT_POLICY
        assert model_context["classes"]
        assert forbidden_fields.isdisjoint(manifest)
        for context_class in model_context["classes"]:
            assert forbidden_fields.isdisjoint(context_class)
            assert set(context_class["runtime_profiles"]) <= set(RUNTIME_PROFILE_IDS)


def test_vera_account_boundary_is_shared_and_not_a_per_case_form() -> None:
    profiles = _runtime_profiles()

    assert [profile["id"] for profile in profiles] == RUNTIME_PROFILE_IDS
    assert all(profile["account_boundary"] == ACCOUNT_BOUNDARY for profile in profiles)


def test_vera_model_processing_has_no_extra_recipient_or_fake_local_guarantee() -> None:
    for profile in _runtime_profiles():
        processing = profile["model_processing"]
        assert processing["separate_vera_recipient"] is False
        assert processing["automatic_anonymization"] is False
        assert processing["local_only"] is False
        assert (
            processing["local_filtering_or_aggregation"]
            == "only_when_useful_for_the_work"
        )


def test_vera_public_process_model_data_contract_is_canonical_and_linked() -> None:
    """Keep the public rule explicit without mechanizing semantic relevance."""

    contract = PUBLIC_PROCESS_PAGE_CONTRACT.read_text(encoding="utf-8")
    review_skill = (
        VERA_ROOT / "skills" / "privacy-surface-review" / "SKILL.md"
    ).read_text(encoding="utf-8")
    catalog = (
        VERA_ROOT / "skills" / "vera" / "references" / "workflow-catalog.md"
    ).read_text(encoding="utf-8")
    normalized_contract = " ".join(contract.split())

    for required_rule in (
        "Every public process explanation must contain one visible block",
        "This entire block must be the final block",
        "Quali dati arrivano al modello",
        "What data reaches the model",
        'data-model-data-status="relevant|not-relevant"',
        "full population",
        "Codex and Cowork",
        "Not relevant to this process",
        "never a fallback for an incomplete review",
        "It is not a central per-process register",
        "must not infer a status from keywords",
    ):
        assert required_rule in normalized_contract
    assert "../vera/references/public-process-page-contract.md" in review_skill
    assert "`public-process-page-contract.md`" in catalog


def test_archive_pages_explain_the_purpose_preserving_model_projection() -> None:
    studio_page = (
        ROOT / "static" / "shared" / "studio-archive" / "index.html"
    ).read_text(encoding="utf-8")
    organization_page = (
        ROOT / "static" / "shared" / "archive-organization" / "index.html"
    ).read_text(encoding="utf-8")

    assert studio_page.count('"model.engagement.copy":') == 5
    assert organization_page.count('"model.inventory.copy":') == 5
    assert organization_page.count('"model.review.copy":') == 5
    for snippet in (
        "stored emails, legal names, and tax identifiers stay local",
        "code performs an exact match and returns only matching safe rows",
        "every snapshot file within 5,000 files and 2 GB",
        "raw hashes, Drive IDs, versions, capabilities, and absolute source paths stay local",
        "Organization technical references are pseudonymized",
        "only after operator review and approval",
        "sanitized control roles and labels outside tables",
        "Typed or selected values, credentials and one-time codes",
        "sanitization does not guarantee anonymization",
    ):
        assert snippet in studio_page
    for localized_agenzia_gate in (
        "solo dopo revisione e approvazione dell’operatore",
        "only after operator review and approval",
        "seulement après examen et approbation par l’opérateur",
        "erst nach Prüfung und Freigabe durch den Bediener",
        "solo después de la revisión y aprobación del operador",
    ):
        assert localized_agenzia_gate in studio_page
    for contradictory_exclusion in (
        "hash e ID di esecuzione grezzi",
        "raw hashes and execution IDs",
        "empreintes et ID d’exécution bruts",
        "rohe Hashes und Ausführungs-IDs",
        "huellas e ID de ejecución brutos",
    ):
        assert contradictory_exclusion not in studio_page
    for snippet in (
        "every snapshot file, not a sample",
        "Hashes, Drive root, file and parent IDs, versions, capabilities, checksums, and absolute source paths remain in local control",
        "random hash-bound reference valid for four hours",
        "for a plan supplied in Cowork or ChatGPT, the reference is review-only",
        "Technical references are pseudonymized; document content is not automatically anonymized",
    ):
        assert snippet in organization_page


def test_three_reconciliation_pages_share_the_same_concrete_model_data_flow() -> None:
    pages = (
        ROOT / "static" / "shared" / "riconciliazione-partite" / "index.html",
        ROOT / "static" / "shared" / "journal-bank-reconciliation" / "index.html",
        ROOT / "static" / "shared" / "check-entries" / "index.html",
    )
    required = (
        "Il modello comprende la struttura",
        "Il codice elabora localmente l'intero perimetro",
        "Il modello riceve un indice dei casi da rivedere",
        "L'indice usa riferimenti opachi ai casi",
        "Il modello richiede il contesto di un caso quando serve",
        "I dati professionali non vengono anonimizzati né pseudonimizzati automaticamente",
    )

    for path in pages:
        page = path.read_text(encoding="utf-8")
        model_block = page.split('data-model-data-status="relevant"', 1)[1].split(
            "</section>",
            1,
        )[0]
        for snippet in required:
            assert snippet in model_block
        if path.parent.name == "journal-bank-reconciliation":
            assert "Solo nel runtime Codex" in model_block
            assert "Cowork non esegue questo passaggio" in model_block
            assert "l’intero insieme rientra in un unico pacchetto limitato" in model_block
            assert "non può modificare gli abbinamenti deterministici" in model_block
        else:
            assert "Codex" not in model_block
            assert "Cowork" not in model_block


def test_vera_external_confirmations_are_limited_to_optional_boundaries() -> None:
    for manifest in _manifests():
        assert isinstance(manifest["external_boundaries"], list)
        for boundary in manifest["external_boundaries"]:
            if boundary["requires_confirmation"]:
                assert boundary["optional"] is True
            assert set(boundary["runtime_profiles"]) <= set(
                manifest["runtime_profiles"]
            )


def test_vera_workflow_wrappers_do_not_show_routine_privacy_notices() -> None:
    components = json.loads((VERA_ROOT / "components.json").read_text(encoding="utf-8"))
    roles = components.get("workflow_roles", {})

    for workstream in components["plugins"]:
        if roles.get(workstream, {}).get("kind") == "internal_engine":
            continue
        wrapper = VERA_ROOT / "skills" / workstream / "SKILL.md"
        text = wrapper.read_text(encoding="utf-8")
        assert "## Privacy Boundary" not in text
        assert "commercialista_notice" not in text


def test_vera_governance_uses_runtime_profiles_without_double_confirmation() -> None:
    profiles = _runtime_profiles()
    review = (VERA_ROOT / "skills" / "privacy-surface-review" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert all(
        profile["account_boundary"]["selected_by"] == "firm_or_user"
        for profile in profiles
    )
    assert "approved Codex" not in review
    assert "do not ask again" in review


def test_vera_component_guidance_avoids_fake_minimums_and_ambiguous_authority() -> None:
    new_client = (
        ROOT / "plugins" / "new-client" / "skills" / "new-client" / "SKILL.md"
    ).read_text(encoding="utf-8")
    registro_skill = (
        ROOT
        / "plugins"
        / "registro-imprese-sari"
        / "skills"
        / "registro-imprese-sari"
        / "SKILL.md"
    ).read_text(encoding="utf-8")
    registro_sources = (
        ROOT
        / "plugins"
        / "registro-imprese-sari"
        / "references"
        / "official-sources.md"
    ).read_text(encoding="utf-8")

    assert "client-relationship privacy role or processing basis" in new_client
    assert "processing authority" not in new_client
    assert "minimum metadata needed for provenance" not in registro_skill
    assert "register minimal metadata" not in registro_sources


def test_vera_privacy_validator_reports_unregistered_manifest_gap(
    tmp_path: Path,
) -> None:
    validator = _validator_module()
    vera_root = tmp_path / "plugins" / "vera"
    shutil.copytree(VERA_ROOT, vera_root)
    missing = vera_root / "privacy" / "workstreams" / "check-entries.json"
    missing.unlink()

    errors = validator.validate_privacy_surfaces(vera_root)

    assert "check-entries: registered workstream has no privacy manifest" in errors


def test_vera_privacy_validator_reports_shared_service_manifest_gap(
    tmp_path: Path,
) -> None:
    validator = _validator_module()
    vera_root = tmp_path / "plugins" / "vera"
    shutil.copytree(VERA_ROOT, vera_root)
    missing = vera_root / "privacy" / "services" / "plugin-feedback.json"
    missing.unlink()

    errors = validator.validate_privacy_surfaces(vera_root)

    assert (
        "plugin-feedback: registered shared service has no privacy manifest" in errors
    )


def test_vera_privacy_validator_detects_changed_shared_service_source(
    tmp_path: Path,
) -> None:
    validator = _validator_module()
    vera_root = tmp_path / "plugins" / "vera"
    shutil.copytree(VERA_ROOT, vera_root)
    components = json.loads((vera_root / "components.json").read_text(encoding="utf-8"))
    components["plugins"] = []
    components["workflow_roles"] = {}
    components["shared_services"] = [
        "plugin-update-check",
        "plugin-feedback",
    ]
    (vera_root / "components.json").write_text(
        json.dumps(components, indent=2) + "\n", encoding="utf-8"
    )
    for manifest in (vera_root / "privacy" / "workstreams").glob("*.json"):
        manifest.unlink()
    for relative_path in (
        Path("modules/change_requests/api.py"),
        Path("modules/change_requests/store.py"),
        Path("scripts/manage_change_requests.py"),
    ):
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative_path, target)

    validator._refresh_service("all", vera_root)
    updater = vera_root / "scripts" / "check_for_update.py"
    updater.write_text(
        updater.read_text(encoding="utf-8") + "\n# material boundary change\n",
        encoding="utf-8",
    )

    errors = validator.validate_privacy_surfaces(vera_root)

    assert (
        "plugin-update-check: privacy review is stale; run the review skill, then --refresh-service"
        in errors
    )
    assert (
        "plugin-feedback: privacy review is stale; run the review skill, then --refresh-service"
        in errors
    )


def test_vera_privacy_validator_detects_changed_governed_source(
    tmp_path: Path,
) -> None:
    plugins_root = tmp_path / "plugins"
    vera_root = plugins_root / "vera"
    component_root = plugins_root / "prompt-optimizer"
    shared_assurance = (
        plugins_root / "_shared" / "vendor" / "modules" / "vera_assurance"
    )
    shutil.copytree(VERA_ROOT, vera_root)
    shutil.copytree(ROOT / "plugins" / "prompt-optimizer", component_root)
    shutil.copytree(
        ROOT / "plugins" / "_shared" / "vendor" / "modules" / "vera_assurance",
        shared_assurance,
    )
    shared_server = tmp_path / "scripts" / "serve_review_workbench.py"
    shared_server.parent.mkdir()
    shutil.copy2(ROOT / "scripts" / "serve_review_workbench.py", shared_server)
    components = json.loads((vera_root / "components.json").read_text(encoding="utf-8"))
    components["plugins"] = ["prompt-optimizer"]
    components["workflow_roles"] = {}
    components["shared_services"] = []
    (vera_root / "components.json").write_text(
        json.dumps(components, indent=2) + "\n", encoding="utf-8"
    )
    manifest_dir = vera_root / "privacy" / "workstreams"
    for manifest in manifest_dir.glob("*.json"):
        if manifest.stem != "prompt-optimizer":
            manifest.unlink()
    for manifest in (vera_root / "privacy" / "services").glob("*.json"):
        manifest.unlink()
    validator_path = (
        vera_root
        / "skills"
        / "privacy-surface-review"
        / "scripts"
        / "validate_privacy_surfaces.py"
    )
    refreshed = subprocess.run(
        [sys.executable, str(validator_path), "--refresh", "prompt-optimizer"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert refreshed.returncode == 0, refreshed.stdout + refreshed.stderr
    governed_adapter = component_root / "assets" / "review-workbench-adapter.json"
    governed_adapter.write_text(
        governed_adapter.read_text(encoding="utf-8")
        + "\nMaterial browser-boundary change.\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(validator_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "prompt-optimizer: privacy review is stale" in result.stdout


def test_privacy_fingerprint_governs_projected_local_review_server(
    tmp_path: Path,
) -> None:
    validator = _validator_module()
    repository_root = tmp_path / "repository"
    plugins_root = repository_root / "plugins"
    vera_root = plugins_root / "vera"
    component_root = plugins_root / "client-file-preparation"
    shared_assurance = (
        plugins_root / "_shared" / "vendor" / "modules" / "vera_assurance"
    )
    shutil.copytree(VERA_ROOT, vera_root)
    shutil.copytree(ROOT / "plugins" / "client-file-preparation", component_root)
    shutil.copytree(
        ROOT / "plugins" / "_shared" / "vendor" / "modules" / "vera_assurance",
        shared_assurance,
    )
    shared_server = repository_root / "scripts" / "serve_review_workbench.py"
    shared_server.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "serve_review_workbench.py", shared_server)

    components = json.loads((vera_root / "components.json").read_text(encoding="utf-8"))
    components["plugins"] = ["client-file-preparation"]
    components["workflow_roles"] = {
        "client-file-preparation": {"kind": "internal_engine"}
    }
    components["shared_services"] = []
    (vera_root / "components.json").write_text(
        json.dumps(components, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest_dir = vera_root / "privacy" / "workstreams"
    for manifest in manifest_dir.glob("*.json"):
        if manifest.stem != "client-file-preparation":
            manifest.unlink()
    for manifest in (vera_root / "privacy" / "services").glob("*.json"):
        manifest.unlink()
    validator._refresh("client-file-preparation", vera_root)

    assert validator.validate_privacy_surfaces(vera_root) == []

    packaged_component = vera_root / "modules" / "client-file-preparation"
    shutil.copytree(component_root, packaged_component)
    shutil.copy2(shared_server, packaged_component / "scripts" / "review_server.py")
    shutil.copytree(
        shared_assurance,
        vera_root / "vendor" / "modules" / "vera_assurance",
    )
    assert validator.validate_privacy_surfaces(vera_root) == []

    shared_server.write_text(
        shared_server.read_text(encoding="utf-8") + "\n# privacy material change\n",
        encoding="utf-8",
    )
    shutil.rmtree(packaged_component)
    assert (
        "client-file-preparation: privacy review is stale; run the review skill, then --refresh"
        in validator.validate_privacy_surfaces(vera_root)
    )


def test_privacy_fingerprint_governs_workflow_wrapper_references(
    tmp_path: Path,
) -> None:
    validator = _validator_module()
    plugins_root = tmp_path / "repository" / "plugins"
    vera_root = plugins_root / "vera"
    component_root = plugins_root / "studio-archive"
    shared_assurance = (
        plugins_root / "_shared" / "vendor" / "modules" / "vera_assurance"
    )
    shared_ocr = plugins_root / "_shared" / "vendor" / "modules" / "vera_ocr"
    shutil.copytree(VERA_ROOT, vera_root)
    shutil.copytree(ROOT / "plugins" / "studio-archive", component_root)
    shutil.copytree(
        ROOT / "plugins" / "_shared" / "vendor" / "modules" / "vera_assurance",
        shared_assurance,
    )
    shutil.copytree(
        ROOT / "plugins" / "_shared" / "vendor" / "modules" / "vera_ocr",
        shared_ocr,
    )
    components = json.loads((vera_root / "components.json").read_text(encoding="utf-8"))
    components["plugins"] = ["studio-archive"]
    components["workflow_roles"] = {}
    components["shared_services"] = []
    (vera_root / "components.json").write_text(
        json.dumps(components, indent=2) + "\n",
        encoding="utf-8",
    )
    for manifest in (vera_root / "privacy" / "workstreams").glob("*.json"):
        if manifest.stem != "studio-archive":
            manifest.unlink()
    for manifest in (vera_root / "privacy" / "services").glob("*.json"):
        manifest.unlink()
    validator._refresh("studio-archive", vera_root)

    assert validator.validate_privacy_surfaces(vera_root) == []

    reference = (
        vera_root / "skills" / "studio-archive" / "references" / "marketplace-gmail.md"
    )
    reference.write_text(
        reference.read_text(encoding="utf-8") + "\nMaterial Gmail boundary change.\n",
        encoding="utf-8",
    )

    assert (
        "studio-archive: privacy review is stale; run the review skill, then --refresh"
        in validator.validate_privacy_surfaces(vera_root)
    )


def test_privacy_fingerprint_governs_shared_ocr_source(
    tmp_path: Path,
) -> None:
    validator = _validator_module()
    plugins_root = tmp_path / "repository" / "plugins"
    vera_root = plugins_root / "vera"
    component_root = plugins_root / "previdenza-inps"
    shared_assurance = (
        plugins_root / "_shared" / "vendor" / "modules" / "vera_assurance"
    )
    shared_ocr = plugins_root / "_shared" / "vendor" / "modules" / "vera_ocr"
    shutil.copytree(VERA_ROOT, vera_root)
    shutil.copytree(ROOT / "plugins" / "previdenza-inps", component_root)
    shutil.copytree(
        ROOT / "plugins" / "_shared" / "vendor" / "modules" / "vera_assurance",
        shared_assurance,
    )
    shutil.copytree(
        ROOT / "plugins" / "_shared" / "vendor" / "modules" / "vera_ocr",
        shared_ocr,
    )
    components = json.loads((vera_root / "components.json").read_text(encoding="utf-8"))
    components["plugins"] = ["previdenza-inps"]
    components["workflow_roles"] = {}
    components["shared_services"] = []
    (vera_root / "components.json").write_text(
        json.dumps(components, indent=2) + "\n", encoding="utf-8"
    )
    for manifest in (vera_root / "privacy" / "workstreams").glob("*.json"):
        if manifest.stem != "previdenza-inps":
            manifest.unlink()
    for manifest in (vera_root / "privacy" / "services").glob("*.json"):
        manifest.unlink()
    validator._refresh("previdenza-inps", vera_root)

    assert validator.validate_privacy_surfaces(vera_root) == []

    adapter = shared_ocr / "__init__.py"
    adapter.write_text(
        adapter.read_text(encoding="utf-8") + "\n# material model-route change\n",
        encoding="utf-8",
    )

    assert (
        "previdenza-inps: privacy review is stale; run the review skill, then --refresh"
        in validator.validate_privacy_surfaces(vera_root)
    )


def test_packaged_ocr_consumer_cannot_fall_back_to_repository_shared_source(
    tmp_path: Path,
) -> None:
    validator = _validator_module()
    plugins_root = tmp_path / "repository" / "plugins"
    vera_root = plugins_root / "vera"
    source_component = plugins_root / "previdenza-inps"
    shared_assurance = (
        plugins_root / "_shared" / "vendor" / "modules" / "vera_assurance"
    )
    shared_ocr = plugins_root / "_shared" / "vendor" / "modules" / "vera_ocr"
    shutil.copytree(VERA_ROOT, vera_root)
    shutil.copytree(ROOT / "plugins" / "previdenza-inps", source_component)
    shutil.copytree(
        ROOT / "plugins" / "_shared" / "vendor" / "modules" / "vera_assurance",
        shared_assurance,
    )
    shutil.copytree(
        ROOT / "plugins" / "_shared" / "vendor" / "modules" / "vera_ocr",
        shared_ocr,
    )
    components = json.loads((vera_root / "components.json").read_text(encoding="utf-8"))
    components["plugins"] = ["previdenza-inps"]
    components["workflow_roles"] = {}
    components["shared_services"] = []
    (vera_root / "components.json").write_text(
        json.dumps(components, indent=2) + "\n", encoding="utf-8"
    )
    for manifest in (vera_root / "privacy" / "workstreams").glob("*.json"):
        if manifest.stem != "previdenza-inps":
            manifest.unlink()
    for manifest in (vera_root / "privacy" / "services").glob("*.json"):
        manifest.unlink()
    validator._refresh("previdenza-inps", vera_root)
    shutil.copytree(source_component, vera_root / "modules" / "previdenza-inps")
    shutil.copytree(
        shared_assurance,
        vera_root / "vendor" / "modules" / "vera_assurance",
    )

    errors = validator.validate_privacy_surfaces(vera_root)

    assert any(
        error.startswith("previdenza-inps: cannot fingerprint governed source:")
        and "governed shared path" in error
        for error in errors
    )


def test_vera_privacy_validator_rejects_confirmation_on_required_boundary(
    tmp_path: Path,
) -> None:
    validator = _validator_module()
    vera_root = tmp_path / "plugins" / "vera"
    shutil.copytree(VERA_ROOT, vera_root)
    manifest_path = (
        vera_root / "privacy" / "workstreams" / "deep-research-validator.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["external_boundaries"][0]["requires_confirmation"] = True
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    errors = validator.validate_privacy_surfaces(vera_root)

    assert (
        "deep-research-validator: confirmation is allowed only for an optional boundary"
        in errors
    )
