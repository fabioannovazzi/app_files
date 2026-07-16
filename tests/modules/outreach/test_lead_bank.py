from __future__ import annotations

import csv
import json
from pathlib import Path

from modules.outreach import OutreachLead, email_hash
from modules.outreach.lead_bank import (
    DiscoveredLeadBatch,
    build_lead_bank_from_sources,
    discover_leads_from_html,
    extract_email_addresses,
    fetch_static_html,
)


def test_extract_email_addresses_reads_visible_text_and_mailto_links() -> None:
    text = (
        '<a href="mailto:Info@Example.com?subject=Hello">Email</a> '
        "Contact office@example.org."
    )

    assert extract_email_addresses(text) == ("info@example.com", "office@example.org")


def test_discover_leads_from_html_uses_previous_heading_as_name() -> None:
    html = """
    <html>
      <title>Directory</title>
      <body>
        <h2>Example Studio</h2>
        <a href="mailto:info@example-studio.example.com">info@example-studio.example.com</a>
      </body>
    </html>
    """

    leads = discover_leads_from_html(
        html,
        source_url="https://directory.example/italy",
        country="Italy",
        city="Roma",
        source_note="official-register",
    )

    assert leads == [
        OutreachLead(
            name="Example Studio",
            email="info@example-studio.example.com",
            city="Roma",
            country="Italy",
            source_url="https://directory.example/italy",
            source_note="official-register",
        )
    ]


def test_discover_leads_from_html_keeps_firm_domain_contact_email() -> None:
    html = """
    <html>
      <title>Fiduciaire Test SA</title>
      <body>
        <a href="mailto:info@fiduciaire-test.example.com">info@fiduciaire-test.example.com</a>
      </body>
    </html>
    """

    leads = discover_leads_from_html(
        html,
        source_url="https://fiduciaire-test.example.com/contact",
        country="Switzerland",
        city="Genève",
        source_note="treuhandsuisse-directory:swiss-romande",
    )

    assert leads == [
        OutreachLead(
            name="Fiduciaire Test SA",
            email="info@fiduciaire-test.example.com",
            city="Genève",
            country="Switzerland",
            source_url="https://fiduciaire-test.example.com/contact",
            source_note="treuhandsuisse-directory:swiss-romande",
        )
    ]


def test_build_lead_bank_from_sources_appends_only_new_hashes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    queue_path = tmp_path / "queue.csv"
    ledger_path = tmp_path / "ledger.jsonl"
    ledger_path.write_text(
        json.dumps({"email_hash": email_hash("already@example.com"), "status": "sent"})
        + "\n",
        encoding="utf-8",
    )

    def fake_discover_leads_from_source(
        source_url: str,
        *,
        country: str,
        city: str = "",
        source_note: str = "public-directory",
        use_playwright: bool = False,
        timeout_seconds: int = 20,
    ) -> DiscoveredLeadBatch:
        return DiscoveredLeadBatch(
            source_url=source_url,
            leads=(
                OutreachLead(
                    name="Already",
                    email="already@example.com",
                    city=city,
                    country=country,
                    source_url=source_url,
                    source_note=source_note,
                ),
                OutreachLead(
                    name="New",
                    email="new@example.com",
                    city=city,
                    country=country,
                    source_url=source_url,
                    source_note=source_note,
                ),
            ),
        )

    monkeypatch.setattr(
        "modules.outreach.lead_bank.discover_leads_from_source",
        fake_discover_leads_from_source,
    )

    appended_count = build_lead_bank_from_sources(
        ["https://directory.example/uk"],
        queue_path=queue_path,
        ledger_path=ledger_path,
        country="United Kingdom",
        city="London",
        source_note="public-directory",
    )

    rows = _read_queue(queue_path)
    assert appended_count == 1
    assert rows[0]["email"] == "new@example.com"
    assert rows[0]["email_hash"] == email_hash("new@example.com")
    assert rows[0]["status"] == "queued"


def test_fetch_static_html_uses_configured_session() -> None:
    response = _FakeResponse("<html>ok</html>")
    session = _FakeSession(response)

    text = fetch_static_html("https://directory.example", session=session)

    assert text == "<html>ok</html>"
    assert session.requested_url == "https://directory.example"


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.content = text.encode("utf-8")
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        return None


class _FakeSession:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.requested_url = ""

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: int,
    ) -> _FakeResponse:
        self.requested_url = url
        return self.response


def _read_queue(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))
