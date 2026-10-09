"""Fixed calls and independent exports over the unchanged merger CaseStore."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Preserve company grants, exact references and actual professional decisions."""
    request = json.loads(sys.stdin.read(2_000_001))
    module, root = Path(request["module"]), Path(request["workspace"])
    if module.name != "fusione-guidata":
        raise PermissionError("Unsupported merger producer")
    sys.path.insert(0, str(Path(__file__).parent))
    from native_transformation import bounded, files, regular

    sys.path.insert(0, str(module / "scripts"))
    import fusione_case
    import fusione_report
    import run_fusione
    from fusione_archive import ledger
    from fusione_case import CaseStore, reference

    store = CaseStore(root, request["case_actor"])
    if store.metadata["operation_id"] != request["operation_id"]:
        raise PermissionError("Merger operation identity changed")
    action = request["action"]

    def apply(case_root: Path, proposal: Path) -> dict:
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            code = run_fusione.main(
                [
                    "apply",
                    "--case",
                    str(case_root),
                    "--actor",
                    store.actor,
                    "--request",
                    str(proposal),
                ]
            )
        if code:
            raise ValueError("Public merger proposal refused")
        return json.loads(captured.getvalue())

    def backup(destination: Path) -> None:
        regular(store.path)
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if destination.exists():
            raise ValueError("Merger snapshot already exists")
        with sqlite3.connect(store.path.as_uri() + "?mode=ro", uri=True) as source:
            with sqlite3.connect(destination) as target:
                source.backup(target)
        destination.chmod(0o600)

    if action == "snapshot":
        report = store.report()
        report.pop("generated_at")
        # Own declared grant only. The public store enforces every actual read/write.
        with store._connect() as db:
            grant = store._grant(db)
        helper = fusione_report._report_builder()
        result = {
            "report": report,
            "grant": grant,
            "shared_implementation": {
                "model_data_report.py": hashlib.sha256(
                    Path(helper.__globals__["__file__"]).read_bytes()
                ).hexdigest(),
                "client_ledger.py": hashlib.sha256(
                    Path(ledger().__file__).read_bytes()
                ).hexdigest(),
            },
        }
    elif action == "verify_export":
        receipt = request["receipt"]
        directory = Path(receipt["directory"])
        case_report = json.loads((directory / "case-report.json").read_bytes())
        model_report = json.loads((directory / "model_data_report.json").read_bytes())
        # A historical snapshot never restores a revoked company permission.
        for record in case_report["history"]:
            if store.read(record["id"], record["version"]) != record:
                raise ValueError(
                    "Merger export history differs from authoritative records"
                )
            if record["kind"] in {"Evidence", "Artifact"}:
                store.document_bytes(record["id"], record["version"])
        baseline = Path(receipt["baseline"])
        regular(baseline)
        if (
            hashlib.sha256(baseline.read_bytes()).hexdigest()
            != receipt["baseline_sha256"]
        ):
            raise ValueError("Merger export baseline changed")
        with tempfile.TemporaryDirectory(prefix="vera-fusion-export-replay-") as name:
            temporary = Path(name).resolve()
            replay_root = temporary / "case"
            replay_root.mkdir()
            (replay_root / "case.sqlite").write_bytes(baseline.read_bytes())
            replay = CaseStore(replay_root, store.actor)
            if replay.metadata["operation_id"] != store.metadata["operation_id"]:
                raise ValueError("Merger export belongs to another operation")
            # Freeze only recorded export clocks in this isolated verifier. No live
            # producer, stored history or professional timestamp is changed.
            fusione_case.now = lambda: case_report["generated_at"]
            fusione_report.now = lambda: model_report["created_at"]
            target = temporary / "reproduced"
            fusione_report.export_report(replay, target, runtime_profile="openai-codex")
            if set(files(target)) != set(receipt["artifacts"]):
                raise ValueError("Merger export artifact population changed")
            for filename in receipt["artifacts"]:
                if (target / filename).read_bytes() != (
                    directory / filename
                ).read_bytes():
                    raise ValueError(
                        "Merger export differs from unchanged public replay"
                    )
        result = {
            "verified": True,
            "case_report": case_report,
            "model_report": model_report,
            # Exact saved artifact, already compared with the canonical public
            # formatter above. Reading adds no phase, receipt or provider claim.
            "model_report_markdown": (directory / "model_data_report.md").read_text(
                encoding="utf-8"
            ),
        }
    elif action == "document":
        record = store.read(request["object_id"], request["version"])
        if record["sha256"] != request["record_sha256"]:
            raise ValueError("Merger document reference changed")
        import base64

        data = store.document_bytes(record["id"], record["version"])
        if len(data) > 1_000_000:
            raise ValueError("Merger document exceeds native download limit")
        result = {
            "name": record["data"]["filename"],
            "base64": base64.b64encode(data).decode(),
            "sha256": record["data"]["sha256"],
            "mime_type": "application/octet-stream",
        }
    else:
        if files(root) != request["expected_files"]:
            raise ValueError("Merger changed before public execution")
        if action == "preview_proposal":
            with tempfile.TemporaryDirectory(prefix="vera-fusion-proposal-") as name:
                clone = Path(name).resolve() / "case"
                clone.mkdir()
                backup(clone / "case.sqlite")
                record = apply(clone, Path(request["proposal"]))
                status = CaseStore(clone, store.actor).status(record["id"])
            result = {"proposed_record": record, "status": status, "preview_only": True}
        elif action == "apply_proposal":
            record = apply(root, Path(request["proposal"]))
            result = {
                "record": record,
                "status": store.status(record["id"]),
                "professional_approval_added": False,
            }
        elif action == "approve":
            fields = request["fields"]
            record = store.read(fields["target_id"])
            if reference(record) != request["target"]:
                raise ValueError("Merger approval target changed")
            decision = store.approve(
                fields["decision_id"],
                reference(record),
                professional_role=fields["professional_role"],
                scope_text=fields["scope_text"],
                confirmation=fields["confirmation"],
            )
            result = {
                "decision": decision,
                "status": store.status(record["id"]),
                "authenticated_signature": False,
            }
        elif action == "export":
            baseline = Path(request["baseline"])
            backup(baseline)
            destination = Path(request["destination"])
            destination.parent.mkdir(mode=0o700, exist_ok=True)
            declared = fusione_report.export_report(
                store, destination, runtime_profile="openai-codex"
            )
            result = {
                "directory": str(destination),
                "baseline": str(baseline),
                "baseline_sha256": hashlib.sha256(baseline.read_bytes()).hexdigest(),
                "artifacts": files(destination),
                "declared_outputs": declared,
            }
        else:
            raise ValueError("Unknown native merger operation")
    sys.stdout.write(bounded(result))


if __name__ == "__main__":
    main()
