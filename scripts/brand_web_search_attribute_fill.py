from __future__ import annotations

"""Run brand-site web-search PDP attribute fill."""

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

# Allow direct execution via `python scripts/brand_web_search_attribute_fill.py`.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from modules.pdp.attribute_mapping_runner import run_attribute_mapping_web
from modules.pdp.run_status_notifications import (
    resolve_notification_recipients,
    send_run_notification,
)
from modules.utilities.secrets_loader import load_env_from_secrets_file

__all__ = ["main"]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fill missing PDP taxonomy attributes using brand-site web search. "
            "Image/VLM fill is owned by scripts/export_pdp_attributes.py --run-vlm."
        )
    )
    parser.add_argument(
        "--notify-email",
        action="append",
        default=None,
        help=(
            "Optional run-notification recipient (repeatable). "
            "Can also be set via PDP_RUN_NOTIFY_EMAILS."
        ),
    )
    parser.add_argument(
        "--retailer",
        action="append",
        default=None,
        help="Limit web-search fill to one retailer. Repeat for multiple retailers.",
    )
    parser.add_argument(
        "--category",
        action="append",
        default=None,
        help=(
            "Limit web-search fill to one normalized category key. Repeat for "
            "multiple categories."
        ),
    )
    parser.add_argument(
        "--categories",
        action="append",
        dest="category",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def _configure_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    log_dir = ROOT_DIR / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.FileHandler(
                log_dir / "brand_web_search_attribute_fill.log",
                encoding="utf-8",
            )
        )
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    _configure_logging()
    load_env_from_secrets_file()
    logger = logging.getLogger(__name__)
    recipients = resolve_notification_recipients(args.notify_email)
    started_at = dt.datetime.now(dt.timezone.utc)
    send_run_notification(
        run_name="brand_web_search_attribute_fill",
        status="started",
        recipients=recipients,
        started_at=started_at,
        details={
            "retailers": ", ".join(args.retailer or []) or "all",
            "categories": ", ".join(args.category or []) or "all",
        },
        logger=logger,
    )
    try:
        run_attribute_mapping_web(retailers=args.retailer, categories=args.category)
    except Exception as exc:
        send_run_notification(
            run_name="brand_web_search_attribute_fill",
            status="failed",
            recipients=recipients,
            started_at=started_at,
            finished_at=dt.datetime.now(dt.timezone.utc),
            details={"error": str(exc)},
            logger=logger,
        )
        raise
    send_run_notification(
        run_name="brand_web_search_attribute_fill",
        status="success",
        recipients=recipients,
        started_at=started_at,
        finished_at=dt.datetime.now(dt.timezone.utc),
        logger=logger,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
