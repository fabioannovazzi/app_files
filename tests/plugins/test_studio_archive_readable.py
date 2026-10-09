"""Human navigation preserves exact ledger evidence and remains portable."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "plugins/studio-archive/scripts"
sys.path.insert(0, str(SCRIPTS))
import client_ledger as ledger
from readable_archive import refresh_readable_archive

from tests.model_data_helpers import write_no_model_report


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.links.extend(
                value for name, value in attrs if name == "href" and value
            )


def case(tmp_path: Path) -> tuple[Path, str, str, dict]:
    root = tmp_path / "Cliente sintetico"
    root.mkdir()
    cid = "client_" + "1" * 24
    ledger.create_client_manifest(root, cid)
    engagement = ledger.create_engagement(root, cid, "Verifiche <script>2026</script>")
    eid = engagement["engagement_id"]
    source = tmp_path / "fonte #1.csv"
    source.write_text("account,amount\nSYN,100.00\n")
    imported = ledger.import_document(root, cid, eid, source, "source")
    run = ledger.prepare_run(
        root,
        cid,
        eid,
        "treasury-forecast",
        "1.0.0",
        input_ids=[imported["receipt"]["input_id"]],
        label="Ottobre",
        purpose="Synthetic saving test",
    )
    return root, cid, eid, run


def finish(root: Path, eid: str, run: dict) -> None:
    rid = run["run"]["run_id"]
    ledger.start_run(root, eid, rid)
    output = Path(run["output_dir"])
    (output / "risultato.csv").write_text("amount\n100.00\n")
    write_no_model_report(output, "treasury-forecast", rid)
    artifacts = [
        dict(
            artifact_id="output." + hashlib.sha256(p.name.encode()).hexdigest()[:20],
            path=p.name,
            purpose="Synthetic result",
            audience="deliverable",
            media_type="text/plain",
        )
        for p in output.iterdir()
        if p.is_file()
    ]
    ledger.finalize_run(root, eid, rid, artifacts)
    ledger.complete_run(root, eid, rid)


def test_completed_view_links_all_artifacts_and_preserves_ledger(
    tmp_path: Path,
) -> None:
    root, cid, eid, run = case(tmp_path)
    finish(root, eid, run)
    manifest = ledger.validate_run_artifacts(root, eid, run["run"]["run_id"])
    before = {
        p.relative_to(root): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (root / "Vera/engagements").rglob("*")
        if p.is_file()
    }
    result = refresh_readable_archive(root, ledger)
    page = next((root / "Vera/Pratiche").glob("*/Previsione*/Indice.html"))
    text = page.read_text()
    assert result["run_count"] == 1
    assert "Esecuzione conclusa" in text
    assert "non equivale ad approvazione" in text
    assert "risultato.csv" in text
    assert all(item["path"] in text for item in manifest["artifacts"])
    assert before == {
        p.relative_to(root): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (root / "Vera/engagements").rglob("*")
        if p.is_file()
    }
    assert "&lt;script&gt;" in Path(result["index_path"]).read_text()
    assert "<script>2026" not in Path(result["index_path"]).read_text()


def test_view_links_survive_client_folder_move(tmp_path: Path) -> None:
    root, cid, eid, run = case(tmp_path)
    finish(root, eid, run)
    refresh_readable_archive(root, ledger)
    moved = tmp_path / "Cliente rinominato"
    root.rename(moved)
    pages = [
        moved / "Vera/APRI ARCHIVIO.html",
        *list((moved / "Vera/Pratiche").rglob("*.html")),
    ]
    for page in pages:
        parser = Links()
        parser.feed(page.read_text())
        assert all((page.parent / unquote(link)).exists() for link in parser.links)
    result = refresh_readable_archive(moved, ledger)
    assert "Cliente rinominato" in Path(result["index_path"]).read_text()
    assert ledger.load_client_manifest(moved)["client_id"] == cid
    assert ledger.validate_run_artifacts(moved, eid, run["run"]["run_id"])


@pytest.mark.parametrize("status", ["prepared", "running", "failed", "cancelled"])
def test_unfinalized_outputs_are_not_presented_as_results(
    tmp_path: Path, status: str
) -> None:
    root, cid, eid, run = case(tmp_path)
    rid = run["run"]["run_id"]
    if status != "prepared":
        ledger.start_run(root, eid, rid)
    if status == "failed":
        ledger.fail_run(root, eid, rid, "Synthetic failure")
    if status == "cancelled":
        ledger.cancel_run(root, eid, rid)
    (Path(run["output_dir"]) / "partial.csv").write_text("not final")
    refresh_readable_archive(root, ledger)
    page = next((root / "Vera/Pratiche").glob("*/Previsione*/Indice.html"))
    assert "Nessun risultato finalizzato" in page.read_text()
    assert "partial.csv" not in page.read_text()


def test_changed_finalized_output_has_explicit_integrity_failure(
    tmp_path: Path,
) -> None:
    root, cid, eid, run = case(tmp_path)
    finish(root, eid, run)
    (Path(run["output_dir"]) / "risultato.csv").write_text("changed")
    refresh_readable_archive(root, ledger)
    page = next((root / "Vera/Pratiche").glob("*/Previsione*/Indice.html"))
    assert "Verifica non superata" in page.read_text()
    assert ">risultato.csv</a>" not in page.read_text()


def test_rebuild_does_not_overwrite_unowned_navigation_file(tmp_path: Path) -> None:
    root, cid, eid, run = case(tmp_path)
    target = root / "Vera/APRI ARCHIVIO.html"
    target.write_text("Human-authored document")
    with pytest.raises(ledger.LedgerError, match="unowned"):
        refresh_readable_archive(root, ledger)
    assert target.read_text() == "Human-authored document"


def test_view_is_rebuildable_without_touching_outputs(tmp_path: Path) -> None:
    root, cid, eid, run = case(tmp_path)
    finish(root, eid, run)
    refresh_readable_archive(root, ledger)
    old = (root / "Vera/APRI ARCHIVIO.html").read_bytes()
    shutil.rmtree(root / "Vera/Pratiche")
    (root / "Vera/APRI ARCHIVIO.html").unlink()
    refresh_readable_archive(root, ledger)
    assert (root / "Vera/APRI ARCHIVIO.html").read_bytes() == old
    assert ledger.validate_run_artifacts(root, eid, run["run"]["run_id"])


def test_cli_creates_readable_client_and_engagement(tmp_path: Path) -> None:
    import os
    import subprocess

    archive = tmp_path / "Studio"
    archive.mkdir()
    env = dict(
        os.environ,
        VERA_STUDIO_ARCHIVE_STATE_DIR=str(tmp_path / "private"),
        VERA_STUDIO_ARCHIVE_SESSION_ID="readable-test-" + tmp_path.name,
    )

    def command(*args: str) -> dict:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "studio_archive.py"), *args],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)

    command("configure", "--archive-root", str(archive))
    created = command("create-client", "--legal-name", "Cliente leggibile")
    assert created["readable_archive"]["status"] == "ready"
    cid = created["client"]["client_id"]
    engagement = command(
        "create-engagement",
        "--client-id",
        cid,
        "--engagement-label",
        "Verifiche ottobre",
    )
    assert engagement["readable_archive"]["engagement_count"] == 1
    assert (
        "Verifiche ottobre"
        in Path(engagement["readable_archive"]["index_path"]).read_text()
    )
    recovered = command("recover-ledger")
    assert recovered["engagement_count"] == 1
