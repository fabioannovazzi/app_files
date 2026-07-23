from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = ROOT / "static"
VIDEO_LIBRARY = STATIC_ROOT / "shared" / "video-library.js"

SETUP_IDS = {
    "it": "yAnkIabnQ1M",
    "en": "vU4eow_MMDA",
    "fr": "GPY7HqkH62c",
    "de": "1LJCCTxGL_8",
    "es": "RKcy1G79RAs",
}
BAD_SETUP_IDS = {"XnxtkNGecqc", "2-jQCy1aQwA", "Jj8ENI1D8Eg", "3fseEPtIAG8"}
ENGLISH_OUTWARD_IDS = {
    "3zvFm3fGdQ8",
    "s3vtavYiUco",
    "T_cklFKk3WA",
    "Ol9yz9NWOlw",
    "i-EtiyVeBQ8",
    "OdEdNAVu0hY",
    "u_UmkF7pDZ8",
    "zMQjPiyiDnA",
    "0vM_PmJccwY",
    "6HCRTPbOanc",
    "LPjR9Off3sc",
    "KVGdOyK-Vmc",
    "Lqt3odBszD0",
    "Qn9YTSX388I",
    "VnOXN2SnqNE",
    "KfABIkftuoE",
    "LYNGc7XVmsI",
    "jbZ34kOeQRc",
    "wbeoePNN4YA",
    "FdZhrFCHwV4",
    "GRAPmp9D7ds",
    "wvZ1xR7waRQ",
    "9gJxX-dya70",
    "EItLLt-gVgo",
}
CLARA_SPANISH_OUTWARD_IDS = {
    "8aCsIsrwWfU",
    "FCMj7mUSy5k",
    "sJ6EJmabrrw",
    "CxMUDaA3XG0",
    "TzxMFJhR_vQ",
    "7K0ecDNm3ow",
    "UaGED7QgTNE",
    "hCusu-KXNJk",
    "Rh-v4L9qN2k",
    "E_6CKkZuTJY",
    "0ONQKCbIv_8",
    "oPTUz-FhB-A",
}
VERA_SPANISH_OUTWARD_IDS = {
    "BEiFYgK5Wew",
    "p0OOhlz7_Sc",
    "bFhSQiilox8",
    "bL-LXrQzCA4",
    "ePe_bVrC-bs",
    "-TnYwnglpqE",
    "X3BOp9ZxiAQ",
    "5wEggdDYrm0",
    "1REbQ-wBNf8",
    "DGrRH3MGRcg",
    "BrCOAgSVyYg",
    "PD0vpXBY7GU",
}
SPANISH_MODULE_IDS = {
    "xaWouXRwO8c",
    "41H8PKFFmKg",
    "Q351IGPEPxg",
    "lHOahBSRknQ",
    "GI6u74BPnN8",
}


def _production_video_sources() -> str:
    roots = (STATIC_ROOT, ROOT / "templates", ROOT / "modules" / "pdp")
    suffixes = {".css", ".html", ".js", ".json", ".py"}
    return "\n".join(
        path.read_text(encoding="utf-8")
        for source_root in roots
        for path in source_root.rglob("*")
        if path.is_file() and path.suffix in suffixes
    )


def _library_definition() -> dict[str, object]:
    source = VIDEO_LIBRARY.read_text(encoding="utf-8")
    prefix = "  const library = "
    start = source.index(prefix) + len(prefix)
    end = source.index("\n\n  const catalogVersion", start)
    return json.loads(source[start:end].removesuffix(";"))


def test_public_site_has_no_self_hosted_video_or_transcript_artifacts() -> None:
    production_sources = _production_video_sources()
    video_surface_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            VIDEO_LIBRARY,
            STATIC_ROOT / "shared" / "check-entries" / "index.html",
            STATIC_ROOT / "shared" / "journal-sampling" / "index.html",
            STATIC_ROOT / "shared" / "new-client" / "index.html",
        )
    )

    assert not list(STATIC_ROOT.rglob("*.mp4"))
    assert not list(STATIC_ROOT.rglob("*.vtt"))
    assert "video-production/rendered" not in production_sources
    assert "transcript.txt" not in production_sources
    assert "video-transcript" not in production_sources
    assert "video__transcript" not in production_sources
    assert not re.search(
        r"""["'](?:proof\.transcript|core\.video\.transcript|proof\.video\.transcript)["']\s*:""",
        video_surface_sources,
    )
    assert not re.search(
        r"""["'](?:transcript|transcriptLabel|transcriptUrl)["']\s*:""",
        video_surface_sources,
        re.IGNORECASE,
    )
    assert not re.search(
        r"""<a\b[^>]*(?:href|class|id)=["'][^"']*transcript""",
        video_surface_sources,
        re.IGNORECASE,
    )
    assert not re.search(
        r"""sourceKind\s*[:=]\s*["']local["']""",
        production_sources,
    )


def test_setup_guides_use_only_verified_localized_youtube_ids() -> None:
    vera_page = (STATIC_ROOT / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )
    clara_page = (STATIC_ROOT / "shared" / "clara" / "index.html").read_text(
        encoding="utf-8"
    )
    combined = f"{vera_page}\n{clara_page}"

    for youtube_id in SETUP_IDS.values():
        assert youtube_id in vera_page
        assert youtube_id in clara_page
    assert SETUP_IDS["es"] in combined
    assert BAD_SETUP_IDS.isdisjoint(set(re.findall(r"[\w-]{11}", combined)))


def test_vera_hero_consolidates_installation_and_localized_setup_video() -> None:
    vera_page = (STATIC_ROOT / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )
    hero_start = vera_page.index('<section class="hero">')
    hero_end = vera_page.index("</section>", hero_start)
    hero = vera_page[hero_start:hero_end]
    video_start = hero.index('id="vera-install-video-link"')
    video_end = hero.index("</a>", video_start)
    install_video = hero[video_start:video_end]

    assert 'id="installa"' in hero
    assert 'data-i18n="install.title"' in hero
    assert 'data-i18n="install.copy"' in hero
    assert 'data-i18n="install.button"' in hero
    assert hero.count('id="vera-install-video-link"') == 1
    assert f'href="https://youtu.be/{SETUP_IDS["it"]}"' in install_video
    assert 'data-i18n-aria-label="install.video.title"' in install_video
    assert "overview-video__body" not in install_video
    assert vera_page.count('id="installa"') == 1
    assert 'id="vera-hero-install-video-link"' not in vera_page
    assert "install-panel__video" not in vera_page
    assert vera_page.index('id="installa"') < vera_page.index('id="modello"')
    assert (
        'document.getElementById("vera-install-video-link").href = '
        "`https://youtu.be/${installVideo.id}`;"
    ) in vera_page
    assert 'document.getElementById("vera-hero-install-video-link")' not in vera_page
    for language, youtube_id in SETUP_IDS.items():
        assert f'{language}: {{ id: "{youtube_id}",' in vera_page
    assert (
        '"install.video.title": "Da ChatGPT sul telefono a Vera o Clara in Codex"'
        in vera_page
    )
    assert (
        '"install.video.title": "From ChatGPT on your phone to Vera or Clara in Codex"'
        in vera_page
    )
    assert (
        '"install.video.title": "De ChatGPT sur votre téléphone à Vera ou Clara dans Codex"'
        in vera_page
    )
    assert (
        '"install.video.title": "Von ChatGPT auf dem Smartphone zu Vera oder Clara in Codex"'
        in vera_page
    )
    assert (
        '"install.video.title": "De ChatGPT en el teléfono a Vera o Clara en Codex"'
        in vera_page
    )


def test_clara_hero_consolidates_installation_and_localized_setup_video() -> None:
    clara_page = (STATIC_ROOT / "shared" / "clara" / "index.html").read_text(
        encoding="utf-8"
    )
    hero_start = clara_page.index('<section class="hero">')
    hero_end = clara_page.index("</section>", hero_start)
    hero = clara_page[hero_start:hero_end]
    video_start = hero.index('id="clara-install-video-link"')
    video_end = hero.index("</a>", video_start)
    install_video = hero[video_start:video_end]

    assert 'id="download"' in hero
    assert 'data-i18n="install.title"' in hero
    assert 'data-i18n="install.copy"' in hero
    assert 'data-i18n="install.button"' in hero
    assert hero.count('id="clara-install-video-link"') == 1
    assert f'href="https://youtu.be/{SETUP_IDS["en"]}"' in install_video
    assert 'data-i18n-aria-label="install.video.title"' in install_video
    assert "video-story__body" not in install_video
    assert clara_page.count('id="download"') == 1
    assert clara_page.count("data-clara-install-link") == 1
    assert "download-panel" not in clara_page
    assert 'data-i18n="download.step1"' not in clara_page
    assert 'data-i18n="download.help.title"' not in clara_page
    assert 'data-i18n="install.signed_out"' not in clara_page
    assert clara_page.index('id="download"') < clara_page.index(
        '<section id="presentations">'
    )
    assert (
        'document.getElementById("clara-install-video-link").href = '
        "`https://youtu.be/${activeInstallVideo.id}`;"
    ) in clara_page
    for language, youtube_id in SETUP_IDS.items():
        assert f'{language}: {{ id: "{youtube_id}",' in clara_page
    assert (
        '"install.video.title": "From ChatGPT on your phone to Vera or Clara in Codex"'
        in clara_page
    )
    assert (
        '"install.video.title": "Da ChatGPT sul telefono a Vera o Clara in Codex"'
        in clara_page
    )
    assert (
        '"install.video.title": "De ChatGPT sur votre téléphone à Vera ou Clara dans Codex"'
        in clara_page
    )
    assert (
        '"install.video.title": "Von ChatGPT auf dem Smartphone zu Vera oder Clara in Codex"'
        in clara_page
    )
    assert (
        '"install.video.title": "De ChatGPT en el teléfono a Vera o Clara en Codex"'
        in clara_page
    )


def test_spanish_catalog_uses_all_native_outward_videos_without_english_fallback() -> (
    None
):
    library = _library_definition()
    clara = library["clara"]["es"]
    vera = library["vera"]["es"]

    clara_ids = {clara["featured"]["id"], *(video["id"] for video in clara["videos"])}
    vera_ids = {vera["featured"]["id"], *(video["id"] for video in vera["videos"])}
    spanish_catalog_ids = clara_ids | vera_ids
    localized_module_ids = set(
        re.findall(
            r'es:\s*"([A-Za-z0-9_-]{11})"', VIDEO_LIBRARY.read_text(encoding="utf-8")
        )
    )

    assert clara_ids == CLARA_SPANISH_OUTWARD_IDS
    assert vera_ids == VERA_SPANISH_OUTWARD_IDS
    assert len(spanish_catalog_ids) == 24
    assert spanish_catalog_ids.isdisjoint(ENGLISH_OUTWARD_IDS)
    assert SPANISH_MODULE_IDS <= localized_module_ids


def test_video_policy_preserves_real_clara_transcription_capability_copy() -> None:
    clara_page = (STATIC_ROOT / "shared" / "clara" / "index.html").read_text(
        encoding="utf-8"
    )

    assert '"capabilities.transcribe.title": "Transcribe a meeting or recording"' in (
        clara_page
    )
    assert (
        '"capabilities.transcribe.title": "Transcribe una reunión o una grabación"'
        in clara_page
    )
    assert "local transcript for speaker attribution and review" in clara_page
    assert "transcripción local para atribuir los hablantes" in clara_page
