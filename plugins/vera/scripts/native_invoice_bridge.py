"""Isolated replay, preparation and exact approved export of maintained invoices."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

__all__ = ["main"]


def preview_content(payload: bytes) -> bytes:
    """Normalize only two public presentation orders lost by sorted JSON persistence.

    Exact escaped public rows/decision pairs and every other byte must remain
    unchanged. No HTML parsing, field judgment or arbitrary markup adoption.
    """
    text = payload.decode("utf-8")
    for begin, end, pattern in (
        (
            "<summary>Esamina tutti i campi e le relative fonti</summary><table><thead><tr><th>Campo</th><th>Valore proposto</th><th>Fonte e interpretazione</th></tr></thead><tbody>",
            "</tbody></table></details></section>",
            r"<tr><th scope='row'>.*?</tr>",
        ),
        (
            "<section><h2>Decisioni da rivedere</h2><dl>",
            "</dl></section>",
            r"<dt>.*?</dt><dd>.*?</dd>",
        ),
    ):
        if text.count(begin) != 1:
            raise ValueError("Unknown invoice preview structure")
        start = text.index(begin) + len(begin)
        stop = text.index(end, start)
        content = text[start:stop]
        rows = re.findall(pattern, content, flags=re.DOTALL)
        if "".join(rows) != content:
            raise ValueError("Unknown invoice preview content")
        text = text[:start] + "".join(sorted(rows)) + text[stop:]
    return text.encode("utf-8")


def main() -> None:
    """Use the public producer and offline XSD; make no extraction or tax decision."""
    root = Path(sys.argv[1])
    if root.name != "invoice-xml":
        raise PermissionError("Unsupported invoice producer")
    sys.path.insert(0, str(root / "scripts"))
    import invoice_workflow as producer
    from invoice_schema import flatten_fields

    for vendor in (
        root / "vendor/modules",
        root.parent / "_shared/vendor/modules",
        root.parent.parent / "vendor/modules",
    ):
        if (vendor / "vera_assurance").is_dir():
            sys.path.insert(0, str(vendor))
            break
    from vera_assurance import load_client_engagement_context_file

    request = json.loads(sys.stdin.read(128001))
    if request["operation"] == "implementation":
        files = {}
        for directory in (
            root / "scripts",
            root / "references/xsd",
            vendor / "vera_assurance",
        ):
            for path in sorted(directory.rglob("*")):
                if path.is_file() and path.suffix in {".py", ".xsd", ".json"}:
                    files[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        result = {"sha256": producer.digest(files)}
    else:
        context = load_client_engagement_context_file(
            Path(request["context"]),
            expected_workflow_id="invoice-xml",
            allowed_statuses=("running", "ready_for_review", "completed"),
        )
        output, inputs = Path(context["output_dir"]), Path(context["input_dir"])
        registered = {
            Path(row["path"]): row["sha256"] for row in context["input_bindings"]
        }

        def ordinary(path: Path, limit: int = producer.MAX_INPUT_BYTES) -> bytes:
            if any(parent.is_symlink() for parent in (path, *path.parents)):
                raise ValueError("Invoice artifacts cannot use linked paths")
            return producer._regular(path, limit)

        def proposal(path: Path) -> dict:
            value = json.loads(ordinary(path, 5 * 1024 * 1024))
            for source in value["sources"]:
                relative = Path(source["path"])
                path = inputs / relative
                if (
                    relative.is_absolute()
                    or ".." in relative.parts
                    or path not in registered
                ):
                    raise PermissionError(
                        "Invoice source is outside the exact registered run"
                    )
                if (
                    source["sha256"] != registered[path]
                    or hashlib.sha256(ordinary(path)).hexdigest() != registered[path]
                ):
                    raise ValueError("Invoice source receipt changed")
            return value

        def files(directory: Path) -> dict[str, bytes]:
            if directory.is_symlink() or not directory.is_dir():
                raise ValueError("Invalid invoice artifact directory")
            return {p.name: ordinary(p) for p in directory.iterdir()}

        def replay(
            value: dict, actual: Path | None = None, review: dict | None = None
        ) -> dict:
            # Exact public regeneration proves mechanical reproducibility. Temporary
            # verification never writes into the authoritative client's output.
            with tempfile.TemporaryDirectory(
                prefix="vera-invoice-replay-"
            ) as temporary:
                prepared = producer.prepare_draft(
                    value, input_root=inputs, output_dir=Path(temporary).resolve()
                )
                expected = files(prepared)
                validation = json.loads(expected["validation.json"])
                if actual is not None:
                    names = {p.name for p in actual.iterdir()}
                    if names - {"export"} != set(expected):
                        raise ValueError(
                            "Unknown or incomplete invoice revision artifacts"
                        )
                    changed = [
                        name
                        for name, content in expected.items()
                        if (
                            preview_content(ordinary(actual / name))
                            != preview_content(content)
                            if name == "preview.html"
                            else ordinary(actual / name) != content
                        )
                    ]
                    if changed:
                        raise ValueError(
                            "Invoice artifact differs from public replay: "
                            + ", ".join(changed)
                        )
                export = None
                if (
                    review is not None
                    or actual is not None
                    and (actual / "export").exists()
                ):
                    if review is None:
                        review = json.loads(ordinary(actual / "export/review.json"))
                    export = producer.export_invoice(
                        prepared, review, input_root=inputs
                    )
                    if actual is not None and (actual / "export").exists():
                        if files(actual / "export") != files(prepared / "export"):
                            raise ValueError(
                                "Invoice XML, approval or export report changed"
                            )
                return {
                    "proposal_sha256": producer.digest(value),
                    "validation": validation,
                    "fields": flatten_fields(value["invoice"]),
                    "proposal": value,
                    "export": export,
                    "review": review,
                }

        operation = request["operation"]
        if operation == "prepare_evidence":
            from source_evidence import prepare_source_evidence

            selection = json.loads(ordinary(Path(request["selection"])))
            for row in selection:
                path = inputs / Path(row["path"])
                if path not in registered:
                    raise PermissionError(
                        "Prepare only exact registered invoice originals"
                    )
            directory = prepare_source_evidence(
                selection, input_root=inputs, output_dir=Path(request["output"])
            )
            result = {
                "directory": str(directory),
                "manifest": json.loads(ordinary(directory / "source_evidence.json")),
            }
        elif operation in {"inspect_proposal", "save_proposal"}:
            from source_evidence import prepare_source_evidence

            value = proposal(Path(request["proposal"]))
            with tempfile.TemporaryDirectory(
                prefix="vera-invoice-authoring-"
            ) as temporary:
                directory = Path(temporary).resolve()
                intake = prepare_source_evidence(
                    value["sources"], input_root=inputs, output_dir=directory
                )
                captured = {
                    p.name: hashlib.sha256(ordinary(p)).hexdigest()
                    for p in intake.iterdir()
                }
                if captured != request["expected_intake_artifacts"]:
                    raise ValueError(
                        "Invoice prepared material differs from actual original replay"
                    )
                prepared = producer.prepare_draft(
                    value, input_root=inputs, output_dir=directory
                )
                result = {
                    "record": {
                        **replay(value),
                        "status": json.loads(ordinary(prepared / "validation.json"))[
                            "status"
                        ],
                        "intake_artifacts": {
                            intake.name + "/" + name: sha
                            for name, sha in captured.items()
                        },
                    },
                    "memo": ordinary(prepared / "preview.html").decode("utf-8"),
                }
                if operation == "save_proposal":
                    reference = result["record"]["proposal_sha256"]
                    producer._write_new(
                        output / ("invoice-native-proposal-" + reference + ".json"),
                        producer._json(value),
                    )
                    actual_intake = prepare_source_evidence(
                        value["sources"], input_root=inputs, output_dir=output
                    )
                    if {
                        p.name: hashlib.sha256(ordinary(p)).hexdigest()
                        for p in actual_intake.iterdir()
                    } != captured:
                        raise ValueError(
                            "Invoice source material changed during conservation; recovery required"
                        )
                    actual = producer.prepare_draft(
                        value, input_root=inputs, output_dir=output
                    )
                    replay(value, actual)
                    if (
                        ordinary(actual / "preview.html").decode("utf-8")
                        != result["memo"]
                    ):
                        raise ValueError(
                            "Invoice conserved preview differs; recovery required"
                        )
        elif operation in {"candidate", "prepare"}:
            value = proposal(output / "proposal.json")
            result = replay(value)
            if (
                request.get("proposal_sha256")
                and result["proposal_sha256"] != request["proposal_sha256"]
            ):
                raise ValueError("Invoice candidate changed")
            if operation == "prepare":
                result["revision"] = producer.prepare_draft(
                    value, input_root=inputs, output_dir=output
                ).name
        else:
            identity = request["proposal_sha256"]
            if len(identity) != 64 or any(
                c not in "0123456789abcdef" for c in identity
            ):
                raise ValueError("Choose one exact invoice proposal")
            actual = output / ("draft-" + identity)
            value = proposal(actual / "proposal.json")
            if producer.digest(value) != identity:
                raise ValueError("Invoice revision content identity changed")
            if operation not in {"read", "check_export", "export"}:
                raise ValueError("Unknown invoice operation")
            review = (
                request["review"] if operation in {"check_export", "export"} else None
            )
            result = replay(value, actual, review)
            if operation == "export":
                result["export"] = producer.export_invoice(
                    actual, review, input_root=inputs
                )
        if len(json.dumps(result).encode()) > 8_000_000:
            raise ValueError(
                "Invoice projection exceeds native limit; retain specialist artifacts"
            )
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
