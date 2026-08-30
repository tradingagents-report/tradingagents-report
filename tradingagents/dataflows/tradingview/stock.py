"""TradingView adapters for company identity, OHLCV, and technical indicators."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, time, timedelta, timezone
from math import isfinite
from typing import Any
from urllib.parse import quote

import pandas as pd

from ..errors import NoMarketDataError
from ..provider_models import ProviderResult, parse_instrument
from ..stockstats_utils import (
    _assert_ohlcv_not_stale,
    calculate_indicator_window,
    validate_indicator,
)
from .client import TradingViewClient
from .symbols import encode_path_symbol, resolve_tradingview_symbol


def _search_markets(client: TradingViewClient, query: str, asset_class: str):
    filter_name = {"equity": "stock"}.get(asset_class, asset_class)
    data = client.get(
        f"/api/search/market/{quote(query, safe='')}",
        params={"filter": filter_name},
    )
    markets = data.get("markets", [])
    return markets if isinstance(markets, list) else []


def _resolve(symbol: str, client: TradingViewClient):
    ref = parse_instrument(symbol)
    search = None
    if not ref.exchange_hint:
        def search(query: str):
            return _search_markets(client, query, ref.asset_class)

    return ref, resolve_tradingview_symbol(ref, search=search)


def fetch_tradingview_ohlcv(
    symbol: str,
    start_date: str,
    end_date: str,
    *,
    client: TradingViewClient | None = None,
) -> ProviderResult[pd.DataFrame]:
    """Fetch and validate an inclusive daily TradingView OHLCV range."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    if end < start:
        raise ValueError("end_date must not be before start_date")

    api = client or TradingViewClient()
    ref, resolved = _resolve(symbol, api)
    end_of_day = datetime.combine(end.date(), time(23, 59, 59), tzinfo=timezone.utc)
    path_symbol = encode_path_symbol(resolved.symbol)
    # Canonicalize daily range so get_stock_data / get_indicators /
    # get_verified_market_snapshot share one TradingView /api/price cache key.
    # 400 covers ~1y lookback + stockstats warmup (~250) + buffer.
    requested_range = max(2, (end - start).days + 10)
    payload = api.get(
        f"/api/price/{path_symbol}",
        params={
            "range": max(400, requested_range),
            "to": int(end_of_day.timestamp()),
            "timeframe": "D",
            "type": "Japanese",
        },
    )

    history = payload.get("history")
    if not isinstance(history, list) or not history:
        raise NoMarketDataError(symbol, resolved.symbol, "TradingView returned no price history")

    source_columns = ["time", "open", "max", "min", "close", "volume"]
    raw = pd.DataFrame(history)
    if any(column not in raw.columns for column in source_columns):
        raise NoMarketDataError(symbol, resolved.symbol, "TradingView history is missing OHLC fields")

    frame = raw[source_columns].rename(
        columns={
            "time": "Date",
            "open": "Open",
            "max": "High",
            "min": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    timestamps = pd.to_numeric(frame["Date"], errors="coerce")
    if timestamps.isna().any() or not timestamps.map(isfinite).all():
        raise NoMarketDataError(symbol, resolved.symbol, "TradingView returned invalid OHLCV fields")
    frame["Date"] = pd.to_datetime(timestamps, unit="s", utc=True, errors="coerce").dt.tz_localize(None)
    numeric_columns = ["Open", "High", "Low", "Close", "Volume"]
    frame[numeric_columns] = frame[numeric_columns].apply(pd.to_numeric, errors="coerce")
    numeric_values = frame[numeric_columns]
    invalid_numeric = numeric_values.isna().any().any() or numeric_values.isin(
        [float("inf"), float("-inf")]
    ).any().any()
    if frame["Date"].isna().any() or invalid_numeric:
        raise NoMarketDataError(symbol, resolved.symbol, "TradingView returned invalid OHLCV fields")
    if frame["Date"].duplicated().any():
        raise NoMarketDataError(symbol, resolved.symbol, "TradingView returned duplicate OHLCV timestamps")
    invalid_bar = (
        (frame["High"] < frame["Low"])
        | (frame["High"] < frame["Open"])
        | (frame["High"] < frame["Close"])
        | (frame["Low"] > frame["Open"])
        | (frame["Low"] > frame["Close"])
        | (frame["Volume"] < 0)
    )
    if invalid_bar.any():
        raise NoMarketDataError(symbol, resolved.symbol, "TradingView returned invalid OHLCV fields")

    frame = frame.sort_values("Date")
    frame = frame[(frame["Date"] >= start) & (frame["Date"] < end + timedelta(days=1))]
    frame = frame.reset_index(drop=True)
    if frame.empty:
        raise NoMarketDataError(
            symbol,
            resolved.symbol,
            f"no rows between {start_date} and {end_date}",
        )
    _assert_ohlcv_not_stale(frame, end_date, symbol, resolved.symbol)

    return ProviderResult(
        data=frame,
        provider="tradingview",
        requested=ref,
        resolved_symbol=resolved.symbol,
        as_of=frame["Date"].max().to_pydatetime().replace(tzinfo=timezone.utc),
        adjustment_mode="Japanese",
        quote_currency=_currency_field(payload.get("info"), "currency_code"),
        provenance={"endpoint": f"/api/price/{path_symbol}"},
    )


def get_tradingview_stock(symbol: str, start_date: str, end_date: str) -> str:
    """Return TradingView daily prices in the existing stock report format."""
    result = fetch_tradingview_ohlcv(symbol, start_date, end_date)
    label = result.resolved_symbol
    if result.resolved_symbol != result.requested.raw_symbol.upper():
        label = f"{result.resolved_symbol} (from {result.requested.raw_symbol})"
    header = f"# Stock data for {label} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(result.data)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    if result.quote_currency:
        header += f"# Quote currency: {result.quote_currency}\n"
    header += "\n"
    return header + result.data.to_csv(index=False)


def get_tradingview_indicators(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int,
) -> str:
    """Calculate stockstats indicators from TradingView daily candles."""
    validate_indicator(indicator)
    end = datetime.strptime(curr_date, "%Y-%m-%d")
    start = end - timedelta(days=look_back_days + 250)
    result = fetch_tradingview_ohlcv(
        symbol,
        start.strftime("%Y-%m-%d"),
        curr_date,
    )
    return calculate_indicator_window(
        result.data, symbol, indicator, curr_date, look_back_days
    )


def get_tradingview_identity(
    ticker: str,
    *,
    client: TradingViewClient | None = None,
) -> dict[str, str]:
    """Return normalized company identity fields from TradingView."""
    api = client or TradingViewClient()
    _, resolved = _resolve(ticker, api)
    path_symbol = encode_path_symbol(resolved.symbol)
    payload = api.get(f"/api/market-data/{path_symbol}/company")
    company: Any = payload.get("company")
    if not isinstance(company, dict):
        raise NoMarketDataError(ticker, resolved.symbol, "TradingView returned no company identity")

    local_name = _company_display_name(company, payload)
    english_name = _identity_field(company.get("description")) or _identity_field(
        payload.get("description")
    )
    identity = {
        "company_name": local_name or english_name,
        "sector": _identity_field(company.get("sector")),
        "industry": _identity_field(company.get("industry")),
        "exchange": _identity_field(company.get("listed_exchange")),
        "quote_currency": _currency_field(company, "currency_code", "currency"),
        "fundamental_currency": _currency_field(
            company,
            "fundamental_currency_code",
            "currency_fund",
        ),
    }
    if (
        local_name
        and english_name
        and local_name != english_name
        and identity.get("company_name") == local_name
    ):
        identity["english_name"] = english_name
    if not any(identity.values()):
        raise NoMarketDataError(ticker, resolved.symbol, "TradingView returned no company identity")
    return {**{key: value for key, value in identity.items() if value}, "quote_type": "stock"}


def _company_display_name(company: dict[str, Any], payload: Mapping[str, Any] | None = None) -> str:
    """Prefer TradingView localized name, then English description."""
    sources: list[Any] = [
        company.get("local_description"),
        company.get("local-description"),
    ]
    if payload is not None:
        sources.extend(
            [
                payload.get("local_description"),
                payload.get("local-description"),
            ]
        )
    sources.append(company.get("description"))
    if payload is not None:
        sources.append(payload.get("description"))
    for value in sources:
        text = _identity_field(value)
        if text:
            return text
    return ""


def _identity_field(value: Any) -> str:
    """Normalize TradingView company fields and discard placeholder values."""
    text = value.strip() if isinstance(value, str) else str(value or "").strip()
    return "" if text.lower() in {"", "-", "n/a", "na", "none", "null", "unknown"} else text


def _currency_field(source: Any, *keys: str) -> str | None:
    if not isinstance(source, dict):
        return None
    for key in keys:
        value = _identity_field(source.get(key))
        if value:
            return value.upper()
    return None
