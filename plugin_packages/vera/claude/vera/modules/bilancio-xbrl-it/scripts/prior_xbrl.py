#!/usr/bin/env python3
"""Securely extract prior-period facts from a local XBRL instance.

This parser is deterministic because XML structure, context references, and
lexical fact values are mechanically verifiable. It does not decide the
accounting meaning or current-year applicability of any extracted fact.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from lxml import etree

__all__ = ["parse_prior_xbrl"]

XBRLI_NS = "http://www.xbrl.org/2003/instance"
LINK_NS = "http://www.xbrl.org/2003/linkbase"
XLINK_NS = "http://www.w3.org/1999/xlink"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
XML_NS = "http://www.w3.org/XML/1998/namespace"
XBRLDI_NS = "http://xbrl.org/2006/xbrldi"
MAX_INSTANCE_BYTES = 64 * 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _period(context: etree._Element) -> dict[str, str | None]:
    period = context.find(f"{{{XBRLI_NS}}}period")
    if period is None:
        raise ValueError("Every prior-XBRL context requires a period")
    instant = period.findtext(f"{{{XBRLI_NS}}}instant")
    start = period.findtext(f"{{{XBRLI_NS}}}startDate")
    end = period.findtext(f"{{{XBRLI_NS}}}endDate")
    forever = period.find(f"{{{XBRLI_NS}}}forever") is not None
    if instant:
        return {"kind": "INSTANT", "start": None, "end": instant.strip()}
    if start and end:
        return {"kind": "DURATION", "start": start.strip(), "end": end.strip()}
    if forever:
        return {"kind": "FOREVER", "start": None, "end": None}
    raise ValueError("Prior-XBRL context period is incomplete")


def _resolved_qname(value: str, element: etree._Element) -> dict[str, str]:
    """Resolve one lexical QName without consulting any remote taxonomy."""

    lexical = value.strip()
    if not lexical:
        raise ValueError("Prior-XBRL dimension QName is empty")
    if ":" in lexical:
        prefix, local_name = lexical.split(":", 1)
        namespace = element.nsmap.get(prefix)
    else:
        prefix = ""
        local_name = lexical
        namespace = element.nsmap.get(None)
    if not local_name or not namespace:
        raise ValueError(f"Prior-XBRL dimension QName cannot be resolved: {lexical}")
    return {
        "qname": lexical,
        "namespace": str(namespace),
        "local_name": local_name,
    }


def _context_dimensions(context: etree._Element) -> list[dict[str, Any]]:
    """Preserve explicit and typed context dimensions in document order."""

    dimensions: list[dict[str, Any]] = []
    seen_axes: set[tuple[str, str]] = set()
    members = context.xpath(
        ".//xbrldi:explicitMember | .//xbrldi:typedMember",
        namespaces={"xbrldi": XBRLDI_NS},
    )
    for member in members:
        axis = _resolved_qname(str(member.get("dimension") or ""), member)
        axis_key = (axis["namespace"], axis["local_name"])
        if axis_key in seen_axes:
            raise ValueError("Prior-XBRL context repeats a dimension axis")
        seen_axes.add(axis_key)
        parent = member.getparent()
        container = (
            etree.QName(parent).localname.upper() if parent is not None else "UNKNOWN"
        )
        if member.tag == f"{{{XBRLDI_NS}}}explicitMember":
            resolved_member = _resolved_qname(str(member.text or ""), member)
            dimensions.append(
                {
                    "kind": "EXPLICIT",
                    "container": container,
                    "axis": axis,
                    "member": resolved_member,
                    "source_line": member.sourceline,
                }
            )
            continue
        children = list(member)
        if len(children) != 1:
            raise ValueError(
                "Prior-XBRL typed dimensions require exactly one typed value element"
            )
        typed_value = children[0]
        typed_qname = etree.QName(typed_value)
        canonical_xml = etree.tostring(
            typed_value, method="c14n", with_comments=False
        ).decode("utf-8")
        dimensions.append(
            {
                "kind": "TYPED",
                "container": container,
                "axis": axis,
                "typed_value": {
                    "namespace": str(typed_qname.namespace or ""),
                    "local_name": typed_qname.localname,
                    "canonical_xml": canonical_xml,
                    "sha256": hashlib.sha256(canonical_xml.encode("utf-8")).hexdigest(),
                },
                "source_line": member.sourceline,
            }
        )
    return dimensions


def parse_prior_xbrl(path: Path) -> dict[str, Any]:
    """Return source-anchored contexts and facts without loading remote resources."""

    if path.is_symlink() or not path.is_file():
        raise ValueError("Prior XBRL must be a regular local file")
    source = path.resolve()
    if source.stat().st_size > MAX_INSTANCE_BYTES:
        raise ValueError("Prior XBRL exceeds the size limit")
    xml = source.read_bytes()
    if b"<!DOCTYPE" in xml.upper():
        raise ValueError("Prior XBRL must not contain a document type declaration")
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        huge_tree=False,
        remove_comments=False,
    )
    try:
        root = etree.fromstring(xml, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise ValueError("Prior XBRL is not well-formed XML") from exc
    if root.tag != f"{{{XBRLI_NS}}}xbrl":
        raise ValueError("Prior document root is not xbrli:xbrl")
    schema_refs = root.findall(f"{{{LINK_NS}}}schemaRef")
    if len(schema_refs) != 1:
        raise ValueError("Prior XBRL requires exactly one schemaRef")
    schema_ref = schema_refs[0].get(f"{{{XLINK_NS}}}href")
    if not schema_ref:
        raise ValueError("Prior-XBRL schemaRef href is missing")

    contexts: dict[str, dict[str, Any]] = {}
    entity_identifiers: set[tuple[str, str]] = set()
    for context in root.findall(f"{{{XBRLI_NS}}}context"):
        context_id = str(context.get("id") or "")
        if not context_id or context_id in contexts:
            raise ValueError("Prior-XBRL context IDs must be present and unique")
        identifier = context.find(f"{{{XBRLI_NS}}}entity/{{{XBRLI_NS}}}identifier")
        if identifier is None or not (identifier.text or "").strip():
            raise ValueError("Prior-XBRL context entity identifier is missing")
        scheme = str(identifier.get("scheme") or "")
        value = str(identifier.text).strip()
        entity_identifiers.add((scheme, value))
        dimensions = _context_dimensions(context)
        signature_dimensions = [
            {key: value for key, value in item.items() if key != "source_line"}
            for item in dimensions
        ]
        dimension_signature = hashlib.sha256(
            json.dumps(
                signature_dimensions,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        contexts[context_id] = {
            "context_id": context_id,
            "entity_scheme": scheme,
            "entity_identifier": value,
            "period": _period(context),
            "has_dimensions": bool(dimensions),
            "dimensions": dimensions,
            "dimension_signature": dimension_signature,
            "source_line": context.sourceline,
        }
    if not contexts:
        raise ValueError("Prior XBRL contains no contexts")
    if len(entity_identifiers) != 1:
        raise ValueError("Prior XBRL contains multiple entity identifiers")

    ignored_namespaces = {XBRLI_NS, LINK_NS}
    facts: list[dict[str, Any]] = []
    for element in root:
        qname = etree.QName(element)
        context_ref = element.get("contextRef")
        if qname.namespace in ignored_namespaces or context_ref is None:
            continue
        if context_ref not in contexts:
            raise ValueError(
                f"Prior-XBRL fact references unknown context {context_ref}"
            )
        nil = element.get(f"{{{XSI_NS}}}nil") in {"true", "1"}
        prefix = element.prefix
        lexical_qname = f"{prefix}:{qname.localname}" if prefix else qname.localname
        facts.append(
            {
                "fact_id": f"prior_fact_{len(facts) + 1:06d}",
                "qname": lexical_qname,
                "namespace": qname.namespace,
                "local_name": qname.localname,
                "context_ref": context_ref,
                "period": contexts[context_ref]["period"],
                "dimensions": contexts[context_ref]["dimensions"],
                "dimension_signature": contexts[context_ref]["dimension_signature"],
                "unit_ref": element.get("unitRef"),
                "decimals": element.get("decimals"),
                "precision": element.get("precision"),
                "language": element.get(f"{{{XML_NS}}}lang"),
                "nil": nil,
                "value": None if nil else (element.text or "").strip(),
                "source_anchor": {
                    "document_path": source.name,
                    "line": element.sourceline,
                    "xpath": element.getroottree().getpath(element),
                    "raw_value": None if nil else (element.text or ""),
                    "confidence": "HIGH",
                },
            }
        )
    entity_scheme, entity_identifier = next(iter(entity_identifiers))
    facts_by_context: dict[str, list[dict[str, str]]] = {}
    for fact in facts:
        facts_by_context.setdefault(str(fact["context_ref"]), []).append(
            {"fact_id": str(fact["fact_id"]), "qname": str(fact["qname"])}
        )
    context_fact_groups = [
        {
            "context_id": context_id,
            "period": contexts[context_id]["period"],
            "dimensions": contexts[context_id]["dimensions"],
            "dimension_signature": contexts[context_id]["dimension_signature"],
            "facts": sorted(items, key=lambda item: item["fact_id"]),
        }
        for context_id, items in sorted(facts_by_context.items())
    ]
    return {
        "schema_version": 2,
        "file_name": source.name,
        "sha256": _sha256(source),
        "schema_ref": schema_ref,
        "entity_scheme": entity_scheme,
        "entity_identifier": entity_identifier,
        "contexts": list(contexts.values()),
        "facts": facts,
        "context_fact_groups": context_fact_groups,
    }
