"""Provider-neutral normalization shared by A-share adapters."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

import pandas as pd

from ..errors import NoMarketDataError, VendorUnavailableError
from ..listings import resolve_listing
from ..provider_models import InstrumentRef, ProviderResult, parse_instrument
from ..stockstats_utils import calculate_indicator_window, validate_indicator

_COLUMN_ALIASES = {
    "Date": ("Date", "date", "日期", "trade_date"),
    "Open": ("Open", "open", "开盘"),
    "High": ("High", "high", "最高"),
    "Low": ("Low", "low", "最低"),
    "Close": ("Close", "close", "收盘"),
    "Volume": ("Volume", "volume", "vol", "成交量"),
    "Amount": ("Amount", "amount", "成交额"),
}


def resolve_cn_symbol(symbol: str) -> tuple[InstrumentRef, str, str]:
    """Resolve an exchange-qualified A-share symbol into exchange and code."""
    listing = resolve_listing(symbol)
    if listing.exchange not in {"SSE", "SZSE"}:
        raise ValueError(
            "A-share symbols must be exchange-qualified, for example "
            "600519.SS, SSE:600519, or 000001.SZ"
        )
    return parse_instrument(listing.provider_symbol), listing.exchange, listing.symbol


def _column_mapping(raw: pd.DataFrame) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for target, candidates in _COLUMN_ALIASES.items():
        source = next((candidate for candidate in candidates if candidate in raw.columns), None)
        if source is not None:
            mapping[source] = target
    return mapping


def normalize_ohlcv(
    raw: pd.DataFrame,
    *,
    provider: str,
    requested_symbol: str,
    resolved_symbol: str,
    start_date: str,
    end_date: str,
    adjustment_mode: str | None = None,
    quote_currency: str = "CNY",
    market: str = "CN",
) -> ProviderResult[pd.DataFrame]:
    """Validate and normalize one inclusive OHLCV window."""
    if not isinstance(raw, pd.DataFrame) or raw.empty:
        raise NoMarketDataError(requested_symbol, resolved_symbol, f"{provider} returned no rows")
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    if end < start:
        raise ValueError("end_date must not be before start_date")

    frame = raw.rename(columns=_column_mapping(raw)).copy()
    required = ["Date", "Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise VendorUnavailableError(f"{provider} OHLCV is missing columns: {missing}")
    selected = required + (["Amount"] if "Amount" in frame.columns else [])
    frame = frame[selected]
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    numeric = [column for column in selected if column != "Date"]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="coerce")
    if frame["Date"].isna().any() or frame[required[1:]].isna().any().any():
        raise VendorUnavailableError(f"{provider} returned invalid OHLCV fields")
    frame = frame[(frame["Date"] >= start) & (frame["Date"] <= end)]
    frame = frame.sort_values("Date").reset_index(drop=True)
    if frame.empty:
        raise NoMarketDataError(
            requested_symbol,
            resolved_symbol,
            f"no rows between {start_date} and {end_date}",
        )
    return ProviderResult(
        data=frame,
        provider=provider,
        requested=parse_instrument(requested_symbol),
        resolved_symbol=resolved_symbol,
        as_of=frame["Date"].max().to_pydatetime(),
        adjustment_mode=adjustment_mode,
        quote_currency=quote_currency,
        provenance={"market": market},
    )


def format_stock_data(
    result: ProviderResult[pd.DataFrame],
    start_date: str,
    end_date: str,
) -> str:
    """Format normalized rows for the existing text-oriented market tool."""
    frame = result.data.copy()
    frame["Date"] = frame["Date"].dt.strftime("%Y-%m-%d")
    fetched_at = datetime.now().isoformat(timespec="seconds")
    return (
        f"# {result.requested.raw_symbol} stock data\n\n"
        f"- Provider: {result.provider}\n"
        f"- Resolved symbol: {result.resolved_symbol}\n"
        f"- Date range: {start_date} to {end_date}\n"
        f"- Currency: {result.quote_currency or 'unknown'}\n"
        f"- Fetched at: {fetched_at}\n\n" + frame.to_csv(index=False)
    )


def stock_text_from_fetch(
    fetch: Callable[..., ProviderResult[pd.DataFrame]],
    symbol: str,
    start_date: str,
    end_date: str,
) -> str:
    """Adapt a structured OHLCV fetcher to the existing text tool contract."""
    return format_stock_data(
        fetch(symbol, start_date, end_date),
        start_date,
        end_date,
    )


def indicators_from_fetch(
    fetch: Callable[..., ProviderResult[pd.DataFrame]],
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int,
) -> str:
    """Calculate an existing stockstats indicator from provider OHLCV."""
    validate_indicator(indicator)
    end = datetime.strptime(curr_date, "%Y-%m-%d")
    start = end - timedelta(days=look_back_days + 250)
    result = fetch(
        symbol,
        start.strftime("%Y-%m-%d"),
        curr_date,
    )
    return calculate_indicator_window(
        result.data,
        symbol,
        indicator,
        curr_date,
        look_back_days,
    )
