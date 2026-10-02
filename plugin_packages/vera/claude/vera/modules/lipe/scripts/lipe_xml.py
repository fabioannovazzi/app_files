"""Offline IVP18 serialization for synthetic conformance tests only.

Production export stays closed until professional UAT, authenticated review and
real importer acceptance are implemented. A JSON reviewer name is not identity.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from lipe_core import ROOT, ContractError, calculate, read_json
from lxml import etree

__all__ = ["build_test_xml"]

NS = "urn:www.agenziaentrate.gov.it:specificheTecniche:sco:ivp"
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


class _OfflineResolver(etree.Resolver):  # type: ignore[misc]
    """Deny every schema dependency outside the exact verified local bundle."""

    def __init__(self, allowed: set[Path]) -> None:
        super().__init__()
        self.allowed = allowed

    def resolve(self, url: str, pubid: str, context: Any) -> Any:
        path = Path(url.removeprefix("file://")).resolve()
        if path not in self.allowed:
            raise ContractError("Unexpected XML schema dependency")
        return self.resolve_filename(str(path), context)


def _schema() -> Any:
    root = ROOT / "references/xsd"
    manifest = read_json(root / "manifest.json")
    allowed = set()
    for item in manifest["files"]:
        path = (root / item["path"]).resolve()
        if (
            not path.is_relative_to(root.resolve())
            or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]
        ):
            raise ContractError("Official schema bundle changed")
        allowed.add(path)
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    parser.resolvers.add(_OfflineResolver(allowed))
    return etree.XMLSchema(
        etree.parse(str(root / "sco/ivp/fornituraIvp_2018_v1.xsd"), parser)
    )


def build_test_xml(case: dict, source_root: Path) -> bytes:
    """Recalculate exact sources, use fictional identity and require valid XSD."""
    if case["data_origin"] != "SYNTHETIC":
        raise ContractError(
            "Real XML export unavailable: professional and importer acceptance pending"
        )
    result = calculate(case, source_root)
    if result["status"] != "DRAFT_FOR_REVIEW":
        raise ContractError("Blocked case cannot produce even a test XML")
    root = etree.Element(f"{{{NS}}}Fornitura", nsmap={"iv": NS})

    def tag(parent: Any, name: str, value: Any = None) -> Any:
        child = etree.SubElement(parent, f"{{{NS}}}{name}")
        if value is not None:
            child.text = str(value)
        return child

    tag(tag(root, "Intestazione"), "CodiceFornitura", "IVP18")
    communication = tag(root, "Comunicazione")
    communication.set("identificativo", "00001")
    front = tag(communication, "Frontespizio")
    for name, value in (
        ("CodiceFiscale", "RSSMRA80A01H501U"),
        ("AnnoImposta", case["tax_year"]),
        ("PartitaIVA", "12345678901"),
        ("FirmaDichiarazione", "1"),
    ):
        tag(front, name, value)
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
    schema = _schema()
    if not schema.validate(root):
        raise ContractError("XSD validation failed: " + str(schema.error_log))
    return bytes(
        etree.tostring(root, encoding="UTF-8", xml_declaration=True, pretty_print=True)
    )
