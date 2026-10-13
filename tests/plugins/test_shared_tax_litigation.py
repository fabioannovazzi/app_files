from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "plugins/_shared/vendor/modules/italian_tax_litigation"
COWORK_REFERENCE_NOTE = b"""> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

"""


def _archive_path(product: str, suffix: str) -> Path:
    if suffix == "antigravity":
        return (
            ROOT
            / "static/shared"
            / product
            / "downloads"
            / f"{product}-antigravity-plugin.zip"
        )
    return ROOT / "plugin_packages" / product / f"{product}-{suffix}"


@pytest.mark.parametrize("product", ["vera", "lucia"])
@pytest.mark.parametrize(
    "suffix", ["plugin.zip", "chatgpt-upload.zip", "claude-plugin.zip", "antigravity"]
)
@pytest.mark.parametrize(
    "relative",
    [
        "workflow.md",
        "references/procedura-italiana.md",
        "references/termini-e-ripresa.md",
        "references/fonti.md",
        "references/evidence-and-progress.md",
    ],
)
def test_each_host_contains_the_canonical_procedural_guide(
    product: str, suffix: str, relative: str
) -> None:
    """A release cannot ship an independently drifting procedural copy."""
    filename = _archive_path(product, suffix)
    target = f"vendor/modules/italian_tax_litigation/{relative}"
    with ZipFile(filename) as archive:
        name = next(name for name in archive.namelist() if name.endswith(target))
        assert (
            archive.read(name).removeprefix(COWORK_REFERENCE_NOTE)
            == (GUIDE / relative).read_bytes()
        )


def _command(
    root: Path, name: str, *arguments: str
) -> subprocess.CompletedProcess[str]:
    """Execute a real packaged helper using the existing test environment."""
    helper_dir = root / "vendor/modules/scripts"
    if not helper_dir.is_dir():
        helper_dir = root / "scripts"
    result = subprocess.run(
        [
            sys.executable,
            str(helper_dir / name),
            *arguments,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result


@pytest.mark.parametrize(
    "suffix", ["plugin.zip", "chatgpt-upload.zip", "claude-plugin.zip", "antigravity"]
)
@pytest.mark.parametrize("product_name", ["vera", "lucia"])
@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
def test_packaged_product_prepares_and_resumes_without_claiming_filing(
    tmp_path: Path, suffix: str, product_name: str, language: str
) -> None:
    """Exercise the shipped dependencies, Vera report and unresolved external act."""
    filename = _archive_path(product_name, suffix)
    helper_subdir = "vendor/modules/scripts" if product_name == "vera" else "scripts"
    with ZipFile(filename) as archive:
        helper = next(
            name
            for name in archive.namelist()
            if name.endswith(helper_subdir + "/legal_matter.py")
        )
        prefix = helper.removesuffix(helper_subdir + "/legal_matter.py")
        names = [
            name
            for name in archive.namelist()
            if name.startswith(prefix + helper_subdir + "/legal_")
        ]
        for name in names:
            target = tmp_path / "package" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
    product = tmp_path / "package" / prefix
    source = tmp_path / "ricevuta.txt"
    statement = "Ricevuta fittizia: ricorso notificato il 5 ottobre 2026."
    source.write_text(statement + "\n", encoding="utf-8")
    run = tmp_path / "pratica"
    _command(
        product,
        "legal_documents.py",
        "prepare",
        "--run-dir",
        str(run),
        "--workflow",
        "revisione-documentale",
        "--file",
        str(source),
        "--topic",
        "Notifica",
    )
    review_path = run / "review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["context"].update(
        represented_party="Parte fittizia",
        jurisdiction="Italia; prova tecnica",
        relationship="Incarico simulato",
        formation="Documento fittizio",
        forum="Non verificato",
        legal_basis="Nessuna conclusione giuridica; sola prova tecnica",
        firm_instructions="Nessun modello",
        instructions="Verificare il pacchetto locale",
        language=language,
    )
    review["coverage"]["D001"]["reviewed_anchors"] = ["line:1"]
    review["items"][0].update(
        status="supported",
        summary="Dichiarazione nel testo fittizio",
        reasoning="Il testo non certifica la notifica né un deposito",
        proposal="Acquisire la prova reale",
        citations=[{"source_id": "D001", "anchor": "line:1", "quote": statement}],
    )
    review_path.write_text(json.dumps(review), encoding="utf-8")
    _command(
        product,
        "legal_documents.py",
        "render",
        "--run-dir",
        str(run),
        "--review",
        str(review_path),
        "--product",
        product_name.title(),
    )
    _command(
        product,
        "legal_matter.py",
        "init",
        "--run-dir",
        str(run),
        "--kind",
        "contenzioso-tributario",
        "--purpose",
        "Preparare la pratica fittizia",
    )
    state = json.loads((run / "matter.json").read_text(encoding="utf-8"))
    state["language"] = language
    state["stages"] = [
        {
            "id": "preparazione",
            "label": "Preparazione",
            "status": "done",
            "note": "Rapporto locale prodotto",
            "outputs": ["review.html"],
        },
        {
            "id": "deposito",
            "label": "Prova del deposito",
            "status": "pending",
            "note": "Non acquisita",
            "outputs": [],
        },
    ]
    state["questions"] = [
        {
            "id": "Q1",
            "question": "È disponibile una ricevuta reale del deposito?",
            "reason": "La preparazione non prova l'azione esterna",
            "blocks": ["deposito"],
            "status": "open",
            "answer": "",
            "citations": [],
        }
    ]
    proposed = run / "proposta.json"
    proposed.write_text(json.dumps(state), encoding="utf-8")
    _command(
        product,
        "legal_matter.py",
        "save",
        "--run-dir",
        str(run),
        "--state",
        str(proposed),
        "--expected-revision",
        "0",
    )
    result = _command(product, "legal_matter.py", "status", "--run-dir", str(run))
    _command(product, "legal_matter.py", "render", "--run-dir", str(run))

    html = (run / "review.html").read_text(encoding="utf-8")
    labels = json.loads(
        (product / helper_subdir / "legal_documents_labels.json").read_text(
            encoding="utf-8"
        )
    )[language]
    reviewer_prefix = "professional_" if product_name == "vera" else ""
    assert "<h1>" + product_name.title() + " · " in html
    assert labels[reviewer_prefix + "complete"] in html
    assert labels[reviewer_prefix + "quote_meaning"] in html
    if product_name == "vera":
        assert labels["complete"] not in html
        assert labels["quote_meaning"] not in html
    assert json.loads(result.stderr)["blocked_stages"] == {"deposito": ["Q1"]}
    assert (
        json.loads((run / "matter.json").read_text(encoding="utf-8"))["revision"] == 1
    )
    assert (run / "matter.html").is_file()


def test_vera_help_links_the_shared_function_and_keeps_explanation_on_its_page() -> (
    None
):
    page = (ROOT / "static/shared/vera/index.html").read_text(encoding="utf-8")
    assert 'data-vera-workflow="contenzioso-tributario"' in page
    assert "../contenzioso-tributario/index.html?from=vera" in page
    assert "La guida è una base editoriale" not in page


def test_shared_progress_reference_resolves_without_a_product_specific_skill() -> None:
    text = (GUIDE / "references/termini-e-ripresa.md").read_text(encoding="utf-8")
    assert "`evidence-and-progress.md`" in text
    assert (GUIDE / "references/evidence-and-progress.md").is_file()
    assert "../../revisione-contratti/" not in text
