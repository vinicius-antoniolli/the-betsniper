import sqlite3

import pandas as pd

from _paths import PUBLIC_DB


with sqlite3.connect(PUBLIC_DB) as conn:
    df = pd.read_sql(
        "SELECT league_name, home_team FROM matches WHERE home_team IN ('AtlÃ©tico-MG', 'OperÃ¡rio PR')",
        conn,
    )
print(df)
