from __future__ import annotations

import math
import re
from unicodedata import normalize


def plain_text(value: object) -> str:
    text = "" if value is None else str(value)
    return normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower().strip()


def _missing(value: object) -> bool:
    if value in (None, ""):
        return True
    try:
        return bool(math.isnan(float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def display_score(value: object) -> str:
    if _missing(value):
        return "N/D"
    return f"{float(value):.1f}"


def expected_point_from_text(value: object) -> float | None:
    text = str(value or "").replace(",", ".")
    match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)(?:\s*ou mais|\s*or more|\+)", text, re.IGNORECASE)
    if match:
        number = float(match.group(1))
        return number - 0.5 if number >= 1 else number
    match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s+(?:cart|escante|chute|finaliz|falta)", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    match = re.search(r"mais/menos de\s+(\d+(?:\.\d+)?)", plain_text(text), re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def score_parts(values: list[float], pick: object, line: object) -> tuple[str, int, int, str]:
    try:
        threshold = float(line)
    except (TypeError, ValueError):
        return "N/D", 0, 0, ""
    if threshold <= 0:
        return "N/D", 0, 0, ""
    clean = [float(value) for value in values if not _missing(value)]
    if not clean:
        return "N/D", 0, 0, ""
    pick_text = plain_text(pick)
    if "under" in pick_text or "menos" in pick_text:
        hits = sum(1 for value in clean if value < threshold)
        rule = f"valor < {threshold:g}"
    elif "over" in pick_text or "mais" in pick_text:
        hits = sum(1 for value in clean if value > threshold)
        rule = f"valor > {threshold:g}"
    else:
        return "N/D", 0, 0, ""
    return display_score(round((hits / len(clean)) * 100, 1)), hits, len(clean), rule


def score_from_values(values: list[float], pick: object, line: object) -> str:
    score, _, _, _ = score_parts(values, pick, line)
    return score


def hit_score(hits: int, total: int) -> str:
    if total <= 0:
        return "N/D"
    return display_score(round((hits / total) * 100, 1))


def line_hit(value: object, pick: object, line: object) -> bool | None:
    score, hits, total, _ = score_parts([value], pick, line)
    if score == "N/D" or total == 0:
        return None
    return hits == 1


def line_pick(value: object) -> object:
    text = plain_text(value)
    if "+" in str(value or "") or "ou mais" in text or "mais de" in text or "acima de" in text or "over" in text:
        return "Over"
    if "menos de" in text or "abaixo de" in text or "under" in text:
        return "Under"
    return value
