from __future__ import annotations


GAME_COLUMNS = ["Data", "Liga", "Casa", "Fora", "Time", "Mercado", "Pick", "Linha", "ODD", "Score", "Motivo"]
GAME_MARKET_COLUMNS = ["Mercado", "Pick", "Linha", "ODD", "Score", "Motivo"]
TEAM_COLUMNS = ["Time", "Mercado", "Pick", "Linha", "Odd", "Score", "Motivo"]
TEAM_PREDICTION_COLUMNS = ["Time", "Mercado", "Pick", "Linha", "ODD", "Score", "Motivo"]
TEAM_MARKET_COLUMNS = ["Mercado", "Pick", "Linha", "ODD", "Score", "Motivo"]
PLAYER_COLUMNS = ["Jogador", "Time", "Mercado", "Pick", "Linha", "ODD", "Score", "Motivo"]
PLAYER_MARKET_COLUMNS = ["Jogador", "Mercado", "Pick", "Linha", "ODD", "Score", "Motivo"]
BEST_BETS_COLUMNS = [
    "Data",
    "Liga",
    "Casa",
    "Fora",
    "Tipo",
    "Time",
    "Jogador",
    "Mercado",
    "Pick",
    "Linha",
    "ODD",
    "Score",
    "Motivo",
]
PLAYER_REQUESTED_MARKETS = ["Faltas cometidas", "Faltas sofridas", "Finalizações", "Chutes a gol"]
TABLE_5_ROWS_HEIGHT = 215


PLAYER_MARKETS = {
    "players-shots": "Finalizações",
    "playertotals-shots": "Finalizações",
    "betfair-player-shots": "Finalizações",
    "players-shotsongoal": "Chutes a gol",
    "playertotals-shotsongoal": "Chutes a gol",
    "betfair-player-shots-on-target": "Chutes a gol",
    "players-foulscommitted": "Faltas cometidas",
    "playertotals-foulscommitted": "Faltas cometidas",
    "betfair-player-fouls-committed": "Faltas cometidas",
    "betfair-player-fouls-suffered": "Faltas sofridas",
}

POPULAR_PLAYER_MARKETS = {
    "betfair-popular-marcador-a-qualquer-momento": ("Gols", "goals"),
    "betfair-popular-primeiro-jogador-a-marcar": ("Gols", "goals"),
    "betfair-popular-primeiro-marcador-do-gol": ("Gols", "goals"),
    "betfair-popular-assistencia-a-qualquer-momento": ("Assistencias", "assists"),
    "betfair-popular-recebe-um-cartao": ("Cartoes", "cards"),
    "betfair-popular-marca-ou-faz-assistencia": ("Gol ou assistencia", "goals_or_assists"),
}

MODEL_LINES = {
    "over_15": "1.5",
    "over_25": "2.5",
    "btts": "Sim",
}

TEAM_SCORE_ATTRS = {
    "Gols marcados": "goals_for",
    "Gols sofridos": "goals_against",
    "Escanteios a favor": "corners_for",
    "Escanteios contra": "corners_against",
    "Escanteios totais": "corners_total",
    "Cartões a favor": "cards_for",
    "Cartões contra": "cards_against",
    "Cartões totais": "cards_total",
    "Finalizações Totais": "shots_total_for",
    "Finalizações Contra": "shots_total_against",
    "Finalizações por time": "shots_total_for",
    "Chutes no gol a favor": "shots_on_target_for",
    "Chutes no gol contra": "shots_on_target_against",
    "Chutes no gol por time": "shots_on_target_for",
    "Impedimentos a favor": "offsides_for",
    "Impedimentos contra": "offsides_against",
    "Arremessos Laterais": "throw_ins_for",
    "Gols no 1º Tempo a favor": "first_half_goals_for",
    "Gols no 1º Tempo contra": "first_half_goals_against",
    "Escanteios no 1º Tempo a favor": "first_half_corners_for",
    "Escanteios no 1º Tempo contra": "first_half_corners_against",
    "xG a favor": "xg_for",
    "xG contra": "xg_against",
    "Faltas cometidas": "fouls_committed",
    "Faltas sofridas": "fouls_suffered",
}

TEAM_STAT_CATEGORIES = [
    ("Gols marcados", "goals_for"),
    ("Gols Sofridos", "goals_against"),
    ("Gols no 1º Tempo a favor", "first_half_goals_for"),
    ("Gols no 1º Tempo contra", "first_half_goals_against"),
    ("Escanteios a favor", "corners_for"),
    ("Escanteios contra", "corners_against"),
    ("Escanteios no 1º Tempo a favor", "first_half_corners_for"),
    ("Escanteios no 1º Tempo contra", "first_half_corners_against"),
    ("Cartões a favor", "cards_for"),
    ("Cartões contra", "cards_against"),
    ("Finalizações Totais", "shots_total_for"),
    ("Finalizações Contra", "shots_total_against"),
    ("Chutes no gol a favor", "shots_on_target_for"),
    ("Chutes no gol contra", "shots_on_target_against"),
    ("Impedimentos a favor", "offsides_for"),
    ("Impedimentos contra", "offsides_against"),
    ("Arremessos Laterais", "throw_ins_for"),
    ("Faltas cometidas", "fouls_committed"),
    ("Faltas sofridas", "fouls_suffered"),
    ("xG a favor", "xg_for"),
    ("xG contra", "xg_against"),
]

PLAYER_SCORE_ATTRS = {
    "Gols": "goals",
    "Gol ou assistencia": "goals_or_assists",
    "Assistências": "assists",
    "Finalizações": "shots",
    "Chutes a gol": "shots_on_target",
    "Faltas cometidas": "fouls",
    "Faltas sofridas": "fouls_suffered",
    "Envolvimentos em faltas": "foul_involvements",
    "Cartoes": "cards",
    "Cartão Amarelo": "yellow_cards",
    "Cartão Vermelho": "red_cards",
}

PLAYER_STAT_CATEGORIES = [
    ("Gols", "goals"),
    ("Assistências", "assists"),
    ("Finalizações", "shots"),
    ("Chutes a gol", "shots_on_target"),
    ("Faltas cometidas", "fouls"),
    ("Faltas sofridas", "fouls_suffered"),
    ("Cartão Amarelo", "yellow_cards"),
    ("Cartão Vermelho", "red_cards"),
]

GAME_MARKETS = {
    "totals": "Gols totais",
    "teamtotals-goals-team1": "Gols marcados",
    "teamtotals-goals-team2": "Gols marcados",
    "btts": "Ambas marcam",
    "betfair-result": "Resultado final",
    "betfair-double-chance": "Chance dupla",
    "betfair-draw-no-bet": "Empate sem aposta",
    "betfair-goalkeeper-saves": "Defesas do goleiro",
    "betfair-team-shots": "Finalizações por time",
    "betfair-team-shots-on-target": "Chutes no gol por time",
    "totals-corners": "Escanteios totais",
    "teamtotals-corners-team1": "Escanteios a favor",
    "teamtotals-corners-team2": "Escanteios a favor",
    "totals-bookings": "Cartões totais",
    "teamtotals-bookings-team1": "Cartões a favor",
    "teamtotals-bookings-team2": "Cartões a favor",
}

GAME_SECTIONS = ["Gols", "Escanteios", "Cartões", "Outros"]
SOURCE_PRIORITY = {"espn": 0}
SOURCE_LABELS = {"espn": "ESPN"}
MIN_SCORE_SAMPLES = 3
SCORE_SAMPLE_LIMIT = 10
STATS_DISPLAY_GAMES = SCORE_SAMPLE_LIMIT
UNSUPPORTED_COMPOUND_MARKET_TOKENS = (
    "cotacoes aumentadas",
    "combinadas",
    "combinadas especiais",
    "escanteios e cartoes",
    "cabec",
    "fora da area",
)
UNSUPPORTED_PLAYER_PERIOD_TOKENS = (
    "1o tempo",
    "1 tempo",
    "primeiro tempo",
    "2o tempo",
    "2 tempo",
    "segundo tempo",
)
