"""Run-local extraction proposals, checked against independently read PDF words.

The adapter chooses source references, never accounting values. Exact source
ownership, Decimal arithmetic and replay are mechanical controls; account/header
semantics still require the normal source-bound mapping review. A subprocess is
process separation, not an operating-system security sandbox.
"""

from __future__ import annotations

import hashlib
import json

# Explicit local Python execution is the adapter contract; no shell is used.
import subprocess  # nosec B404
import sys
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from .rules import RuleLayout, money_candidate, negative_notation, signed_amount

__all__ = ["source_inventory", "read_adapter_pdf"]


class AdapterFailure(ValueError):
    """Keep bounded private diagnostics available to the host recovery loop."""

    def __init__(self, message: str, evidence: dict[str, Any]) -> None:
        super().__init__(message)
        self.evidence = evidence


def _bands(
    layout: dict[str, Any], *, source_role: str = "journal"
) -> dict[str, tuple[float, float]]:
    from . import _coordinate

    columns = layout.get("columns", {})
    if not isinstance(columns, dict):
        raise ValueError("Adapter requires reviewed physical column semantics")
    required = {
        "account_debit",
        "account_credit",
        "debit",
        "credit",
        "description",
    }
    if source_role == "bank":
        required = {"date", "description"}
        required |= {"amount"} if "amount" in columns else {"debit", "credit"}
    if (
        set(columns) != required
        if source_role == "journal"
        else not required <= set(columns)
        or set(columns) - required - {"balance", "reference", "value_date"}
    ):
        raise ValueError("Adapter requires reviewed physical column semantics")
    result = {}
    for name, bounds in columns.items():
        if not isinstance(bounds, list) or len(bounds) != 2:
            raise ValueError("Invalid adapter column bounds")
        left, right = map(_coordinate, bounds)
        if not 0 <= left < right:
            raise ValueError("Invalid adapter column bounds")
        result[name] = (left, right)
    ordered = sorted(result.values())
    if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
        raise ValueError("Adapter column bands must not overlap")
    body = layout.get("body", [])
    if (
        not isinstance(body, list)
        or len(body) != 2
        or not 0 <= _coordinate(body[0]) < _coordinate(body[1])
    ):
        raise ValueError("Adapter requires reviewed body coordinates")
    return result


def source_inventory(
    path: Path, layout: dict[str, Any], *, source_role: str = "journal"
) -> dict[str, Any]:
    """Read all source words with stable IDs; keep this evidence local."""
    import pdfplumber
    from pdfplumber.utils.exceptions import PdfminerException

    from .recovery import _file_digest

    bands = _bands(layout, source_role=source_role)
    rules = RuleLayout(layout)
    date_formats = ("%d/%m/%Y", "%Y-%m-%d")
    if source_role == "bank":
        date_formats += ("%d.%m.%Y", "%d/%m/%y", "%d.%m.%y")
    if layout.get("date_format", "%d/%m/%Y") not in date_formats:
        raise ValueError(
            "Adapter date format requires an explicit supported source format"
        )
    issues: list[dict[str, Any]] = []

    def reject(page: int, row: int, reason: str) -> None:
        issues.append({"source_page": page, "source_row": row, "reason": reason})

    pages = []
    digest = _file_digest(path)
    with pdfplumber.open(path) as document:
        for number, page in enumerate(document.pages, 1):
            try:
                if (
                    rules.body[1] > page.height
                    or max(b[1] for b in bands.values()) > page.width
                ):
                    reject(number, 0, "reviewed_coordinates_outside_page")
                words = sorted(
                    rules.words(page, number, reject), key=lambda w: (w["top"], w["x0"])
                )
                row, top = 0, None
                evidence = []
                for index, word in enumerate(words, 1):
                    if top is None or abs(float(word["top"]) - top) > 2:
                        row += 1
                        top = float(word["top"])
                    evidence.append(
                        {
                            "id": f"p{number}w{index}",
                            "page": number,
                            "row": row,
                            **{
                                key: str(word[key])
                                for key in ("text", "x0", "x1", "top", "bottom")
                            },
                        }
                    )
                pages.append({"page": number, "words": evidence})
            except PdfminerException:
                reject(number, 0, "page_decode_failed")
                pages.append({"page": number, "words": []})
            finally:
                page.close()
    if _file_digest(path) != digest:
        raise ValueError("Source changed during inventory")
    return {
        "schema_version": "vera.pdf_words.v1",
        "source_sha256": digest,
        "pages": pages,
        "issues": issues,
    }


def _run_adapter(layout: dict[str, Any], inventory: dict[str, Any]) -> dict[str, Any]:
    """Execute the exact host-written file; never import it into the checker."""
    from .recovery import _file_digest

    spec = layout["agent_adapter"]
    if not isinstance(spec, dict) or set(spec) != {"path", "sha256"}:
        raise ValueError("agent_adapter requires an absolute path and sha256")
    path = Path(spec["path"])
    if not path.is_absolute() or any(p.is_symlink() for p in path.parents):
        raise ValueError("Adapter must be an ordinary absolute run-local file")
    if _file_digest(path) != spec["sha256"]:
        raise ValueError("Run-local adapter changed; record a new recovery revision")
    code = path.read_bytes()
    # Only the Python interpreter is launched. No shell, dynamic installation,
    # model call or server-provided command is part of this execution contract.
    with tempfile.TemporaryDirectory(prefix="vera-pdf-adapter-") as directory:
        root = Path(directory)
        executable = root / "adapter.py"
        executable.write_bytes(code)
        with (
            (root / "input.json").open("w+", encoding="utf-8") as source,
            (root / "output.json").open("w+", encoding="utf-8") as output,
            (root / "stderr.txt").open("w+", encoding="utf-8") as errors,
        ):
            json.dump(inventory, source)
            source.seek(0)
            try:
                completed = subprocess.run(  # nosec B603
                    [sys.executable, "-I", "-B", str(executable)],
                    stdin=source,
                    stdout=output,
                    stderr=errors,
                    cwd=root,
                    timeout=60,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                errors.seek(0)
                raise AdapterFailure(
                    "Run-local adapter exceeded its execution budget",
                    {
                        "stderr": errors.read(32000),
                        "stderr_projection_limit": 32000,
                    },
                ) from exc
            errors.seek(0)
            private_error = errors.read(32001)
            evidence = {
                "stderr": private_error[:32000],
                "stderr_truncated": len(private_error) > 32000,
                "exit_code": completed.returncode,
            }
            if completed.returncode:
                raise AdapterFailure(
                    "Run-local adapter failed; inspect retained local diagnostics",
                    evidence,
                )
            if output.tell() > 32 * 1024 * 1024:
                raise ValueError("Adapter proposal exceeds the local output limit")
            output.seek(0)
            try:
                proposal = json.load(output)
            except (ValueError, UnicodeError) as exc:
                raise AdapterFailure(
                    "Run-local adapter emitted invalid JSON", evidence
                ) from exc
    if (
        _file_digest(path) != spec["sha256"]
        or hashlib.sha256(code).hexdigest() != spec["sha256"]
    ):
        raise ValueError("Adapter changed during execution")
    if (
        not isinstance(proposal, dict)
        or set(proposal) != {"rows"}
        or not isinstance(proposal["rows"], list)
    ):
        raise ValueError("Adapter must emit exactly a rows array of source references")
    return proposal


def read_adapter_pdf(
    path: Path, layout: dict[str, Any], *, currency: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Reconstruct proposed rows from source and enforce independent controls."""
    from .recovery import _identity

    before = _identity(path, currency)
    if layout.get("source_sha256") != before["source_sha256"]:
        raise ValueError("Adapter layout must be bound to the exact PDF")
    bands = _bands(layout)
    rules = RuleLayout(layout)
    inventory = source_inventory(path, layout)
    proposal = _run_adapter(layout, inventory)
    if _identity(path, currency) != before:
        raise ValueError(
            "Source or independent checker changed during adapter execution"
        )
    issues = list(inventory["issues"])
    words = {w["id"]: w for p in inventory["pages"] for w in p["words"]}
    rows: list[dict[str, Any]] = []
    claimed: set[str] = set()
    used_accounts: set[str] = set()
    totals: dict[str, dict[str, Decimal]] = {}
    headers: dict[str, tuple[str, str]] = {}
    source_amounts: dict[str, tuple[str, Decimal]] = {}

    def reject(page: int, row: int, reason: str) -> None:
        issues.append({"source_page": page, "source_row": row, "reason": reason})

    def within(word: dict[str, Any], band: str) -> bool:
        left, right = bands[band]
        return left <= float(word["x0"]) and float(word["x1"]) <= right

    def references(value: Any) -> list[dict[str, Any]]:
        if (
            not isinstance(value, list)
            or not value
            or any(not isinstance(v, str) or v not in words for v in value)
        ):
            raise ValueError("invalid_source_reference")
        if len(set(value)) != len(value):
            raise ValueError("duplicate_source_reference")
        result = [words[v] for v in value]
        if result != sorted(
            result, key=lambda w: (w["page"], w["row"], float(w["x0"]))
        ):
            raise ValueError("source_references_out_of_order")
        return result

    for candidate in proposal["rows"]:
        page = row = 0
        try:
            if not isinstance(candidate, dict) or set(candidate) != {
                "amount",
                "side",
                "account",
                "date",
                "registration",
                "description",
            }:
                raise ValueError("invalid_posting_proposal")
            amount_word = references([candidate["amount"]])[0]
            page, row = amount_word["page"], amount_word["row"]
            side = candidate["side"]
            if side not in ("debit", "credit") or not within(amount_word, side):
                raise ValueError("amount_outside_reviewed_side")
            token = amount_word["text"]
            if not money_candidate(token):
                raise ValueError("unsupported_source_amount")
            if rules.amount_issue(token):
                raise ValueError(rules.amount_issue(token))
            if amount_word["id"] in claimed:
                raise ValueError("duplicate_source_amount")
            account_words = references(candidate["account"])
            date_word = references([candidate["date"]])[0]
            registration_word = references([candidate["registration"]])[0]
            if (date_word["page"], date_word["row"]) != (
                registration_word["page"],
                registration_word["row"],
            ):
                raise ValueError("registration_header_requires_one_source_line")
            header_position = (date_word["page"], date_word["row"])
            if header_position >= (page, row):
                raise ValueError("registration_header_must_precede_posting")
            date = (
                datetime.strptime(
                    date_word["text"], layout.get("date_format", "%d/%m/%Y")
                )
                .date()
                .isoformat()
            )
            registration = registration_word["text"]
            if money_candidate(registration) or registration == date_word["text"]:
                raise ValueError("invalid_registration_reference")
            if any(
                w["page"] != page
                or not header_position < (w["page"], w["row"]) <= (page, row)
                or not within(w, "account_" + side)
                or money_candidate(w["text"])
                or w["id"] in used_accounts
                for w in account_words
            ):
                raise ValueError("account_reference_outside_posting")
            description_words = (
                references(candidate["description"]) if candidate["description"] else []
            )
            if any(
                w["page"] != page
                or not header_position < (page, w["row"]) <= (page, row)
                or not within(w, "description")
                for w in description_words
            ):
                raise ValueError("description_reference_outside_posting")
            header = (date_word["id"], registration_word["id"])
            if registration in headers and headers[registration] != header:
                raise ValueError("duplicate_registration_number")
            headers[registration] = header
            value = signed_amount(token)
            output_side, output_value = side, value
            if negative_notation(token) and rules.negative_semantics == "opposite_side":
                output_side = "credit" if side == "debit" else "debit"
                output_value = -value
            record = {
                "entry_date": date,
                "movement_number": registration,
                "account": " ".join(w["text"] for w in account_words),
                "line_desc": " ".join(w["text"] for w in description_words),
                "debit": str(output_value) if output_side == "debit" else "0",
                "credit": str(output_value) if output_side == "credit" else "0",
                "currency": currency,
                "unit": "currency",
                "reported_increment": "0.01",
                "source_file": path.name,
                "source_sheet": "PDF",
                "source_page": page,
                "source_row": row,
                "source_amount_text": token,
                "source_amount_side": side,
                "source_references": candidate,
            }
            rows.append(record)
            claimed.add(amount_word["id"])
            used_accounts.update(w["id"] for w in account_words)
            source_amounts[amount_word["id"]] = (side, value)
            total = totals.setdefault(
                registration, {"debit": Decimal(0), "credit": Decimal(0)}
            )
            total[output_side] += output_value
        except (ValueError, TypeError, KeyError) as exc:
            # Only fixed check identifiers leave this local evidence via reporting.
            reject(page, row, str(exc))
    for page_evidence in inventory["pages"]:
        number = page_evidence["page"]
        rules.page_total_count = 0
        lines: dict[int, list[dict[str, Any]]] = {}
        for word in page_evidence["words"]:
            lines.setdefault(word["row"], []).append(word)
        for line_number, line in lines.items():
            if rules.total(line, bands, number, line_number, reject):
                if any(w["id"] in claimed for w in line):
                    reject(number, line_number, "control_amount_claimed_as_posting")
                continue
            for word in line:
                if not money_candidate(word["text"]):
                    if any(c.isdigit() for c in word["text"]) and any(
                        within(word, side) for side in ("debit", "credit")
                    ):
                        reject(
                            number,
                            line_number,
                            "unrecognized_numeric_content_in_amount_band",
                        )
                    continue
                if word["id"] not in claimed:
                    reject(number, line_number, "unclaimed_source_amount")
                    continue
                if (
                    not rules.body[0] <= float(word["top"]) < rules.body[1]
                    or rules.page_total_count
                ):
                    reject(
                        number,
                        line_number,
                        "posting_outside_reviewed_body_or_after_total",
                    )
                side, value = source_amounts[word["id"]]
                rules.running[side] += value
        rules.close_page(number, reject)
    if not rules.labels:
        reject(0, 0, "adapter_requires_independent_printed_running_totals")
    for registration, total in totals.items():
        if total["debit"] != total["credit"]:
            reject(0, 0, "registration_debit_credit_do_not_balance")
    rows.sort(
        key=lambda r: (r["source_page"], r["source_row"], r["source_amount_side"])
    )
    header_positions = sorted(
        {(words[date]["page"], words[date]["row"]) for date, _ in headers.values()}
    )
    for record in rows:
        date_word = words[record["source_references"]["date"]]
        own_header = (date_word["page"], date_word["row"])
        position = (record["source_page"], record["source_row"])
        if any(own_header < other < position for other in header_positions):
            reject(
                record["source_page"],
                record["source_row"],
                "posting_crosses_registration_header",
            )
    accepted = bool(rows) and not issues
    diagnostics = {
        "parser": "registration_pdf",
        "adapter": "source_references.v1",
        "accepted": accepted,
        "page_count": len(inventory["pages"]),
        "candidate_row_count": len(proposal["rows"]),
        "emitted_row_count": len(rows) if accepted else 0,
        "readable_rows": rows,
        "readable_row_count": len(rows),
        "requires_mapping_qualification": True,
        "rejected_row_count": len(issues),
        "rejected_rows": issues[:50],
        "unresolved_issues": issues,
        "reason": None if accepted else "registration_pdf_incomplete_or_unbalanced",
        **rules.diagnostics(),
    }
    return rows if accepted else [], diagnostics
