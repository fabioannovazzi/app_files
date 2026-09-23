from __future__ import annotations

import json
import posixpath
import re
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]

DOCUMENT_SKILLS = {
    "revisione-contratti",
    "confronto-documenti",
    "revisione-documentale",
    "redazione-da-modello",
    "controllo-documento",
    "estrazione-clausole",
    "metodo-studio",
    "verifica-citazioni",
    "contenzioso-civile",
    "operazioni-ma",
    "lavoro",
    "recupero-crediti",
}


def _run_packaged_script(plugin: Path, name: str, *arguments: str) -> None:
    completed = subprocess.run(
        [sys.executable, str(plugin / "scripts" / name), *arguments],
        cwd=plugin,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize(
    "filename",
    ["lucia-plugin.zip", "lucia-chatgpt-upload.zip", "lucia-claude-plugin.zip"],
)
def test_document_workflows_execute_from_each_complete_package(tmp_path, filename):
    """Exercise packaged dependencies/assets, not merely matching ZIP versions."""
    with ZipFile(ROOT / "plugin_packages" / "lucia" / filename) as archive:
        archive.extractall(tmp_path / "package")
    script = next((tmp_path / "package").rglob("scripts/legal_playbook.py"))
    plugin = script.parent.parent
    available = {p.parent.name for p in (plugin / "skills").glob("*/SKILL.md")}
    assert DOCUMENT_SKILLS <= available

    source = tmp_path / "accordo.txt"
    source.write_text("Accordo fittizio. Durata: dodici mesi.\n", encoding="utf-8")
    run = tmp_path / "run"
    editor = tmp_path / "editor.html"
    _run_packaged_script(plugin, "legal_playbook.py", "editor", "--out", str(editor))
    _run_packaged_script(
        plugin,
        "legal_playbook.py",
        "prepare",
        "--playbook",
        str(plugin / "assets/playbook-nda.json"),
        "--run-dir",
        str(run),
        "--files",
        str(source),
    )
    _run_packaged_script(plugin, "legal_playbook.py", "inspect", "--run-dir", str(run))
    _run_packaged_script(
        plugin, "legal_proofreading.py", "scaffold", "--run-dir", str(run)
    )
    audit_path = run / "proofreading.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["context"].update(
        represented_party="Non acquisita",
        jurisdiction="Da verificare",
        relationship="Da verificare",
        formation="Da verificare",
        forum="Da verificare",
        legal_basis="Nessuna conclusione giuridica",
    )
    for mapping in audit["documents"]["D001"]["maps"].values():
        mapping["note"] = (
            "Mappa non ancora esaminata: prova di esecuzione del pacchetto."
        )
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
    _run_packaged_script(
        plugin, "legal_proofreading.py", "render", "--run-dir", str(run)
    )
    _run_packaged_script(
        plugin,
        "legal_citations.py",
        "scaffold",
        "--run-dir",
        str(run),
        "--document",
        "D001",
        "--scope",
        "Riferimenti nel documento selezionato",
    )
    _run_packaged_script(plugin, "legal_citations.py", "render", "--run-dir", str(run))
    _run_packaged_script(plugin, "legal_matter.py", "render", "--run-dir", str(run))

    assert "__FONT_DATA__" not in editor.read_text(encoding="utf-8")
    assert (run / "proofreading.html").stat().st_size > 0
    assert (run / "citations.html").stat().st_size > 0
    assert (run / "matter.html").stat().st_size > 0


@pytest.mark.parametrize(
    "filename",
    ["lucia-plugin.zip", "lucia-chatgpt-upload.zip", "lucia-claude-plugin.zip"],
)
def test_packaged_lucia_workflow_references_resolve(filename: str) -> None:
    with ZipFile(ROOT / "plugin_packages" / "lucia" / filename) as archive:
        names = archive.namelist()
        for workflow in ("comunicazione-professionale", "presenza-digitale-studio"):
            wrapper = min(
                (
                    name
                    for name in names
                    if name.endswith(f"skills/{workflow}/SKILL.md")
                ),
                key=len,
            )
            text = " ".join(archive.read(wrapper).decode().split())
            assert (
                "`Plugin Improvement Feedback` section in `../lucia/SKILL.md`" in text
            )
            target = posixpath.normpath(
                posixpath.join(posixpath.dirname(wrapper), "../lucia/SKILL.md")
            )
            assert "## Plugin Improvement Feedback" in archive.read(target).decode()

        skill = next(
            name
            for name in names
            if name.endswith(
                "modules/apertura-pratica/skills/apertura-pratica/SKILL.md"
            )
        )
        reference = re.search(
            r"`([^`]*references/source-registry.json)`", archive.read(skill).decode()
        )
        assert reference is not None
        target = posixpath.normpath(
            posixpath.join(posixpath.dirname(skill), reference.group(1))
        )
        assert target in names


@pytest.mark.parametrize(
    "filename",
    ["lucia-plugin.zip", "lucia-chatgpt-upload.zip", "lucia-claude-plugin.zip"],
)
def test_italian_method_and_shared_references_are_available_in_every_host(filename):
    with ZipFile(ROOT / "plugin_packages" / "lucia" / filename) as archive:
        names = archive.namelist()
        for workflow in (
            "revisione-contratti",
            "confronto-documenti",
            "revisione-documentale",
            "redazione-da-modello",
        ):
            skill = min(
                (
                    name
                    for name in names
                    if name.endswith(f"skills/{workflow}/SKILL.md")
                ),
                key=len,
            )
            references = re.findall(
                r"`([^`]*(?:prassi-italiana|contratti-italiani|colonne-italiane|document-workflow)\.md)`",
                archive.read(skill).decode(),
            )
            assert references
            for relative in references:
                target = posixpath.normpath(
                    posixpath.join(posixpath.dirname(skill), relative)
                )
                assert target in names
                assert archive.read(target).strip()
        guide = next(
            name for name in names if name.endswith("references/prassi-italiana.md")
        )
        sources = posixpath.join(posixpath.dirname(guide), "fonti-italiane.md")
        assert sources in names
