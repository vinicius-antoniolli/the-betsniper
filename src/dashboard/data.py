from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd


SqlParams = dict[str, Any] | tuple[Any, ...] | list[Any] | None


def read_sql_frame(db_path: Path, query: str, params: SqlParams = None) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame()
    with sqlite3.connect(db_path) as con:
        return pd.read_sql_query(query, con, params=params or {})
