from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint

from src.time_utils import utc_now


class Team(SQLModel, table=True):
    __tablename__ = "teams"
    __table_args__ = {"extend_existing": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    source: str = Field(index=True)
    source_team_id: str = Field(index=True)
    name: str = Field(index=True)
    country: str | None = None
    created_at: datetime = Field(default_factory=utc_now)

    __table_args__ = (UniqueConstraint("source", "source_team_id", name="uq_team_source_id"), {"extend_existing": True})


class Player(SQLModel, table=True):
    __tablename__ = "players"
    __table_args__ = {"extend_existing": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    source: str = Field(index=True)
    source_player_id: str = Field(index=True)
    name: str = Field(index=True)
    team_name: str | None = None
    created_at: datetime = Field(default_factory=utc_now)

    __table_args__ = (UniqueConstraint("source", "source_player_id", name="uq_player_source_id"), {"extend_existing": True})


class Match(SQLModel, table=True):
    __tablename__ = "matches"
    __table_args__ = {"extend_existing": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    source: str = Field(index=True)
    source_match_id: str = Field(index=True)
    league_id: int = Field(index=True)
    league_name: str
    season: int = Field(index=True)
    target_date: str = Field(index=True)
    kickoff_at: datetime | None = Field(default=None, index=True)
    status: str | None = None
    home_team: str = Field(index=True)
    away_team: str = Field(index=True)
    home_score: int | None = None
    away_score: int | None = None
    raw_json: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    __table_args__ = (UniqueConstraint("source", "source_match_id", name="uq_match_source_id"), {"extend_existing": True})


class OddsSnapshot(SQLModel, table=True):
    __tablename__ = "odds_snapshots"
    __table_args__ = {"extend_existing": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    source: str = Field(index=True)
    source_match_id: str | None = Field(default=None, index=True)
    bookmaker: str = Field(index=True)
    market_key: str = Field(index=True)
    outcome_name: str
    price: float | None = None
    point: float | None = None
    fetched_at: datetime = Field(default_factory=utc_now, index=True)
    raw_json: str | None = None
    raw_home_team: str | None = Field(default=None, index=True)
    raw_away_team: str | None = Field(default=None, index=True)
    commence_time: str | None = None
    market_name: str | None = Field(default=None, index=True)
    market_type: str | None = None
    market_category: str | None = None
    team_side: str | None = None
    team_name: str | None = Field(default=None, index=True)
    player_name: str | None = Field(default=None, index=True)
    player_id: str | None = None
    main_line: str | None = None
    market_id: str | None = None
    market_type_raw: str | None = None
    selection_id: str | None = None
    runner_name: str | None = None
    runner_handicap: float | None = None


class TeamStat(SQLModel, table=True):
    __tablename__ = "team_stats"
    __table_args__ = {"extend_existing": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    source: str = Field(index=True)
    source_match_id: str = Field(index=True)
    team_name: str = Field(index=True)
    opponent_name: str | None = None
    match_date: str = Field(index=True)
    is_home: bool = False
    goals_for: int | None = None
    goals_against: int | None = None
    btts: bool | None = None
    over_15: bool | None = None
    over_25: bool | None = None
    corners_for: int | None = None
    corners_against: int | None = None
    cards_for: int | None = None
    cards_against: int | None = None
    shots_total_for: int | None = None
    shots_total_against: int | None = None
    shots_on_target_for: int | None = None
    shots_on_target_against: int | None = None
    offsides_for: int | None = None
    offsides_against: int | None = None
    throw_ins_for: int | None = None
    first_half_goals_for: int | None = None
    first_half_goals_against: int | None = None
    first_half_corners_for: int | None = None
    first_half_corners_against: int | None = None
    xg_for: float | None = None
    xg_against: float | None = None
    fouls_committed: int | None = None
    fouls_suffered: int | None = None
    raw_json: str | None = None
    created_at: datetime = Field(default_factory=utc_now)

    __table_args__ = (UniqueConstraint("source", "source_match_id", "team_name", name="uq_team_stat"), {"extend_existing": True})


class PlayerStat(SQLModel, table=True):
    __tablename__ = "player_stats"
    __table_args__ = {"extend_existing": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    source: str = Field(index=True)
    source_match_id: str = Field(index=True)
    player_name: str = Field(index=True)
    team_name: str | None = Field(default=None, index=True)
    match_date: str = Field(index=True)
    minutes: int | None = None
    goals: int | None = None
    assists: int | None = None
    shots: int | None = None
    shots_on_target: int | None = None
    fouls: int | None = None
    fouls_suffered: int | None = None
    tackles: int | None = None
    cards: int | None = None
    yellow_cards: int | None = None
    red_cards: int | None = None
    raw_json: str | None = None
    created_at: datetime = Field(default_factory=utc_now)

    __table_args__ = (UniqueConstraint("source", "source_match_id", "player_name", name="uq_player_stat"), {"extend_existing": True})


class PlayerLineup(SQLModel, table=True):
    __tablename__ = "player_lineups"

    id: Optional[int] = Field(default=None, primary_key=True)
    source: str = Field(index=True)
    source_match_id: str = Field(index=True)
    player_id: str | None = Field(default=None, index=True)
    player_name: str = Field(index=True)
    team_name: str = Field(index=True)
    starter: bool = Field(default=False, index=True)
    position: str | None = None
    jersey: str | None = None
    raw_json: str | None = None
    created_at: datetime = Field(default_factory=utc_now)

    __table_args__ = (
        UniqueConstraint("source", "source_match_id", "player_name", "team_name", name="uq_player_lineup"),
        {"extend_existing": True},
    )


class AnalysisResult(SQLModel, table=True):
    __tablename__ = "analysis_results"

    id: Optional[int] = Field(default=None, primary_key=True)
    target_date: str = Field(index=True)
    source_match_id: str = Field(index=True)
    league_name: str
    home_team: str
    away_team: str
    market_key: str = Field(index=True)
    pick: str
    score: float = Field(index=True)
    home_hit_rate: float | None = None
    away_hit_rate: float | None = None
    sample_size: int = 10
    reason: str | None = None
    created_at: datetime = Field(default_factory=utc_now, index=True)

    __table_args__ = (
        UniqueConstraint("target_date", "source_match_id", "market_key", "pick", name="uq_analysis_pick"),
        {"extend_existing": True},
    )


class FetchCache(SQLModel, table=True):
    __tablename__ = "fetch_cache"
    __table_args__ = {"extend_existing": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    source: str = Field(index=True)
    cache_key: str = Field(index=True, unique=True)
    endpoint_or_url: str
    params_hash: str
    status_code: int | None = None
    body: str
    fetched_at: datetime = Field(default_factory=utc_now, index=True)
    expires_at: datetime | None = Field(default=None, index=True)


class EntityAlias(SQLModel, table=True):
    __tablename__ = "entity_aliases"
    __table_args__ = {"extend_existing": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    entity_type: str = Field(index=True)
    canonical_name: str = Field(index=True)
    alias: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=utc_now)
