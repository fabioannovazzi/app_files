from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
COMM = ROOT / "plugins/comunicazione-professionale/scripts"
REPORT = ROOT / "plugins/report-builder"


def _helpers(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(
        name, ROOT / f"tests/plugins/{name}.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _command(
    script: str, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(COMM / script), *args],
        text=True,
        capture_output=True,
        check=check,
    )


def _preview(review: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "plugins/vera/scripts/studio_document_format.py"),
            "preview",
            "--review-dir",
            str(review),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _json(path: Path, payload: Any) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _studio(
    tmp_path: Path, *, name: str = "Studio Alpha", serif: bool = False
) -> tuple[Path, dict[str, Any]]:
    helper = _helpers("test_comunicazione_professionale")
    workspace = tmp_path / name.replace(" ", "-")
    _command(
        "initialize_workspace.py",
        "--workspace",
        str(workspace),
        "--workspace-id",
        workspace.name,
        "--owner",
        "Synthetic reviewer",
        "--retention-owner",
        "Synthetic reviewer",
        "--confirmed-by-user",
    )
    logo = tmp_path / f"{workspace.name}.png"
    Image.new("RGB", (240, 80), "#152f52" if not serif else "#5c302b").save(logo)
    brand = helper._brand()
    brand.update(studio_name=name, logo_path=str(logo))
    base = _json(
        tmp_path / f"{workspace.name}-base.json",
        {"brand_profile": brand, "profile": helper._new_studio_profile()},
    )
    settings = {
        "font_family": "Times New Roman" if serif else "Arial",
        "body_font_size_pt": 12 if serif else 10,
        "line_spacing_pt": 16 if serif else 13,
        "paragraph_after_pt": 10 if serif else 5,
        "heading_1_size_pt": 22 if serif else 16,
        "heading_2_size_pt": 15 if serif else 12,
        "heading_color": "5C302B" if serif else "152F52",
        "header_text": name,
        "footer_text": f"{name} - document review",
        "page_numbers": True,
        "use_logo": True,
        "table_header_fill": "5C302B" if serif else "152F52",
        "table_header_color": "FFFFFF",
        "table_alternate_fill": "F5EEEA" if serif else "EFF4FA",
        "number_format": "decimal_point" if serif else "decimal_comma",
        "date_format": "mdy" if serif else "dmy",
        "signature_lines": [name, "Accountancy team"],
    }
    preference = _json(tmp_path / f"{workspace.name}-settings.json", settings)
    sample = tmp_path / f"{workspace.name}-sample.docx"
    document = Document()
    document.add_heading(name, level=1)
    document.add_paragraph("Representative style example with synthetic text.")
    document.save(sample)
    _command(
        "review_document_format.py",
        "prepare",
        "--workspace",
        str(workspace),
        "--review-id",
        "format-review-001",
        "--settings",
        str(preference),
        "--sample",
        str(sample),
        "--base-profile",
        str(base),
    )
    review = workspace / "runs/format-review-001"
    _preview(review)
    payload = json.loads((review / "format_review.json").read_text())
    denied = _command(
        "review_document_format.py",
        "approve",
        "--review-dir",
        str(review),
        "--review-digest",
        payload["review_digest"],
        "--reviewer",
        "Synthetic reviewer",
        check=False,
    )
    assert denied.returncode != 0
    assert not (workspace / "studio_profile.json").exists()
    _command(
        "review_document_format.py",
        "approve",
        "--review-dir",
        str(review),
        "--review-digest",
        payload["review_digest"],
        "--reviewer",
        "Synthetic reviewer",
        "--confirmed-by-user",
    )
    core = _helpers("test_report_builder_plugin").load_core()
    return workspace, core.load_studio_format(
        workspace, studio_id=workspace.name, studio_name=name
    )


def test_two_studio_profiles_reuse_approved_assets_without_mixing(
    tmp_path: Path,
) -> None:
    alpha, alpha_format = _studio(tmp_path)
    beta, beta_format = _studio(tmp_path, name="Studio Beta", serif=True)
    core = _helpers("test_report_builder_plugin").load_core()
    assert (
        core.load_studio_format(
            alpha, studio_id="Studio-Alpha", studio_name="Studio Alpha"
        )
        == alpha_format
    )
    assert alpha_format["settings"]["font_family"] == "Arial"
    assert beta_format["settings"]["font_family"] == "Times New Roman"
    assert alpha_format["logo_base64"] != beta_format["logo_base64"]
    assert "samples" not in alpha_format and "profile" not in alpha_format
    with pytest.raises(ValueError, match="identity"):
        core.load_studio_format(
            beta, studio_id="Studio-Alpha", studio_name="Studio Alpha"
        )


@pytest.mark.parametrize("target", ["profile", "logo"])
def test_studio_profile_rejects_changed_approved_content(
    tmp_path: Path, target: str
) -> None:
    workspace, _ = _studio(tmp_path)
    path = workspace / "studio_profile.json"
    payload = json.loads(path.read_text())
    if target == "profile":
        payload["profile"]["document"]["docx"]["header_text"] = "Another studio"
        _json(path, payload)
    else:
        (
            workspace / payload["brand_assets"]["logo"]["workspace_relative_path"]
        ).write_bytes(b"changed")
    core = _helpers("test_report_builder_plugin").load_core()
    with pytest.raises(ValueError, match="digest|changed"):
        core.load_studio_format(
            workspace, studio_id="Studio-Alpha", studio_name="Studio Alpha"
        )


def test_profile_revision_archives_previous_standard_and_preserves_communications(
    tmp_path: Path,
) -> None:
    workspace, _ = _studio(tmp_path)
    before = json.loads((workspace / "studio_profile.json").read_text())
    settings = _json(
        tmp_path / "revision.json", {"font_family": "Arial", "paragraph_after_pt": 12}
    )
    _command(
        "review_document_format.py",
        "prepare",
        "--workspace",
        str(workspace),
        "--review-id",
        "format-review-002",
        "--settings",
        str(settings),
    )
    review = workspace / "runs/format-review-002"
    _preview(review)
    digest = json.loads((review / "format_review.json").read_text())["review_digest"]
    _command(
        "review_document_format.py",
        "approve",
        "--review-dir",
        str(review),
        "--review-digest",
        digest,
        "--reviewer",
        "Synthetic",
        "--confirmed-by-user",
    )
    after = json.loads((workspace / "studio_profile.json").read_text())
    assert after["version"] == 2
    assert (
        json.loads((workspace / "profiles/studio_profile-v001.json").read_text())
        == before
    )
    assert after["profile"]["email"] == before["profile"]["email"]
    assert (
        after["profile"]["document"]["docx"]["number_format"]
        == before["profile"]["document"]["docx"]["number_format"]
    )
    assert after["profile"]["document"]["docx"]["paragraph_after_pt"] == 12
    assert (
        after["profile"]["document"]["layout"]
        == before["profile"]["document"]["layout"]
    )


@pytest.mark.parametrize(
    "serif, expected_date", [(False, "01/10/2026"), (True, "10/01/2026")]
)
def test_docx_format_changes_presentation_and_preserves_exact_financial_closure(
    tmp_path: Path, serif: bool, expected_date: str
) -> None:
    workspace, profile = _studio(
        tmp_path, name="Studio Beta" if serif else "Studio Alpha", serif=serif
    )
    helper = _helpers("test_report_builder_plugin")
    core, output = helper._build_reviewed_detail_report(tmp_path)
    analysis = core.read_json(output / "report_analysis.json")
    before_ledger = core.read_json(output / "numeric_evidence_ledger.json")
    recipe = core.read_json(output / "used_recipe.json")
    recipe["studio_format"] = profile
    recipe["report_date"] = "2026-10-01"
    recipe["executive_summary"] = (
        "A longer reviewed narrative exercises wrapping without changing financial evidence. "
        * 40
    )
    core.write_json(output / "used_recipe.json", recipe)
    core.write_report_docx(
        recipe,
        analysis,
        core.read_json(output / "report_audit.json"),
        output / "report.docx",
    )
    ledger = core.write_numeric_evidence_ledger(output, analysis)
    document = Document(output / "report.docx")
    assert ledger["entries"] == before_ledger["entries"]
    assert core.read_json(output / "report_analysis.json") == analysis
    assert document.styles["Normal"].font.name == profile["settings"]["font_family"]
    assert (
        document.sections[0].header.paragraphs[0].text.endswith(profile["studio_name"])
    )
    assert "PAGE" in document.sections[0].footer._element.xml
    assert len(document.sections) == 2
    assert document.sections[1].header.is_linked_to_previous
    assert document.tables[2].rows[0]._tr.xpath("./w:trPr/w:tblHeader")
    assert document.tables[2].rows[1]._tr.xpath("./w:trPr/w:cantSplit")
    assert not document.tables[2].rows[1]._tr.xpath("./w:trPr/w:trHeight")
    assert expected_date in [p.text for p in document.paragraphs]
    assert any(
        p.text == "\n".join(profile["settings"]["signature_lines"])
        for p in document.paragraphs
    )
    # Regeneration uses the frozen settings, even if the studio's current profile changes.
    (workspace / "studio_profile.json").unlink()
    replay = tmp_path / "regenerated.docx"
    core.write_report_docx(
        recipe, analysis, core.read_json(output / "report_audit.json"), replay
    )
    assert replay.read_bytes() == (output / "report.docx").read_bytes()


def test_shared_writer_rejects_omitted_word_standard_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, _ = _studio(tmp_path)
    profile_path = workspace / "studio_profile.json"
    before = profile_path.read_bytes()
    stored = json.loads(before)
    proposal = copy.deepcopy(stored["profile"])
    del proposal["document"]["docx"]
    monkeypatch.syspath_prepend(str(COMM))
    spec = importlib.util.spec_from_file_location(
        "studio_format_profile_writer", COMM / "promote_studio_profile.py"
    )
    assert spec and spec.loader
    writer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(writer)

    with writer.workflow_lock(workspace):
        with pytest.raises(ValueError, match="DOCX preferences are missing"):
            writer.persist_studio_profile(
                workspace,
                profile=proposal,
                brand_profile=stored["brand_profile"],
                workspace_id=workspace.name,
                logo=None,
                approved_from=stored["approved_from"],
            )

    assert profile_path.read_bytes() == before
    assert not (workspace / "profiles").exists()


def test_word_format_distinguishes_totals_from_five_column_text_preview(
    tmp_path: Path,
) -> None:
    _, profile = _studio(tmp_path)
    core = _helpers("test_report_builder_plugin").load_core()
    document = Document()
    core.add_numeric_totals_table(
        document,
        [
            {
                "column": "Revenue",
                "sum": "1234.50",
                "currency": "EUR",
                "unit": "currency",
                "scale": "1",
            }
        ],
    )
    preview = document.add_table(rows=2, cols=5)
    preview.cell(1, 1).text = "A source description, not a reviewed total"

    core.apply_studio_format(document, profile)

    assert (
        document.tables[0].cell(1, 1).paragraphs[0].alignment
        == WD_ALIGN_PARAGRAPH.RIGHT
    )
    assert preview.cell(1, 1).paragraphs[0].alignment != WD_ALIGN_PARAGRAPH.RIGHT


def test_docx_format_schema_matches_the_shared_profile_extension() -> None:
    communication = json.loads(
        (COMM.parent / "schemas/model_contribution.schema.json").read_text()
    )
    report = json.loads((REPORT / "assets/studio-docx-format.schema.json").read_text())
    assert communication["$defs"]["documentProfile"]["properties"]["docx"] == report


def test_format_adoption_rejects_changed_selected_example(tmp_path: Path) -> None:
    workspace, _ = _studio(tmp_path)
    settings = _json(
        tmp_path / "changed-evidence-settings.json", {"paragraph_after_pt": 8}
    )
    sample = tmp_path / "selected-example.txt"
    sample.write_text("Selected formatting evidence.", encoding="utf-8")
    _command(
        "review_document_format.py",
        "prepare",
        "--workspace",
        str(workspace),
        "--review-id",
        "format-review-002",
        "--settings",
        str(settings),
        "--sample",
        str(sample),
    )
    review = workspace / "runs/format-review-002"
    payload = json.loads((review / "format_review.json").read_text())
    Path(payload["samples"][0]["snapshot_path"]).write_text(
        "Changed evidence.", encoding="utf-8"
    )
    before = (workspace / "studio_profile.json").read_bytes()

    result = _command(
        "review_document_format.py",
        "approve",
        "--review-dir",
        str(review),
        "--review-digest",
        payload["review_digest"],
        "--reviewer",
        "Synthetic",
        "--confirmed-by-user",
        check=False,
    )

    assert result.returncode != 0
    assert "evidence changed" in result.stderr
    assert (workspace / "studio_profile.json").read_bytes() == before


def test_selected_format_survives_assured_native_review_regeneration(
    tmp_path: Path,
) -> None:
    workspace, profile = _studio(tmp_path)
    helper = _helpers("test_report_builder_plugin")
    source = tmp_path / "income_statement.csv"
    source.write_text("line,amount\nRevenue,1234.50\nCost,-234.50\n", encoding="utf-8")
    managed = helper._managed_report_run(tmp_path, source)
    core = managed["core"]
    output = managed["output_dir"]
    core.build_report(
        managed["source_path"],
        output,
        run_id=managed["run_id"],
        client_engagement=managed["context"],
        studio_workspace=workspace,
        studio_id=workspace.name,
        studio_name="Studio Alpha",
    )
    saved = core.read_json(output / "used_recipe.json")["studio_format"]
    assert saved == profile
    review = core.read_json(output / "review_payload.json")
    item = next(
        item
        for item in review["items"]
        if item["item_type"] == "report_section"
        and item["data"]["section"] == "income_statement"
    )
    response = helper._call_mcp_server(
        "tools/call",
        {
            "name": "apply_report_builder_decisions",
            "arguments": {
                "client_engagement": str(managed["context_path"]),
                "run_intake": core.read_json(output / "run_intake.json"),
                "review_payload": review,
                "final_artifacts": core.read_json(output / "final_artifacts.json"),
                "decisions": [
                    {
                        "item_id": item["id"],
                        "action": "edit",
                        "edit_value": "The reviewer confirmed this longer report narrative after inspecting the mapped source evidence.",
                        "reviewer_note": "Reviewed narrative",
                    }
                ],
                "decision_source": "pytest_studio_format",
                "reviewer": "Synthetic reviewer",
            },
        },
    )
    assert response["structuredContent"]["ok"] is True, response
    assert core.read_json(output / "used_recipe.json")["studio_format"] == saved
    assert Document(output / "report.docx").styles["Normal"].font.name == "Arial"
    assert (
        Document(output / "report.docx")
        .sections[0]
        .header.paragraphs[0]
        .text.endswith("Studio Alpha")
    )


def _native(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "plugins/vera/scripts/studio_document_format.py"),
            *args,
        ],
        check=check,
        text=True,
        capture_output=True,
    )


def test_raw_example_setup_requires_intact_previews_before_adoption(
    tmp_path: Path,
) -> None:
    """Exercise raw source → evidence → reviewed proposal → previews → standard."""
    material = tmp_path / "materials"
    _native(
        "practice-materials",
        "--spec",
        str(
            ROOT / "scripts/course_materials/inputs/studio-document-format/demo-en.json"
        ),
        "--output-dir",
        str(material),
    )
    example = material / "studio-example.docx"
    document = Document(example)
    assert round(document.sections[0].page_width.mm) == 210
    # No example text reaches the emitted structural packet.
    document.add_paragraph("CLIENT-CONTENT-SENTINEL-DO-NOT-COPY")
    document.save(example)
    evidence = tmp_path / "evidence.json"
    _native("inspect", "--sample", str(example), "--output", str(evidence))
    observed = json.loads(evidence.read_text())
    assert observed["samples"][0]["sections"][0]["margins_mm"]["left"] == pytest.approx(
        22, abs=0.02
    )
    assert "CLIENT-CONTENT-SENTINEL-DO-NOT-COPY" not in evidence.read_text()
    workspace = tmp_path / "studio"
    _command(
        "initialize_workspace.py",
        "--workspace",
        str(workspace),
        "--workspace-id",
        "Studio-Riva",
        "--owner",
        "Synthetic reviewer",
        "--retention-owner",
        "Synthetic reviewer",
        "--confirmed-by-user",
    )
    brand = _json(
        tmp_path / "brand.json",
        {
            **_helpers("test_comunicazione_professionale")._brand(),
            "studio_name": "Studio Riva",
        },
    )
    # This fixture records explicitly chosen preferences, not model interpretation evidence.
    settings = _json(
        tmp_path / "settings.json",
        {
            "font_family": "Arial",
            "body_font_size_pt": 10,
            "heading_1_size_pt": 16,
            "margins_mm": {"top": 30, "bottom": 22, "left": 22, "right": 22},
            "header_text": "Studio Riva",
            "page_numbers": True,
        },
    )
    _native(
        "prepare",
        "--workspace",
        str(workspace),
        "--review-id",
        "setup-001",
        "--settings",
        str(settings),
        "--sample",
        str(example),
        "--brand",
        str(brand),
    )
    review = workspace / "runs/setup-001"
    digest = json.loads((review / "format_review.json").read_text())["review_digest"]
    assert not (workspace / "studio_profile.json").exists()
    short = review / "preview-short.docx"
    short.write_bytes(short.read_bytes() + b"tamper")
    result = _native(
        "approve",
        "--review-dir",
        str(review),
        "--review-digest",
        digest,
        "--reviewer",
        "Synthetic reviewer",
        "--confirmed-by-user",
        check=False,
    )
    assert result.returncode != 0
    assert "preview changed" in result.stderr
    assert not (workspace / "studio_profile.json").exists()
    _native("preview", "--review-dir", str(review))
    _native(
        "approve",
        "--review-dir",
        str(review),
        "--review-digest",
        digest,
        "--reviewer",
        "Synthetic reviewer",
        "--confirmed-by-user",
    )
    core = _helpers("test_report_builder_plugin").load_core()
    saved = core.load_studio_format(
        workspace, studio_id="Studio-Riva", studio_name="Studio Riva"
    )
    assert saved["margins_mm"]["left"] == 22
    assert "CLIENT-CONTENT-SENTINEL-DO-NOT-COPY" not in json.dumps(saved)
    adopted = json.loads((workspace / "studio_profile.json").read_text())
    assert adopted["profile"]["document"]["layout"]["left_margin_mm"] == 20
    assert adopted["profile"]["derived_from_history_ids"] == []
    assert adopted["approved_from"]["review_event"]["preview_manifest_sha256"]


def test_adoption_requires_generated_previews_and_exact_review_digest(
    tmp_path: Path,
) -> None:
    workspace, _ = _studio(tmp_path)
    settings = _json(tmp_path / "settings.json", {"font_family": "Arial"})
    _command(
        "review_document_format.py",
        "prepare",
        "--workspace",
        str(workspace),
        "--review-id",
        "missing-previews",
        "--settings",
        str(settings),
    )
    review = workspace / "runs/missing-previews"
    digest = json.loads((review / "format_review.json").read_text())["review_digest"]
    before = (workspace / "studio_profile.json").read_bytes()
    result = _native(
        "approve",
        "--review-dir",
        str(review),
        "--review-digest",
        digest,
        "--reviewer",
        "Synthetic reviewer",
        "--confirmed-by-user",
        check=False,
    )
    assert result.returncode != 0
    assert "short and long previews" in result.stderr
    assert (workspace / "studio_profile.json").read_bytes() == before
    _native("preview", "--review-dir", str(review))
    manifest = json.loads((review / "preview_manifest.json").read_text())
    manifest["review_digest"] = "a-different-proposal"
    _json(review / "preview_manifest.json", manifest)
    result = _native(
        "approve",
        "--review-dir",
        str(review),
        "--review-digest",
        digest,
        "--reviewer",
        "Synthetic reviewer",
        "--confirmed-by-user",
        check=False,
    )
    assert result.returncode != 0
    assert "another format proposal" in result.stderr
    assert (workspace / "studio_profile.json").read_bytes() == before


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
def test_studio_course_has_distinct_raw_sources_and_real_generated_materials(
    tmp_path: Path, language: str
) -> None:
    from scripts.course_materials.build_catalog import _eligible, _source_records

    assert "studio-document-format" in _eligible("vera")
    source_paths = {
        record["repository_path"]
        for record in _source_records("vera", "studio-document-format")
    }
    assert "plugins/vera/skills/studio-document-format/SKILL.md" in source_paths
    assert (
        "plugins/comunicazione-professionale/scripts/studio_document_format.py"
        in source_paths
    )
    assert (
        "plugins/comunicazione-professionale/assets/studio-document-format/baseline-profile-en.json"
        in source_paths
    )
    assert "plugins/report-builder/scripts/studio_formatting.py" in source_paths
    for phase, studio in [("demo", "Studio Riva"), ("practice", "Studio Selva")]:
        folder = tmp_path / phase
        _native(
            "practice-materials",
            "--spec",
            str(
                ROOT
                / f"scripts/course_materials/inputs/studio-document-format/{phase}-{language}.json"
            ),
            "--output-dir",
            str(folder),
        )
        assert (
            Document(folder / "studio-example.docx")
            .sections[0]
            .header.paragraphs[0]
            .text
            == studio
        )
        assert (folder / "financial-source.csv").is_file()
    assert (tmp_path / "demo/financial-source.csv").read_bytes() != (
        tmp_path / "practice/financial-source.csv"
    ).read_bytes()


def test_course_reuse_creates_a_real_separate_financial_client_run(
    tmp_path: Path,
) -> None:
    output = tmp_path / "outputs"
    output.mkdir()
    workspace, _ = _studio(output, name="Studio Riva")
    material = output / "sources"
    _native(
        "practice-materials",
        "--spec",
        str(
            ROOT / "scripts/course_materials/inputs/studio-document-format/demo-en.json"
        ),
        "--output-dir",
        str(material),
    )
    descriptor = _json(
        tmp_path / "tutorial_case.json",
        {
            "tutorial": True,
            "local_only": True,
            "workflow_id": "studio-document-format",
            "directory": str(tmp_path),
            "output_dir": str(output),
        },
    )
    _native(
        "report-case",
        "--tutorial-case",
        str(descriptor),
        "--source",
        str(material / "financial-source.csv"),
        "--studio-workspace",
        str(workspace),
    )
    reuse = json.loads((tmp_path / "report_reuse_case.json").read_text())
    helper = _helpers("test_report_builder_plugin")
    core = helper.load_core()
    context_path = Path(reuse["client_engagement_path"])
    context = json.loads(context_path.read_text())
    assert context["workflow_id"] == "report-builder"
    assert not (workspace / "Vera/client.json").exists()
    assert Path(reuse["client_root"]).is_relative_to(output)
    sources = list(Path(reuse["input_dir"]).glob("**/*.csv"))
    assert len(sources) == 1
    inspected = core.inspect_inputs(
        sources[0],
        Path(reuse["output_dir"]) / "inspection",
        language="en",
        document_language="en",
    )
    table_id = inspected.inspection["tables"][0]["table_id"]
    recipe = inspected.suggested_recipe
    recipe.update(entity="Fictional course company", period="2026-09-01 to 2026-09-30")
    recipe["sections"]["income_statement"]["assigned_table"] = table_id
    recipe = core.review_numeric_measure_columns(
        inspected.inspection,
        recipe,
        section_key="income_statement",
        **helper._numeric_review_args(inspected.inspection, table_id, ["amount"]),
        reviewer_ref="synthetic.course-test",
        reviewed_on="2026-10-01",
        numeric_locale="en",
        currency="EUR",
        unit="currency",
        scale="1",
        parse_policy="strict_all_nonblank_v1",
    )
    recipe_path = Path(reuse["output_dir"]) / "recipe.json"
    core.write_json(recipe_path, recipe)
    core.build_report(
        sources[0],
        Path(reuse["output_dir"]) / "report",
        recipe_path=recipe_path,
        run_id=context["run_id"],
        client_engagement=context,
        studio_workspace=workspace,
        studio_id="Studio-Riva",
        studio_name="Studio Riva",
    )
    report = Path(reuse["output_dir"]) / "report"
    assert Document(report / "report.docx").styles["Normal"].font.name == "Arial"
    analysis = core.read_json(report / "report_analysis.json")
    assert analysis["sections"][1]["numeric_columns"][0]["sum"] == "14500"
    assert (
        core.read_json(report / "used_recipe.json")["studio_format"]["studio_id"]
        == "Studio-Riva"
    )
