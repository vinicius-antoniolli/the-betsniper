from __future__ import annotations

import argparse
import logging

from config import LOG_DIR, ensure_runtime_dirs
from src.db.session import init_db
from src.etl.daily import run_etl_window


def configure_logging() -> None:
    ensure_runtime_dirs()
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_DIR / "daily.log", encoding="utf-8"),
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD. Default: today in APP_TIMEZONE.")
    parser.add_argument("--days", type=int, default=2, help="Number of days to collect from the base date.")
    parser.add_argument("--skip-odds", action="store_true")
    args = parser.parse_args()

    configure_logging()
    init_db()
    run_etl_window(target_date=args.date, include_odds=not args.skip_odds, days=args.days)


if __name__ == "__main__":
    main()
