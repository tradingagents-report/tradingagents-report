"""BaoStock A-share daily OHLCV adapter."""

from __future__ import annotations

import importlib
from typing import Any

import pandas as pd

from ..china.common import (
    indicators_from_fetch,
    normalize_ohlcv,
    resolve_cn_symbol,
    stock_text_from_fetch,
)
from ..errors import VendorAuthenticationError, VendorNotConfiguredError, VendorUnavailableError


def _sdk(value: Any | None):
    if value is not None:
        return value
    try:
        return importlib.import_module("baostock")
    except ImportError as exc:
        raise VendorNotConfiguredError("BaoStock optional dependency is not installed") from exc


def baostock_symbol(symbol: str) -> str:
    _, exchange, code = resolve_cn_symbol(symbol)
    return f"{'sh' if exchange == 'SSE' else 'sz'}.{code}"


def fetch_baostock_ohlcv(
    symbol: str,
    start_date: str,
    end_date: str,
    *,
    sdk: Any | None = None,
):
    client = _sdk(sdk)
    resolved = baostock_symbol(symbol)
    login = client.login()
    if getattr(login, "error_code", "") != "0":
        raise VendorAuthenticationError("BaoStock login failed")
    try:
        cursor = client.query_history_k_data_plus(
            code=resolved,
            fields="date,open,high,low,close,volume,amount",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="2",
        )
        if getattr(cursor, "error_code", "") != "0":
            raise VendorUnavailableError("BaoStock history request failed")
        rows = []
        while cursor.next():
            rows.append(cursor.get_row_data())
        raw = pd.DataFrame(rows, columns=cursor.fields)
    finally:
        client.logout()
    return normalize_ohlcv(
        raw,
        provider="baostock",
        requested_symbol=symbol,
        resolved_symbol=resolved,
        start_date=start_date,
        end_date=end_date,
        adjustment_mode="forward",
    )


def get_baostock_stock(symbol: str, start_date: str, end_date: str) -> str:
    return stock_text_from_fetch(
        fetch_baostock_ohlcv,
        symbol,
        start_date,
        end_date,
    )


def get_baostock_indicators(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int,
) -> str:
    return indicators_from_fetch(fetch_baostock_ohlcv, symbol, indicator, curr_date, look_back_days)
