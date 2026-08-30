"""Response cache for TradingView Data API requests.

Caching is keyed by HTTP method + path + query params + JSON body so identical
requests reuse the upstream payload within a TTL window.

Default is an in-process memory TTL cache (covers single-worker analysis bursts
like get_stock_data + get_indicators × N). Optional Redis (`REDIS_URL`) shares
hits across processes. `TRADINGVIEW_CACHE_ENABLED=false` disables caching.
Redis connect/read/write failures fail-open to memory or live requests.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import threading
import time
from collections.abc import Mapping
from typing import Any, Protocol

logger = logging.getLogger(__name__)

_CACHE_KEY_PREFIX = "tv:resp:v1:"
_DEFAULT_TTL_SECONDS = 60
_MEMORY_MAX_ENTRIES = 256

# Endpoint families observed in production traffic (price/quote dominate).
_TTL_BY_PREFIX: tuple[tuple[str, int], ...] = (
    ("/api/token", 0),  # never cache credential/token responses
    ("/api/price", 60),
    ("/api/quote", 60),
    ("/api/search", 60),
    ("/api/screener", 60),
    ("/api/news", 120),
    ("/api/calendar", 120),
    ("/api/ideas", 120),
    ("/api/market-data", 300),
    ("/api/ta", 300),
    ("/api/leaderboard", 300),
)

_BOOL_TRUE = ("true", "1", "yes", "on")
_BOOL_FALSE = ("false", "0", "no", "off")

_lock = threading.Lock()
_default_cache: ResponseCache | None = None


class ResponseCache(Protocol):
    def get(self, key: str) -> dict[str, Any] | list[Any] | None: ...

    def set(
        self,
        key: str,
        value: dict[str, Any] | list[Any],
        *,
        ttl_seconds: int,
    ) -> None: ...


class NullResponseCache:
    """No-op cache used when caching is explicitly disabled."""

    def get(self, key: str) -> dict[str, Any] | list[Any] | None:
        return None

    def set(
        self,
        key: str,
        value: dict[str, Any] | list[Any],
        *,
        ttl_seconds: int,
    ) -> None:
        return None


class MemoryTTLResponseCache:
    """Process-local TTL cache — collapses duplicate upstream calls in one worker."""

    def __init__(self, max_entries: int = _MEMORY_MAX_ENTRIES) -> None:
        self._max_entries = max(1, max_entries)
        self._store: dict[str, tuple[float, dict[str, Any] | list[Any]]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> dict[str, Any] | list[Any] | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() >= expires_at:
                del self._store[key]
                return None
            return copy.deepcopy(value)

    def set(
        self,
        key: str,
        value: dict[str, Any] | list[Any],
        *,
        ttl_seconds: int,
    ) -> None:
        if ttl_seconds <= 0:
            return
        with self._lock:
            if len(self._store) >= self._max_entries and key not in self._store:
                oldest_key = min(self._store.items(), key=lambda item: item[1][0])[0]
                del self._store[oldest_key]
            self._store[key] = (
                time.monotonic() + ttl_seconds,
                copy.deepcopy(value),
            )


class RedisResponseCache:
    """JSON-serialize TradingView response payloads into Redis with TTL."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def get(self, key: str) -> dict[str, Any] | list[Any] | None:
        try:
            raw = self._client.get(key)
        except Exception:
            logger.debug("TradingView Redis cache get failed", exc_info=True)
            return None
        if raw is None:
            return None
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            payload = json.loads(raw)
        except (TypeError, ValueError, UnicodeDecodeError):
            logger.debug("TradingView Redis cache payload invalid", exc_info=True)
            return None
        if isinstance(payload, (dict, list)):
            return payload
        return None

    def set(
        self,
        key: str,
        value: dict[str, Any] | list[Any],
        *,
        ttl_seconds: int,
    ) -> None:
        if ttl_seconds <= 0:
            return
        try:
            self._client.setex(key, ttl_seconds, json.dumps(value, separators=(",", ":")))
        except Exception:
            logger.debug("TradingView Redis cache set failed", exc_info=True)


class TieredResponseCache:
    """Memory L1 + optional Redis L2 for cross-process reuse."""

    def __init__(self, memory: MemoryTTLResponseCache, redis: ResponseCache) -> None:
        self._memory = memory
        self._redis = redis

    def get(self, key: str) -> dict[str, Any] | list[Any] | None:
        hit = self._memory.get(key)
        if hit is not None:
            return hit
        hit = self._redis.get(key)
        if hit is not None:
            # Rehydrate L1 without extending Redis TTL (best-effort short local reuse).
            self._memory.set(key, hit, ttl_seconds=_DEFAULT_TTL_SECONDS)
            return hit
        return None

    def set(
        self,
        key: str,
        value: dict[str, Any] | list[Any],
        *,
        ttl_seconds: int,
    ) -> None:
        self._memory.set(key, value, ttl_seconds=ttl_seconds)
        self._redis.set(key, value, ttl_seconds=ttl_seconds)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    normalized = raw.strip().lower()
    if normalized in _BOOL_TRUE:
        return True
    if normalized in _BOOL_FALSE:
        return False
    raise ValueError(f"Invalid boolean for {name}: {raw!r}")


def get_redis_url() -> str | None:
    """Return REDIS_URL when configured."""
    value = os.getenv("REDIS_URL")
    if value and value.strip():
        return value.strip()
    return None


def cache_enabled() -> bool:
    """Return whether response caching should be attempted (memory and/or Redis)."""
    return _env_bool("TRADINGVIEW_CACHE_ENABLED", True)


def ttl_for_path(path: str) -> int:
    """Return TTL seconds for a TradingView API path (0 = do not cache)."""
    normalized = "/" + str(path or "").lstrip("/")
    for prefix, ttl in _TTL_BY_PREFIX:
        if normalized == prefix or normalized.startswith(prefix + "/"):
            return ttl
    return _DEFAULT_TTL_SECONDS


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def build_cache_key(
    method: str,
    path: str,
    *,
    params: Mapping[str, Any] | None = None,
    body: Mapping[str, Any] | None = None,
) -> str:
    """Build a stable Redis key for one TradingView request fingerprint."""
    fingerprint = _canonical_json(
        {
            "method": method.upper(),
            "path": "/" + str(path).lstrip("/"),
            "params": dict(params) if params else {},
            "body": dict(body) if body else {},
        }
    )
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
    return f"{_CACHE_KEY_PREFIX}{digest}"


def _connect_redis(url: str) -> Any:
    import redis

    client = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=1.0)
    client.ping()
    return client


def create_response_cache(url: str | None = None) -> ResponseCache:
    """Create memory cache, optionally tiered with Redis when URL is usable."""
    if not cache_enabled():
        return NullResponseCache()

    memory = MemoryTTLResponseCache()
    resolved = url if url is not None else get_redis_url()
    if not resolved:
        return memory
    try:
        return TieredResponseCache(memory, RedisResponseCache(_connect_redis(resolved)))
    except Exception:
        logger.debug("TradingView Redis cache unavailable; using memory only", exc_info=True)
        return memory


def get_default_response_cache() -> ResponseCache:
    """Return a process-wide cache instance (lazy, thread-safe)."""
    global _default_cache
    if _default_cache is not None:
        return _default_cache
    with _lock:
        if _default_cache is None:
            _default_cache = create_response_cache()
    return _default_cache


def reset_default_response_cache() -> None:
    """Drop the process-wide cache singleton (tests / config reloads)."""
    global _default_cache
    with _lock:
        _default_cache = None
