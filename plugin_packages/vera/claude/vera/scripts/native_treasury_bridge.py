"""Isolated native intake over the unchanged public Treasury producer."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Reuse public parsing and cent-exact calculation; never infer table roles."""
    root = Path(sys.argv[1])
    sys.path.insert(0, str(root / "scripts"))
    import run_treasury
    from treasury_core import TreasuryError, build_forecast
    from treasury_inputs import HEADERS, load_inputs, manifest_paths
    from treasury_session import current_record

    request = json.loads(sys.stdin.read(128001))
    if request["operation"] == "contract":
        result = {
            "headers": HEADERS,
            "implementation": {
                name: hashlib.sha256((root / "scripts" / name).read_bytes()).hexdigest()
                for name in (
                    "run_treasury.py",
                    "treasury_inputs.py",
                    "treasury_core.py",
                    "treasury_session.py",
                    "treasury_report.py",
                )
            },
        }
    elif request["operation"] == "inspect":
        from vera_assurance import load_client_engagement_context_file

        context = load_client_engagement_context_file(
            Path(request["context"]), expected_workflow_id="treasury-forecast"
        )
        if context["schema_version"] != "vera.client_workflow_context.v2":
            raise ValueError("Treasury requires a portable v2 client workflow")
        inputs = Path(context["run_root"]) / "inputs"
        try:
            manifest = request["manifest"]
            paths = manifest_paths(manifest, inputs)
            run_treasury.validate_context(Path(request["context"]), paths)
            data, previous = load_inputs(
                manifest,
                inputs,
                client_id=context["client_id"],
                engagement_id=context["engagement_id"],
            )
            # Public build_forecast enforces accounting/predecessor correctness;
            # incomplete dates remain explicit, without manufacturing acceptance.
            record = build_forecast(data, previous=previous)
        except TreasuryError as exc:
            result = {"ok": False, "error": str(exc)}
        else:
            table = request.get("table")
            offset = request.get("offset", 0)
            result = {
                "ok": True,
                "status": record["status"],
                "calculation_complete": record["calculation_complete"],
                "opening_cash": record["opening_cash"],
                "tables": {name: len(data[name]) for name in HEADERS},
                "invoice_evidence_count": len(data["invoice_evidence"]),
                "previous": (
                    None
                    if previous is None
                    else {
                        key: previous[key]
                        for key in (
                            "record_sha256",
                            "company_name",
                            "currency",
                            "as_of",
                            "status",
                        )
                    }
                ),
                "table": table,
                "headers": HEADERS[table] if table else [],
                "rows": data[table][offset : offset + 20] if table else [],
                "total": len(data[table]) if table else 0,
                "has_more": bool(table and offset + 20 < len(data[table])),
            }
    elif request["operation"] == "read":
        try:
            _, record = current_record(Path(request["output"]))
        except (TreasuryError, OSError, ValueError, KeyError) as exc:
            result = {"ok": False, "error": str(exc)}
        else:
            result = {"ok": True, "status": record["status"]}
    elif request["operation"] == "prepare":
        status = run_treasury.main(
            [
                "prepare",
                "--client-engagement",
                request["context"],
                "--manifest",
                request["manifest_path"],
            ]
        )
        if status:
            raise ValueError(
                "Treasury preparation did not complete; retained outputs require specialist recovery"
            )
        _, record = current_record(Path(request["output"]))
        result = {
            key: record[key]
            for key in ("record_sha256", "status", "calculation_complete")
        }
    elif request["operation"] == "predecessor":
        from treasury_core import validate_record
        from treasury_inputs import read_json

        record = read_json(Path(request["path"]))
        validate_record(record, accepted=True)
        result = {
            key: record[key]
            for key in ("record_sha256", "company_name", "currency", "as_of", "status")
        }
    else:
        raise ValueError("Unknown Treasury intake operation")
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
