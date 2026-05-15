from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from config import ROOT_DIR
from main import configure_logging
from src.db.session import init_db
from src.etl.daily import run_etl_window, target_date_window


def streamlit_command(port: int) -> list[str]:
    streamlit_exe = ROOT_DIR / ".venv" / "Scripts" / "streamlit.exe"
    if streamlit_exe.exists():
        base = [str(streamlit_exe)]
    else:
        base = [sys.executable, "-m", "streamlit"]
    return [*base, "run", "app.py", "--server.port", str(port)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Coleta dados/odds e abre o dashboard Betsniper.")
    parser.add_argument("--date", help="YYYY-MM-DD. Default: hoje em APP_TIMEZONE.")
    parser.add_argument("--days", type=int, default=2, help="Quantidade de dias a coletar a partir da data base.")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--skip-etl", action="store_true", help="Abre o dashboard sem coletar dados antes.")
    parser.add_argument("--skip-odds", action="store_true", help="Roda ETL sem coletar odds Betfair.")
    args = parser.parse_args()

    configure_logging()
    init_db()
    dates = target_date_window(args.date, args.days)
    if not args.skip_etl:
        run_etl_window(target_date=args.date, include_odds=not args.skip_odds, days=args.days)

    env = os.environ.copy()
    env["DASHBOARD_BASE_DATE"] = dates[0]
    try:
        subprocess.run(streamlit_command(args.port), cwd=ROOT_DIR, check=True, env=env)
    except KeyboardInterrupt:
        print("\nDashboard encerrado.")


if __name__ == "__main__":
    main()
