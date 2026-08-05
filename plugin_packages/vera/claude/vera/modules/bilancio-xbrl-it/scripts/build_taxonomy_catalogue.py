#!/usr/bin/env python3
"""Build a checksum-pinned, form-aware catalogue from an official taxonomy ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence
from zipfile import BadZipFile, ZipFile

__all__ = ["build_catalogue", "main"]

LOGGER = logging.getLogger(__name__)
MAX_MEMBERS = 20_000
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
SUPPORTED_FORMS = {"ORDINARY", "ABBREVIATED", "MICRO"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_extract(package: Path, destination: Path) -> None:
    """Extract a bounded ZIP package without links or traversal."""

    try:
        archive = ZipFile(package)
    except BadZipFile as exc:
        raise ValueError("Taxonomy package is not a readable ZIP archive") from exc
    with archive:
        members = archive.infolist()
        if len(members) > MAX_MEMBERS:
            raise ValueError("Taxonomy package has too many members")
        if sum(member.file_size for member in members) > MAX_EXPANDED_BYTES:
            raise ValueError("Taxonomy package exceeds the expanded-size limit")
        for member in members:
            relative = Path(member.filename)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Taxonomy package contains an unsafe path")
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Taxonomy package contains a symbolic link")
            target = (destination / relative).resolve()
            if (
                destination.resolve() not in target.parents
                and target != destination.resolve()
            ):
                raise ValueError("Taxonomy member escapes the extraction directory")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)


def _qname_text(qname: object) -> str:
    prefix = getattr(qname, "prefix", None)
    local_name = getattr(qname, "localName", None)
    if prefix and local_name:
        return f"{prefix}:{local_name}"
    return str(qname)


def _parse_entry_points(values: Sequence[str]) -> dict[str, str]:
    entry_points: dict[str, str] = {}
    for value in values:
        form, separator, relative_path = value.partition("=")
        normalized = form.strip().upper()
        if (
            not separator
            or normalized not in SUPPORTED_FORMS
            or not relative_path.strip()
        ):
            raise ValueError(
                "Each entry point must be FORM=relative/path.xsd for ORDINARY, ABBREVIATED, or MICRO"
            )
        if normalized in entry_points:
            raise ValueError(f"Duplicate taxonomy entry point for {normalized}")
        entry_points[normalized] = relative_path.strip()
    if set(entry_points) != SUPPORTED_FORMS:
        raise ValueError(
            "Taxonomy catalogue requires ordinary, abbreviated, and micro entry points"
        )
    return entry_points


def _concept_record(concept: object) -> dict[str, Any]:
    qname = concept.qname
    return {
        "qname": _qname_text(qname),
        "label_it": concept.label(lang="it") or concept.label() or _qname_text(qname),
        "type": _qname_text(concept.typeQname) if concept.typeQname else None,
        "period_type": concept.periodType,
        "balance": concept.balance,
        "abstract": bool(concept.isAbstract),
        "nillable": bool(concept.isNillable),
        "forms": [],
        "presentation_roles": [],
        "calculation_parents": [],
        "table_memberships": [],
    }


def build_catalogue(
    package: Path,
    entry_points: Mapping[str, str],
    taxonomy_id: str,
    expected_sha256: str,
    official_source: str,
) -> dict[str, object]:
    """Load each official form DTS with Arelle and return a unified catalogue."""

    normalized_entry_points = _parse_entry_points(
        [f"{form}={path}" for form, path in entry_points.items()]
    )
    actual_sha256 = _sha256(package)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            "Taxonomy package checksum does not match the expected checksum"
        )
    try:
        import arelle
        from arelle import Cntlr, ModelManager, XbrlConst
    except ImportError as exc:
        raise RuntimeError(
            "arelle-release is required to build the taxonomy catalogue"
        ) from exc
    with tempfile.TemporaryDirectory(prefix="vera-xbrl-taxonomy-") as temporary:
        root = Path(temporary)
        _safe_extract(package, root)
        controller = Cntlr.Cntlr(
            logFileName="logToBuffer", disable_persistent_config=True
        )
        cache_dir = root / "arelle-cache"
        bundled_cache = Path(arelle.__file__).parent / "resources" / "cache"
        if not bundled_cache.is_dir():
            raise RuntimeError("Arelle's bundled standards cache is unavailable")
        shutil.copytree(bundled_cache, cache_dir)
        controller.webCache.cacheDir = str(cache_dir)
        controller.webCache.workOffline = True
        manager = ModelManager.initialize(controller)
        concepts: dict[str, dict[str, Any]] = {}
        namespaces: dict[str, str] = {}
        relationship_arcroles = {
            "presentation": XbrlConst.parentChild,
            "calculation": XbrlConst.summationItem,
            "dimension_domain": XbrlConst.dimensionDomain,
            "domain_member": XbrlConst.domainMember,
        }
        relationship_rows: dict[str, list[dict[str, object]]] = {
            name: [] for name in relationship_arcroles
        }
        try:
            for form, relative_path in normalized_entry_points.items():
                entry_path = (root / relative_path).resolve()
                if root.resolve() not in entry_path.parents or not entry_path.is_file():
                    raise ValueError(
                        f"Taxonomy entry point for {form} is missing or outside the package"
                    )
                model = manager.load(str(entry_path))
                try:
                    if model is None or getattr(model, "errors", None):
                        raise ValueError(
                            f"Arelle could not load the {form} taxonomy DTS without errors"
                        )
                    for concept in model.qnameConcepts.values():
                        qname = concept.qname
                        qname_text = _qname_text(qname)
                        prefix = getattr(qname, "prefix", None)
                        namespace = getattr(qname, "namespaceURI", None)
                        if prefix and namespace:
                            namespaces[str(prefix)] = str(namespace)
                        item = concepts.setdefault(qname_text, _concept_record(concept))
                        item["forms"].append(form)
                    for name, arcrole in relationship_arcroles.items():
                        relationship_set = model.relationshipSet(arcrole)
                        for relationship in relationship_set.modelRelationships:
                            source = _qname_text(relationship.fromModelObject.qname)
                            target = _qname_text(relationship.toModelObject.qname)
                            role = relationship.linkrole
                            relationship_rows[name].append(
                                {
                                    "from": source,
                                    "to": target,
                                    "role": role,
                                    "form": form,
                                    "order": str(relationship.order),
                                    "weight": (
                                        str(relationship.weight)
                                        if relationship.weight is not None
                                        else None
                                    ),
                                }
                            )
                            target_item = concepts.get(target)
                            if target_item is None:
                                continue
                            if name == "presentation":
                                target_item["presentation_roles"].append(role)
                            elif name == "calculation":
                                target_item["calculation_parents"].append(source)
                            else:
                                target_item["table_memberships"].append(role)
                finally:
                    if model is not None:
                        model.close()
            for item in concepts.values():
                for key in (
                    "forms",
                    "presentation_roles",
                    "calculation_parents",
                    "table_memberships",
                ):
                    item[key] = sorted(set(item[key]))
            for name, rows in relationship_rows.items():
                unique = {json.dumps(row, sort_keys=True): row for row in rows}
                relationship_rows[name] = [unique[key] for key in sorted(unique)]
            return {
                "schema_version": 1,
                "taxonomy_id": taxonomy_id,
                "taxonomy_package_sha256": actual_sha256,
                "official_source": official_source,
                "entry_points": normalized_entry_points,
                "namespaces": dict(sorted(namespaces.items())),
                "concepts": sorted(concepts.values(), key=lambda item: item["qname"]),
                "relationships": relationship_rows,
            }
        finally:
            controller.close()


def main(argv: list[str] | None = None) -> int:
    """Build and write one form-aware catalogue."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--entry-point", action="append", required=True)
    parser.add_argument("--taxonomy-id", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--official-source", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        entry_points = _parse_entry_points(args.entry_point)
        catalogue = build_catalogue(
            args.package.resolve(),
            entry_points,
            args.taxonomy_id,
            args.expected_sha256,
            args.official_source,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(catalogue, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        LOGGER.info("Wrote %s concepts to %s", len(catalogue["concepts"]), args.output)
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 2


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
