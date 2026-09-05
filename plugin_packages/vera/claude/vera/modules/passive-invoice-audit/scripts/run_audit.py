"""Command-line entry point for Vera's passive-invoice audit."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from decimal import Decimal
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPTS_DIR.parent
for _vendor_root in (
    PLUGIN_ROOT / "vendor" / "modules",
    PLUGIN_ROOT.parent.parent / "vendor" / "modules",
    PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
):
    if (_vendor_root / "vera_assurance").is_dir():
        if str(_vendor_root) not in sys.path:
            sys.path.insert(0, str(_vendor_root))
        break

from audit_core import AuditConfig, run_audit
from cowork_worker import configured_runtime, run_cowork_chunk
from luna_worker import run_luna_chunk
from vera_assurance import AssuranceContractError, load_client_engagement_context_file

__all__ = ["main"]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit passive FatturaPA XMLs against an actual ledger without posting changes."
    )
    parser.add_argument("--invoices", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--ledger-mapping", type=Path, required=True)
    parser.add_argument("--ledger-sheet")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--client-engagement", type=Path, required=True)
    parser.add_argument("--history-jsonl", type=Path)
    parser.add_argument(
        "--chart-of-accounts-json",
        type=Path,
        help="Optional JSON object mapping account codes to client descriptions.",
    )
    parser.add_argument("--chunk-size", type=int, default=25)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument(
        "--reasoning-effort",
        choices=("low", "medium", "high", "xhigh", "max"),
        default="low",
    )
    parser.add_argument("--amount-tolerance", type=Decimal, default=Decimal("0.01"))
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    """Run or resume one audit job."""

    args = _arguments()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    input_paths = [args.invoices, args.ledger, args.ledger_mapping]
    input_paths.extend(
        path
        for path in (args.history_jsonl, args.chart_of_accounts_json)
        if path is not None
    )
    try:
        client_context = load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="passive-invoice-audit",
            input_paths=input_paths,
            output_dir=args.output,
        )
    except AssuranceContractError as exc:
        logging.getLogger(__name__).error("CLIENT_ENGAGEMENT_BLOCKED: %s", exc)
        return 2

    history = []
    if args.history_jsonl:
        history = [
            json.loads(line)
            for line in args.history_jsonl.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    chart_of_accounts = {}
    if args.chart_of_accounts_json:
        chart_of_accounts = json.loads(
            args.chart_of_accounts_json.read_text(encoding="utf-8")
        )
        if not isinstance(chart_of_accounts, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in chart_of_accounts.items()
        ):
            raise ValueError("Chart of accounts must be a JSON object of strings")
    cowork = configured_runtime() == "cowork-haiku"
    summary = run_audit(
        invoice_source=args.invoices,
        ledger_path=args.ledger,
        mapping_path=args.ledger_mapping,
        output_dir=args.output,
        runner=run_cowork_chunk if cowork else run_luna_chunk,
        config=AuditConfig(
            semantic_model="haiku" if cowork else "gpt-5.6-luna",
            chunk_size=args.chunk_size,
            concurrency=args.concurrency,
            max_retries=args.max_retries,
            reasoning_effort=args.reasoning_effort,
            amount_tolerance=args.amount_tolerance,
        ),
        ledger_sheet=args.ledger_sheet,
        history=history,
        chart_of_accounts=chart_of_accounts,
        client_run_id=str(client_context["run_id"]),
        client_run_root=Path(str(client_context["run_root"])),
    )
    if summary["status"] == "awaiting_semantic_review":
        logging.getLogger(__name__).warning(
            "Semantic review pending: dispatch prepared cowork_request.json files, save validated worker responses, and resume the same command."
        )
        return 3
    logging.getLogger(__name__).info(
        "Audit complete: %s invoices, %s require professional attention",
        summary["population"],
        summary["invoices_requiring_professional_attention"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
