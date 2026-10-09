"""Fixed local Patent Box producer calls; no model, signing or source discovery."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

__all__ = ["main"]

LIMIT = 2_000_000
OPERATIONS = {
    "initialize": {"as_of", "demo"},
    "import_ledger": {"evidence_id"},
    "inspect_ledger": {"evidence_id", "options"},
    "normalize_ledger": {"plan"},
    "propose": {"proposal"},
    "review": {"digest", "reviewer", "confirmation_ref", "synthetic"},
    "calculate": {"digest"},
    "prepare_professional_review": {
        "digest",
        "source_scan_ref",
        "action",
        "previous_digest",
        "reason",
    },
    "accept_professional_review": {
        "digest",
        "request_digest",
        "signature_ref",
        "mandate_ref",
        "mandate_signature_ref",
    },
    "verify_formalities": {"plan", "trust_basis"},
}


def file_hash(path: Path) -> str:
    """Exact bytes, single-link files and fixed paths provide mechanical confinement."""
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("Patent Box requires regular single-link files")
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def files(output: Path) -> dict[str, str]:
    """Bind all outputs; private interaction state is outside this directory."""
    if any(parent.is_symlink() for parent in (output, *output.parents)):
        raise ValueError("Linked Patent Box output directory")
    result = {}
    for path in sorted(output.rglob("*")):
        if path.is_symlink():
            raise ValueError("Linked Patent Box output")
        if not path.is_dir():
            result[path.relative_to(output).as_posix()] = file_hash(path)
    return result


def bounded(value: Any) -> str:
    """Refuse oversized complete payloads; never silently sample a proposal."""
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if len(raw.encode("utf-8")) > LIMIT:
        raise ValueError("Patent Box native payload exceeds complete-record limit")
    return raw


def read(path: Path) -> dict:
    file_hash(path)
    if path.stat().st_size > LIMIT:
        raise ValueError("Patent Box record exceeds complete-record limit")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("Patent Box record must be an object")
    return value


def implementation(root: Path) -> dict:
    """Pin maintained code, contracts, configuration and shared context validation."""
    directories = [
        root / name for name in ("scripts", "patent_box", "schemas", "config")
    ]
    directories += [
        path / "vera_assurance"
        for path in (
            root / "vendor/modules",
            root.parent.parent / "vendor/modules",
            root.parent / "_shared/vendor/modules",
        )
        if (path / "vera_assurance").is_dir()
    ][:1]
    return {
        f"{index}/{path.relative_to(directory).as_posix()}": file_hash(path)
        for index, directory in enumerate(directories)
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.suffix in {".py", ".json"}
    }


def selected_path(
    output: Path, reference: Any, population: dict, *, directory=False
) -> Path:
    """Resolve an explicit existing run artifact, never a caller's external path."""
    if not isinstance(reference, str) or not reference:
        raise ValueError("Select an existing Patent Box artifact")
    relative = Path(reference)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or relative.as_posix() != reference
    ):
        raise PermissionError("Patent Box artifact reference leaves this run")
    path = output / relative
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise PermissionError("Linked Patent Box artifact reference")
    if directory:
        if not path.is_dir() or not any(
            name.startswith(reference + "/") for name in population
        ):
            raise ValueError("Select an existing source-scan directory")
    elif reference not in population or file_hash(path) != population[reference]:
        raise ValueError("Selected Patent Box artifact changed")
    return path


def public_view(context: dict, output: Path, population: dict, workflow: Any) -> dict:
    """Read exact session and version identities without asserting professional validity."""
    session = None
    if "patent_box_session.json" in population:
        session = read(output / "patent_box_session.json")
        if (
            session["run_id"] != context["run_id"]
            or session["workflow"] != "patent-box-review"
        ):
            raise PermissionError("Patent Box session belongs to another run")
        bindings = {
            str(Path(row["path"]).resolve()): row for row in context["input_bindings"]
        }
        seen = set()
        for row in session["inputs"]:
            source = Path(row["selected_path"])
            reference = row["path"]
            snapshot = selected_path(output, reference, population)
            if (
                str(source.resolve()) not in bindings
                or file_hash(source) != row["sha256"]
                or file_hash(snapshot) != row["sha256"]
                or row["evidence_id"] in seen
            ):
                raise ValueError("Patent Box selected evidence changed")
            seen.add(row["evidence_id"])
        if len(session["inputs"]) != len(bindings):
            raise ValueError("Patent Box session does not retain every selected input")
    elif population:
        raise ValueError(
            "Patent Box output has no complete session; ordinary recovery required"
        )
    proposals = []
    for name in population:
        if "/" not in name and name.startswith("proposal_") and name.endswith(".json"):
            digest = name[len("proposal_") : -len(".json")]
            proposal = read(output / name)
            if (
                workflow.canonical_hash(proposal) != digest
                or not session
                or proposal["case"]["case_id"] != session["run_id"]
            ):
                raise ValueError("Patent Box proposal version changed")
            proposals.append(
                {
                    "digest": digest,
                    "claim_period_id": proposal["case"]["claim_period_id"],
                    "demo": proposal["case"]["demo"],
                    "rules_status": proposal["rules"]["status"],
                    "local_decision_present": f"decision_{digest}.json" in population,
                    "authenticated_decision_present": f"authenticated_decision_{digest}.json"
                    in population,
                    "calculation_present": f"calculation_{digest}/result.json"
                    in population,
                    "professional_verification_performed": False,
                }
            )
    return {"session": session, "proposals": proposals, "files": population}


def invoke(
    action: str,
    fields: dict,
    context_path: Path,
    output: Path,
    population: dict,
    workflow: Any,
) -> Any:
    """Delegate semantic contracts, arithmetic and authentication to unchanged producers."""
    if action == "initialize":
        if type(fields["demo"]) is not bool:
            raise ValueError("Choose the actual synthetic/real case status")
        return workflow.initialize(
            context_path, as_of=fields["as_of"], demo=fields["demo"]
        )
    if action == "import_ledger":
        return workflow.import_ledger(context_path, evidence_id=fields["evidence_id"])
    if action == "inspect_ledger":
        return workflow.inspect_ledger(
            context_path, evidence_id=fields["evidence_id"], options=fields["options"]
        )
    if action == "normalize_ledger":
        return workflow.normalize_ledger(context_path, fields["plan"])
    if action == "propose":
        return workflow.propose(context_path, fields["proposal"])
    if action == "review":
        if type(fields["synthetic"]) is not bool:
            raise ValueError("Choose the actual review synthetic status")
        return workflow.review(context_path, confirmed=True, **fields)
    if action == "calculate":
        return workflow.calculate_draft(context_path, digest=fields["digest"])
    if action == "prepare_professional_review":
        scan = selected_path(
            output, fields["source_scan_ref"], population, directory=True
        )
        return workflow.prepare_professional_review(
            context_path,
            digest=fields["digest"],
            source_scan=scan,
            action=fields["action"],
            previous_digest=fields["previous_digest"],
            reason=fields["reason"],
        )
    if action == "accept_professional_review":
        return workflow.accept_professional_review(
            context_path,
            digest=fields["digest"],
            request_digest=fields["request_digest"],
            signature=selected_path(output, fields["signature_ref"], population),
            mandate=selected_path(output, fields["mandate_ref"], population),
            mandate_signature=selected_path(
                output, fields["mandate_signature_ref"], population
            ),
        )
    if action == "verify_formalities":
        # The existing administrator configuration remains the sole trust/executable source.
        config = workflow.professional_review._configuration(output)
        return workflow.verify_formalities(
            context_path,
            fields["plan"],
            openssl=config["openssl"],
            trusted_roots=config["trusted_roots"],
            crls=config["crls"],
            trust_basis=fields["trust_basis"],
        )
    raise ValueError("Unsupported Patent Box action")


def main() -> None:
    """Return verified unchanged refusals separately from uncertain partial writes."""
    root = Path(sys.argv[1]).resolve()
    if root.name != "patent-box-review":
        raise PermissionError("Unsupported Patent Box component")
    raw = sys.stdin.read(LIMIT + 1)
    if len(raw.encode("utf-8")) > LIMIT:
        raise ValueError("Patent Box request exceeds complete-record limit")
    request = json.loads(raw)
    if request["operation"] == "implementation":
        sys.stdout.write(bounded(implementation(root)))
        return
    sys.path.insert(0, str(root / "scripts"))
    import patent_box_workflow as workflow

    context_path = Path(request["context"])
    context = workflow.load_client_engagement_context_file(
        context_path,
        expected_workflow_id="patent-box-review",
        allowed_statuses=(
            ("running", "ready_for_review", "completed")
            if request["operation"] == "read"
            else ("running",)
        ),
    )
    output = Path(context["output_dir"])
    before = files(output)
    if request["operation"] == "read":
        result = public_view(context, output, before, workflow)
        if files(output) != before:
            raise ValueError("Patent Box artifacts changed while reading")
    else:
        action = request["operation"]
        fields = request["fields"]
        if (
            action not in OPERATIONS
            or not isinstance(fields, dict)
            or set(fields) != OPERATIONS[action]
        ):
            raise ValueError("Unexpected Patent Box operation fields")
        if before != request["expected_files"]:
            raise ValueError("Patent Box run or output changed before producer call")
        try:
            value = invoke(action, fields, context_path, output, before, workflow)
        except (ValueError, PermissionError, OSError) as error:
            after = files(output)
            result = {
                "status": "refused" if before == after else "uncertain",
                "error": f"{type(error).__name__}: {error}",
                "files": after,
            }
        else:
            after = files(output)
            if any(after.get(name) != sha for name, sha in before.items()):
                raise ValueError(
                    "Patent Box producer changed prior bytes; ordinary recovery required"
                )
            result = {"status": "complete", "public_result": value, "files": after}
    sys.stdout.write(bounded(result))


if __name__ == "__main__":
    main()
