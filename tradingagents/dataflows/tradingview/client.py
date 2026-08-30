"""Secret-safe HTTP client for the TradingView Data API.

Console (recommended): ``https://api.tradingviewapi.com`` with
``Authorization: Bearer <TRADINGVIEW_API_KEY>``. Get a key at
https://www.tradingviewapi.com/

RapidAPI remains an explicit opt-in via ``TRADINGVIEW_BACKEND=rapid``.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Mapping
from concurrent.futures import Future
from typing import Any

import requests

from ..errors import (
    VendorAuthenticationError,
    VendorNotConfiguredError,
    VendorRateLimitError,
    VendorUnavailableError,
)
from .cache import (
    ResponseCache,
    build_cache_key,
    get_default_response_cache,
    ttl_for_path,
)

logger = logging.getLogger(__name__)

_CONSOLE_HOST = "api.tradingviewapi.com"
_CONSOLE_BASE_URL = f"https://{_CONSOLE_HOST}"
_RAPIDAPI_HOST = "tradingview-data1.p.rapidapi.com"
_RAPIDAPI_BASE_URL = f"https://{_RAPIDAPI_HOST}"
_SIGNUP_URL = "https://www.tradingviewapi.com/"
_TIMEOUT_SECONDS = 30
_MAX_REQUEST_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 0.5
# Pause briefly on 429 and continue the same request instead of failing the analysis job.
_RATE_LIMIT_BACKOFF_SECONDS = 2.5
_RATE_LIMIT_BACKOFF_MAX_SECONDS = 10.0

# Collapse concurrent identical cacheable requests (e.g. parallel indicator tools).
_inflight_lock = threading.Lock()
_inflight: dict[str, Future[dict[str, Any] | list[Any]]] = {}

# Share a short cooldown across threads so parallel tool calls pause together on 429.
_cooldown_lock = threading.Lock()
_cooldown_until = 0.0


def _format_request(
    method: str,
    path: str,
    *,
    params: Mapping[str, Any] | None = None,
    body: Mapping[str, Any] | None = None,
) -> str:
    """Build a secret-safe request fingerprint for logs (no API key)."""
    parts = [method.upper(), "/" + str(path).lstrip("/")]
    if params:
        query = "&".join(f"{key}={params[key]}" for key in sorted(params))
        parts.append(f"?{query}")
    if body:
        keys = ",".join(sorted(str(key) for key in body))
        parts.append(f" body_keys=[{keys}]")
    return "".join(parts)


def _retry_after_seconds(response: requests.Response) -> float | None:
    """Seconds to wait from a 429 ``Retry-After`` header, when present."""
    raw = response.headers.get("Retry-After") if response.headers else None
    if raw is None:
        return None
    try:
        return min(float(raw), _RATE_LIMIT_BACKOFF_MAX_SECONDS)
    except (TypeError, ValueError):
        return None


def _wait_for_rate_limit_cooldown() -> None:
    """Block until any process-wide TradingView 429 cooldown has elapsed."""
    with _cooldown_lock:
        remaining = _cooldown_until - time.monotonic()
    if remaining > 0:
        time.sleep(remaining)


def _mark_rate_limited(delay_seconds: float) -> None:
    """Extend the shared cooldown so concurrent callers also pause briefly."""
    global _cooldown_until
    deadline = time.monotonic() + max(0.0, delay_seconds)
    with _cooldown_lock:
        if deadline > _cooldown_until:
            _cooldown_until = deadline


def reset_rate_limit_cooldown() -> None:
    """Clear the shared 429 cooldown (tests only)."""
    global _cooldown_until
    with _cooldown_lock:
        _cooldown_until = 0.0


def _first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def requested_tradingview_backend() -> str | None:
    """Return an explicit ``TRADINGVIEW_BACKEND`` override, if set."""
    raw = os.getenv("TRADINGVIEW_BACKEND", "").strip().lower()
    if raw in {"console", "rapid", "rapidapi"}:
        return "rapid" if raw in {"rapid", "rapidapi"} else "console"
    return None


def resolve_tradingview_auth() -> tuple[str, str]:
    """Return ``(api_key, backend)`` where backend is ``console`` or ``rapid``.

    Console is the default. ``TRADINGVIEW_API_KEY`` is preferred; the legacy
    RapidAPI env names still work as Console credentials so existing deploys
    keep running. Set ``TRADINGVIEW_BACKEND=rapid`` to use the RapidAPI host.
    """
    backend = requested_tradingview_backend() or "console"
    if backend == "rapid":
        api_key = _first_env(
            "TRADINGVIEW_RAPIDAPI_KEY", "RAPIDAPI_KEY", "TRADINGVIEW_API_KEY"
        )
    else:
        api_key = _first_env(
            "TRADINGVIEW_API_KEY", "TRADINGVIEW_RAPIDAPI_KEY", "RAPIDAPI_KEY"
        )
    if not api_key:
        raise VendorNotConfiguredError(
            "TradingView Data API is not configured. "
            f"Get a Console key at {_SIGNUP_URL}"
        )
    return api_key, backend


def get_tradingview_api_key() -> str:
    """Return the configured TradingView API key (Console first)."""
    return resolve_tradingview_auth()[0]


class TradingViewClient:
    """Perform authenticated requests and validate TradingView response envelopes."""

    def __init__(
        self,
        api_key: str | None = None,
        session: requests.Session | None = None,
        cache: ResponseCache | None = None,
        backend: str | None = None,
    ) -> None:
        if api_key is None:
            self._api_key, resolved_backend = resolve_tradingview_auth()
            self._backend = backend or resolved_backend
        else:
            self._api_key = api_key
            self._backend = backend or requested_tradingview_backend() or "console"
        if self._backend not in {"console", "rapid"}:
            raise ValueError(
                f"TradingView backend must be 'console' or 'rapid', got {self._backend!r}"
            )
        self._session = session if session is not None else requests.Session()
        self._cache = cache if cache is not None else get_default_response_cache()

    def get(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """GET one API path and return the validated response envelope's data."""
        return self._request("GET", path, params=params)

    def post(
        self,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """POST JSON to one API path and return the validated envelope's data."""
        return self._request("POST", path, params=params, body=body)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        label = _format_request(method, path, params=params, body=body)
        ttl_seconds = ttl_for_path(path)
        cache_key: str | None = None
        if ttl_seconds > 0:
            cache_key = build_cache_key(method, path, params=params, body=body)
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.info("TradingView cache hit %s", label)
                return cached

            leader = False
            with _inflight_lock:
                pending = _inflight.get(cache_key)
                if pending is None:
                    pending = Future()
                    _inflight[cache_key] = pending
                    leader = True

            if not leader:
                logger.info("TradingView coalesce wait %s", label)
                return pending.result(timeout=_TIMEOUT_SECONDS + 5)

            try:
                data = self._execute(method, path, params=params, body=body)
                self._cache.set(cache_key, data, ttl_seconds=ttl_seconds)
                pending.set_result(data)
                return data
            except Exception as exc:
                pending.set_exception(exc)
                raise
            finally:
                with _inflight_lock:
                    if _inflight.get(cache_key) is pending:
                        del _inflight[cache_key]

        return self._execute(method, path, params=params, body=body)

    def _execute(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        label = _format_request(method, path, params=params, body=body)
        logger.info("TradingView upstream request %s", label)
        headers = dict(self._auth_headers())
        if body is not None:
            headers["Content-Type"] = "application/json"
        url = f"{self._base_url}/{path.lstrip('/')}"

        for attempt in range(_MAX_REQUEST_ATTEMPTS):
            _wait_for_rate_limit_cooldown()
            try:
                response = self._session.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=dict(body) if body is not None else None,
                    timeout=_TIMEOUT_SECONDS,
                )
            except requests.RequestException:
                if attempt == _MAX_REQUEST_ATTEMPTS - 1:
                    raise VendorUnavailableError(
                        "TradingView Data API request failed"
                    ) from None
                logger.warning(
                    "TradingView upstream retry %s attempt=%s",
                    label,
                    attempt + 1,
                )
                time.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue

            logger.info(
                "TradingView upstream response %s status=%s",
                label,
                response.status_code,
            )

            if response.status_code == 429:
                delay = _retry_after_seconds(response) or _RATE_LIMIT_BACKOFF_SECONDS
                _mark_rate_limited(delay)
                if attempt == _MAX_REQUEST_ATTEMPTS - 1:
                    raise VendorRateLimitError(
                        "TradingView Data API rate limit exceeded"
                    )
                logger.warning(
                    "TradingView rate limited %s; waiting %.1fs then continuing "
                    "(attempt %s/%s)",
                    label,
                    delay,
                    attempt + 1,
                    _MAX_REQUEST_ATTEMPTS,
                )
                _wait_for_rate_limit_cooldown()
                continue

            if response.status_code in (401, 403):
                raise VendorAuthenticationError(
                    "TradingView Data API rejected the configured credentials"
                )
            if not 200 <= response.status_code < 300:
                raise VendorUnavailableError("TradingView Data API is unavailable")

            try:
                payload = response.json()
            except (TypeError, ValueError):
                raise VendorUnavailableError(
                    "TradingView Data API returned invalid JSON"
                ) from None

            if not isinstance(payload, dict) or payload.get("success") is not True:
                raise VendorUnavailableError(
                    "TradingView Data API returned an unsuccessful response"
                )
            data = payload.get("data")
            # Ideas list/hot/minds return arrays; most other endpoints return objects.
            if not isinstance(data, (dict, list)):
                raise VendorUnavailableError(
                    "TradingView Data API returned invalid response data"
                )
            return data

        raise VendorUnavailableError("TradingView Data API request failed")

    @property
    def _base_url(self) -> str:
        if self._backend == "rapid":
            return _RAPIDAPI_BASE_URL
        return _CONSOLE_BASE_URL

    def _auth_headers(self) -> dict[str, str]:
        if self._backend == "rapid":
            return {
                "x-rapidapi-host": _RAPIDAPI_HOST,
                "x-rapidapi-key": self._api_key,
            }
        return {"Authorization": f"Bearer {self._api_key}"}
