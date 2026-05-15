from __future__ import annotations

import logging
import math
import random
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext, Page

from config import ROOT_DIR, settings


log = logging.getLogger(__name__)

BETFAIR_DEFAULT_ORIGINS = ("https://www.betfair.bet.br", "https://www.betfair.com")
USERNAME_SELECTORS = (
    "input[name='username']",
    "input[name='email']",
    "input[id*='username' i]",
    "input[id*='email' i]",
    "input[autocomplete='username']",
    "input[type='email']",
    "input[type='text']",
)
PASSWORD_SELECTORS = (
    "input[name='password']",
    "input[id*='password' i]",
    "input[autocomplete='current-password']",
    "input[type='password']",
)
SUBMIT_SELECTORS = (
    "button[type='submit']",
    "input[type='submit']",
    "[data-testid*='login' i]",
    "[data-test*='login' i]",
)
SUBMIT_LABELS = ("Entrar", "Login", "Log in", "Iniciar sessao", "Iniciar sessão", "Acessar")


def rooted(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else ROOT_DIR / path


def betfair_credentials() -> tuple[str, str] | None:
    username = (settings.betfair_username or "").strip()
    password = settings.betfair_password or ""
    if username and password:
        return username, password
    return None


def _parse_float(value: str | None, name: str) -> float | None:
    if value is None or not str(value).strip():
        return None
    try:
        return float(str(value).strip().replace(",", "."))
    except ValueError:
        log.warning("%s invalido: %s", name, value)
        return None


def betfair_geolocation() -> dict[str, float] | None:
    latitude = _parse_float(settings.betfair_geolocation_latitude, "BETFAIR_GEO_LATITUDE")
    longitude = _parse_float(settings.betfair_geolocation_longitude, "BETFAIR_GEO_LONGITUDE")
    if latitude is None and longitude is None:
        return None
    if latitude is None or longitude is None:
        log.warning("BETFAIR_GEO_LATITUDE e BETFAIR_GEO_LONGITUDE devem ser configurados juntos.")
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        log.warning("Coordenadas Betfair fora do intervalo valido.")
        return None
    latitude, longitude = _jitter_coordinates(latitude, longitude)
    return {
        "latitude": latitude,
        "longitude": longitude,
        "accuracy": float(settings.betfair_geolocation_accuracy),
    }


def _jitter_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    max_meters = max(0, min(int(settings.betfair_geolocation_jitter_meters), 30))
    if max_meters <= 0:
        return latitude, longitude
    distance = max_meters * math.sqrt(random.random())
    bearing = random.uniform(0, 2 * math.pi)
    lat_delta = (distance * math.cos(bearing)) / 111_320
    lon_scale = 111_320 * max(math.cos(math.radians(latitude)), 0.01)
    lon_delta = (distance * math.sin(bearing)) / lon_scale
    return latitude + lat_delta, longitude + lon_delta


def betfair_context_options(storage_state: Path | None = None) -> dict[str, Any]:
    options: dict[str, Any] = {
        "ignore_https_errors": True,
        "locale": "pt-BR",
        "timezone_id": settings.app_timezone,
        "viewport": {"width": 1440, "height": 1200},
    }
    if storage_state and storage_state.exists():
        options["storage_state"] = str(storage_state)
    if settings.betfair_allow_geolocation:
        options["permissions"] = ["geolocation"]
        geolocation = betfair_geolocation()
        if geolocation:
            options["geolocation"] = geolocation
    return options


def betfair_origins() -> list[str]:
    origins = set(BETFAIR_DEFAULT_ORIGINS)
    for url in (settings.betfair_base_url, settings.betfair_competition_url):
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            origins.add(f"{parsed.scheme}://{parsed.netloc}")
    return sorted(origins)


def grant_betfair_geolocation(context: BrowserContext) -> None:
    if not settings.betfair_allow_geolocation:
        return
    for origin in betfair_origins():
        try:
            context.grant_permissions(["geolocation"], origin=origin)
        except Exception as exc:
            log.debug("Falha ao liberar geolocalizacao Betfair para %s: %s", origin, exc)


def is_betfair_login_page(page: Page) -> bool:
    try:
        title = page.title().lower()
        url = page.url.lower()
        if "login" in title and "betfair" in title:
            return True
        if "login" in url and "betfair" in url:
            return True
        if _has_password_field(page):
            return True
        text = page.locator("body").inner_text(timeout=1500).lower()
        return "login na betfair" in text or "novo no betfair" in text
    except Exception:
        return False


def ensure_betfair_login(page: Page, storage_state: Path, return_url: str | None = None, force: bool = False) -> bool:
    if not settings.betfair_auto_login:
        return not is_betfair_login_page(page)
    if not force and not is_betfair_login_page(page):
        return True

    credentials = betfair_credentials()
    if not credentials:
        log.warning("Betfair pediu login, mas BETFAIR_USERNAME/BETFAIR_PASSWORD nao estao configurados.")
        return False

    username, password = credentials
    log.info("Betfair pediu login. Tentando login automatico.")
    _open_login_form(page)
    if not _fill_login_form(page, username, password):
        log.warning("Nao foi possivel preencher o formulario de login da Betfair.")
        return False

    if not _submit_login_form(page):
        log.warning("Nao foi possivel enviar o formulario de login da Betfair.")
        return False

    logged_in = wait_for_betfair_login(page, settings.betfair_login_timeout_seconds)
    if not logged_in:
        log.warning(
            "Login Betfair nao confirmou em %ss. Se houver captcha/2FA, rode com BETFAIR_WEB_HEADLESS=false.",
            settings.betfair_login_timeout_seconds,
        )
        return False

    storage_state.parent.mkdir(parents=True, exist_ok=True)
    page.context.storage_state(path=str(storage_state))
    log.info("Sessao Betfair salva em %s", storage_state)
    if return_url:
        page.goto(return_url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(3000)
    return True


def wait_for_betfair_login(page: Page, timeout_seconds: int) -> bool:
    deadline = time.monotonic() + max(timeout_seconds, 1)
    while time.monotonic() < deadline:
        if not is_betfair_login_page(page):
            return True
        page.wait_for_timeout(1000)
    return not is_betfair_login_page(page)


def _contexts(page: Page) -> list[Any]:
    return [page, *page.frames]


def _has_password_field(page: Page) -> bool:
    for context in _contexts(page):
        for selector in PASSWORD_SELECTORS:
            try:
                if context.locator(selector).first.is_visible(timeout=500):
                    return True
            except Exception:
                continue
    return False


def _open_login_form(page: Page) -> None:
    if _has_password_field(page):
        return
    for context in _contexts(page):
        for label in SUBMIT_LABELS:
            try:
                context.get_by_text(label, exact=False).first.click(timeout=1500)
                page.wait_for_timeout(1000)
                if _has_password_field(page):
                    return
            except Exception:
                continue


def _fill_login_form(page: Page, username: str, password: str) -> bool:
    username_filled = _fill_first(page, USERNAME_SELECTORS, username)
    password_filled = _fill_first(page, PASSWORD_SELECTORS, password)
    return username_filled and password_filled


def _fill_first(page: Page, selectors: tuple[str, ...], value: str) -> bool:
    for context in _contexts(page):
        for selector in selectors:
            try:
                locator = context.locator(selector).first
                locator.fill(value, timeout=2500)
                return True
            except Exception:
                continue
    return False


def _submit_login_form(page: Page) -> bool:
    for context in _contexts(page):
        for selector in SUBMIT_SELECTORS:
            try:
                context.locator(selector).first.click(timeout=2500)
                page.wait_for_timeout(1000)
                return True
            except Exception:
                continue
        for label in SUBMIT_LABELS:
            try:
                context.get_by_text(label, exact=False).first.click(timeout=2500)
                page.wait_for_timeout(1000)
                return True
            except Exception:
                continue
    for context in _contexts(page):
        for selector in PASSWORD_SELECTORS:
            try:
                context.locator(selector).first.press("Enter", timeout=2500)
                page.wait_for_timeout(1000)
                return True
            except Exception:
                continue
    return False
