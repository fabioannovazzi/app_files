from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "static" / "shared" / "bilancio-xbrl-it" / "prototype"
PAGOPA_LANDING = (
    "https://amministrazionetrasparente.pagopa.it/"
    "archivio29_bilanci_0_3105_731_1.html"
)
PAGOPA_PDF = (
    "https://pagopa.portaleamministrazionetrasparente.it/archiviofile/"
    "pagopa/utente2005/Bilanci%20(dal%202022)/Bilancio%202024/"
    "PAGOPA_Bilancio%20al%2031%20dicembre%202024_v.del%2020.05.2025%20"
    "nuovo%20Ateco_signed_oscurato.pdf"
)


def _read(name: str) -> str:
    return (PROTOTYPE / name).read_text(encoding="utf-8")


def test_bilancio_public_prototype_has_a_stable_source_backed_entrypoint() -> None:
    page = _read("index.html")
    function_copy = (
        ROOT / "static" / "shared" / "product-function-pages.js"
    ).read_text(encoding="utf-8")
    renderer = (
        ROOT / "static" / "shared" / "product-function-page.js"
    ).read_text(encoding="utf-8")

    assert (
        '<link rel="canonical" href="https://mparanza.com/static/shared/'
        'bilancio-xbrl-it/prototype/">'
    ) in page
    assert PAGOPA_LANDING in page
    assert PAGOPA_PDF in page
    assert (
        'publicExampleHref: "/static/shared/bilancio-xbrl-it/prototype/"'
        in function_copy
    )
    assert f'publicExampleSourceHref: "{PAGOPA_LANDING}"' in function_copy
    assert "const publicExample = page.publicExampleHref" in renderer
    assert renderer.index("${publicExample}") < renderer.index(
        '<section class="function-model-data"'
    )


def test_bilancio_public_prototype_preserves_the_professional_boundary() -> None:
    page = _read("index.html")
    script = _read("prototype.js")

    for required in (
        "Nessun file del visitatore viene letto o caricato.",
        "La demo non approva, firma, valida o deposita un XBRL.",
        "Il bilancio di verifica non è stato fornito.",
        "La disponibilità di un file non equivale alla sua approvazione",
        "Nessuna approvazione professionale",
    ):
        assert required in page + script

    for forbidden in (
        "fetch(",
        "XMLHttpRequest",
        'type="file"',
        "/api/",
        "/private/tmp",
    ):
        assert forbidden not in page + script


def test_bilancio_public_prototype_keeps_decisions_local_and_resettable() -> None:
    script = _read("prototype.js")

    for required in (
        'const STORAGE_KEY = "mparanza-vera-bilancio-public-demo-v1";',
        "window.localStorage.setItem",
        "window.localStorage.removeItem",
        "public_source_only: true",
        "actual_trial_balance_ingested: false",
        "sent_to_mparanza: false",
        "sent_to_model: false",
        "Aggiungi una motivazione prima di rinviare questa voce.",
    ):
        assert required in script


def test_bilancio_public_prototype_makes_version_dependencies_explicit() -> None:
    page = _read("index.html")
    script = _read("prototype.js")

    assert "demo_rev_7" in page
    assert 'state.revision = "demo_rev_8";' in script
    assert "la versione precedente non viene sovrascritta" in page
    for dependent_area in (
        "Mappature",
        "Prospetti",
        "Schede",
        "Nota",
        "Validazione",
    ):
        assert f'"{dependent_area}"' in script
    assert "da ricalcolare" in script


def test_bilancio_public_prototype_ends_with_the_governed_model_data_section() -> (
    None
):
    page = _read("index.html")
    main = page.split('<main id="main-content">', 1)[1].split("</main>", 1)[0]
    section_starts = list(re.finditer(r"<section\b", main))
    model_data_start = main.index('<section class="function-model-data"')

    assert section_starts[-1].start() == model_data_start
    assert 'data-model-data-workflow="bilancio-xbrl-it"' in main
    assert 'data-model-data-status="relevant"' in main
    model_data = main[model_data_start:]
    for required in (
        "Quali dati arrivano al modello",
        "Questa demo pubblica non invia dati a un modello.",
        "non vengono inviate a Mparanza, OpenAI o altri servizi",
        "Nel workflow Vera operativo",
        "non c’è anonimizzazione o pseudonimizzazione automatica",
        "non può accettare righe, fatti, mappature, informative, approvazione o XBRL",
    ):
        assert required in model_data
