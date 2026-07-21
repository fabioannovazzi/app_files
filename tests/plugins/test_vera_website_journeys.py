from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHARED_ROOT = ROOT / "static" / "shared"
VERA_INSTALL_URL = (
    "https://chatgpt.com/auth/login?next="
    "%2Fplugins%2Fplugins_6a57ac5ce65c8191ae7bd0a51160eb7d"
)
VERA_SITE_MODULES = {
    "client-intake",
    "client-onboarding",
    "journal-sampling",
    "check-entries",
    "journal-bank-reconciliation",
    "riconciliazione-partite",
    "concordato-plan-review",
    "previdenza-inps",
    "registro-imprese-sari",
    "report-builder",
    "prompt-optimizer",
    "deep-research-validator",
}
VERA_MODULE_PAGES = {
    module: SHARED_ROOT / module / "index.html" for module in VERA_SITE_MODULES
}
VERA_CORE_PAGES = (SHARED_ROOT / "vera" / "index.html", *VERA_MODULE_PAGES.values())
VERA_SCOPE_BY_MODULE = {
    "client-intake": "mixed",
    "client-onboarding": "italy",
    "journal-sampling": "core",
    "check-entries": "mixed",
    "journal-bank-reconciliation": "core",
    "riconciliazione-partite": "core",
    "report-builder": "mixed",
    "prompt-optimizer": "core",
    "deep-research-validator": "core",
    "concordato-plan-review": "italy",
    "previdenza-inps": "italy",
    "registro-imprese-sari": "italy",
}
VERA_RENDERED_VIDEO_IDENTITIES = {
    *(
        ("client-onboarding", edition, language)
        for edition in ("core", "italy")
        for language in ("it", "en", "fr", "de")
    ),
    *(("journal-sampling", "core", language) for language in ("it", "en", "fr", "de")),
    *(("check-entries", "core", language) for language in ("it", "en", "fr", "de")),
    *(
        ("check-entries", "italy-fatturapa", language)
        for language in ("en", "fr", "de")
    ),
}
VERA_CORE_VIDEO_FORBIDDEN_PHRASES = (
    "fatturapa",
    "d.lgs",
    "codice fiscale",
    "partita iva",
    "antiriciclaggio",
    "anti-money laundering",
    "anti-blanchiment",
    "geldwäsche",
    "ri 30",
    "rs 70",
    "italia",
    "italy",
    "italie",
    "italien",
)
VERA_PUBLIC_PAGES = (
    *VERA_CORE_PAGES,
    SHARED_ROOT / "client-intake" / "geneva.html",
    SHARED_ROOT / "client-intake" / "zurich.html",
    SHARED_ROOT / "client-intake" / "uk.html",
)
VERA_CONNECTED_JOURNEYS = (
    ("client-intake", "../client-onboarding/index.html?lang=it"),
    ("client-onboarding", "../client-intake/index.html?lang=it"),
    ("journal-sampling", "../check-entries/index.html?lang=it"),
    ("check-entries", "../journal-sampling/index.html?lang=it"),
    (
        "journal-bank-reconciliation",
        "../riconciliazione-partite/index.html?lang=it",
    ),
    (
        "riconciliazione-partite",
        "../journal-bank-reconciliation/index.html?lang=it",
    ),
    ("concordato-plan-review", "../previdenza-inps/index.html?lang=it"),
    ("concordato-plan-review", "../registro-imprese-sari/index.html?lang=it"),
    ("previdenza-inps", "../report-builder/index.html?lang=it"),
    ("registro-imprese-sari", "../prompt-optimizer/index.html?lang=it"),
    ("prompt-optimizer", "../deep-research-validator/index.html?lang=it"),
    ("deep-research-validator", "../prompt-optimizer/index.html?lang=it"),
    ("deep-research-validator", "../report-builder/index.html?lang=it"),
    ("report-builder", "../riconciliazione-partite/index.html?lang=it"),
    ("report-builder", "../concordato-plan-review/index.html?lang=it"),
    ("report-builder", "../deep-research-validator/index.html?lang=it"),
)
DISCARDED_PUBLIC_PHRASES = (
    "official openai listing",
    "openai marketplace",
    "installa vera dal marketplace",
    "install vera from the marketplace",
    "not signed in? chatgpt asks you to sign in, then opens vera's listing.",
    "does not log in to inps autonomously",
    "no credentials or submissions",
    "never receives credentials",
    "never request credentials in chat",
    "ready_to_file always remains false",
    "generare il dossier non significa accettare il cliente",
    "non sostituisce",
    "giudizio professionale",
    "il professionista decide",
    "professional judgment remains",
    "vera does not",
    "vera doesn't",
    "vera never",
    "vera non ",
    "ne remplace pas",
    "vera ne décide pas",
    "vera ne se connecte pas",
    "vera entscheidet nicht",
    "vera meldet sich nicht",
    "vera ersetzt nicht",
)


@pytest.mark.parametrize(
    "page_path",
    VERA_CORE_PAGES,
    ids=lambda path: path.parent.name,
)
def test_vera_core_pages_publish_consistent_multilingual_metadata(
    page_path: Path,
) -> None:
    page = page_path.read_text(encoding="utf-8")
    canonical_url = f"https://mparanza.com/{page_path.relative_to(ROOT).as_posix()}"

    assert re.search(
        r'<meta\b(?=[^>]*\bname="description")[^>]*\bcontent="[^"]+"',
        page,
    )
    assert f'<link rel="canonical" href="{canonical_url}">' in page
    assert f'<meta property="og:url" content="{canonical_url}">' in page
    for property_name in (
        "og:type",
        "og:site_name",
        "og:title",
        "og:description",
        "og:locale",
    ):
        assert re.search(
            rf'<meta\b(?=[^>]*\bproperty="{property_name}")[^>]*\bcontent="[^"]+"',
            page,
        ), property_name
    for language in ("it", "en", "fr", "de"):
        assert (
            f'<link rel="alternate" hreflang="{language}" '
            f'href="{canonical_url}?lang={language}">'
        ) in page
    assert f'<link rel="alternate" hreflang="x-default" href="{canonical_url}">' in page


@pytest.mark.parametrize(
    "page_path",
    tuple(VERA_MODULE_PAGES.values()),
    ids=lambda path: path.parent.name,
)
def test_vera_module_pages_present_an_outcome_led_connected_journey(
    page_path: Path,
) -> None:
    page = page_path.read_text(encoding="utf-8")
    prompt_nodes = re.findall(
        r'<code\b(?=[^>]*(?:id="prompt-example"|data-journey="prompt.text"))[^>]*>',
        page,
    )

    assert re.search(r'class="(?:journey-)?breadcrumb"', page)
    assert "Fornisci" in page
    assert "Vera prepara" in page
    assert "Ricevi" in page
    assert 'id="proof"' in page or 'id="result"' in page
    assert len(prompt_nodes) == 1
    assert "../vera/index.html?lang=it" in page
    assert VERA_INSTALL_URL in page


@pytest.mark.parametrize(
    ("module", "expected_link"),
    VERA_CONNECTED_JOURNEYS,
)
def test_vera_module_pages_link_the_intended_next_journey(
    module: str,
    expected_link: str,
) -> None:
    page = VERA_MODULE_PAGES[module].read_text(encoding="utf-8")

    assert f'href="{expected_link}"' in page


@pytest.mark.parametrize(
    "page_path",
    VERA_PUBLIC_PAGES,
    ids=lambda path: path.parent.name if path.name == "index.html" else path.stem,
)
def test_vera_public_pages_omit_discarded_defensive_and_marketplace_copy(
    page_path: Path,
) -> None:
    page = html.unescape(page_path.read_text(encoding="utf-8")).casefold()
    present_phrases = [phrase for phrase in DISCARDED_PUBLIC_PHRASES if phrase in page]

    assert present_phrases == []


@pytest.mark.parametrize(
    ("module", "render_call", "scenario_count"),
    (
        (
            "concordato-plan-review",
            'renderPairs("prompt-list", t.prompts.items)',
            3,
        ),
        (
            "journal-bank-reconciliation",
            'renderOutputList("prompt-list", t.prompts.items)',
            3,
        ),
        ("journal-sampling", 'setOutputList("prompt-list", data.prompts.items)', 3),
        (
            "riconciliazione-partite",
            'data.prompts.rows, ([title, copy])',
            5,
        ),
    ),
)
def test_vera_scenario_prompt_libraries_are_visible_and_localized(
    module: str,
    render_call: str,
    scenario_count: int,
) -> None:
    page = VERA_MODULE_PAGES[module].read_text(encoding="utf-8")
    prompt_list = re.search(r'<ul\b(?=[^>]*\bid="prompt-list")[^>]*>', page)
    prompt_blocks = re.findall(
        r"^        prompts: \{\n(.*?)^        \},$",
        page,
        flags=re.MULTILINE | re.DOTALL,
    )

    assert prompt_list is not None
    assert "hidden" not in prompt_list.group(0)
    assert render_call in page
    assert len(prompt_blocks) == 4
    for prompt_block in prompt_blocks:
        assert prompt_block.count("\n            [") == scenario_count


def test_report_builder_publishes_three_localized_scenario_prompts() -> None:
    page = VERA_MODULE_PAGES["report-builder"].read_text(encoding="utf-8")
    prompt_section = _section_markup(page, "prompts")

    assert prompt_section.count("<li>") == 3
    for item_number in range(1, 4):
        for field in ("title", "copy"):
            key = f"prompts.item{item_number}.{field}"
            assert f'data-i18n="{key}"' in prompt_section
            assert page.count(f'"{key}":') == 4


@pytest.mark.parametrize(
    ("module", "artifact_names", "translation_keys"),
    (
        (
            "previdenza-inps",
            (
                "extraction_report.json",
                "claims_review_normalized.json",
                "document_requests.md",
                "final_artifacts.json",
                "review_handoff.md",
            ),
            tuple(f"technical.item{item_number}" for item_number in range(7, 12)),
        ),
        (
            "registro-imprese-sari",
            (
                "local_evidence_inventory.json",
                "sari_question_draft.md",
                "document_checklist.md",
                "final_artifacts.json",
            ),
            tuple(f"technical.item{item_number}" for item_number in range(7, 11)),
        ),
    ),
)
def test_italy_workflows_publish_the_complete_artifact_inventory(
    module: str,
    artifact_names: tuple[str, ...],
    translation_keys: tuple[str, ...],
) -> None:
    page = VERA_MODULE_PAGES[module].read_text(encoding="utf-8")

    for artifact_name in artifact_names:
        assert f"<code>{artifact_name}</code>" in page
    for key in translation_keys:
        assert f'data-i18n="{key}"' in page
        assert page.count(f'"{key}":') == 4


def _section_markup(page: str, section_id: str) -> str:
    marker = f'id="{section_id}"'
    marker_index = page.index(marker)
    section_start = page.rfind("<section", 0, marker_index)
    section_end = page.index("</section>", marker_index) + len("</section>")
    return page[section_start:section_end]


def test_vera_hub_separates_core_workflows_from_the_italy_pack() -> None:
    page = (SHARED_ROOT / "vera" / "index.html").read_text(encoding="utf-8")
    core = _section_markup(page, "core")
    italy = _section_markup(page, "italia")

    assert core.count('class="module-row"') == 8
    assert italy.count('class="module-row"') == 7
    for expected_href in (
        "../client-intake/index.html#work",
        "../journal-sampling/index.html",
        "../check-entries/index.html#journey",
        "../journal-bank-reconciliation/index.html",
        "../riconciliazione-partite/index.html",
        "../report-builder/index.html",
        "../prompt-optimizer/index.html",
        "../deep-research-validator/index.html",
    ):
        assert f'href="{expected_href}"' in core
    for expected_href in (
        "../client-intake/index.html#market-selector",
        "../client-onboarding/index.html#italy-pack",
        "../check-entries/index.html#italy-adapter",
        "../report-builder/index.html#italy-preset",
        "../concordato-plan-review/index.html",
        "../previdenza-inps/index.html",
        "../registro-imprese-sari/index.html",
    ):
        assert f'href="{expected_href}"' in italy

    assert "FatturaPA" not in core
    assert "FatturaPA" in italy
    assert 'href="#core"' in page
    assert 'href="#italia"' in page
    assert page.index('id="core"') < page.index('id="italia"')
    assert page.index('id="italia"') < page.index('id="video"')


def test_vera_hub_localizes_every_visible_copy_key_in_all_four_languages() -> None:
    page = (SHARED_ROOT / "vera" / "index.html").read_text(encoding="utf-8")
    visible_keys = set(re.findall(r'data-i18n(?:-aria-label)?="([^"]+)"', page))

    assert visible_keys
    for key in visible_keys:
        assert page.count(f'"{key}":') == 4, key


def test_vera_hub_module_fragments_resolve_to_real_page_sections() -> None:
    hub_path = SHARED_ROOT / "vera" / "index.html"
    page = hub_path.read_text(encoding="utf-8")
    module_hrefs = re.findall(
        r'<a\b(?=[^>]*\bclass="module-row")(?=[^>]*\bdata-module-link)[^>]*'
        r'\bhref="([^"]+)"',
        page,
    )

    assert len(module_hrefs) == 15
    for href in module_hrefs:
        target = urlsplit(href)
        target_path = (hub_path.parent / target.path).resolve()
        assert target_path.is_relative_to(SHARED_ROOT.resolve())
        assert target_path.is_file(), href
        if target.fragment:
            target_page = target_path.read_text(encoding="utf-8")
            assert re.search(
                rf'\bid=["\']{re.escape(target.fragment)}["\']', target_page
            ), href


@pytest.mark.parametrize(
    ("module", "scope"),
    VERA_SCOPE_BY_MODULE.items(),
)
def test_vera_module_pages_publish_the_shared_scope_taxonomy(
    module: str,
    scope: str,
) -> None:
    page = VERA_MODULE_PAGES[module].read_text(encoding="utf-8")
    scope_script = (SHARED_ROOT / "vera-scope.js").read_text(encoding="utf-8")

    assert f'data-vera-module="{module}"' in page
    assert f'data-vera-scope="{scope}"' in page
    assert re.search(r'href="\.\./vera-scope\.css\?v=[^"]+"', page)
    assert re.search(r'src="\.\./vera-scope\.js\?v=[^"]+"', page)
    assert f'"{module}": "{scope}"' in scope_script


@pytest.mark.parametrize(
    "module",
    (
        "client-onboarding",
        "concordato-plan-review",
        "previdenza-inps",
        "registro-imprese-sari",
    ),
)
def test_italy_scoped_pages_label_the_country_in_every_language(module: str) -> None:
    page = VERA_MODULE_PAGES[module].read_text(encoding="utf-8")

    assert 'data-vera-scope="italy"' in page
    for country_label in (
        "Pacchetto Italia",
        "Italy pack",
        "Pack Italie",
        "Italien-Paket",
    ):
        assert country_label in page


def test_client_intake_jurisdiction_and_presentation_language_are_independent() -> None:
    jurisdiction_root = SHARED_ROOT / "client-intake"
    jurisdiction_script = (jurisdiction_root / "jurisdiction-pages.js").read_text(
        encoding="utf-8"
    )
    page_defaults = {
        "geneva.html": ("geneva", "fr"),
        "zurich.html": ("zurich", "de"),
        "uk.html": ("uk", "en"),
    }

    for filename, (jurisdiction, default_language) in page_defaults.items():
        page = (jurisdiction_root / filename).read_text(encoding="utf-8")
        assert f'data-jurisdiction="{jurisdiction}"' in page
        assert f'data-presentation-language="{default_language}"' in page
        assert 'src="jurisdiction-pages.js?v=' in page
        for language in ("it", "en", "fr", "de"):
            assert f'hreflang="{language}"' in page
        assert f'slug: "{filename}"' in jurisdiction_script
        assert f'defaultLanguage: "{default_language}"' in jurisdiction_script

    assert 'const SUPPORTED_LANGUAGES = ["it", "en", "fr", "de"]' in (
        jurisdiction_script
    )
    assert "const page = jurisdictions[document.body.dataset.jurisdiction]" in (
        jurisdiction_script
    )
    assert 'url.searchParams.set("lang", language)' in jurisdiction_script
    assert "document.body.dataset.presentationLanguage = language" in (
        jurisdiction_script
    )
    assert "const copy = page.copy[language]" in jurisdiction_script
    assert "dataset.jurisdiction =" not in jurisdiction_script
    assert "window.location.replace" not in jurisdiction_script


def test_vera_hub_uses_the_central_curated_video_catalog() -> None:
    page = (SHARED_ROOT / "vera" / "index.html").read_text(encoding="utf-8")

    assert 'src="../video-library.js?v=2026072002"' in page
    assert 'window.MparanzaVideos.getCatalog("vera", lang)' in page
    assert (
        'const curatedVideoModules = ["client-intake", '
        '"journal-bank-reconciliation", "report-builder", "prompt-optimizer"]'
    ) in page
    assert page.count("data-video-index=") == 4
    assert page.count('class="overview-video"') == 1


def test_vera_video_catalog_v3_separates_edition_language_and_jurisdiction() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required to execute the browser video catalog")
    script = r"""
const fs = require("node:fs");
global.window = {};
eval(fs.readFileSync(process.argv[1], "utf8"));
const catalogs = ["it", "en", "fr", "de"].map((language) =>
  window.MparanzaVideos.getCatalog("vera", language)
);
process.stdout.write(JSON.stringify(catalogs));
"""

    result = subprocess.run(
        [node, "-e", script, str(SHARED_ROOT / "video-library.js")],
        check=True,
        capture_output=True,
        text=True,
    )
    catalogs = json.loads(result.stdout)
    required_video_fields = {
        "title",
        "sourceKind",
        "module",
        "edition",
        "scope",
        "jurisdiction",
        "moduleLabel",
        "workstream",
        "kind",
        "language",
        "shortTitle",
        "description",
        "duration",
        "pageTargets",
        "captions",
        "lastVerifiedAt",
        "status",
    }
    rendered_identities: set[tuple[str, str, str]] = set()
    manifest = json.loads(
        (SHARED_ROOT / "video-production" / "rendered" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    manifest_by_identity = {
        (asset["module"], asset["edition"], asset["language"]): asset
        for asset in manifest["assets"]
    }

    assert [catalog["language"] for catalog in catalogs] == ["it", "en", "fr", "de"]
    for catalog in catalogs:
        language = catalog["language"]
        published_modules = {video["module"] for video in catalog["videos"]}

        assert catalog["version"] == "3.0.0"
        assert catalog["featured"]["kind"] == "overview"
        assert catalog["featured"]["language"] == language
        assert catalog["featured"]["edition"] == "core"
        assert catalog["featured"]["scope"] == "core"
        assert catalog["featured"]["jurisdiction"] is None
        assert VERA_SITE_MODULES <= published_modules
        assert catalog["pending"] == []
        for video in catalog["videos"]:
            assert required_video_fields <= video.keys()
            assert video["language"] == language
            assert video["pageTargets"]
            assert video["captions"]["status"] in {"available", "pending"}
            if video["scope"] == "core":
                assert video["edition"] == "core"
                assert video["jurisdiction"] is None
            elif video["jurisdiction"] == "IT":
                assert video["scope"] == "country"
                assert video["edition"] in {"italy", "italy-fatturapa"}
            else:
                assert video["scope"] == "country"
                assert video["edition"] == "country-aware"
                assert video["jurisdiction"] is None
                assert video["jurisdictions"] == ["IT", "CH-GE", "CH-ZH", "UK"]
            if video["sourceKind"] == "local":
                identity = (video["module"], video["edition"], language)
                rendered_identities.add(identity)
                assert "id" not in video
                assert video["status"] == "local_rendered"
                assert video["src"].startswith(
                    "/static/shared/video-production/rendered/"
                )
                assert video["poster"].startswith(
                    "/static/shared/video-production/rendered/"
                )
                assert video["captions"]["status"] == "available"
                assert video["captions"]["language"] == language

                asset = manifest_by_identity[identity]
                public_prefix = "/static/shared/video-production/rendered/"
                assert video["src"] == public_prefix + asset["files"]["video"]["path"]
                assert (
                    video["poster"] == public_prefix + asset["files"]["poster"]["path"]
                )
                assert (
                    video["captions"]["src"]
                    == public_prefix + asset["files"]["captions"]["path"]
                )
                assert (
                    video["captions"]["transcript"]
                    == public_prefix + asset["files"]["transcript"]["path"]
                )
                assert video["title"] == asset["title"]
                assert video["pageTargets"] == asset["pageTargets"]
                assert video["scope"] == asset["scope"]
                assert video["jurisdiction"] == asset["jurisdiction"]
            else:
                assert video["sourceKind"] == "youtube"
                assert video["status"] == "published"
                assert video["id"]

    assert rendered_identities == VERA_RENDERED_VIDEO_IDENTITIES
    italian_fatturapa = next(
        video
        for video in catalogs[0]["videos"]
        if video["module"] == "check-entries" and video["edition"] == "italy-fatturapa"
    )
    assert italian_fatturapa["sourceKind"] == "youtube"
    assert italian_fatturapa["id"] == "I1dp3FYVy2w"


def test_vera_missing_guide_pack_is_complete_and_rendered_locally() -> None:
    spec_path = SHARED_ROOT / "video-production" / "vera-missing-guides.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    concepts = spec["concepts"]

    assert spec["schemaVersion"] == "2.0.0"
    assert spec["identityModel"] == "module + edition + language"
    assert spec["publicationStatus"] == "local_rendered"
    assert spec["remotePublish"] is False
    assert spec["renderedManifest"] == "rendered/manifest.json"
    assert {(concept["module"], concept["edition"]) for concept in concepts} == {
        ("client-onboarding", "core"),
        ("client-onboarding", "italy"),
        ("journal-sampling", "core"),
        ("check-entries", "core"),
        ("check-entries", "italy-fatturapa"),
    }
    assert sum(len(concept["localizations"]) for concept in concepts) == 19
    for concept in concepts:
        assert len(concept["scenes"]) == 6
        assert concept["pageTargets"]
        if concept["scope"] == "core":
            assert concept["edition"] == "core"
            assert concept["jurisdiction"] is None
        else:
            assert concept["scope"] == "country"
            assert concept["jurisdiction"] == "IT"
        for localization in concept["localizations"].values():
            assert localization["title"]
            assert localization["narration"]
            assert len(localization["onScreen"]) == 6
            if concept["scope"] == "core":
                core_script = " ".join(
                    (
                        localization["title"],
                        localization["narration"],
                        *localization["onScreen"],
                    )
                ).casefold()
                for phrase in VERA_CORE_VIDEO_FORBIDDEN_PHRASES:
                    assert phrase not in core_script
                assert not re.search(r"\baml\b", core_script)

    check_entries = next(
        concept
        for concept in concepts
        if concept["module"] == "check-entries"
        and concept["edition"] == "italy-fatturapa"
    )
    existing = check_entries["existingLocalization"]
    assert existing["sourceKind"] == "youtube"
    assert existing["language"] == "it"
    assert existing["edition"] == "italy-fatturapa"
    assert existing["scope"] == "country"
    assert existing["jurisdiction"] == "IT"
    assert existing["youtubeId"] == "I1dp3FYVy2w"


def test_vera_rendered_guide_manifest_is_complete_and_local() -> None:
    manifest_path = SHARED_ROOT / "video-production" / "rendered" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rendered_root = manifest_path.parent.resolve()
    assets = manifest["assets"]

    assert manifest["schemaVersion"] == "2.0.0"
    assert manifest["publicationStatus"] == "local_rendered"
    assert manifest["remotePublish"] is False
    assert manifest["assetCount"] == 19
    assert len(assets) == 19
    assert {
        (asset["module"], asset["edition"], asset["language"]) for asset in assets
    } == (VERA_RENDERED_VIDEO_IDENTITIES)

    for asset in assets:
        assert asset["status"] == "local_rendered"
        if asset["scope"] == "core":
            assert asset["edition"] == "core"
            assert asset["jurisdiction"] is None
        else:
            assert asset["scope"] == "country"
            assert asset["jurisdiction"] == "IT"
        assert asset["cueCount"] == 6
        assert asset["media"]["videoCodec"] == "h264"
        assert asset["media"]["audioCodec"] == "aac"
        assert asset["media"]["width"] == 1280
        assert asset["media"]["height"] == 720
        assert asset["media"]["frameRate"] == "30/1"
        assert asset["media"]["durationSeconds"] == asset["targetDurationSeconds"]
        assert set(asset["files"]) == {
            "video",
            "poster",
            "captions",
            "transcript",
        }

        for file_record in asset["files"].values():
            assert file_record["path"].startswith(
                f'{asset["module"]}/{asset["edition"]}/{asset["language"]}/'
            )
            artifact = (manifest_path.parent / file_record["path"]).resolve()
            assert artifact.is_relative_to(rendered_root)
            assert artifact.is_file()
            assert artifact.stat().st_size == file_record["bytes"]
            assert (
                hashlib.sha256(artifact.read_bytes()).hexdigest()
                == file_record["sha256"]
            )

        video_path = manifest_path.parent / asset["files"]["video"]["path"]
        poster_path = manifest_path.parent / asset["files"]["poster"]["path"]
        captions_path = manifest_path.parent / asset["files"]["captions"]["path"]
        transcript_path = manifest_path.parent / asset["files"]["transcript"]["path"]
        assert video_path.read_bytes()[4:8] == b"ftyp"
        assert poster_path.read_bytes()[:2] == b"\xff\xd8"
        assert captions_path.read_text(encoding="utf-8").startswith("WEBVTT\n")
        assert " --> " in captions_path.read_text(encoding="utf-8")
        transcript = transcript_path.read_text(encoding="utf-8")
        assert asset["title"] in transcript
        if asset["scope"] == "core":
            normalized_transcript = transcript.casefold()
            for phrase in VERA_CORE_VIDEO_FORBIDDEN_PHRASES:
                assert phrase not in normalized_transcript
            assert not re.search(r"\baml\b", normalized_transcript)


def test_vera_rendered_guides_are_adopted_by_their_module_pages() -> None:
    onboarding = VERA_MODULE_PAGES["client-onboarding"].read_text(encoding="utf-8")
    sampling = VERA_MODULE_PAGES["journal-sampling"].read_text(encoding="utf-8")
    entries = VERA_MODULE_PAGES["check-entries"].read_text(encoding="utf-8")

    assert onboarding.count("<video") == 2
    assert 'id="core-video"' in onboarding
    assert 'id="proof-video"' in onboarding
    assert "/rendered/client-onboarding/core/it/guide.mp4" in onboarding
    assert "/rendered/client-onboarding/italy/it/guide.mp4" in onboarding
    assert (
        "`/static/shared/video-production/rendered/client-onboarding/core/${lang}`"
        in onboarding
    )
    assert (
        "`/static/shared/video-production/rendered/client-onboarding/italy/${lang}`"
        in onboarding
    )

    assert sampling.count("<video") == 1
    assert "/rendered/journal-sampling/core/it/guide.mp4" in sampling
    assert (
        "`/static/shared/video-production/rendered/journal-sampling/core/${language}`"
        in sampling
    )

    for provisional_copy in (
        "In preparazione",
        "In preparation",
        "En préparation",
        "In Vorbereitung",
        "proof.state",
    ):
        assert provisional_copy not in sampling

    assert entries.count("<video") == 2
    assert 'id="proof-core-video"' in entries
    assert 'id="proof-italy-video"' in entries
    assert "/rendered/check-entries/core/it/guide.mp4" in entries
    assert "/rendered/check-entries/italy-fatturapa/en/guide.mp4" in entries
    assert 'id="proof-italy-local" hidden' in entries
    assert "I1dp3FYVy2w" in entries
    assert 'id="proof-italy-youtube"' in entries
    assert (
        "`/static/shared/video-production/rendered/check-entries/core/${lang}`"
        in entries
    )
    assert (
        "`/static/shared/video-production/rendered/check-entries/italy-fatturapa/${lang}`"
        in entries
    )

    for page in (onboarding, sampling, entries):
        assert re.search(r"<video[^>]+controls[^>]+playsinline[^>]+preload=", page)
        assert 'kind="captions"' in page
