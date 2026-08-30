"""Look-ahead-safe Finnhub online news and insider transactions."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from ..listings import resolve_listing
from ..news_utils import in_news_window
from .client import get_client, translate_error


def _published(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OSError):
        return None


def get_finnhub_news(
    symbol: str,
    start_date: str,
    end_date: str,
    *,
    client: Any | None = None,
) -> str:
    ticker = resolve_listing(symbol).symbol.upper()
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    try:
        rows = (client or get_client()).company_news(ticker, _from=start_date, to=end_date)
    except Exception as exc:
        raise translate_error(exc, "company news request") from exc
    filtered = [
        row for row in rows or [] if in_news_window(_published(row.get("datetime")), start, end)
    ]
    if not filtered:
        return f"No news found for {symbol} between {start_date} and {end_date}"
    return f"# Finnhub news for {ticker}\n\n" + json.dumps(filtered, ensure_ascii=False)


def get_finnhub_global_news(
    curr_date: str,
    look_back_days: int = 7,
    limit: int = 50,
    *,
    client: Any | None = None,
) -> str:
    end = datetime.strptime(curr_date, "%Y-%m-%d")
    start = end - timedelta(days=look_back_days)
    try:
        rows = (client or get_client()).general_news("general", min_id=0)
    except Exception as exc:
        raise translate_error(exc, "global news request") from exc
    filtered = [
        row for row in rows or [] if in_news_window(_published(row.get("datetime")), start, end)
    ][:limit]
    if not filtered:
        return f"No global news found between {start.date()} and {curr_date}"
    return "# Finnhub global news\n\n" + json.dumps(filtered, ensure_ascii=False)


def get_finnhub_insider_transactions(
    symbol: str,
    curr_date: str | None = None,
    *,
    client: Any | None = None,
) -> str:
    ticker = resolve_listing(symbol).symbol.upper()
    end = datetime.strptime(curr_date, "%Y-%m-%d") if curr_date else datetime.now()
    start = end - timedelta(days=365)
    try:
        response = (client or get_client()).stock_insider_transactions(
            ticker, _from=start.strftime("%Y-%m-%d"), to=end.strftime("%Y-%m-%d")
        )
    except Exception as exc:
        raise translate_error(exc, "insider transactions request") from exc
    rows = (response or {}).get("data", [])
    filtered = []
    for row in rows:
        date = datetime.strptime(str(row.get("transactionDate")), "%Y-%m-%d")
        if start <= date <= end:
            filtered.append(row)
    if not filtered:
        return f"No insider transactions reported for symbol '{ticker}'"
    return f"# Finnhub insider transactions for {ticker}\n\n" + json.dumps(
        filtered, ensure_ascii=False
    )
