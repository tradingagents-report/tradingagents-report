"""AKShare A-share daily OHLCV adapter."""

from __future__ import annotations

import importlib
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
        return importlib.import_module("akshare")
    except ImportError as exc:
        raise VendorNotConfiguredError("AKShare optional dependency is not installed") from exc


def fetch_akshare_ohlcv(
    symbol: str,
    start_date: str,
    end_date: str,
    *,
    sdk: Any | None = None,
):
    _, _, code = resolve_cn_symbol(symbol)
    client = _sdk(sdk)
    try:
        raw = client.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=datetime.strptime(start_date, "%Y-%m-%d").strftime("%Y%m%d"),
            end_date=datetime.strptime(end_date, "%Y-%m-%d").strftime("%Y%m%d"),
            adjust="qfq",
        )
    except Exception as exc:
        raise VendorUnavailableError("AKShare history request failed") from exc
    return normalize_ohlcv(
        pd.DataFrame(raw),
        provider="akshare",
        requested_symbol=symbol,
        resolved_symbol=code,
        start_date=start_date,
        end_date=end_date,
        adjustment_mode="qfq",
    )


def get_akshare_stock(symbol: str, start_date: str, end_date: str) -> str:
    return stock_text_from_fetch(
        fetch_akshare_ohlcv,
        symbol,
        start_date,
        end_date,
    )


def get_akshare_indicators(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int,
) -> str:
    return indicators_from_fetch(fetch_akshare_ohlcv, symbol, indicator, curr_date, look_back_days)
