import sqlite3
import pandas as pd
conn = sqlite3.connect('public_data/betsniper_public.db')
df = pd.read_sql("SELECT league_name, home_team FROM matches WHERE home_team IN ('Atlético-MG', 'Operário PR')", conn)
print(df)
