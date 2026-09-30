"""Immutable public-source acquisition, discovery records and coverage review.

The host model chooses scope, follows pagination and assesses source relevance.
Code owns bounded retrieval, original bytes, hashes and exact reference closure.
A completed declared scope is never a claim of exhaustive legal monitoring.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterator
from urllib.parse import urljoin

from .contracts import (
    ContractError,
    canonical_hash,
    file_hash,
    indexed,
    read_json,
    validate,
)
from .monitor import compare_snapshots, impact_queue
from .source_transport import (
    MAX_BYTES,
    FetchError,
    PublicResponse,
    checked_url,
    fetch_public,
)

__all__ = [
    "open_scan",
    "acquire",
    "attach_text",
    "finish_scan",
    "read_final_scan",
    "compare_scans",
    "write_impact_queue",
]
MAX_LINKS = 5000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save(path: Path, value: Any) -> None:
    if path.is_symlink() or path.parent.is_symlink():
        raise ContractError("Symlink artifacts are forbidden")
    raw = (
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise ContractError("Source record exceeds byte budget")
    with path.open("xb") as stream:
        stream.write(raw)
    path.chmod(0o600)


def _read(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ContractError("Expected a bounded regular source record")
    value = read_json(path)
    if not isinstance(value, dict):
        raise ContractError("Expected a source-record object")
    return value


def _hash(value: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ContractError("Invalid artifact digest")
    return value


def _put_bytes(root: Path, value: bytes) -> str:
    if len(value) > MAX_BYTES:
        raise ContractError("Source object exceeds size limit")
    digest = hashlib.sha256(value).hexdigest()
    path = root / "objects" / digest
    if path.exists():
        if path.is_symlink() or not path.is_file() or file_hash(path) != digest:
            raise ContractError("Existing source object integrity failed")
    else:
        with path.open("xb") as stream:
            stream.write(value)
        path.chmod(0o600)
    return digest


def _bytes(root: Path, digest: str) -> bytes:
    path = root / "objects" / _hash(digest)
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > MAX_BYTES
        or file_hash(path) != digest
    ):
        raise ContractError("Source object changed or is missing")
    return path.read_bytes()


def _bound(root: Path) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise ContractError("Expected a source scan directory")
    for name in ("objects", "receipts", "texts"):
        if (root / name).is_symlink() or not (root / name).is_dir():
            raise ContractError("Invalid source scan storage")
    session = _read(root / "scan.json")
    if (
        session["directory"] != str(root.resolve())
        or canonical_hash(session["plan"]) != session["plan_hash"]
    ):
        raise ContractError("Research plan or scan binding changed")
    validate(session["plan"], "source-plan.schema.json")
    return session


@contextmanager
def _writing(root: Path) -> Iterator[dict[str, Any]]:
    session = _bound(root)
    lock = root / ".write-lock"
    lock.mkdir(mode=0o700)
    try:
        if (root / "final.json").exists():
            raise ContractError("Finalized scans are immutable; open a new scan")
        yield session
    finally:
        lock.rmdir()


def _receipt(root: Path, receipt_id: str) -> dict[str, Any]:
    row = _read(root / "receipts" / (_hash(receipt_id) + ".json"))
    if canonical_hash(row) != receipt_id:
        raise ContractError("Acquisition receipt changed")
    if row["original_sha256"] is not None:
        _bytes(root, row["original_sha256"])
    return row


def _receipts(root: Path) -> dict[str, dict[str, Any]]:
    return {
        p.stem: _receipt(root, p.stem)
        for p in sorted((root / "receipts").glob("*.json"))
    }


def _text_record(root: Path, receipt_id: str) -> dict[str, Any] | None:
    path = root / "texts" / (_hash(receipt_id) + ".json")
    if not path.exists():
        return None
    record = _read(path)
    receipt = _receipt(root, receipt_id)
    if (
        record["receipt_id"] != receipt_id
        or record["original_sha256"] != receipt["original_sha256"]
    ):
        raise ContractError("Extracted text belongs to another original")
    _bytes(root, record["text_sha256"])
    return record


def open_scan(plan: dict[str, Any], output_root: Path) -> dict[str, Any]:
    """Start a public-only scan from an explicit host-reviewed scope and window."""
    validate(plan, "source-plan.schema.json")
    if not plan["reviewed_by"].strip() or not plan["review_basis"].strip():
        raise ContractError("Research plan needs a named review and rationale")
    if datetime.fromisoformat(plan["reviewed_at"]) > datetime.now(timezone.utc):
        raise ContractError("Research plan review cannot be in the future")
    indexed(plan["scopes"], "scope_id")
    for scope in plan["scopes"]:
        if scope["window_start"] > scope["window_end"]:
            raise ContractError("Invalid research time window")
        for url in scope["entry_urls"]:
            checked_url(url, set(scope["allowed_hosts"]))
    if output_root.is_symlink():
        raise ContractError("Symlink scan roots are forbidden")
    output_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root = output_root / ("source_scan_" + uuid.uuid4().hex)
    root.mkdir(mode=0o700)
    for name in ("objects", "receipts", "texts"):
        (root / name).mkdir(mode=0o700)
    session = {
        "schema_version": "1.0",
        "directory": str(root.resolve()),
        "created_at": _now(),
        "plan": plan,
        "plan_hash": canonical_hash(plan),
        "data_boundary": "PUBLIC_SOURCE_METADATA_ONLY",
        "review_assurance": "HOST_RESEARCH_PLAN_ASSERTION_NOT_PROFESSIONAL_APPROVAL",
    }
    _save(root / "scan.json", session)
    return session


class _HTMLDiscovery(HTMLParser):
    def __init__(self, base_url: str, hosts: set[str]) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url, self.hosts = base_url, hosts
        self.links: dict[str, dict[str, Any]] = {}
        self.text: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self.hidden += 1
        if tag != "a" or self.hidden:
            return
        href = dict(attrs).get("href")
        if not href:
            return
        target = urljoin(self.base_url, href)
        try:
            target = checked_url(target, self.hosts)
            allowed, reason = True, "Within configured public host scope"
        except FetchError as error:
            allowed, reason = False, str(error)
        link_id = canonical_hash(target)
        self.links[link_id] = {
            "link_id": link_id,
            "url": target,
            "allowed": allowed,
            "security_reason": reason,
        }
        if len(self.links) > MAX_LINKS:
            raise FetchError("HTML link budget exceeded")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.text.append(data)


def _inspect(
    response: PublicResponse, hosts: set[str]
) -> tuple[bytes | None, str | None, list[dict[str, Any]]]:
    media = response.content_type.split(";", 1)[0].strip().lower()
    if media not in (
        "text/html",
        "text/plain",
        "application/json",
        "application/xml",
        "text/xml",
    ):
        return None, None, []
    charset = re.search(r"charset=[\"']?([^\s;\"']+)", response.content_type, re.I)
    try:
        text = response.body.decode(charset.group(1) if charset else "utf-8")
    except (LookupError, UnicodeError) as error:
        raise FetchError("Text encoding requires explicit host extraction") from error
    if media == "text/html":
        parser = _HTMLDiscovery(response.url, hosts)
        parser.feed(text)
        parser.close()
        return (
            "\n".join(parser.text).encode("utf-8"),
            "stdlib-htmlparser/" + sys.version.split()[0],
            list(parser.links.values()),
        )
    return text.replace("\r\n", "\n").encode("utf-8"), "plain-text/1", []


def acquire(
    root: Path,
    *,
    scope_id: str,
    url: str,
    kind: str,
    parent_receipt_id: str | None = None,
    fetcher: Callable[..., PublicResponse] = fetch_public,
) -> dict[str, Any]:
    """Fetch an entry or a link actually discovered on a selected listing page."""
    with _writing(root) as session:
        scopes = indexed(session["plan"]["scopes"], "scope_id")
        if scope_id not in scopes or kind not in ("LISTING", "DOCUMENT"):
            raise ContractError("Unknown scope or source kind")
        scope = scopes[scope_id]
        hosts = set(scope["allowed_hosts"])
        url = checked_url(url, hosts)
        if parent_receipt_id is None:
            if url not in {checked_url(u, hosts) for u in scope["entry_urls"]}:
                raise ContractError("URL is not a reviewed entry or a discovered link")
        else:
            parent = _receipt(root, parent_receipt_id)
            if (
                parent["scope_id"] != scope_id
                or parent["kind"] != "LISTING"
                or parent["fetch_status"] != "OK"
            ):
                raise ContractError(
                    "Discovery parent is not a successful listing in this scope"
                )
            if not any(
                link["url"] == url and link["allowed"] for link in parent["links"]
            ):
                raise ContractError("URL was not discovered on the cited listing")
        previous = _receipts(root)
        limits = session["plan"]["limits"]
        if len(previous) >= limits["max_requests"]:
            raise ContractError("Research request budget exhausted")
        if previous:
            last = max(
                datetime.fromisoformat(r["acquired_at"]) for r in previous.values()
            )
            elapsed = (datetime.now(timezone.utc) - last).total_seconds()
            if elapsed < -1:
                raise ContractError("Acquisition clock moved backwards")
            time.sleep(max(0, limits["min_interval_seconds"] - elapsed))
        row: dict[str, Any] = {
            "scan_plan_hash": session["plan_hash"],
            "sequence": len(previous) + 1,
            "scope_id": scope_id,
            "url": url,
            "kind": kind,
            "parent_receipt_id": parent_receipt_id,
            "acquired_at": _now(),
            "fetch_status": "HTTP_ERROR",
            "error": None,
            "original_sha256": None,
            "final_url": None,
            "content_type": None,
            "redirects": [],
            "etag": None,
            "last_modified": None,
            "links": [],
            "text_status": "NOT_EXTRACTED",
            "text_error": None,
        }
        text: bytes | None = None
        extractor: str | None = None
        try:
            response = fetcher(
                url,
                allowed_hosts=hosts,
                max_bytes=limits["max_bytes"],
                timeout=limits["timeout_seconds"],
            )
            checked_url(response.url, hosts)
            if len(response.body) > limits["max_bytes"]:
                raise FetchError("Response exceeds the reviewed byte budget")
            row.update(
                fetch_status="OK",
                original_sha256=_put_bytes(root, response.body),
                final_url=response.url,
                content_type=response.content_type,
                redirects=list(response.redirects),
                etag=response.etag,
                last_modified=response.last_modified,
            )
            try:
                text, extractor, row["links"] = _inspect(response, hosts)
                if text is not None:
                    row["text_status"] = "EXTRACTED"
            except FetchError as error:
                row["text_status"], row["text_error"] = "FAILED", str(error)
        except FetchError as error:
            row["error"] = str(error)
            row["fetch_status"] = (
                "TIMEOUT" if "deadline" in str(error) else "HTTP_ERROR"
            )
        row["acquired_at"] = _now()
        receipt_id = canonical_hash(row)
        _save(root / "receipts" / (receipt_id + ".json"), row)
        if text is not None:
            _save(
                root / "texts" / (receipt_id + ".json"),
                {
                    "receipt_id": receipt_id,
                    "original_sha256": row["original_sha256"],
                    "text_sha256": _put_bytes(root, text),
                    "extractor": extractor,
                    "method": "BUILT_IN_EXTRACTION",
                    "recorded_at": _now(),
                },
            )
        return {"receipt_id": receipt_id, **row}


def attach_text(
    root: Path, *, receipt_id: str, text_path: Path, extractor: str
) -> dict[str, Any]:
    """Record a host-extracted PDF/OCR text version against the unchanged original."""
    with _writing(root):
        receipt = _receipt(root, receipt_id)
        if receipt["fetch_status"] != "OK" or not extractor.strip():
            raise ContractError(
                "Text needs an acquired original and extractor identity/version"
            )
        if (
            text_path.is_symlink()
            or not text_path.is_file()
            or text_path.stat().st_size > MAX_BYTES
        ):
            raise ContractError("Extracted text must be a bounded selected file")
        raw = text_path.read_bytes()
        raw.decode("utf-8")
        record = {
            "receipt_id": receipt_id,
            "original_sha256": receipt["original_sha256"],
            "text_sha256": _put_bytes(root, raw),
            "extractor": extractor,
            "method": "HOST_EXTRACTION_ATTESTATION",
            "recorded_at": _now(),
        }
        _save(root / "texts" / (receipt_id + ".json"), record)
        return record


def finish_scan(root: Path, review: dict[str, Any]) -> dict[str, Any]:
    """Close declared coverage only when all acquired links have explicit dispositions."""
    validate(review, "source-coverage-review.schema.json")
    if not review["reviewed_by"].strip() or datetime.fromisoformat(
        review["reviewed_at"]
    ) > datetime.now(timezone.utc):
        raise ContractError("Coverage review needs a current named reviewer")
    with _writing(root) as session:
        receipts = _receipts(root)
        scopes = indexed(session["plan"]["scopes"], "scope_id")
        reviewed = indexed(review["scope_reviews"], "scope_id")
        if set(reviewed) != set(scopes):
            raise ContractError("Coverage review must account for every declared scope")
        gaps: list[str] = []
        for scope_id, scope in scopes.items():
            part = reviewed[scope_id]
            if not part["pagination_complete"] or not part["coverage_reason"].strip():
                gaps.append(scope_id + ": pagination or window coverage unresolved")
            entries = {
                checked_url(u, set(scope["allowed_hosts"])) for u in scope["entry_urls"]
            }
            scope_receipts = {
                rid: r for rid, r in receipts.items() if r["scope_id"] == scope_id
            }
            fetched = {
                r["url"] for r in scope_receipts.values() if r["fetch_status"] == "OK"
            }
            if not entries <= fetched:
                gaps.append(scope_id + ": missing or unavailable entry pages")
            decisions = {}
            for decision in part["link_decisions"]:
                key = (decision["receipt_id"], decision["link_id"])
                if key in decisions:
                    raise ContractError("Duplicate link disposition")
                decisions[key] = decision
            links = {
                (rid, link["link_id"]): link
                for rid, r in scope_receipts.items()
                for link in r["links"]
            }
            if set(decisions) - set(links):
                raise ContractError(
                    "Coverage refers to a link outside its acquired scope"
                )
            for key, link in links.items():
                decision = decisions.get(key)
                if decision is None or not decision["reason"].strip():
                    gaps.append(
                        scope_id + ": undisposed discovered link " + link["link_id"]
                    )
                elif decision["classification"] in (
                    "DISCOVERED_DOCUMENT",
                    "LISTING_PAGE",
                ):
                    if not link["allowed"] or link["url"] not in fetched:
                        gaps.append(scope_id + ": relevant document/page not acquired")
            for rid, row in scope_receipts.items():
                if row["fetch_status"] != "OK":
                    gaps.append(scope_id + ": failed retrieval " + rid)
                elif _text_record(root, rid) is None:
                    gaps.append(scope_id + ": no extractable text " + rid)
                if row["kind"] == "LISTING" and (
                    row["text_status"] != "EXTRACTED"
                    or (row["content_type"] or "").split(";", 1)[0].strip().lower()
                    != "text/html"
                ):
                    gaps.append(scope_id + ": listing discovery is incomplete " + rid)
        selections = indexed(review["source_selections"], "source_id")
        selected_receipts = indexed(review["source_selections"], "receipt_id")
        excluded_receipts = indexed(review["source_exclusions"], "receipt_id")
        if set(selected_receipts) & set(excluded_receipts):
            raise ContractError("A source cannot be both selected and excluded")
        for receipt_id, exclusion in excluded_receipts.items():
            if (
                receipt_id not in receipts
                or receipts[receipt_id]["kind"] != "DOCUMENT"
                or not exclusion["reason"].strip()
            ):
                raise ContractError(
                    "Source exclusion needs an acquired document and rationale"
                )
        document_ids = {
            rid for rid, row in receipts.items() if row["kind"] == "DOCUMENT"
        }
        if document_ids - set(selected_receipts) - set(excluded_receipts):
            gaps.append("Acquired documents remain without source dispositions")
        sources = []
        extraction = {}
        for source_id, selection in selections.items():
            receipt_id = selection["receipt_id"]
            if receipt_id not in receipts or receipts[receipt_id]["kind"] != "DOCUMENT":
                raise ContractError(
                    "Selected source must reference a document acquisition"
                )
            row = receipts[receipt_id]
            metadata = selection["metadata"]
            for begin, end in (
                ("effective_from", "effective_to"),
                ("affected_from", "affected_to"),
            ):
                if (
                    metadata[begin]
                    and metadata[end]
                    and metadata[begin] > metadata[end]
                ):
                    raise ContractError("Invalid proposed source-effect interval")
            # Proposed relevance never narrows case impact before professional approval.
            sources.append(
                {
                    "source_id": source_id,
                    "url": row["url"],
                    "content_sha256": row["original_sha256"],
                    "retrieved_at": row["acquired_at"],
                    "fetch_status": row["fetch_status"],
                    "rule_ids": [],
                    "impact_reviewed": False,
                    "affected_from": None,
                    "affected_to": None,
                    "regime": "UNKNOWN",
                }
            )
            extraction[source_id] = _text_record(root, receipt_id)
        coverage = "PARTIAL" if gaps else "COMPLETE_DECLARED_SCOPE"
        snapshot = {"schema_version": "1.0", "coverage": coverage, "sources": sources}
        validate(snapshot, "source-snapshot.schema.json")
        final = {
            "schema_version": "1.0",
            "plan_hash": session["plan_hash"],
            "review": review,
            "receipt_ids": sorted(receipts),
            "text_records": {rid: _text_record(root, rid) for rid in receipts},
            "snapshot": snapshot,
            "extraction": extraction,
            "gaps": gaps,
            "status": "PARTIAL_SCAN" if gaps else "COMPARED_DECLARED_SCOPE",
            "exhaustive_legal_monitoring": False,
            "source_activation": "NONE",
            "completed_at": _now(),
        }
        final["final_hash"] = canonical_hash(final)
        _save(root / "final.json", final)
        return final


def _final(root: Path) -> dict[str, Any]:
    session = _bound(root)
    final = _read(root / "final.json")
    if (
        final["plan_hash"] != session["plan_hash"]
        or canonical_hash({k: v for k, v in final.items() if k != "final_hash"})
        != final["final_hash"]
    ):
        raise ContractError("Final scan integrity failed")
    if sorted(_receipts(root)) != final["receipt_ids"]:
        raise ContractError("Acquisition population changed after finalization")
    if {rid: _text_record(root, rid) for rid in final["receipt_ids"]} != final[
        "text_records"
    ]:
        raise ContractError("Reviewed text population changed after finalization")
    for source_id, selection in indexed(
        final["review"]["source_selections"], "source_id"
    ).items():
        if (
            _text_record(root, selection["receipt_id"])
            != final["extraction"][source_id]
        ):
            raise ContractError("Source extraction changed after finalization")
    return final


def read_final_scan(root: Path) -> dict[str, Any]:
    """Read a finalized scan after checking its original/text receipt integrity."""
    return _final(root)


def compare_scans(before_root: Path, after_root: Path) -> dict[str, Any]:
    """Distinguish byte/text changes without inferring whether the law changed."""
    before, after = _final(before_root), _final(after_root)
    comparison = compare_snapshots(before["snapshot"], after["snapshot"])
    event_sources = {event["source_id"] for event in comparison["events"]}
    for source_id in sorted(
        set(before["extraction"]) & set(after["extraction"]) - event_sources
    ):
        left, right = before["extraction"][source_id], after["extraction"][source_id]
        if (
            left
            and right
            and any(left[key] != right[key] for key in ("extractor", "text_sha256"))
        ):
            source = indexed(after["snapshot"]["sources"], "source_id")[source_id]
            comparison["events"].append(
                {
                    "source_id": source_id,
                    "kind": "EXTRACTION_CHANGED_REVIEW_REQUIRED",
                    "rule_ids": [],
                    "mapping_unknown": True,
                    "affected_from": None,
                    "affected_to": None,
                    "before_hash": source["content_sha256"],
                    "after_hash": source["content_sha256"],
                    "regime": "UNKNOWN",
                    "regime_reviewed": False,
                    "changes_active_rules": False,
                }
            )
    for event in comparison["events"]:
        left, right = before["extraction"].get(event["source_id"]), after[
            "extraction"
        ].get(event["source_id"])
        state = "NOT_COMPARABLE"
        if left and right:
            if left["extractor"] != right["extractor"]:
                state = "EXTRACTOR_CHANGED"
            else:
                state = (
                    "TEXT_UNCHANGED"
                    if left["text_sha256"] == right["text_sha256"]
                    else "TEXT_CHANGED"
                )
        event["text_comparison"] = state
        event["legal_effect"] = "UNREVIEWED"
        event["visual_review_required"] = (
            event["kind"] == "CONTENT_CHANGED_REVIEW_REQUIRED"
            and state == "TEXT_UNCHANGED"
        )
        event["event_id"] = canonical_hash(
            {k: v for k, v in event.items() if k != "event_id"}
        )
    comparison["before_scan_hash"] = before["final_hash"]
    comparison["after_scan_hash"] = after["final_hash"]
    return comparison


def write_impact_queue(
    comparison: dict[str, Any], case_index: dict[str, Any], destination: Path
) -> dict[str, Any]:
    """Write an immutable private review queue; never reopen or edit a case automatically."""
    result = impact_queue(comparison, case_index)
    _save(destination, result)
    return result
