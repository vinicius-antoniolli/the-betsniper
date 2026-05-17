import sqlite3

import pandas as pd

from _paths import PUBLIC_DB

with sqlite3.connect(PUBLIC_DB) as conn:
    df = pd.read_sql("SELECT DISTINCT source_match_id, raw_home_team, raw_away_team FROM odds_snapshots", conn)
print(df)
