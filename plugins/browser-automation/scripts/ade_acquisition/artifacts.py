"""Verify acquired originals and extract CMS content without claiming signature validity."""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from typing import Any
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from .contracts import AcquisitionError, Client, canonical_hash

__all__ = ["inspect_invoice", "extract_cms_xml", "MAX_BYTES"]
MAX_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class _Node:
    tag: int
    content: bytes
    children: tuple[_Node, ...]


def _read_node(data: bytes, offset: int, depth: int = 0) -> tuple[_Node, int]:
    if depth > 24 or offset + 2 > len(data):
        raise AcquisitionError("p7m-invalid-encoding")
    tag, length = data[offset], data[offset + 1]
    cursor = offset + 2
    indefinite = length == 128
    if length > 128:
        size = length & 127
        if size > 4 or cursor + size > len(data):
            raise AcquisitionError("p7m-invalid-length")
        length = int.from_bytes(data[cursor : cursor + size], "big")
        cursor += size
    if indefinite and not tag & 32:
        raise AcquisitionError("p7m-invalid-indefinite-value")
    end = len(data) if indefinite else cursor + length
    if end > len(data):
        raise AcquisitionError("p7m-truncated")
    start = cursor
    children: list[_Node] = []
    if tag & 32:
        while cursor < end:
            if indefinite and data[cursor : cursor + 2] == b"\x00\x00":
                return _Node(tag, data[start:cursor], tuple(children)), cursor + 2
            child, cursor = _read_node(data, cursor, depth + 1)
            children.append(child)
            if len(children) > 10000:
                raise AcquisitionError("p7m-node-limit")
        if indefinite or cursor != end:
            raise AcquisitionError("p7m-invalid-structure")
    return _Node(tag, data[start:end], tuple(children)), end


def _tag(node: _Node, expected: int) -> _Node:
    if node.tag != expected:
        raise AcquisitionError("p7m-invalid-structure")
    return node


def _octets(node: _Node) -> bytes:
    if node.tag == 4:
        return node.content
    if node.tag not in {0x24, 0xA0} or not node.children:
        raise AcquisitionError("p7m-content-missing")
    return b"".join(_octets(child) for child in node.children)


def extract_cms_xml(data: bytes) -> bytes:
    """Extract SignedData eContent, including constructed BER; never validate a signature."""
    if not 0 < len(data) <= MAX_BYTES:
        raise AcquisitionError("invoice-size-invalid")
    if data.startswith(b"-----BEGIN"):
        match = re.fullmatch(
            rb"\s*-----BEGIN (PKCS7|CMS)-----([A-Za-z0-9+/=\s]+)-----END \1-----\s*",
            data,
        )
        if not match:
            raise AcquisitionError("p7m-invalid-pem")
        try:
            data = base64.b64decode(re.sub(rb"\s", b"", match[2]), validate=True)
        except ValueError as exc:
            raise AcquisitionError("p7m-invalid-pem") from exc
    node, end = _read_node(data, 0)
    if end != len(data):
        raise AcquisitionError("p7m-trailing-bytes")
    try:
        root = _tag(node, 0x30).children
        if _tag(root[0], 6).content.hex() != "2a864886f70d010702":
            raise AcquisitionError("p7m-not-signed-data")
        signed = _tag(_tag(root[1], 0xA0).children[0], 0x30).children
        encapsulated = _tag(signed[2], 0x30).children
        if _tag(encapsulated[0], 6).content.hex() != "2a864886f70d010701":
            raise AcquisitionError("p7m-content-type-unsupported")
        return _octets(_tag(encapsulated[1], 0xA0))
    except IndexError as exc:
        raise AcquisitionError("p7m-content-missing") from exc


def inspect_invoice(
    data: bytes, filename: str, client: Client, category: str
) -> tuple[dict[str, Any], bytes | None]:
    """Require actual FatturaPA bytes and the requested party before accepting a download."""
    if not 0 < len(data) <= MAX_BYTES:
        raise AcquisitionError("invoice-size-invalid")
    signed = filename.lower().endswith(".p7m")
    xml = extract_cms_xml(data) if signed else data
    try:
        root = ElementTree.fromstring(xml)
    except (ParseError, DefusedXmlException) as exc:
        raise AcquisitionError("download-not-invoice-xml") from exc
    local = lambda element: element.tag.rsplit("}", 1)[-1]
    if local(root) not in {"FatturaElettronica", "FatturaElettronicaSemplificata"}:
        raise AcquisitionError("download-not-fatturapa")
    party_name = (
        "CedentePrestatore"
        if category in {"emesse", "estere"}
        else "CessionarioCommittente"
    )
    parties = [element for element in root.iter() if local(element) == party_name]
    ids = {
        str(element.text).strip().upper()
        for party in parties
        for element in party.iter()
        if local(element) in {"IdCodice", "CodiceFiscale"} and element.text
    }
    if not {client.tax_code, client.vat_number} & ids:
        raise AcquisitionError("invoice-client-mismatch")
    documents = []
    for element in root.iter():
        if local(element) == "DatiGeneraliDocumento":
            values = {local(child): (child.text or "").strip() for child in element}
            if not values.get("Numero") or not values.get("Data"):
                raise AcquisitionError("invoice-document-identity-missing")
            documents.append(
                {
                    key: values.get(key, "")
                    for key in ("TipoDocumento", "Data", "Numero")
                }
            )
    if not documents:
        raise AcquisitionError("invoice-document-identity-missing")
    identity = canonical_hash(
        {
            "client": client.vat_number,
            "category": category,
            "parties": [
                {
                    "role": local(p),
                    "ids": sorted(
                        {
                            (e.text or "").strip()
                            for e in p.iter()
                            if local(e) in {"IdCodice", "CodiceFiscale"}
                        }
                    ),
                }
                for p in root.iter()
                if local(p) in {"CedentePrestatore", "CessionarioCommittente"}
            ],
            "documents": documents,
        }
    )
    return {
        "format": "p7m" if signed else "xml",
        "invoice_identity": identity,
        "sha256": hashlib.sha256(data).hexdigest(),
        "byte_length": len(data),
        "xml_sha256": hashlib.sha256(xml).hexdigest(),
        "document_count": len(documents),
        "signature_validation": "not_performed",
    }, (xml if signed else None)
