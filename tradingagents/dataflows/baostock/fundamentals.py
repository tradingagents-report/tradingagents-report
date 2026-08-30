"""BaoStock A-share identity and summary fundamentals."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from ..errors import NoMarketDataError, VendorAuthenticationError, VendorUnavailableError
from .market import _sdk, baostock_symbol


def _query(client, method: str, **kwargs) -> pd.DataFrame:
    login = client.login()
    if getattr(login, "error_code", "") != "0":
        raise VendorAuthenticationError("BaoStock login failed")
    try:
        cursor = getattr(client, method)(**kwargs)
        if getattr(cursor, "error_code", "") != "0":
            raise VendorUnavailableError(f"BaoStock {method} failed")
        rows = []
        while cursor.next():
            rows.append(cursor.get_row_data())
        return pd.DataFrame(rows, columns=cursor.fields)
    finally:
        client.logout()


def get_baostock_identity(symbol: str, *, sdk: Any | None = None) -> dict[str, str]:
    resolved = baostock_symbol(symbol)
    frame = _query(_sdk(sdk), "query_stock_basic", code=resolved)
    if frame.empty:
        raise NoMarketDataError(symbol, resolved, "BaoStock returned no identity")
    row = frame.iloc[0]
    return {
        "company_name": str(row.get("code_name", resolved)),
        "exchange": "SSE" if resolved.startswith("sh.") else "SZSE",
        "list_date": str(row.get("ipoDate", "")),
        "quote_type": "stock",
    }


def get_baostock_fundamentals(
    symbol: str, curr_date: str | None = None, *, sdk: Any | None = None
) -> str:
    resolved = baostock_symbol(symbol)
    cutoff = datetime.strptime(curr_date, "%Y-%m-%d") if curr_date else datetime.now()
    frame = _query(
        _sdk(sdk),
        "query_profit_data",
        code=resolved,
        year=cutoff.year - 1,
        quarter=4,
    )
    if "pubDate" in frame.columns:
        dates = pd.to_datetime(frame["pubDate"], errors="coerce")
        frame = frame[dates.notna() & (dates <= cutoff)]
    if frame.empty:
        raise NoMarketDataError(symbol, resolved, "BaoStock returned no fundamentals")
    return f"# BaoStock fundamentals for {symbol}\n\n" + frame.to_json(
        orient="records", force_ascii=False, date_format="iso"
    )
