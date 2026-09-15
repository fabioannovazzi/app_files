"""Verify that one Clara case HTML deck is mechanically ready for delivery."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Mapping

from advisory_delivery import AdvisoryDeliveryError, verify_advisory_delivery
from case_store import atomic_text

__all__ = ["verify_advisory_html_delivery", "main"]
LOGGER = logging.getLogger(__name__)
AdvisoryHTMLDeliveryError = AdvisoryDeliveryError


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_text(path, json.dumps(payload, indent=2) + "\n")


def verify_advisory_html_delivery(
    case_dir: Path, deck: Path, validation_audit_path: Path
) -> dict[str, Any]:
    """Apply the shared case contract plus required HTML static and browser QA."""
    if deck.suffix.casefold() not in {".html", ".htm"}:
        raise AdvisoryHTMLDeliveryError("delivery gate requires an HTML deck")
    result = verify_advisory_delivery(case_dir, deck, validation_audit_path)
    result["schema_version"] = "clara.advisory_html_delivery.v1"
    result["deck"] = result.pop("artifact")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("deck", type=Path)
    parser.add_argument("validation_audit", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        output = args.output.expanduser().resolve()
        protected = {
            args.deck.expanduser().resolve(),
            args.validation_audit.expanduser().resolve(),
        }
        if output in protected:
            raise AdvisoryHTMLDeliveryError(
                "delivery receipt output must not overwrite an input artifact"
            )
        receipt = verify_advisory_html_delivery(
            args.case_dir,
            args.deck,
            args.validation_audit,
        )
        _write_json(output, receipt)
    except (AdvisoryHTMLDeliveryError, OSError, ValueError) as exc:
        LOGGER.error("Advisory HTML delivery verification failed: %s", exc)
        return 2
    LOGGER.info(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
