from __future__ import annotations

import math
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


def format_sample_value(value: object) -> str:
    if _is_missing(value):
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value).strip()
    if math.isnan(number):
        return ""
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def sample_values_suffix(values: list[object]) -> str:
    samples = [sample for value in values if (sample := format_sample_value(value))]
    return f" [ {' - '.join(samples)} ]" if samples else ""


def format_hits_with_samples(hits: int, total: int, values: list[object] | None = None) -> str:
    return f"Acertos {hits}/{total}{sample_values_suffix(values or [])}"
