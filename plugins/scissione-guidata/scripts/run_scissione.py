"""Persist scissione revisions only inside a running Studio Archive engagement."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import re
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for candidate in (
    ROOT / "vendor/modules",
    ROOT.parent.parent / "vendor/modules",
    ROOT.parent / "_shared/vendor/modules",
):
    if (candidate / "vera_assurance").is_dir():
        sys.path.insert(0, str(candidate))
        break

from scissione_core import (  # noqa: E402
    ScissioneError,
    build_revision,
    digest,
    validate_case,
)
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
    load_client_workflow_context_for_output,
)

__all__ = ["execute", "main", "read_revision"]
FILES = {
    "revision.json",
    "review.html",
    "review.md",
    "ownership_before_after.json",
    "allocations.json",
    "change_impact.json",
}


def _read(path: Path) -> Any:
    info = path.lstat()
    if (
        path.is_symlink()
        or not path.is_file()
        or info.st_nlink != 1
        or info.st_size > 10_000_000
    ):
        raise ScissioneError("Expected a bounded regular single-link JSON file")
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        path.chmod(0o600)
        json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def _safe(root: Path, relative: str) -> Path:
    path = Path(relative)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"..", "."} for part in path.parts)
        or "\\" in relative
    ):
        raise ScissioneError("Expected a relative path inside this run")
    current = root
    for part in path.parts:
        current /= part
        if current.is_symlink():
            raise ScissioneError("Linked paths are not allowed")
    if not current.resolve().is_relative_to(root.resolve()):
        raise ScissioneError("Path leaves the run")
    return current


def read_revision(output: Path, revision_id: str | None = None) -> dict:
    """Verify the complete artifact inventory before reading a historical version."""
    if revision_id is None:
        pointer = _read(_safe(output, "scissione_current.json"))
        revision_id = pointer["revision_sha256"]
    if not isinstance(revision_id, str) or not re.fullmatch(
        r"[a-f0-9]{64}", revision_id
    ):
        raise ScissioneError("Invalid revision identity")
    folder = _safe(output, f"scissione_versions/{revision_id}")
    inventory = _read(_safe(folder, "artifact_manifest.json"))
    if set(inventory["files"]) != FILES:
        raise ScissioneError("Unexpected revision artifact inventory")
    for name, expected in inventory["files"].items():
        path = _safe(folder, name)
        if (
            not path.is_file()
            or path.stat().st_nlink != 1
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            raise ScissioneError("An immutable scissione artifact changed")
    revision = _read(_safe(folder, "revision.json"))
    if (
        digest(
            {key: value for key, value in revision.items() if key != "revision_sha256"}
        )
        != revision_id
        or revision["revision_sha256"] != revision_id
    ):
        raise ScissioneError("Revision digest mismatch")
    return revision


def _report(revision: dict) -> str:
    case = revision["case"]
    lines = [
        "# Scissione guidata — dossier di lavoro",
        "",
        f"Versione: {revision['revision_sha256']}",
        f"Stato tecnico: {revision['status']}",
        "",
        "Bozza per revisione professionale. Firma e deposito non eseguiti.",
        "La quadratura non attesta completezza della due diligence o validità giuridica.",
        "",
        "## Perimetro e questioni aperte",
        "",
        case["purpose"],
        "",
    ]
    lines.extend(f"- {issue}" for issue in revision["issues"])
    lines.extend(["", "## Decisioni ed evidenze", ""])
    for row in case["records"]:
        review = revision["approvals"].get(row["id"])
        lines.extend(
            [
                f"### {row['id']} ({row['kind']})",
                "",
                f"Stato evidenza: {row['status']}; revisore: {review['reviewer'] if review else 'in attesa'}.",
                f"Evidenze: {', '.join(row['evidence_ids']) or 'derivato'}; dipendenze: {', '.join(row['depends_on']) or 'nessuna'}.",
                "",
                json.dumps(row["data"], ensure_ascii=False, indent=2),
                "",
            ]
        )
    lines.extend(
        [
            "## Prospetti",
            "",
            json.dumps(revision["schedule"], ensure_ascii=False, indent=2),
            "",
            "## Modifiche e approvazioni da riaprire",
            "",
            json.dumps(revision["change_impact"], ensure_ascii=False, indent=2),
            "",
            "## Quali dati arrivano al modello",
            "",
            "Il modello può leggere il fascicolo, i documenti importati selezionati, fatti, assegnazioni, valori e decisioni necessari al lavoro. Questi script effettuano controlli e calcoli locali e non chiamano servizi esterni; la lettura dei file da parte di Codex o Cowork li porta nel contesto del modello del servizio scelto. Nessuna anonimizzazione automatica o garanzia di trattamento esclusivamente locale. Il report della singola esecuzione registra ciò che è stato effettivamente letto.",
        ]
    )
    return "\n".join(lines) + "\n"


def _store(output: Path, revision: dict) -> None:
    versions = _safe(output, "scissione_versions")
    versions.mkdir(exist_ok=True, mode=0o700)
    target = _safe(versions, revision["revision_sha256"])
    stage = output / f".scissione-{uuid.uuid4().hex}"
    stage.mkdir(mode=0o700)
    try:
        _write(stage / "revision.json", revision)
        _write(
            stage / "ownership_before_after.json",
            revision["schedule"].get("owners", []),
        )
        _write(stage / "allocations.json", revision["schedule"].get("allocations", []))
        _write(stage / "change_impact.json", revision["change_impact"])
        report = _report(revision)
        (stage / "review.md").write_text(report, encoding="utf-8")
        (stage / "review.html").write_text(
            '<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Scissione guidata</title><style>body{max-width:70rem;margin:3rem auto;padding:0 1.5rem;font:16px/1.6 system-ui;color:#002060}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><body><pre>'
            + html.escape(report)
            + "</pre></body></html>",
            encoding="utf-8",
        )
        inventory = {
            name: hashlib.sha256((stage / name).read_bytes()).hexdigest()
            for name in sorted(FILES)
        }
        _write(
            stage / "artifact_manifest.json",
            {"files": inventory, "revision_sha256": revision["revision_sha256"]},
        )
        if target.exists():
            raise ScissioneError(
                "A revision already exists; reload instead of overwriting"
            )
        stage.rename(target)
        temporary = output / f".scissione-pointer-{uuid.uuid4().hex}.json"
        _write(
            temporary,
            {
                "revision_sha256": revision["revision_sha256"],
                "report": f"scissione_versions/{revision['revision_sha256']}/review.html",
            },
        )
        temporary.replace(_safe(output, "scissione_current.json"))
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def execute(
    context_path: Path,
    command: str,
    request_path: Path | None = None,
    revision_id: str | None = None,
) -> dict:
    """Bind all case sources and writes to the real portable archive contract."""
    statuses = (
        ("running", "ready_for_review", "completed")
        if command == "show"
        else ("running",)
    )
    context = load_client_engagement_context_file(
        context_path,
        expected_workflow_id="scissione-guidata",
        allowed_statuses=statuses,
    )
    output = Path(context["output_dir"])
    if command == "show":
        return read_revision(output, revision_id)
    if (
        request_path is None
        or not request_path.is_absolute()
        or not request_path.is_relative_to(output)
    ):
        raise ScissioneError(
            "Save the proposal or review request inside this run's output folder"
        )
    load_client_workflow_context_for_output(
        request_path, expected_workflow_id="scissione-guidata"
    )
    request = _read(request_path)
    lock = _safe(output, ".scissione.lock")
    try:
        stream = lock.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise ScissioneError("Another write is in progress; reload and retry") from exc
    try:
        with stream:
            exists = (output / "scissione_current.json").exists()
            previous = read_revision(output) if exists else None
            if command == "prepare":
                if previous:
                    raise ScissioneError("Case exists; submit an explicit revision")
                if request.get("previous_revision_path") is not None:
                    prior_path = _safe(
                        Path(context["run_root"]) / "inputs",
                        request["previous_revision_path"],
                    )
                    binding = next(
                        (
                            item
                            for item in context["input_bindings"]
                            if item["path"] == str(prior_path)
                        ),
                        None,
                    )
                    if (
                        binding is None
                        or binding["kind"] != "upstream_artifact"
                        or binding["upstream_workflow_id"] != "scissione-guidata"
                    ):
                        raise ScissioneError(
                            "Continuation requires a finalized same-engagement scissione artifact"
                        )
                    previous = _read(prior_path)
                    if previous["revision_sha256"] != digest(
                        {
                            key: value
                            for key, value in previous.items()
                            if key != "revision_sha256"
                        }
                    ):
                        raise ScissioneError("Previous revision digest mismatch")
                case = request["case"]
            elif command in {"revise", "review"}:
                if (
                    previous is None
                    or request["revision_sha256"] != previous["revision_sha256"]
                ):
                    raise ScissioneError("Stale or missing revision")
                case = request["case"] if command == "revise" else previous["case"]
            else:
                raise ScissioneError("Unknown case command")
            validate_case(case)
            input_root = Path(context["run_root"]) / "inputs"
            paths = [_safe(input_root, item["path"]) for item in case["evidence"]]
            load_client_engagement_context_file(
                context_path,
                expected_workflow_id="scissione-guidata",
                input_paths=paths,
            )
            for item, path in zip(case["evidence"], paths, strict=True):
                if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                    raise ScissioneError(
                        "Evidence digest does not match the receipted input"
                    )
            revision = build_revision(
                case, previous=previous, review=request if command == "review" else None
            )
            _store(output, revision)
            return revision
    finally:
        lock.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "revise", "review", "show"])
    parser.add_argument("--client-engagement", type=Path, required=True)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--revision")
    args = parser.parse_args(argv)
    try:
        revision = execute(
            args.client_engagement, args.command, args.request, args.revision
        )
    except (
        ScissioneError,
        AssuranceContractError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        logging.error("Scissione blocked: %s", exc)
        return 2
    logging.info(
        "Scissione %s; revision %s; %s unresolved issues",
        revision["status"],
        revision["revision_sha256"],
        len(revision["issues"]),
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
