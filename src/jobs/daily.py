from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from config import settings
from main import configure_logging
from src.db.session import init_db
from src.etl.daily import run_daily_etl


def run_scheduler() -> None:
    configure_logging()
    init_db()
    scheduler = BlockingScheduler(timezone=settings.app_timezone)
    scheduler.add_job(run_daily_etl, "cron", hour=8, minute=0, id="daily_etl", replace_existing=True)
    logging.getLogger(__name__).info("Scheduler ativo: 08:00 %s", settings.app_timezone)
    scheduler.start()


if __name__ == "__main__":
    run_scheduler()
