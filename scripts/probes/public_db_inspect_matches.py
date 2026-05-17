import sqlite3

import pandas as pd

from _paths import PUBLIC_DB

with sqlite3.connect(PUBLIC_DB) as conn:
    df = pd.read_sql("SELECT source_match_id, home_team, away_team FROM matches", conn)
print(df)
