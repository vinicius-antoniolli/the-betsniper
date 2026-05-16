import sqlite3
import pandas as pd
conn = sqlite3.connect('public_data/betsniper_public.db')
df = pd.read_sql("SELECT DISTINCT source_match_id, raw_home_team, raw_away_team FROM odds_snapshots", conn)
print(df)
