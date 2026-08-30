"""AKShare A-share identity and financial-data adapter."""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..china.common import resolve_cn_symbol
from ..errors import NoMarketDataError, VendorUnavailableError
from .market import _sdk


def _filter_frame(frame: pd.DataFrame, curr_date: str | None) -> pd.DataFrame:
    if not curr_date or frame.empty:
        return frame
    column = next(
        (name for name in ("报告期", "REPORT_DATE", "公告日期", "date") if name in frame.columns),
        None,
    )
    if column is None:
        return frame
    dates = pd.to_datetime(frame[column], errors="coerce")
    return frame[dates.notna() & (dates <= pd.Timestamp(curr_date))]


def _as_text(frame: pd.DataFrame, label: str, symbol: str) -> str:
    if frame.empty:
        raise NoMarketDataError(symbol, detail=f"AKShare returned no {label}")
    return f"# AKShare {label} for {symbol}\n\n" + frame.to_json(
        orient="records", force_ascii=False, date_format="iso"
    )


def get_akshare_identity(symbol: str, *, sdk: Any | None = None) -> dict[str, str]:
    _, exchange, code = resolve_cn_symbol(symbol)
    try:
        frame = pd.DataFrame(_sdk(sdk).stock_individual_info_em(symbol=code))
    except Exception as exc:
        raise VendorUnavailableError("AKShare identity request failed") from exc
    if frame.empty or not {"item", "value"}.issubset(frame.columns):
        raise NoMarketDataError(symbol, code, "AKShare returned no identity")
    values = dict(zip(frame["item"].astype(str), frame["value"].astype(str), strict=False))
    return {
        "company_name": values.get("股票简称", code),
        "exchange": exchange,
        "industry": values.get("行业", ""),
        "list_date": values.get("上市时间", ""),
        "quote_type": "stock",
    }


def get_akshare_fundamentals(
    symbol: str, curr_date: str | None = None, *, sdk: Any | None = None
) -> str:
    _, _, code = resolve_cn_symbol(symbol)
    try:
        frame = pd.DataFrame(_sdk(sdk).stock_financial_abstract_ths(symbol=code))
    except Exception as exc:
        raise VendorUnavailableError("AKShare fundamentals request failed") from exc
    return _as_text(_filter_frame(frame, curr_date), "fundamentals", symbol)


def _statement(
    symbol: str,
    curr_date: str | None,
    sdk: Any | None,
    endpoint: str,
    label: str,
) -> str:
    _, _, code = resolve_cn_symbol(symbol)
    try:
        frame = pd.DataFrame(getattr(_sdk(sdk), endpoint)(symbol=code))
    except Exception as exc:
        raise VendorUnavailableError(f"AKShare {label} request failed") from exc
    return _as_text(_filter_frame(frame, curr_date), label, symbol)


def get_balance_sheet(
    symbol: str, freq: str = "quarterly", curr_date: str | None = None, *, sdk: Any | None = None
) -> str:
    return _statement(symbol, curr_date, sdk, "stock_balance_sheet_by_report_em", "balance sheet")


def get_income_statement(
    symbol: str, freq: str = "quarterly", curr_date: str | None = None, *, sdk: Any | None = None
) -> str:
    return _statement(symbol, curr_date, sdk, "stock_profit_sheet_by_report_em", "income statement")


def get_cashflow(
    symbol: str, freq: str = "quarterly", curr_date: str | None = None, *, sdk: Any | None = None
) -> str:
    return _statement(symbol, curr_date, sdk, "stock_cash_flow_sheet_by_report_em", "cash flow")
