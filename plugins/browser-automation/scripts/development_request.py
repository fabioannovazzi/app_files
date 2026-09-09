#!/usr/bin/env python3
"""Prepare an exact, reviewable development handoff from selected saved evidence.

The model selects and sanitizes facts. Code checks shape, source references,
file integrity and export approval; it neither judges success nor sends data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from capability_pipeline import canonical_json_bytes, sha256_payload
from discovery_pack import verify_developer_pack
from teaching_checkpoint import read_checkpoint

__all__ = ["prepare_request", "export_request", "verify_archive", "main"]
LOG = logging.getLogger(__name__)
SCHEMA = "browser-development-request/v1"
MAX_BYTES = 32 * 1024 * 1024
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
TEXT_KEYS = {"request_id", "title", "process", "objective", "source_version"}
LIST_KEYS = {"requested_work", "acceptance_checks", "gaps", "known_limits"}


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 6000


def _validate(payload: Any) -> None:
    if not isinstance(payload, dict) or set(payload) != TEXT_KEYS | LIST_KEYS | {
        "schema_version",
        "findings",
    }:
        raise ValueError("invalid development request fields")
    if payload["schema_version"] != SCHEMA or not all(
        _text(payload[k]) for k in TEXT_KEYS
    ):
        raise ValueError("request identity and purpose are required")
    if not SLUG.fullmatch(payload["request_id"]):
        raise ValueError("request_id must be a local slug, not an invented CR number")
    for key in LIST_KEYS:
        values = payload[key]
        if (
            not isinstance(values, list)
            or len(values) > 100
            or not all(_text(v) for v in values)
        ):
            raise ValueError("request lists must contain bounded text")
    if not payload["requested_work"] or not payload["acceptance_checks"]:
        raise ValueError("requested work and concrete acceptance checks are required")
    findings = payload["findings"]
    if not isinstance(findings, list) or len(findings) > 100:
        raise ValueError("findings must be a bounded array")
    for finding in findings:
        if (
            not isinstance(finding, dict)
            or set(finding) != {"summary", "basis", "step_ids"}
            or not _text(finding["summary"])
        ):
            raise ValueError("invalid finding")
        if finding["basis"] not in {"observed", "operator_report", "unknown"}:
            raise ValueError("findings must distinguish observation from reports")
        refs = finding["step_ids"]
        if not isinstance(refs, list) or not all(_text(r) for r in refs):
            raise ValueError("invalid step references")
        if finding["basis"] == "observed" and not refs:
            raise ValueError(
                "observed findings require saved checkpoint step references"
            )


def _read_file(path: Path) -> bytes:
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ValueError("only regular files without symlink ancestry are allowed")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("file exceeds handoff size limit")
    return path.read_bytes()


def _safe_name(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        name not in {"", "."}
        and "\\" not in name
        and ":" not in name
        and not path.is_absolute()
        and ".." not in path.parts
        and path.as_posix() == name
    )


def _validate_manifest(manifest: Any) -> None:
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version",
        "request_id",
        "files",
    }:
        raise ValueError("invalid review manifest")
    files = manifest["files"]
    if (
        manifest["schema_version"] != SCHEMA
        or not isinstance(manifest["request_id"], str)
        or not SLUG.fullmatch(manifest["request_id"])
    ):
        raise ValueError("invalid review identity")
    if not isinstance(files, dict) or not {
        "request.json",
        "sources.json",
        "RICHIESTA.md",
    } <= set(files):
        raise ValueError("required review files are missing")
    if {"review-manifest.json", "transfer-approval.json"} & set(files):
        raise ValueError("reserved review file names")
    if any(
        not _safe_name(n)
        or not isinstance(d, str)
        or not re.fullmatch(r"[a-f0-9]{64}", d)
        for n, d in files.items()
    ):
        raise ValueError("invalid review file hash or path")


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)


def prepare_request(
    payload: dict[str, Any],
    directory: Path,
    *,
    checkpoint: Path | None = None,
    developer_pack: Path | None = None,
) -> dict[str, Any]:
    """Prepare local files only. No raw checkpoint or business review is copied."""
    _validate(payload)
    if len(canonical_json_bytes(payload)) > 48 * 1024:
        raise ValueError("structured request exceeds the CR text limit")
    sources: dict[str, Any] = {"checkpoint": None, "developer_pack_attached": False}
    steps: dict[str, Any] = {}
    if checkpoint is not None:
        record = read_checkpoint(checkpoint)
        sources["checkpoint"] = {
            "revision": record["revision"],
            "sha256": record["sha256"],
        }
        steps = {s["id"]: s for s in record["payload"]["steps"]}
    for finding in payload["findings"]:
        if any(ref not in steps for ref in finding["step_ids"]):
            raise ValueError("finding references an unavailable checkpoint step")
        if finding["basis"] == "observed" and any(
            steps[r]["evidence_basis"] != "observed" for r in finding["step_ids"]
        ):
            raise ValueError("operator reports cannot be promoted to observed evidence")
    # Export only a bounded evidence projection for referenced steps; the model
    # supplies sanitized meanings in findings, so original private text stays out.
    selected = sorted({r for f in payload["findings"] for r in f["step_ids"]})
    sources["step_evidence"] = [
        {"id": r, "basis": steps[r]["evidence_basis"], "capture": steps[r]["capture"]}
        for r in selected
    ]
    files = {
        "request.json": canonical_json_bytes(payload),
        "sources.json": canonical_json_bytes(sources),
    }
    if developer_pack is not None:
        errors = verify_developer_pack(developer_pack)
        if errors:
            raise ValueError("developer pack integrity or lineage validation failed")
        evidence = json.loads(_read_file(developer_pack / "discovery-evidence.json"))
        if (
            evidence["review"]["operator_reviewed"] is not True
            or evidence["review"]["approved_for_developer_transfer"] is not True
        ):
            raise ValueError("developer pack needs actual operator transfer approval")
        lock = json.loads(_read_file(developer_pack / "developer-pack.lock.json"))
        for name in [*lock["files"], "developer-pack.lock.json"]:
            if not _safe_name(name):
                raise ValueError("unsafe developer pack path")
            content = _read_file(developer_pack / name)
            if (
                name in lock["files"]
                and hashlib.sha256(content).hexdigest() != lock["files"][name]
            ):
                raise ValueError("developer pack changed while preparing")
            files["developer-pack/" + name] = content
        sources["developer_pack_attached"] = True
        files["sources.json"] = canonical_json_bytes(sources)
    labels = {
        "observed": "Osservato",
        "operator_report": "Riferito dall’operatore",
        "unknown": "Da verificare",
    }
    lines = [
        f"# {payload['title']}",
        "",
        f"Processo: {payload['process']}",
        f"Versione osservata: {payload['source_version']}",
        "",
        "## Obiettivo",
        payload["objective"],
        "",
        "## Risultati e loro evidenza",
    ]
    lines += [
        f"- {labels[f['basis']]}: {f['summary']}" for f in payload["findings"]
    ] or ["- Nessun risultato documentato."]
    for key, label in [
        ("requested_work", "Lavoro richiesto"),
        ("acceptance_checks", "Come verificheremo il risultato"),
        ("gaps", "Informazioni mancanti"),
        ("known_limits", "Limiti noti"),
    ]:
        lines += ["", "## " + label] + (
            [f"- {v}" for v in payload[key]] or ["- Nessuno indicato."]
        )
    lines += [
        "",
        "## Materiale per lo sviluppo",
        (
            "Developer pack revisionato allegato."
            if developer_pack
            else "Developer pack tecnico non disponibile: questa richiesta conserva il materiale utile senza inventare una capability o una validazione."
        ),
        "",
        "Questa è una richiesta locale, non un CR già trasmesso. Non autorizza esecuzione o pubblicazione. Il significato e la riservatezza dei contenuti devono essere verificati dal modello e dall’operatore; gli hash provano soltanto integrità.",
        "",
        "## File da rivedere prima dell’esportazione",
    ]
    lines += ["- " + name for name in sorted(files)]
    files["RICHIESTA.md"] = ("\n".join(lines) + "\n").encode()
    if sum(map(len, files.values())) > MAX_BYTES:
        raise ValueError("handoff exceeds size limit")
    manifest = {
        "schema_version": SCHEMA,
        "request_id": payload["request_id"],
        "files": {
            name: hashlib.sha256(data).hexdigest()
            for name, data in sorted(files.items())
        },
    }
    if any(p.is_symlink() for p in (directory, *directory.parents)):
        raise ValueError("output directory must not use symlinks")
    directory.mkdir(mode=0o700)
    for name, data in files.items():
        _write(directory / name, data)
    _write(directory / "review-manifest.json", canonical_json_bytes(manifest))
    return {
        "review_path": str(directory / "RICHIESTA.md"),
        "review_sha256": sha256_payload(manifest),
        "status": "awaiting_operator_review",
        "archive_created": False,
    }


def export_request(
    directory: Path, output: Path, *, expected_sha256: str, approval_id: str
) -> Path:
    """Export only exact reviewed files after explicit approval of their content."""
    if not _text(approval_id):
        raise ValueError("explicit operator approval reference required")
    manifest_bytes = _read_file(directory / "review-manifest.json")
    manifest = json.loads(manifest_bytes)
    if sha256_payload(manifest) != expected_sha256:
        raise ValueError("review changed; review the current files again")
    _validate_manifest(manifest)
    files = {}
    for name, digest in manifest["files"].items():
        if not _safe_name(name):
            raise ValueError("unsafe review file path")
        data = _read_file(directory / name)
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("review file changed; prepare and review a new request")
        files[name] = data
    actual = {
        p.relative_to(directory).as_posix()
        for p in directory.rglob("*")
        if p.is_file() or p.is_symlink()
    }
    if actual != set(files) | {"review-manifest.json"}:
        raise ValueError("review contains unlisted files")
    if sum(map(len, files.values())) > MAX_BYTES:
        raise ValueError("handoff exceeds size limit")
    request = json.loads(files["request.json"])
    _validate(request)
    if request["request_id"] != manifest["request_id"]:
        raise ValueError("request identity mismatch")
    files["review-manifest.json"] = manifest_bytes
    files["transfer-approval.json"] = canonical_json_bytes(
        {
            "review_sha256": expected_sha256,
            "approval_id": approval_id,
            "scope": "export_only_not_sent",
        }
    )
    if sum(map(len, files.values())) > MAX_BYTES:
        raise ValueError("archive exceeds size limit")
    if output.suffix.lower() != ".zip" or any(
        p.is_symlink() for p in (output, *output.parents)
    ):
        raise ValueError("output must be a new ZIP without symlinks")
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with (
        os.fdopen(fd, "wb") as stream,
        ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive,
    ):
        for name, data in files.items():
            archive.writestr(name, data)
    verify_archive(output)
    return output


def verify_archive(path: Path) -> dict[str, Any]:
    """Check exact names, bounded sizes and bytes without extracting any files."""
    _read_file(path)
    with ZipFile(path) as archive:
        entries = archive.infolist()
        names = [e.filename for e in entries]
        if (
            len(names) != len(set(names))
            or any(not _safe_name(n) for n in names)
            or sum(e.file_size for e in entries) > MAX_BYTES
            or any(stat.S_ISLNK(e.external_attr >> 16) for e in entries)
        ):
            raise ValueError("unsafe archive entries or size")
        manifest = json.loads(archive.read("review-manifest.json"))
        _validate_manifest(manifest)
        approval = json.loads(archive.read("transfer-approval.json"))
        if not isinstance(approval, dict) or set(approval) != {
            "review_sha256",
            "approval_id",
            "scope",
        }:
            raise ValueError("invalid archive approval")
        if (
            approval["review_sha256"] != sha256_payload(manifest)
            or not _text(approval["approval_id"])
            or approval["scope"] != "export_only_not_sent"
        ):
            raise ValueError("archive approval mismatch")
        if set(names) != set(manifest["files"]) | {
            "review-manifest.json",
            "transfer-approval.json",
        }:
            raise ValueError("archive contains unlisted or missing files")
        for name, digest in manifest["files"].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError("archive file hash mismatch")
        request = json.loads(archive.read("request.json"))
        _validate(request)
        if request["request_id"] != manifest["request_id"]:
            raise ValueError("request identity mismatch")
    return {
        "request_id": manifest["request_id"],
        "integrity_verified": True,
        "sent": False,
        "cr_id": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    prepare = subs.add_parser("prepare")
    prepare.add_argument("--input", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--checkpoint", type=Path)
    prepare.add_argument("--developer-pack", type=Path)
    export = subs.add_parser("export")
    export.add_argument("directory", type=Path)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--review-sha256", required=True)
    export.add_argument("--approval-id", required=True)
    verify = subs.add_parser("verify")
    verify.add_argument("archive", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result: Any = prepare_request(
                json.loads(_read_file(args.input)),
                args.output,
                checkpoint=args.checkpoint,
                developer_pack=args.developer_pack,
            )
        elif args.command == "export":
            result = str(
                export_request(
                    args.directory,
                    args.output,
                    expected_sha256=args.review_sha256,
                    approval_id=args.approval_id,
                )
            )
        else:
            result = verify_archive(args.archive)
        LOG.info("%s", json.dumps(result, ensure_ascii=False))
    except (ValueError, OSError, KeyError, BadZipFile) as exc:
        LOG.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
