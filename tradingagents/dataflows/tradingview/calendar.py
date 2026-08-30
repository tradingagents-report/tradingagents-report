"""TradingView earnings and economic calendar adapters (look-ahead aware)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from ..exchange_catalog import tv_market_for_symbol
from ..provider_models import parse_instrument
from .client import TradingViewClient
from .symbols import resolve_tradingview_symbol

_MAX_CALENDAR_WINDOW_DAYS = 40


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


def _parse_curr_date(curr_date: str) -> datetime:
    return datetime.strptime(curr_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _clamp_window(look_back_days: int, look_forward_days: int) -> tuple[int, int]:
    look_back = max(0, int(look_back_days))
    look_forward = max(0, int(look_forward_days))
    total = look_back + look_forward
    if total <= 0:
        look_forward = 7
        total = look_forward
    if total > _MAX_CALENDAR_WINDOW_DAYS:
        # Prefer forward visibility for event risk; shrink look-back first.
        overflow = total - _MAX_CALENDAR_WINDOW_DAYS
        shrink_back = min(look_back, overflow)
        look_back -= shrink_back
        overflow -= shrink_back
        look_forward = max(0, look_forward - overflow)
    return look_back, look_forward


def _window_bounds(
    curr_date: str,
    look_back_days: int,
    look_forward_days: int,
) -> tuple[datetime, datetime, int, int]:
    look_back, look_forward = _clamp_window(look_back_days, look_forward_days)
    as_of = _parse_curr_date(curr_date)
    start = as_of - timedelta(days=look_back)
    return as_of, start, look_back, look_forward


def _parse_event_dt(value: Any) -> datetime | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "n/a"
    return value.strftime("%Y-%m-%d %H:%M UTC")


def _fmt_scalar(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def get_tradingview_earnings_calendar(
    curr_date: str,
    look_forward_days: int = 14,
    market: str | None = None,
    ticker: str | None = None,
    *,
    client: TradingViewClient | None = None,
) -> str:
    """Return earnings events around ``curr_date``, optionally filtered to one ticker.

    Future events relative to ``curr_date`` omit realized surprise/actual fields
    to reduce look-ahead bias in historical runs.

    When ``market`` is omitted, infer it from ``ticker`` via the exchange catalog;
    fall back to ``america`` only for market-wide scans without a ticker.
    """
    as_of, start, look_back, look_forward = _window_bounds(curr_date, 0, look_forward_days)
    end = as_of + timedelta(days=look_forward) + timedelta(hours=23, minutes=59, seconds=59)
    api = client or TradingViewClient()

    resolved = None
    if ticker:
        resolved = _resolve(ticker, api)

    if market and str(market).strip():
        market_code = str(market).strip().lower()
    else:
        market_code = (
            tv_market_for_symbol(ticker)
            or tv_market_for_symbol(resolved)
            or ("america" if not ticker else None)
        )
    if not market_code:
        return (
            f"No earnings calendar market could be inferred for {ticker or resolved}; "
            "pass market= explicitly (e.g. america, china, hongkong)."
        )

    params: dict[str, Any] = {
        "from": int(start.timestamp()),
        "to": int(end.timestamp()),
        "market": market_code,
    }
    payload = api.get("/api/calendar/earnings", params=params)
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        return (
            f"No earnings calendar events found for market={market_code} "
            f"between {start.date()} and {end.date()}"
        )

    lines = [
        f"# Earnings Calendar ({market_code})",
        f"# As-of analysis date: {curr_date}",
        f"# Window: +{look_forward} day(s) (TradingView max span {_MAX_CALENDAR_WINDOW_DAYS}d)",
        "",
    ]
    matched = 0
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        symbol = row.get("symbol")
        if not isinstance(symbol, str):
            continue
        if resolved is not None and symbol.upper() != resolved.upper():
            # Also accept bare ticker match (e.g. AAPL vs NASDAQ:AAPL).
            bare = symbol.split(":", 1)[-1].upper()
            if bare != resolved.split(":", 1)[-1].upper() and bare != str(ticker).upper():
                continue

        event_dt = _parse_event_dt(
            row.get("earnings_release_next_date") or row.get("earnings_release_date")
        )
        if event_dt is None or event_dt < start or event_dt > end:
            continue

        is_future = event_dt.date() > as_of.date()
        name = row.get("description") or row.get("name") or symbol
        lines.append(f"## {symbol} — {name}")
        lines.append(f"Earnings date: {_fmt_dt(event_dt)}")
        if not is_future:
            lines.append(f"EPS (FQ): {_fmt_scalar(row.get('earnings_per_share_fq'))}")
            lines.append(f"EPS forecast (FQ): {_fmt_scalar(row.get('earnings_per_share_forecast_fq'))}")
            lines.append(f"EPS surprise %: {_fmt_scalar(row.get('eps_surprise_percent_fq'))}")
            lines.append(f"Revenue (FQ): {_fmt_scalar(row.get('revenue_fq'))}")
            lines.append(f"Revenue surprise %: {_fmt_scalar(row.get('revenue_surprise_percent_fq'))}")
        else:
            lines.append(
                f"EPS forecast (next): {_fmt_scalar(row.get('earnings_per_share_forecast_next_fq'))}"
            )
            lines.append(
                f"Revenue forecast (next): {_fmt_scalar(row.get('revenue_forecast_next_fq'))}"
            )
            lines.append(
                "(Actuals omitted: event is after the analysis date — avoid look-ahead.)"
            )
        lines.append("")
        matched += 1

    if matched == 0:
        scope = f" for {resolved or ticker}" if ticker else ""
        return (
            f"No earnings calendar events found{scope} for market={market_code} "
            f"between {start.date()} and {end.date()}"
        )
    return "\n".join(lines).rstrip() + "\n"


def get_tradingview_economic_calendar(
    curr_date: str,
    look_back_days: int = 7,
    look_forward_days: int = 14,
    market: str | None = None,
    *,
    client: TradingViewClient | None = None,
) -> str:
    """Return macro calendar events around ``curr_date``.

    Events after ``curr_date`` keep forecast/previous but redact ``actual`` values.
    """
    as_of, start, look_back, look_forward = _window_bounds(
        curr_date, look_back_days, look_forward_days
    )
    end = as_of + timedelta(days=look_forward) + timedelta(hours=23, minutes=59, seconds=59)
    api = client or TradingViewClient()
    params: dict[str, Any] = {
        "from": int(start.timestamp()),
        "to": int(end.timestamp()),
    }
    if market:
        params["market"] = market

    payload = api.get("/api/calendar/economic", params=params)
    rows = payload.get("result")
    if not isinstance(rows, list) or not rows:
        return (
            f"No economic calendar events found between {start.date()} and {end.date()}"
        )

    market_label = market or "all"
    lines = [
        f"# Economic Calendar ({market_label})",
        f"# As-of analysis date: {curr_date}",
        f"# Window: -{look_back}/+{look_forward} day(s)",
        "",
    ]
    matched = 0
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        event_dt = _parse_event_dt(row.get("date"))
        if event_dt is None or event_dt < start or event_dt > end:
            continue
        is_future = event_dt.date() > as_of.date()
        title = row.get("title") or row.get("indicator") or "Event"
        country = row.get("country") or ""
        importance = row.get("importance")
        lines.append(f"## {title}" + (f" ({country})" if country else ""))
        lines.append(f"Date: {_fmt_dt(event_dt)}")
        if importance is not None:
            lines.append(f"Importance: {importance}")
        lines.append(f"Previous: {_fmt_scalar(row.get('previous'))}")
        lines.append(f"Forecast: {_fmt_scalar(row.get('forecast'))}")
        if is_future:
            lines.append("Actual: n/a (event after analysis date — actual redacted)")
        else:
            lines.append(f"Actual: {_fmt_scalar(row.get('actual'))}")
        lines.append("")
        matched += 1

    if matched == 0:
        return (
            f"No economic calendar events found between {start.date()} and {end.date()}"
        )
    return "\n".join(lines).rstrip() + "\n"
