"""Tushare A-share identity and financial-data adapter."""

from __future__ import annotations

import importlib
import os
from typing import Any

import pandas as pd

from ..errors import NoMarketDataError, VendorNotConfiguredError, VendorUnavailableError
from .market import tushare_symbol


def _pro(sdk: Any | None):
    token = os.getenv("TUSHARE_TOKEN", "").strip()
    if not token:
        raise VendorNotConfiguredError("TUSHARE_TOKEN is not configured")
    if sdk is None:
        try:
            sdk = importlib.import_module("tushare")
        except ImportError as exc:
            raise VendorNotConfiguredError("Tushare optional dependency is not installed") from exc
    return sdk.pro_api(token)


def _filter(frame: pd.DataFrame, curr_date: str | None) -> pd.DataFrame:
    if not curr_date or frame.empty:
        return frame
    column = next(
        (
            name
            for name in ("end_date", "ann_date", "trade_date", "f_ann_date")
            if name in frame.columns
        ),
        None,
    )
    if column is None:
        return frame
    dates = pd.to_datetime(frame[column], errors="coerce")
    return frame[dates.notna() & (dates <= pd.Timestamp(curr_date))]


def _text(frame: pd.DataFrame, label: str, symbol: str) -> str:
    if frame.empty:
        raise NoMarketDataError(symbol, detail=f"Tushare returned no {label}")
    return f"# Tushare {label} for {symbol}\n\n" + frame.to_json(
        orient="records", force_ascii=False, date_format="iso"
    )


def get_tushare_identity(symbol: str, *, sdk: Any | None = None) -> dict[str, str]:
    resolved = tushare_symbol(symbol)
    try:
        frame = pd.DataFrame(
            _pro(sdk).stock_basic(ts_code=resolved, fields="name,industry,list_date")
        )
    except Exception as exc:
        if isinstance(exc, VendorNotConfiguredError):
            raise
        raise VendorUnavailableError("Tushare identity request failed") from exc
    if frame.empty:
        raise NoMarketDataError(symbol, resolved, "Tushare returned no identity")
    row = frame.iloc[0]
    return {
        "company_name": str(row.get("name", resolved)),
        "exchange": "SSE" if resolved.endswith(".SH") else "SZSE",
        "industry": str(row.get("industry", "")),
        "list_date": str(row.get("list_date", "")),
        "quote_type": "stock",
    }


def get_tushare_fundamentals(
    symbol: str, curr_date: str | None = None, *, sdk: Any | None = None
) -> str:
    resolved = tushare_symbol(symbol)
    try:
        frame = pd.DataFrame(_pro(sdk).daily_basic(ts_code=resolved))
    except Exception as exc:
        if isinstance(exc, VendorNotConfiguredError):
            raise
        raise VendorUnavailableError("Tushare fundamentals request failed") from exc
    return _text(_filter(frame, curr_date), "fundamentals", symbol)


def _statement(
    symbol: str, curr_date: str | None, sdk: Any | None, endpoint: str, label: str
) -> str:
    resolved = tushare_symbol(symbol)
    try:
        frame = pd.DataFrame(getattr(_pro(sdk), endpoint)(ts_code=resolved))
    except Exception as exc:
        if isinstance(exc, VendorNotConfiguredError):
            raise
        raise VendorUnavailableError(f"Tushare {label} request failed") from exc
    return _text(_filter(frame, curr_date), label, symbol)


def get_balance_sheet(
    symbol: str, freq: str = "quarterly", curr_date: str | None = None, *, sdk: Any | None = None
) -> str:
    return _statement(symbol, curr_date, sdk, "balancesheet", "balance sheet")


def get_income_statement(
    symbol: str, freq: str = "quarterly", curr_date: str | None = None, *, sdk: Any | None = None
) -> str:
    return _statement(symbol, curr_date, sdk, "income", "income statement")


def get_cashflow(
    symbol: str, freq: str = "quarterly", curr_date: str | None = None, *, sdk: Any | None = None
) -> str:
    return _statement(symbol, curr_date, sdk, "cashflow", "cash flow")
