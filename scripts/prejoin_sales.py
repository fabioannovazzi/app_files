from __future__ import annotations

"""Run only the dataset-specific sales-join stage for PDP data."""

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

# Allow direct execution via `python scripts/prejoin_sales.py`.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from modules.pdp.prejoin_sales import run_sales_join
from modules.pdp.run_status_notifications import (
    resolve_notification_recipients,
    send_run_notification,
)
from modules.pdp.sales_dataset_paths import (
    SALES_DATASET_ENV_VAR,
    get_sales_dataset_csv_dir,
    list_available_sales_dataset_names,
)
from modules.utilities.secrets_loader import load_env_from_secrets_file


def _dataset_has_csv_inputs(dataset: str) -> bool:
    csv_dir = get_sales_dataset_csv_dir(dataset)
    if not csv_dir.is_dir():
        return False
    return any(path.is_file() for path in csv_dir.glob("*.csv"))


def _get_runnable_dataset_names() -> list[str]:
    return [
        name
        for name in list_available_sales_dataset_names()
        if _dataset_has_csv_inputs(name)
    ]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run only dataset-specific sales-join outputs using the shared mapped "
            "attribute cache. This script does not run vision or web-search LLM calls."
        )
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--dataset",
        default=None,
        help=(
            "Sales dataset name. Uses data/pdp/sales_data for 'default' and "
            "data/pdp/sales_data/datasets/<name> for named datasets. "
            f"If omitted, reads {SALES_DATASET_ENV_VAR}."
        ),
    )
    group.add_argument(
        "--all-datasets",
        action="store_true",
        help=(
            "Run join stage for every dataset that currently has CSV inputs "
            "(including 'default' when data/pdp/sales_data/csv_files contains CSV files)."
        ),
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
    return parser.parse_args()


def _configure_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    log_dir = ROOT_DIR / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.FileHandler(log_dir / "prejoin_sales.log", encoding="utf-8")
        )
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def _notify_failure(
    *,
    recipients: list[str],
    started_at: dt.datetime,
    logger: logging.Logger,
    error: str,
    dataset: str = "",
    all_datasets: bool = False,
) -> None:
    send_run_notification(
        run_name="prejoin_sales",
        status="failed",
        recipients=recipients,
        started_at=started_at,
        finished_at=dt.datetime.now(dt.timezone.utc),
        details={
            "error": error,
            "dataset": dataset,
            "all_datasets": all_datasets,
        },
        logger=logger,
    )


def main() -> None:
    args = _parse_args()
    _configure_logging()
    load_env_from_secrets_file()
    logger = logging.getLogger(__name__)
    recipients = resolve_notification_recipients(args.notify_email)
    started_at = dt.datetime.now(dt.timezone.utc)
    send_run_notification(
        run_name="prejoin_sales",
        status="started",
        recipients=recipients,
        started_at=started_at,
        details={
            "dataset": args.dataset or "",
            "all_datasets": args.all_datasets,
        },
        logger=logger,
    )
    if args.all_datasets:
        dataset_names = _get_runnable_dataset_names()
        if not dataset_names:
            message = (
                "No datasets with CSV inputs were found under data/pdp/sales_data."
            )
            _notify_failure(
                recipients=recipients,
                started_at=started_at,
                logger=logger,
                error=message,
                all_datasets=True,
            )
            raise SystemExit(message)
        try:
            logging.info(
                "Running sales-join stage for datasets: %s",
                ", ".join(dataset_names),
            )
            for dataset_name in dataset_names:
                logging.info(
                    "Starting sales-join stage for dataset '%s'.", dataset_name
                )
                run_sales_join(dataset=dataset_name)
        except Exception as exc:
            _notify_failure(
                recipients=recipients,
                started_at=started_at,
                logger=logger,
                error=str(exc),
                all_datasets=True,
            )
            raise
        else:
            send_run_notification(
                run_name="prejoin_sales",
                status="success",
                recipients=recipients,
                started_at=started_at,
                finished_at=dt.datetime.now(dt.timezone.utc),
                details={"datasets": ",".join(dataset_names)},
                logger=logger,
            )
        return

    try:
        run_sales_join(dataset=args.dataset)
    except Exception as exc:
        _notify_failure(
            recipients=recipients,
            started_at=started_at,
            logger=logger,
            error=str(exc),
            dataset=args.dataset or "",
        )
        raise
    else:
        send_run_notification(
            run_name="prejoin_sales",
            status="success",
            recipients=recipients,
            started_at=started_at,
            finished_at=dt.datetime.now(dt.timezone.utc),
            details={"dataset": args.dataset or ""},
            logger=logger,
        )


if __name__ == "__main__":
    main()
