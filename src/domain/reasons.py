from __future__ import annotations

from unicodedata import normalize

import pandas as pd


def _is_missing(value: object) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _metadata_key(value: str) -> str:
    return normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").casefold()


def clean_reason_for_display(value: object) -> object:
    if _is_missing(value):
        return value
    parts: list[str] = []
    for raw_part in str(value).split("|"):
        part = raw_part.strip()
        if not part:
            continue
        key = _metadata_key(part)
        if key == "fonte: espn":
            continue
        if key.startswith("criterio:"):
            continue
        parts.append(part)
    return " | ".join(parts)
