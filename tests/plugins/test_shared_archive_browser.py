"""Render the real shared Clara/Lucia resource in an MCP Apps browser host."""

from __future__ import annotations

import shutil

import pytest

from tests.plugins.test_lucia_archive_panel import ROOT, call, panel

__all__: list[str] = []


@pytest.mark.parametrize("product", ["lucia", "clara"])
def test_real_shared_panel_browser_documents_and_existing_chat(
    panel, monkeypatch, product
):
    from playwright.sync_api import expect, sync_playwright

    if product == "clara":
        shutil.copyfile(
            ROOT / "plugins/clara/scripts/studio_archive_mcp.cjs",
            panel / "scripts/studio_archive_mcp.cjs",
        )
        monkeypatch.setenv("CLARA_ARCHIVE_PANEL_ONLY", "1")
    resource = call(panel, "resources/list")["resources"][0]
    source = call(panel, "resources/read", {"uri": resource["uri"]})["contents"][0][
        "text"
    ]
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1100, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.expose_function(
            "mcpCall", lambda params: call(panel, "tools/call", params)
        )
        page.route(
            "https://codex.test/",
            lambda route: route.fulfill(
                content_type="text/html",
                body="<iframe style='width:100%;height:95vh;border:0'></iframe>",
            ),
        )
        page.goto("https://codex.test/")
        page.evaluate(
            """() => window.addEventListener('message',async event=>{
          const m=event.data,win=event.source;
          let result;
          if(m.method==='ui/initialize')result={hostCapabilities:{experimental:{'openai/files':{}}}};
          if(m.method==='tools/call')result=await window.mcpCall(m.params);
          if(m.method==='ui/open-link'){window.openedChat=m.params.url;result={};}
          if(m.method==='openai/files/open'){window.openedFile=m.params.path;result={};}
          if(result)win.postMessage({jsonrpc:'2.0',id:m.id,result},'*');
        })"""
        )
        page.evaluate("html=>document.querySelector('iframe').srcdoc=html", source)
        frame = page.frame_locator("iframe")
        expect(frame.get_by_role("heading", name="Clienti e progetti")).to_be_visible()
        expect(frame.get_by_role("searchbox")).to_be_visible()
        expect(frame.get_by_role("button", name="Other product only")).to_have_count(0)
        expect(
            frame.get_by_role("button", name="nuova chat", exact=False)
        ).to_have_count(0)
        frame.get_by_role("button", name="Synthetic client", exact=True).click()
        frame.get_by_role("button", name="Synthetic practice", exact=True).click()
        frame.get_by_role("button", name="Existing discussion", exact=True).click()
        page.wait_for_function("window.openedChat === 'codex://threads/synthetic'")
        frame.get_by_role("button", name="Opinion", exact=True).click()
        page.wait_for_function("window.openedFile === '/synthetic/Source.txt'")
        assert errors == []
        browser.close()
