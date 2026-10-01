"""Prepare blind course-based Cowork runs and verify maintainer evidence.

Exact fixture identities, arithmetic and file hashes are mechanically verifiable.
Host use, meaning, visible links and document quality require named inspection.
This tool neither drives Cowork nor authenticates a reviewer's host attestation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import shutil
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

__all__ = ["prepare", "verify", "main"]

ROOT = Path(__file__).resolve().parents[2]
CATALOG = Path(__file__).with_name("cowork_acceptance_cases.json")
ROUTES = ("guided", "ordinary")
PHASES = ("demo", "practice", "resume")
CHECKS = (
    "native_workflow_used",
    "findings_and_unresolved_items",
    "readable_deliverables",
    "source_and_output_links_opened",
    "durable_records_reopened",
    "previous_work_preserved",
)


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _file(root: Path, relative: str) -> Path:
    """Evidence must be a contained regular file, including all parent paths."""
    path = root / relative
    if (
        not relative
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
        or any(p.is_symlink() for p in (path, *path.parents))
        or not path.is_file()
        or not path.resolve().is_relative_to(root.resolve())
    ):
        raise ValueError(f"Missing, symlinked or foreign evidence: {relative}")
    return path


def _records(root: Path, items: list[dict[str, str]]) -> None:
    if not items or len({item["path"] for item in items}) != len(items):
        raise ValueError("Evidence requires distinct file records")
    for item in items:
        if _sha(_file(root, item["path"])) != item["sha256"]:
            raise ValueError(f"Evidence changed: {item['path']}")


def _scan(source: Path, destination: Path) -> None:
    """Rasterize the existing fictional text; retain no PDF text layer."""
    import pymupdf

    with pymupdf.open() as text_pdf:
        page = text_pdf.new_page()
        # Built-in Helvetica supports the fixture's European characters.
        if (
            page.insert_textbox(
                pymupdf.Rect(40, 40, 555, 800), source.read_text(), fontsize=12
            )
            < 0
        ):
            raise ValueError("Scan fixture text does not fit")
        pixels = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
        with pymupdf.open() as scan_pdf:
            scan_pdf.new_page().insert_image(page.rect, pixmap=pixels)
            scan_pdf.save(destination)


def prepare(
    package: Path, output: Path, *, package_url: str, root: Path = ROOT
) -> dict[str, Any]:
    """Create separate source-only workspaces; never execute uploaded code."""
    if output.exists():
        raise ValueError(
            "Use a new isolated output folder; previous runs are preserved"
        )
    catalog = _read(CATALOG)
    output.mkdir(parents=True)
    shutil.copyfile(package, output / "package.zip")
    shutil.copyfile(CATALOG, output / "cases.json")
    manifest: dict[str, Any] = {
        "schema": "vera.cowork_acceptance.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "package": {"path": "package.zip", "sha256": _sha(package), "url": package_url},
        "catalog_sha256": _sha(CATALOG),
        "courses": {},
        "steps": [],
    }
    with ZipFile(package) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Ambiguous archive members")
        metadata = json.loads(archive.read(".claude-plugin/plugin.json"))
        if metadata["name"] != "vera":
            raise ValueError("Use the downloadable Vera Cowork package")
        manifest["version"] = metadata["version"]
        for case, spec in catalog["cases"].items():
            workflow = spec["workflow"]
            prefix = f"assets/courses/{workflow}/"
            raw = archive.read(prefix + "course.json")
            course = json.loads(raw)
            current = root / "plugins/vera" / prefix / "course.json"
            canonical = _read(current)
            # Cowork rewrites host-specific teaching prose. Bind both revisions
            # while requiring exactly the same authored source/practice files.
            if any(
                course[key] != canonical[key]
                for key in ("product", "workflow", "revision", "files")
            ):
                raise ValueError(
                    f"Package course fixtures differ from source: {workflow}"
                )
            provenance = {
                "revision": course["revision"],
                "sha256": hashlib.sha256(raw).hexdigest(),
                "source_sha256": _sha(current),
            }
            manifest["courses"][workflow] = provenance
            _write(output / f"courses/{workflow}.json", course)
            for route in ROUTES:
                workspace = output / f"workspaces/{case}/{route}"
                workspace.mkdir(parents=True)
                inputs = []
                for entry in course["files"]:
                    if catalog["language"] not in entry["languages"]:
                        continue
                    relative = Path(entry["path"])
                    if relative.is_absolute() or ".." in relative.parts:
                        raise ValueError("Foreign fixture path")
                    data = archive.read(prefix + entry["path"])
                    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                        raise ValueError("Package fixture hash mismatch")
                    phase = "demo" if entry["role"] == "source" else "practice"
                    target = workspace / phase / relative.name
                    target.parent.mkdir(exist_ok=True)
                    target.write_bytes(data)
                    if spec.get("derived_from") == target.name:
                        scan = target.with_name("F24-first-scan.pdf")
                        _scan(target, scan)
                        # Derivation is recorded outside the connected workspace.
                        _write(
                            output / f"derivations/{case}-{route}-{phase}.json",
                            {
                                "source_sha256": _sha(target),
                                "scan_sha256": _sha(scan),
                                "method": "PyMuPDF 2x raster, image-only PDF",
                                "source": entry,
                            },
                        )
                        target.unlink()
                        target = scan
                    inputs.append(
                        {
                            "path": target.relative_to(output).as_posix(),
                            "sha256": _sha(target),
                        }
                    )
                locale = course["locales"][catalog["language"]]
                for phase in PHASES:
                    prompt = (
                        locale["request"] if phase == "demo" else locale["practice"]
                    )
                    if route == "guided" and phase == "demo":
                        prompt = f"Vera, insegnami {locale['title']}. Usa il corso esistente e i suoi esempi, nella cartella demo."
                    if case == "fiscal-scan" and phase != "resume":
                        prompt += " Usa F24-first-scan.pdf come primo F24; se la lettura della scansione non è disponibile, indica il blocco."
                    if phase == "resume":
                        prompt = "Vera, riprendi il lavoro salvato in questa cartella. Riapri fonti, risultati e note di revisione precedenti senza rifare il calcolo. Mostra i punti ancora da chiarire e mantieni il lavoro precedente."
                    prompt += "\nLavora solo nella cartella collegata e conserva fonti e risultati precedenti."
                    prompt_path = workspace / f"request-{phase}.txt"
                    prompt_path.write_text(prompt + "\n")
                    identity = f"{case}/{route}/{phase}"
                    manifest["steps"].append(
                        {
                            "id": identity,
                            "case": case,
                            "route": route,
                            "phase": phase,
                            "inputs": inputs,
                            "prompt": {
                                "path": prompt_path.relative_to(output).as_posix(),
                                "sha256": _sha(prompt_path),
                            },
                            "review": f"reviews/{case}-{route}-{phase}.json",
                        }
                    )
                    _write(
                        output / f"reviews/{case}-{route}-{phase}.json",
                        {
                            "id": identity,
                            "outcome": "not_run",
                            "reason": "",
                            "reviewer": "",
                            "date": "",
                            "session_id": "",
                            "host": {
                                "name": "Claude Cowork",
                                "environment": "",
                                "model": "",
                                "installed_version": "",
                                "package_sha256": "",
                            },
                            "checks": {},
                            "evidence": [],
                            "artifacts": [],
                            "durable_records": [],
                            "mechanical_files": {},
                        },
                    )
    _write(output / "run.json", manifest)
    return manifest


def _mechanical(
    root: Path, step: dict[str, Any], review: dict[str, Any], spec: dict[str, Any]
) -> None:
    """Check current native outputs, not a reviewer-entered answer summary."""
    phase = "practice" if step["phase"] == "resume" else step["phase"]
    files = review["mechanical_files"]
    expected = spec["expected"][phase]
    records = {item["path"] for item in review["artifacts"]}
    if not set(files.values()).issubset(records):
        raise ValueError("Mechanical outputs must be included in artifact hashes")
    if step["case"] == "bank":
        audit = _read(_file(root, files["audit"]))
        if any(audit[key] != value for key, value in expected.items()):
            raise ValueError("Reconciliation counts differ from the authored case")
        with _file(root, files["matches"]).open(
            encoding="utf-8-sig", newline=""
        ) as stream:
            matches = list(csv.DictReader(stream))
        amounts = [Decimal("-1220"), Decimal("-732")]
        if phase == "practice":
            amounts.append(Decimal("-488"))
        if sorted(Decimal(row["bank_amount"]) for row in matches) != sorted(amounts):
            raise ValueError("Matched amounts differ from the authored case")
        for row in matches:
            if (
                Decimal(row["bank_amount"]) != Decimal(row["journal_amount"])
                or Decimal(row["amount_delta"]) != 0
                or not row["shared_references"]
            ):
                raise ValueError("Match lacks exact amount and reference evidence")
            expected_pair = {
                Decimal("-1220"): ("2026-03-18", "trn001"),
                Decimal("-732"): ("2026-03-25", "trn002"),
                Decimal("-488"): ("2026-04-04", "trn003"),
            }[Decimal(row["bank_amount"])]
            if (
                row["status"] != "matched"
                or row["bank_date"] != expected_pair[0]
                or row["journal_date"] != expected_pair[0]
                or expected_pair[1] not in row["shared_references"].split(",")
            ):
                raise ValueError("Match date/reference differs from the source pair")
        for side in ("bank", "journal"):
            if len({row[f"{side}_transaction_id"] for row in matches}) != len(matches):
                raise ValueError("Reused matching evidence")
    elif step["case"] == "report":
        ledger = _read(_file(root, files["numeric_ledger"]))
        sums = [
            (item["source_sheet"], item["value"])
            for item in ledger["entries"]
            if item["evidence_id"].endswith(".sum")
        ]
        if sorted(sums) != sorted(expected.items()):
            raise ValueError("Report totals differ from the authored case")
    else:
        with _file(root, files["fields"]).open(
            encoding="utf-8-sig", newline=""
        ) as stream:
            rows = list(csv.DictReader(stream))
        if {Path(row["relative_path"]).name for row in rows} != set(expected):
            raise ValueError("Fiscal extraction has wrong document coverage")
        for filename, fields in expected.items():
            for code, value in fields.items():
                values = [
                    row["normalized_value"]
                    for row in rows
                    if Path(row["relative_path"]).name == filename
                    and row["field_code"] == code
                ]
                if values != [value]:
                    raise ValueError(
                        f"Missing, duplicate or incorrect field: {filename}/{code}"
                    )


def verify(run: Path, *, root: Path = ROOT) -> dict[str, Any]:
    """Reject stale or incomplete passes; retain blocked/failed/not-run scope."""
    manifest = _read(run / "run.json")
    catalog = _read(run / "cases.json")
    if (
        manifest["schema"] != "vera.cowork_acceptance.v1"
        or _sha(run / "cases.json") != manifest["catalog_sha256"]
        or _sha(CATALOG) != manifest["catalog_sha256"]
    ):
        raise ValueError("Stale acceptance catalog")
    _records(run, [manifest["package"]])
    if set(manifest["courses"]) != {
        spec["workflow"] for spec in catalog["cases"].values()
    }:
        raise ValueError("Missing course scope")
    with ZipFile(_file(run, manifest["package"]["path"])) as archive:
        metadata = json.loads(archive.read(".claude-plugin/plugin.json"))
        if metadata["name"] != "vera" or metadata["version"] != manifest["version"]:
            raise ValueError("Package version changed")
        for workflow, course in manifest["courses"].items():
            raw = archive.read(f"assets/courses/{workflow}/course.json")
            if hashlib.sha256(raw).hexdigest() != course["sha256"]:
                raise ValueError("Course evidence differs from the installed package")
    for workflow, course in manifest["courses"].items():
        current = root / f"plugins/vera/assets/courses/{workflow}/course.json"
        if (
            _sha(current) != course["source_sha256"]
            or _sha(_file(run, f"courses/{workflow}.json")) != course["sha256"]
        ):
            raise ValueError("Stale course revision")
        canonical = _read(current)
        for source in canonical["sources"]:
            if _sha(_file(root, source["repository_path"])) != source["sha256"]:
                raise ValueError(
                    f"Course runtime source changed: {source['repository_path']}"
                )
    expected_ids = {
        f"{case}/{route}/{phase}"
        for case in catalog["cases"]
        for route in ROUTES
        for phase in PHASES
    }
    if {step["id"] for step in manifest["steps"]} != expected_ids or len(
        manifest["steps"]
    ) != len(expected_ids):
        raise ValueError("Missing or duplicate route/phase")
    outcomes: dict[str, str] = {}
    sessions: dict[str, str] = {}
    previous: dict[str, dict[str, Any]] = {}
    owners: dict[str, str] = {}
    for step in manifest["steps"]:
        identity = f"{step['case']}/{step['route']}/{step['phase']}"
        if identity != step["id"]:
            raise ValueError("Step identity changed")
        _records(run, step["inputs"])
        _records(run, [step["prompt"]])
        review = _read(_file(run, step["review"]))
        outcome = review["outcome"]
        if review["id"] != identity or outcome not in {
            "passed",
            "failed",
            "blocked",
            "not_run",
        }:
            raise ValueError("Invalid scoped outcome")
        outcomes[identity] = outcome
        if outcome == "not_run":
            continue
        if not all(
            isinstance(review[key], str) and review[key].strip()
            for key in ("reason", "reviewer", "date", "session_id")
        ):
            raise ValueError(
                "Executed or blocked steps require named, dated observations"
            )
        datetime.fromisoformat(review["date"])
        _records(run, review["evidence"])
        for category in ("artifacts", "durable_records"):
            if review[category]:
                _records(run, review[category])
        if outcome != "passed":
            continue
        key = f"{step['case']}/{step['route']}"
        owner = owners.setdefault(review["session_id"], key)
        if owner != key:
            raise ValueError("Routes/cases need independent Cowork sessions")
        host = review["host"]
        if (
            host["name"] != "Claude Cowork"
            or not host["environment"]
            or not host["model"]
            or host["installed_version"] != manifest["version"]
            or host["package_sha256"] != manifest["package"]["sha256"]
        ):
            raise ValueError(
                "Pass requires exact real Cowork package/environment attestation"
            )
        for check in CHECKS:
            observation = review["checks"].get(check, {})
            if (
                observation.get("outcome") != "passed"
                or not observation.get("note")
                or not observation.get("evidence_paths")
                or not set(observation["evidence_paths"]).issubset(
                    {item["path"] for item in review["evidence"]}
                )
            ):
                raise ValueError(f"Pass lacks inspected evidence: {identity}/{check}")
        _records(run, review["artifacts"])
        _records(run, review["durable_records"])
        prefix = f"workspaces/{key}/"
        if any(
            not item["path"].startswith(prefix)
            for item in review["artifacts"] + review["durable_records"]
        ):
            raise ValueError("Outputs and records must belong to this route workspace")
        suffixes = {Path(item["path"]).suffix for item in review["artifacts"]}
        required = (
            {".xlsx", ".md"}
            if step["case"] == "bank"
            else (
                {".docx", ".xlsx", ".md"}
                if step["case"] == "report"
                else {".csv", ".md"}
            )
        )
        if not required.issubset(suffixes):
            raise ValueError("Pass lacks the workflow's actual deliverables")
        if {item["sha256"] for item in review["artifacts"]} & {
            item["sha256"] for item in step["inputs"]
        }:
            raise ValueError("Copied input cannot count as generated work")
        _mechanical(run, step, review, catalog["cases"][step["case"]])
        if step["phase"] != "demo":
            predecessor = key + ("/practice" if step["phase"] == "resume" else "/demo")
            if outcomes.get(predecessor) != "passed":
                raise ValueError(
                    "Practice/resume requires its own preceding accepted run"
                )
            old = previous[key]
            _records(run, old["artifacts"] + old["durable_records"])
            if step["phase"] == "resume" and review["session_id"] == sessions[key]:
                raise ValueError("Resume requires a new Cowork session")
        sessions[key] = review["session_id"]
        previous[key] = review
    required = [
        value for key, value in outcomes.items() if not key.startswith("fiscal-scan/")
    ]
    return {
        "version": manifest["version"],
        "package_sha256": manifest["package"]["sha256"],
        "outcomes": outcomes,
        "core_passed": all(value == "passed" for value in required),
        "all_passed": all(value == "passed" for value in outcomes.values()),
        "evidence_kind": "maintainer_host_attestation_with_file_checks",
    }


def main() -> None:
    """Prepare candidates or enforce acceptance for an exact recorded package."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("prepare")
    setup.add_argument("--package", type=Path, required=True)
    setup.add_argument("--package-url", required=True)
    setup.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("verify")
    check.add_argument("run", type=Path)
    check.add_argument("--require-core-passed", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        if args.command == "prepare":
            result = prepare(args.package, args.output, package_url=args.package_url)
            logging.info(
                "Prepared %d unexecuted Cowork steps at %s",
                len(result["steps"]),
                args.output,
            )
        else:
            result = verify(args.run)
            logging.info(json.dumps(result, indent=2))
            if args.require_core_passed and not result["core_passed"]:
                parser.exit(1, "Real Cowork core acceptance is incomplete\n")
            if (
                args.require_core_passed
                and result["version"]
                != _read(ROOT / "plugins/vera/.codex-plugin/plugin.json")["version"]
            ):
                parser.exit(1, "Acceptance is for a different release version\n")
    except (ValueError, OSError, KeyError, BadZipFile) as exc:
        parser.exit(2, f"Invalid acceptance evidence: {exc}\n")


if __name__ == "__main__":
    main()
