"""Local Playwright adapter for Francesco Platania's Fatture e Corrispettivi flow.

Only the explicit search, delegate, pagination, detail and download controls below
are used. Authentication belongs to the operator in the visible browser. Browser
profiles, credentials, cookies, screenshots and complete page bodies are not saved.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

from .artifacts import MAX_BYTES
from .contracts import CATEGORIES, AcquisitionError, Client, Plan, canonical_hash, money

__all__ = ["Portal", "open_browser", "LOGIN_URL"]
LOGIN_URL = "https://iampe.agenziaentrate.gov.it/sam/UI/Login?realm=/agenziaentrate"
WIZARD_URL = "https://ivaservizi.agenziaentrate.gov.it/instr/InstradamentofcWeb/wizard"
CONS_URL = "https://ivaservizi.agenziaentrate.gov.it/cons/cons-web/"
PORTAL_HOST = "ivaservizi.agenziaentrate.gov.it"
ROWS = "table:visible tbody tr"


@contextmanager
def open_browser() -> Iterator[Any]:
    """Use installed Chrome in a temporary context; never install a browser at runtime."""
    from playwright.sync_api import Error, sync_playwright

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=False)
            try:
                context = browser.new_context(accept_downloads=True, locale="it-IT")
                page = context.new_page()
                page.set_default_timeout(20000)
                page.goto(LOGIN_URL, wait_until="domcontentloaded")
                yield page
            finally:
                browser.close()
    except Error as exc:
        # Playwright messages can contain DOM text or private paths; expose only a code.
        raise AcquisitionError("browser-unavailable-or-closed") from exc


def _integer(value: str) -> int:
    text = value.strip()
    if not re.fullmatch(r"(?:\d{1,3}(?:\.\d{3})+|\d+)", text):
        raise AcquisitionError("portal-count-invalid")
    return int(text.replace(".", ""))


def _has_vat(value: str, vat: str) -> bool:
    return bool(re.search(rf"(?<!\d){re.escape(vat)}(?!\d)", value))


class Portal:
    """Bounded synchronous read/download operations, returning only selected evidence."""

    def __init__(self, page: Any) -> None:
        self.page = page

    def _check(self) -> None:
        if urlparse(self.page.url).hostname != PORTAL_HOST:
            raise AcquisitionError("authentication-required")
        if self.page.locator("#error-page:visible, .alert-danger:visible").count():
            raise AcquisitionError("portal-reported-error")

    def _settle(self) -> None:
        # Allow Angular to start the request, then require its loader to finish.
        self.page.wait_for_timeout(700)
        self.page.locator("#loader").wait_for(state="hidden", timeout=30000)
        self._check()

    def _goto(self, url: str) -> None:
        self.page.goto(url, wait_until="domcontentloaded")
        self._settle()

    def _button(self, label: str, *, prefix: bool = False) -> Any:
        pattern = rf"^\s*{re.escape(label)}" + ("" if prefix else r"\s*$")
        locator = self.page.locator("button:visible").filter(
            has_text=re.compile(pattern, re.I)
        )
        locator.first.wait_for(state="visible")
        if locator.count() != 1:
            raise AcquisitionError("portal-control-missing-or-ambiguous")
        return locator

    def _click(self, label: str) -> None:
        self._check()
        self._button(label).click()
        self._settle()

    def select_client(self, plan: Plan, client: Client) -> None:
        """Select the explicitly requested delegate; each query also verifies its VAT filter."""
        self._goto(WIZARD_URL)
        if plan.access_mode == "delega_diretta":
            self.page.locator("input[value='delegaDiretta']").click()
            self._click("PROCEDI")
            self.page.locator("input[value='delDiretta']").click()
            self.page.locator("#cf").fill(client.tax_code)
            self._click("PROCEDI")
        else:
            self.page.locator("input[value='incaricato']").click()
            self._click("PROCEDI")
            self.page.locator("#incaricante").fill(plan.work_identity)
            self.page.locator("input[value='incaricoDelega']").click()
            self.page.locator("#cfDelegante").fill(client.tax_code)
            self._click("PROCEDI")
        if self.page.locator("#pIva:visible").count():
            self.page.locator("#pIva").fill(client.vat_number)
            self._click("PROCEDI")
        confirm = self.page.locator("button:visible").filter(
            has_text=re.compile(r"^\s*CONFERMA\s*$", re.I)
        )
        if confirm.count():
            self._click("CONFERMA")
        self._check()

    def _vat(self, client: Client) -> None:
        locator = self.page.locator("#piva")
        locator.wait_for(state="visible")
        if locator.evaluate("e => e.tagName.toLowerCase()") == "select":
            options = locator.locator("option")
            matches = [
                index
                for index in range(options.count())
                if _has_vat(
                    (options.nth(index).get_attribute("value") or "")
                    + " "
                    + options.nth(index).inner_text(),
                    client.vat_number,
                )
            ]
            if len(matches) != 1:
                raise AcquisitionError("portal-client-not-available")
            locator.select_option(index=matches[0])
            selected = locator.locator("option:checked")
            if not _has_vat(
                (selected.get_attribute("value") or "") + " " + selected.inner_text(),
                client.vat_number,
            ):
                raise AcquisitionError("portal-client-mismatch")
        else:
            locator.fill(client.vat_number)
            if locator.input_value().strip() != client.vat_number:
                raise AcquisitionError("portal-client-mismatch")

    def _date(self, field: str, value: date) -> None:
        locator = self.page.locator(f"#{field}")
        locator.evaluate(
            """(e, value) => {
            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(e, value);
            e.dispatchEvent(new Event('input', {bubbles:true}));
            e.dispatchEvent(new Event('change', {bubbles:true})); e.blur();
        }""",
            value.isoformat(),
        )
        if locator.input_value() not in {value.isoformat(), value.strftime("%d/%m/%Y")}:
            raise AcquisitionError("portal-date-filter-mismatch")

    def _search(self, section: str, client: Client, start: date, end: date) -> None:
        self._goto(CONS_URL + section)
        self._vat(client)
        self._date("dal", start)
        self._date("al", end)
        self._click("Cerca")

    def search_invoices(
        self, client: Client, category: str, start: date, end: date
    ) -> int:
        self._search(CATEGORIES[category], client, start, end)
        heading = self.page.locator("#elenco-fatture h2")
        heading.wait_for(state="visible")
        match = re.search(r"\(([0-9.]+)\)", heading.inner_text())
        if not match:
            raise AcquisitionError("portal-result-count-unavailable")
        return _integer(match[1])

    def invoice_rows(self) -> list[dict[str, Any]]:
        self._check()
        rows = self.page.locator(ROWS)
        result = []
        for index in range(rows.count()):
            values = rows.nth(index).locator("td").all_inner_texts()
            if len(values) < 2:
                raise AcquisitionError("portal-invoice-row-unrecognized")
            # Hash the complete visible row; never infer document identity from position.
            result.append(
                {"key": canonical_hash([v.strip() for v in values]), "index": index}
            )
        if len({r["key"] for r in result}) != len(result):
            raise AcquisitionError("portal-invoice-rows-ambiguous")
        return result

    def next_page(self, number: int, fingerprint: str) -> None:
        """Require an actual page change; a disabled or repeated next control is an error."""
        controls = self.page.locator(".page-link:visible")
        target = controls.filter(has_text=re.compile(rf"^\s*{number}\s*$"))
        if not target.count():
            target = controls.filter(
                has_text=re.compile(
                    r"^\s*(?:›|»|>|succ(?:essiva)?|avanti|next)\s*$", re.I
                )
            )
        if target.count() != 1:
            raise AcquisitionError("portal-pagination-unavailable")
        if (
            target.get_attribute("aria-disabled") == "true"
            or "disabled"
            in (target.locator("xpath=..").get_attribute("class") or "").split()
        ):
            raise AcquisitionError("portal-pagination-disabled")
        target.click()
        self._settle()
        if canonical_hash(self.page.locator(ROWS).all_inner_texts()) == fingerprint:
            raise AcquisitionError("portal-pagination-did-not-advance")

    def page_fingerprint(self) -> str:
        return canonical_hash(self.page.locator(ROWS).all_inner_texts())

    def restore_invoices(
        self,
        client: Client,
        category: str,
        start: date,
        end: date,
        page_number: int,
        expected: int,
        keys: list[str],
    ) -> None:
        breadcrumb = self.page.locator("#main nav ol li:nth-child(2) a:visible")
        if breadcrumb.count() == 1:
            breadcrumb.click()
            self._settle()
            if (
                self.page.locator("#elenco-fatture h2:visible").count()
                and [r["key"] for r in self.invoice_rows()] == keys
            ):
                return
        if self.search_invoices(client, category, start, end) != expected:
            raise AcquisitionError("portal-population-changed")
        for number in range(2, page_number + 1):
            self.next_page(number, self.page_fingerprint())
        if [r["key"] for r in self.invoice_rows()] != keys:
            raise AcquisitionError("portal-population-changed")

    def download_invoice(self, row: dict[str, Any]) -> tuple[str, bytes]:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        current = self.invoice_rows()
        if row["index"] >= len(current) or current[row["index"]]["key"] != row["key"]:
            raise AcquisitionError("portal-population-changed")
        self.page.locator(ROWS).nth(row["index"]).locator("td").last.click()
        self._settle()
        button = self._button("Download file fattura", prefix=True)
        try:
            with self.page.expect_download(timeout=40000) as event:
                button.click()
            download = event.value
            path = download.path()
            if path is None or download.failure():
                raise AcquisitionError("invoice-download-failed")
            local = Path(path)
            if not 0 < local.stat().st_size <= MAX_BYTES:
                raise AcquisitionError("invoice-size-invalid")
            data = local.read_bytes()
            filename = download.suggested_filename
            download.delete()
            return filename, data
        except PlaywrightTimeout as exc:
            raise AcquisitionError("invoice-original-unavailable") from exc

    def _tables(self) -> list[dict[str, Any]]:
        return self.page.locator("table:visible").evaluate_all(
            """tables => tables.map(t => ({
          headers: [...t.querySelectorAll('thead th')].map(e => e.innerText.trim().replace(/\\s+/g, ' ')),
          rows: [...t.querySelectorAll('tbody tr')].map(tr => [...tr.querySelectorAll('th,td')].map(e => e.innerText.trim().replace(/\\s+/g, ' ')))
        }))"""
        )

    def cash_devices(
        self, client: Client, start: date, end: date
    ) -> list[dict[str, Any]]:
        self._search("corrispettivi/invii", client, start, end)
        rows = self.page.locator(ROWS)
        devices = []
        for index in range(rows.count()):
            cells = rows.nth(index).locator("td")
            if cells.count() < 2:
                raise AcquisitionError("portal-cash-summary-unrecognized")
            control = rows.nth(index).locator("button, a.btn")
            count_text = (
                control.inner_text()
                if control.count() == 1
                else cells.nth(1).inner_text()
            )
            devices.append(
                {
                    "name": cells.first.inner_text().strip(),
                    "count": _integer(count_text),
                    "index": index,
                }
            )
        if not devices or len({d["name"] for d in devices}) != len(devices):
            raise AcquisitionError("portal-cash-summary-unavailable")
        return devices

    def cash_rows(
        self, client: Client, start: date, end: date, device: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if device["count"] == 0:
            return []
        devices = self.cash_devices(client, start, end)
        if device not in devices:
            raise AcquisitionError("portal-population-changed")
        self.page.locator(ROWS).nth(device["index"]).locator("button, a.btn").click()
        self._settle()
        result: list[dict[str, Any]] = []
        fingerprints = set()
        number = 1
        while len(result) < device["count"]:
            tables = [
                table
                for table in self._tables()
                if any(h.lower().startswith("matricola") for h in table["headers"])
            ]
            if len(tables) != 1 or not tables[0]["rows"]:
                raise AcquisitionError("portal-cash-table-unrecognized")
            table = tables[0]
            fingerprint = canonical_hash(table)
            if fingerprint in fingerprints:
                raise AcquisitionError("portal-pagination-repeated")
            fingerprints.add(fingerprint)
            for cells in table["rows"]:
                if len(cells) != len(table["headers"]):
                    raise AcquisitionError("portal-cash-row-unrecognized")
                result.append(dict(zip(table["headers"], cells, strict=True)))
            if len(result) > device["count"]:
                raise AcquisitionError("portal-cash-count-mismatch")
            if len(result) < device["count"]:
                number += 1
                self.next_page(number, self.page_fingerprint())
        return result

    def stamp_duty(self, client: Client, year: int, quarter: int) -> dict[str, Any]:
        self._goto(CONS_URL + "fatture/bollo")
        self._vat(client)
        year_select = self.page.locator("#anno")
        year_select.select_option(str(year))
        self._settle()
        quarter_select = self.page.locator("#trimestre")
        options = quarter_select.locator("option").evaluate_all(
            "es => es.map(e => e.value)"
        )
        if str(quarter) not in options:
            return {"status": "not_available", "amount": None, "payment_status": ""}
        quarter_select.select_option(str(quarter))
        self._click("Cerca")
        rows = self.page.locator("#table-elenco-fatture tbody tr")
        matches = []
        for index in range(rows.count()):
            cells = rows.nth(index).locator("td").all_inner_texts()
            if cells and _has_vat(cells[0], client.vat_number):
                matches.append([cell.strip() for cell in cells])
        if len(matches) != 1 or len(matches[0]) < 7:
            raise AcquisitionError("portal-bollo-row-missing-or-unrecognized")
        row = matches[0]
        amount = money(row[6])
        if amount is None:
            raise AcquisitionError("portal-bollo-amount-missing")
        return {
            "status": "acquired",
            "amount": str(amount),
            "list_a_count": _integer(row[3]),
            "list_b_count": _integer(row[4]),
            "document_count": _integer(row[5]),
            "attestations": row[7] if len(row) > 7 else "",
            "payment_status": row[8] if len(row) > 8 else "",
            "row_evidence": row,
        }
