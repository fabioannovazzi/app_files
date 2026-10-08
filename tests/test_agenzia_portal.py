"""Exercise the actual Playwright adapter against synthetic portal DOM, without network."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "ade_portal_fixtures", ROOT / "tests/test_agenzia_acquisition.py"
)
assert spec and spec.loader
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
portal_module = fixtures.importlib.import_module(f"{fixtures.PACKAGE}.portal")

pytestmark = pytest.mark.skipif(
    os.environ.get("VERA_ADE_BROWSER_TEST") != "1",
    reason="Set VERA_ADE_BROWSER_TEST=1 with installed Chrome for the offline DOM acceptance suite",
)

HTML = r"""<!doctype html><html lang="it"><body><main id="main"></main><script>
const vat='01234567890'; const main=document.querySelector('main'); let listPage=1;
const xml=INVOICE;
function controls(){return `<select id="piva"><option value="${vat}">${vat}</option></select><input id="dal" type="date"><input id="al" type="date"><button onclick="search()">Cerca</button>`}
function invoiceList(){main.innerHTML=controls()+`<div id="elenco-fatture"><h2>Fatture (2)</h2></div><table><tbody><tr><td>Fattura ${listPage}</td><td><button onclick="detail()">Dettaglio</button></td></tr></tbody></table><button class="page-link" onclick="listPage=2;invoiceList()">2</button>`}
function detail(){main.innerHTML=`<nav><ol><li>Home</li><li><a href="#" onclick="invoiceList()">Elenco</a></li></ol></nav><button onclick="download()">Download file fattura</button>`}
function download(){let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([xml],{type:'application/xml'}));a.download='originale.xml';a.click()}
function cashList(){main.innerHTML=controls()+`<table><tbody><tr><td>RT</td><td><button onclick="cashRows('RT')">2</button></td></tr><tr><td>Distributori</td><td><button onclick="cashRows('DA')">1</button></td></tr></tbody></table>`}
function cashRows(type){let ids=type==='RT'?['1','2']:['3'];main.innerHTML=`<table><thead><tr>${['Id invio','Matricola dispositivo','Data e ora rilevazione','Ammontare','Imponibile','Imposta'].map(x=>'<th>'+x+'</th>').join('')}</tr></thead><tbody>${ids.map(id=>`<tr><td>${id}</td><td>${type}</td><td>02/01/2026 12:00:00</td><td>12,20</td><td>10,00</td><td>2,20</td></tr>`).join('')}</tbody></table>`}
function stamp(){main.innerHTML=`<select id="piva"><option>${vat}</option></select><select id="anno"><option>2026</option></select><select id="trimestre"><option>1</option><option>4</option></select><button onclick="stampResult()">Cerca</button>`}
function stampResult(){main.insertAdjacentHTML('beforeend',`<div id="table-elenco-fatture"><h2>Bolli</h2><table><tbody><tr>${[vat,'Ditta','2026','2','0','2','4,00','ricevuta','pagato'].map(x=>'<td>'+x+'</td>').join('')}</tr></tbody></table></div>`)}
function search(){if(location.href.includes('corrispettivi'))cashList();else invoiceList()}
if(location.href.includes('wizard')){main.innerHTML=`<input type="radio" value="delegaDiretta"><button onclick="main.innerHTML=\`<input type='radio' value='delDiretta'><input id='cf'><button onclick='invoiceList()'>PROCEDI</button>\`">PROCEDI</button>`}
else if(location.href.includes('bollo'))stamp();else if(location.href.includes('corrispettivi'))cashList();else invoiceList();
</script></body></html>"""


@pytest.fixture
def portal():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("VERA_ADE_TEST_CHANNEL", "chrome"), headless=True
        )
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(1000)
        page.route(
            "**/*",
            lambda route: route.fulfill(
                status=200,
                content_type="text/html",
                body=HTML.replace("INVOICE", json.dumps(fixtures.invoice().decode())),
            ),
        )
        adapter = portal_module.Portal(page)
        yield adapter
        browser.close()


def test_real_adapter_selects_delegation_downloads_and_restores_pages(portal):
    plan = fixtures.contracts.Plan.parse(fixtures.plan_data())
    client = plan.clients[0]
    portal.select_client(plan, client)
    assert (
        portal.search_invoices(client, "ricevute", date(2026, 1, 1), date(2026, 1, 31))
        == 2
    )
    first = portal.invoice_rows()
    name, data = portal.download_invoice(first[0])
    assert name == "originale.xml"
    assert data == fixtures.invoice()
    portal.restore_invoices(
        client, "ricevute", date(2026, 1, 1), date(2026, 1, 31), 1, 2, [first[0]["key"]]
    )
    portal.next_page(2, portal.page_fingerprint())
    assert portal.invoice_rows()[0]["key"] != first[0]["key"]


def test_real_adapter_acquires_every_cash_device(portal):
    client = fixtures.contracts.Client.parse(fixtures.CLIENT)
    start, end = date(2026, 1, 1), date(2026, 1, 31)
    devices = portal.cash_devices(client, start, end)
    results = [portal.cash_rows(client, start, end, device) for device in devices]
    assert [len(rows) for rows in results] == [2, 1]
    assert results[1][0]["Matricola dispositivo"] == "DA"


def test_real_adapter_keeps_bollo_payment_status_and_unavailable_quarter(portal):
    client = fixtures.contracts.Client.parse(fixtures.CLIENT)
    acquired = portal.stamp_duty(client, 2026, 4)
    absent = portal.stamp_duty(client, 2026, 2)
    assert acquired["amount"] == "4.00"
    assert acquired["payment_status"] == "pagato"
    assert absent["status"] == "not_available"
    assert absent["amount"] is None


def test_real_adapter_does_not_use_single_wrong_vat_option(portal):
    portal.page.goto(portal_module.CONS_URL + "fatture/ricevute")
    client = fixtures.contracts.Client.parse(
        {**fixtures.CLIENT, "vat_number": "11111111111"}
    )
    with pytest.raises(
        fixtures.contracts.AcquisitionError, match="client-not-available"
    ):
        portal._vat(client)
