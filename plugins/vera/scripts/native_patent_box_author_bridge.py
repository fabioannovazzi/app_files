"""Read-only preflight against unchanged Patent Box proposal/normalization contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from native_patent_box_bridge import LIMIT, bounded, files  # noqa: E402  # isort: skip

__all__ = ["main"]


def main() -> None:
    """Mechanical schema/reference/arithmetic preflight does not decide fiscal meaning."""
    root = Path(sys.argv[1]).resolve()
    if root.name != "patent-box-review":
        raise PermissionError("Unsupported Patent Box component")
    raw = sys.stdin.read(LIMIT + 1)
    if len(raw.encode()) > LIMIT:
        raise ValueError("Whole Patent Box proposal exceeds native boundary")
    request = json.loads(raw)
    sys.path.insert(0, str(root / "scripts"))
    import patent_box_workflow as workflow

    # Reuse the exact helpers invoked by the maintained public producers.
    # No context replacement, monkeypatch, alternate validator or public write.
    _, output, session = workflow._bound(Path(request["context"]))
    before = files(output)
    if before != request["expected_files"]:
        raise ValueError("Patent Box outputs changed before preflight")
    body = request["body"]
    if request["task"] == "propose":
        checked = workflow._check_proposal(body, session)
        if "normalization_digest" in checked:
            record = workflow._normalization(
                output, session, checked["normalization_digest"]
            )
            workflow._bind_normalized_costs(checked, record)
            checked["normalization_record"] = record
        else:
            records = workflow.indexed(session["inputs"], "evidence_id")
            evidence = {row["evidence_id"] for row in checked["case"]["costs"]}
            if not evidence <= set(records):
                raise ValueError("Cost evidence is outside the selected run")
            expected = [
                row
                for identity in sorted(evidence)
                for row in workflow._ledger_rows(output, records[identity])
            ]
            if workflow.indexed(expected, "cost_id") != workflow.indexed(
                checked["case"]["costs"], "cost_id"
            ):
                raise ValueError("Cost population differs from selected mapped ledger")
        result = {
            "normalized_proposal": checked,
            "prospective_digest": workflow.canonical_hash(checked),
        }
    elif request["task"] == "normalize_ledger":
        workflow.validate(body, "ledger-normalization.schema.json")
        tables = [
            workflow._ledger_table(output, session, row["table_id"])
            for row in body["mappings"]
        ]
        result = {
            "normalization": workflow.normalize_population(
                tables, body, {row["evidence_id"] for row in session["inputs"]}
            )
        }
    else:
        raise ValueError("Unsupported specialist Patent Box task")
    if files(output) != before:
        raise ValueError("Read-only Patent Box preflight changed public bytes")
    sys.stdout.write(
        bounded(
            {
                **result,
                "public_outputs_written": False,
                "professional_acceptance": False,
            }
        )
    )


if __name__ == "__main__":
    main()
