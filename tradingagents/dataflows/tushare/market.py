"""Tushare A-share daily OHLCV adapter."""

from __future__ import annotations

import importlib
import os
from datetime import datetime
from typing import Any

import pandas as pd

from ..china.common import (
    indicators_from_fetch,
    normalize_ohlcv,
    resolve_cn_symbol,
    stock_text_from_fetch,
)
from ..errors import VendorNotConfiguredError, VendorUnavailableError


def _sdk(value: Any | None):
    if value is not None:
        return value
    try:
        return importlib.import_module("tushare")
    except ImportError as exc:
        raise VendorNotConfiguredError("Tushare optional dependency is not installed") from exc


def tushare_symbol(symbol: str) -> str:
    _, exchange, code = resolve_cn_symbol(symbol)
    return f"{code}.{'SH' if exchange == 'SSE' else 'SZ'}"


def fetch_tushare_ohlcv(
    symbol: str,
    start_date: str,
    end_date: str,
    *,
    sdk: Any | None = None,
):
    token = os.getenv("TUSHARE_TOKEN", "").strip()
    if not token:
        raise VendorNotConfiguredError("TUSHARE_TOKEN is not configured")
    client = _sdk(sdk)
    if hasattr(client, "set_token"):
        client.set_token(token)
    resolved = tushare_symbol(symbol)
    try:
        raw = client.pro_bar(
            ts_code=resolved,
            start_date=datetime.strptime(start_date, "%Y-%m-%d").strftime("%Y%m%d"),
            end_date=datetime.strptime(end_date, "%Y-%m-%d").strftime("%Y%m%d"),
            adj="qfq",
        )
    except Exception as exc:
        raise VendorUnavailableError("Tushare history request failed") from exc
    return normalize_ohlcv(
        pd.DataFrame(raw),
        provider="tushare",
        requested_symbol=symbol,
        resolved_symbol=resolved,
        start_date=start_date,
        end_date=end_date,
        adjustment_mode="qfq",
    )


def get_tushare_stock(symbol: str, start_date: str, end_date: str) -> str:
    return stock_text_from_fetch(
        fetch_tushare_ohlcv,
        symbol,
        start_date,
        end_date,
    )


def get_tushare_indicators(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int,
) -> str:
    return indicators_from_fetch(fetch_tushare_ohlcv, symbol, indicator, curr_date, look_back_days)
