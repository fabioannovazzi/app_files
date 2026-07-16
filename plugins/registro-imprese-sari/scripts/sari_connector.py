"""Bounded read-only connector for an explicitly authorized public SARI lookup.

SARI's JSON routes are public frontend implementation details, not a documented
API. This connector therefore fails closed unless the caller records both a
case-specific network approval and a separate written-use authorization. The
ordinary workflow uses the public browser and registers the user-selected
official result with ``register_official_source.py`` instead.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import logging
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from case_core import (
    PLUGIN_NAME,
    assert_generic_public_query,
    ensure_safe_output_dir,
    iso_now,
    load_json_object,
    normalize_html_text,
    safe_identifier,
    sha256_bytes,
    write_private_json,
)

__all__ = [
    "SariClient",
    "SariConnectorError",
    "normalize_card",
    "normalize_search_result",
    "run_detail",
    "run_search",
    "main",
]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SARI_ORIGIN = "https://supportospecialisticori.infocamere.it"
SARI_PREFIX = "/sariWeb/"
SARI_HOST = "supportospecialisticori.infocamere.it"
MAX_RESPONSE_BYTES = 2_000_000
MAX_RESULTS = 10
MAX_REQUESTS_PER_OPERATION = 2
TENANT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,23}$")
CARD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
AUTHORIZATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,119}$")


class SariConnectorError(RuntimeError):
    """Raised when a SARI request violates the bounded connector contract."""


class _ChamberTitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "input":
            return
        values = dict(attrs)
        if values.get("id") == "titoloAssistenza":
            self.title = str(values.get("value") or "").strip()


class _RejectRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        _validate_url(newurl)
        raise SariConnectorError(
            "SARI redirects are not allowed within the two-request operation budget"
        )


@dataclass(frozen=True)
class _Fetched:
    raw: bytes
    content_type: str
    final_url: str


def _validate_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != SARI_HOST:
        raise SariConnectorError("SARI request or redirect left the exact HTTPS host")
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise SariConnectorError(
            "SARI URL must not contain credentials or a custom port"
        )
    if not parsed.path.startswith(SARI_PREFIX):
        raise SariConnectorError("SARI URL left the allowed /sariWeb/ path")
    return url


def _authorization(value: object, *, field: str) -> str:
    text = str(value or "").strip()
    if not AUTHORIZATION_RE.fullmatch(text):
        raise SariConnectorError(
            f"{field} must be a stable 3-120 character authorization reference"
        )
    return text


def _json_payload(raw: bytes, *, context: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SariConnectorError(f"{context} did not return valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise SariConnectorError(f"{context} did not return a JSON object")
    return value


def _flatten_abstract(value: object) -> str:
    fragments: list[str] = []
    if isinstance(value, list):
        for record in value:
            if not isinstance(record, dict):
                continue
            for texts in record.values():
                if isinstance(texts, list):
                    fragments.extend(normalize_html_text(text) for text in texts)
    return " ".join(fragment for fragment in fragments if fragment).strip()


def _facet_paths(value: object) -> list[str]:
    paths: list[str] = []

    def walk(node: object, parents: list[str]) -> None:
        if not isinstance(node, dict):
            return
        description = normalize_html_text(node.get("description"))
        current = [*parents, description] if description else parents
        children = node.get("children")
        if isinstance(children, list) and children:
            for child in children:
                walk(child, current)
        elif current:
            paths.append(" > ".join(current))

    if isinstance(value, list):
        for item in value:
            walk(item, [])
    return sorted(set(paths))


def normalize_search_result(payload: dict[str, Any], *, limit: int) -> dict[str, Any]:
    """Normalize only candidate metadata; do not infer relevance or applicability."""

    result = payload.get("result")
    if not isinstance(result, dict):
        raise SariConnectorError("SARI search response is missing result")
    documents = result.get("_listdocs")
    if not isinstance(documents, list):
        raise SariConnectorError("SARI search response is missing result._listdocs")
    candidates: list[dict[str, Any]] = []
    for document in documents[:limit]:
        if not isinstance(document, dict):
            continue
        card_id = str(document.get("id_scheda") or document.get("id") or "").strip()
        if not CARD_ID_RE.fullmatch(card_id):
            continue
        candidates.append(
            {
                "card_id": card_id,
                "title": normalize_html_text(document.get("titolo")),
                "updated_at": str(document.get("dt_ultima_modifica") or "").strip()
                or None,
                "content_type": str(document.get("tipo_scheda") or "").strip() or None,
                "abstract": _flatten_abstract(document.get("_abstract")),
                "facet_paths": _facet_paths(document.get("_listfacets")),
                "selection_status": "candidate_requires_human_selection",
            }
        )
    count = result.get("_numDocs")
    return {
        "reported_result_count": count if isinstance(count, int) else len(documents),
        "returned_candidate_count": len(candidates),
        "candidates": candidates,
        "semantic_classification": "not_performed",
    }


def normalize_card(payload: dict[str, Any], *, card_id: str) -> dict[str, Any]:
    """Normalize the official fields of one human-selected SARI card."""

    fields: dict[str, str] = {}
    for key, value in payload.items():
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            text = normalize_html_text(value)
            if text:
                fields[str(key)] = text
    title = fields.get("titolo", "")
    if not title:
        raise SariConnectorError("selected SARI card has no title")
    return {
        "card_id": card_id,
        "title": title,
        "fields": fields,
        "applicability_status": "requires_professional_confirmation",
        "semantic_classification": "not_performed",
    }


class SariClient:
    """One in-memory anonymous tenant session with no cookie persistence."""

    def __init__(self, *, timeout_seconds: float = 15.0) -> None:
        self.timeout_seconds = timeout_seconds
        cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookie_jar),
            _RejectRedirectHandler(),
        )
        self.tenant = ""
        self.chamber_title = ""
        self.request_count = 0

    def _fetch(self, url: str, *, expected_content_type: str) -> _Fetched:
        _validate_url(url)
        if self.request_count >= MAX_REQUESTS_PER_OPERATION:
            raise SariConnectorError(
                f"SARI operation exceeds the {MAX_REQUESTS_PER_OPERATION}-request limit"
            )
        self.request_count += 1
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Accept": expected_content_type,
                "User-Agent": f"{PLUGIN_NAME}/0.1 bounded-read-only",
            },
        )
        try:
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                final_url = response.geturl()
                _validate_url(final_url)
                content_type = response.headers.get_content_type().lower()
                if content_type != expected_content_type:
                    raise SariConnectorError(
                        f"unexpected SARI content type {content_type!r}; expected {expected_content_type!r}"
                    )
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            raise SariConnectorError(f"SARI request failed: {exc}") from exc
        if len(raw) > MAX_RESPONSE_BYTES:
            raise SariConnectorError(
                f"SARI response exceeds {MAX_RESPONSE_BYTES} bytes"
            )
        return _Fetched(raw=raw, content_type=content_type, final_url=final_url)

    def initialize_tenant(self, tenant: str, *, expected_chamber: str) -> _Fetched:
        normalized_tenant = str(tenant or "").strip().lower()
        if not TENANT_RE.fullmatch(normalized_tenant):
            raise SariConnectorError("tenant must be one conservative SARI slug")
        expected = " ".join(str(expected_chamber or "").split())
        if len(expected) < 4 or len(expected) > 180:
            raise SariConnectorError(
                "expected chamber title must contain 4-180 characters"
            )
        fetched = self._fetch(
            f"{SARI_ORIGIN}{SARI_PREFIX}{urllib.parse.quote(normalized_tenant)}",
            expected_content_type="text/html",
        )
        parser = _ChamberTitleParser()
        parser.feed(fetched.raw.decode("utf-8", errors="strict"))
        parser.close()
        actual = " ".join(parser.title.split())
        if not actual or expected.casefold() not in actual.casefold():
            raise SariConnectorError(
                "SARI tenant/chamber mismatch; use the official browser directory instead "
                f"(expected {expected!r}, observed {actual!r})"
            )
        self.tenant = normalized_tenant
        self.chamber_title = actual
        return fetched

    def search(self, query: str, *, limit: int) -> _Fetched:
        if not self.tenant:
            raise SariConnectorError("initialize tenant before search")
        params = urllib.parse.urlencode(
            {
                "query": query,
                "start": 0,
                "size": limit,
                "facetnode": "",
                "pageType": "search",
                "userRole": "mypageUD",
            }
        )
        return self._fetch(
            f"{SARI_ORIGIN}{SARI_PREFIX}faq/get/?{params}",
            expected_content_type="application/json",
        )

    def fetch_card(self, card_id: str) -> _Fetched:
        if not self.tenant:
            raise SariConnectorError("initialize tenant before fetching a card")
        if not CARD_ID_RE.fullmatch(card_id):
            raise SariConnectorError("card id contains unsupported characters")
        return self._fetch(
            f"{SARI_ORIGIN}{SARI_PREFIX}card/get_dettaglio/{urllib.parse.quote(card_id)}",
            expected_content_type="application/json",
        )


def _source_manifest(output_dir: Path, *, run_id: str) -> dict[str, Any]:
    path = output_dir / "official_sources.json"
    if path.exists():
        manifest = load_json_object(path)
        if manifest.get("plugin") != PLUGIN_NAME or manifest.get("run_id") != run_id:
            raise SariConnectorError(
                "existing official_sources.json belongs to another run"
            )
        sources = manifest.get("sources")
        if not isinstance(sources, list):
            raise SariConnectorError(
                "existing official_sources.json has invalid sources"
            )
        return manifest
    return {
        "schema_version": "1.0",
        "plugin": PLUGIN_NAME,
        "run_id": run_id,
        "created_at": iso_now(),
        "sources": [],
        "source_count": 0,
    }


def _upsert_source(manifest: dict[str, Any], source: dict[str, Any]) -> None:
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise SariConnectorError("official source manifest has invalid sources")
    sources[:] = [
        item for item in sources if item.get("source_id") != source["source_id"]
    ]
    sources.append(source)
    sources.sort(key=lambda item: str(item.get("source_id") or ""))
    manifest["source_count"] = len(sources)
    manifest["updated_at"] = iso_now()


def _record_network_receipt(
    output_dir: Path,
    *,
    run_id: str,
    operation: str,
    tenant: str,
    network_approval_id: str,
    written_use_authorization_id: str,
    query_sha256: str | None,
) -> None:
    write_private_json(
        output_dir / "sari_network_receipt.json",
        {
            "schema_version": "1.0",
            "plugin": PLUGIN_NAME,
            "run_id": run_id,
            "operation": operation,
            "tenant": tenant,
            "recorded_at": iso_now(),
            "network_approval_id": network_approval_id,
            "written_use_authorization_id": written_use_authorization_id,
            "query_sha256": query_sha256,
            "credentials_used": False,
            "cookies_persisted_or_exported": False,
            "login_or_submission_performed": False,
            "request_limit": MAX_REQUESTS_PER_OPERATION,
        },
    )


def _record_run_connector_posture(
    output_dir: Path,
    *,
    run_id: str,
    operation: str,
    tenant: str,
    network_approval_id: str,
    written_use_authorization_id: str,
    phase: str,
    outputs: list[str],
) -> None:
    run_path = output_dir / "run_intake.json"
    if not run_path.exists():
        return
    run = load_json_object(run_path)
    if run.get("plugin") != PLUGIN_NAME or run.get("run_id") != run_id:
        raise SariConnectorError("run_intake.json belongs to another run")
    data_posture = run.get("data_posture")
    if not isinstance(data_posture, dict):
        data_posture = {}
    data_posture.setdefault("local_files_read", [])
    data_posture.setdefault("model_excerpts_sent", [])
    data_posture.setdefault("upload_paths_used", [])
    data_posture.setdefault("hosted_notebook_execution_used", False)
    data_posture.setdefault("remote_sql_execution_used", False)
    connectors = data_posture.get("external_connectors_used")
    if not isinstance(connectors, list):
        connectors = []
    connector_entry = {
        "connector": "authorized_sari_json_read_only",
        "origin": SARI_ORIGIN,
        "tenant": tenant,
        "operation": operation,
        "credentials_used": False,
    }
    connectors = [
        entry
        for entry in connectors
        if not isinstance(entry, dict)
        or (
            entry.get("connector"),
            entry.get("tenant"),
            entry.get("operation"),
        )
        != (
            connector_entry["connector"],
            tenant,
            operation,
        )
    ]
    connectors.append(connector_entry)
    data_posture["external_connectors_used"] = connectors
    data_posture["external_execution_approval"] = {
        "approved": True,
        "approved_at": iso_now(),
        "approved_by": network_approval_id,
        "reason": written_use_authorization_id,
        "scope": (
            f"Exactly {MAX_REQUESTS_PER_OPERATION} bounded read-only SARI requests "
            f"for {operation} on tenant {tenant}; redirects prohibited."
        ),
    }
    run["data_posture"] = data_posture
    trace = run.get("execution_trace")
    if not isinstance(trace, list):
        trace = []
    trace.append(
        {
            "step_id": f"sari_connector_{phase}_{len(trace) + 1}",
            "kind": "external_official_source_read",
            "command": [
                "python",
                "scripts/sari_connector.py",
                operation,
                "--tenant",
                tenant,
            ],
            "execution_location": "external_connector",
            "status": "passed" if phase == "completed" else "authorized",
            "inputs": [f"{SARI_ORIGIN}{SARI_PREFIX}{tenant}"],
            "outputs": outputs,
        }
    )
    run["execution_trace"] = trace
    write_private_json(run_path, run)


def run_search(
    *,
    output_dir: Path,
    run_id: str,
    tenant: str,
    expected_chamber: str,
    query: str,
    network_approval_id: str,
    written_use_authorization_id: str,
    limit: int = MAX_RESULTS,
    client: SariClient | None = None,
) -> dict[str, Any]:
    """Run one authorized metadata-only SARI search."""

    run_id = safe_identifier(run_id, field="run_id")
    clean_query = assert_generic_public_query(query)
    if not 1 <= limit <= MAX_RESULTS:
        raise SariConnectorError(f"limit must be between 1 and {MAX_RESULTS}")
    network_approval_id = _authorization(
        network_approval_id, field="network_approval_id"
    )
    written_use_authorization_id = _authorization(
        written_use_authorization_id, field="written_use_authorization_id"
    )
    safe_output = ensure_safe_output_dir(output_dir, plugin_root=PLUGIN_ROOT)
    _record_network_receipt(
        safe_output,
        run_id=run_id,
        operation="search_metadata",
        tenant=tenant,
        network_approval_id=network_approval_id,
        written_use_authorization_id=written_use_authorization_id,
        query_sha256=sha256_bytes(clean_query.encode("utf-8")),
    )
    _record_run_connector_posture(
        safe_output,
        run_id=run_id,
        operation="search",
        tenant=tenant,
        network_approval_id=network_approval_id,
        written_use_authorization_id=written_use_authorization_id,
        phase="authorized",
        outputs=["sari_network_receipt.json"],
    )
    active_client = client or SariClient()
    tenant_page = active_client.initialize_tenant(
        tenant, expected_chamber=expected_chamber
    )
    fetched = active_client.search(clean_query, limit=limit)
    payload = _json_payload(fetched.raw, context="SARI search")
    normalized = normalize_search_result(payload, limit=limit)
    retrieved_at = iso_now()
    share_base = f"{SARI_ORIGIN}{SARI_PREFIX}{active_client.tenant}"
    for candidate in normalized["candidates"]:
        candidate["browser_url"] = (
            f"{share_base}?{urllib.parse.urlencode({'apriContenuto': candidate['card_id']})}"
        )
    result = {
        "schema_version": "1.0",
        "plugin": PLUGIN_NAME,
        "run_id": run_id,
        "retrieved_at": retrieved_at,
        "tenant": active_client.tenant,
        "chamber_title": active_client.chamber_title,
        "query": clean_query,
        "query_sha256": sha256_bytes(clean_query.encode("utf-8")),
        "written_use_authorization_id": written_use_authorization_id,
        **normalized,
    }
    result_path = write_private_json(
        safe_output / "sari_search_candidates.json", result
    )
    manifest = _source_manifest(safe_output, run_id=run_id)
    source_id = f"SARI-{active_client.tenant.upper()}-SEARCH"
    _upsert_source(
        manifest,
        {
            "source_id": source_id,
            "source_type": "official_sari_search_metadata",
            "publisher": "InfoCamere / Camera di commercio selezionata",
            "tenant": active_client.tenant,
            "chamber_title": active_client.chamber_title,
            "official_url": share_base,
            "retrieval_endpoint": f"{SARI_ORIGIN}{SARI_PREFIX}faq/get/",
            "retrieved_at": retrieved_at,
            "response_sha256": sha256_bytes(fetched.raw),
            "tenant_page_sha256": sha256_bytes(tenant_page.raw),
            "artifact_path": result_path.name,
            "artifact_sha256": sha256_bytes(result_path.read_bytes()),
            "use_authorization_id": written_use_authorization_id,
            "applicability_status": "candidate_search_only",
        },
    )
    write_private_json(safe_output / "official_sources.json", manifest)
    _record_run_connector_posture(
        safe_output,
        run_id=run_id,
        operation="search",
        tenant=active_client.tenant,
        network_approval_id=network_approval_id,
        written_use_authorization_id=written_use_authorization_id,
        phase="completed",
        outputs=[
            "sari_search_candidates.json",
            "official_sources.json",
            "sari_network_receipt.json",
        ],
    )
    return result


def run_detail(
    *,
    output_dir: Path,
    run_id: str,
    tenant: str,
    expected_chamber: str,
    card_id: str,
    network_approval_id: str,
    written_use_authorization_id: str,
    client: SariClient | None = None,
) -> dict[str, Any]:
    """Fetch exactly one authorized, human-selected SARI card."""

    run_id = safe_identifier(run_id, field="run_id")
    card_id = str(card_id or "").strip()
    if not CARD_ID_RE.fullmatch(card_id):
        raise SariConnectorError("card id contains unsupported characters")
    network_approval_id = _authorization(
        network_approval_id, field="network_approval_id"
    )
    written_use_authorization_id = _authorization(
        written_use_authorization_id, field="written_use_authorization_id"
    )
    safe_output = ensure_safe_output_dir(output_dir, plugin_root=PLUGIN_ROOT)
    _record_network_receipt(
        safe_output,
        run_id=run_id,
        operation="selected_card_detail",
        tenant=tenant,
        network_approval_id=network_approval_id,
        written_use_authorization_id=written_use_authorization_id,
        query_sha256=None,
    )
    _record_run_connector_posture(
        safe_output,
        run_id=run_id,
        operation="detail",
        tenant=tenant,
        network_approval_id=network_approval_id,
        written_use_authorization_id=written_use_authorization_id,
        phase="authorized",
        outputs=["sari_network_receipt.json"],
    )
    active_client = client or SariClient()
    tenant_page = active_client.initialize_tenant(
        tenant, expected_chamber=expected_chamber
    )
    fetched = active_client.fetch_card(card_id)
    normalized = normalize_card(
        _json_payload(fetched.raw, context="SARI selected card"), card_id=card_id
    )
    retrieved_at = iso_now()
    browser_url = (
        f"{SARI_ORIGIN}{SARI_PREFIX}{active_client.tenant}?"
        + urllib.parse.urlencode({"apriContenuto": card_id})
    )
    result = {
        "schema_version": "1.0",
        "plugin": PLUGIN_NAME,
        "run_id": run_id,
        "retrieved_at": retrieved_at,
        "tenant": active_client.tenant,
        "chamber_title": active_client.chamber_title,
        "browser_url": browser_url,
        "written_use_authorization_id": written_use_authorization_id,
        **normalized,
    }
    result_path = write_private_json(safe_output / f"sari_card_{card_id}.json", result)
    manifest = _source_manifest(safe_output, run_id=run_id)
    source_id = f"SARI-{active_client.tenant.upper()}-CARD-{card_id}"
    _upsert_source(
        manifest,
        {
            "source_id": source_id,
            "source_type": "official_sari_selected_card",
            "publisher": "InfoCamere / Camera di commercio selezionata",
            "tenant": active_client.tenant,
            "chamber_title": active_client.chamber_title,
            "card_id": card_id,
            "title": normalized["title"],
            "official_url": browser_url,
            "retrieval_endpoint": (
                f"{SARI_ORIGIN}{SARI_PREFIX}card/get_dettaglio/{card_id}"
            ),
            "retrieved_at": retrieved_at,
            "response_sha256": sha256_bytes(fetched.raw),
            "tenant_page_sha256": sha256_bytes(tenant_page.raw),
            "artifact_path": result_path.name,
            "artifact_sha256": sha256_bytes(result_path.read_bytes()),
            "use_authorization_id": written_use_authorization_id,
            "applicability_status": "requires_professional_confirmation",
        },
    )
    write_private_json(safe_output / "official_sources.json", manifest)
    _record_run_connector_posture(
        safe_output,
        run_id=run_id,
        operation="detail",
        tenant=active_client.tenant,
        network_approval_id=network_approval_id,
        written_use_authorization_id=written_use_authorization_id,
        phase="completed",
        outputs=[
            result_path.name,
            "official_sources.json",
            "sari_network_receipt.json",
        ],
    )
    return result


def main(argv: list[str] | None = None) -> int:
    """Run the explicitly authorized direct connector."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("search", "detail"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--expected-chamber", required=True)
    parser.add_argument("--network-approval-id", required=True)
    parser.add_argument("--written-use-authorization-id", required=True)
    parser.add_argument("--query")
    parser.add_argument("--card-id")
    parser.add_argument("--limit", type=int, default=MAX_RESULTS)
    args = parser.parse_args(argv)
    common = {
        "output_dir": args.output_dir,
        "run_id": args.run_id,
        "tenant": args.tenant,
        "expected_chamber": args.expected_chamber,
        "network_approval_id": args.network_approval_id,
        "written_use_authorization_id": args.written_use_authorization_id,
    }
    try:
        if args.operation == "search":
            if not args.query:
                parser.error("search requires --query")
            result = run_search(query=args.query, limit=args.limit, **common)
            LOGGER.info(
                "Stored %s SARI candidates for human selection in %s",
                result["returned_candidate_count"],
                args.output_dir,
            )
        else:
            if not args.card_id:
                parser.error("detail requires --card-id")
            result = run_detail(card_id=args.card_id, **common)
            LOGGER.info("Stored selected SARI card %s", result["card_id"])
    except (SariConnectorError, ValueError) as exc:
        LOGGER.error("SARI_CONNECTOR_BLOCKED: %s", exc)
        return 2
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
