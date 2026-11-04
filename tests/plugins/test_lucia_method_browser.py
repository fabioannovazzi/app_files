"""Exercise the real firm-method MCP resource, UI bridge and durable save."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("width", [400, 1080])
def test_method_native_resource_saves_and_reopens_without_downloads(tmp_path, width):
    package = os.environ.get("LUCIA_REVIEW_PACKAGE_ROOT")
    server = (
        Path(package) / "scripts/on_demand_mcp.cjs"
        if package
        else ROOT / "plugins/lucia/scripts/method_mcp.cjs"
    )
    env = {**os.environ, "LUCIA_METHOD_PYTHON": sys.executable}
    env.update(
        MPARANZA_RUNTIME_ROOT=str(tmp_path / "runtime"),
        MPARANZA_INCIDENT_STATE_DIR=str(tmp_path / "incidents"),
        MPARANZA_INCIDENT_DEVICE_DIR=str(tmp_path / "device"),
        VERA_REPORTING_STATE_DIR=str(tmp_path / "reporting"),
        MPARANZA_INCIDENT_DELIVERY="local-only",
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
            response = json.loads(worker.stdout.readline())
            assert "error" not in response, response
            assert not response["result"].get("isError"), response
            return response["result"]

        try:
            rpc(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "package-browser-test", "version": "1"},
                },
            )
            assert worker.stdin
            worker.stdin.write(
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
                + "\n"
            )
            worker.stdin.flush()
            source = rpc("resources/read", {"uri": "ui://lucia/firm-method-v1.html"})[
                "contents"
            ][0]["text"]
            browser = runtime.chromium.launch()
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.set_default_timeout(10000)
            errors, downloads = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("download", lambda download: downloads.append(download))
            page.expose_function("mcpCall", lambda params: rpc("tools/call", params))
            page.route(
                "https://codex.test/",
                lambda route: route.fulfill(
                    content_type="text/html",
                    body="<style>body{margin:0}iframe{width:100%;height:100vh;border:0}</style><iframe></iframe>",
                ),
            )
            page.goto("https://codex.test/")
            page.evaluate(
                """() => {
                addEventListener('message', async event => {
                    const m=event.data, win=event.source;
                    if(m.method==='ui/initialize')win.postMessage({jsonrpc:'2.0',id:m.id,result:{hostCapabilities:{message:{text:{}},experimental:{'openai/message':{}}}}},'*');
                    if(m.method==='ui/notifications/initialized')window.ready=true;
                    if(m.method==='ui/message'){window.selectedMethod=m.params;win.postMessage({jsonrpc:'2.0',id:m.id,result:{}},'*');}
                if(m.method==='tools/call')win.postMessage({jsonrpc:'2.0',id:m.id,result:await window.mcpCall(m.params)},'*');
                });
            }"""
            )

            def mount(args):
                launch = rpc(
                    "tools/call", {"name": "lucia_method_open", "arguments": args}
                )
                page.evaluate(
                    "html=>{window.ready=false;document.querySelector('iframe').srcdoc=html}",
                    source,
                )
                page.wait_for_function("window.ready")
                page.evaluate(
                    "params=>document.querySelector('iframe').contentWindow.postMessage({jsonrpc:'2.0',method:'ui/notifications/tool-result',params},'*')",
                    launch,
                )
                return page.frame_locator("iframe")

            app = mount({"directory": str(tmp_path)})
            expect(
                app.get_by_role("heading", name="Le istruzioni che Lucia applicherà")
            ).to_be_visible()
            expect(
                app.get_by_role(
                    "button", name="Usa questa versione con Lucia", exact=True
                )
            ).to_be_disabled()
            expect(
                app.get_by_role("status").filter(has_text="Esempio NDA")
            ).to_be_visible()
            expect(app.locator("#destination")).to_contain_text(str(tmp_path))
            app.get_by_label("Nome del procedimento", exact=True).fill(
                "Metodo sintetico — NDA"
            )
            app.get_by_role("button", name="Salva le istruzioni", exact=True).click()
            expect(app.locator("#message")).to_have_text(
                "Versione salvata nella cartella dello studio scelta. Le versioni precedenti restano disponibili."
            )
            app.get_by_role(
                "button", name="Usa questa versione con Lucia", exact=True
            ).click()
            expect(app.locator("#message")).to_contain_text(
                "Versione selezionata nella chat"
            )
            selected = page.evaluate("window.selectedMethod")
            assert selected["_meta"]["openai/message"]["target"] == "active"
            assert "Metodo sintetico — NDA" in selected["content"][0]["text"]
            files = list(tmp_path.glob("*.json"))
            assert str(files[0]) in selected["content"][0]["text"]
            assert len(files) == 1
            first = json.loads(files[0].read_text())
            assert first["name"] == "Metodo sintetico — NDA"
            app = mount({"directory": str(tmp_path), "filename": files[0].name})
            expect(app.get_by_label("Nome del procedimento", exact=True)).to_have_value(
                first["name"]
            )
            app.get_by_role("button", name="Crea una copia", exact=True).click()
            app.get_by_label("Nome del procedimento", exact=True).fill(
                "Secondo metodo sintetico"
            )
            app.get_by_role("button", name="Salva le istruzioni", exact=True).click()
            expect(app.locator("#message")).to_have_text(
                "Versione salvata nella cartella dello studio scelta. Le versioni precedenti restano disponibili."
            )
            assert len(list(tmp_path.glob("*.json"))) == 2
            assert json.loads(files[0].read_text()) == first
            frame = page.frames[1]
            assert frame.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors and not downloads
            browser.close()
        finally:
            worker.terminate()
            worker.wait(timeout=10)
