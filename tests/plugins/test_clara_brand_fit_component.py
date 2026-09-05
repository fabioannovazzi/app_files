from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLARA_ROOT = ROOT / "plugins" / "clara"
PUBLIC_BRAND_FIT_ROOT = (
    ROOT
    / "static"
    / "shared"
    / "attribute-reporting"
    / "brand-fit"
    / "guest-in-residence"
)
VERIFIED_PUBLIC_REPORT_SHA256 = (
    "775c5163fc850942c90034c5a5501e5252ebe6ec6534f25605e45017d7ba519c"
)
VERIFIED_PUBLIC_IMAGES = {
    "18050bde154e1ab2.jpg": (
        "18050bde154e1ab285ce023b998eed70503db0a3df0942c214dadcbef8ddc520"
    ),
    "33a23a6daefef765.jpg": (
        "33a23a6daefef76583fc3000569f7b23ff6299f87cafbf91ad71101e5f31873b"
    ),
    "7ed75e631e7ac915.jpg": (
        "7ed75e631e7ac915d8b3137e3008198c798d730d47c3d98ad704aadb5bf71b5a"
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_clara_brand_fit_wrapper_is_visible_and_delegates_to_attribute_component() -> (
    None
):
    skill_root = CLARA_ROOT / "skills" / "brand-fit"
    wrapper = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    metadata = (skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8")

    assert "name: brand-fit" in wrapper
    assert "../../modules/attribute-reporting" in wrapper
    assert "../../../attribute-reporting" in wrapper
    assert "skills/brand-fit/SKILL.md" in wrapper
    assert "check_dependencies.py --module attribute-reporting" in wrapper
    assert "stored database snapshot" in wrapper
    assert "live shelf" in wrapper
    assert "user's existing ChatGPT plan" in wrapper
    assert "no separate API" in wrapper
    assert (
        'display_name: "Compare the retailer assortment with the brand catalogue"'
        in metadata
    )
    assert "Use $brand-fit" in metadata


def test_clara_routes_brand_fit_separately_from_retailer_signals_and_charts() -> None:
    manifest = json.loads(
        (CLARA_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    fixtures = json.loads(
        (CLARA_ROOT / "evals" / "trigger_fixtures.json").read_text(encoding="utf-8")
    )
    router = (CLARA_ROOT / "skills" / "clara" / "SKILL.md").read_text(encoding="utf-8")
    catalog = (
        CLARA_ROOT / "skills" / "clara" / "references" / "workflow-catalog.md"
    ).read_text(encoding="utf-8")
    brand_fit_cases = {
        item["id"]: item
        for item in fixtures["should_trigger"]
        if item.get("expected_skill") == "clara:brand-fit"
    }

    assert manifest["name"] == "clara"
    assert manifest["interface"]["displayName"] == "Clara"
    assert manifest["interface"]["shortDescription"] == ("AI companion for consultants")
    assert "brand-fit" in manifest["keywords"]
    assert "references/workflow-catalog.md" in router
    assert "- `brand-fit`:" in catalog
    assert set(brand_fit_cases) == {
        "brand-fit-current-presence-and-owned-catalogue",
        "brand-fit-stored-snapshot-boundary",
    }
    for case in brand_fit_cases.values():
        assert set(case["must_not_route_to"]) == {
            "clara:attribute-reporting",
            "clara:reporting-engine",
            "clara:interview",
            "clara:transcribe",
            "clara:deck-correction",
        }


def test_clara_public_page_marks_brand_fit_available_with_honest_boundary() -> None:
    page = (ROOT / "static" / "shared" / "clara" / "index.html").read_text(
        encoding="utf-8"
    )
    function_copy = (
        ROOT / "static" / "shared" / "product-function-pages.js"
    ).read_text(encoding="utf-8")

    assert page.count('"functions.brandFit"') == 6
    assert 'data-i18n="functions.brandFit"' in page
    assert 'href="../clara-brand-fit/index.html?lang=en"' in page
    assert '"clara-brand-fit"' in function_copy
    assert "brand's presence at the retailer and the brand catalogue" in function_copy
    assert (
        "The comparison uses stored data and is not a live shelf check."
        in function_copy
    )


def test_public_brand_fit_example_preserves_checked_report_and_local_images() -> None:
    report = PUBLIC_BRAND_FIT_ROOT / "index.html"
    page = report.read_text(encoding="utf-8")

    assert _sha256(report) == VERIFIED_PUBLIC_REPORT_SHA256
    assert "Guest in Residence Brand Fit" in page
    assert 'data-report-id="brand-fit-e7e7f41d53c84bf3b39b9ec5523bcbbf"' in page
    assert 'data-correctness-verdict="correct_with_caveats"' in page
    assert "not proof that every owned product is absent from Saks" in page
    assert "/private/" not in page
    assert "file:" not in page

    image_root = PUBLIC_BRAND_FIT_ROOT / "assets" / "products"
    for name, expected_sha256 in VERIFIED_PUBLIC_IMAGES.items():
        image = image_root / name
        assert image.is_file()
        assert _sha256(image) == expected_sha256
        assert f"assets/products/{name}" in page


def test_brand_fit_docs_separate_installed_clara_from_legacy_builder() -> None:
    docs = (ROOT / "docs" / "brand_fit_packages.md").read_text(encoding="utf-8")
    install = (
        ROOT / "static" / "shared" / "clara" / "LEGGIMI_INSTALLAZIONE.txt"
    ).read_text(encoding="utf-8")

    assert "Installed Clara and legacy builder" in docs
    assert "local Retailer Signals HTML report is not uploaded" in docs
    assert "stored snapshot, not a claim" in docs
    assert "legacy repository builder" in docs
    assert "sending the package to Pro" not in docs
    assert "chatgpt.com/plugins/plugins_6a57b17fb5848191be710192d93fe03a" in install
    assert "Scarica lo ZIP" not in install
    assert "marketplace locale" not in install
