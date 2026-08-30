"""Tests for the TradingView Data API HTTP boundary."""

from unittest.mock import Mock

import pytest
import requests

from tradingagents.dataflows.errors import (
    VendorAuthenticationError,
    VendorNotConfiguredError,
    VendorRateLimitError,
    VendorUnavailableError,
)
from tradingagents.dataflows.tradingview import client as tv_client
from tradingagents.dataflows.tradingview.cache import (
    NullResponseCache,
    reset_default_response_cache,
)
from tradingagents.dataflows.tradingview.client import (
    TradingViewClient,
    get_tradingview_api_key,
    reset_rate_limit_cooldown,
    resolve_tradingview_auth,
)

_CONSOLE_HOST = "api.tradingviewapi.com"
_CONSOLE_BASE_URL = f"https://{_CONSOLE_HOST}"
_RAPIDAPI_HOST = "tradingview-data1.p.rapidapi.com"
_RAPIDAPI_BASE_URL = f"https://{_RAPIDAPI_HOST}"


@pytest.fixture(autouse=True)
def _reset_tv_cache(monkeypatch):
    monkeypatch.delenv("TRADINGVIEW_BACKEND", raising=False)
    reset_default_response_cache()
    reset_rate_limit_cooldown()
    yield
    reset_default_response_cache()
    reset_rate_limit_cooldown()


def _patch_sleep(monkeypatch) -> list[float]:
    """Record sleeps and clear cooldown so mocked waits still advance state."""
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        reset_rate_limit_cooldown()

    monkeypatch.setattr(tv_client.time, "sleep", fake_sleep)
    return sleeps


def _client(session: Mock, api_key: str = "secret-value") -> TradingViewClient:
    # Bypass process cache so each test exercises the live request path.
    return TradingViewClient(
        api_key=api_key,
        session=session,
        cache=NullResponseCache(),
    )


def test_console_key_takes_precedence(monkeypatch):
    monkeypatch.setenv("TRADINGVIEW_API_KEY", "console-key")
    monkeypatch.setenv("TRADINGVIEW_RAPIDAPI_KEY", "legacy")
    monkeypatch.setenv("RAPIDAPI_KEY", "generic")

    assert resolve_tradingview_auth() == ("console-key", "console")
    assert get_tradingview_api_key() == "console-key"


def test_legacy_rapidapi_env_is_console_fallback(monkeypatch):
    monkeypatch.delenv("TRADINGVIEW_API_KEY", raising=False)
    monkeypatch.setenv("TRADINGVIEW_RAPIDAPI_KEY", "legacy")
    monkeypatch.setenv("RAPIDAPI_KEY", "generic")

    assert resolve_tradingview_auth() == ("legacy", "console")


def test_generic_key_is_used_as_fallback(monkeypatch):
    monkeypatch.delenv("TRADINGVIEW_API_KEY", raising=False)
    monkeypatch.delenv("TRADINGVIEW_RAPIDAPI_KEY", raising=False)
    monkeypatch.setenv("RAPIDAPI_KEY", "generic")

    assert get_tradingview_api_key() == "generic"


def test_rapid_backend_uses_rapidapi_host(monkeypatch):
    monkeypatch.setenv("TRADINGVIEW_BACKEND", "rapid")
    monkeypatch.setenv("TRADINGVIEW_RAPIDAPI_KEY", "rapid-key")
    monkeypatch.delenv("TRADINGVIEW_API_KEY", raising=False)

    assert resolve_tradingview_auth() == ("rapid-key", "rapid")


def test_missing_key_is_not_configured(monkeypatch):
    monkeypatch.delenv("TRADINGVIEW_API_KEY", raising=False)
    monkeypatch.delenv("TRADINGVIEW_RAPIDAPI_KEY", raising=False)
    monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
    monkeypatch.delenv("TRADINGVIEW_BACKEND", raising=False)

    with pytest.raises(VendorNotConfiguredError, match="tradingviewapi.com"):
        get_tradingview_api_key()


def test_get_sends_required_headers():
    response = Mock(status_code=200)
    response.json.return_value = {
        "success": True,
        "data": {"value": 1},
        "msg": "Success",
    }
    session = Mock()
    session.request.return_value = response
    client = _client(session)

    assert client.get("/api/test", params={"language": "en"}) == {"value": 1}
    session.request.assert_called_once_with(
        "GET",
        f"{_CONSOLE_BASE_URL}/api/test",
        headers={"Authorization": "Bearer secret-value"},
        params={"language": "en"},
        json=None,
        timeout=30,
    )


def test_get_accepts_list_data_payload():
    response = Mock(status_code=200)
    response.json.return_value = {
        "success": True,
        "data": [{"id": 1}],
        "msg": "Success",
    }
    session = Mock()
    session.request.return_value = response
    client = _client(session)

    assert client.get("/api/ideas/list/NASDAQ:AAPL") == [{"id": 1}]


def test_post_sends_json_body():
    response = Mock(status_code=200)
    response.json.return_value = {
        "success": True,
        "data": {"totalCount": 1, "data": []},
    }
    session = Mock()
    session.request.return_value = response
    client = _client(session)

    body = {"market": "america", "range": [0, 10]}
    assert client.post("/api/screener/scan", body=body) == {"totalCount": 1, "data": []}
    session.request.assert_called_once_with(
        "POST",
        f"{_CONSOLE_BASE_URL}/api/screener/scan",
        headers={
            "Authorization": "Bearer secret-value",
            "Content-Type": "application/json",
        },
        params=None,
        json=body,
        timeout=30,
    )


def test_get_retries_timeout_and_returns_later_success():
    response = Mock(status_code=200)
    response.json.return_value = {
        "success": True,
        "data": {"value": 1},
    }
    session = Mock()
    session.request.side_effect = [requests.Timeout("timed out"), response]
    client = _client(session)

    assert client.get("/api/test") == {"value": 1}
    assert session.request.call_count == 2


def test_get_stops_after_three_transport_failures():
    session = Mock()
    session.request.side_effect = requests.Timeout("timed out")
    client = _client(session)

    with pytest.raises(VendorUnavailableError):
        client.get("/api/test")

    assert session.request.call_count == 3


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, VendorAuthenticationError),
        (403, VendorAuthenticationError),
        (429, VendorRateLimitError),
        (500, VendorUnavailableError),
    ],
)
def test_status_mapping_does_not_leak_key(status, error, monkeypatch):
    response = Mock(status_code=status, text="upstream failed", headers={})
    session = Mock()
    session.request.return_value = response
    client = _client(session)
    _patch_sleep(monkeypatch)

    with pytest.raises(error) as caught:
        client.get("/api/test")

    assert "secret-value" not in str(caught.value)
    if status == 429:
        assert session.request.call_count == tv_client._MAX_REQUEST_ATTEMPTS


def test_get_retries_rate_limit_and_continues(monkeypatch):
    limited = Mock(status_code=429, headers={})
    ok = Mock(status_code=200)
    ok.json.return_value = {"success": True, "data": {"value": 1}}
    session = Mock()
    session.request.side_effect = [limited, ok]
    client = _client(session)
    sleeps = _patch_sleep(monkeypatch)

    assert client.get("/api/test") == {"value": 1}
    assert session.request.call_count == 2
    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(tv_client._RATE_LIMIT_BACKOFF_SECONDS, abs=0.05)


def test_get_honours_retry_after_on_rate_limit(monkeypatch):
    limited = Mock(status_code=429, headers={"Retry-After": "3"})
    ok = Mock(status_code=200)
    ok.json.return_value = {"success": True, "data": {"value": 1}}
    session = Mock()
    session.request.side_effect = [limited, ok]
    client = _client(session)
    sleeps = _patch_sleep(monkeypatch)

    assert client.get("/api/test") == {"value": 1}
    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(3.0, abs=0.05)


def test_client_error_repr_does_not_leak_key():
    response = Mock(status_code=401)
    session = Mock()
    session.request.return_value = response
    client = _client(session)

    with pytest.raises(VendorAuthenticationError) as caught:
        client.get("/api/test")

    assert "secret-value" not in repr(caught.value)


@pytest.mark.parametrize(
    "exception",
    [requests.Timeout("timed out"), requests.RequestException("request failed")],
)
def test_transport_errors_are_unavailable_and_do_not_leak_key(exception):
    session = Mock()
    session.request.side_effect = exception
    client = _client(session)

    with pytest.raises(VendorUnavailableError) as caught:
        client.get("/api/test")

    assert "secret-value" not in str(caught.value)


def test_invalid_json_is_unavailable():
    response = Mock(status_code=200)
    response.json.side_effect = requests.exceptions.JSONDecodeError("bad", "", 0)
    session = Mock()
    session.request.return_value = response

    with pytest.raises(VendorUnavailableError):
        _client(session).get("/api/test")


@pytest.mark.parametrize(
    "payload",
    [
        {"success": False, "data": {}, "msg": "failed"},
        {"success": True, "data": None},
        {"success": True, "data": "bad"},
        ["not", "an", "envelope"],
    ],
)
def test_invalid_envelope_is_unavailable(payload):
    response = Mock(status_code=200)
    response.json.return_value = payload
    session = Mock()
    session.request.return_value = response

    with pytest.raises(VendorUnavailableError):
        _client(session).get("/api/test")


def test_rapid_backend_sends_rapidapi_headers(monkeypatch):
    monkeypatch.setenv("TRADINGVIEW_BACKEND", "rapid")
    response = Mock(status_code=200)
    response.json.return_value = {"success": True, "data": {"value": 1}}
    session = Mock()
    session.request.return_value = response
    client = _client(session)

    assert client.get("/api/test") == {"value": 1}
    session.request.assert_called_once_with(
        "GET",
        f"{_RAPIDAPI_BASE_URL}/api/test",
        headers={
            "x-rapidapi-host": _RAPIDAPI_HOST,
            "x-rapidapi-key": "secret-value",
        },
        params=None,
        json=None,
        timeout=30,
    )


def test_client_reads_key_from_environment_when_not_supplied(monkeypatch):
    monkeypatch.setenv("TRADINGVIEW_API_KEY", "secret-value")
    session = Mock()
    session.request.return_value = Mock(
        status_code=200,
        json=Mock(return_value={"success": True, "data": {}}),
    )

    assert (
        TradingViewClient(session=session, cache=NullResponseCache()).get("/api/test")
        == {}
    )
