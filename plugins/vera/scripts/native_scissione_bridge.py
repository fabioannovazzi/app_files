"""Isolated replay and professional review over the maintained Scissione producer."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Reproduce version lineage and exact authored reports; never select legal applicability."""
    root = Path(sys.argv[1])
    if root.name != "scissione-guidata":
        raise PermissionError("Unsupported Scissione producer")
    sys.path.insert(0, str(root / "scripts"))
    import run_scissione as producer
    from scissione_core import build_revision, digest
    from vera_assurance import load_client_engagement_context_file

    request = json.loads(sys.stdin.read(128001))
    if request["operation"] == "implementation":
        directories = [root / "scripts"]
        directories += [
            p
            for p in (
                root / "vendor/modules",
                root.parent.parent / "vendor/modules",
                root.parent / "_shared/vendor/modules",
            )
            if (p / "vera_assurance").is_dir()
        ][:1]
        result = {
            "sha256": digest(
                {
                    str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for d in directories
                    for p in sorted(d.rglob("*.py"))
                }
            )
        }
    else:
        context = load_client_engagement_context_file(
            Path(request["context"]),
            expected_workflow_id="scissione-guidata",
            allowed_statuses=("running", "ready_for_review", "completed"),
        )
        output = Path(context["output_dir"])
        seen = set()
        byte_count = 0

        def replay(identity: str) -> dict:
            nonlocal byte_count
            if identity in seen or len(seen) >= 100:
                raise ValueError(
                    "Scissione lineage is cyclic or exceeds the bounded native replay"
                )
            seen.add(identity)
            folder = output / "scissione_versions" / identity
            if folder.exists():
                value = producer.read_revision(output, identity)
                byte_count += len(json.dumps(value).encode())
            else:
                matches = [
                    row
                    for row in context["input_bindings"]
                    if row["kind"] == "upstream_artifact"
                    and row["upstream_workflow_id"] == "scissione-guidata"
                    and Path(row["path"]).suffix.lower() == ".json"
                ]
                matches = [
                    json.loads(Path(row["path"]).read_bytes()) for row in matches
                ]
                matches = [
                    row
                    for row in matches
                    if isinstance(row, dict) and row.get("revision_sha256") == identity
                ]
                if len(matches) != 1:
                    raise ValueError(
                        "Missing or ambiguous finalized upstream Scissione lineage"
                    )
                # The maintained archive validates the exact upstream receipt. Its historical
                # sources/implementation need not be available in this continuation run.
                value = matches[0]
                if (
                    digest({k: v for k, v in value.items() if k != "revision_sha256"})
                    != identity
                ):
                    raise ValueError("Upstream Scissione revision integrity changed")
                return value
            if byte_count > 40_000_000:
                raise ValueError("Scissione lineage exceeds native replay size")
            previous = (
                replay(value["previous_sha256"]) if value["previous_sha256"] else None
            )
            ids = [
                key
                for key, row in value["approvals"].items()
                if row["reviewed_revision"] == value["previous_sha256"]
            ]
            review = None
            if ids:
                fields = ("reviewer", "role", "reviewed_at", "rationale")
                first = value["approvals"][ids[0]]
                if any(
                    any(value["approvals"][key][f] != first[f] for f in fields)
                    for key in ids
                ):
                    raise ValueError("Scissione approval batch is inconsistent")
                review = {
                    "revision_sha256": value["previous_sha256"],
                    "record_ids": ids,
                    **{f: first[f] for f in fields},
                }
            if build_revision(value["case"], previous=previous, review=review) != value:
                raise ValueError(
                    "Scissione revision cannot be reproduced by the maintained engine"
                )
            # Verification deliberately calls the maintained private report formatter.
            # It is bound by the complete implementation hash, rather than duplicated.
            memo = producer._report(value)
            if (folder / "review.md").read_text() != memo:
                raise ValueError("Scissione memo differs from the maintained report")
            # Re-render HTML in an isolated temporary output with the maintained
            # formatter. Never reproduce its template or touch official versions.
            with tempfile.TemporaryDirectory(prefix="vera-scissione-replay-") as name:
                temporary = Path(name)
                producer._store(temporary, value)
                rendered = temporary / "scissione_versions" / identity / "review.html"
                if rendered.read_bytes() != (folder / "review.html").read_bytes():
                    raise ValueError(
                        "Scissione HTML differs from the maintained report"
                    )
            for filename, data in {
                "ownership_before_after.json": value["schedule"].get("owners", []),
                "allocations.json": value["schedule"].get("allocations", []),
                "change_impact.json": value["change_impact"],
            }.items():
                if json.loads((folder / filename).read_bytes()) != data:
                    raise ValueError(
                        "Scissione derived artifact differs from its revision"
                    )
            return value

        if request["operation"] in {"inspect_proposal", "save_proposal"}:
            proposal = producer._read(Path(request["request"]))
            previous = None
            command = "prepare"
            if "revision_sha256" in proposal:
                previous = replay(proposal["revision_sha256"])
                command = "revise"
            elif proposal.get("previous_revision_path") is not None:
                prior = producer._safe(
                    Path(context["run_root"]) / "inputs",
                    proposal["previous_revision_path"],
                )
                binding = next(
                    (
                        row
                        for row in context["input_bindings"]
                        if row["path"] == str(prior)
                    ),
                    None,
                )
                if (
                    binding is None
                    or binding["kind"] != "upstream_artifact"
                    or binding["upstream_workflow_id"] != "scissione-guidata"
                ):
                    raise PermissionError(
                        "Choose a sealed same-engagement Scissione predecessor"
                    )
                previous = producer._read(prior)
                if (
                    digest(
                        {k: v for k, v in previous.items() if k != "revision_sha256"}
                    )
                    != previous["revision_sha256"]
                ):
                    raise ValueError("Scissione predecessor changed")
            case = proposal["case"]
            producer.validate_case(case)
            inputs = Path(context["run_root"]) / "inputs"
            sources = [producer._safe(inputs, row["path"]) for row in case["evidence"]]
            load_client_engagement_context_file(
                Path(request["context"]),
                expected_workflow_id="scissione-guidata",
                input_paths=sources,
            )
            for row, path in zip(case["evidence"], sources, strict=True):
                if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
                    raise ValueError("Scissione original source changed")
            value = build_revision(case, previous=previous)
            if request["operation"] == "save_proposal":
                existing = (
                    producer.read_revision(output)
                    if (output / "scissione_current.json").exists()
                    else None
                )
                if (existing is not None) != (command == "revise") or (
                    existing is not None
                    and existing["revision_sha256"] != proposal["revision_sha256"]
                ):
                    raise ValueError(
                        "Scissione current pointer changed before conservation"
                    )
                path = output / (
                    "scissione-native-proposal-" + value["revision_sha256"] + ".json"
                )
                producer._write(path, proposal)
                produced = producer.execute(Path(request["context"]), command, path)
                if produced != value:
                    raise ValueError(
                        "Scissione conservation differs from preview; recovery required"
                    )
            result = {"record": value, "memo": producer._report(value)}
        else:
            value = replay(request["revision"])
        if request["operation"] in {"inspect_proposal", "save_proposal"}:
            pass
        elif request["operation"] == "read":
            result = value
        elif request["operation"] == "validate":
            review = json.loads(Path(request["request"]).read_bytes())
            candidate = build_revision(value["case"], previous=value, review=review)
            result = {"revision_sha256": candidate["revision_sha256"]}
        elif request["operation"] == "review":
            candidate = producer.execute(
                Path(request["context"]), "review", Path(request["request"])
            )
            result = {"revision_sha256": candidate["revision_sha256"]}
        else:
            raise ValueError("Unknown Scissione native operation")
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
