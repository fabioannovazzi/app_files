"""Isolated replay of the maintained evaluator against exact retained review bytes."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Evaluate or verify an owned immutable label version, without any worker."""
    root = Path(sys.argv[1])
    if root.name != "passive-invoice-audit" or root.is_symlink():
        raise PermissionError("Unsupported label evaluator")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(root / "scripts"))
    for vendor in (
        root / "vendor/modules",
        root.parent / "_shared/vendor/modules",
        root.parent.parent / "vendor/modules",
    ):
        if (vendor / "vera_assurance").is_dir():
            sys.path.insert(0, str(vendor))
            break
    import audit_core as producer
    from native_passive_audit import ordinary
    from vera_assurance import load_client_engagement_context_file

    request = json.loads(sys.stdin.read(20_001))
    if (
        set(request) != {"context", "review_ref", "operation"}
        or request["operation"] not in {"evaluate", "verify"}
        or not re.fullmatch(r"[0-9a-f]{64}", request["review_ref"])
    ):
        raise ValueError("Invalid exact review-evaluation request")
    context = load_client_engagement_context_file(
        Path(request["context"]),
        expected_workflow_id="passive-invoice-audit",
        allowed_statuses=("running", "ready_for_review", "completed"),
    )
    output = Path(context["output_dir"])
    folder = output / "professional_reviews" / request["review_ref"]
    record_bytes = ordinary(folder / "review.json", 100_000)
    record = json.loads(record_bytes)
    if hashlib.sha256(
        json.dumps(record, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest() != request["review_ref"] or record["run_scope"] != [
        context[key] for key in ("client_id", "engagement_id", "run_id")
    ]:
        raise ValueError("Professional review identity or run changed")
    if not re.fullmatch(r"[0-9a-f]{64}", record["population_sha256"]):
        raise ValueError("Invalid retained population reference")
    population = (
        output
        / "professional_review_populations"
        / (record["population_sha256"] + ".jsonl")
    )
    labels = folder / "labels.jsonl"
    for path, expected in (
        (population, record["population_sha256"]),
        (labels, record["labels_sha256"]),
    ):
        if hashlib.sha256(ordinary(path)).hexdigest() != expected:
            raise ValueError("Retained population or human labels changed")
    report = folder / "evaluation.json"
    if request["operation"] == "evaluate":
        if (
            json.loads(ordinary(Path(context["run_manifest_path"])))["status"]
            != "running"
            or report.exists()
        ):
            raise PermissionError("Evaluation requires a new owned running-run version")
        producer.evaluate_results(population, labels, report)
    actual = json.loads(ordinary(report))
    replay = producer.evaluate_results(population, labels)
    if {key: value for key, value in actual.items() if key != "evaluated_at"} != {
        key: value for key, value in replay.items() if key != "evaluated_at"
    }:
        raise ValueError(
            "Professional evaluation does not replay through public producer"
        )
    if ordinary(
        folder / "review.json", 100_000
    ) != record_bytes or context != load_client_engagement_context_file(
        Path(request["context"]),
        expected_workflow_id="passive-invoice-audit",
        allowed_statuses=("running", "ready_for_review", "completed"),
    ):
        raise ValueError("Review or source context changed during evaluation")
    sys.stdout.write(
        json.dumps(
            {
                "review_ref": request["review_ref"],
                "evaluation_sha256": hashlib.sha256(ordinary(report)).hexdigest(),
                "professional_approval": False,
            }
        )
    )


if __name__ == "__main__":
    main()
