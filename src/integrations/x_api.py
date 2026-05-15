from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from base64 import b64encode
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote, urlsplit, urlunsplit

import httpx


POSTS_ENDPOINT = "/2/tweets"


class XPostError(RuntimeError):
    pass


@dataclass(frozen=True)
class XCredentials:
    api_key: str | None
    api_key_secret: str | None
    access_token: str | None
    access_token_secret: str | None

    @classmethod
    def from_settings(cls, settings: object) -> "XCredentials":
        return cls(
            api_key=getattr(settings, "x_api_key", None),
            api_key_secret=getattr(settings, "x_api_key_secret", None),
            access_token=getattr(settings, "x_access_token", None),
            access_token_secret=getattr(settings, "x_access_token_secret", None),
        )

    def missing_fields(self) -> list[str]:
        fields = {
            "X_API_KEY": self.api_key,
            "X_API_KEY_SECRET": self.api_key_secret,
            "X_ACCESS_TOKEN": self.access_token,
            "X_ACCESS_TOKEN_SECRET": self.access_token_secret,
        }
        return [name for name, value in fields.items() if not str(value or "").strip()]

    def require_complete(self) -> None:
        missing = self.missing_fields()
        if missing:
            raise XPostError(f"Config X incompleta: {', '.join(missing)}")


@dataclass(frozen=True)
class XPostResult:
    post_id: str
    text: str


def _oauth_encode(value: object) -> str:
    return quote(str(value), safe="-._~")


def _signature_base_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _oauth_header(method: str, url: str, credentials: XCredentials) -> str:
    credentials.require_complete()
    oauth_params = {
        "oauth_consumer_key": str(credentials.api_key),
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": str(credentials.access_token),
        "oauth_version": "1.0",
    }
    normalized = "&".join(
        f"{_oauth_encode(key)}={_oauth_encode(value)}"
        for key, value in sorted(oauth_params.items())
    )
    base_url = _signature_base_url(url)
    signature_base = "&".join(
        _oauth_encode(part)
        for part in (method.upper(), base_url, normalized)
    )
    signing_key = f"{_oauth_encode(credentials.api_key_secret)}&{_oauth_encode(credentials.access_token_secret)}"
    signature = hmac.new(signing_key.encode(), signature_base.encode(), hashlib.sha1).digest()
    oauth_params["oauth_signature"] = b64encode(signature).decode()
    values = ", ".join(
        f'{_oauth_encode(key)}="{_oauth_encode(value)}"'
        for key, value in sorted(oauth_params.items())
    )
    return f"OAuth {values}"


def _post_url(api_base_url: str) -> str:
    return f"{api_base_url.rstrip('/')}{POSTS_ENDPOINT}"


def post_x_text(
    text: str,
    credentials: XCredentials,
    api_base_url: str = "https://api.x.com",
    timeout: float = 30,
) -> XPostResult:
    url = _post_url(api_base_url)
    response = httpx.post(
        url,
        headers={
            "Authorization": _oauth_header("POST", url, credentials),
            "Content-Type": "application/json",
        },
        json={"text": text},
        timeout=timeout,
    )
    if response.status_code >= 400:
        body = response.text[:500].replace("\n", " ")
        raise XPostError(f"X API {response.status_code}: {body}")
    payload = response.json()
    post_id = str((payload.get("data") or {}).get("id") or "")
    if not post_id:
        raise XPostError(f"X API resposta sem id: {payload}")
    return XPostResult(post_id=post_id, text=text)


def publish_x_posts(
    posts: list[str],
    credentials: XCredentials,
    api_base_url: str = "https://api.x.com",
    delay_seconds: int = 60,
    max_chars: int = 280,
    post_fn: Callable[[str, XCredentials, str], XPostResult] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    progress_fn: Callable[[int, int, XPostResult], None] | None = None,
) -> list[XPostResult]:
    credentials.require_complete()
    if not posts:
        return []
    over_limit = [(index + 1, len(text)) for index, text in enumerate(posts) if len(text) > max_chars]
    if over_limit:
        details = ", ".join(f"post {index}: {chars}/{max_chars}" for index, chars in over_limit)
        raise XPostError(f"Post X acima do limite: {details}")

    sender = post_fn or post_x_text
    results: list[XPostResult] = []
    for index, text in enumerate(posts):
        result = sender(text, credentials, api_base_url)
        results.append(result)
        if progress_fn:
            progress_fn(index + 1, len(posts), result)
        if index < len(posts) - 1 and delay_seconds > 0:
            sleep_fn(delay_seconds)
    return results
