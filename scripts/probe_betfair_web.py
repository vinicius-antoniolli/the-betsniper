from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.collectors.betfair_web import BetfairWebClient
from src.db.session import get_session, init_db


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().date().isoformat())
    args = parser.parse_args()

    init_db()
    with get_session() as session:
        events = BetfairWebClient(session, args.date).odds()

    markets = Counter()
    props = 0
    for event in events:
        for bookmaker in event.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                markets[market.get("key") or "unknown"] += len(market.get("outcomes") or [])
                if market.get("player_prop"):
                    props += len(market.get("outcomes") or [])

    print(f"BetfairWeb: eventos={len(events)} player_props={props}")
    print("mercados:", ", ".join(f"{key}={value}" for key, value in markets.most_common()) or "nenhum")


if __name__ == "__main__":
    main()
