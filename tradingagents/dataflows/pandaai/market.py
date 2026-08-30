"""PandaAI A-share and US daily OHLCV adapter."""

from __future__ import annotations

import importlib
import os
from typing import Any

import pandas as pd

from ..china.common import normalize_ohlcv, resolve_cn_symbol, stock_text_from_fetch
from ..errors import (
    VendorAuthenticationError,
    VendorNotConfiguredError,
    VendorUnavailableError,
)
from ..listings import resolve_listing
from ..market_routing import market_for_listing


def _sdk(value: Any | None):
    if value is not None:
        return value
    try:
        return importlib.import_module("panda_data")
    except ImportError as exc:
        raise VendorNotConfiguredError("PandaAI requires the optional panda_data package") from exc


def fetch_pandaai_ohlcv(
    symbol: str,
    start_date: str,
    end_date: str,
    *,
    sdk: Any | None = None,
):
    """Fetch one inclusive daily window from PandaAI."""
    username = os.getenv("PANDAAI_USERNAME", "").strip()
    password = os.getenv("PANDAAI_PASSWORD", "").strip()
    if not username or not password:
        raise VendorNotConfiguredError("PandaAI username/password are not configured")
    client = _sdk(sdk)
    auth = {"username": username, "password": password}
    base_url = os.getenv("PANDAAI_BASE_URL", "").strip()
    if base_url:
        auth["base_url"] = base_url
    try:
        client.init_token(**auth)
    except Exception as exc:
        raise VendorAuthenticationError("PandaAI authentication failed") from exc

    listing = resolve_listing(symbol)
    market = market_for_listing(listing)
    try:
        if market == "CN":
            _, _, code = resolve_cn_symbol(symbol)
            resolved = code
            raw = client.get_market_data(
                symbol=[code],
                start_date=start_date,
                end_date=end_date,
                type="stock",
                fields=[],
            )
            currency = "CNY"
        elif market == "US":
            resolved = listing.symbol.upper()
            raw = client.get_us_daily(
                symbol=[resolved], start_date=start_date, end_date=end_date, fields=[]
            )
            currency = "USD"
        else:
            raise ValueError(f"PandaAI does not support ambiguous symbol {symbol!r}")
    except (ValueError, VendorNotConfiguredError):
        raise
    except Exception as exc:
        raise VendorUnavailableError("PandaAI daily data request failed") from exc
    return normalize_ohlcv(
        pd.DataFrame(raw),
        provider="pandaai",
        requested_symbol=symbol,
        resolved_symbol=resolved,
        start_date=start_date,
        end_date=end_date,
        quote_currency=currency,
        market=market,
    )


def get_pandaai_stock(symbol: str, start_date: str, end_date: str) -> str:
    return stock_text_from_fetch(
        fetch_pandaai_ohlcv,
        symbol,
        start_date,
        end_date,
    )
