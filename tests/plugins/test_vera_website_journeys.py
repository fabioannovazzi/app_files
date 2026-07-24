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
VERA_PLUGIN_ROOT = ROOT / "plugins" / "vera"
VERA_SITE_MODULES = {
    "new-client",
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
VERA_CORE_PAGES = (
    SHARED_ROOT / "vera" / "index.html",
    *(
        VERA_MODULE_PAGES[module]
        for module in (
            "journal-sampling",
            "check-entries",
            "journal-bank-reconciliation",
            "riconciliazione-partite",
            "report-builder",
            "prompt-optimizer",
            "deep-research-validator",
        )
    ),
)
VERA_NATIVE_JURISDICTION_PAGES = {
    SHARED_ROOT / "new-client" / "index.html": "it",
    SHARED_ROOT / "concordato-plan-review" / "index.html": "it",
    SHARED_ROOT / "previdenza-inps" / "index.html": "it",
    SHARED_ROOT / "registro-imprese-sari" / "index.html": "it",
    SHARED_ROOT / "new-client" / "geneva.html": "fr",
    SHARED_ROOT / "new-client" / "zurich.html": "de",
    SHARED_ROOT / "new-client" / "uk.html": "en",
}
VERA_SCOPE_BY_MODULE = {
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
        ("studio-archive", "core", language)
        for language in ("it", "en", "fr", "de", "es")
    ),
    *(
        ("new-client", edition, language)
        for edition in ("core", "italy")
        for language in ("it", "en", "fr", "de", "es")
    ),
    *(
        ("journal-sampling", "core", language)
        for language in ("it", "en", "fr", "de", "es")
    ),
    *(
        ("check-entries", "core", language)
        for language in ("it", "en", "fr", "de", "es")
    ),
    *(
        ("check-entries", "italy-fatturapa", language)
        for language in ("en", "fr", "de", "es")
    ),
}
SHARED_DATA_HANDLING_VIDEO_IDENTITIES = {
    ("data-handling", "core", language) for language in ("it", "en", "fr", "de", "es")
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
    *VERA_NATIVE_JURISDICTION_PAGES,
)
VERA_CONNECTED_JOURNEYS = (
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
    ("report-builder", "../concordato-plan-review/index.html"),
    ("report-builder", "../deep-research-validator/index.html?lang=it"),
)


def _split_js_top_level(source: str) -> list[str]:
    """Split JavaScript object entries without splitting nested values."""

    chunks: list[str] = []
    start = 0
    depths = {"{": 0, "[": 0, "(": 0}
    closing = {"}": "{", "]": "[", ")": "("}
    quote = ""
    escaped = False
    line_comment = False
    block_comment = False
    index = 0
    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if line_comment:
            line_comment = char != "\n"
        elif block_comment:
            if char == "*" and following == "/":
                block_comment = False
                index += 1
        elif quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        elif char == "/" and following == "/":
            line_comment = True
            index += 1
        elif char == "/" and following == "*":
            block_comment = True
            index += 1
        elif char in {'"', "'", "`"}:
            quote = char
        elif char in depths:
            depths[char] += 1
        elif char in closing:
            depths[closing[char]] -= 1
        elif char == "," and not any(depths.values()):
            chunks.append(source[start:index])
            start = index + 1
        index += 1
    chunks.append(source[start:])
    return chunks


def _strip_leading_js_comments(source: str) -> str:
    """Remove comments that appear before one JavaScript object property."""

    value = source.lstrip()
    while value.startswith(("//", "/*")):
        if value.startswith("//"):
            newline = value.find("\n")
            return (
                "" if newline < 0 else _strip_leading_js_comments(value[newline + 1 :])
            )
        comment_end = value.find("*/", 2)
        return (
            ""
            if comment_end < 0
            else _strip_leading_js_comments(value[comment_end + 2 :])
        )
    return value


def _js_object_properties(literal: str) -> dict[str, str]:
    """Return the direct properties of a JavaScript object literal."""

    value = literal.strip()
    if not (value.startswith("{") and value.endswith("}")):
        return {}
    properties: dict[str, str] = {}
    property_pattern = re.compile(
        r'^(?:"([^"]+)"|\'([^\']+)\'|([A-Za-z_$][\w$]*))\s*:\s*'
    )
    for raw_entry in _split_js_top_level(value[1:-1]):
        entry = _strip_leading_js_comments(raw_entry)
        match = property_pattern.match(entry)
        if match is None:
            continue
        key = next(group for group in match.groups() if group is not None)
        properties[key] = entry[match.end() :].strip()
    return properties


def _js_object_key_paths(literal: str, prefix: str = "") -> set[str]:
    """Collect nested property paths from a JavaScript object literal."""

    paths: set[str] = set()
    for key, value in _js_object_properties(literal).items():
        path = f"{prefix}.{key}" if prefix else key
        paths.add(path)
        if value.startswith("{"):
            paths.update(_js_object_key_paths(value, path))
    return paths


def _find_js_object_end(source: str, start: int) -> int:
    """Find the closing brace for one JavaScript object literal."""

    depth = 0
    quote = ""
    escaped = False
    line_comment = False
    block_comment = False
    index = start
    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if line_comment:
            line_comment = char != "\n"
        elif block_comment:
            if char == "*" and following == "/":
                block_comment = False
                index += 1
        elif quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        elif char == "/" and following == "/":
            line_comment = True
            index += 1
        elif char == "/" and following == "*":
            block_comment = True
            index += 1
        elif char in {'"', "'", "`"}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise AssertionError("Unclosed JavaScript object literal")


def _js_named_object_literals(source: str) -> list[tuple[str, str]]:
    """Extract const-assigned JavaScript object literals from one HTML page."""

    literals: list[tuple[str, str]] = []
    pattern = re.compile(r"\bconst\s+([A-Za-z_$][\w$]*)\s*=\s*\{")
    for match in pattern.finditer(source):
        start = source.index("{", match.start())
        end = _find_js_object_end(source, start)
        literals.append((match.group(1), source[start : end + 1]))
    return literals


def _vtt_seconds(timestamp: str) -> float:
    """Convert one WebVTT timestamp to seconds."""

    hours, minutes, seconds = timestamp.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _read_vtt_cues(path: Path) -> list[tuple[float, float, str]]:
    """Read ordered cue timing and text from a generated WebVTT file."""

    blocks = path.read_text(encoding="utf-8").strip().split("\n\n")
    cues: list[tuple[float, float, str]] = []
    for block in blocks[1:]:
        _, timing, *text_lines = block.splitlines()
        start, end = timing.split(" --> ")
        cues.append((_vtt_seconds(start), _vtt_seconds(end), " ".join(text_lines)))
    return cues


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
    "vera doesn't",
    "vera never",
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
    for language in ("it", "en", "fr", "de", "es"):
        assert (
            f'<link rel="alternate" hreflang="{language}" '
            f'href="{canonical_url}?lang={language}">'
        ) in page
    assert f'<link rel="alternate" hreflang="x-default" href="{canonical_url}">' in page


@pytest.mark.parametrize(
    ("page_path", "native_language"),
    VERA_NATIVE_JURISDICTION_PAGES.items(),
    ids=[path.parent.name for path in VERA_NATIVE_JURISDICTION_PAGES],
)
def test_vera_jurisdiction_pages_publish_only_the_native_language(
    page_path: Path,
    native_language: str,
) -> None:
    page = page_path.read_text(encoding="utf-8")
    canonical_url = f"https://mparanza.com/{page_path.relative_to(ROOT).as_posix()}"

    assert f'<html lang="{native_language}">' in page
    assert (
        f'<link rel="alternate" hreflang="{native_language}" '
        f'href="{canonical_url}">'
    ) in page
    assert f'<link rel="alternate" hreflang="x-default" href="{canonical_url}">' in page
    assert set(re.findall(r'hreflang="([a-z-]+)"', page)) == {
        native_language,
        "x-default",
    }
    assert not re.search(r'data-lang="(?:it|en|fr|de|es)"', page)


def test_static_pages_with_spanish_selector_have_complete_locale_objects() -> None:
    expected_languages = {"it", "en", "fr", "de", "es"}
    localized_pages = 0

    for page_path in sorted(SHARED_ROOT.rglob("*.html")):
        page = page_path.read_text(encoding="utf-8")
        if 'data-lang="es"' not in page:
            continue

        localized_pages += 1
        page_label = page_path.relative_to(ROOT).as_posix()
        language_buttons = set(re.findall(r'data-lang="([a-z]{2})"', page))
        assert language_buttons == expected_languages, page_label
        assert 'hreflang="es"' in page, page_label

        locale_object_count = 0
        for object_name, literal in _js_named_object_literals(page):
            properties = _js_object_properties(literal)
            present_languages = language_buttons.intersection(properties)
            if len(present_languages) < 3:
                continue

            locale_object_count += 1
            assert language_buttons <= properties.keys(), (
                f"{page_label}: {object_name} is missing "
                f"{sorted(language_buttons.difference(properties))}"
            )
            localized_values = {
                language: properties[language].lstrip() for language in language_buttons
            }
            object_value_flags = {
                language: value.startswith("{")
                for language, value in localized_values.items()
            }
            assert (
                len(set(object_value_flags.values())) == 1
            ), f"{page_label}: {object_name} mixes locale value structures"
            if not all(object_value_flags.values()):
                continue

            signatures = {
                language: _js_object_key_paths(value)
                for language, value in localized_values.items()
            }
            reference_language = "it" if "it" in signatures else sorted(signatures)[0]
            reference = signatures[reference_language]
            for language, signature in signatures.items():
                assert signature == reference, (
                    f"{page_label}: {object_name}.{language} key mismatch; "
                    f"missing={sorted(reference - signature)}, "
                    f"extra={sorted(signature - reference)}"
                )

        assert (
            locale_object_count > 0
        ), f"{page_label}: Spanish selector has no locale-indexed copy object"

    assert localized_pages > 0


@pytest.mark.parametrize(
    ("module", "expected_spanish_labels"),
    (
        (
            "check-entries",
            {
                "sections": "Secciones de la página",
                "language": "Idioma",
                "problem": "Problema resuelto",
            },
        ),
        (
            "journal-bank-reconciliation",
            {
                "sections": "Secciones de la página",
                "language": "Idioma",
                "problem": "Problema resuelto",
            },
        ),
        (
            "journal-sampling",
            {
                "sections": "Secciones de la página",
                "language": "Idioma",
                "problem": "Problema resuelto",
            },
        ),
        (
            "report-builder",
            {
                "sections": "Secciones de la página",
                "language": "Idioma",
            },
        ),
        (
            "riconciliazione-partite",
            {
                "sections": "Secciones de la página",
                "language": "Idioma",
                "problem": "Problema resuelto",
            },
        ),
    ),
)
def test_spanish_vera_pages_localize_accessibility_labels(
    module: str,
    expected_spanish_labels: dict[str, str],
) -> None:
    page = VERA_MODULE_PAGES[module].read_text(encoding="utf-8")
    objects = dict(_js_named_object_literals(page))
    accessibility_copy = _js_object_properties(objects["accessibilityLabels"])
    spanish_copy = _js_object_properties(accessibility_copy["es"])

    assert accessibility_copy.keys() == {"it", "en", "fr", "de", "es"}
    assert {
        key: json.loads(value) for key, value in spanish_copy.items()
    } == expected_spanish_labels
    assert set(re.findall(r'data-accessibility-label="([^"]+)"', page)) == set(
        expected_spanish_labels
    )
    assert 'querySelectorAll("[data-accessibility-label]")' in page
    assert (
        'node.setAttribute("aria-label", '
        "accessibilityLabels[safeLang][node.dataset.accessibilityLabel])"
    ) in page


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
    assert 'href="../vera/index.html"' in page


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
    ("module", "render_call", "scenario_count", "localized_language_count"),
    (
        (
            "concordato-plan-review",
            'renderPairs("prompt-list", t.prompts.items)',
            3,
            5,
        ),
        (
            "journal-bank-reconciliation",
            'renderOutputList("prompt-list", t.prompts.items)',
            3,
            5,
        ),
        (
            "journal-sampling",
            'setOutputList("prompt-list", data.prompts.items)',
            3,
            5,
        ),
        (
            "riconciliazione-partite",
            "data.prompts.rows, ([title, copy])",
            5,
            5,
        ),
    ),
)
def test_vera_scenario_prompt_libraries_are_visible_and_localized(
    module: str,
    render_call: str,
    scenario_count: int,
    localized_language_count: int,
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
    assert len(prompt_blocks) == localized_language_count
    for prompt_block in prompt_blocks:
        assert prompt_block.count("\n            [") == scenario_count


def test_report_builder_publishes_three_localized_scenario_prompts() -> None:
    page = VERA_MODULE_PAGES["report-builder"].read_text(encoding="utf-8")
    prompt_section = _section_markup(page, "prompts")
    language_count = len(set(re.findall(r'data-lang="([a-z]{2})"', page)))

    assert prompt_section.count("<li>") == 3
    for item_number in range(1, 4):
        for field in ("title", "copy"):
            key = f"prompts.item{item_number}.{field}"
            assert f'data-i18n="{key}"' in prompt_section
            assert page.count(f'"{key}":') == language_count


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
        assert page.count(f'"{key}":') == 5


def _section_markup(page: str, section_id: str) -> str:
    marker = f'id="{section_id}"'
    marker_index = page.index(marker)
    section_start = page.rfind("<section", 0, marker_index)
    section_end = page.index("</section>", marker_index) + len("</section>")
    return page[section_start:section_end]


def test_vera_hub_separates_general_workflows_from_market_specific_work() -> None:
    page = (SHARED_ROOT / "vera" / "index.html").read_text(encoding="utf-8")
    core = _section_markup(page, "core")
    jurisdiction = _section_markup(page, "jurisdiction")

    assert core.count('class="module-row"') == 9
    assert jurisdiction.count('data-jurisdiction-item="it"') == 5
    assert jurisdiction.count('data-jurisdiction-item="en"') == 1
    assert jurisdiction.count('data-jurisdiction-item="fr"') == 1
    assert jurisdiction.count('data-jurisdiction-item="de"') == 1
    for expected_href in (
        "../new-client/index.html#journey",
        "../studio-archive/index.html",
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
        "../check-entries/index.html#italy-adapter",
        "../report-builder/index.html#italy-preset",
        "../concordato-plan-review/index.html",
        "../previdenza-inps/index.html",
        "../registro-imprese-sari/index.html",
        "../new-client/uk.html",
        "../new-client/geneva.html",
        "../new-client/zurich.html",
    ):
        assert f'href="{expected_href}"' in jurisdiction

    assert "FatturaPA" not in core
    assert "FatturaPA" in jurisdiction
    assert 'href="#core"' in page
    assert 'href="#jurisdiction"' in page
    assert page.index('id="core"') < page.index('id="jurisdiction"')
    assert page.index('id="jurisdiction"') < page.index('id="video"')


def test_vera_publishes_one_new_client_path_without_retired_identity_names() -> None:
    hub = (SHARED_ROOT / "vera" / "index.html").read_text(encoding="utf-8")
    new_client = (SHARED_ROOT / "new-client" / "index.html").read_text(encoding="utf-8")
    public_identity_sources = "\n".join(
        (
            hub,
            new_client,
            (SHARED_ROOT / "vera-scope.js").read_text(encoding="utf-8"),
            (SHARED_ROOT / "video-library.js").read_text(encoding="utf-8"),
            (SHARED_ROOT / "video-production" / "vera-missing-guides.json").read_text(
                encoding="utf-8"
            ),
        )
    ).casefold()

    assert hub.count('id="new-client"') == 1
    assert hub.count('href="../new-client/index.html#journey"') == 1
    assert not (SHARED_ROOT / "client-intake").exists()
    assert not (SHARED_ROOT / "client-onboarding").exists()
    for retired_identity in (
        "client-intake",
        "client-onboarding",
        "client intake",
        "client onboarding",
    ):
        assert retired_identity not in public_identity_sources

    assert "journey-step__number" not in new_client
    assert "01 ·" not in new_client
    assert "02 ·" not in new_client
    assert "03 ·" not in new_client
    assert 'data-vera-module="new-client"' in new_client
    assert "data-vera-scope=" not in new_client
    assert "vera-scope.css" not in new_client
    assert "vera-scope.js" not in new_client
    assert 'id="italy"' in new_client
    assert 'href="#italy"' in new_client
    assert 'id="italy-pack"' not in new_client
    assert "z32cIdqyXCk" not in new_client
    assert "hLhP6x00ghQ" not in new_client
    assert "d9S4SA63sVw" not in new_client
    assert "Mjfz1e98oIw" not in new_client
    assert "https://youtu.be/FWjVBeJYLF8" in new_client
    assert "UwLsy2FuP8o" not in new_client
    assert "video-production/rendered" not in new_client
    assert '"documents.privacy.title": "Protection des données"' in new_client

    journey_css = (SHARED_ROOT / "vera-journey.css").read_text(encoding="utf-8")
    assert 'body[data-vera-module="new-client"] .journey-step' in journey_css
    assert "flex-wrap: nowrap;" in journey_css
    assert "grid-template-columns: minmax(210px, 0.42fr) minmax(0, 0.58fr);" in (
        journey_css
    )


def test_vera_hub_language_buttons_and_copy_keys_stay_in_sync() -> None:
    page = (SHARED_ROOT / "vera" / "index.html").read_text(encoding="utf-8")
    visible_keys = set(re.findall(r'data-i18n(?:-aria-label)?="([^"]+)"', page))
    language_buttons = set(re.findall(r'data-lang="([a-z]{2})"', page))
    copy_languages = set(re.findall(r"^      ([a-z]{2}): \{$", page, re.MULTILINE))

    assert visible_keys
    assert language_buttons == copy_languages == {"it", "en", "fr", "de", "es"}
    for key in visible_keys:
        assert page.count(f'"{key}":') == len(copy_languages), key
    for language in copy_languages:
        assert f'hreflang="{language}"' in page


def test_studio_archive_page_explains_gmail_and_whatsapp_in_plain_language() -> None:
    page = (SHARED_ROOT / "studio-archive" / "index.html").read_text(encoding="utf-8")
    visible_keys = set(re.findall(r'data-i18n(?:-aria-label)?="([^"]+)"', page))
    language_buttons = set(re.findall(r'data-lang="([a-z]{2})"', page))
    copy_languages = set(re.findall(r"^      ([a-z]{2}): \{$", page, re.MULTILINE))

    assert page.count("<h1") == 1
    assert language_buttons == copy_languages == {"it", "en", "fr", "de", "es"}
    for key in visible_keys:
        assert page.count(f'"{key}":') == len(copy_languages), key
    for phrase in (
        "Find a client’s messages without sorting everything by hand.",
        "This works only in Codex Desktop and handles one client at a time.",
        "You do not need to move emails into folders or export chats.",
        "Connect Gmail first",
        "Open WhatsApp Desktop first",
        "Computer Use",
        "Opening the chat may mark messages as read.",
        "Vera does not create a complete copy of your emails or chats.",
        "Vera does not synchronize the mailbox or chats",
        "that content may be sent to Codex/ChatGPT",
        "This function does not start in ChatGPT on the web or mobile.",
    ):
        assert phrase in page
    assert "plugins_6a57ac5ce65c8191ae7bd0a51160eb7d" not in page
    assert 'href="../vera/index.html"' in page
    assert "ChatGPT · Marketplace" not in page
    assert "90 days" not in page
    assert "90 giorni" not in page
    assert "https://youtu.be/" not in page
    assert "<video" not in page


@pytest.mark.parametrize(
    ("page_path", "product"),
    (
        (SHARED_ROOT / "vera" / "index.html", "Vera"),
        (SHARED_ROOT / "clara" / "index.html", "Clara"),
    ),
)
def test_product_install_copy_explains_marketplace_and_desktop_handoff(
    page_path: Path,
    product: str,
) -> None:
    page = page_path.read_text(encoding="utf-8")
    for phrase in (
        f"The button opens {product} in the Marketplace.",
        f"Il pulsante apre {product} nel Marketplace.",
        f"Le bouton ouvre {product} dans le Marketplace.",
        f"Die Schaltfläche öffnet {product} im Marketplace.",
        f"El botón abre {product} en el Marketplace.",
        "Workflows do not start in ChatGPT on the web or mobile.",
        "I workflow non partono in ChatGPT web o mobile.",
        "Les workflows ne démarrent pas dans ChatGPT sur le web ou mobile.",
        "Workflows starten nicht in ChatGPT im Web oder auf Mobilgeräten.",
        "Los flujos no se inician en ChatGPT web o móvil.",
    ):
        assert phrase in page


def _vera_data_boundary_section(page: str) -> str:
    section_start = page.index('<section class="section-block" id="data-boundary">')
    section_end = page.index('<section class="section-block" id="video">')
    return page[section_start:section_end]


def test_vera_hub_data_boundary_is_compact_and_not_manifest_driven() -> None:
    page = (SHARED_ROOT / "vera" / "index.html").read_text(encoding="utf-8")
    section = _vera_data_boundary_section(page)

    assert "<table" not in section
    assert "data-privacy-workstream" not in page
    assert "data-privacy-fingerprint" not in page
    assert "privacy.row." not in page
    assert "privacy.notice" not in page
    assert "privacy.governance" not in page
    assert section.count('class="data-position__fact"') == 4
    assert section.count('class="data-route"') == 2
    assert 'href="/data-handling?lang=it#data-handling-video"' in section
    assert "data-compliance-video-link" in section
    assert "`/data-handling?lang=${lang}#data-handling-video`" in page
    for label in (
        "Guarda il video sulla gestione dei dati",
        "Watch the data-handling video",
        "Voir la vidéo sur le traitement des données",
        "Video zur Datenverarbeitung ansehen",
        "Ver el vídeo sobre el tratamiento de datos",
    ):
        assert label in page


@pytest.mark.parametrize(
    (
        "title",
        "automatic",
        "local_python",
        "chatgpt_plan",
        "recipient_boundary",
        "secrets",
        "hosted_boundary",
        "workflow_mapping",
        "external_destination",
    ),
    (
        (
            "Vera lavora sui dati reali del cliente.",
            "Vera e Clara non anonimizzano automaticamente i dati.",
            "Possono usare Python in locale per filtrare o aggregare le informazioni",
            "piano ChatGPT già utilizzato dall’utente",
            "non inviano a Mparanza file dei clienti, prompt o contenuti del contesto del modello",
            "Password, chiavi API, cookie, token e dati di sessione",
            "Servizi hosted da Mparanza",
            "Ogni workflow viene mappato quando viene aggiunto o quando cambia",
            "non sono una terza categoria Mparanza",
        ),
        (
            "Vera works on real client data.",
            "Vera and Clara do not automatically anonymise data.",
            "They may use local Python to filter or aggregate information",
            "user’s existing ChatGPT plan",
            "do not send client files, prompts, or model-context content to Mparanza",
            "Passwords, API keys, cookies, tokens, and session data",
            "Mparanza-hosted services",
            "Each workflow is mapped when it is added or changed",
            "not a third Mparanza category",
        ),
        (
            "Vera travaille sur les données réelles du client.",
            "Vera et Clara n’anonymisent pas automatiquement les données.",
            "Elles peuvent utiliser Python localement pour filtrer ou agréger",
            "l’offre ChatGPT existante de l’utilisateur",
            "n’envoient à Mparanza ni fichiers clients, ni prompts, ni contenu du contexte du modèle",
            "Mots de passe, clés API, cookies, jetons et données de session",
            "Services hébergés par Mparanza",
            "Chaque workflow est cartographié lorsqu’il est ajouté ou modifié",
            "ne constituent pas une troisième catégorie Mparanza",
        ),
        (
            "Vera arbeitet mit echten Mandantendaten.",
            "Vera und Clara anonymisieren Daten nicht automatisch.",
            "Sie können Python lokal einsetzen, um Informationen zu filtern oder zu aggregieren",
            "bestehenden ChatGPT-Tarifs des Nutzers",
            "senden keine Mandantendateien, Prompts oder Inhalte des Modellkontexts an Mparanza",
            "Passwörter, API-Schlüssel, Cookies, Token und Sitzungsdaten",
            "Mparanza-gehostete Dienste",
            "Jeder Workflow wird beim Hinzufügen oder Ändern zugeordnet",
            "keine dritte Mparanza-Kategorie",
        ),
        (
            "Vera trabaja con datos reales del cliente.",
            "Vera y Clara no anonimizan automáticamente los datos.",
            "Pueden usar Python en local para filtrar o agregar información",
            "plan de ChatGPT que ya utiliza el usuario",
            "no envían a Mparanza archivos de clientes, prompts ni contenido del contexto del modelo",
            "contraseñas, claves de API, cookies, tokens y datos de sesión",
            "Servicios alojados por Mparanza",
            "Cada flujo de trabajo se mapea cuando se añade o cambia",
            "no forman una tercera categoría de Mparanza",
        ),
    ),
)
def test_vera_hub_localizes_the_real_data_boundary(
    title: str,
    automatic: str,
    local_python: str,
    chatgpt_plan: str,
    recipient_boundary: str,
    secrets: str,
    hosted_boundary: str,
    workflow_mapping: str,
    external_destination: str,
) -> None:
    page = (SHARED_ROOT / "vera" / "index.html").read_text(encoding="utf-8")

    assert title in page
    assert automatic in page
    assert local_python in page
    assert chatgpt_plan in page
    assert recipient_boundary in page
    assert secrets in page
    assert hosted_boundary in page
    assert workflow_mapping in page
    assert external_destination in page


@pytest.mark.parametrize(
    "model_processing_copy",
    (
        "I dati forniti al modello vengono trattati attraverso il piano ChatGPT",
        "Data supplied to the model is processed through the user’s existing ChatGPT plan",
        "Les données fournies au modèle sont traitées dans le cadre de l’offre ChatGPT existante",
        "Daten, die dem Modell bereitgestellt werden, werden im Rahmen des bestehenden ChatGPT-Tarifs",
        "Los datos proporcionados al modelo se procesan mediante el plan de ChatGPT",
    ),
)
def test_vera_hub_names_the_model_processing_plan(
    model_processing_copy: str,
) -> None:
    page = (SHARED_ROOT / "vera" / "index.html").read_text(encoding="utf-8")

    assert model_processing_copy in page
    assert "relevant content enters" not in page
    assert "contenuto pertinente entra" not in page
    assert "contenu pertinent entre" not in page
    assert "relevante Inhalte" not in page


def test_vera_hub_names_the_two_processing_categories() -> None:
    page = (SHARED_ROOT / "vera" / "index.html").read_text(encoding="utf-8")
    section = _vera_data_boundary_section(page)

    for key in (
        "privacy.routes.local.title",
        "privacy.routes.hosted.title",
    ):
        assert f'data-i18n="{key}"' in section
        assert page.count(f'"{key}":') == 5

    assert 'data-i18n="privacy.routes.codex.title"' not in section
    assert "privacy.routes.external" not in page


@pytest.mark.parametrize(
    "labels",
    (
        ("Area di lavoro 1 di 3", "Area di lavoro 2 di 3", "Area di lavoro 3 di 3"),
        ("Work area 1 of 3", "Work area 2 of 3", "Work area 3 of 3"),
        (
            "Domaine de travail 1 sur 3",
            "Domaine de travail 2 sur 3",
            "Domaine de travail 3 sur 3",
        ),
        (
            "Arbeitsbereich 1 von 3",
            "Arbeitsbereich 2 von 3",
            "Arbeitsbereich 3 von 3",
        ),
        (
            "Área de trabajo 1 de 3",
            "Área de trabajo 2 de 3",
            "Área de trabajo 3 de 3",
        ),
    ),
)
def test_vera_hub_explains_work_area_numbers_in_every_language(
    labels: tuple[str, str, str],
) -> None:
    page = (SHARED_ROOT / "vera" / "index.html").read_text(encoding="utf-8")

    for label in labels:
        assert f'"{label}"' in page


def test_vera_hub_module_fragments_resolve_to_real_page_sections() -> None:
    hub_path = SHARED_ROOT / "vera" / "index.html"
    page = hub_path.read_text(encoding="utf-8")
    module_hrefs = re.findall(
        r'<a\b(?=[^>]*\bclass="module-row")(?=[^>]*\bdata-module-link)[^>]*'
        r'\bhref="([^"]+)"',
        page,
    )

    assert len(module_hrefs) == 17
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


def test_new_client_jurisdiction_pages_use_one_native_language() -> None:
    jurisdiction_root = SHARED_ROOT / "new-client"
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
        assert set(re.findall(r'hreflang="([a-z-]+)"', page)) == {
            default_language,
            "x-default",
        }
        assert 'hreflang="x-default"' in page
        assert f'slug: "{filename}"' in jurisdiction_script
        assert f'defaultLanguage: "{default_language}"' in jurisdiction_script

    assert "const SUPPORTED_LANGUAGES" not in jurisdiction_script
    assert "const page = jurisdictions[document.body.dataset.jurisdiction]" in (
        jurisdiction_script
    )
    assert "document.body.dataset.presentationLanguage = language" in (
        jurisdiction_script
    )
    assert "const copy = page.copy[language]" in jurisdiction_script
    assert "const language = page.defaultLanguage" in jurisdiction_script
    assert "renderLanguageSwitch(language)" not in jurisdiction_script
    assert "coreVideoIds" not in jurisdiction_script
    assert "Report Builder" not in jurisdiction_script
    assert not re.search(r'title: "[123]\. ', jurisdiction_script)
    assert "dataset.jurisdiction =" not in jurisdiction_script
    assert "window.location.replace" not in jurisdiction_script


def test_vera_hub_uses_the_central_curated_video_catalog() -> None:
    page = (SHARED_ROOT / "vera" / "index.html").read_text(encoding="utf-8")

    assert re.search(r'src="\.\./video-library\.js\?v=[^"]+"', page)
    assert 'window.MparanzaVideos.getCatalog("vera", lang)' in page
    assert 'const videoLang = lang === "es" ? "en" : lang;' not in page
    assert (
        'const curatedVideoModules = ["new-client", '
        '"journal-bank-reconciliation", "report-builder", "prompt-optimizer"]'
    ) in page
    assert page.count("data-video-index=") == 4
    assert page.count('<a class="overview-video') == 1
    assert "install-panel__video" not in page
    assert "UwLsy2FuP8o" not in page
    assert "link.href = `https://youtu.be/${item.id}`" in page
    assert 'link.querySelector("img").src = thumbnailUrl(item.id)' in page
    assert 'es: { id: "RKcy1G79RAs", duration: "1:20" }' in page


def test_vera_missing_guide_pack_is_complete_youtube_source() -> None:
    spec_path = SHARED_ROOT / "video-production" / "vera-missing-guides.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    concepts = spec["concepts"]

    assert spec["schemaVersion"] == "3.0.0"
    assert spec["identityModel"] == "module + edition + jurisdiction + language"
    assert spec["publicationStatus"] == "youtube_source"
    assert spec["remotePublish"] is True
    assert "renderedManifest" not in spec
    assert {(concept["module"], concept["edition"]) for concept in concepts} == {
        ("new-client", "italy"),
        ("studio-archive", "core"),
        ("journal-sampling", "core"),
        ("check-entries", "core"),
        ("check-entries", "italy-fatturapa"),
        ("data-handling", "core"),
    }
    assert sum(len(concept["localizations"]) for concept in concepts) == 21
    for concept in concepts:
        assert len(concept["scenes"]) == 6
        assert concept["pageTargets"]
        if concept["scope"] == "core":
            assert concept["edition"] == "core"
            assert concept["jurisdiction"] is None
        else:
            assert concept["scope"] == "country"
            assert concept["jurisdiction"] == "IT"
            assert set(concept["localizations"]) <= {"it"}
        for localization in concept["localizations"].values():
            assert localization["title"]
            assert localization["narration"]
            assert len(localization["onScreen"]) == 6
            narration_sentences = [
                sentence.strip()
                for sentence in re.split(
                    r"(?<=[.!?])\s+", localization["narration"].strip()
                )
                if sentence.strip()
            ]
            assert len(narration_sentences) >= len(concept["scenes"])
            assert all(
                re.search(r"[.!?]$", sentence) for sentence in narration_sentences
            )
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

    italy = next(
        concept
        for concept in concepts
        if concept["module"] == "new-client" and concept["edition"] == "italy"
    )
    required_italy_phrases = {
        "it": (
            "bozza di valutazione",
            "documentato",
            "resta aperto",
            "richiede riesame",
            "fascicolo cliente di lavoro",
        )
    }
    for language, required_phrases in required_italy_phrases.items():
        localization = italy["localizations"][language]
        localized_script = " ".join(
            (localization["narration"], *localization["onScreen"])
        ).casefold()
        for phrase in required_phrases:
            assert phrase in localized_script

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
    assert check_entries["localizations"] == {}

    data_handling = next(
        concept for concept in concepts if concept["module"] == "data-handling"
    )
    assert data_handling["brand"] == "Vera + Clara"
    assert set(data_handling["localizations"]) == {"it", "en", "fr", "de", "es"}
    assert "/data-handling" in data_handling["pageTargets"]
    for language, required_phrases in {
        "it": (
            "non viene anonimizzato automaticamente",
            "piano ChatGPT",
            "nessun contenuto",
        ),
        "en": (
            "not anonymised automatically",
            "existing ChatGPT plan",
            "no client or work content",
        ),
        "fr": (
            "n’est pas anonymisé automatiquement",
            "offre ChatGPT existante",
            "aucun contenu",
        ),
        "de": (
            "nicht automatisch anonymisiert",
            "bestehender ChatGPT-Tarif",
            "keine Kunden- oder Arbeitsinhalte",
        ),
        "es": (
            "no se anonimiza automáticamente",
            "plan actual de ChatGPT",
            "no se envía",
        ),
    }.items():
        narration = data_handling["localizations"][language]["narration"]
        for phrase in required_phrases:
            assert phrase in narration

    studio_archive = next(
        concept for concept in concepts if concept["module"] == "studio-archive"
    )
    assert studio_archive["conceptId"] == "one-client-two-message-sources"
    assert studio_archive["edition"] == "core"
    assert set(studio_archive["localizations"]) == {"it", "en", "fr", "de", "es"}
    assert "/static/shared/studio-archive/index.html" in studio_archive["pageTargets"]
    for language, required_phrases in {
        "it": (
            "directory pubblica dei plugin",
            "si ferma su ChatGPT web o mobile",
            "Dentro Codex Desktop",
            "connector Gmail di OpenAI",
            "Computer Use",
            "non crea archivi di messaggi Gmail o WhatsApp su Mparanza",
        ),
        "en": (
            "public Plugins Directory",
            "stops on ChatGPT web and mobile",
            "Inside Codex Desktop",
            "OpenAI’s separately connected Gmail connector",
            "Computer Use",
            "creates no Gmail or WhatsApp message store on Mparanza",
        ),
        "fr": (
            "répertoire public des plugins",
            "s’arrêtent sur ChatGPT web ou mobile",
            "Dans Codex Desktop",
            "connecteur Gmail d’OpenAI",
            "Computer Use",
            "aucune archive de messages Gmail ou WhatsApp chez Mparanza",
        ),
        "de": (
            "öffentlichen Plugin-Verzeichnis",
            "in ChatGPT im Web oder auf Mobilgeräten gestoppt",
            "In Codex Desktop",
            "Gmail-Connector von OpenAI",
            "Computer Use",
            "kein Gmail- oder WhatsApp-Nachrichtenarchiv",
        ),
        "es": (
            "directorio público de plugins",
            "se detiene en ChatGPT web o móvil",
            "Dentro de Codex Desktop",
            "conector de Gmail de OpenAI",
            "Computer Use",
            "no crea un archivo de mensajes de Gmail o WhatsApp en Mparanza",
        ),
    }.items():
        narration = studio_archive["localizations"][language]["narration"]
        for phrase in required_phrases:
            assert phrase in narration


def test_vera_video_catalog_v4_is_youtube_only_and_jurisdiction_native() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required to execute the browser video catalog")
    script = r"""
const fs = require("node:fs");
global.window = {};
eval(fs.readFileSync(process.argv[1], "utf8"));
const catalogs = ["it", "en", "fr", "de", "es"].map((language) =>
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
    catalogs = {catalog["language"]: catalog for catalog in json.loads(result.stdout)}

    assert all(catalog["version"] == "4.1.0" for catalog in catalogs.values())
    assert catalogs["es"]["featured"]["id"] == "BEiFYgK5Wew"
    assert catalogs["es"]["featured"]["audioLanguage"] == "es"
    assert len(catalogs["es"]["videos"]) == 8
    assert {video["audioLanguage"] for video in catalogs["es"]["videos"]} == {"es"}
    assert {video["id"] for video in catalogs["es"]["videos"]} == {
        "X3BOp9ZxiAQ",
        "5wEggdDYrm0",
        "PD0vpXBY7GU",
        "DGrRH3MGRcg",
        "ePe_bVrC-bs",
        "-TnYwnglpqE",
        "Q351IGPEPxg",
        "lHOahBSRknQ",
    }

    expected_jurisdictions = {
        "it": {"IT"},
        "en": {"UK"},
        "fr": {"CH-GE"},
        "de": {"CH-ZH"},
        "es": set(),
    }
    for language, catalog in catalogs.items():
        country_videos = [
            video for video in catalog["videos"] if video["scope"] == "country"
        ]
        assert {video["jurisdiction"] for video in country_videos} == (
            expected_jurisdictions[language]
        )
        for video in catalog["videos"]:
            assert video["sourceKind"] == "youtube"
            assert video["status"] == "published"
            assert video["id"]
            assert video["language"] == language
            assert video["audioLanguage"] == language
            assert "src" not in video
            assert "poster" not in video
            assert "captions" not in video


def test_replaced_vera_guides_are_linked_from_module_pages_on_youtube() -> None:
    new_client = VERA_MODULE_PAGES["new-client"].read_text(encoding="utf-8")
    sampling = VERA_MODULE_PAGES["journal-sampling"].read_text(encoding="utf-8")
    entries = VERA_MODULE_PAGES["check-entries"].read_text(encoding="utf-8")

    assert "<video" not in new_client
    assert "<video" not in sampling
    assert "<video" not in entries
    assert "FWjVBeJYLF8" in new_client
    assert "UwLsy2FuP8o" not in new_client
    assert "HW8amlcU0Lk" in sampling
    for youtube_id in ("xakA0V5-3-8", "I1dp3FYVy2w"):
        assert youtube_id in entries
    for page in (new_client, sampling, entries):
        assert "https://youtu.be/" in page
        assert "video-production/rendered" not in page
        assert "transcript.txt" not in page
