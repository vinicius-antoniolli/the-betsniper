from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

from sqlmodel import Session, select

from src.db.models import FetchCache
from src.time_utils import utc_now


def make_cache_key(source: str, endpoint_or_url: str, params: dict[str, Any] | None = None) -> str:
    payload = json.dumps(params or {}, sort_keys=True, ensure_ascii=True)
    digest = hashlib.sha256(f"{source}|{endpoint_or_url}|{payload}".encode("utf-8")).hexdigest()
    return digest


def get_cached(session: Session, source: str, endpoint_or_url: str, params: dict[str, Any] | None = None) -> str | None:
    cache_key = make_cache_key(source, endpoint_or_url, params)
    row = session.exec(select(FetchCache).where(FetchCache.cache_key == cache_key)).first()
    if not row:
        return None
    if row.expires_at and row.expires_at < utc_now():
        return None
    return row.body


def put_cached(
    session: Session,
    source: str,
    endpoint_or_url: str,
    params: dict[str, Any] | None,
    body: str,
    ttl: timedelta | None,
    status_code: int | None = None,
) -> None:
    cache_key = make_cache_key(source, endpoint_or_url, params)
    params_hash = hashlib.sha256(json.dumps(params or {}, sort_keys=True).encode("utf-8")).hexdigest()
    row = session.exec(select(FetchCache).where(FetchCache.cache_key == cache_key)).first()
    expires_at = utc_now() + ttl if ttl else None
    if row:
        row.body = body
        row.status_code = status_code
        row.fetched_at = utc_now()
        row.expires_at = expires_at
    else:
        row = FetchCache(
            source=source,
            cache_key=cache_key,
            endpoint_or_url=endpoint_or_url,
            params_hash=params_hash,
            status_code=status_code,
            body=body,
            expires_at=expires_at,
        )
        session.add(row)
    session.commit()
