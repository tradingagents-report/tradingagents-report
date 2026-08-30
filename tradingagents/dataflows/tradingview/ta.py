"""TradingView multi-timeframe technical analysis gauges and indicator snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from ..errors import NoMarketDataError
from ..provider_models import parse_instrument
from .client import TradingViewClient
from .symbols import encode_path_symbol, resolve_tradingview_symbol

_TIMEFRAME_ORDER = ("1", "5", "15", "60", "240", "1D", "1W", "1M")
_TIMEFRAME_LABELS = {
    "1": "1m",
    "5": "5m",
    "15": "15m",
    "60": "1h",
    "240": "4h",
    "1D": "1D",
    "1W": "1W",
    "1M": "1M",
}

# Keep the indicator dump focused; pivots alone dominate the raw payload.
_INDICATOR_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Momentum",
        (
            "RSI",
            "RSI[1]",
            "Stoch.K",
            "Stoch.K[1]",
            "Stoch.D",
            "Stoch.D[1]",
            "Stoch.RSI.K",
            "CCI20",
            "CCI20[1]",
            "Mom",
            "Mom[1]",
            "AO",
            "AO[1]",
            "AO[2]",
            "W.R",
            "UO",
        ),
    ),
    (
        "Trend",
        (
            "ADX",
            "ADX+DI",
            "ADX+DI[1]",
            "ADX-DI",
            "ADX-DI[1]",
            "MACD.macd",
            "MACD.signal",
            "BBPower",
            "Ichimoku.BLine",
            "HullMA9",
            "VWMA",
            "close",
        ),
    ),
    (
        "Moving Averages",
        (
            "SMA10",
            "SMA20",
            "SMA30",
            "SMA50",
            "SMA100",
            "SMA200",
            "EMA10",
            "EMA20",
            "EMA30",
            "EMA50",
            "EMA100",
            "EMA200",
        ),
    ),
    (
        "Classic Pivots",
        (
            "Pivot.M.Classic.R3",
            "Pivot.M.Classic.R2",
            "Pivot.M.Classic.R1",
            "Pivot.M.Classic.Middle",
            "Pivot.M.Classic.S1",
            "Pivot.M.Classic.S2",
            "Pivot.M.Classic.S3",
        ),
    ),
    (
        "Recommendations (-1 Sell … +1 Buy)",
        (
            "Recommend.All",
            "Recommend.MA",
            "Recommend.Other",
            "Rec.BBPower",
            "Rec.HullMA9",
            "Rec.Ichimoku",
            "Rec.Stoch.RSI",
            "Rec.UO",
            "Rec.VWMA",
            "Rec.WR",
        ),
    ),
)


def _search_markets(client: TradingViewClient, query: str, asset_class: str):
    market = {"equity": "stock"}.get(asset_class, asset_class)
    payload = client.get(
        f"/api/search/market/{quote(query, safe='')}",
        params={"filter": market},
    )
    markets = payload.get("markets", [])
    return markets if isinstance(markets, list) else []


def _resolve(symbol: str, client: TradingViewClient) -> str:
    ref = parse_instrument(symbol)
    search = None
    if not ref.exchange_hint:

        def search(query: str):
            return _search_markets(client, query, ref.asset_class)

    return resolve_tradingview_symbol(ref, search=search).symbol


def _bias_label(score: float) -> str:
    if score >= 0.5:
        return "Strong Buy"
    if score > 0.1:
        return "Buy"
    if score >= -0.1:
        return "Neutral"
    if score > -0.5:
        return "Sell"
    return "Strong Sell"


def _score(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def get_tradingview_ta_summary(
    symbol: str,
    curr_date: str | None = None,
    *,
    client: TradingViewClient | None = None,
) -> str:
    """Return multi-timeframe TradingView Buy/Sell/Neutral gauges."""
    del curr_date
    api = client or TradingViewClient()
    resolved = _resolve(symbol, api)
    path_symbol = encode_path_symbol(resolved)
    payload = api.get(f"/api/ta/{path_symbol}")
    if not isinstance(payload, Mapping) or not payload:
        raise NoMarketDataError(symbol, resolved, "TradingView returned no TA summary")

    retrieved = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        f"# TradingView TA Summary for {resolved}",
        f"# Snapshot retrieved: {retrieved}",
        "# Note: gauges reflect TradingView's latest snapshot, not a historical "
        "point-in-time reconstruction.",
        "# Score guide: roughly -1 Strong Sell … 0 Neutral … +1 Strong Buy",
        "",
        "| Timeframe | Overall | Moving Averages | Oscillators |",
        "| --- | --- | --- | --- |",
    ]

    rows = 0
    for key in _TIMEFRAME_ORDER:
        bucket = payload.get(key)
        if not isinstance(bucket, Mapping):
            continue
        overall = _score(bucket.get("All"))
        ma = _score(bucket.get("MA"))
        other = _score(bucket.get("Other"))
        if overall is None and ma is None and other is None:
            continue
        label = _TIMEFRAME_LABELS.get(key, key)

        def cell(score: float | None) -> str:
            if score is None:
                return "n/a"
            return f"{score:.3f} ({_bias_label(score)})"

        lines.append(f"| {label} | {cell(overall)} | {cell(ma)} | {cell(other)} |")
        rows += 1

    if rows == 0:
        raise NoMarketDataError(symbol, resolved, "TradingView TA summary had no timeframes")
    return "\n".join(lines)


def get_tradingview_ta_indicators(
    symbol: str,
    curr_date: str | None = None,
    *,
    client: TradingViewClient | None = None,
) -> str:
    """Return a curated TradingView indicator snapshot (momentum, trend, pivots)."""
    del curr_date
    api = client or TradingViewClient()
    resolved = _resolve(symbol, api)
    path_symbol = encode_path_symbol(resolved)
    payload = api.get(f"/api/ta/{path_symbol}/indicators")
    if not isinstance(payload, Mapping) or not payload:
        raise NoMarketDataError(symbol, resolved, "TradingView returned no TA indicators")

    retrieved = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        f"# TradingView TA Indicators for {resolved}",
        f"# Snapshot retrieved: {retrieved}",
        "# Note: values reflect TradingView's latest snapshot, not a historical "
        "point-in-time reconstruction.",
        "# Fields ending in [1]/[2] are prior bars — use them for momentum "
        "acceleration/deceleration, not as a second as-of close.",
        "# Prefer Recommend.MA vs Recommend.Other/All when explaining whether "
        "the sell/buy bias is trend-driven or oscillator-driven.",
        "",
    ]

    emitted = 0
    for title, keys in _INDICATOR_GROUPS:
        group_lines = []
        for key in keys:
            value = payload.get(key)
            if value is None or isinstance(value, (dict, list)):
                continue
            if isinstance(value, float):
                group_lines.append(f"{key}: {value:.6g}")
            else:
                group_lines.append(f"{key}: {value}")
        if group_lines:
            lines.append(f"## {title}")
            lines.extend(group_lines)
            lines.append("")
            emitted += len(group_lines)

    if emitted == 0:
        raise NoMarketDataError(symbol, resolved, "TradingView TA indicators had no usable fields")
    return "\n".join(lines).rstrip() + "\n"
