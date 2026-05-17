from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus, unquote, urljoin, urlparse

import httpx
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, Response, sync_playwright
from sqlmodel import Session, select

from config import ROOT_DIR, settings
from src.collectors.betfair_auth import (
    betfair_context_options,
    betfair_credentials,
    ensure_betfair_login,
    grant_betfair_geolocation,
    is_betfair_login_page,
)
from src.collectors.playwright_runtime import chromium_launch_options
from src.db.models import Match
from src.time_utils import match_kickoff_is_expired


log = logging.getLogger(__name__)


DEFAULT_COMPETITION_URL = "https://www.betfair.bet.br/apostas/futebol/brasileir%C3%A3o-s%C3%A9rie-a/c-13"
POPULAR_TAB_ID = "Z-bW5BIAACIAOhai"
SMP_PRICES_URL = "https://smp.betfair.bet.br/www/sports/fixedodds/readonly/v1/getMarketPrices"
BFF_CARD_DOCUMENT_ID = "Card#2cb9a894754301e94e941b59a9fe938f"


TARGET_TEXT = {
    "ambas marcam",
    "both teams",
    "chance dupla",
    "defesa",
    "defesas",
    "double chance",
    "goals",
    "gols",
    "total goals",
    "resultado",
    "corners",
    "escanteios",
    "cards",
    "cartoes",
    "bookings",
    "shots",
    "chute",
    "chutes no gol",
    "finalizacoes",
    "shots on target",
    "chutes a gol",
    "fouls",
    "faltas",
}


@dataclass
class BetfairMatch:
    source_match_id: str
    home_team: str
    away_team: str
    commence_time: str | None

    @property
    def label(self) -> str:
        return f"{self.home_team} x {self.away_team}"


class BetfairWebClient:
    source = "betfair-web"

    def __init__(
        self,
        session: Session,
        target_date: str,
        league_name: str | None = None,
        competition_url: str | None = None,
    ):
        self.session = session
        self.target_date = target_date
        self.league_name = league_name
        self.competition_url = competition_url
        self.storage_state = self._rooted(settings.betfair_storage_state)
        self.event_urls_file = self._rooted(settings.betfair_event_urls_file)

    def odds(self) -> list[dict[str, Any]]:
        if not settings.betfair_web_enabled:
            log.info("BETFAIR_WEB_ENABLED=false. Pulando Betfair web.")
            return []

        matches = self._target_matches()
        if not matches:
            return []

        with sync_playwright() as p:
            browser = p.chromium.launch(**chromium_launch_options(headless=settings.betfair_web_headless))
            context = browser.new_context(**betfair_context_options(self.storage_state))
            grant_betfair_geolocation(context)
            page = context.new_page()

            events: list[dict[str, Any]] = []
            try:
                self._open_seed(page)
                self._accept_cookies(page)
                event_url_map = self._event_url_map()
                event_url_map.update(self._discover_event_urls(page, matches))
                for match in matches[: settings.betfair_max_event_pages]:
                    events.extend(self._scrape_match(page, match, event_url_map.get(self._norm(match.label))))
                    time.sleep(1.0)
            finally:
                context.close()
                browser.close()

        return [event for event in events if event.get("bookmakers")]

    def _scrape_match(self, page: Page, match: BetfairMatch, mapped_url: str | None) -> list[dict[str, Any]]:
        payloads: list[Any] = []

        def on_response(response: Response) -> None:
            content_type = response.headers.get("content-type", "")
            if "json" not in content_type:
                return
            url = response.url.lower()
            if "betfair" not in url and "sports" not in url:
                return
            try:
                data = response.json()
            except Exception:
                return
            text = json.dumps(data, ensure_ascii=False).lower()
            if "getmarketprices" in url or "smp.betfair" in url or self._looks_related(text, match):
                payloads.append(data)

        page.on("response", on_response)
        try:
            pre_rows: list[dict[str, Any]] = []
            popular_rows: list[dict[str, Any]] = []
            event_url = mapped_url or self._find_event_url(page, match)
            if event_url:
                log.info("Betfair URL: %s -> %s", match.label, event_url)
                popular_rows = self._rows_from_popular_html(event_url, match)
                try:
                    self._safe_goto(page, self._popular_url(event_url))
                except Exception as exc:
                    log.warning("Betfair navegação falhou: %s | %s", match.label, exc)
                    rows = self._dedupe_rows(popular_rows)
                    return [self._event_from_rows(match, rows)] if rows else []
                pre_rows = self._rows_from_dom(page, match)
                self._expand_markets(page)
            else:
                self._search_match(page, match)
                event_url = self._find_event_url(page, match)
                if not event_url:
                    log.warning("Betfair URL nao encontrada: %s", match.label)
                    return []
                log.info("Betfair URL via busca: %s -> %s", match.label, event_url)
                popular_rows = self._rows_from_popular_html(event_url, match)
                pre_rows = self._rows_from_dom(page, match)
                self._expand_markets(page)
            time.sleep(3.0)
            rows = popular_rows + pre_rows + self._rows_from_payloads(payloads, match)
            rows.extend(self._rows_from_dom(page, match))
            rows = self._dedupe_rows(rows)
            return [self._event_from_rows(match, rows)] if rows else []
        finally:
            page.remove_listener("response", on_response)

    def _target_matches(self) -> list[BetfairMatch]:
        query = select(Match).where(Match.target_date == self.target_date)
        if self.league_name:
            query = query.where(Match.league_name == self.league_name)
        rows = self.session.exec(query.order_by(Match.kickoff_at)).all()
        active_rows = [row for row in rows if not match_kickoff_is_expired(row.kickoff_at)]
        expired_count = len(rows) - len(active_rows)
        if expired_count:
            log.info("Betfair ignorou %s jogo(s) com inicio ha mais de 2h.", expired_count)
        return [
            BetfairMatch(
                source_match_id=row.source_match_id,
                home_team=row.home_team,
                away_team=row.away_team,
                commence_time=row.kickoff_at.isoformat() if row.kickoff_at else None,
            )
            for row in active_rows
        ]

    def _event_url_map(self) -> dict[str, str]:
        if not self.event_urls_file.exists():
            return {}
        try:
            raw = json.loads(self.event_urls_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {self._norm(key): str(value) for key, value in raw.items() if value}

    def _open_seed(self, page: Page) -> None:
        url = self.competition_url or settings.betfair_competition_url or DEFAULT_COMPETITION_URL
        self._safe_goto(page, url)
        should_login = self._is_login_page(page) or (
            settings.betfair_auto_login and betfair_credentials() is not None and not self.storage_state.exists()
        )
        if should_login:
            logged_in = ensure_betfair_login(page, self.storage_state, url, force=not self._is_login_page(page))
            if not logged_in:
                log.warning(
                    "Betfair abriu tela de login e o login automatico nao concluiu. "
                    "Confira BETFAIR_USERNAME/BETFAIR_PASSWORD ou rode scripts\\betfair_login.py."
                )

    def _safe_goto(self, page: Page, url: str) -> None:
        last_error: Exception | None = None
        for wait_until in ["domcontentloaded", "commit"]:
            for _ in range(2):
                try:
                    page.goto(url, wait_until=wait_until, timeout=60_000)
                    page.wait_for_timeout(8000)
                    self._accept_cookies(page)
                    page.wait_for_timeout(1000)
                    return
                except PlaywrightError as exc:
                    last_error = exc
                    if "ERR_QUIC_PROTOCOL_ERROR" not in str(exc):
                        break
                    page.wait_for_timeout(1500)
                except Exception as exc:
                    last_error = exc
                    break
        if last_error:
            raise last_error

    def _accept_cookies(self, page: Page) -> None:
        for label in ["Aceitar todos os cookies", "Aceitar", "Accept", "I agree", "Concordo"]:
            try:
                page.get_by_text(label, exact=False).first.click(timeout=1500, force=True)
                return
            except Exception:
                continue

    @staticmethod
    def _is_login_page(page: Page) -> bool:
        return is_betfair_login_page(page)

    def _find_event_url(self, page: Page, match: BetfairMatch) -> str | None:
        candidates = page.locator("a[href]").evaluate_all(
            """links => links.map(a => ({href: a.href, text: (a.innerText || a.textContent || '').trim()}))"""
        )
        for item in candidates:
            text = self._norm(item.get("text"))
            href = item.get("href")
            if href and self._event_text_matches(text, match):
                return str(href)
        home = self._norm(match.home_team)
        away = self._norm(match.away_team)
        for item in candidates:
            text = self._norm(item.get("text"))
            href = item.get("href")
            if href and (home in text or away in text) and self._looks_like_event_url(str(href)):
                return str(href)
        return None

    def _discover_event_urls(self, page: Page, matches: list[BetfairMatch]) -> dict[str, str]:
        found = self._discover_event_urls_from_html(matches)
        try:
            candidates = page.locator("a[href]").evaluate_all(
                """links => links.map(a => ({href: a.href, text: (a.innerText || a.textContent || '').trim()}))"""
            )
        except Exception:
            candidates = []
        for match in matches:
            key = self._norm(match.label)
            if key in found:
                continue
            home = self._norm(match.home_team)
            away = self._norm(match.away_team)
            for item in candidates:
                text = self._norm(item.get("text"))
                href = str(item.get("href") or "")
                if href and self._event_text_matches(text, match):
                    found[key] = href
                    break
        if found:
            log.info("Betfair URLs descobertas: %s", len(found))
            self._save_event_url_map(found)
        return found

    def _discover_event_urls_from_html(self, matches: list[BetfairMatch]) -> dict[str, str]:
        url = self.competition_url or settings.betfair_competition_url or DEFAULT_COMPETITION_URL
        try:
            response = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30, follow_redirects=True)
            response.raise_for_status()
        except Exception as exc:
            log.warning("Betfair HTML competicao falhou: %s", exc)
            return {}

        events: list[tuple[str, str]] = []
        for item in self._sports_events_from_html(response.text, url):
            event_url = item.get("url") or self._event_url(item["name"], item["event_id"])
            events.append((item["name"], event_url))

        found: dict[str, str] = {}
        for match in matches:
            key = self._norm(match.label)
            for event_name, event_url in events:
                if self._event_text_matches(event_name, match):
                    found[key] = event_url
                    break
        return found

    def _sports_events_from_html(self, text: str, base_url: str) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        pattern = re.compile(
            r'"eventId"\s*:\s*(?P<event_id>\d+)\s*,\s*"name"\s*:\s*"(?P<name>[^"]+?)"',
            re.IGNORECASE,
        )
        for match in pattern.finditer(text):
            name = match.group("name")
            if " x " not in name:
                continue
            rows.append({"event_id": match.group("event_id"), "name": name})
        href_pattern = re.compile(r"""href=["'](?P<href>[^"']*/e-(?P<event_id>\d+)[^"']*)["']""", re.IGNORECASE)
        for match in href_pattern.finditer(text):
            href = unescape(match.group("href"))
            event_url = urljoin(base_url, href)
            parsed = urlparse(event_url)
            slug = unquote(parsed.path.rstrip("/").split("/")[-2] if "/e-" in parsed.path else "")
            name = slug.replace("-", " ")
            if name and " x " in name:
                rows.append({"event_id": match.group("event_id"), "name": name, "url": event_url})
        return rows

    def _event_url(self, event_name: str, event_id: str) -> str:
        slug = self._slug(event_name)
        base_url = self.competition_url or settings.betfair_competition_url or DEFAULT_COMPETITION_URL
        parsed = urlparse(base_url)
        competition_path = parsed.path.rsplit("/", 1)[0].strip("/")
        return f"{parsed.scheme}://{parsed.netloc}/{competition_path}/{quote(slug)}/e-{event_id}"

    def _save_event_url_map(self, found: dict[str, str]) -> None:
        current = self._event_url_map()
        current.update(found)
        self.event_urls_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.event_urls_file.write_text(
                json.dumps(current, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            log.warning("Nao salvou URLs Betfair: %s", exc)

    def _search_match(self, page: Page, match: BetfairMatch) -> None:
        queries = [
            quote_plus(f"{match.home_team} {match.away_team}"),
            quote_plus(f"{match.away_team} {match.home_team}"),
        ]
        for query in queries:
            for url in [
                urljoin(settings.betfair_base_url, f"search?q={query}"),
                f"https://www.betfair.bet.br/apostas/search?q={query}",
                f"https://www.betfair.bet.br/apostas/?q={query}",
            ]:
                try:
                    self._safe_goto(page, url)
                    self._expand_markets(page)
                    return
                except Exception:
                    continue

    def _popular_url(self, event_url: str) -> str:
        base = event_url.split("#", 1)[0]
        separator = "&" if "?" in base else "?"
        if "tabId=" not in base:
            base = f"{base}{separator}tabId={POPULAR_TAB_ID}"
        return f"{base}#popular"

    def _rows_from_popular_html(self, event_url: str, match: BetfairMatch) -> list[dict[str, Any]]:
        try:
            response = httpx.get(
                self._popular_url(event_url),
                headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"},
                timeout=30,
                follow_redirects=True,
            )
            response.raise_for_status()
        except Exception as exc:
            log.warning("Betfair popular HTML falhou: %s | %s", match.label, exc)
            return []

        payload = self._preloaded_catalog(response.text)
        env = self._environment(response.text)
        markets = (payload or {}).get("data", {}).get("SportsbookMarket") or []
        rows = self._rows_from_sportsbook_markets(markets, match)
        rows.extend(self._rows_from_bff_popular_cards(payload or {}, env or {}, event_url, match))
        return self._dedupe_rows(rows)

    def _preloaded_catalog(self, html: str) -> dict[str, Any] | None:
        match = re.search(
            r"window\.__TBD_PRELOADED_CATALOG__\s*=\s*(\{.*?\})\s*\n\s*window\.__CONTENT_LOADING_PARAMETERS__",
            html,
            re.DOTALL,
        )
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None

    def _environment(self, html: str) -> dict[str, Any] | None:
        match = re.search(
            r"window\.__TBD_ENVIRONMENT__\s*=\s*(\{.*?\})\s*\n\s*window\.__TBD_PRELOADED_CATALOG__",
            html,
            re.DOTALL,
        )
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None

    def _rows_from_bff_popular_cards(
        self,
        catalog: dict[str, Any],
        env: dict[str, Any],
        event_url: str,
        match: BetfairMatch,
    ) -> list[dict[str, Any]]:
        endpoint_config = (env.get("ENDPOINTS") or {}).get("CATALOGUE") or {}
        endpoint = f"{endpoint_config.get('host', '')}{endpoint_config.get('path', '')}"
        app_key = env.get("APP_KEY")
        urns = self._popular_card_group_urns(catalog)
        if not endpoint or not app_key or not urns:
            return []

        rows: list[dict[str, Any]] = []
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Origin": "https://www.betfair.bet.br",
            "Referer": self._popular_url(event_url),
        }
        params = {"_ak": app_key}
        current_urn = (catalog.get("router") or {}).get("currentUrn")
        if current_urn:
            params["currentViewUrn"] = str(current_urn)

        for index in range(0, len(urns), 8):
            body = {
                "documentId": BFF_CARD_DOCUMENT_ID,
                "variables": {
                    "urn": urns[index : index + 8],
                    "numberOfFilledCardsInCardGroup": 12,
                },
            }
            try:
                response = httpx.post(
                    endpoint,
                    params=params,
                    json=body,
                    headers=headers,
                    timeout=30,
                    follow_redirects=True,
                )
                response.raise_for_status()
                data = response.json()
            except Exception as exc:
                log.warning("Betfair BFF cards falhou: %s | %s", match.label, exc)
                continue
            rows.extend(self._rows_from_sportsbook_markets(self._sportsbook_markets_from_payload(data), match))

        return self._dedupe_rows(rows)

    def _popular_card_group_urns(self, catalog: dict[str, Any]) -> list[str]:
        urns: list[str] = []
        for tab in (catalog.get("data") or {}).get("NavigationTab") or []:
            title = self._translated(tab.get("title"))
            if title and self._norm(title) != "popular":
                continue
            for item in tab.get("items") or []:
                if item.get("typename") == "PebbleCardGroup" and item.get("urn"):
                    urns.append(str(item["urn"]))
        if not urns:
            for group in (catalog.get("data") or {}).get("PebbleCardGroup") or []:
                if group.get("urn"):
                    urns.append(str(group["urn"]))
        return list(dict.fromkeys(urns))

    def _sportsbook_markets_from_payload(self, payload: Any) -> list[dict[str, Any]]:
        markets: list[dict[str, Any]] = []
        for obj in self._walk_dicts(payload):
            if obj.get("__typename") == "SportsbookMarket" or obj.get("typename") == "SportsbookMarket":
                markets.append(obj)
            market = obj.get("market")
            if isinstance(market, dict) and (
                market.get("__typename") == "SportsbookMarket" or market.get("typename") == "SportsbookMarket"
            ):
                markets.append(market)
        return markets

    def _rows_from_sportsbook_markets(
        self,
        markets: list[dict[str, Any]],
        match: BetfairMatch,
        prices: dict[tuple[str, int], float] | None = None,
    ) -> list[dict[str, Any]]:
        unique_markets: list[dict[str, Any]] = []
        seen_market_ids: set[str] = set()
        for market in markets:
            market_id = self._market_id(market)
            if not market_id or market_id in seen_market_ids:
                continue
            seen_market_ids.add(market_id)
            unique_markets.append(market)

        if prices is None:
            market_ids = [
                self._market_id(market)
                for market in unique_markets
                if self._market_id(market) and not (market.get("liveData") or {}).get("runners")
            ]
            prices = self._market_prices(market_ids)
        rows: list[dict[str, Any]] = []
        for market in unique_markets:
            market_id = self._market_id(market)
            market_name = str(market.get("name") or market.get("marketTypeName") or market.get("marketType") or "")
            if not market_id or not market_name:
                continue
            live_prices = self._live_runner_prices(market, prices)
            runners = market.get("runners") or (market.get("liveData") or {}).get("runners") or []
            for runner in runners:
                selection_id = runner.get("selectionId")
                if selection_id is None:
                    continue
                try:
                    selection_id_int = int(selection_id)
                except (TypeError, ValueError):
                    continue
                price = live_prices.get(selection_id_int) or prices.get((market_id, selection_id_int)) or self._runner_price(runner)
                if not price:
                    continue
                row = self._row_from_market_runner(market, runner, price, match)
                if row:
                    rows.append(row)
        return self._dedupe_rows(rows)

    def _market_id(self, market: dict[str, Any]) -> str:
        market_id = market.get("marketId")
        if market_id:
            return str(market_id)
        urn = str(market.get("urn") or "")
        if urn.startswith("ppb:sbkMarket:"):
            return urn.rsplit(":", 1)[-1]
        return ""

    def _live_runner_prices(
        self,
        market: dict[str, Any],
        prices: dict[tuple[str, int], float],
    ) -> dict[int, float]:
        market_id = self._market_id(market)
        output = {selection_id: price for (price_market_id, selection_id), price in prices.items() if price_market_id == market_id}
        for runner in (market.get("liveData") or {}).get("runners") or []:
            selection_id = runner.get("selectionId")
            price = self._runner_price(runner)
            if selection_id is None or not price:
                continue
            try:
                output[int(selection_id)] = float(price)
            except (TypeError, ValueError):
                continue
        return output

    def _market_prices(self, market_ids: list[str]) -> dict[tuple[str, int], float]:
        prices: dict[tuple[str, int], float] = {}
        for index in range(0, len(market_ids), 70):
            chunk = market_ids[index : index + 70]
            if not chunk:
                continue
            try:
                response = httpx.post(
                    SMP_PRICES_URL,
                    params={"priceHistory": 1},
                    json={"marketIds": chunk},
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "Origin": "https://www.betfair.bet.br",
                        "Referer": "https://www.betfair.bet.br/apostas/",
                    },
                    timeout=30,
                    follow_redirects=True,
                )
                response.raise_for_status()
                data = response.json()
            except Exception as exc:
                log.warning("Betfair SMP falhou: %s", exc)
                continue
            prices.update(self._prices_from_market_price_payload(data))
        return prices

    def _prices_from_market_price_payload(self, payload: Any) -> dict[tuple[str, int], float]:
        prices: dict[tuple[str, int], float] = {}
        markets = payload if isinstance(payload, list) else [payload]
        for market in markets:
            if not isinstance(market, dict):
                continue
            market_id = str(market.get("marketId") or "")
            if not market_id:
                continue
            for runner in market.get("runnerDetails") or []:
                selection_id = runner.get("selectionId")
                price = self._runner_price(runner)
                if selection_id is None or not price:
                    continue
                try:
                    prices[(market_id, int(selection_id))] = float(price)
                except (TypeError, ValueError):
                    continue
        return prices

    def _runner_price(self, runner: dict[str, Any]) -> float | None:
        for key in ["winRunnerOdds", "runnerOdds", "odds", "trueOdds"]:
            value = runner.get(key)
            price = self._price(value) if isinstance(value, dict) else self._as_price(value)
            if price:
                return price
        return self._as_price(runner.get("price"))

    def _row_from_market_runner(
        self,
        market: dict[str, Any],
        runner: dict[str, Any],
        price: float,
        match: BetfairMatch,
    ) -> dict[str, Any] | None:
        market_name = str(market.get("name") or market.get("marketTypeName") or market.get("marketType") or "")
        runner_name = str(runner.get("name") or self._translated(runner.get("displayName")) or "")
        market_id = self._market_id(market)
        market_type = str(market.get("marketType") or market.get("marketTypeName") or "")
        selection_id = runner.get("selectionId")
        runner_handicap = runner.get("handicap")
        if "combinad" in self._norm(market_name):
            return {
                "market_key": self._popular_market_key(market_name),
                "market_name": market_name[:120],
                "outcome_name": runner_name or self._outcome_from_text(market_name),
                "price": price,
                "point": self._threshold_point(runner_name) or self._threshold_point(market_name),
                "player_name": None,
                "team_name": self._team_name(market_name, runner_name, match),
                "market_id": market_id,
                "market_type_raw": market_type,
                "selection_id": selection_id,
                "runner_name": runner_name,
                "runner_handicap": runner_handicap,
            }
        player_row = self._player_prop_from_text(runner_name, price, match)
        if player_row:
            player_row["market_name"] = market_name[:120]
            player_row["market_id"] = market_id
            player_row["market_type_raw"] = market_type
            player_row["selection_id"] = selection_id
            player_row["runner_name"] = runner_name
            player_row["runner_handicap"] = runner_handicap
            return player_row
        team_side = self._team_goal_market_side(market_type, market_name)
        market_key = self._market_key(market_name, runner_name) or self._popular_market_key(market_name)
        team_goal_key = self._team_goal_market_key(team_side)
        if team_goal_key:
            market_key = team_goal_key
        player_name = self._player_name_from_runner(market_key, market_name, runner_name)
        if player_name and (re.search(r"\be\b", self._norm(player_name)) or " ou" in self._norm(player_name)):
            player_name = None
        if market_key.startswith("betfair-player") and not player_name:
            market_key = self._popular_market_key(market_name)
        outcome_name = self._outcome_from_runner(market_name, runner_name)
        if market_key.startswith(("betfair-popular", "betfair-oddsboost")):
            outcome_name = runner_name or outcome_name
        if market_key.startswith("betfair-team") and not self._threshold_point(f"{market_name} {runner_name}"):
            outcome_name = runner_name or outcome_name
        if self._unsupported_score_market(market_key, market_name, runner_name, outcome_name):
            market_key = self._popular_market_key(market_name)
            outcome_name = runner_name or outcome_name
        if team_side == "home":
            team_name = match.home_team
        elif team_side == "away":
            team_name = match.away_team
        else:
            team_name = None if market_key in {
                "betfair-result",
                "betfair-double-chance",
                "betfair-draw-no-bet",
            } else self._team_name(market_name, runner_name, match)
        return {
            "market_key": market_key,
            "market_name": market_name[:120],
            "outcome_name": outcome_name,
            "price": price,
            "point": self._line_point(market_key, market_name, runner_name, runner_handicap),
            "player_name": player_name,
            "team_name": team_name,
            "team_side": team_side,
            "market_id": market_id,
            "market_type_raw": market_type,
            "selection_id": selection_id,
            "runner_name": runner_name,
            "runner_handicap": runner_handicap,
        }

    def _expand_markets(self, page: Page) -> None:
        labels = ["Mais", "Mostrar", "Todos", "Player", "Jogador", "Chutes", "Finalizações", "Faltas", "Escanteios", "Cartões"]
        for label in labels:
            try:
                buttons = page.get_by_text(label, exact=False)
                count = min(buttons.count(), 8)
                for index in range(count):
                    try:
                        buttons.nth(index).click(timeout=800)
                        page.wait_for_timeout(250)
                    except Exception:
                        continue
            except Exception:
                continue

    def _rows_from_payloads(self, payloads: list[Any], match: BetfairMatch) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        prices: dict[tuple[str, int], float] = {}
        markets: list[dict[str, Any]] = []
        for payload in payloads:
            has_sportsbook_markets = bool(self._sportsbook_markets_from_payload(payload))
            for obj in self._walk_dicts(payload):
                prices.update(self._prices_from_market_price_payload(obj))
                if obj.get("typename") == "SportsbookMarket" or (obj.get("marketId") and obj.get("runners")):
                    markets.append(obj)
                market_name = self._market_name(obj)
                if not market_name or not self._target_market(market_name):
                    continue
                for outcome in self._extract_outcomes(obj):
                    market_key = self._market_key(market_name, outcome.get("name"))
                    if not market_key:
                        continue
                    if has_sportsbook_markets:
                        continue
                    player_name = self._player_name(market_name, outcome["name"])
                    if market_key.startswith("betfair-player") and not player_name:
                        continue
                    team_side = self._team_goal_market_side("", market_name)
                    team_name = self._team_name(market_name, outcome["name"], match)
                    if team_side == "home":
                        team_name = match.home_team
                    elif team_side == "away":
                        team_name = match.away_team
                    rows.append(
                        {
                            "market_key": market_key,
                            "market_name": market_name,
                            "outcome_name": outcome["name"],
                            "price": outcome["price"],
                            "point": outcome.get("point") or self._point(market_name) or self._point(outcome["name"]),
                            "player_name": player_name,
                            "team_name": team_name,
                            "team_side": team_side,
                        }
                    )
        rows.extend(self._rows_from_sportsbook_markets(markets, match, prices))
        return self._dedupe_rows(rows)

    def _rows_from_dom(self, page: Page, match: BetfairMatch) -> list[dict[str, Any]]:
        try:
            text = page.locator("body").inner_text(timeout=5000)
        except Exception:
            return []
        rows: list[dict[str, Any]] = []
        lines = [row.strip() for row in text.splitlines() if row.strip()]
        for index, line in enumerate(lines):
            if not self._target_market(line):
                continue
            odds = self._odds_near(lines, index)
            if not odds:
                continue
            player_odds = self._odds_after(lines, index)
            player_row = self._player_prop_from_text(line, (player_odds or odds)[-1], match)
            if player_row:
                rows.append(player_row)
                continue

            market_key = self._market_key(line, line)
            if not market_key:
                continue
            if market_key.startswith("betfair-player"):
                continue
            team_side = self._team_goal_market_side("", line)
            team_name = self._team_name(line, "", match)
            if team_side == "home":
                team_name = match.home_team
            elif team_side == "away":
                team_name = match.away_team
            rows.append(
                {
                    "market_key": market_key,
                    "market_name": line[:120],
                    "outcome_name": self._outcome_from_text(line),
                    "price": odds[-1],
                    "point": self._point(line),
                    "player_name": None,
                    "team_name": team_name,
                    "team_side": team_side,
                }
            )
        return self._dedupe_rows(rows)

    def _player_prop_from_text(self, line: str, price: float, match: BetfairMatch) -> dict[str, Any] | None:
        text = re.sub(r"\s+", " ", line).strip()
        normalized = self._norm(text)
        if not any(token in normalized for token in ["falta", "chute", "finaliz"]):
            return None
        if " cada" in normalized or re.search(r"\be\b", normalized):
            return None
        pattern = re.compile(
            r"^(?P<player>[A-Za-zÀ-ÿ'. -]{3,60}?)\s+"
            r"(?P<verb>comete|sofre|recebe|faz|da|dá|tem)\s+"
            r"(?P<number>\d+(?:[\.,]\d+)?)\s*(?:ou mais|\+)?\s+"
            r"(?P<metric>envolvimentos?\s+em\s+faltas?|faltas?|chutes?\s+no\s+gol|chutes?|finaliza(?:ções|coes))",
            re.IGNORECASE,
        )
        match_text = pattern.search(text)
        if not match_text:
            return None
        player = match_text.group("player").strip()
        if re.search(r"\s+e\s+", player, flags=re.IGNORECASE):
            return None
        verb = self._norm(match_text.group("verb"))
        metric = self._norm(match_text.group("metric"))
        raw_number = float(match_text.group("number").replace(",", "."))
        point = raw_number - 0.5 if raw_number >= 1 else raw_number
        if "chute" in metric and "gol" in metric:
            market_key = "betfair-player-shots-on-target"
        elif "chute" in metric or "finaliz" in metric:
            market_key = "betfair-player-shots"
        elif verb in {"sofre", "recebe"}:
            market_key = "betfair-player-fouls-suffered"
        else:
            market_key = "betfair-player-fouls-committed"
        return {
            "market_key": market_key,
            "market_name": text[:120],
            "outcome_name": "Over",
            "price": price,
            "point": point,
            "player_name": player,
            "team_name": self._team_name(text, "", match),
        }

    @staticmethod
    def _odds_near(lines: list[str], index: int) -> list[float]:
        values: list[float] = []
        window = lines[index : index + 5]
        for item in window:
            clean = item.replace(",", ".").strip()
            if re.fullmatch(r"[1-9]\d?(?:\.\d{1,2})?", clean):
                price = float(clean)
                if 1.01 <= price <= 1000:
                    values.append(price)
            for raw in re.findall(r"(?<!\d)([1-9]\d?[\.,]\d{1,2})(?!\d)", item):
                price = float(raw.replace(",", "."))
                if 1.01 <= price <= 1000:
                    values.append(price)
        return values[:4]

    @staticmethod
    def _odds_after(lines: list[str], index: int) -> list[float]:
        values: list[float] = []
        for item in lines[index + 1 : index + 5]:
            clean = item.replace(",", ".").strip()
            if re.fullmatch(r"[1-9]\d?(?:\.\d{1,2})?", clean):
                price = float(clean)
                if 1.01 <= price <= 1000:
                    values.append(price)
                continue
            if values:
                break
        return values

    def _event_from_rows(self, match: BetfairMatch, rows: list[dict[str, Any]]) -> dict[str, Any]:
        markets: dict[tuple[str, str, Any], dict[str, Any]] = {}
        for row in rows:
            key = row["market_key"]
            market_name = row.get("market_name") or key
            market_group_key = (key, market_name, row.get("market_id"))
            market = markets.setdefault(
                market_group_key,
                {
                    "key": key,
                    "name": market_name,
                    "market_type": key,
                    "player_prop": bool(row.get("player_name")) or key.startswith("betfair-player"),
                    "team_side": row.get("team_side"),
                    "market_id": row.get("market_id"),
                    "market_type_raw": row.get("market_type_raw"),
                    "outcomes": [],
                },
            )
            market["outcomes"].append(
                {
                    "name": row["outcome_name"],
                    "price": row["price"],
                    "point": row.get("point"),
                    "player_name": row.get("player_name"),
                    "team_name": row.get("team_name"),
                    "team_side": row.get("team_side"),
                    "main_line": True,
                    "market_id": row.get("market_id"),
                    "market_type_raw": row.get("market_type_raw"),
                    "selection_id": row.get("selection_id"),
                    "runner_name": row.get("runner_name"),
                    "runner_handicap": row.get("runner_handicap"),
                }
            )
        return {
            "id": match.source_match_id,
            "home_team": match.home_team,
            "away_team": match.away_team,
            "commence_time": match.commence_time,
            "bookmakers": [{"key": "betfair", "title": "Betfair", "markets": list(markets.values())}],
        }

    def _extract_outcomes(self, obj: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for candidate in self._walk_dicts(obj):
            name = self._outcome_name(candidate)
            price = self._price(candidate)
            if not name or price is None:
                continue
            rows.append({"name": name, "price": price, "point": self._point(json.dumps(candidate, ensure_ascii=False))})
        return self._dedupe_outcomes(rows)

    def _market_name(self, obj: dict[str, Any]) -> str | None:
        for key in ["marketName", "market_name", "marketType", "marketTypeName", "name", "title", "description"]:
            value = obj.get(key)
            if isinstance(value, str) and self._target_market(value):
                return value
        return None

    def _outcome_name(self, obj: dict[str, Any]) -> str | None:
        for key in ["runnerName", "selectionName", "outcomeName", "name", "label", "title", "description"]:
            value = obj.get(key)
            if isinstance(value, str) and 1 <= len(value) <= 120:
                return value
        return None

    def _price(self, obj: dict[str, Any]) -> float | None:
        display_odds = obj.get("decimalDisplayOdds")
        if isinstance(display_odds, dict):
            price = self._as_price(display_odds.get("decimalOdds"))
            if price:
                return price
        for odds_key in ["displayOdds", "odds"]:
            odds_value = obj.get(odds_key)
            if isinstance(odds_value, dict):
                price = self._as_price(odds_value.get("decimal"))
                if price:
                    return price
        true_odds = obj.get("trueOdds")
        if isinstance(true_odds, dict):
            decimal_odds = true_odds.get("decimalOdds")
            if isinstance(decimal_odds, dict):
                price = self._as_price(decimal_odds.get("decimalOdds"))
                if price:
                    return price
        for key in ["decimalOdds", "decimal", "odds", "price", "displayOdds", "decimalPrice"]:
            value = obj.get(key)
            price = self._as_price(value)
            if price:
                return price
            if isinstance(value, dict):
                for nested in ["decimal", "decimalOdds", "price"]:
                    price = self._as_price(value.get(nested))
                    if price:
                        return price
        return None

    @staticmethod
    def _as_price(value: Any) -> float | None:
        if isinstance(value, str):
            value = value.replace(",", ".")
        try:
            price = float(value)
        except (TypeError, ValueError):
            return None
        return price if 1.01 <= price <= 1000 else None

    @staticmethod
    def _point(text: str | None) -> float | None:
        if not text:
            return None
        match = re.search(r"(?<!\d)(\d+(?:[\.,]5)?)(?:\+|\s|$)", text)
        if not match:
            return None
        try:
            point = float(match.group(1).replace(",", "."))
        except ValueError:
            return None
        return point if 0 <= point <= 30 else None

    def _market_key(self, market_name: str, outcome_name: str | None) -> str | None:
        text = self._norm(f"{market_name} {outcome_name or ''}")
        if "combinad" in text:
            return None
        team_goal_key = self._team_goal_market_key(self._team_goal_market_side("", market_name))
        if team_goal_key:
            return team_goal_key
        if "goleiro" in text or "defesa" in text or "saves" in text:
            return "betfair-goalkeeper-saves"
        if "chance dupla" in text or "double chance" in text:
            return "betfair-double-chance" if "mais/menos" not in text else self._popular_market_key(market_name)
        if "empate sem aposta" in text or "draw no bet" in text:
            return "betfair-draw-no-bet"
        if "resultado final" in text or "resultado da partida" in text or "match odds" in text:
            return "betfair-result" if "mais/menos" not in text and "ambos" not in text else self._popular_market_key(market_name)
        if "placar correto" in text or "2 gols de vantagem" in text:
            return self._popular_market_key(market_name)
        if ("chute" in text or "shot" in text) and ("time" in text or self._team_text_matches(market_name, outcome_name or "")):
            return "betfair-team-shots-on-target" if ("gol" in text or "target" in text or "alvo" in text) else "betfair-team-shots"
        if "shot" in text or "chute" in text or "finaliz" in text:
            if "target" in text or "gol" in text or "alvo" in text:
                return "betfair-player-shots-on-target"
            return "betfair-player-shots"
        if "foul" in text or "falta" in text:
            if "suffer" in text or "won" in text or "sofr" in text or "receb" in text:
                return "betfair-player-fouls-suffered"
            return "betfair-player-fouls-committed"
        if "corner" in text or "escanteio" in text:
            return "totals-corners"
        if "card" in text or "cartao" in text or "cartoes" in text or "booking" in text:
            return "totals-bookings"
        if "both teams" in text or "ambas" in text:
            return "btts"
        if ("goal" in text or "gol" in text) and any(token in text for token in ["over", "under", "mais", "menos"]):
            return "totals"
        return None

    def _team_goal_market_side(self, market_type: object, market_name: object) -> str | None:
        raw_type = str(market_type or "").upper()
        text = self._norm(market_name)
        if not (raw_type.endswith("_GOALS") or "goal" in text or "gol" in text):
            return None
        if raw_type.startswith("HOME_TEAM_OVER/UNDER") or "time da casa com mais/menos" in text or "home team over/under" in text:
            return "home"
        if raw_type.startswith("AWAY_TEAM_OVER/UNDER") or "time visitante com mais/menos" in text or "away team over/under" in text:
            return "away"
        return None

    @staticmethod
    def _team_goal_market_key(side: str | None) -> str | None:
        if side == "home":
            return "teamtotals-goals-team1"
        if side == "away":
            return "teamtotals-goals-team2"
        return None

    def _unsupported_score_market(
        self,
        market_key: str,
        market_name: str,
        runner_name: str,
        outcome_name: str,
    ) -> bool:
        if market_key not in {"totals", "totals-corners", "totals-bookings", "btts"}:
            return False
        text = self._norm(f"{market_name} {runner_name} {outcome_name}")
        complex_tokens = [
            "cada time",
            "cada equipe",
            "cada tempo",
            "em cada tempo",
            "mais escanteios",
            "bate mais",
            "vence",
            "marca primeiro",
            "cartao vermelho",
            "penalti",
            "placar",
            "resultado correto",
        ]
        if any(token in text for token in complex_tokens):
            return True
        if market_key == "btts":
            return not any(token in self._norm(outcome_name) for token in ["sim", "nao", "yes", "no"])
        return not self._is_over_under(outcome_name) and not self._is_over_under(runner_name)

    @staticmethod
    def _threshold_point(text: str | None) -> float | None:
        if not text:
            return None
        normalized = str(text).replace(",", ".")
        match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)(?:\s*ou\s+mais|\s*or\s+more|\+)", normalized, re.IGNORECASE)
        if match:
            value = float(match.group(1))
            return value - 0.5 if value >= 1 else value
        match = re.search(r"(?:mais/menos|over/under|acima/abaixo|mais|menos|over|under)\s+de?\s*(\d+(?:\.\d+)?)", normalized, re.IGNORECASE)
        if match:
            return float(match.group(1))
        return BetfairWebClient._point(normalized)

    def _line_point(
        self,
        market_key: str,
        market_name: str,
        runner_name: str,
        handicap: Any,
    ) -> float | None:
        text_point = self._threshold_point(market_name) or self._threshold_point(runner_name)
        if market_key.startswith("betfair-player"):
            return text_point
        if market_key in {"betfair-result", "betfair-double-chance", "betfair-draw-no-bet"}:
            return None
        market_point = text_point
        if market_key in {"totals", "totals-corners", "totals-bookings"} and market_point is not None:
            return market_point
        if self._is_over_under(runner_name):
            try:
                point = float(handicap)
            except (TypeError, ValueError):
                return text_point
            return point if point > 0 else text_point
        return text_point

    def _is_over_under(self, value: object) -> bool:
        text = self._norm(value)
        return any(token in text for token in ["acima", "abaixo", "over", "under", "mais", "menos"])

    def _player_name_from_runner(self, market_key: str, market_name: str, runner_name: str) -> str | None:
        if market_key.startswith("betfair-team") or market_key in {
            "betfair-goalkeeper-saves",
            "betfair-result",
            "betfair-double-chance",
            "betfair-draw-no-bet",
        }:
            return None
        if market_key.startswith("betfair-player"):
            cleaned = re.sub(r"[^A-Za-zÀ-ÿ\s'.-]", " ", runner_name)
            cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
            if 3 <= len(cleaned) <= 60 and not any(token in self._norm(cleaned) for token in ["mais", "menos", "over", "under"]):
                return cleaned
        return self._player_name(market_name, runner_name)

    def _player_name(self, market_name: str, outcome_name: str) -> str | None:
        text = re.sub(r"\s+", " ", f"{market_name} {outcome_name}").strip()
        if not any(token in self._norm(text) for token in ["shot", "chute", "finaliz", "foul", "falta"]):
            return None
        cleaned = re.split(r"\b(?:over|under|mais|menos|shots?|chutes?|finaliz|fouls?|faltas?)\b", text, flags=re.I)[0]
        cleaned = re.sub(r"[^A-Za-zÀ-ÿ\s'.-]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
        return cleaned if 3 <= len(cleaned) <= 60 else None

    def _team_name(self, market_name: str, outcome_name: str, match: BetfairMatch) -> str | None:
        text = self._norm(f"{market_name} {outcome_name}")
        if self._norm(match.home_team) in text or self._team_text_matches(match.home_team, text):
            return match.home_team
        if self._norm(match.away_team) in text or self._team_text_matches(match.away_team, text):
            return match.away_team
        return None

    @staticmethod
    def _outcome_from_text(text: str) -> str:
        lowered = text.lower()
        if "under" in lowered or "menos" in lowered or "abaixo" in lowered:
            return "Under"
        if "over" in lowered or "mais" in lowered or "acima" in lowered:
            return "Over"
        if re.search(r"\b(sim|yes)\b", lowered):
            return "Sim"
        if re.fullmatch(r"\s*(nao|não|no)\s*", lowered):
            return "Não"
        return "Linha"

    def _outcome_from_runner(self, market_name: str, runner_name: str) -> str:
        runner_text = self._norm(runner_name)
        market_text = self._norm(market_name)
        if "abaixo" in runner_text or "menos" in runner_text or "under" in runner_text:
            return "Under"
        if "acima" in runner_text or "ou mais" in runner_text or "over" in runner_text or "mais" in runner_text:
            return "Over"
        if re.search(r"(?<!\d)\d+(?:[\.,]\d+)?(?:\s*ou\s+mais|\s*or\s+more|\+)", runner_name, re.IGNORECASE):
            return "Over"
        if re.search(r"\b(sim|yes)\b", runner_text):
            return "Sim"
        if re.fullmatch(r"\s*(nao|não|no)\s*", runner_text):
            return "Não"
        if "abaixo" in market_text or "menos" in market_text or "under" in market_text:
            return "Under"
        if "acima" in market_text or "ou mais" in market_text or "over" in market_text or "mais" in market_text:
            return "Over"
        if re.search(r"(?<!\d)\d+(?:[\.,]\d+)?(?:\s*ou\s+mais|\s*or\s+more|\+)", market_name, re.IGNORECASE):
            return "Over"
        return runner_name or self._outcome_from_text(market_name)

    def _popular_market_key(self, market_name: str) -> str:
        if self._norm(market_name) == self._norm("Cotações Aumentadas"):
            return "betfair-oddsboost"
        return f"betfair-popular-{self._slug(market_name) or 'mercado'}"

    @staticmethod
    def _player_line_point(text: str) -> float | None:
        match = re.search(r"(?<!\d)(\d+(?:[\.,]\d+)?)(?:\s*ou mais|\+)", text, re.IGNORECASE)
        if not match:
            return BetfairWebClient._point(text)
        try:
            value = float(match.group(1).replace(",", "."))
        except ValueError:
            return None
        return value - 0.5 if value >= 1 else value

    @staticmethod
    def _translated(value: Any) -> str | None:
        if isinstance(value, dict):
            text = value.get("translated") or value.get("name") or value.get("translate")
            return str(text) if text else None
        return str(value) if value else None

    @staticmethod
    def _target_market(value: str) -> bool:
        text = BetfairWebClient._norm(value)
        return any(token in text for token in TARGET_TEXT)

    def _looks_related(self, text: str, match: BetfairMatch) -> bool:
        home = self._norm(match.home_team)
        away = self._norm(match.away_team)
        normalized = self._norm(text)
        return (home in normalized or away in normalized) and any(token in normalized for token in TARGET_TEXT)

    def _event_text_matches(self, text: Any, match: BetfairMatch) -> bool:
        normalized = self._norm(text)
        parts = re.split(r"\s+x\s+|\s+v\s+|\s+vs\s+", normalized, maxsplit=1)
        if len(parts) == 2:
            direct = self._team_text_matches(match.home_team, parts[0]) and self._team_text_matches(match.away_team, parts[1])
            reverse = self._team_text_matches(match.home_team, parts[1]) and self._team_text_matches(match.away_team, parts[0])
            return direct or reverse
        return self._team_text_matches(match.home_team, normalized) and self._team_text_matches(match.away_team, normalized)

    @staticmethod
    def _looks_like_event_url(value: str) -> bool:
        return "/e-" in value and ("/apostas/futebol/" in value or "/sport/football/" in value)

    def _team_text_matches(self, team_name: Any, text: Any) -> bool:
        team = self._norm(team_name)
        candidate = self._norm(text)
        if not team or not candidate:
            return False
        if team in candidate or candidate in team:
            return True
        ignored = {"fc", "afc", "cf", "club", "de", "da", "do", "the"}
        team_tokens = {token for token in re.findall(r"[a-z0-9]+", team) if len(token) >= 3 and token not in ignored}
        candidate_tokens = {token for token in re.findall(r"[a-z0-9]+", candidate) if len(token) >= 3 and token not in ignored}
        return bool(team_tokens & candidate_tokens)

    @staticmethod
    def _walk_dicts(value: Any) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        stack = [value]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                rows.append(current)
                stack.extend(current.values())
            elif isinstance(current, list):
                stack.extend(current)
        return rows

    @staticmethod
    def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[Any, ...]] = set()
        deduped: list[dict[str, Any]] = []
        for row in rows:
            key = (row.get("market_key"), row.get("outcome_name"), row.get("price"), row.get("point"), row.get("player_name"), row.get("team_name"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        return deduped

    @staticmethod
    def _dedupe_outcomes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[Any, ...]] = set()
        deduped: list[dict[str, Any]] = []
        for row in rows:
            key = (row.get("name"), row.get("price"), row.get("point"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        return deduped[:80]

    @staticmethod
    def _norm(value: Any) -> str:
        text = str(value or "").casefold()
        text = unicodedata.normalize("NFKD", text)
        return "".join(char for char in text if not unicodedata.combining(char))

    @classmethod
    def _slug(cls, value: str) -> str:
        text = cls._norm(value)
        text = text.replace("&", " e ")
        text = re.sub(r"[^a-z0-9]+", "-", text)
        return text.strip("-")

    @staticmethod
    def _rooted(value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else ROOT_DIR / path
