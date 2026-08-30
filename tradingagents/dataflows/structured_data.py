"""Provider-neutral facade for structured market data."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .interface import route_structured
from .provider_models import ProviderResult


def get_ohlcv(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Return a defensive copy of routed OHLCV data."""
    result = route_structured("get_ohlcv", symbol, start_date, end_date)
    if not isinstance(result, ProviderResult):
        raise TypeError("Structured OHLCV route returned an unexpected result type")
    data = result.data
    if not isinstance(data, pd.DataFrame):
        raise TypeError("Structured OHLCV route returned an unexpected data type")
    if data.empty:
        raise ValueError(f"No OHLCV data available for {symbol}.")
    result_data = data.copy()
    if result.quote_currency:
        result_data.attrs["quote_currency"] = result.quote_currency
    return result_data


def get_instrument_identity(ticker: str) -> dict[str, str]:
    """Return non-empty string identity values from the structured router."""
    result = route_structured("get_instrument_identity", ticker)
    data: Any = result.data if isinstance(result, ProviderResult) else result
    if not isinstance(data, dict):
        raise TypeError("Structured identity route returned an unexpected data type")
    return {
        key: value.strip()
        for key, value in data.items()
        if isinstance(key, str) and isinstance(value, str) and value.strip()
    }
