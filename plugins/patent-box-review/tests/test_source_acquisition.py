"""Public discovery and security acceptance with isolated network boundaries."""

from __future__ import annotations

import copy
import io
import json
import socket
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import pytest
from patent_box import source_acquisition as acquisition
from patent_box import source_transport as transport
from patent_box.contracts import ContractError, canonical_hash


@pytest.fixture(autouse=True)
def no_rate_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acquisition.time, "sleep", lambda _: None)


def plan(*entries: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "plan_id": "TEST.PLAN",
        "public_data_only": True,
        "reviewed_by": "Synthetic research-plan reviewer",
        "reviewed_at": "2020-01-01T00:00:00+00:00",
        "review_basis": "Isolated transport and reference tests, no legal claim",
        "limits": {
            "max_requests": 10,
            "max_bytes": 10000,
            "timeout_seconds": 5,
            "min_interval_seconds": 1,
        },
        "scopes": [
            {
                "scope_id": "PUBLIC",
                "authority": "Fictional test authority",
                "topic": "Test public sources",
                "window_start": "2020-01-01",
                "window_end": "2026-09-29",
                "allowed_hosts": ["institution.example"],
                "entry_urls": list(entries) or ["https://institution.example/index"],
            }
        ],
    }


def metadata() -> dict[str, Any]:
    return {
        "authority": "Test authority",
        "document_type": "INDIVIDUAL_RULING",
        "number": "test",
        "published_on": None,
        "effective_from": None,
        "effective_to": None,
        "affected_from": None,
        "affected_to": None,
        "regime": "UNKNOWN",
        "rule_ids": [],
        "relationship": "NEW",
        "previous_source_ids": [],
        "applicability_rationale": "Not assessed in a transport test",
    }


def review(
    selection: dict[str, Any] | None = None,
    decisions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "reviewed_by": "Synthetic review",
        "reviewed_at": "2020-01-01T00:00:00+00:00",
        "scope_reviews": [
            {
                "scope_id": "PUBLIC",
                "pagination_complete": True,
                "coverage_reason": "One-page fixture scope",
                "link_decisions": decisions or [],
            }
        ],
        "source_selections": (
            []
            if selection is None
            else [
                {
                    "source_id": "SOURCE.ONE",
                    "receipt_id": selection["receipt_id"],
                    "metadata": metadata(),
                }
            ]
        ),
        "source_exclusions": [],
    }


def scan(tmp_path: Path, *entries: str) -> Path:
    return Path(acquisition.open_scan(plan(*entries), tmp_path)["directory"])


def fetch_html(body: bytes):
    def fetch(url: str, **_: Any) -> transport.PublicResponse:
        return transport.PublicResponse(url, "text/html; charset=utf-8", body)

    return fetch


def document_scan(tmp_path: Path, body: bytes) -> Path:
    root = scan(tmp_path, "https://institution.example/document")
    row = acquisition.acquire(
        root,
        scope_id="PUBLIC",
        url="https://institution.example/document",
        kind="DOCUMENT",
        fetcher=fetch_html(body),
    )
    acquisition.finish_scan(root, review(row))
    return root


def test_listing_discovers_document_absent_from_plan(tmp_path: Path) -> None:
    root = scan(tmp_path)
    listing = acquisition.acquire(
        root,
        scope_id="PUBLIC",
        url="https://institution.example/index",
        kind="LISTING",
        fetcher=fetch_html(b'<a href="/new-rule">New rule</a>'),
    )
    document = acquisition.acquire(
        root,
        scope_id="PUBLIC",
        url=listing["links"][0]["url"],
        kind="DOCUMENT",
        parent_receipt_id=listing["receipt_id"],
        fetcher=fetch_html(b"<p>New document fixture</p>"),
    )
    decision = {
        "receipt_id": listing["receipt_id"],
        "link_id": listing["links"][0]["link_id"],
        "classification": "DISCOVERED_DOCUMENT",
        "reason": "Synthetic host choice",
    }

    final = acquisition.finish_scan(root, review(document, [decision]))

    assert final["snapshot"]["coverage"] == "COMPLETE_DECLARED_SCOPE"
    assert (
        final["snapshot"]["sources"][0]["url"] == "https://institution.example/new-rule"
    )
    assert final["snapshot"]["sources"][0]["impact_reviewed"] is False
    assert final["source_activation"] == "NONE"


def test_unobserved_link_cannot_be_fetched_as_discovery(tmp_path: Path) -> None:
    root = scan(tmp_path)

    with pytest.raises(ContractError, match="not a reviewed entry"):
        acquisition.acquire(
            root,
            scope_id="PUBLIC",
            url="https://institution.example/invented",
            kind="DOCUMENT",
            fetcher=fetch_html(b"unused"),
        )


def test_missing_link_review_keeps_coverage_partial(tmp_path: Path) -> None:
    root = scan(tmp_path)
    acquisition.acquire(
        root,
        scope_id="PUBLIC",
        url="https://institution.example/index",
        kind="LISTING",
        fetcher=fetch_html(b'<a href="/next-page">More</a>'),
    )

    final = acquisition.finish_scan(root, review())

    assert final["status"] == "PARTIAL_SCAN"
    assert "undisposed discovered link" in final["gaps"][0]


def test_unfetched_pagination_page_keeps_coverage_partial(tmp_path: Path) -> None:
    root = scan(tmp_path)
    listing = acquisition.acquire(
        root,
        scope_id="PUBLIC",
        url="https://institution.example/index",
        kind="LISTING",
        fetcher=fetch_html(b'<a href="/page-2">More</a>'),
    )
    decision = {
        "receipt_id": listing["receipt_id"],
        "link_id": listing["links"][0]["link_id"],
        "classification": "LISTING_PAGE",
        "reason": "Following page not acquired",
    }

    final = acquisition.finish_scan(root, review(decisions=[decision]))

    assert final["snapshot"]["coverage"] == "PARTIAL"
    assert "relevant document/page not acquired" in final["gaps"][0]


def test_transport_failure_is_preserved_as_partial_scan(tmp_path: Path) -> None:
    root = scan(tmp_path, "https://institution.example/document")

    def unavailable(*_: Any, **kwargs: Any) -> transport.PublicResponse:
        raise transport.FetchError("HTTP status 503")

    row = acquisition.acquire(
        root,
        scope_id="PUBLIC",
        url="https://institution.example/document",
        kind="DOCUMENT",
        fetcher=unavailable,
    )

    final = acquisition.finish_scan(root, review(row))

    assert row["original_sha256"] is None
    assert final["status"] == "PARTIAL_SCAN"
    assert final["snapshot"]["sources"][0]["fetch_status"] == "HTTP_ERROR"


def test_acquired_document_needs_selection_or_exclusion(tmp_path: Path) -> None:
    root = scan(tmp_path)
    acquisition.acquire(
        root,
        scope_id="PUBLIC",
        url="https://institution.example/index",
        kind="DOCUMENT",
        fetcher=fetch_html(b"<p>Document</p>"),
    )

    final = acquisition.finish_scan(root, review())

    assert "Acquired documents remain without source dispositions" in final["gaps"]


def test_changed_original_with_same_text_requires_visual_review(tmp_path: Path) -> None:
    before = document_scan(tmp_path / "before", b'<p class="old">Same words</p>')
    after = document_scan(tmp_path / "after", b'<p class="new">Same words</p>')

    result = acquisition.compare_scans(before, after)

    assert result["events"][0]["text_comparison"] == "TEXT_UNCHANGED"
    assert result["events"][0]["visual_review_required"] is True
    assert result["events"][0]["legal_effect"] == "UNREVIEWED"


def test_changed_words_are_distinct_from_legal_effect(tmp_path: Path) -> None:
    before = document_scan(tmp_path / "before", b"<p>Before</p>")
    after = document_scan(tmp_path / "after", b"<p>After</p>")

    result = acquisition.compare_scans(before, after)

    assert result["events"][0]["text_comparison"] == "TEXT_CHANGED"
    assert result["events"][0]["changes_active_rules"] is False


def test_unchanged_sources_produce_no_change_event(tmp_path: Path) -> None:
    before = document_scan(tmp_path / "before", b"<p>Same</p>")
    after = document_scan(tmp_path / "after", b"<p>Same</p>")

    result = acquisition.compare_scans(before, after)

    assert result["events"] == []
    assert result["status"] == "COMPARED_DECLARED_SCOPE"


def test_source_change_proposes_reopening_without_overwriting_approved_case(
    tmp_path: Path,
) -> None:
    before = document_scan(tmp_path / "before", b"<p>Before</p>")
    after = document_scan(tmp_path / "after", b"<p>After</p>")
    comparison = acquisition.compare_scans(before, after)
    case_index = {
        "schema_version": "1.0",
        "cases": [
            {
                "case_id": "opaque-001",
                "regime": "NEW",
                "state": "APPROVED",
                "period_start": "2025-01-01",
                "period_end": "2025-12-31",
                "rule_ids": ["RULE.ONE"],
                "approved_hash": "a" * 64,
            }
        ],
    }
    unchanged = copy.deepcopy(case_index)

    result = acquisition.write_impact_queue(
        comparison, case_index, tmp_path / "private-queue.json"
    )

    assert case_index == unchanged
    assert result["items"][0]["action"] == "PROPOSE_REOPEN"
    assert result["items"][0]["previous_case_hash"] == "a" * 64
    assert result["items"][0]["automatic_mutation"] is False


def test_proposed_old_regime_classification_does_not_hide_impacts(
    tmp_path: Path,
) -> None:
    root = scan(tmp_path, "https://institution.example/document")
    document = acquisition.acquire(
        root,
        scope_id="PUBLIC",
        url="https://institution.example/document",
        kind="DOCUMENT",
        fetcher=fetch_html(b"<p>Unreviewed scope</p>"),
    )
    proposed = review(document)
    proposed["source_selections"][0]["metadata"].update(
        regime="OLD", affected_from="2030-01-01", rule_ids=["OLD.RULE"]
    )

    final = acquisition.finish_scan(root, proposed)

    assert final["snapshot"]["sources"][0]["regime"] == "UNKNOWN"
    assert final["snapshot"]["sources"][0]["affected_from"] is None
    assert final["snapshot"]["sources"][0]["rule_ids"] == []


def test_finalized_scan_cannot_be_reused_for_new_fetches(tmp_path: Path) -> None:
    root = document_scan(tmp_path, b"<p>Completed</p>")

    with pytest.raises(ContractError, match="immutable"):
        acquisition.acquire(
            root,
            scope_id="PUBLIC",
            url="https://institution.example/document",
            kind="DOCUMENT",
            fetcher=fetch_html(b"changed"),
        )


def test_tampered_original_fails_before_comparison(tmp_path: Path) -> None:
    before = document_scan(tmp_path / "before", b"<p>Original</p>")
    after = document_scan(tmp_path / "after", b"<p>Next</p>")
    final = json.loads((before / "final.json").read_text())
    (
        before / "objects" / final["snapshot"]["sources"][0]["content_sha256"]
    ).write_bytes(b"tampered")

    with pytest.raises(ContractError, match="changed or is missing"):
        acquisition.compare_scans(before, after)


def test_pdf_text_is_bound_to_original_and_extractor_version(tmp_path: Path) -> None:
    root = scan(tmp_path, "https://institution.example/document")

    def pdf_fetch(url: str, **_: Any) -> transport.PublicResponse:
        return transport.PublicResponse(
            url, "application/pdf", b"%PDF-synthetic-byte-fixture"
        )

    row = acquisition.acquire(
        root,
        scope_id="PUBLIC",
        url="https://institution.example/document",
        kind="DOCUMENT",
        fetcher=pdf_fetch,
    )
    text = tmp_path / "extracted.txt"
    text.write_text("Synthetic host extraction fixture")
    extraction = acquisition.attach_text(
        root, receipt_id=row["receipt_id"], text_path=text, extractor="test-extractor/1"
    )

    final = acquisition.finish_scan(root, review(row))

    assert final["extraction"]["SOURCE.ONE"] == extraction
    assert extraction["original_sha256"] == row["original_sha256"]
    assert final["snapshot"]["coverage"] == "COMPLETE_DECLARED_SCOPE"


@pytest.mark.parametrize(
    "url",
    [
        "http://institution.example/x",
        "https://institution.example.evil/x",
        "https://user:pass@institution.example/x",
        "https://institution.example/x?token=secret",
        "https://institution.example:8443/x",
    ],
)
def test_unapproved_scheme_authority_or_credentials_are_rejected(url: str) -> None:
    with pytest.raises(transport.FetchError):
        transport.checked_url(url, {"institution.example"})


@pytest.mark.parametrize(
    "addresses",
    [
        ["127.0.0.1"],
        ["169.254.169.254"],
        ["10.0.0.1"],
        ["::1"],
        ["224.0.0.1"],
        ["::ffff:127.0.0.1"],
        ["93.184.216.34", "192.168.1.1"],
    ],
)
def test_private_and_mixed_dns_answers_are_rejected(
    monkeypatch: pytest.MonkeyPatch, addresses: list[str]
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in addresses
        ],
    )

    with pytest.raises(transport.FetchError, match="forbidden"):
        transport.public_addresses("institution.example")


def test_public_dns_answers_are_passed_as_numeric_addresses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )

    result = transport.public_addresses("institution.example")

    assert result == ["93.184.216.34"]


def test_whole_request_timeout_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def expired(*args: Any, **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd="source-worker", timeout=1)

    monkeypatch.setattr(subprocess, "run", expired)

    with pytest.raises(transport.FetchError, match="deadline"):
        transport.fetch_public(
            "https://institution.example/document",
            allowed_hosts={"institution.example"},
            timeout=1,
        )


class _ResponseFixture:
    def __init__(self, status: int, headers: dict[str, str], body: bytes = b"") -> None:
        self.status, self.headers, self.body = status, headers, body
        self.read_limit: int | None = None

    def getheader(self, name: str, default: Any = None) -> Any:
        return self.headers.get(name, default)

    def read(self, limit: int) -> bytes:
        self.read_limit = limit
        return self.body[:limit]


def stub_connection(
    monkeypatch: pytest.MonkeyPatch, response: _ResponseFixture
) -> list[dict[str, Any]]:
    calls = []

    class Connection:
        def __init__(self, host: str, address: str, timeout: float) -> None:
            calls.append({"host": host, "address": address, "timeout": timeout})

        def request(self, method: str, path: str, headers: dict[str, str]) -> None:
            calls[-1].update(method=method, path=path, headers=headers)

        def getresponse(self) -> _ResponseFixture:
            return response

        def close(self) -> None:
            calls[-1]["closed"] = True

    monkeypatch.setattr(transport, "_PinnedHTTPSConnection", Connection)

    def isolated_worker(
        arguments: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[bytes]:
        # Keep the public API as Act; emulate only the process boundary so DNS,
        # TLS destination and response fixtures remain self-contained.
        stream = io.StringIO()
        with monkeypatch.context() as worker_context, redirect_stdout(stream):
            worker_context.setattr(sys, "argv", [arguments[2], arguments[3]])
            code = transport._worker()
        return subprocess.CompletedProcess(
            arguments, code, stream.getvalue().encode(), b""
        )

    monkeypatch.setattr(subprocess, "run", isolated_worker)
    return calls


def test_redirect_to_private_address_is_rejected_before_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, *args, **kwargs: [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("127.0.0.1" if host == "127.0.0.1" else "93.184.216.34", 443),
            )
        ],
    )
    calls = stub_connection(
        monkeypatch, _ResponseFixture(302, {"Location": "https://127.0.0.1/metadata"})
    )

    with pytest.raises(transport.FetchError, match="forbidden"):
        transport.fetch_public(
            "https://institution.example/start",
            allowed_hosts={"institution.example", "127.0.0.1"},
            max_bytes=100,
            timeout=5,
        )
    assert len(calls) == 1
    assert calls[0]["address"] == "93.184.216.34"
    assert calls[0]["closed"] is True


def test_body_over_limit_is_rejected_even_without_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(transport, "public_addresses", lambda _: ["93.184.216.34"])
    maximum = 5
    response = _ResponseFixture(200, {"Content-Type": "text/plain"}, b"123456789")
    stub_connection(monkeypatch, response)

    with pytest.raises(transport.FetchError, match="byte limit"):
        transport.fetch_public(
            "https://institution.example/doc",
            allowed_hosts={"institution.example"},
            max_bytes=maximum,
            timeout=5,
        )
    assert response.read_limit == maximum + 1


def test_response_length_does_not_allow_truncated_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(transport, "public_addresses", lambda _: ["93.184.216.34"])
    stub_connection(
        monkeypatch, _ResponseFixture(200, {"Content-Length": "9"}, b"12345")
    )

    with pytest.raises(transport.FetchError, match="Truncated"):
        transport.fetch_public(
            "https://institution.example/doc",
            allowed_hosts={"institution.example"},
            max_bytes=10,
            timeout=5,
        )


def test_public_request_sends_no_session_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(transport, "public_addresses", lambda _: ["93.184.216.34"])
    calls = stub_connection(
        monkeypatch, _ResponseFixture(200, {"Content-Type": "text/plain"}, b"text")
    )

    response = transport.fetch_public(
        "https://institution.example/doc",
        allowed_hosts={"institution.example"},
        max_bytes=10,
        timeout=5,
    )

    assert response.body == b"text"
    assert "Cookie" not in calls[0]["headers"]
    assert "Authorization" not in calls[0]["headers"]
    assert calls[0]["headers"]["Accept-Encoding"] == "identity"


def test_rate_limit_is_observed_between_source_acquisitions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    waits = []
    monkeypatch.setattr(acquisition.time, "sleep", waits.append)
    root = scan(tmp_path)
    acquisition.acquire(
        root,
        scope_id="PUBLIC",
        url="https://institution.example/index",
        kind="DOCUMENT",
        fetcher=fetch_html(b"<p>first</p>"),
    )

    acquisition.acquire(
        root,
        scope_id="PUBLIC",
        url="https://institution.example/index",
        kind="DOCUMENT",
        fetcher=fetch_html(b"<p>second</p>"),
    )

    assert len(waits) == 1
    assert 0 < waits[0] <= 1
