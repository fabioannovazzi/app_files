"""Serialize reviewed FatturaPA fields using the official schema's order.

Fixed schema order, escaping and XSD validation are mechanically verifiable;
this module makes no decisions about the meaning or tax treatment of a bill.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from lxml import etree

__all__ = ["InvoiceSchema", "flatten_fields"]

ROOT = Path(__file__).resolve().parents[1] / "references" / "xsd"
XS = "{http://www.w3.org/2001/XMLSchema}"
NAMESPACE = "http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2"
SIGNATURE_URL = (
    "http://www.w3.org/TR/2002/REC-xmldsig-core-20020212/xmldsig-core-schema.xsd"
)


# lxml's native resolver base is untyped without optional third-party stubs.
class _OfflineResolver(etree.Resolver):  # type: ignore[misc]
    """Resolve the sole official import to verified local bytes; deny others."""

    def resolve(self, url: str, pubid: str, context: Any) -> Any:
        if url == SIGNATURE_URL:
            return self.resolve_string(
                (ROOT / "xmldsig-core-schema.xsd").read_bytes(), context
            )
        raise ValueError("Unexpected schema dependency; network access is disabled")


def flatten_fields(value: Any, pointer: str = "") -> dict[str, str | None]:
    """Project exact JSON pointers for review; keep unknown values as null."""
    if isinstance(value, dict):
        result: dict[str, str | None] = {}
        for key, child in value.items():
            if not isinstance(key, str) or not key or "/" in key or "~" in key:
                raise ValueError("Invoice keys must be XML element names")
            result.update(flatten_fields(child, f"{pointer}/{key}"))
        return result
    if isinstance(value, list):
        result = {}
        for index, child in enumerate(value):
            result.update(flatten_fields(child, f"{pointer}/{index}"))
        return result
    if value is not None and not isinstance(value, str):
        raise ValueError(f"Use exact strings, not JSON numbers, at {pointer}")
    return {pointer: value}


class InvoiceSchema:
    """Use the bundled FPR12 schema without modifying it or fetching imports."""

    def __init__(self) -> None:
        manifest = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
        expected = {"Schema_VFPR12_v1.2.3.xsd", "xmldsig-core-schema.xsd"}
        if {row["path"] for row in manifest["files"]} != expected:
            raise ValueError("Unexpected schema bundle membership")
        for row in manifest["files"]:
            path = ROOT / row["path"]
            if (
                path.is_symlink()
                or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]
            ):
                raise ValueError("Official schema bytes differ from the bundle receipt")
        parser = etree.XMLParser(
            resolve_entities=False, load_dtd=False, no_network=True
        )
        parser.resolvers.add(_OfflineResolver())
        self.tree = etree.fromstring(
            (ROOT / "Schema_VFPR12_v1.2.3.xsd").read_bytes(), parser
        )
        self.validator = etree.XMLSchema(self.tree)
        self.types = {
            node.attrib["name"]: node for node in self.tree.findall(f"{XS}complexType")
        }
        self.receipt = manifest

    def _append(self, node: Any, type_name: str, value: Any) -> None:
        if type_name not in self.types:
            if not isinstance(value, str):
                raise ValueError(f"Missing or non-text value for {node.tag}")
            node.text = value
            return
        if not isinstance(value, dict):
            raise ValueError(f"Expected a field object for {node.tag}")
        declarations = self.types[type_name].findall(f".//{XS}element")
        permitted = {
            item.attrib["name"] for item in declarations if "name" in item.attrib
        }
        if set(value) - permitted:
            raise ValueError(
                f"Unknown or unsupported fields in {node.tag}: {sorted(set(value) - permitted)}"
            )
        for declaration in declarations:
            name = declaration.attrib.get("name")
            if name is None or name not in value:
                continue
            entries = value[name] if isinstance(value[name], list) else [value[name]]
            if not entries:
                raise ValueError(
                    f"Empty repeated element {name}; omit absent optional fields"
                )
            for entry in entries:
                child = etree.SubElement(node, name)
                self._append(child, declaration.attrib["type"], entry)

    def serialize(self, invoice: dict[str, Any]) -> bytes:
        """Serialize all supplied fields; XSD validation is a separate result."""
        flatten_fields(invoice)
        root = etree.Element(
            f"{{{NAMESPACE}}}FatturaElettronica",
            nsmap={"p": NAMESPACE},
            versione="FPR12",
        )
        self._append(root, "FatturaElettronicaType", invoice)
        return bytes(
            etree.tostring(
                root, encoding="UTF-8", xml_declaration=True, pretty_print=True
            )
        )

    def errors(self, payload: bytes) -> list[str]:
        """Validate serialized bytes; do not accept declarations or signatures."""
        parser = etree.XMLParser(
            resolve_entities=False, load_dtd=False, no_network=True
        )
        root = etree.fromstring(payload, parser)
        if root.getroottree().docinfo.doctype:
            raise ValueError("Invoice XML must not contain a DTD")
        if self.validator.validate(root):
            return []
        return [str(error.message) for error in self.validator.error_log]
