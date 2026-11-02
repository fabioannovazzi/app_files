"""Click the real MCP resource through both entry points in Chromium."""

from __future__ import annotations

import json
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from tests.plugins import test_journal_bank_reconciliation_plugin as bank
from tests.plugins.test_vera_native_inps import inps_run  # noqa: F401
from tests.plugins.test_vera_native_sari_review import prepared_sari  # noqa: F401
from tests.plugins.test_vera_native_workspace import (
    ROOT,
    archived_review_binding,
    configure,
)

__all__: list[str] = []


@contextmanager
def review_host(env, *, empty=False):
    """Serve the packaged resource over MCP in an isolated Chromium host."""
    package = os.environ.get("VERA_REVIEW_PACKAGE_ROOT")
    server = (
        Path(package) / "scripts/on_demand_mcp.cjs"
        if package
        else ROOT / "plugins/vera/mcp/workspace.cjs"
    )
    with (
        subprocess.Popen(
            ["node", str(server)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            env=env,
        ) as worker,
        sync_playwright() as runtime,
    ):

        def rpc(method, params):
            assert worker.stdin and worker.stdout
            worker.stdin.write(
                json.dumps(
                    {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
                )
                + "\n"
            )
            worker.stdin.flush()
            message = json.loads(worker.stdout.readline())
            assert "error" not in message, message.get("error")
            return message["result"]

        try:
            rpc(
                "initialize",
                {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "review-test", "version": "1"},
                },
            )
            worker.stdin.write(
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
                + "\n"
            )
            worker.stdin.flush()
            source = rpc("resources/read", {"uri": "ui://vera/workspace-v1.html"})[
                "contents"
            ][0]["text"]
            browser = runtime.chromium.launch()
            page = browser.new_page(viewport={"width": 560, "height": 900})
            page.set_default_timeout(15000)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))

            def call_from_panel(params):
                result = rpc("tools/call", params)
                if empty and params["name"] == "vera_workspace_view":
                    result["_meta"]["workspace"].update(
                        items=[], selection=None, total=0, has_more=False
                    )
                return result

            page.expose_function("mcpCall", call_from_panel)
            page.route(
                "https://codex.test/",
                lambda route: route.fulfill(
                    content_type="text/html",
                    body="<style>body{margin:0}iframe{display:block;width:100%;height:95vh;border:0}</style><iframe></iframe>",
                ),
            )
            page.goto("https://codex.test/")
            page.evaluate(
                """() => {
              window.addEventListener('message', async event => {
                const m=event.data, win=event.source;
                if(m.method==='ui/initialize') win.postMessage({jsonrpc:'2.0',id:m.id,result:{hostContext:{displayMode:'fullscreen'}}},'*');
                if(m.method==='tools/call') win.postMessage({jsonrpc:'2.0',id:m.id,result:await window.mcpCall(m.params)},'*');
                if(m.method==='ui/notifications/initialized') window.ready=true;
              });
            }"""
            )

            def mount(name, args):
                launch = rpc("tools/call", {"name": name, "arguments": args})
                assert not launch.get("isError"), launch
                page.evaluate(
                    "(html)=>{window.ready=false;document.querySelector('iframe').srcdoc=html}",
                    source,
                )
                page.wait_for_function("window.ready")
                page.evaluate(
                    "(params)=>document.querySelector('iframe').contentWindow.postMessage({jsonrpc:'2.0',method:'ui/notifications/tool-result',params},'*')",
                    launch,
                )
                return page.frame_locator("iframe")

            yield page, mount, errors
            browser.close()
        finally:
            if worker.stdin:
                worker.stdin.close()


@pytest.mark.parametrize("scenario", ["several", "one", "empty"])
def test_chat_and_archive_show_same_saved_bank_editor_in_browser(
    tmp_path, monkeypatch, scenario
):
    prepare = (
        bank._prepare_closed_mcp_review_run
        if scenario == "one"
        else bank._prepare_sealed_mcp_review_run
    )
    output, _, review, _, _ = prepare(tmp_path, portable=True)
    binding, _ = archived_review_binding(output, "journal-bank-reconciliation")
    env = {**os.environ, **configure(monkeypatch, tmp_path, [binding])}
    kind = "matched_pair" if scenario == "one" else "unmatched_bank"
    item = next(row for row in review["items"] if row["item_type"] == kind)
    with review_host(env, empty=scenario == "empty") as (page, mount, errors):

        def capture():
            folder = Path(os.environ.get("VERA_REVIEW_SCREENSHOTS", tmp_path))
            folder.mkdir(exist_ok=True, parents=True)
            page.screenshot(path=folder / f"bank-{scenario}.png")

        chat = mount("vera_open_review", {"work_ref": binding["work_ref"]})
        if scenario == "empty":
            expect(
                chat.get_by_text("Nessun elemento da rivedere.", exact=True)
            ).to_be_visible()
            expect(chat.get_by_role("combobox")).to_have_count(0)
            expect(chat.get_by_role("searchbox")).to_have_count(0)
            capture()
            return
        if scenario == "one":
            initial = chat.locator("main").inner_text()
            for label in (
                "Copia percorso",
                "Solo copia JSON",
                "decisioni selezionate",
                "Impatto decisione",
                "Tutti gli stati",
                "ui_decisions.json",
                binding["run_id"],
            ):
                assert label.casefold() not in initial.casefold()
            expect(chat.get_by_role("progressbar")).to_have_count(0)
            expect(
                chat.get_by_role("button", name="Salva decisione", exact=True)
            ).to_have_count(0)
            expect(chat.get_by_role("searchbox")).to_have_count(0)
            expect(chat.locator("button.finding")).to_have_count(0)
            expect(
                chat.get_by_text(
                    "Movimento bancario e scrittura del giornale abbinati.",
                    exact=True,
                )
            ).to_be_visible()
            expect(
                chat.get_by_role("button", name="Precedenti", exact=True)
            ).to_have_count(0)
            capture()
            return
        chat.get_by_text("Scegli un elemento", exact=False).click()
        chat.locator('[data-review-item="' + item["id"] + '"]').click()
        expect(chat.locator("#app")).to_have_attribute("aria-busy", "false")
        chat.get_by_role("combobox", name="Decisione").click()
        chat.get_by_role("option", name="Da chiarire", exact=True).click()
        note = chat.get_by_label("Nota del revisore")
        note.fill("Please verify this fee")
        page.evaluate(
            """(route) => document.querySelector("iframe").contentWindow.postMessage({
            jsonrpc:"2.0",method:"ui/notifications/tool-result",params:{_meta:{workspace:route}}
        },"*")""",
            {
                "kind": "review_route",
                "view": "items",
                "workflow": "journal-bank-reconciliation",
                "work_ref": binding["work_ref"],
            },
        )
        expect(note).to_have_value("Please verify this fee")
        expect(chat.get_by_label("Valore da modificare")).to_be_hidden()
        expect(chat.get_by_label("Documenti richiesti", exact=True)).to_be_hidden()
        chat.get_by_role(
            "checkbox", name="Ho verificato questo elemento", exact=False
        ).check()
        chat.get_by_role("button", name="Salva decisione", exact=True).click()
        expect(
            chat.get_by_text("Decisione salvata · Da chiarire", exact=False).first
        ).to_be_visible()
        assert (
            json.loads((output / "ui_decisions.json").read_bytes())["decisions"][0][
                "reviewer_note"
            ]
            == "Please verify this fee"
        )

        archive = mount("vera_workspace_open", {})
        archive.get_by_role("button", name="Apri lavoro →").click()
        expect(archive.get_by_label("Nota del revisore")).to_have_value(
            "Please verify this fee"
        )
        expect(
            archive.get_by_role("button", name="Precedenti", exact=True)
        ).to_have_count(0)
        visible = archive.locator("main").inner_text()
        assert binding["run_id"] not in visible
        assert "ui_decisions.json" not in visible
        capture()
        assert errors == []


@pytest.mark.parametrize(
    ("fixture", "open_item", "decision", "edit", "documents"),
    [
        (
            "inps_run",
            "Consulta evidenza e riscontro",
            "Riscontro su questo elemento",
            "Richiedo una modifica",
            "Richiedo documenti",
        ),
        (
            "prepared_sari",
            "Consulta e riesamina",
            "Decisione sul rilievo corrente",
            "Modifica",
            "Richiedi documenti",
        ),
    ],
)
def test_specialist_review_shows_only_fields_for_selected_action(
    request, tmp_path, fixture, open_item, decision, edit, documents
):
    """Switch real choices in the prepared case without losing a private draft."""
    _, binding, _ = request.getfixturevalue(fixture)
    with review_host(os.environ.copy()) as (page, mount, errors):
        panel = mount("vera_open_review", {"work_ref": binding["work_ref"]})
        panel.get_by_role("button", name=open_item, exact=True).first.click()
        select = panel.get_by_role("combobox", name=decision, exact=True)
        correction = panel.get_by_label("Modifica richiesta", exact=True)
        required = panel.get_by_label("Documenti richiesti, uno per riga", exact=True)
        expect(select).to_be_visible()
        expect(correction).to_be_hidden()
        expect(required).to_be_hidden()
        visible = panel.locator("main").inner_text()
        assert "fact id" not in visible
        assert "evidence count" not in visible
        if fixture == "inps_run":
            expect(
                panel.get_by_role("heading", name="Decorrenza del rapporto")
            ).to_be_visible()
            expect(panel.locator("blockquote")).to_have_text(
                "decorre dal 1 gennaio 2021"
            )
        select.click()
        panel.get_by_role("option", name=edit, exact=True).click()
        correction.fill("Correggere la data")
        expect(required).to_be_hidden()
        select.click()
        panel.get_by_role("option", name=documents, exact=True).click()
        expect(correction).to_be_hidden()
        required.fill("Documento originale")
        select.click()
        panel.get_by_role("option", name=edit, exact=True).click()
        expect(correction).to_have_value("Correggere la data")
        expect(required).to_be_hidden()
        panel.locator("body").evaluate(
            "(body) => body.ownerDocument.defaultView.scrollTo(0, 0)"
        )
        folder = Path(os.environ.get("VERA_REVIEW_SCREENSHOTS", tmp_path))
        folder.mkdir(exist_ok=True, parents=True)
        page.screenshot(path=folder / f"{binding['workflow_id']}.png")
        assert errors == []


def test_each_registered_work_opens_only_its_own_reader(tmp_path):
    """Exercise the shipped panel's dispatch; the case read ends at the local boundary."""
    routes = json.loads((ROOT / "plugins/vera/ui/review-routes.json").read_bytes())
    domain_tools = {
        "adeguati-assetti": "assetti",
        "aml-review": "aml",
        "bandi-agevolazioni": "bandi",
        "browser-automation": "browser",
        "business-planning": "business_plan",
        "business-valuation": "valuation",
        "centrale-rischi-review": "cr",
        "composizione-negoziata": "cnc",
        "comunicazione-professionale": "communication",
        "esg-reporting-assurance": "esg",
        "financial-analysis": "financial",
        "fusione-guidata": "fusion",
        "invoice-xml": "invoice",
        "lipe": "lipe",
        "management-control-pack": "management",
        "passive-invoice-audit": "passive",
        "patent-box-review": "patent_box",
        "presenza-digitale-studio": "website",
        "previdenza-inps": "inps",
        "rating-legalita": "rating",
        "registro-imprese-sari": "sari_review",
        "sales-plan": "sales_plan",
        "scissione-guidata": "scissione",
        "trasformazione": "transformation",
        "variance-analysis": "variance",
    }
    assert {k for k, v in routes.items() if v == "task"} == set(domain_tools)
    html = subprocess.check_output(
        [
            "node",
            "-e",
            "process.stdout.write(require('./plugins/vera/mcp/workspace.cjs').resource().contents[0].text)",
        ],
        cwd=ROOT,
        text=True,
    )
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        page.route(
            "https://review.test/",
            lambda route: route.fulfill(
                content_type="text/html", body="<iframe></iframe>"
            ),
        )
        page.goto("https://review.test/")
        page.evaluate(
            """() => {
          window.reads = [];
          window.addEventListener("message", event => {
            const m = event.data, frame = event.source;
            if(m.method === "ui/initialize") frame.postMessage({jsonrpc:"2.0",id:m.id,result:{}}, "*");
            if(m.method === "ui/notifications/initialized") window.ready = true;
            if(m.method === "tools/call") {
              window.reads.push(m.params);
              frame.postMessage({jsonrpc:"2.0",id:m.id,error:{code:-32000,message:"End of route probe"}}, "*");
            }
          });
        }"""
        )
        page.evaluate("(html) => document.querySelector('iframe').srcdoc = html", html)
        page.wait_for_function("window.ready")
        for name, view in routes.items():
            page.evaluate(
                """(route) => {
              window.reads = [];
              const frame = document.querySelector("iframe").contentWindow;
              frame.postMessage({jsonrpc:"2.0",method:"ui/notifications/tool-result",params:{_meta:{workspace:route}}}, "*");
            }""",
                {
                    "kind": "review_route",
                    "workflow": name,
                    "view": view,
                    "work_ref": "fixture-" + name,
                },
            )
            status = page.frame_locator("iframe").locator("#status")
            if view is None:
                expect(status).to_have_text(
                    "Il risultato di questo lavoro si consulta nella chat e nei documenti consegnati."
                )
                assert page.evaluate("window.reads") == []
            else:
                page.wait_for_function("window.reads.length > 0", timeout=2000)
                reads = page.evaluate("window.reads")
                assert {row["arguments"]["work_ref"] for row in reads} == {
                    "fixture-" + name
                }
                if view == "items":
                    assert [row["name"] for row in reads] == ["vera_workspace_view"]
                else:
                    prefix = f"vera_workspace_{domain_tools[name]}_"
                    assert all(row["name"].startswith(prefix) for row in reads), (
                        name,
                        reads,
                    )
                expect(status).to_have_text("End of route probe")
        browser.close()
