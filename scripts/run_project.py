from __future__ import annotations

import argparse
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from config import ROOT_DIR, settings
from main import configure_logging
from src.db.session import init_db
from src.etl.daily import run_etl_window, target_date_window

STREAMLIT_ETL_CACHE_KEY_ENV = "BETSNIPER_STREAMLIT_ETL_CACHE_KEY"


def streamlit_command(port: int) -> list[str]:
    streamlit_exe = ROOT_DIR / ".venv" / "Scripts" / "streamlit.exe"
    if streamlit_exe.exists():
        base = [str(streamlit_exe)]
    else:
        base = [sys.executable, "-m", "streamlit"]
    return [*base, "run", "app.py", "--server.port", str(port)]


def running_inside_streamlit() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
    except Exception:
        return False

    try:
        return get_script_run_ctx(suppress_warning=True) is not None
    except TypeError:
        return get_script_run_ctx() is not None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coleta dados/odds e abre o dashboard Betsniper.")
    parser.add_argument("--date", help="YYYY-MM-DD. Default: hoje em APP_TIMEZONE.")
    parser.add_argument("--days", type=int, default=2, help="Quantidade de dias a coletar a partir da data base.")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--skip-etl", action="store_true", help="Abre o dashboard sem coletar dados antes.")
    parser.add_argument("--skip-odds", action="store_true", help="Roda ETL sem coletar odds Betfair.")
    return parser.parse_args()


def apply_dashboard_base_date(date_value: str) -> None:
    os.environ["DASHBOARD_BASE_DATE"] = date_value
    settings.dashboard_base_date = date_value


def etl_cache_key(args: argparse.Namespace, dates: list[str]) -> str:
    return json.dumps(
        {
            "dates": dates,
            "skip_etl": args.skip_etl,
            "skip_odds": args.skip_odds,
        },
        sort_keys=True,
    )


def prepare_dashboard_data(args: argparse.Namespace, run_once: bool = False) -> list[str]:
    dates = target_date_window(args.date, args.days)
    if args.skip_etl:
        return dates

    cache_key = etl_cache_key(args, dates)
    if run_once and os.environ.get(STREAMLIT_ETL_CACHE_KEY_ENV) == cache_key:
        return dates

    run_etl_window(target_date=args.date, include_odds=not args.skip_odds, days=args.days)
    if run_once:
        os.environ[STREAMLIT_ETL_CACHE_KEY_ENV] = cache_key
    return dates


def render_app_in_current_streamlit_process(args: argparse.Namespace) -> None:
    dates = prepare_dashboard_data(args, run_once=True)
    apply_dashboard_base_date(dates[0])
    runpy.run_path(str(ROOT_DIR / "app.py"), run_name="__main__")


def main() -> None:
    args = parse_args()

    configure_logging()
    init_db()
    if running_inside_streamlit():
        render_app_in_current_streamlit_process(args)
        return

    dates = prepare_dashboard_data(args)
    env = os.environ.copy()
    env["DASHBOARD_BASE_DATE"] = dates[0]
    try:
        subprocess.run(streamlit_command(args.port), cwd=ROOT_DIR, check=True, env=env)
    except KeyboardInterrupt:
        print("\nDashboard encerrado.")


if __name__ == "__main__":
    main()
