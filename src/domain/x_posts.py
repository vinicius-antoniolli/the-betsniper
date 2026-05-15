from __future__ import annotations

import pandas as pd
import re
from dataclasses import dataclass
from unicodedata import normalize

COMPACT_MARKETS = {
    "ambos os times marcam?": "BTTS",
    "aposta no escanteio da partida": "EscMatch",
    "chance dupla": "DC",
    "chutes a gol": "SOT",
    "envolvimentos em faltas": "FEnv",
    "escanteios totais": "Esc",
    "faixa de gols marcados - partida": "FxGols",
    "faltas cometidas": "FCom",
    "faltas sofridas": "FSof",
    "finalizacoes": "Chutes",
    "finalizações": "Chutes",
    "gol marcado em ambos os tempos": "Gol2T?",
    "gol ou assistencia": "G/A",
    "gol ou assistência": "G/A",
    "gols marcados": "GF",
    "gols sofridos": "GA",
    "gols totais": "Gols",
    "gols": "Gols",
    "lidera no intervalo ou no tempo integral": "HT/FT",
    "time com mais chutes no gol": "+SOT",
    "vence qualquer um dos tempos": "VT",
}

TEAM_COLORS = {
    "internacional": "🔴⚪",
    "flamengo": "🔴⚫",
    "chapecoense": "🟢⚪",
    "botafogo": "⚫⚪",
    "cruzeiro": "🔵⚪",
    "atletico-mg": "⚫⚪",
    "atletico mineiro": "⚫⚪",
    "gremio": "🔵⚫⚪",
    "palmeiras": "🟢⚪",
    "sao paulo": "🔴⚪⚫",
    "corinthians": "⚫⚪",
    "santos": "⚫⚪",
    "vasco": "⚫⚪",
    "vasco da gama": "⚫⚪",
    "fluminense": "🔴🟢⚪",
    "bahia": "🔴🔵⚪",
    "vitoria": "🔴⚫",
    "fortaleza": "🔴🔵⚪",
    "ceara": "⚫⚪",
    "athletico-pr": "🔴⚫",
    "athletico pr": "🔴⚫",
    "coritiba": "🟢⚪",
    "juventude": "🟢⚪",
    "criciuma": "🟡⚫⚪",
    "goias": "🟢⚪",
    "atletico-go": "🔴⚫",
    "atletico go": "🔴⚫",
    "atletico goianiense": "🔴⚫",
    "sport": "🔴⚫",
    "sport recife": "🔴⚫",
    "nautico": "🔴⚪",
    "santa cruz": "🔴⚫⚪",
    "red bull bragantino": "🔴⚪",
    "bragantino": "🔴⚪",
    "cuiaba": "🟡🟢",
    "guarani": "🟢⚪",
    "ponte preta": "⚫⚪",
    "paysandu": "🔵⚪",
    "remo": "🔵⚪",
    "vila nova": "🔴⚪",
    "crb": "🔴⚪",
    "csa": "🔵⚪",
    "sampaio correa": "🔴🟢🟡",
    "mirassol": "🟡🟢",
    "novorizontino": "🟡⚫",
    "operario": "⚫⚪",
    "operario-pr": "⚫⚪",
    "avai": "🔵⚪",
    "figueirense": "⚫⚪",
    "ituano": "🔴⚫",
    "tombense": "🔴⚪",
    "londrina": "🔵⚪",
    "botafogo-sp": "🔴⚪⚫",
    "botafogo sp": "🔴⚪⚫",
    "abc": "⚫⚪",
    "america-mg": "🟢⚫",
    "america mg": "🟢⚫",
    "america-rn": "🔴⚪",
    "campinense": "🔴⚫",
    "treze": "⚫⚪",
    "botafogo-pb": "⚫⚪",
    "botafogo pb": "⚫⚪",
    "barra-fc": "🔵⚪",
    "barra fc": "🔵⚪",
    "barra": "🔵⚪",
    # Premier League
    "arsenal": "🔴⚪",
    "aston villa": "🟣🔵",
    "bournemouth": "🔴⚫",
    "brentford": "🔴⚪",
    "brighton": "🔵⚪",
    "chelsea": "🔵⚪",
    "crystal palace": "🔴🔵",
    "everton": "🔵⚪",
    "fulham": "⚪⚫",
    "ipswich town": "🔵⚪",
    "ipswich": "🔵⚪",
    "leicester city": "🔵⚪",
    "leicester": "🔵⚪",
    "liverpool": "🔴⚪",
    "manchester city": "🩵⚪",
    "man city": "🩵⚪",
    "manchester united": "🔴⚫",
    "man united": "🔴⚫",
    "newcastle": "⚫⚪",
    "newcastle united": "⚫⚪",
    "nottingham forest": "🔴⚪",
    "southampton": "🔴⚪",
    "tottenham": "⚪🔵",
    "tottenham hotspur": "⚪🔵",
    "west ham": "🟣🔵",
    "wolverhampton": "🟠⚫",
    "wolves": "🟠⚫",
    # Europe (Champions & Europa League)
    "real madrid": "⚪",
    "barcelona": "🔴🔵",
    "atletico madrid": "🔴⚪",
    "bayern munich": "🔴⚪",
    "bayern de munique": "🔴⚪",
    "borussia dortmund": "🟡⚫",
    "bayer leverkusen": "🔴⚫",
    "rb leipzig": "⚪🔴",
    "psg": "🔵🔴",
    "paris saint-germain": "🔵🔴",
    "juventus": "⚫⚪",
    "inter": "🔵⚫",
    "inter de milao": "🔵⚫",
    "ac milan": "🔴⚫",
    "milan": "🔴⚫",
    "napoli": "🔵⚪",
    "roma": "🔴🟡",
    "lazio": "🩵⚪",
    "atalanta": "🔵⚫",
    "benfica": "🔴⚪",
    "porto": "🔵⚪",
    "sporting": "🟢⚪",
    "sporting cp": "🟢⚪",
    "ajax": "🔴⚪",
    "psv": "🔴⚪",
    "feyenoord": "🔴⚪",
    "galatasaray": "🔴🟡",
    "fenerbahce": "🟡🔵",
    "besiktas": "⚫⚪",
    "bologna": "🔴🔵",
    "monaco": "🔴⚪",
    "lille": "🔴⚪",
    "marseille": "🩵⚪",
    "olympique de marseille": "🩵⚪",
    "lyon": "🔴🔵",
    # South America (Libertadores & Sudamericana)
    "river plate": "⚪🔴",
    "boca juniors": "🔵🟡",
    "racing": "🩵⚪",
    "racing club": "🩵⚪",
    "independiente": "🔴",
    "san lorenzo": "🔴🔵",
    "estudiantes": "🔴⚪",
    "rosario central": "🟡🔵",
    "velez sarsfield": "🔵⚪",
    "talleres": "🔵⚪",
    "argentinos juniors": "🔴⚪",
    "lanus": "🔴⚪",
    "nacional": "🔵⚪🔴",
    "penarol": "🟡⚫",
    "colo colo": "⚫⚪",
    "universidad de chile": "🔵🔴",
    "universidad catolica": "🔵⚪",
    "olimpia": "⚫⚪",
    "cerro porteno": "🔵🔴",
    "libertad": "⚫⚪",
    "ldu": "⚪🔴",
    "independiente del valle": "🔵⚫",
    "barcelona sc": "🟡⚫",
    "emelec": "🔵⚪",
    "bolivar": "🩵",
    "the strongest": "🟡⚫",
    "universitario": "🔴⚪",
    "alianza lima": "🔵⚪",
    "sporting cristal": "🩵⚪",
    "deportivo tachira": "🟡⚫",
    "caracas": "🔴⚫",
    "millonarios": "🔵⚪",
    "atletico nacional": "🔵⚪",
    "america de cali": "🟢⚪",
    "junior": "🔴⚪",
}

def _get_team_emojis(team_name: str) -> str:
    if not team_name:
        return ""
    key = _ascii_key(team_name).lower()
    return TEAM_COLORS.get(key, "")


@dataclass(frozen=True)
class XPostDraft:
    match_key: str
    match_label: str
    market_count: int
    text: str

    @property
    def char_count(self) -> int:
        return len(self.text)


def _clean(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "n/d"}:
        return ""
    return " ".join(text.split())


def _number(value: object, decimals: int) -> str:
    text = _clean(value).replace(",", ".")
    if not text:
        return ""
    try:
        return f"{float(text):.{decimals}f}"
    except ValueError:
        return _clean(value)


def _match_key(row: pd.Series) -> str:
    source_match_id = _clean(row.get("_source_match_id"))
    if source_match_id:
        return source_match_id
    return "|".join(_clean(row.get(column)) for column in ("Data", "Liga", "Casa", "Fora"))


def _match_label(rows: pd.DataFrame) -> str:
    row = rows.iloc[0]
    home = _clean(row.get("Casa"))
    away = _clean(row.get("Fora"))
    
    if home and away:
        home_emojis = _get_team_emojis(home)
        away_emojis = _get_team_emojis(away)
        home_part = f"{home_emojis} {home}".strip() if home_emojis else home
        away_part = f"{away} {away_emojis}".strip() if away_emojis else away
        return f"{home_part} x {away_part}"
    return home or away or "Jogo"


def _ascii_key(value: object) -> str:
    text = normalize("NFKD", _clean(value)).encode("ascii", "ignore").decode("ascii")
    return text.lower()


def _short_team(value: object) -> str:
    text = _clean(value)
    if len(text) <= 14:
        return text
    words = text.split()
    if len(words) >= 2:
        return f"{words[0]} {words[1][0]}."
    return text[:14].rstrip()


def _short_person(value: object) -> str:
    text = _clean(value)
    if len(text) <= 12:
        return text
    words = text.split()
    if len(words) >= 2:
        return f"{words[0][0]}.{words[-1]}"
    return text[:12].rstrip()


def _compact_match_label(rows: pd.DataFrame) -> str:
    row = rows.iloc[0]
    home_raw = _clean(row.get("Casa"))
    away_raw = _clean(row.get("Fora"))
    home = _short_team(home_raw)
    away = _short_team(away_raw)
    
    if home and away:
        home_emojis = _get_team_emojis(home_raw)
        away_emojis = _get_team_emojis(away_raw)
        home_part = f"{home_emojis} {home}".strip() if home_emojis else home
        away_part = f"{away} {away_emojis}".strip() if away_emojis else away
        return f"{home_part} x {away_part}"
    return home or away or "Jogo"


def _market_subject(row: pd.Series) -> str:
    row_type = _clean(row.get("Tipo"))
    if row_type == "Jogador":
        return _clean(row.get("Jogador")) or _clean(row.get("Time"))
    if row_type == "Time":
        return _clean(row.get("Time"))
    team = _clean(row.get("Time"))
    return "" if team == "Jogo" else team


def _compact_subject(row: pd.Series) -> str:
    row_type = _clean(row.get("Tipo"))
    if row_type == "Jogador":
        return _short_person(row.get("Jogador")) or _short_team(row.get("Time"))
    if row_type == "Time":
        return _short_team(row.get("Time"))
    team = _clean(row.get("Time"))
    return "" if team == "Jogo" else _short_team(team)


def _compact_market(value: object) -> str:
    key = _ascii_key(value)
    if key in COMPACT_MARKETS:
        return COMPACT_MARKETS[key]
    text = _clean(value)
    if len(text) <= 12:
        return text
    words = text.split()
    return "".join(word[0].upper() for word in words if word[:1].isalnum())[:10] or text[:10].rstrip()


def _compact_pick(value: object, subject: str) -> str:
    text = _clean(value)
    if subject and _ascii_key(text) == _ascii_key(subject):
        return ""
    key = _ascii_key(text)
    if key == "over":
        return "O"
    if key == "under":
        return "U"
    if key == "sim":
        return "Sim"
    if key in {"nao", "não"}:
        return "Nao"
    text = text.replace(" e ", "/")
    return text if len(text) <= 14 else text[:14].rstrip()


def _market_line(row: pd.Series) -> str:
    market = _clean(row.get("Mercado"))
    selection = _selection_text(row)
    odd = _number(row.get("ODD"), 2)
    parts = [part for part in (market, selection, "ODD" if odd else "", odd) if part]
    return " - ".join(parts)


def _selection_text(row: pd.Series) -> str:
    subject = _market_subject(row)
    pick = _clean(row.get("Pick"))
    line = _clean(row.get("Linha"))
    parts: list[str] = []
    if subject and (not pick or _ascii_key(pick) != _ascii_key(subject)):
        parts.append(subject)
    if pick:
        parts.append(pick)
    if line:
        parts.append(line)
    if not parts and subject:
        parts.append(subject)
    return " ".join(parts).upper()


def _compact_market_line(row: pd.Series) -> str:
    market = _compact_market(row.get("Mercado"))
    selection = _compact_selection_text(row)
    odd = _number(row.get("ODD"), 2)
    parts = [part for part in (market, selection, "ODD" if odd else "", odd) if part]
    return " - ".join(parts)


def _compact_selection_text(row: pd.Series) -> str:
    subject = _compact_subject(row)
    raw_subject = _market_subject(row)
    pick = _compact_pick(row.get("Pick"), raw_subject or subject)
    line = _clean(row.get("Linha"))
    pick_line = f"{pick}{line}" if pick in {"O", "U"} and line else " ".join(part for part in (pick, line) if part)
    raw_pick = _clean(row.get("Pick"))
    parts: list[str] = []
    if subject and (not raw_pick or _ascii_key(raw_pick) != _ascii_key(raw_subject)):
        parts.append(subject)
    if pick_line:
        parts.append(pick_line)
    if not parts and subject:
        parts.append(subject)
    return " ".join(parts).upper()


def _with_hit_percentage(text: str) -> str:
    def add_percentage(match: re.Match[str]) -> str:
        hits = int(match.group(1))
        total = int(match.group(2))
        if total <= 0:
            return match.group(0)
        percent = (hits / total) * 100
        percent_text = str(int(percent)) if percent.is_integer() else f"{percent:.1f}"
        return f"{match.group(0)} ({percent_text}%)"

    return re.sub(r"Acertos\s+(\d+)/(\d+)(?!\s*\()", add_percentage, text)


def _reason_text(row: pd.Series) -> str:
    reason = _clean(row.get("Motivo"))
    if not reason:
        return ""
    parts: list[str] = []
    for raw_part in reason.split("|"):
        part = _clean(raw_part)
        if not part:
            continue
        key = _ascii_key(part)
        if key.startswith("fonte:"):
            continue
        if key.startswith("criterio:"):
            continue
        if key.startswith("filtro:"):
            part = _clean(part.split(":", 1)[1])
        part = _with_hit_percentage(part)
        if part:
            parts.append(part)
    return " | ".join(parts)


def _post_text(label: str, datetime_league: str, line: str, reason: str) -> str:
    blocks = [label]
    if datetime_league:
        blocks.append(datetime_league)
    if line:
        blocks.append(line)
    if reason:
        blocks.append(f"Motivo: {reason}")
    return "\n\n".join(blocks)


def _fit_compact_post_text(label: str, datetime_league: str, line: str, reason: str, max_chars: int) -> str:
    text = _post_text(label, datetime_league, line, reason)
    if len(text) <= max_chars:
        return text
    text = _post_text(label, "", line, reason)
    if len(text) <= max_chars:
        return text
    prefix = _post_text(label, "", line, "")
    if len(prefix) >= max_chars:
        return prefix[:max_chars].rstrip()
    if reason:
        reason_prefix = f"{prefix}\n\nMotivo: "
        room = max_chars - len(reason_prefix)
        if room > 3:
            return f"{reason_prefix}{reason[: room - 3].rstrip()}..."
    return prefix[:max_chars].rstrip()


def build_best_bet_x_posts(rows: pd.DataFrame, max_chars: int = 280) -> list[XPostDraft]:
    if rows.empty:
        return []
    drafts: list[XPostDraft] = []
    for index, row in rows.reset_index(drop=True).iterrows():
        row_frame = pd.DataFrame([row])
        match_key = _match_key(row)
        label = _match_label(row_frame)
        league = _clean(row.get("Liga"))
        data = _clean(row.get("Data"))
        
        datetime_league = f"{data} - {league}" if data and league else data or league
        
        line = _market_line(row)
        reason = _reason_text(row)
        text = _post_text(label, datetime_league, line, reason)
        if len(text) > max_chars:
            compact_label = _compact_match_label(row_frame)
            compact_line = _compact_market_line(row)
            text = _fit_compact_post_text(compact_label, datetime_league, compact_line, reason, max_chars)
            if len(text) > max_chars:
                text = _fit_compact_post_text(compact_label, "", compact_line, reason, max_chars)
        drafts.append(
            XPostDraft(
                match_key=f"{match_key}|{index}",
                match_label=label,
                market_count=1,
                text=text,
            )
        )
    return drafts
