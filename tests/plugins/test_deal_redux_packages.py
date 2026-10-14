from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.plugins.test_lucia_negotiation import tracked_document

ROOT = Path(__file__).resolve().parents[2]


class WorkAreaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.area = ""
        self.negotiation_area = ""

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "article":
            self.area = attrs.get("id", "")
        if tag == "a" and "posizioni-negoziali/index.html" in attrs.get("href", ""):
            self.negotiation_area = self.area

    def handle_endtag(self, tag):
        if tag == "article":
            self.area = ""


def test_breadcrumb_returns_to_the_work_area_containing_each_product_link():
    navigation = (ROOT / "static/shared/function-page-navigation.js").read_text(
        encoding="utf-8"
    )
    mapping = re.search(
        r'^\s*"posizioni-negoziali":\s*(\[.*\]),\s*$', navigation, re.MULTILINE
    )
    assert mapping is not None
    contexts = json.loads(mapping.group(1))
    for product in ("vera", "lucia"):
        parser = WorkAreaParser()
        parser.feed(
            (ROOT / f"static/shared/{product}/index.html").read_text(encoding="utf-8")
        )
        assert parser.negotiation_area
        assert [product, parser.negotiation_area] in contexts


def test_help_copy_is_complete_in_five_languages_and_preserves_product_links():
    node = shutil.which("node")
    if node is None:
        node = str(
            Path.home()
            / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
        )
    result = subprocess.run(
        [
            node,
            "-e",
            "global.window={};require(process.argv[1]);process.stdout.write(JSON.stringify(window.MPARANZA_FUNCTION_PAGES));",
            str(ROOT / "static/shared/deal-redux-pages.js"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    page = json.loads(result.stdout)["posizioni-negoziali"]
    assert page["shared"] is True
    assert set(page["copy"]) == {"it", "en", "fr", "de", "es"}
    for copy in page["copy"].values():
        assert copy["modelDataStatus"] == "relevant"
        assert all(
            copy[key].strip()
            for key in [
                "name",
                "summary",
                "input",
                "work",
                "output",
                "prompt",
                "modelData",
                "professionalRole",
            ]
        )
        assert "65c987e33045ac1beb5c7490859efb64a057bfbe" in copy["useWhen"]
        assert "Mike" in copy["useWhen"]
    for product in ("vera", "lucia"):
        source = (ROOT / f"static/shared/{product}/index.html").read_text(
            encoding="utf-8"
        )
        assert f"../posizioni-negoziali/index.html?from={product}" in source
    page_source = (ROOT / "static/shared/posizioni-negoziali/index.html").read_text(
        encoding="utf-8"
    )
    assert "product-function-page.js" in page_source
    assert "deal-redux-pages.js" in page_source


def test_upstream_attribution_snapshot_matches_its_recorded_bytes():
    upstream = ROOT / "plugins/_shared/vendor/modules/deal_redux/references/upstream"
    provenance = json.loads((upstream / "PROVENANCE.json").read_text(encoding="utf-8"))
    for source in provenance["files"]:
        assert (
            hashlib.sha256((upstream / source["bundled_file"]).read_bytes()).hexdigest()
            == source["sha256"]
        )
    data = (upstream / "deal-redux.md").read_bytes()
    assert (
        hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        == "0f746a736a332d79a9ab466e6208ebe40c58ab48"
    )


def command(root: Path, helper: str, *arguments: str) -> None:
    helpers = (
        root / "vendor/modules/scripts" if root.name == "vera" else root / "scripts"
    )
    result = subprocess.run(
        [sys.executable, str(helpers / helper), *arguments],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("product", ["vera", "lucia"])
@pytest.mark.parametrize(
    "host", ["plugin", "chatgpt-upload", "claude-plugin", "antigravity-plugin"]
)
@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
def test_shipped_negotiation_helpers_deliver_bound_complete_outputs(
    tmp_path, product, host, language
):
    filename = ROOT / "plugin_packages" / product / f"{product}-{host}.zip"
    if host == "antigravity-plugin":
        filename = ROOT / "static/shared" / product / "downloads" / filename.name
    helpers = "vendor/modules/scripts" if product == "vera" else "scripts"
    with ZipFile(filename) as archive:
        entry = next(
            n
            for n in archive.namelist()
            if n.endswith(helpers + "/legal_negotiation.py")
        )
        prefix = entry.removesuffix(helpers + "/legal_negotiation.py")
        skill = (
            "mparanza-posizioni-negoziali"
            if host == "claude-plugin"
            else "posizioni-negoziali"
        )
        assert prefix + f"skills/{skill}/SKILL.md" in archive.namelist()
        package = tmp_path / product
        for name in archive.namelist():
            relative = name.removeprefix(prefix)
            if (
                name.startswith(prefix)
                and (
                    relative.startswith(helpers + "/legal_")
                    or relative.startswith("vendor/modules/courseware/assets/")
                    or relative.startswith("vendor/modules/deal_redux/")
                )
                and not name.endswith("/")
            ):
                target = package / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
        assert (
            archive.read(entry)
            == (ROOT / "plugins/lucia/scripts/legal_negotiation.py").read_bytes()
        )
    provenance = json.loads(
        (
            package / "vendor/modules/deal_redux/references/upstream/PROVENANCE.json"
        ).read_text(encoding="utf-8")
    )
    assert provenance == json.loads(
        (
            ROOT
            / "plugins/_shared/vendor/modules/deal_redux/references/upstream/PROVENANCE.json"
        ).read_text(encoding="utf-8")
    )
    source = tracked_document(tmp_path)
    source_bytes = source.read_bytes()
    run = tmp_path / "round-1"
    command(
        package,
        "legal_documents.py",
        "prepare",
        "--run-dir",
        str(run),
        "--workflow",
        "revisione-documentale",
        "--file",
        str(source),
        "--topic",
        "Negoziazione sintetica",
    )
    command(
        package,
        "legal_negotiation.py",
        "scaffold",
        "--run-dir",
        str(run),
        "--source",
        "D001",
    )
    path = run / "negotiation.json"
    review = json.loads(path.read_text(encoding="utf-8"))
    review["context"].update(
        {
            k: "Synthetic supplied context"
            for k in review["context"]
            if k != "assumptions"
        }
    )
    review["context"]["language"] = language
    inventory = json.loads(
        (run / "negotiation-inventory.json").read_text(encoding="utf-8")
    )
    review["positions"] = [
        {
            "id": "P1",
            "title": "Liability limit",
            "effect": "The proposed limit falls from EUR 100,000 to EUR 50,000.",
            "grouping_reason": "Both revisions amend the same limit.",
            "change_ids": [
                c["id"]
                for c in inventory["changes"]
                if c["paragraph_anchor"] == "word/document.xml#p1"
            ],
            "citations": [
                {
                    "source_id": "D001",
                    "anchor": "word/document.xml#p1",
                    "quote": "EUR 50.000",
                }
            ],
            "response": "",
        }
    ]
    assigned = set(review["positions"][0]["change_ids"])
    review["other_changes"] = [
        {
            "change_id": c["id"],
            "reason": "Retained in the complete ledger; further substantive review pending.",
        }
        for c in inventory["changes"]
        if c["id"] not in assigned
    ]
    review["comment_reviews"] = [
        {
            "comment_id": c["id"],
            "analysis": "The author's assertion does not establish the legal effect.",
            "position_ids": [],
        }
        for c in inventory["comments"]
    ]
    path.write_text(json.dumps(review), encoding="utf-8")
    command(
        package,
        "legal_negotiation.py",
        "render",
        "--run-dir",
        str(run),
        "--review",
        str(path),
        "--product",
        product.title(),
    )
    command(package, "legal_negotiation.py", "verify", "--run-dir", str(run))
    html = (run / "negotiation.html").read_text(encoding="utf-8")
    assert "@font-face" in html
    assert all(c["id"] in html for c in inventory["changes"])
    assert source.read_bytes() == source_bytes
    assert (run / "negotiation-reviewed.json").read_bytes() == path.read_bytes()
    assert len(inventory["changes"]) == 9
    assert len(inventory["comments"]) == 2
    assert (
        hashlib.sha256((run / "negotiation-inventory.json").read_bytes()).hexdigest()
        == review["inventory_sha256"]
    )
