"""Compile authored, localized course content into each native product package.

This build does no translation or semantic authoring. Changes to workflow sources
require editorial review before regenerating their recorded fingerprints.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
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
    "advisory-brief-planner",
    "advisory-case-director",
    "advisory-deliverable-validator",
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
# Authored plotting values, checked against each case's displayed output rows.
# Labels and value text come from those localized rows, never guessed headers.
VISUALS = {
    "vera/business-planning": {"column": 1, "bars": [[0, 60000], [1, 42000]]},
    "clara/business-planning": {"column": 1, "bars": [[0, 60000], [1, 42000]]},
    "vera/financial-analysis": {
        "column": 2,
        "maximum": 100,
        "bars": [[0, 60], [1, 85]],
    },
    "vera/sales-plan": {"column": 2, "bars": [[0, 1800], [1, 1881]]},
    "clara/attribute-reporting": {
        "column": 2,
        "maximum": 100,
        "bars": [[0, 60], [1, 30]],
    },
    "clara/reporting-engine": {"column": 1, "bars": [[0, 40000], [1, 50000]]},
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
    ids = set(re.findall(r"^- `([a-z0-9-]+)`:", catalog.read_text(), re.M)) - EXCLUDED
    if product != "vera":
        ids.discard("studio-archive")
    return {
        key
        for key in ids
        if (ROOT / f"plugins/{product}/skills/{key}/SKILL.md").is_file()
    }


def _source_records(product: str, workflow: str) -> list[dict[str, str]]:
    root = ROOT / "plugins" / product
    skill = root / "skills" / workflow / "SKILL.md"
    paths = {skill}
    paths.update(
        path for path in skill.parent.rglob("*.md") if path.name != "cowork-runtime.md"
    )
    paths.update(skill.parent.rglob("*.py"))
    text = skill.read_text()
    for module in set(re.findall(r"\.\./\.\./modules/([a-z0-9-]+)", text)):
        module_root = root / "modules" / module
        if not module_root.is_dir():
            module_root = ROOT / "plugins" / module
        if not module_root.is_dir():
            raise ValueError(f"Missing component source: {product}/{module}")
        # Pin method documents, input schemas and execution code. Compiled and
        # package-generated support files are deliberately outside this set.
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
        for candidate in candidates:
            if candidate.is_dir():
                paths.update(
                    p
                    for p in candidate.rglob("*")
                    if p.suffix in {".md", ".py", ".json"} and p.is_file()
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
    return records


def _locales() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for language in LANGUAGES:
        for file in sorted(AUTHORING.glob(f"lessons_{language}*.json")):
            for key, content in _json(file).items():
                if language in result.setdefault(key, {}):
                    raise ValueError(f"Duplicate course locale: {key}/{language}")
                result[key][language] = content
    # These products own the same shared workflows. Reuse the course only with
    # an explicit product adaptation, then bind to the target's own sources.
    for target, source in {
        "clara/business-planning": "vera/business-planning",
        "lucia/comunicazione-professionale": "vera/comunicazione-professionale",
        "lucia/presenza-digitale-studio": "vera/presenza-digitale-studio",
        "lucia/quesito-legale-fiscale": "vera/quesito-legale-fiscale",
    }.items():
        content = copy.deepcopy(result[source])
        name = target.split("/")[0].title()
        # JSON text replacement only changes the invoking assistant and the
        # supplied fictional firm's actual service; no runtime translation.
        serialized = json.dumps(content, ensure_ascii=False).replace("Vera", name)
        if target == "lucia/presenza-digitale-studio":
            serialized = (
                serialized.replace("consulenza contabile", "assistenza legale")
                .replace(
                    "Contabilità e controllo di gestione",
                    "Contratti e controversie commerciali",
                )
                .replace(
                    "contabilità e controllo di gestione",
                    "contratti e controversie commerciali",
                )
                .replace("accounting advisory", "legal advisory")
                .replace(
                    "Accounting and management control",
                    "Contracts and commercial disputes",
                )
                .replace("conseil comptable", "conseil juridique")
                .replace(
                    "Comptabilité et contrôle de gestion",
                    "Contrats et litiges commerciaux",
                )
                .replace("Buchhaltungsberatung", "Rechtsberatung")
                .replace(
                    "Buchhaltung und Controlling", "Verträge und Handelsstreitigkeiten"
                )
                .replace("asesoramiento contable", "asesoramiento jurídico")
                .replace(
                    "Contabilidad y control de gestión",
                    "Contratos y controversias comerciales",
                )
            )
        result[target] = json.loads(serialized)
    return result


def build(*, require_complete: bool = True, check: bool = False) -> dict[str, Any]:
    """Build exact product catalogs; reject missing or unexpected authored lessons."""
    locales = _locales()
    expected = {
        f"{product}/{key}"
        for product in ("vera", "clara", "lucia")
        for key in _eligible(product)
    }
    if set(locales) != expected:
        raise ValueError(
            f"Course coverage mismatch: missing={sorted(expected-set(locales))}; unexpected={sorted(set(locales)-expected)}"
        )
    missing = {
        key: sorted(set(LIMITED_LANGUAGES.get(key, LANGUAGES)) - set(locales[key]))
        for key in expected
    }
    missing = {key: value for key, value in missing.items() if value}
    if require_complete and missing:
        raise ValueError(
            "Missing authored translations: " + json.dumps(missing, ensure_ascii=False)
        )
    count = 0
    for product in ("vera", "clara", "lucia"):
        index: dict[str, Any] = {
            "schema": "mparanza.course_catalog.v1",
            "product": product,
            "courses": {},
        }
        assets = ROOT / "plugins" / product / "assets/courses"
        for workflow in sorted(_eligible(product)):
            key = f"{product}/{workflow}"
            supported = LIMITED_LANGUAGES.get(key, LANGUAGES)
            extra = set(locales[key]) - set(supported)
            if extra:
                raise ValueError(f"Unsupported course translations: {key}: {extra}")
            course = {
                "schema": "mparanza.course.v1",
                "product": product,
                "workflow": workflow,
                "revision": "2026-09-14.1",
                "seconds": [45, 60, 75, 90, 75, 45],
                "supported_languages": supported,
                "language_basis": (
                    "workflow_output_contract"
                    if key in LIMITED_LANGUAGES
                    else "product_conversation_language_and_workflow_narrative"
                ),
                "sources": _source_records(product, workflow),
                "example_kind": "authored_synthetic_specimen_not_execution_receipt",
                "files": [],
                "locales": locales[key],
            }
            if key in VISUALS:
                course["visual"] = VISUALS[key]
            # Explicit attachments are authored separately and hash-bound. An
            # output from a real fixture run includes its own execution evidence.
            attachment_root = assets / workflow / "files"
            if attachment_root.is_dir():
                course["files"] = [
                    {
                        "path": "files/" + p.relative_to(attachment_root).as_posix(),
                        "sha256": _sha(p),
                    }
                    for p in sorted(attachment_root.rglob("*"))
                    if p.is_file()
                ]
            path = assets / workflow / "course.json"
            _write(path, course, check=check)
            index["courses"][workflow] = {
                "path": path.relative_to(assets).as_posix(),
                "sha256": _sha(path),
                "languages": [
                    language for language in supported if language in locales[key]
                ],
                "duration_seconds": sum(course["seconds"]),
                "titles": {
                    language: content["title"]
                    for language, content in locales[key].items()
                },
            }
            count += len(locales[key])
        _write(assets / "index.json", index, check=check)
    return {
        "workflows": len(expected),
        "localized_courses": count,
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
