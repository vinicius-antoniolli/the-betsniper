import sqlite3
import pandas as pd
conn = sqlite3.connect('public_data/betsniper_public.db')
df = pd.read_sql("SELECT source_match_id, home_team, away_team FROM matches", conn)
print(df)
