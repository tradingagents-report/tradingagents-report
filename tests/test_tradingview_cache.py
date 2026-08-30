"""Tests for TradingView response caching (memory + optional Redis)."""

from __future__ import annotations

import threading
import time
from typing import Any
from unittest.mock import Mock

import pytest

from tradingagents.dataflows.tradingview.cache import (
    MemoryTTLResponseCache,
    NullResponseCache,
    RedisResponseCache,
    TieredResponseCache,
    build_cache_key,
    cache_enabled,
    create_response_cache,
    get_default_response_cache,
    get_redis_url,
    reset_default_response_cache,
    ttl_for_path,
)
from tradingagents.dataflows.tradingview.client import TradingViewClient


class RecordingResponseCache:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        self.ttls: dict[str, int] = {}
        self.get_calls = 0
        self.set_calls = 0

    def get(self, key: str):
        self.get_calls += 1
        return self.store.get(key)

    def set(self, key: str, value, *, ttl_seconds: int) -> None:
        self.set_calls += 1
        self.store[key] = value
        self.ttls[key] = ttl_seconds


@pytest.fixture(autouse=True)
def _reset_cache_singleton(monkeypatch):
    reset_default_response_cache()
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("TRADINGVIEW_CACHE_ENABLED", "true")
    yield
    reset_default_response_cache()


def test_ttl_tiers():
    assert ttl_for_path("/api/price/NASDAQ:AAPL") == 60
    assert ttl_for_path("/api/quote/batch") == 60
    assert ttl_for_path("/api/news") == 120
    assert ttl_for_path("/api/market-data/NASDAQ:AAPL/company") == 300
    assert ttl_for_path("/api/ta/NASDAQ:AAPL") == 300
    assert ttl_for_path("/api/token/generate") == 0
    assert ttl_for_path("/api/unknown") == 60


def test_cache_key_distinguishes_params_and_body():
    base = build_cache_key("GET", "/api/price/AAPL", params={"range": 10})
    other_params = build_cache_key("GET", "/api/price/AAPL", params={"range": 20})
    other_path = build_cache_key("GET", "/api/price/MSFT", params={"range": 10})
    post_a = build_cache_key("POST", "/api/quote/batch", body={"symbols": ["A"]})
    post_b = build_cache_key("POST", "/api/quote/batch", body={"symbols": ["B"]})

    assert base != other_params
    assert base != other_path
    assert post_a != post_b
    assert build_cache_key("GET", "/api/price/AAPL", params={"b": 2, "a": 1}) == (
        build_cache_key("GET", "/api/price/AAPL", params={"a": 1, "b": 2})
    )


def test_cache_enabled_defaults_true_without_redis(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("TRADINGVIEW_CACHE_ENABLED", raising=False)
    assert get_redis_url() is None
    assert cache_enabled() is True

    monkeypatch.setenv("TRADINGVIEW_CACHE_ENABLED", "false")
    assert cache_enabled() is False


def test_get_redis_url_reads_redis_url(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    assert get_redis_url() == "redis://127.0.0.1:6379/0"


def test_create_response_cache_uses_memory_without_redis():
    cache = create_response_cache("")
    assert isinstance(cache, MemoryTTLResponseCache)


def test_create_response_cache_disabled(monkeypatch):
    monkeypatch.setenv("TRADINGVIEW_CACHE_ENABLED", "false")
    assert isinstance(create_response_cache(""), NullResponseCache)


def test_create_response_cache_fails_open_to_memory_on_bad_redis():
    cache = create_response_cache("redis://127.0.0.1:1/0")
    assert isinstance(cache, MemoryTTLResponseCache)


def test_default_cache_is_memory_without_redis():
    assert isinstance(get_default_response_cache(), MemoryTTLResponseCache)


def test_memory_ttl_expires():
    cache = MemoryTTLResponseCache()
    cache.set("k", {"value": 1}, ttl_seconds=1)
    assert cache.get("k") == {"value": 1}
    # Force expiry by rewriting store clock.
    key = next(iter(cache._store))
    value = cache._store[key][1]
    cache._store[key] = (time.monotonic() - 1, value)
    assert cache.get("k") is None


def test_memory_ttl_returns_copies():
    cache = MemoryTTLResponseCache()
    cache.set("k", {"items": [1]}, ttl_seconds=30)
    first = cache.get("k")
    assert first is not None
    first["items"].append(2)
    assert cache.get("k") == {"items": [1]}


def test_redis_response_cache_roundtrip():
    redis_client = Mock()
    redis_client.get.return_value = None
    cache = RedisResponseCache(redis_client)

    assert cache.get("missing") is None
    cache.set("k", {"value": 1}, ttl_seconds=30)
    redis_client.setex.assert_called_once_with("k", 30, '{"value":1}')

    redis_client.get.return_value = '{"value":2}'
    assert cache.get("k") == {"value": 2}

    redis_client.get.side_effect = RuntimeError("down")
    assert cache.get("k") is None


def test_tiered_cache_promotes_redis_hit_to_memory():
    redis = RecordingResponseCache()
    redis.store["k"] = {"value": 9}
    memory = MemoryTTLResponseCache()
    cache = TieredResponseCache(memory, redis)

    assert cache.get("k") == {"value": 9}
    assert memory.get("k") == {"value": 9}


def test_client_serves_identical_requests_from_cache():
    response = Mock(status_code=200)
    response.json.return_value = {"success": True, "data": {"price": 1}}
    session = Mock()
    session.request.return_value = response
    cache = RecordingResponseCache()
    client = TradingViewClient(api_key="secret", session=session, cache=cache)

    assert client.get("/api/price/AAPL", params={"range": 5}) == {"price": 1}
    assert client.get("/api/price/AAPL", params={"range": 5}) == {"price": 1}
    assert session.request.call_count == 1
    assert cache.set_calls == 1


def test_client_uses_default_memory_cache_across_instances():
    response = Mock(status_code=200)
    response.json.return_value = {"success": True, "data": {"price": 1}}
    session = Mock()
    session.request.return_value = response

    first = TradingViewClient(api_key="secret", session=session)
    second = TradingViewClient(api_key="secret", session=session)

    assert first.get("/api/price/AAPL", params={"range": 5}) == {"price": 1}
    assert second.get("/api/price/AAPL", params={"range": 5}) == {"price": 1}
    assert session.request.call_count == 1


def test_client_coalesces_concurrent_identical_requests():
    started = threading.Event()
    release = threading.Event()
    response = Mock(status_code=200)
    response.json.return_value = {"success": True, "data": {"price": 1}}

    def slow_request(*_args, **_kwargs):
        started.set()
        assert release.wait(timeout=2)
        return response

    session = Mock()
    session.request.side_effect = slow_request
    cache = RecordingResponseCache()
    client = TradingViewClient(api_key="secret", session=session, cache=cache)

    results: list[Any] = []
    errors: list[BaseException] = []

    def worker():
        try:
            results.append(client.get("/api/price/AAPL", params={"range": 5}))
        except BaseException as exc:  # noqa: BLE001 - collect for assertion
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    assert started.wait(timeout=2)
    # Give followers time to join the in-flight wait before releasing the leader.
    time.sleep(0.05)
    release.set()
    for thread in threads:
        thread.join(timeout=2)

    assert errors == []
    assert results == [{"price": 1}] * 4
    assert session.request.call_count == 1


def test_client_misses_when_params_differ():
    response = Mock(status_code=200)
    response.json.return_value = {"success": True, "data": {"price": 1}}
    session = Mock()
    session.request.return_value = response
    cache = RecordingResponseCache()
    client = TradingViewClient(api_key="secret", session=session, cache=cache)

    client.get("/api/price/AAPL", params={"range": 5})
    client.get("/api/price/AAPL", params={"range": 10})
    assert session.request.call_count == 2


def test_client_does_not_cache_token_endpoints():
    response = Mock(status_code=200)
    response.json.return_value = {"success": True, "data": {"token": "x"}}
    session = Mock()
    session.request.return_value = response
    cache = RecordingResponseCache()
    client = TradingViewClient(api_key="secret", session=session, cache=cache)

    client.get("/api/token/generate")
    client.get("/api/token/generate")
    assert session.request.call_count == 2
    assert cache.set_calls == 0


def test_client_does_not_cache_failed_responses():
    response = Mock(status_code=500)
    session = Mock()
    session.request.return_value = response
    cache = RecordingResponseCache()
    client = TradingViewClient(api_key="secret", session=session, cache=cache)

    from tradingagents.dataflows.errors import VendorUnavailableError

    with pytest.raises(VendorUnavailableError):
        client.get("/api/price/AAPL")
    assert cache.set_calls == 0
