"""Generate reviewed source contracts and public explanations from the same records."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import logging
from pathlib import Path
from types import ModuleType

__all__ = ["build", "main"]
ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ("vera", "clara", "lucia")
LOGGER = logging.getLogger(__name__)


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load privacy implementation: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(root: Path = ROOT, *, check: bool = False) -> list[str]:
    """Project reviewed bytes only; generation never refreshes or approves a review."""
    shared = root / "plugins/_shared/privacy-runtime"
    contracts = _load(shared / "scripts/privacy_contract.py", "_privacy_contract_build")
    validator = _load(
        shared / "skills/privacy-surface-review/scripts/validate_privacy_surfaces.py",
        "_privacy_source_validation",
    )
    differences = []
    page_index: dict[str, list[str]] = {}
    for product in PRODUCTS:
        product_root = root / "plugins" / product
        errors = validator.validate_privacy_surfaces(product_root)
        if errors:
            raise ValueError(
                f"{product}: unreviewed source register: " + "; ".join(errors)
            )
        registry = json.loads((product_root / "privacy/registry.json").read_text())
        index = {
            "schema_version": 1,
            "product": product,
            "contracts": {},
            "installed_contracts": {},
        }
        public = {"schema_version": 1, "product": product, "pages": {}}
        generated: dict[Path, bytes] = {}
        for workstream, entry in sorted(registry["workstreams"].items()):
            document = contracts.contract_document(product_root, workstream)
            data = contracts.canonical_bytes(document)
            digest = hashlib.sha256(data).hexdigest()
            index["contracts"][workstream] = digest
            index["installed_contracts"][workstream] = digest
            generated[product_root / f"privacy/contracts/{workstream}.json"] = data
            for page in entry["public_pages"]:
                page_id = page["page_id"]
                public_path = root / page["path"]
                if not public_path.is_file():
                    raise ValueError(
                        f"{product}/{page_id}: registered public page is missing"
                    )
                page_source = public_path.read_text(encoding="utf-8")
                if not any(
                    loader in page_source
                    for loader in ("function-model-data.js", "product-function-page.js")
                ):
                    raise ValueError(
                        f"{product}/{page_id}: public page has no shared privacy renderer"
                    )
                if page_id in public["pages"]:
                    raise ValueError(
                        f"{product}/{page_id}: duplicate public privacy owner"
                    )
                public["pages"][page_id] = {
                    "workstream": workstream,
                    "role": entry["role"],
                    "contract_sha256": digest,
                    "reviewed_at": document["manifest"]["review"]["reviewed_at"],
                    "runtime_profiles": document["manifest"]["runtime_profiles"],
                    **document["manifest"]["public_explanations"][page_id],
                }
                page_index.setdefault(page_id, []).append(product)
        generated[product_root / "privacy/contracts/index.json"] = (
            contracts.canonical_bytes(index)
        )
        generated[root / f"static/shared/privacy-contracts/{product}.json"] = (
            contracts.canonical_bytes(public)
        )
        present = set((product_root / "privacy/contracts").glob("*.json"))
        extra = present - generated.keys()
        if extra:
            raise ValueError(
                f"{product}: unregistered retained contracts: {sorted(path.name for path in extra)}"
            )
        for destination, content in generated.items():
            if not destination.is_file() or destination.read_bytes() != content:
                differences.append(destination.relative_to(root).as_posix())
                if not check:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(content)
    destination = root / "static/shared/privacy-contracts/index.json"
    content = contracts.canonical_bytes({"schema_version": 1, "pages": page_index})
    if not destination.is_file() or destination.read_bytes() != content:
        differences.append(destination.relative_to(root).as_posix())
        if not check:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
    return differences


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        differences = build(check=args.check)
    except (OSError, KeyError, ValueError) as exc:
        LOGGER.error("Privacy contract generation failed: %s", exc)
        return 1
    if args.check and differences:
        LOGGER.error("Reviewed privacy contract drift: %s", ", ".join(differences))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
