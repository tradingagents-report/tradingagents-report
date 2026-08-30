"""Deterministic market-data verification snapshot.

The market analyst is an LLM that can confabulate exact numbers — citing a
Bollinger band or a "historically validated bounce" that the underlying data
doesn't support (#830). This module computes a ground-truth snapshot (latest
OHLCV row on or before the analysis date, common indicators, recent closes)
the analyst is told to treat as the source of truth for any exact numeric
claim. Deterministic, no LLM involved.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd
from stockstats import wrap

from tradingagents.dataflows.structured_data import get_ohlcv

# A fixed, common indicator set so the snapshot is the same shape every run.
DEFAULT_SNAPSHOT_INDICATORS: tuple[str, ...] = (
    "close_10_ema", "close_50_sma", "close_200_sma",
    "rsi", "boll", "boll_ub", "boll_lb",
    "macd", "macds", "macdh", "atr",
)


def _verified_rows(symbol: str, curr_date: str) -> pd.DataFrame:
    """OHLCV on or before curr_date, date-sorted. Raises if nothing usable.

    The structured provider route requests one year through ``curr_date``.
    We re-apply the cutoff defensively because this verification path must not
    trust its input to be pre-filtered.
    """
    end_date = pd.Timestamp(curr_date)
    start_date = end_date - pd.DateOffset(years=1)
    data = get_ohlcv(
        symbol,
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d"),
    )
    if data is None or data.empty:
        raise ValueError(f"No OHLCV data available for {symbol}.")

    df = data.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    df = df[df["Date"] <= pd.to_datetime(curr_date)].sort_values("Date")
    if df.empty:
        raise ValueError(f"No OHLCV rows on or before {curr_date} for {symbol}.")
    return df


def _fmt(value) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int,)):
        return str(value)
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


PRICE_CHART_MAX_BARS = 180
PRICE_CHART_INDICATORS: tuple[str, ...] = DEFAULT_SNAPSHOT_INDICATORS


def _quote_currency(df: pd.DataFrame) -> str | None:
    quote_currency = df.attrs.get("quote_currency")
    if isinstance(quote_currency, str) and quote_currency.strip():
        return quote_currency.strip()
    return None


def _reference_from_frame(df: pd.DataFrame) -> dict[str, str | float | None]:
    latest = df.iloc[-1]
    close = pd.to_numeric(latest.get("Close"), errors="coerce")
    if pd.isna(close):
        raise ValueError("Latest OHLCV row has no usable close.")
    return {
        "as_of_price": float(close),
        "as_of_date": _fmt(latest["Date"]),
        "currency": _quote_currency(df),
    }


def _bar_unix(value) -> int | None:
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        return None
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC")
    date = ts.date()
    return int(pd.Timestamp(date, tz="UTC").timestamp())


def _optional_float(value) -> float | None:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return None
    parsed = float(number)
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _indicator_frame(df: pd.DataFrame) -> pd.DataFrame:
    try:
        stock_df = wrap(df.copy())
    except Exception:  # noqa: BLE001 - charts can ship OHLCV without indicators
        return pd.DataFrame()
    for name in PRICE_CHART_INDICATORS:
        try:
            stock_df[name]
        except Exception:  # noqa: BLE001 - skip one broken indicator
            continue
    return stock_df


def _apply_indicator_values(
    bar: dict[str, float | int],
    indicator_row,
    columns,
) -> None:
    for name in PRICE_CHART_INDICATORS:
        if name in bar or name not in columns:
            continue
        value = _optional_float(indicator_row.get(name))
        if value is not None:
            bar[name] = value


def fill_missing_price_chart_indicators(
    bars: list[dict[str, float | int]],
) -> list[dict[str, float | int]]:
    """Attach RSI/MACD/etc. from stored OHLCV when the snapshot omitted them.

    Does not fetch market data. Analysis-time indicator keys are left as-is.
    """
    if not bars or any(
        any(name in bar for name in PRICE_CHART_INDICATORS) for bar in bars
    ):
        return bars
    frame = pd.DataFrame(
        {
            "Date": [
                pd.Timestamp(int(bar["time"]), unit="s", tz="UTC") for bar in bars
            ],
            "Open": [bar["open"] for bar in bars],
            "High": [bar["high"] for bar in bars],
            "Low": [bar["low"] for bar in bars],
            "Close": [bar["close"] for bar in bars],
            "Volume": [bar.get("volume") or 0 for bar in bars],
        }
    )
    indicators = _indicator_frame(frame)
    if indicators.empty:
        return bars
    for position, bar in enumerate(bars):
        if position >= len(indicators):
            break
        _apply_indicator_values(bar, indicators.iloc[position], indicators.columns)
    return bars


def _price_chart_from_frame(
    df: pd.DataFrame,
    curr_date: str,
    max_bars: int = PRICE_CHART_MAX_BARS,
) -> dict[str, object] | None:
    window = max(1, min(int(max_bars), PRICE_CHART_MAX_BARS))
    indicators = _indicator_frame(df)
    tail = df.tail(window)
    indicator_tail = indicators.iloc[-len(tail) :] if not indicators.empty else None
    bars: list[dict[str, float | int]] = []
    for position, (_, row) in enumerate(tail.iterrows()):
        time = _bar_unix(row.get("Date"))
        open_ = _optional_float(row.get("Open"))
        high = _optional_float(row.get("High"))
        low = _optional_float(row.get("Low"))
        close = _optional_float(row.get("Close"))
        volume = _optional_float(row.get("Volume"))
        if time is None or open_ is None or high is None or low is None or close is None:
            continue
        bar: dict[str, float | int] = {
            "time": int(time),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": 0.0 if volume is None else volume,
        }
        if indicator_tail is not None and position < len(indicator_tail):
            _apply_indicator_values(
                bar, indicator_tail.iloc[position], indicator_tail.columns
            )
        bars.append(bar)
    if not bars:
        return None
    timezone = df.attrs.get("timezone")
    return {
        "as_of": _fmt(df.iloc[-1]["Date"]) or curr_date,
        "currency": _quote_currency(df),
        "source": "verified",
        "timezone": (
            timezone.strip()
            if isinstance(timezone, str) and timezone.strip()
            else None
        ),
        "bars": bars,
    }


def get_verified_market_bundle(
    symbol: str,
    curr_date: str,
    max_bars: int = PRICE_CHART_MAX_BARS,
) -> dict[str, object]:
    """Reference card fields plus a look-ahead-safe daily OHLCV snapshot."""
    df = _verified_rows(symbol, curr_date)
    return {
        "reference": _reference_from_frame(df),
        "price_chart": _price_chart_from_frame(df, curr_date, max_bars),
    }


def get_verified_market_reference(symbol: str, curr_date: str) -> dict[str, str | float | None]:
    """Return the deterministic reference price metadata used by the result card."""
    reference = get_verified_market_bundle(symbol, curr_date)["reference"]
    if not isinstance(reference, dict):
        raise TypeError("Verified market bundle is missing reference fields")
    return reference


def build_verified_market_snapshot(
    symbol: str,
    curr_date: str,
    look_back_days: int = 30,
    indicators: Iterable[str] | None = None,
) -> str:
    """Render a ground-truth snapshot: latest OHLCV row, indicators, recent closes."""
    # `df` keeps the original capitalized OHLCV columns (Open/High/Low/Close/
    # Volume); stockstats `wrap()` lowercases columns and adds indicator
    # columns, so read raw prices from `df` and indicators from `stock_df`.
    df = _verified_rows(symbol, curr_date)
    stock_df = wrap(df.copy())

    selected = tuple(indicators or DEFAULT_SNAPSHOT_INDICATORS)
    indicator_values: dict[str, str] = {}
    for name in selected:
        try:
            stock_df[name]  # triggers stockstats calculation
            indicator_values[name] = _fmt(stock_df.iloc[-1][name])
        except Exception as exc:  # noqa: BLE001 — one bad indicator shouldn't sink the snapshot
            indicator_values[name] = f"N/A ({type(exc).__name__})"

    latest = df.iloc[-1]
    latest_date = _fmt(latest["Date"])
    window = max(1, min(int(look_back_days), 30))
    recent = df.tail(window)

    lines = [
        f"## Verified market data snapshot for {symbol.upper()}",
        "",
        f"- Requested analysis date: {curr_date}",
        f"- Latest trading row used: {latest_date}",
        "- Rows after the requested analysis date are excluded before verification.",
    ]
    quote_currency = df.attrs.get("quote_currency")
    if isinstance(quote_currency, str) and quote_currency.strip():
        lines.append(f"- Quote currency: {quote_currency.strip()}")
    lines += [
        "",
        "### Latest verified OHLCV row",
        "",
        "| Field | Value |",
        "|---|---:|",
    ]
    for field in ("Open", "High", "Low", "Close", "Volume"):
        lines.append(f"| {field} | {_fmt(latest.get(field))} |")

    lines += ["", "### Verified technical indicators (latest row)", "",
              "| Indicator | Value |", "|---|---:|"]
    for name, value in indicator_values.items():
        lines.append(f"| {name} | {value} |")

    lines += ["", f"### Recent verified closes (last {len(recent)} rows)", "",
              "| Date | Close |", "|---|---:|"]
    for _, row in recent.iterrows():
        lines.append(f"| {_fmt(row['Date'])} | {_fmt(row.get('Close'))} |")

    lines += [
        "",
        "Use this snapshot as the source of truth for exact OHLCV, price-level, "
        "and indicator-value claims. If another tool output conflicts with it, "
        "flag the discrepancy rather than inventing a reconciled number. Do not "
        "claim historical validation, support/resistance bounces, or exact "
        "percentage moves unless directly supported by tool output with concrete "
        "dates and prices.",
    ]
    return "\n".join(lines)
