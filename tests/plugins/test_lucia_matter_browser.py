"""Exercise the native matter-review resource and durable pending decisions."""

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
def test_matter_native_resource_restores_saved_decisions(tmp_path, width):
    from tests.plugins.test_lucia_matter_native import prepared

    root = prepared(tmp_path)
    package = os.environ.get("LUCIA_REVIEW_PACKAGE_ROOT")
    server = (
        Path(package) / "scripts/on_demand_mcp.cjs"
        if package
        else ROOT / "plugins/lucia/scripts/matter_mcp.cjs"
    )
    env = {**os.environ, "LUCIA_MATTER_PYTHON": sys.executable}
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
            source = rpc(
                "resources/read", {"uri": "ui://lucia/matter-opening-v1.html"}
            )["contents"][0]["text"]
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
                    if(m.method==='ui/initialize')win.postMessage({jsonrpc:'2.0',id:m.id,result:{}},'*');
                    if(m.method==='ui/notifications/initialized')window.ready=true;
                    if(m.method==='tools/call')win.postMessage({jsonrpc:'2.0',id:m.id,result:await window.mcpCall(m.params)},'*');
                });
            }"""
            )

            def mount(args):
                launch = rpc(
                    "tools/call", {"name": "lucia_matter_open", "arguments": args}
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

            app = mount({"run_dir": str(root)})
            expect(app.locator(".review-item").first).to_be_visible()
            expect(app.locator("#toolbar")).to_be_visible()
            app.locator("#reviewer").fill("Revisore sintetico")
            item = app.locator(".review-item").first
            item.get_by_role("combobox", name="Decisione", exact=True).select_option(
                "return"
            )
            item.get_by_role("textbox", name="Nota", exact=True).fill(
                "Richiedere chiarimenti. Non accettare l’incarico."
            )
            app.get_by_role(
                "button", name="Salva le decisioni da applicare", exact=True
            ).click()
            expect(app.locator("#status")).to_contain_text("Decisioni salvate")
            saved = root / "pending_review_decisions.json"
            before = saved.read_bytes()
            assert not (root / "applied_decisions.json").exists()
            app = mount({"run_dir": str(root)})
            expect(app.locator("#reviewer")).to_have_value("Revisore sintetico")
            expect(
                app.locator(".review-item").first.get_by_role(
                    "combobox", name="Decisione", exact=True
                )
            ).to_have_value("return")
            expect(
                app.locator(".review-item").first.get_by_role(
                    "textbox", name="Nota", exact=True
                )
            ).to_have_value("Richiedere chiarimenti. Non accettare l’incarico.")
            assert saved.read_bytes() == before
            assert not errors and not downloads
            browser.close()
        finally:
            worker.terminate()
            worker.wait(timeout=10)
