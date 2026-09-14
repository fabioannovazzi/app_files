"""Compile authored, localized course content into each native product package.

This build does no translation or semantic authoring. Changes to workflow sources
require editorial review before regenerating their recorded fingerprints.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = ["build", "main"]

ROOT = Path(__file__).resolve().parents[2]
AUTHORING = Path(__file__).parent
LANGUAGES = ["it", "en", "fr", "de", "es"]
EXCLUDED = {
    "legal-tax-answer-planner",
    "legal-tax-answer-review",
    "adversarial-opinion",
    "privacy-surface-review",
    "learn-with-vera",
    "learn-with-clara",
    "learn-with-lucia",
    "claim-basis-map",
}
LIMITED_LANGUAGES = {
    "vera/bilancio-oic": ["it", "en"],
    "vera/business-planning": ["it", "en"],
    "clara/business-planning": ["it", "en"],
    "vera/management-control-pack": ["it", "en"],
    "vera/centrale-rischi-review": ["it"],
    "vera/treasury-forecast": ["it"],
}


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: Any, *, check: bool = False) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if check:
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            raise ValueError(f"Course build is stale: {path.relative_to(ROOT)}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _eligible(product: str) -> set[str]:
    catalog = (
        ROOT / f"plugins/{product}/skills/{product}/references/workflow-catalog.md"
    )
    ids = (
        set(
            re.findall(r"^- `([a-z0-9-]+)`:", catalog.read_text(encoding="utf-8"), re.M)
        )
        - EXCLUDED
    )
    if product != "vera":
        ids.discard("studio-archive")
    return {
        key
        for key in ids
        if (ROOT / f"plugins/{product}/skills/{key}/SKILL.md").is_file()
    }


@lru_cache(maxsize=1)
def _package_builder() -> Any:
    """Reuse the package's authoritative vendor selection, including overlays."""
    spec = importlib.util.spec_from_file_location(
        "teaching_package_sources", ROOT / "scripts/build_codex_plugin_zip.py"
    )
    if spec is None or spec.loader is None:
        raise ValueError("Package source registry is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _vendor_records(component: str, prefix: str) -> list[dict[str, str]]:
    package = _package_builder()
    configuration = package.load_vendor_module_config()
    return [
        {
            "path": f"{prefix}vendor/modules/{relative}",
            "repository_path": source.relative_to(ROOT).as_posix(),
            "sha256": _sha(source),
        }
        for relative, source in package.shared_vendor_module_entries(
            configuration.get(component)
        ).items()
    ]


def _source_records(product: str, workflow: str) -> list[dict[str, str]]:
    root = ROOT / "plugins" / product
    skill = root / "skills" / workflow / "SKILL.md"
    paths = {skill}
    paths.update(
        path for path in skill.parent.rglob("*.md") if path.name != "cowork-runtime.md"
    )
    paths.update(skill.parent.rglob("*.py"))
    # Native Clara workflows call product-root helpers rather than a component
    # wrapper. Pin the referenced helpers and their same-directory imports too.
    documents = "\n".join(
        path.read_text(encoding="utf-8") for path in paths if path.suffix == ".md"
    )
    pending = [
        root / "scripts" / name
        for name in set(re.findall(r"scripts/([a-zA-Z0-9_/-]+\.py)", documents))
        if (root / "scripts" / name).is_file()
    ]
    visited: set[Path] = set()
    while pending:
        helper = pending.pop()
        if helper in visited:
            continue
        visited.add(helper)
        paths.add(helper)
        tree = ast.parse(helper.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules = (
                [node.module]
                if isinstance(node, ast.ImportFrom) and node.module
                else (
                    [item.name for item in node.names]
                    if isinstance(node, ast.Import)
                    else []
                )
            )
            for name in modules:
                dependency = helper.parent / (name.replace(".", "/") + ".py")
                if dependency.is_file() and dependency.resolve().is_relative_to(root):
                    pending.append(dependency)
    for relative in set(
        re.findall(r"((?:contracts|schemas)/[a-zA-Z0-9_./-]+\.json)", documents)
    ):
        candidate = root / relative
        if candidate.is_file():
            paths.add(candidate)
    text = skill.read_text(encoding="utf-8")
    vendored = _vendor_records(product, "")
    for module in set(re.findall(r"\.\./\.\./modules/([a-z0-9-]+)", text)):
        module_root = root / "modules" / module
        if not module_root.is_dir():
            module_root = ROOT / "plugins" / module
        if not module_root.is_dir():
            raise ValueError(f"Missing component source: {product}/{module}")
        vendored.extend(_vendor_records(module, f"modules/{module}/"))
        # Pin execution code and the rule packs/templates/assets it consumes.
        # A changed disclosure rule or report template also affects its lesson.
        if module_root == root / "modules" / module:
            candidates = [module_root / "scripts", module_root / "references"]
        else:
            component_skills = set(re.findall(r"skills/([a-z0-9-]+)/", text))
            candidates = [module_root / "skills" / key for key in component_skills]
            candidates += [
                module_root / "references",
                module_root / "scripts",
                module_root / "schemas",
            ]
        candidates += [
            module_root / name
            for name in ("rulepacks", "taxonomy", "templates", "assets")
        ]
        requirements = module_root / "requirements.txt"
        if requirements.is_file():
            paths.add(requirements)
        for candidate in candidates:
            if candidate.is_dir():
                paths.update(
                    p
                    for p in candidate.rglob("*")
                    if p.is_file()
                    and not {"__pycache__", "node_modules", ".git"} & set(p.parts)
                    and p.suffix not in {".pyc", ".pyo"}
                    and p.name != ".DS_Store"
                )
    records = []
    for path in sorted(paths, key=lambda item: item.as_posix()):
        if path.is_relative_to(root):
            relative = path.relative_to(root).as_posix()
        else:
            relative = "modules/" + path.relative_to(ROOT / "plugins").as_posix()
        records.append(
            {
                "path": relative,
                "repository_path": path.relative_to(ROOT).as_posix(),
                "sha256": _sha(path),
            }
        )
    return sorted([*records, *vendored], key=lambda record: record["path"])


def _locales() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for language in LANGUAGES:
        for file in sorted(AUTHORING.glob(f"kits_{language}*.json")):
            for key, content in _json(file).items():
                if language in result.setdefault(key, {}):
                    raise ValueError(f"Duplicate kit locale: {key}/{language}")
                result[key][language] = content
    return result


def _generated_files(folder: Path, expected: set[str], *, check: bool = False) -> None:
    """Keep a compiler-owned kit free of retired inputs and output specimens."""
    if folder.is_symlink():
        raise ValueError(f"Generated kit folder must not be a symlink: {folder}")
    if not folder.exists():
        return
    entries = list(folder.rglob("*"))
    if any(path.is_symlink() for path in entries):
        raise ValueError(f"Generated kit must not contain symlinks: {folder}")
    unexpected = [
        path
        for path in entries
        if path.is_file() and path.relative_to(folder).as_posix() not in expected
    ]
    if check and unexpected:
        raise ValueError(
            f"Unreferenced generated teaching files: {[str(p) for p in unexpected]}"
        )
    for path in unexpected:
        path.unlink()
    if not check:
        for directory in sorted(
            (path for path in entries if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            if not any(directory.iterdir()):
                directory.rmdir()


def build(*, require_complete: bool = True, check: bool = False) -> dict[str, Any]:
    """Compile reviewed kits with exact input files; never author outputs."""
    locales = _locales()
    definitions = _json(AUTHORING / "kits.json")
    expected = {f"{p}/{w}" for p in ("vera", "clara", "lucia") for w in _eligible(p)}
    if set(definitions) != expected:
        raise ValueError(
            f"Kit inventory differs from current teaching scope: {set(definitions) ^ expected}"
        )
    if set(locales) - expected:
        raise ValueError("A kit names a foreign or unavailable workflow")
    count = 0
    missing = []
    for product in ("vera", "clara", "lucia"):
        assets = ROOT / "plugins" / product / "assets/courses"
        index: dict[str, Any] = {
            "schema": "mparanza.teaching_catalog.v2",
            "product": product,
            "courses": {},
        }
        for workflow in sorted(_eligible(product)):
            key = f"{product}/{workflow}"
            supported = LIMITED_LANGUAGES.get(key, LANGUAGES)
            absent = set(supported) - set(locales.get(key, {}))
            if absent:
                missing.append(f"{key}: {sorted(absent)}")
                if not require_complete:
                    continue
                raise ValueError(f"Missing teaching translations: {missing}")
            if set(locales[key]) - set(supported):
                raise ValueError(f"Unsupported teaching translation: {key}")
            definition = definitions[key]
            destinations = [asset["path"] for asset in definition["files"]]
            if len(destinations) != len(set(destinations)):
                raise ValueError(
                    f"Teaching inputs need unique destinations across all languages: {key}"
                )
            files = []
            _generated_files(
                assets / workflow,
                {"course.json", *(asset["path"] for asset in definition["files"])},
                check=check,
            )
            for asset in definition["files"]:
                source = AUTHORING / "inputs" / asset["source"]
                target = assets / workflow / asset["path"]
                if (
                    source.is_symlink()
                    or not source.is_file()
                    or not source.resolve().is_relative_to(
                        (AUTHORING / "inputs").resolve()
                    )
                ):
                    raise ValueError(f"Missing or foreign input file: {source}")
                if (
                    not asset["path"].startswith("files/")
                    or ".." in Path(asset["path"]).parts
                ):
                    raise ValueError(
                        "Kit file destinations must be contained below files/"
                    )
                if check:
                    if (
                        not target.is_file()
                        or target.read_bytes() != source.read_bytes()
                    ):
                        raise ValueError(f"Teaching input is stale: {target}")
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                files.append(
                    {
                        "path": asset["path"],
                        "sha256": _sha(source),
                        "languages": asset["languages"],
                        "role": asset["role"],
                    }
                )
            for language in supported:
                for role in ("source", "practice"):
                    if not any(
                        f["role"] == role and language in f["languages"] for f in files
                    ):
                        raise ValueError(f"Kit needs {role} inputs: {key}/{language}")
            course = {
                "schema": "mparanza.teaching_kit.v2",
                "product": product,
                "workflow": workflow,
                "revision": "2026-09-14.2",
                "seconds": [45, 60, 105, 75, 45, 60],
                "supported_languages": supported,
                "language_basis": (
                    "workflow_output_contract"
                    if key in LIMITED_LANGUAGES
                    else "product_conversation_language_and_workflow_narrative"
                ),
                "group": definition["group"],
                "parent_workflow": definition.get("parent_workflow"),
                "execution": definition["execution"],
                "sources": _source_records(product, workflow),
                "files": files,
                "locales": locales[key],
            }
            path = assets / workflow / "course.json"
            _write(path, course, check=check)
            index["courses"][workflow] = {
                "path": path.relative_to(assets).as_posix(),
                "sha256": _sha(path),
                "languages": supported,
                "duration_seconds": sum(course["seconds"]),
                "group": definition["group"],
                "parent_workflow": definition.get("parent_workflow"),
                "titles": {
                    lang: value["title"] for lang, value in locales[key].items()
                },
                "goals": {lang: value["goal"] for lang, value in locales[key].items()},
            }
            count += len(locales[key])
        _write(assets / "index.json", index, check=check)
    return {
        "workflow_kits": len(locales),
        "localized_kits": count,
        "missing_translations": missing,
    }


def main() -> int:
    """Compile the corpus; partial builds are only for local authoring previews."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authoring-preview", action="store_true")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify compiled bytes without changing them",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            build(require_complete=not args.authoring_preview, check=args.check),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
