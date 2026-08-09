"""Tests for the Presenza digitale dello studio workflow."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

PLUGIN_ROOT = Path("plugins/presenza-digitale-studio")
WORKFLOW_CORE_PATH = PLUGIN_ROOT / "scripts/workflow_core.py"
PREVIEW_DESTINATION = "https://preview.example.test/unlisted-token/"
FINAL_DESTINATION = "https://studio.example.test/"


def _load_workflow_core() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "presenza_digitale_workflow_core",
        WORKFLOW_CORE_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _intake(*, source_path: Path | None = None) -> dict[str, object]:
    selected_files: list[dict[str, str]] = []
    if source_path is not None:
        selected_files.append(
            {"id": "studio-facts", "role": "studio_material", "path": str(source_path)}
        )
    return {
        "schema_version": 1,
        "mode": "first_site",
        "studio": {
            "name": "Studio Esempio",
            "owner": "Studio Esempio",
            "language": "it",
        },
        "reference_date": "2026-08-09",
        "objective": "Create a credible first website",
        "audiences": ["Imprenditori"],
        "requested_pages": ["Home"],
        "existing_site": {"url": None, "platform": None},
        "selected_files": selected_files,
        "constraints": ["No invented claims"],
        "external_routes": {
            "public_site_inspection": {
                "selected": False,
                "destination": "",
                "approved_by_user": False,
            },
            "creative_assistance": {
                "selected": False,
                "destination": "",
                "approved_by_user": False,
            },
            "preview_publication": {
                "selected": True,
                "destination": PREVIEW_DESTINATION,
                "approved_by_user": True,
            },
            "final_publication": {
                "selected": True,
                "destination": FINAL_DESTINATION,
                "approved_by_user": True,
            },
        },
    }


def _valid_site_html(*, noindex: bool = True) -> str:
    robots = (
        '<meta name="robots" content="noindex, nofollow, noarchive">' if noindex else ""
    )
    return f"""<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">{robots}
<title>Studio Esempio</title></head>
<body><main><h1>Studio Esempio</h1><img src="portrait.svg" alt="Ritratto del professionista">
<a href="#contatti">Contatti</a><section id="contatti"><h2>Contatti</h2></section></main></body></html>"""


def _prepare_run(tmp_path: Path, *, noindex: bool = True) -> tuple[ModuleType, Path]:
    workflow = _load_workflow_core()
    workspace = tmp_path / "workspace"
    workflow.initialize_workspace(
        workspace,
        workspace_id="studio-example",
        owner="Studio Esempio",
        retention_owner="Studio Esempio",
    )
    intake_path = _write_json(tmp_path / "intake.json", _intake())
    run_dir = workflow.prepare_run(workspace, intake_path)
    site_dir = run_dir / "work/site"
    (site_dir / "index.html").write_text(
        _valid_site_html(noindex=noindex), encoding="utf-8"
    )
    (site_dir / "portrait.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"></svg>',
        encoding="utf-8",
    )
    workflow.validate_site(run_dir)
    validation = json.loads(
        (run_dir / "site_validation.json").read_text(encoding="utf-8")
    )
    dimension = {"status": "strong", "rationale": "The rendered page is clear."}
    assessment = {
        "schema_version": 1,
        "site_digest": validation["site_digest"],
        "validation_digest": validation["validation_digest"],
        "viewports": [
            {
                "name": "desktop",
                "width": 1440,
                "height": 900,
                "full_page_reviewed": True,
                "issues": [],
            },
            {
                "name": "phone",
                "width": 390,
                "height": 844,
                "full_page_reviewed": True,
                "issues": [],
            },
        ],
        "dimensions": {
            "hierarchy": dimension,
            "copy_clarity": dimension,
            "visual_consistency": dimension,
            "responsiveness": dimension,
            "accessibility_signals": dimension,
            "resilience": dimension,
            "professional_appropriateness": dimension,
        },
        "console_issues": [],
        "weakest_element": "The intentionally small first-site scope.",
        "verdict": "ready",
        "required_changes": [],
    }
    assessment_path = _write_json(tmp_path / "assessment.json", assessment)
    workflow.record_quality_assessment(
        run_dir,
        assessment_path,
        provider="test-provider",
        model="test-model",
        recorded_by="test-operator",
    )
    return workflow, run_dir


def _accept_release_reviews(workflow: ModuleType, run_dir: Path) -> None:
    workflow.record_review(
        run_dir,
        scope="identity_and_claims",
        decision="accepted",
        reviewer="Studio Esempio",
    )
    workflow.record_review(
        run_dir,
        scope="responsive_preview",
        decision="accepted",
        reviewer="Studio Esempio",
    )
    workflow.record_review(
        run_dir,
        scope="publication_destination",
        decision="accepted",
        reviewer="Studio Esempio",
    )


def test_package_website_preview_requires_noindex(tmp_path: Path) -> None:
    workflow, run_dir = _prepare_run(tmp_path, noindex=False)

    with pytest.raises(ValueError, match="must include noindex"):
        workflow.package_website(run_dir, kind="preview")


def test_package_website_release_requires_all_current_reviews(tmp_path: Path) -> None:
    workflow, run_dir = _prepare_run(tmp_path)

    with pytest.raises(ValueError, match="Release reviews missing"):
        workflow.package_website(run_dir, kind="release")


def test_full_first_site_lifecycle_records_exact_publication(tmp_path: Path) -> None:
    workflow, run_dir = _prepare_run(tmp_path)
    _accept_release_reviews(workflow, run_dir)
    workflow.package_website(run_dir, kind="release")

    receipt_path = workflow.record_external_delivery(
        run_dir,
        kind="release",
        destination=FINAL_DESTINATION,
        visible_receipt=FINAL_DESTINATION,
        confirmed_by="Studio Esempio",
    )

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["destination"] == FINAL_DESTINATION
    assert receipt["confirmed_by_user"] is True
    assert len(receipt["package_digest"]) == 64


def test_validate_site_blocks_missing_alt_and_local_asset(tmp_path: Path) -> None:
    workflow = _load_workflow_core()
    workspace = tmp_path / "workspace"
    workflow.initialize_workspace(
        workspace,
        workspace_id="studio-example",
        owner="Studio Esempio",
        retention_owner="Studio Esempio",
    )
    run_dir = workflow.prepare_run(
        workspace, _write_json(tmp_path / "intake.json", _intake())
    )
    (run_dir / "work/site/index.html").write_text(
        """<!doctype html><html lang="it"><head><meta name="viewport" content="width=device-width"><title>Studio</title></head><body><h1>Studio</h1><img src="missing.png"></body></html>""",
        encoding="utf-8",
    )

    report_path = workflow.validate_site(run_dir)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "blocked"
    error_text = "\n".join(report["errors"])
    assert "missing alt" in error_text
    assert "missing local target" in error_text


def test_record_site_brief_rejects_unknown_evidence_id(tmp_path: Path) -> None:
    workflow = _load_workflow_core()
    source_path = tmp_path / "facts.txt"
    source_path.write_text("Dottore commercialista", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workflow.initialize_workspace(
        workspace,
        workspace_id="studio-example",
        owner="Studio Esempio",
        retention_owner="Studio Esempio",
    )
    intake_path = _write_json(
        tmp_path / "intake.json", _intake(source_path=source_path)
    )
    run_dir = workflow.prepare_run(workspace, intake_path)
    brief = {
        "schema_version": 1,
        "mode": "first_site",
        "evidence_summary": "One supplied studio fact.",
        "observed_facts": [
            {
                "id": "fact-1",
                "statement": "Qualified professional",
                "source_ids": ["unknown"],
            }
        ],
        "open_questions": [],
        "target_audiences": ["Imprenditori"],
        "sitemap": [
            {
                "page_id": "home",
                "path": "/",
                "purpose": "Introduce the studio",
                "sections": ["Hero"],
            }
        ],
        "studio_profile": [
            {
                "field": "tone",
                "value": "restrained",
                "basis": "vera_default_proposal",
                "evidence_ids": [],
            }
        ],
        "content_plan": [
            {
                "page_id": "home",
                "primary_message": "Support for entrepreneurs",
                "primary_action": "Contact",
                "required_facts": ["qualification"],
            }
        ],
        "visual_direction": {
            "intent": "calm",
            "palette": ["navy"],
            "typography": "clear",
            "image_strategy": "supplied only",
            "avoid": ["generic AI imagery"],
        },
        "implementation": {
            "approach": "semantic HTML",
            "skills_used": ["frontend-design"],
            "skills_unavailable": [],
        },
        "claims": [],
        "exclusions": ["client portal"],
    }
    brief_path = _write_json(tmp_path / "brief.json", brief)

    with pytest.raises(ValueError, match="unknown source IDs"):
        workflow.record_site_brief(
            run_dir,
            brief_path,
            provider="test-provider",
            model="test-model",
            recorded_by="test-operator",
        )


def test_validate_run_detects_site_change_after_release(tmp_path: Path) -> None:
    workflow, run_dir = _prepare_run(tmp_path)
    _accept_release_reviews(workflow, run_dir)
    workflow.package_website(run_dir, kind="release")
    (run_dir / "work/site/index.html").write_text(
        _valid_site_html().replace("Studio Esempio</h1>", "Studio Aggiornato</h1>"),
        encoding="utf-8",
    )

    result = workflow.validate_run(run_dir)

    assert result["valid"] is False
    assert "current site bytes changed after validation" in result["issues"]
    assert "release package is stale" in result["issues"]
