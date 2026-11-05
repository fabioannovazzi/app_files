"""Render the receipt-checked native Clara report and change its budget view."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("width", [400, 1080])
def test_native_report_keeps_period_controls_and_rejects_stale_refresh(tmp_path, width):
    script = (
        ROOT / "plugins/management-control-pack/assets/budget-report.js"
    ).read_text()
    report = tmp_path / "management_control_dashboard.html"
    language = "it" if width == 400 else "en"
    report.write_text(
        """<!doctype html><html><body><h1>Budget sintetico</h1>
    <section class="budget-report"><p class="eyebrow">PL · AC</p><table><thead><tr><th>PL · Budget</th><th>AC · Actual</th><th>FC · Forecast</th></tr></thead><tbody><tr><td>100</td><td>120</td><td>130</td></tr></tbody></table><p>FC = actuals to cutoff + reviewed remaining-month estimates.</p><div class="budget-controls" hidden>
    <button data-budget-select="month">Mese</button><button data-budget-select="cumulative">Cumulato</button>
    <button data-budget-print>Stampa</button></div>
    <p data-budget-view="month">Marzo: 120 EUR</p><p data-budget-view="cumulative">Gennaio–marzo: 360 EUR</p>
    </section><script>"""
        + script
        + "</script></body></html>"
    )
    report.write_text(
        report.read_text().replace("<html>", f'<html lang="{language}">', 1)
    )
    receipt = tmp_path / "execution_receipt.json"

    def stamp():
        content = report.read_bytes()
        receipt.write_text(
            json.dumps(
                {
                    "schema_version": "vera.management_control_execution_receipt.v1",
                    "workflow_id": "management-control-pack",
                    "outputs": [
                        {
                            "path": report.name,
                            "sha256": hashlib.sha256(content).hexdigest(),
                            "byte_count": len(content),
                        }
                    ],
                }
            )
        )

    stamp()
    package = os.environ.get("CLARA_REVIEW_PACKAGE_ROOT")
    entry = (
        Path(package) / "scripts/on_demand_mcp.cjs"
        if package
        else ROOT / "plugins/clara/scripts/report_mcp.cjs"
    )
    env = {**os.environ, "CLARA_REPORT_PYTHON": sys.executable}
    env.update(
        MPARANZA_RUNTIME_ROOT=str(tmp_path / "runtime"),
        MPARANZA_INCIDENT_STATE_DIR=str(tmp_path / "incidents"),
        MPARANZA_INCIDENT_DEVICE_DIR=str(tmp_path / "device"),
        VERA_REPORTING_STATE_DIR=str(tmp_path / "reporting"),
        MPARANZA_INCIDENT_DELIVERY="local-only",
    )
    with (
        subprocess.Popen(
            ["node", str(entry)],
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
            return json.loads(worker.stdout.readline())["result"]

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
            source = rpc("resources/read", {"uri": "ui://clara/budget-report-v1.html"})[
                "contents"
            ][0]["text"]
            # The host denies external nested frames; srcdoc stays local and isolated.
            source = source.replace(
                "<head>",
                '<head><meta http-equiv="Content-Security-Policy" content="frame-src \'none\'">',
                1,
            )
            launch = rpc(
                "tools/call",
                {"name": "clara_report_open", "arguments": {"report": str(report)}},
            )
            assert not launch.get("isError"), launch
            browser = runtime.chromium.launch()
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.set_default_timeout(10000)
            errors, external_requests = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "request",
                lambda request: (
                    external_requests.append(request.url)
                    if not request.url.startswith("https://codex.test/")
                    else None
                ),
            )
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
                """() => {addEventListener('message',async event=>{
                const m=event.data,win=event.source;
                if(m.method==='ui/initialize')win.postMessage({jsonrpc:'2.0',id:m.id,result:{}},'*');
                if(m.method==='ui/notifications/initialized')window.ready=true;
                if(m.method==='tools/call')win.postMessage({jsonrpc:'2.0',id:m.id,result:await window.mcpCall(m.params)},'*');
            });}"""
            )
            page.evaluate("html=>document.querySelector('iframe').srcdoc=html", source)
            page.wait_for_function("window.ready")
            page.evaluate(
                "params=>document.querySelector('iframe').contentWindow.postMessage({jsonrpc:'2.0',method:'ui/notifications/tool-result',params},'*')",
                launch,
            )
            app = page.frame_locator("iframe")
            content = app.frame_locator("#report")
            expect(
                content.get_by_role("heading", name="Budget sintetico")
            ).to_be_visible()
            expect(content.get_by_role("button", name="Mese", exact=True)).to_have_css(
                "font-family", re.compile("Instrument Sans")
            )
            expect(
                content.get_by_role("columnheader", name="Budget", exact=True)
            ).to_be_visible()
            expect(
                content.get_by_role("columnheader", name="Actual", exact=True)
            ).to_be_visible()
            expect(content.get_by_text("PL · AC", exact=True)).to_have_count(0)
            expect(
                content.get_by_role(
                    "columnheader",
                    name="Previsionale" if language == "it" else "Forecast",
                    exact=True,
                )
            ).to_be_visible()
            expect(content.get_by_text("FC =", exact=False)).to_have_count(0)
            assert "FC =" in report.read_text()
            assert "PL · Budget" in report.read_text()
            expect(content.locator("[data-budget-print]")).to_be_hidden()
            expect(content.get_by_text("Marzo: 120 EUR", exact=True)).to_be_visible()
            expect(
                content.get_by_text("Gennaio–marzo: 360 EUR", exact=True)
            ).to_be_hidden()
            content.get_by_role("button", name="Cumulato", exact=True).click()
            expect(
                content.get_by_text("Gennaio–marzo: 360 EUR", exact=True)
            ).to_be_visible()
            expect(
                content.get_by_role("button", name="Cumulato", exact=True)
            ).to_have_attribute("aria-pressed", "true")
            report.write_text(report.read_text().replace("120 EUR", "999 EUR"))
            stamp()
            app.get_by_role(
                "button", name="Aggiorna" if language == "it" else "Refresh", exact=True
            ).click()
            expect(app.get_by_role("status")).to_contain_text(
                "Impossibile verificare"
                if language == "it"
                else "could not be verified"
            )
            expect(app.locator("#report")).to_be_hidden()
            assert not errors and not external_requests
            browser.close()
        finally:
            worker.terminate()
            worker.wait(timeout=10)
