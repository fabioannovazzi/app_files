"""Render the actual MCP App in an offline host harness, not native-host acceptance."""

from __future__ import annotations

import base64
import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "plugins/browser-automation"
pytestmark = pytest.mark.skipif(
    os.environ.get("VERA_ADE_BROWSER_TEST") != "1",
    reason="Requires the explicitly enabled offline browser acceptance suite",
)


def _html() -> str:
    ui = COMPONENT / "ui"
    return (
        (ui / "agenzia.html")
        .read_text()
        .replace("/*__CSS__*/", (ui / "agenzia.css").read_text())
        .replace("/*__JS__*/", (ui / "agenzia.js").read_text())
        .replace(
            "__FONT_REGULAR__",
            base64.b64encode((ui / "InstrumentSans-Regular.ttf").read_bytes()).decode(),
        )
        .replace(
            "__FONT_BOLD__",
            base64.b64encode(
                (ui / "InstrumentSans-SemiBold.ttf").read_bytes()
            ).decode(),
        )
    )


@pytest.fixture
def panel(tmp_path, monkeypatch):
    from playwright.sync_api import sync_playwright

    monkeypatch.syspath_prepend(str(COMPONENT / "scripts"))
    service = importlib.import_module("agenzia_ui")
    cli = importlib.import_module("agenzia_acquire")
    fake_process = SimpleNamespace(
        **{
            name: getattr(cli.subprocess, name)
            for name in dir(cli.subprocess)
            if not name.startswith("__")
        }
    )
    fake_process.Popen = lambda *a, **k: SimpleNamespace(pid=54321)
    monkeypatch.setattr(cli, "subprocess", fake_process)
    fixture = json.loads(
        (ROOT / "scripts/course_materials/inputs/agenzia/demo.json").read_text()
    )
    source = tmp_path / "plan.json"
    source.write_text(json.dumps(fixture["plan"]))
    output = tmp_path / "output"
    requests = []
    selected = {"run_id": None}

    def bridge(params):
        action = params["name"].removeprefix("agenzia_workspace_")
        args = params.get("arguments", {})
        requests.append((action, args))
        if action == "open" and selected["run_id"]:
            action, args = "status", {"run_id": selected["run_id"]}
        try:
            result = service.dispatch(
                {
                    "plan_path": str(source),
                    "output_directory": str(output),
                    "action": action,
                    "args": args,
                }
            )
            return {
                "_meta": {"agenzia": {**result, "workspace_ref": "bound-local-fixture"}}
            }
        except service.AcquisitionError as exc:
            return {"isError": True, "content": [{"type": "text", "text": exc.code}]}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("VERA_ADE_TEST_CHANNEL", "chrome"), headless=True
        )
        page = browser.new_page(viewport={"width": 1180, "height": 880})
        page.set_default_timeout(5000)
        page.route(
            "**/*",
            lambda route: (
                route.fulfill(
                    status=200,
                    content_type="text/html",
                    body='<html><body style="margin:0"><iframe id="panel" style="border:0;width:100%;height:875px" title="Vera"></iframe></body></html>',
                )
                if route.request.url == "http://127.0.0.1/fixture"
                else route.abort()
            ),
        )
        page.expose_function("toolBridge", bridge)

        def show(width=1180):
            page.set_viewport_size({"width": width, "height": 880})
            page.goto("http://127.0.0.1/fixture")
            page.evaluate(
                """() => window.addEventListener("message", async event => {
              const msg=event.data;if(!msg?.id)return;
              const result=msg.method==="ui/initialize" ? {hostCapabilities:{},hostContext:{}} : await window.toolBridge(msg.params);
              event.source.postMessage({jsonrpc:"2.0",id:msg.id,result},"*");
            })"""
            )
            page.locator("iframe").evaluate("(frame,html)=>frame.srcdoc=html", _html())
            frame = page.frame_locator("#panel")
            frame.get_by_role("heading", name="Scegli cosa acquisire").wait_for()
            return frame

        yield SimpleNamespace(
            page=page,
            show=show,
            requests=requests,
            source=source,
            output=output,
            selected=selected,
        )
        browser.close()


@pytest.mark.parametrize("width", [1180, 390])
def test_panel_saves_selected_dates_and_starts_same_worker(panel, width):
    frame = panel.show(width)
    frame.get_by_label("Al", exact=True).fill("2026-02-28")
    frame.get_by_role("button", name="Conserva selezione").click()
    frame.get_by_role("status").filter(has_text="Selezione conservata").wait_for()
    assert panel.requests[-1][0] == "save"
    assert panel.requests[-1][1]["plan"]["date_to"] == "2026-02-28"
    assert frame.locator("body").evaluate("el=>el.scrollWidth <= window.innerWidth")
    directory = os.environ.get("VERA_ADE_SCREENSHOT_DIR")
    if directory:
        Path(directory).mkdir(parents=True, exist_ok=True)
        panel.page.screenshot(
            path=str(Path(directory) / f"agenzia-panel-{width}.png"), full_page=True
        )
    frame.get_by_role("button", name="Avvia acquisizione").click()
    frame.get_by_role("heading", name="Avvio in corso").wait_for()
    assert panel.requests[-1][0] == "start"
    assert panel.requests[-1][1]["request_id"]
    plans = list((panel.output / "runs").glob("*/plan.json"))
    assert len(plans) == 1
    assert json.loads(plans[0].read_text())["date_to"] == "2026-02-28"


def test_panel_retains_f24_review_when_switching_views(panel):
    demo = importlib.import_module("agenzia_demo")
    result = demo.run_demo(
        ROOT / "scripts/course_materials/inputs/agenzia/demo.json", panel.output
    )
    panel.selected["run_id"] = result["run_id"]
    frame = panel.show()
    frame.get_by_role("button", name="Bolli e F24", exact=True).click()
    frame.get_by_label("Residuo EUR", exact=True).fill("12.00")
    frame.get_by_label("Scadenza", exact=True).fill("2026-06-01")
    frame.get_by_label("Motivo del riesame", exact=True).fill(
        "Scenario didattico: versamento parziale riscontrato"
    )
    frame.get_by_role("checkbox", name="Includi Ditta").check()
    frame.get_by_role("button", name="Fatture", exact=True).click()
    frame.get_by_role("button", name="Bolli e F24", exact=True).click()
    assert frame.get_by_label("Residuo EUR", exact=True).input_value() == "12.00"
    assert frame.get_by_label("Scadenza", exact=True).input_value() == "2026-06-01"
    assert frame.get_by_role("checkbox", name="Includi Ditta").is_checked()
    frame.get_by_role("button", name="Genera prospetto dai valori riesaminati").click()
    frame.get_by_role("status").filter(has_text="Prospetto conservato").wait_for()
    assert panel.requests[-1][0] == "f24"
    assert panel.requests[-1][1]["review"]["items"][0]["amount"] == "12.00"
    assert len(list((panel.output / "runs" / result["run_id"]).glob("*.pdf"))) == 1
