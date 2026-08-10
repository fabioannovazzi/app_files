"""Tests for the Presenza digitale dello studio workflow."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import struct
import tarfile
import zlib
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


def _intake(
    *,
    source_path: Path,
    publication_provider: str = "other",
) -> dict[str, object]:
    selected_files = [
        {"id": "studio-facts", "role": "studio_material", "path": str(source_path)}
    ]
    return {
        "schema_version": 2,
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
        "confirmed_facts": [],
        "constraints": ["No invented claims"],
        "external_routes": {
            "public_site_inspection": {
                "selected": False,
                "provider": "none",
                "destination": "",
                "approved_by_user": False,
            },
            "studio_material_connector": {
                "selected": False,
                "provider": "none",
                "destination": "",
                "approved_by_user": False,
            },
            "creative_assistance": {
                "selected": False,
                "provider": "none",
                "destination": "",
                "approved_by_user": False,
            },
            "preview_publication": {
                "selected": True,
                "provider": publication_provider,
                "destination": PREVIEW_DESTINATION,
                "approved_by_user": True,
            },
            "final_publication": {
                "selected": True,
                "provider": publication_provider,
                "destination": FINAL_DESTINATION,
                "approved_by_user": True,
            },
        },
    }


def _valid_site_html(*, noindex: bool = False) -> str:
    robots = (
        '<meta name="robots" content="noindex, nofollow, noarchive">' if noindex else ""
    )
    return f"""<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">{robots}
<title>Studio Esempio</title></head>
<body><main><h1>Studio Esempio</h1><img src="portrait.svg" alt="Ritratto del professionista">
<a href="#contatti">Contatti</a><section id="contatti"><h2>Contatti</h2></section></main></body></html>"""


def _png_bytes(width: int, height: int) -> bytes:
    """Return a small, valid RGBA PNG with the requested dimensions."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    row = b"\x00" + (b"\x00" * width * 4)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(row * height))
        + chunk(b"IEND", b"")
    )


def _write_viewport_screenshot(
    run_dir: Path,
    relative: str,
    *,
    width: int,
    height: int,
) -> str:
    path = run_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    content = _png_bytes(width, height)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _quality_assessment(
    validation: dict[str, object],
    run_dir: Path,
    *,
    weakest_element: str = "The intentionally small first-site scope.",
) -> dict[str, object]:
    dimension = {"status": "strong", "rationale": "The rendered page is clear."}
    return {
        "schema_version": 2,
        "site_digest": validation["site_digest"],
        "validation_digest": validation["validation_digest"],
        "viewports": [
            {
                "name": "desktop",
                "width": 1440,
                "height": 900,
                "full_page_reviewed": True,
                "screenshot_path": "reviews/browser/desktop.png",
                "screenshot_sha256": _write_viewport_screenshot(
                    run_dir,
                    "reviews/browser/desktop.png",
                    width=1440,
                    height=900,
                ),
                "issues": [],
            },
            {
                "name": "phone",
                "width": 390,
                "height": 844,
                "full_page_reviewed": True,
                "screenshot_path": "reviews/browser/phone.png",
                "screenshot_sha256": _write_viewport_screenshot(
                    run_dir,
                    "reviews/browser/phone.png",
                    width=390,
                    height=844,
                ),
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
        "weakest_element": weakest_element,
        "verdict": "ready",
        "required_changes": [],
    }


def _valid_brief(*, source_id: str = "studio-facts") -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "first_site",
        "evidence_summary": "One supplied studio fact.",
        "observed_facts": [
            {
                "id": "fact-1",
                "statement": "Qualified professional",
                "source_ids": [source_id],
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


def _record_valid_brief(workflow: ModuleType, run_dir: Path, tmp_path: Path) -> None:
    workflow.record_site_brief(
        run_dir,
        _write_json(tmp_path / "brief.json", _valid_brief()),
        provider="test-provider",
        model="test-model",
        recorded_by="test-operator",
    )


def _prepare_run(
    tmp_path: Path,
    *,
    noindex: bool = False,
    publication_provider: str = "other",
) -> tuple[ModuleType, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
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
        tmp_path / "intake.json",
        _intake(
            source_path=source_path,
            publication_provider=publication_provider,
        ),
    )
    run_dir = workflow.prepare_run(workspace, intake_path)
    _record_valid_brief(workflow, run_dir, tmp_path)
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
    assessment = _quality_assessment(validation, run_dir)
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


def _record_sites_release(
    workflow: ModuleType,
    run_dir: Path,
    tmp_path: Path,
) -> tuple[Path, Path]:
    _accept_release_reviews(workflow, run_dir)
    manifest_path = workflow.package_website(run_dir, kind="release")
    sites_project = run_dir / "work/sites-project"
    (sites_project / ".openai").mkdir(exist_ok=True)
    _write_json(
        sites_project / ".openai/hosting.json",
        {"project_id": "site-project-123"},
    )
    binding_path = workflow.prepare_sites_binding(run_dir, kind="release")
    payload_path = sites_project / ".openai/vera-site-package.zip"
    server_path = sites_project / "dist/server/index.js"
    server_path.parent.mkdir(parents=True, exist_ok=True)
    server_path.write_text("export default {};", encoding="utf-8")
    archive_path = tmp_path / "sites-release.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(
            binding_path,
            arcname="dist/.openai/vera-release-binding.json",
        )
        archive.add(
            payload_path,
            arcname="dist/.openai/vera-site-package.zip",
        )
        archive.add(
            sites_project / ".openai/hosting.json",
            arcname="dist/.openai/hosting.json",
        )
        archive.add(server_path, arcname="dist/server/index.js")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    desktop_path = "reviews/sites/release/desktop.png"
    phone_path = "reviews/sites/release/phone.png"
    sites_receipt = {
        "schema_version": 2,
        "provider": "sites",
        "kind": "release",
        "destination": FINAL_DESTINATION,
        "project_id": "site-project-123",
        "commit_sha": "a" * 40,
        "archive_path": str(archive_path),
        "archive_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        "binding_member": "dist/.openai/vera-release-binding.json",
        "site_payload_member": "dist/.openai/vera-site-package.zip",
        "site_payload_sha256": hashlib.sha256(payload_path.read_bytes()).hexdigest(),
        "site_version_id": "version-123",
        "deployment_id": "deployment-123",
        "deployment_status": "succeeded",
        "access_level": "private",
        "access_approved_by_user": False,
        "deployed_url": "https://studio-example.sites.example.test/",
        "browser_review": {
            "reviewed_url": "https://studio-example.sites.example.test/",
            "deployment_id": "deployment-123",
            "viewports": [
                {
                    "name": "desktop",
                    "width": 1280,
                    "height": 800,
                    "full_page_reviewed": True,
                    "screenshot_path": desktop_path,
                    "screenshot_sha256": _write_viewport_screenshot(
                        run_dir,
                        desktop_path,
                        width=1280,
                        height=800,
                    ),
                    "issues": [],
                },
                {
                    "name": "phone",
                    "width": 390,
                    "height": 844,
                    "full_page_reviewed": True,
                    "screenshot_path": phone_path,
                    "screenshot_sha256": _write_viewport_screenshot(
                        run_dir,
                        phone_path,
                        width=390,
                        height=844,
                    ),
                    "issues": [],
                },
            ],
            "console_issues": [],
        },
        "site_digest": manifest["site_digest"],
        "validation_digest": manifest["validation_digest"],
        "quality_assessment_digest": manifest["quality_assessment_digest"],
        "reviews_digest": manifest["reviews_digest"],
        "package_digest": manifest["package_digest"],
    }
    receipt_path = workflow.record_sites_delivery(
        run_dir,
        _write_json(tmp_path / "sites-delivery.json", sites_receipt),
        confirmed_by="Studio Esempio",
    )
    return receipt_path, archive_path


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
    workflow, run_dir = _prepare_run(tmp_path)
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
    brief = _valid_brief(source_id="unknown")
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
    assert any(
        issue.startswith("release package is stale") for issue in result["issues"]
    )


def test_prepare_run_requires_selected_evidence(tmp_path: Path) -> None:
    workflow = _load_workflow_core()
    source_path = tmp_path / "facts.txt"
    source_path.write_text("Studio fact", encoding="utf-8")
    intake = _intake(source_path=source_path)
    intake["selected_files"] = []
    workspace = tmp_path / "workspace"
    workflow.initialize_workspace(
        workspace,
        workspace_id="studio-example",
        owner="Studio Esempio",
        retention_owner="Studio Esempio",
    )

    with pytest.raises(ValueError, match="selected_files"):
        workflow.prepare_run(workspace, _write_json(tmp_path / "intake.json", intake))


@pytest.mark.parametrize(
    ("mode", "existing_site"),
    [
        ("refresh", {"url": None, "platform": None}),
        (
            "first_site",
            {"url": "https://existing.example.test", "platform": "WordPress"},
        ),
    ],
)
def test_prepare_run_rejects_mode_site_contradiction(
    tmp_path: Path,
    mode: str,
    existing_site: dict[str, str | None],
) -> None:
    workflow = _load_workflow_core()
    source_path = tmp_path / "facts.txt"
    source_path.write_text("Studio fact", encoding="utf-8")
    intake = _intake(source_path=source_path)
    intake["mode"] = mode
    intake["existing_site"] = existing_site
    workspace = tmp_path / "workspace"
    workflow.initialize_workspace(
        workspace,
        workspace_id="studio-example",
        owner="Studio Esempio",
        retention_owner="Studio Esempio",
    )

    with pytest.raises(ValueError, match="website_intake"):
        workflow.prepare_run(workspace, _write_json(tmp_path / "intake.json", intake))


def test_record_site_brief_rejects_changed_evidence_snapshot(tmp_path: Path) -> None:
    workflow = _load_workflow_core()
    source_path = tmp_path / "facts.txt"
    source_path.write_text("Verified studio fact", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workflow.initialize_workspace(
        workspace,
        workspace_id="studio-example",
        owner="Studio Esempio",
        retention_owner="Studio Esempio",
    )
    run_dir = workflow.prepare_run(
        workspace,
        _write_json(tmp_path / "intake.json", _intake(source_path=source_path)),
    )
    register = json.loads(
        (run_dir / "source_register.json").read_text(encoding="utf-8")
    )
    snapshot = run_dir / register["sources"][0]["snapshot_path"]
    snapshot.chmod(0o600)
    snapshot.write_text("Changed unsupported fact", encoding="utf-8")

    with pytest.raises(ValueError, match="snapshot (?:byte count|hash) changed"):
        workflow.record_site_brief(
            run_dir,
            _write_json(tmp_path / "brief.json", _valid_brief()),
            provider="test-provider",
            model="test-model",
            recorded_by="test-operator",
        )


def test_ready_quality_rejects_blocked_duplicate_phone_review(tmp_path: Path) -> None:
    workflow, run_dir = _prepare_run(tmp_path)
    validation = json.loads(
        (run_dir / "site_validation.json").read_text(encoding="utf-8")
    )
    assessment = _quality_assessment(validation, run_dir)
    phone = dict(assessment["viewports"][1])
    phone["issues"] = ["Clipped navigation"]
    assessment["viewports"] = [phone, dict(phone)]
    assessment["console_issues"] = ["ReferenceError"]
    for dimension in assessment["dimensions"].values():
        dimension["status"] = "blocked"

    with pytest.raises(ValueError, match="quality_assessment"):
        workflow.record_quality_assessment(
            run_dir,
            _write_json(tmp_path / "bad-assessment.json", assessment),
            provider="test-provider",
            model="test-model",
            recorded_by="test-operator",
        )


def test_new_quality_assessment_invalidates_prior_reviews(tmp_path: Path) -> None:
    workflow, run_dir = _prepare_run(tmp_path)
    _accept_release_reviews(workflow, run_dir)
    validation = json.loads(
        (run_dir / "site_validation.json").read_text(encoding="utf-8")
    )
    workflow.record_quality_assessment(
        run_dir,
        _write_json(
            tmp_path / "new-assessment.json",
            _quality_assessment(
                validation,
                run_dir,
                weakest_element="A newer review",
            ),
        ),
        provider="test-provider",
        model="test-model",
        recorded_by="test-operator",
    )

    with pytest.raises(ValueError, match="Release reviews missing"):
        workflow.package_website(run_dir, kind="release")


def test_delivery_rejects_package_file_changed_after_packaging(tmp_path: Path) -> None:
    workflow, run_dir = _prepare_run(tmp_path)
    _accept_release_reviews(workflow, run_dir)
    manifest_path = workflow.package_website(run_dir, kind="release")
    (manifest_path.parent / "site/index.html").write_text(
        "tampered after packaging",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Package files differ"):
        workflow.record_external_delivery(
            run_dir,
            kind="release",
            destination=FINAL_DESTINATION,
            visible_receipt=FINAL_DESTINATION,
            confirmed_by="Studio Esempio",
        )


def test_delivery_rejects_empty_receipt_and_confirmer(tmp_path: Path) -> None:
    workflow, run_dir = _prepare_run(tmp_path)
    _accept_release_reviews(workflow, run_dir)
    workflow.package_website(run_dir, kind="release")

    with pytest.raises(ValueError, match="visible_receipt must be non-empty"):
        workflow.record_external_delivery(
            run_dir,
            kind="release",
            destination=FINAL_DESTINATION,
            visible_receipt="",
            confirmed_by="",
        )


def test_validate_site_rejects_symlinked_directory(tmp_path: Path) -> None:
    workflow, run_dir = _prepare_run(tmp_path)
    external = tmp_path / "external"
    external.mkdir()
    (external / "private.txt").write_text("must not cross", encoding="utf-8")
    (run_dir / "work/site/vendor").symlink_to(external, target_is_directory=True)

    with pytest.raises(ValueError, match="contains a symlink"):
        workflow.validate_site(run_dir)


def test_validate_site_checks_css_asset_closure(tmp_path: Path) -> None:
    workflow, run_dir = _prepare_run(tmp_path)
    index_path = run_dir / "work/site/index.html"
    index_path.write_text(
        index_path.read_text(encoding="utf-8").replace(
            "</head>", '<link rel="stylesheet" href="style.css"></head>'
        ),
        encoding="utf-8",
    )
    (run_dir / "work/site/style.css").write_text(
        "body { background: url(missing-background.png); }",
        encoding="utf-8",
    )

    report = json.loads(workflow.validate_site(run_dir).read_text(encoding="utf-8"))

    assert report["status"] == "blocked"
    assert any("missing-background.png" in issue for issue in report["errors"])


def test_preview_requires_complete_robots_posture(tmp_path: Path) -> None:
    workflow, run_dir = _prepare_run(tmp_path, noindex=True)
    index_path = run_dir / "work/site/index.html"
    index_path.write_text(
        index_path.read_text(encoding="utf-8").replace(
            "noindex, nofollow, noarchive", "noindex"
        ),
        encoding="utf-8",
    )
    validation = json.loads(workflow.validate_site(run_dir).read_text(encoding="utf-8"))
    workflow.record_quality_assessment(
        run_dir,
        _write_json(
            tmp_path / "assessment-robots.json",
            _quality_assessment(validation, run_dir),
        ),
        provider="test-provider",
        model="test-model",
        recorded_by="test-operator",
    )

    with pytest.raises(ValueError, match="nofollow and noarchive"):
        workflow.package_website(run_dir, kind="preview")


def test_validate_run_rejects_tampered_quality_record(tmp_path: Path) -> None:
    workflow, run_dir = _prepare_run(tmp_path)
    _accept_release_reviews(workflow, run_dir)
    workflow.package_website(run_dir, kind="release")
    quality_path = run_dir / "quality_assessment_record.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    quality["assessment"]["verdict"] = "blocked"
    quality["assessment"]["required_changes"] = ["Fix the site"]
    _write_json(quality_path, quality)

    result = workflow.validate_run(run_dir)

    assert result["valid"] is False
    assert any("quality assessment" in issue.lower() for issue in result["issues"])


def test_sites_delivery_binds_archive_version_and_deployment(tmp_path: Path) -> None:
    workflow, run_dir = _prepare_run(tmp_path, publication_provider="sites")
    receipt_path, _ = _record_sites_release(workflow, run_dir, tmp_path)

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["deployment_status"] == "succeeded"
    assert receipt["project_id"] == "site-project-123"
    assert workflow.validate_run(run_dir)["valid"] is True


def test_validate_run_rejects_changed_sites_archive(tmp_path: Path) -> None:
    workflow, run_dir = _prepare_run(tmp_path, publication_provider="sites")
    _, archive_path = _record_sites_release(workflow, run_dir, tmp_path)
    archive_path.write_bytes(archive_path.read_bytes() + b"changed")

    result = workflow.validate_run(run_dir)

    assert result["valid"] is False
    assert any("archive hash is stale" in issue for issue in result["issues"])


def test_release_rejects_preview_robots_directives(tmp_path: Path) -> None:
    workflow, run_dir = _prepare_run(tmp_path, noindex=True)
    _accept_release_reviews(workflow, run_dir)

    with pytest.raises(ValueError, match="remove preview robots directives"):
        workflow.package_website(run_dir, kind="release")


@pytest.mark.parametrize(
    ("markup", "expected"),
    [
        (
            '<form action="https://forms.example.test/collect"></form>',
            "form is outside",
        ),
        (
            '<iframe src="https://video.example.test/embed"></iframe>',
            "iframe is outside",
        ),
        (
            '<script src="data:text/javascript,document.body.dataset.bad=1"></script>',
            "unsafe data reference",
        ),
        (
            '<script src="https://cdn.example.test/runtime.js"></script>',
            "external active script",
        ),
    ],
)
def test_validate_site_blocks_out_of_scope_active_content(
    tmp_path: Path,
    markup: str,
    expected: str,
) -> None:
    workflow, run_dir = _prepare_run(tmp_path)
    index_path = run_dir / "work/site/index.html"
    index_path.write_text(
        index_path.read_text(encoding="utf-8").replace("</body>", markup + "</body>"),
        encoding="utf-8",
    )

    report = json.loads(workflow.validate_site(run_dir).read_text(encoding="utf-8"))

    assert report["status"] == "blocked"
    assert any(expected in issue for issue in report["errors"])


def test_validate_site_warns_but_allows_passive_https_image(tmp_path: Path) -> None:
    workflow, run_dir = _prepare_run(tmp_path)
    index_path = run_dir / "work/site/index.html"
    index_path.write_text(
        index_path.read_text(encoding="utf-8").replace(
            "</body>",
            '<img src="https://images.example.test/team.jpg" alt="Team"></body>',
        ),
        encoding="utf-8",
    )

    report = json.loads(workflow.validate_site(run_dir).read_text(encoding="utf-8"))

    assert report["status"] == "ready"
    assert any("external asset reference" in warning for warning in report["warnings"])


def test_quality_assessment_rejects_missing_screenshot(tmp_path: Path) -> None:
    workflow, run_dir = _prepare_run(tmp_path)
    validation = json.loads(
        (run_dir / "site_validation.json").read_text(encoding="utf-8")
    )
    assessment = _quality_assessment(validation, run_dir)
    (run_dir / assessment["viewports"][1]["screenshot_path"]).unlink()

    with pytest.raises(ValueError, match="screenshot is missing"):
        workflow.record_quality_assessment(
            run_dir,
            _write_json(tmp_path / "missing-screenshot.json", assessment),
            provider="test-provider",
            model="test-model",
            recorded_by="test-operator",
        )


def test_quality_assessment_rejects_wrong_screenshot_dimensions(tmp_path: Path) -> None:
    workflow, run_dir = _prepare_run(tmp_path)
    validation = json.loads(
        (run_dir / "site_validation.json").read_text(encoding="utf-8")
    )
    assessment = _quality_assessment(validation, run_dir)
    phone = assessment["viewports"][1]
    phone["screenshot_sha256"] = _write_viewport_screenshot(
        run_dir,
        phone["screenshot_path"],
        width=320,
        height=844,
    )

    with pytest.raises(ValueError, match="dimensions do not cover"):
        workflow.record_quality_assessment(
            run_dir,
            _write_json(tmp_path / "wrong-dimensions.json", assessment),
            provider="test-provider",
            model="test-model",
            recorded_by="test-operator",
        )


def test_first_site_can_prepare_from_confirmed_chat_fact(tmp_path: Path) -> None:
    workflow = _load_workflow_core()
    workspace = tmp_path / "workspace"
    workflow.initialize_workspace(
        workspace,
        workspace_id="studio-example",
        owner="Studio Esempio",
        retention_owner="Studio Esempio",
    )
    source_path = tmp_path / "unused.txt"
    source_path.write_text("unused", encoding="utf-8")
    intake = _intake(source_path=source_path)
    intake["selected_files"] = []
    intake["confirmed_facts"] = [
        {
            "id": "confirmed-qualification",
            "statement": "Sono iscritto all'Ordine dei Dottori Commercialisti.",
            "confirmed_by": "Studio Esempio",
            "confirmed_by_user": True,
        }
    ]

    run_dir = workflow.prepare_run(
        workspace,
        _write_json(tmp_path / "confirmed-intake.json", intake),
    )

    register = json.loads(
        (run_dir / "source_register.json").read_text(encoding="utf-8")
    )
    assert register["sources"][0]["origin"] == "confirmed_chat"
    assert register["sources"][0]["role"] == "confirmed_chat_fact"


def test_refresh_accepts_unknown_platform_with_public_url(tmp_path: Path) -> None:
    workflow = _load_workflow_core()
    source_path = tmp_path / "site-snapshot.html"
    source_path.write_text("<h1>Studio</h1>", encoding="utf-8")
    intake = _intake(source_path=source_path)
    intake["mode"] = "refresh"
    intake["existing_site"] = {
        "url": "https://studio.example.test/",
        "platform": None,
    }
    workspace = tmp_path / "workspace"
    workflow.initialize_workspace(
        workspace,
        workspace_id="studio-example",
        owner="Studio Esempio",
        retention_owner="Studio Esempio",
    )

    run_dir = workflow.prepare_run(
        workspace,
        _write_json(tmp_path / "refresh-intake.json", intake),
    )

    assert run_dir.is_dir()


def test_initialize_workspace_rejects_nonempty_unmanaged_directory(
    tmp_path: Path,
) -> None:
    workflow = _load_workflow_core()
    workspace = tmp_path / "existing-folder"
    workspace.mkdir()
    (workspace / "unrelated.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="must be empty or already initialized"):
        workflow.initialize_workspace(
            workspace,
            workspace_id="studio-example",
            owner="Studio Esempio",
            retention_owner="Studio Esempio",
        )


def test_repackaging_current_release_preserves_published_status(tmp_path: Path) -> None:
    workflow, run_dir = _prepare_run(tmp_path)
    _accept_release_reviews(workflow, run_dir)
    workflow.package_website(run_dir, kind="release")
    workflow.record_external_delivery(
        run_dir,
        kind="release",
        destination=FINAL_DESTINATION,
        visible_receipt=FINAL_DESTINATION,
        confirmed_by="Studio Esempio",
    )

    workflow.package_website(run_dir, kind="release")

    state = json.loads((run_dir / "run_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "published"
    assert workflow.validate_run(run_dir)["status"] == "published"


def test_sites_delivery_rejects_archive_without_approved_site_payload(
    tmp_path: Path,
) -> None:
    workflow, run_dir = _prepare_run(tmp_path, publication_provider="sites")
    _record_sites_release(workflow, run_dir, tmp_path)
    supplied_path = tmp_path / "sites-delivery.json"
    supplied = json.loads(supplied_path.read_text(encoding="utf-8"))
    binding_path = run_dir / "work/sites-project/.openai/vera-release-binding.json"
    incomplete = tmp_path / "incomplete-sites.tar.gz"
    with tarfile.open(incomplete, "w:gz") as archive:
        archive.add(binding_path, arcname=supplied["binding_member"])
    supplied["archive_path"] = str(incomplete)
    supplied["archive_sha256"] = hashlib.sha256(incomplete.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="vera-site-package"):
        workflow.record_sites_delivery(
            run_dir,
            _write_json(tmp_path / "incomplete-delivery.json", supplied),
            confirmed_by="Studio Esempio",
        )


def test_sites_delivery_rejects_browser_review_for_another_url(tmp_path: Path) -> None:
    workflow, run_dir = _prepare_run(tmp_path, publication_provider="sites")
    _record_sites_release(workflow, run_dir, tmp_path)
    supplied = json.loads(
        (tmp_path / "sites-delivery.json").read_text(encoding="utf-8")
    )
    supplied["browser_review"]["reviewed_url"] = "https://other.example.test/"

    with pytest.raises(ValueError, match="not bound to this deployment"):
        workflow.record_sites_delivery(
            run_dir,
            _write_json(tmp_path / "wrong-browser-review.json", supplied),
            confirmed_by="Studio Esempio",
        )


@pytest.mark.parametrize("workspace", [Path("/"), Path.home()])
def test_initialize_workspace_rejects_broad_system_target(workspace: Path) -> None:
    workflow = _load_workflow_core()

    with pytest.raises(ValueError, match="filesystem root or home"):
        workflow.initialize_workspace(
            workspace,
            workspace_id="studio-example",
            owner="Studio Esempio",
            retention_owner="Studio Esempio",
        )


def test_initialize_workspace_rejects_file_target(tmp_path: Path) -> None:
    workflow = _load_workflow_core()
    workspace = tmp_path / "not-a-directory"
    workspace.write_text("content", encoding="utf-8")

    with pytest.raises(ValueError, match="directory, not a file"):
        workflow.initialize_workspace(
            workspace,
            workspace_id="studio-example",
            owner="Studio Esempio",
            retention_owner="Studio Esempio",
        )


def test_initialize_workspace_rejects_symlinked_target(tmp_path: Path) -> None:
    workflow = _load_workflow_core()
    target = tmp_path / "actual-workspace"
    target.mkdir()
    workspace = tmp_path / "workspace-link"
    workspace.symlink_to(target, target_is_directory=True)

    with pytest.raises(ValueError, match="must not contain a symlink"):
        workflow.initialize_workspace(
            workspace,
            workspace_id="studio-example",
            owner="Studio Esempio",
            retention_owner="Studio Esempio",
        )


def test_quality_assessment_rejects_stale_screenshot_hash(tmp_path: Path) -> None:
    workflow, run_dir = _prepare_run(tmp_path)
    validation = json.loads(
        (run_dir / "site_validation.json").read_text(encoding="utf-8")
    )
    assessment = _quality_assessment(validation, run_dir)
    assessment["viewports"][0]["screenshot_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="screenshot hash is stale"):
        workflow.record_quality_assessment(
            run_dir,
            _write_json(tmp_path / "stale-screenshot.json", assessment),
            provider="test-provider",
            model="test-model",
            recorded_by="test-operator",
        )


def test_prepare_run_rejects_duplicate_file_and_chat_fact_id(tmp_path: Path) -> None:
    workflow = _load_workflow_core()
    source_path = tmp_path / "facts.txt"
    source_path.write_text("Studio fact", encoding="utf-8")
    intake = _intake(source_path=source_path)
    intake["confirmed_facts"] = [
        {
            "id": "studio-facts",
            "statement": "Confirmed fact",
            "confirmed_by": "Studio Esempio",
            "confirmed_by_user": True,
        }
    ]
    workspace = tmp_path / "workspace"
    workflow.initialize_workspace(
        workspace,
        workspace_id="studio-example",
        owner="Studio Esempio",
        retention_owner="Studio Esempio",
    )

    with pytest.raises(ValueError, match="Evidence IDs must be unique"):
        workflow.prepare_run(
            workspace,
            _write_json(tmp_path / "duplicate-evidence.json", intake),
        )


def test_sites_delivery_rejects_archive_for_another_project(tmp_path: Path) -> None:
    workflow, run_dir = _prepare_run(tmp_path, publication_provider="sites")
    _record_sites_release(workflow, run_dir, tmp_path)
    supplied = json.loads(
        (tmp_path / "sites-delivery.json").read_text(encoding="utf-8")
    )
    archive_path = Path(supplied["archive_path"])
    replacement = tmp_path / "wrong-project-sites.tar.gz"
    with (
        tarfile.open(archive_path, "r:gz") as source,
        tarfile.open(replacement, "w:gz") as target,
    ):
        for member in source.getmembers():
            if member.name == "dist/.openai/hosting.json":
                continue
            handle = source.extractfile(member)
            assert handle is not None
            target.addfile(member, handle)
        wrong_hosting = _write_json(
            tmp_path / "wrong-hosting.json",
            {"project_id": "another-project"},
        )
        target.add(wrong_hosting, arcname="dist/.openai/hosting.json")
    supplied["archive_path"] = str(replacement)
    supplied["archive_sha256"] = hashlib.sha256(replacement.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="hosting project does not match"):
        workflow.record_sites_delivery(
            run_dir,
            _write_json(tmp_path / "wrong-project-delivery.json", supplied),
            confirmed_by="Studio Esempio",
        )


def test_initialize_workspace_is_idempotent_for_same_identity(tmp_path: Path) -> None:
    workflow = _load_workflow_core()
    workspace = tmp_path / "workspace"
    first_manifest = workflow.initialize_workspace(
        workspace,
        workspace_id="studio-example",
        owner="Studio Esempio",
        retention_owner="Studio Esempio",
    )

    second_manifest = workflow.initialize_workspace(
        workspace,
        workspace_id="studio-example",
        owner="Studio Esempio",
        retention_owner="Studio Esempio",
    )

    assert second_manifest == first_manifest


def test_initialize_workspace_rejects_changed_identity(tmp_path: Path) -> None:
    workflow = _load_workflow_core()
    workspace = tmp_path / "workspace"
    workflow.initialize_workspace(
        workspace,
        workspace_id="studio-example",
        owner="Studio Esempio",
        retention_owner="Studio Esempio",
    )

    with pytest.raises(ValueError, match="identity mismatch for owner"):
        workflow.initialize_workspace(
            workspace,
            workspace_id="studio-example",
            owner="Altro Studio",
            retention_owner="Studio Esempio",
        )


def test_prepare_run_rejects_uninitialized_workspace(tmp_path: Path) -> None:
    workflow = _load_workflow_core()
    source_path = tmp_path / "facts.txt"
    source_path.write_text("Studio fact", encoding="utf-8")
    intake_path = _write_json(
        tmp_path / "intake.json", _intake(source_path=source_path)
    )

    with pytest.raises(ValueError, match="Workspace is not initialized"):
        workflow.prepare_run(tmp_path / "missing-workspace", intake_path)


def test_record_site_brief_rejects_malformed_source_register(tmp_path: Path) -> None:
    workflow, run_dir = _prepare_run(tmp_path)
    _write_json(run_dir / "source_register.json", {"schema_version": 1})

    with pytest.raises(ValueError, match="Invalid source register"):
        workflow.record_site_brief(
            run_dir,
            _write_json(tmp_path / "brief.json", _valid_brief()),
            provider="test-provider",
            model="test-model",
            recorded_by="test-operator",
        )


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("role", "studio_material", "Confirmed fact role changed"),
        ("origin", "selected_file", "Confirmed fact origin changed"),
        ("original_path", "/tmp/unexpected", "unexpected source path"),
    ],
)
def test_record_site_brief_rejects_changed_confirmed_fact_provenance(
    tmp_path: Path,
    field: str,
    value: str,
    expected: str,
) -> None:
    workflow = _load_workflow_core()
    workspace = tmp_path / "workspace"
    workflow.initialize_workspace(
        workspace,
        workspace_id="studio-example",
        owner="Studio Esempio",
        retention_owner="Studio Esempio",
    )
    source_path = tmp_path / "unused.txt"
    source_path.write_text("unused", encoding="utf-8")
    intake = _intake(source_path=source_path)
    intake["selected_files"] = []
    intake["confirmed_facts"] = [
        {
            "id": "confirmed-qualification",
            "statement": "Sono iscritto all'Ordine dei Dottori Commercialisti.",
            "confirmed_by": "Studio Esempio",
            "confirmed_by_user": True,
        }
    ]
    run_dir = workflow.prepare_run(
        workspace,
        _write_json(tmp_path / "confirmed-intake.json", intake),
    )
    register_path = run_dir / "source_register.json"
    register = json.loads(register_path.read_text(encoding="utf-8"))
    register["sources"][0][field] = value
    _write_json(register_path, register)

    with pytest.raises(ValueError, match=expected):
        workflow.record_site_brief(
            run_dir,
            _write_json(
                tmp_path / "confirmed-brief.json",
                _valid_brief(source_id="confirmed-qualification"),
            ),
            provider="test-provider",
            model="test-model",
            recorded_by="test-operator",
        )
