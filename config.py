from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


load_dotenv(encoding="utf-8-sig")


ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
LOG_DIR = ROOT_DIR / "logs"


@dataclass(frozen=True)
class FootballLeagueConfig:
    name: str
    country: str
    espn_slug: str
    espn_season: int
    betfair_competition_url: str | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8-sig", extra="ignore")

    app_db_url: str = Field(default="sqlite:///data/betsniper.db", alias="APP_DB_URL")
    app_timezone: str = Field(default="America/Sao_Paulo", alias="APP_TIMEZONE")
    dashboard_base_date: str | None = Field(default=None, alias="DASHBOARD_BASE_DATE")

    football_country: str = Field(default="Brazil", alias="FOOTBALL_COUNTRY")
    espn_league_slug: str = Field(default="bra.1", alias="ESPN_LEAGUE_SLUG")
    espn_season: int = Field(default=2026, alias="ESPN_SEASON")

    scraper_headless: bool = Field(default=True, alias="SCRAPER_HEADLESS")
    scraper_min_delay_seconds: int = Field(default=5, alias="SCRAPER_MIN_DELAY_SECONDS")
    scraper_max_delay_seconds: int = Field(default=15, alias="SCRAPER_MAX_DELAY_SECONDS")

    betfair_web_enabled: bool = Field(default=False, alias="BETFAIR_WEB_ENABLED")
    betfair_web_headless: bool = Field(default=True, alias="BETFAIR_WEB_HEADLESS")
    betfair_base_url: str = Field(default="https://www.betfair.bet.br/apostas/", alias="BETFAIR_BASE_URL")
    betfair_competition_url: str | None = Field(default=None, alias="BETFAIR_COMPETITION_URL")
    betfair_username: str | None = Field(default=None, alias="BETFAIR_USERNAME")
    betfair_password: str | None = Field(default=None, alias="BETFAIR_PASSWORD")
    betfair_auto_login: bool = Field(default=True, alias="BETFAIR_AUTO_LOGIN")
    betfair_allow_geolocation: bool = Field(default=True, alias="BETFAIR_ALLOW_GEOLOCATION")
    betfair_geolocation_latitude: str | None = Field(default=None, alias="BETFAIR_GEO_LATITUDE")
    betfair_geolocation_longitude: str | None = Field(default=None, alias="BETFAIR_GEO_LONGITUDE")
    betfair_geolocation_accuracy: int = Field(default=100, alias="BETFAIR_GEO_ACCURACY")
    betfair_geolocation_jitter_meters: int = Field(default=30, alias="BETFAIR_GEO_JITTER_METERS")
    betfair_login_timeout_seconds: int = Field(default=120, alias="BETFAIR_LOGIN_TIMEOUT_SECONDS")
    betfair_storage_state: str = Field(default="data/betfair_storage_state.json", alias="BETFAIR_STORAGE_STATE")
    betfair_event_urls_file: str = Field(default="data/betfair_event_urls.json", alias="BETFAIR_EVENT_URLS_FILE")
    betfair_max_event_pages: int = Field(default=10, alias="BETFAIR_MAX_EVENT_PAGES")
    odds_stale_after_hours: int = Field(default=12, alias="ODDS_STALE_AFTER_HOURS")

    x_auto_publish_enabled: bool = Field(default=False, alias="X_AUTO_PUBLISH_ENABLED")
    x_api_base_url: str = Field(default="https://api.x.com", alias="X_API_BASE_URL")
    x_api_key: str | None = Field(default=None, alias="X_API_KEY")
    x_api_key_secret: str | None = Field(default=None, alias="X_API_KEY_SECRET")
    x_access_token: str | None = Field(default=None, alias="X_ACCESS_TOKEN")
    x_access_token_secret: str | None = Field(default=None, alias="X_ACCESS_TOKEN_SECRET")
    x_post_delay_seconds: int = Field(default=60, alias="X_POST_DELAY_SECONDS")
    x_post_max_chars: int = Field(default=280, alias="X_POST_MAX_CHARS")
    x_publish_password: str | None = Field(default=None, alias="X_PUBLISH_PASSWORD")


settings = Settings()


def football_leagues() -> tuple[FootballLeagueConfig, ...]:
    return (
        FootballLeagueConfig(
            name="Brazilian Serie A",
            country=settings.football_country,
            espn_slug=settings.espn_league_slug,
            espn_season=settings.espn_season,
            betfair_competition_url=settings.betfair_competition_url,
        ),
        FootballLeagueConfig(
            name="Brazilian Serie B",
            country="Brazil",
            espn_slug="bra.2",
            espn_season=settings.espn_season,
        ),
        FootballLeagueConfig(
            name="Premier League (Inglaterra)",
            country="England",
            espn_slug="eng.1",
            espn_season=2025,
            betfair_competition_url="https://www.betfair.bet.br/apostas/futebol/premier-league/c-10932509",
        ),
        FootballLeagueConfig(
            name="Copa Betano do Brasil",
            country="Brazil",
            espn_slug="bra.copa_do_brazil",
            espn_season=2026,
            betfair_competition_url="https://www.betfair.bet.br/apostas/futebol/copa-do-brasil/c-89219",
        ),
        FootballLeagueConfig(
            name="Copa Libertadores da América",
            country="South America",
            espn_slug="conmebol.libertadores",
            espn_season=2026,
        ),
        FootballLeagueConfig(
            name="Copa Sul Americana",
            country="South America",
            espn_slug="conmebol.sudamericana",
            espn_season=2026,
        ),
        FootballLeagueConfig(
            name="Champions League",
            country="Europe",
            espn_slug="uefa.champions",
            espn_season=2025,
        ),
        FootballLeagueConfig(
            name="Europa League",
            country="Europe",
            espn_slug="uefa.europa",
            espn_season=2025,
        ),
    )


def ensure_runtime_dirs() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)
