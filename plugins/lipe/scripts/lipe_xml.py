"""Offline official schemas, bounded XML reading and synthetic IVP18 serialization.

The synthetic command rejects real data. Approved export has a separate
signature-verifying entrypoint; professional/importer qualification is not
established by schema validation. A JSON reviewer name is not identity.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import url2pathname

from lipe_core import ROOT, ContractError, calculate, read_json
from lxml import etree

__all__ = ["build_test_xml", "load_official_schema", "parse_xml"]

NS = "urn:www.agenziaentrate.gov.it:specificheTecniche:sco:ivp"
MAX_XML_BYTES = 8 * 1024 * 1024
SIGNATURE_SCHEMA_URI = (
    "http://www.w3.org/TR/2002/REC-xmldsig-core-20020212/xmldsig-core-schema.xsd"
)
AMOUNTS = (
    ("vp2", "TotaleOperazioniAttive"),
    ("vp3", "TotaleOperazioniPassive"),
    ("vp4", "IvaEsigibile"),
    ("vp5", "IvaDetratta"),
    ("vp6_debit", "IvaDovuta"),
    ("vp6_credit", "IvaCredito"),
    ("vp7", "DebitoPrecedente"),
    ("vp8", "CreditoPeriodoPrecedente"),
    ("vp9", "CreditoAnnoPrecedente"),
    ("vp10", "VersamentiAutoUE"),
    ("vp11", "CreditiImposta"),
    ("vp12", "InteressiDovuti"),
    ("vp13", "Acconto"),
    ("vp14_debit", "ImportoDaVersare"),
    ("vp14_credit", "ImportoACredito"),
)
FRONT_FIELDS = (
    "CodiceFiscale",
    "AnnoImposta",
    "PartitaIVA",
    "CFDichiarante",
    "CodiceCaricaDichiarante",
    "CodiceFiscaleSocieta",
    "FirmaDichiarazione",
    "CFIntermediario",
    "ImpegnoPresentazione",
    "DataImpegno",
    "FirmaIntermediario",
)


class _OfflineResolver(etree.Resolver):  # type: ignore[misc]
    """Deny every schema dependency outside the exact verified local bundle."""

    def __init__(self, allowed: set[Path], aliases: dict[str, Path]) -> None:
        super().__init__()
        self.allowed = allowed
        self.aliases = aliases

    def resolve(self, url: str, pubid: str, context: Any) -> Any:
        if url in self.aliases:
            path = self.aliases[url]
        elif url.startswith("file:"):
            parsed = urlsplit(url)
            if parsed.netloc or parsed.query or parsed.fragment:
                raise ContractError("Unexpected XML schema dependency")
            path = Path(url2pathname(parsed.path)).resolve()
        else:
            path = Path(url).resolve()
        if path not in self.allowed:
            raise ContractError("Unexpected XML schema dependency")
        return self.resolve_string(path.read_bytes(), context, base_url=path.as_uri())


def load_official_schema(name: str = "IVP18") -> Any:
    """Resolve only hash-verified official schemas, including the receipt import."""
    schemas = {
        "IVP18": "sco/ivp/fornituraIvp_2018_v1.xsd",
        "RECEIPT": "receipts/DatiFatturaMessaggi_v2.0.xsd",
    }
    if name not in schemas:
        raise ContractError("Unknown official LIPE schema")
    root = ROOT / "references/xsd"
    manifest = read_json(root / "manifest.json")
    allowed = set()
    for item in manifest["files"]:
        original = root / item["path"]
        path = original.resolve()
        if (
            original.is_symlink()
            or not path.is_file()
            or not path.is_relative_to(root.resolve())
            or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]
        ):
            raise ContractError("Official schema bundle changed")
        allowed.add(path)
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    parser.resolvers.add(
        _OfflineResolver(
            allowed,
            {
                SIGNATURE_SCHEMA_URI: (
                    root / "sco/ivp/xmldsig-core-schema.xsd"
                ).resolve()
            },
        )
    )
    return etree.XMLSchema(etree.parse((root / schemas[name]).as_uri(), parser))


def parse_xml(raw: bytes) -> Any:
    """Bound untrusted XML and prohibit DTD/entities or external resource loading."""
    if not raw or len(raw) > MAX_XML_BYTES:
        raise ContractError("XML is empty or exceeds the 8 MiB inspection limit")
    parser = etree.XMLParser(
        resolve_entities=False, load_dtd=False, no_network=True, huge_tree=False
    )
    try:
        root = etree.fromstring(raw, parser)
    except etree.XMLSyntaxError as exc:
        raise ContractError("Malformed XML: " + str(exc)[:1000]) from exc
    if root.getroottree().docinfo.doctype:
        raise ContractError("XML document types are not permitted")
    stack = [(root, 1)]
    count = 0
    while stack:
        element, depth = stack.pop()
        count += 1
        if count > 10000 or depth > 64:
            raise ContractError("XML exceeds the element or depth inspection limit")
        if isinstance(element, etree._Entity):
            raise ContractError("XML entity references are not permitted")
        stack.extend((child, depth + 1) for child in element)
    return root


def build_test_xml(
    case: dict, source_root: Path, catalog_path: Path | None = None
) -> bytes:
    """Recalculate exact sources, use fictional identity and require valid XSD."""
    if case["data_origin"] != "SYNTHETIC":
        raise ContractError(
            "xml-test requires synthetic data; use the separate signed-approval export workflow"
        )
    result = calculate(case, source_root, catalog_path)
    if result["status"] != "DRAFT_FOR_REVIEW":
        raise ContractError("Blocked case cannot produce even a test XML")
    return _serialize(
        case,
        result,
        {
            "CodiceFiscale": "RSSMRA80A01H501U",
            "AnnoImposta": str(case["tax_year"]),
            "PartitaIVA": "12345678901",
            "FirmaDichiarazione": "1",
        },
    )


def _serialize(case: dict, result: dict, fields: dict) -> bytes:
    """Serialize already checked values; the export entrypoint authenticates approval."""
    if result["status"] != "DRAFT_FOR_REVIEW" or set(fields) - set(FRONT_FIELDS):
        raise ContractError(
            "Serialization requires supported checked fields and result"
        )
    root = etree.Element(f"{{{NS}}}Fornitura", nsmap={"iv": NS})

    def tag(parent: Any, name: str, value: Any = None) -> Any:
        child = etree.SubElement(parent, f"{{{NS}}}{name}")
        if value is not None:
            child.text = str(value)
        return child

    header = tag(root, "Intestazione")
    tag(header, "CodiceFornitura", "IVP18")
    if "CFDichiarante" in fields:
        tag(header, "CodiceFiscaleDichiarante", fields["CFDichiarante"])
        tag(header, "CodiceCarica", fields["CodiceCaricaDichiarante"])
    communication = tag(root, "Comunicazione")
    communication.set("identificativo", "00001")
    front = tag(communication, "Frontespizio")
    for name in FRONT_FIELDS:
        if name in fields:
            tag(front, name, fields[name])
    data = tag(communication, "DatiContabili")
    for index, module in enumerate(result["modules"], 1):
        node = tag(data, "Modulo")
        tag(node, "NumeroModulo", index)
        tag(
            node,
            "Mese" if case["regime"] == "MONTHLY" else "Trimestre",
            module["xml_period"],
        )
        for key, name in AMOUNTS:
            value = module["rows"][key]
            if value is not None and value != "0.00":
                if key == "vp13":
                    tag(node, "Metodo", module["vp13_method"])
                tag(node, name, value.replace(".", ","))
    schema = load_official_schema()
    if not schema.validate(root):
        raise ContractError("XSD validation failed: " + str(schema.error_log))
    return bytes(
        etree.tostring(root, encoding="UTF-8", xml_declaration=True, pretty_print=True)
    )
