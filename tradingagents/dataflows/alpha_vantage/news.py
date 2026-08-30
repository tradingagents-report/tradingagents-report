from __future__ import annotations

import json

from ..listings import is_china_a_share
from .common import _make_api_request, format_datetime_for_api


def get_news(ticker, start_date, end_date) -> dict[str, str] | str:
    """Returns live and historical market news & sentiment data from premier news outlets worldwide.

    Covers stocks, cryptocurrencies, forex, and topics like fiscal policy, mergers & acquisitions, IPOs.

    Args:
        ticker: Stock symbol for news articles.
        start_date: Start date for news search.
        end_date: End date for news search.

    Returns:
        Dictionary containing news sentiment data or JSON string.
    """
    # Alpha Vantage NEWS_SENTIMENT expects US-style tickers. Yahoo/TV A-share
    # forms (``300814.SZ``, ``SZSE:300814``) are rejected and must not reach
    # the wire — return the legacy empty marker so vendor routing can fall back.
    if is_china_a_share(ticker):
        return f"No news found for {ticker}"

    params = {
        "tickers": ticker,
        "time_from": format_datetime_for_api(start_date),
        "time_to": format_datetime_for_api(end_date),
    }

    raw = _make_api_request("NEWS_SENTIMENT", params)
    return _normalize_news_payload(raw, ticker, start_date, end_date)


def get_global_news(curr_date, look_back_days: int = 7, limit: int = 50) -> dict[str, str] | str:
    """Returns global market news & sentiment data without ticker-specific filtering.

    Covers broad market topics like financial markets, economy, and more.

    Args:
        curr_date: Current date in yyyy-mm-dd format.
        look_back_days: Number of days to look back (default 7).
        limit: Maximum number of articles (default 50).

    Returns:
        Dictionary containing global news sentiment data or JSON string.
    """
    from datetime import datetime, timedelta

    # Calculate start date
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - timedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    params = {
        "topics": "financial_markets,economy_macro,economy_monetary",
        "time_from": format_datetime_for_api(start_date),
        "time_to": format_datetime_for_api(curr_date),
        "limit": str(limit),
    }

    return _make_api_request("NEWS_SENTIMENT", params)


def get_insider_transactions(symbol: str) -> dict[str, str] | str:
    """Returns latest and historical insider transactions by key stakeholders.

    Covers transactions by founders, executives, board members, etc.

    Args:
        symbol: Ticker symbol. Example: "IBM".

    Returns:
        Dictionary containing insider transaction data or JSON string.
    """
    if is_china_a_share(symbol):
        return f"No insider transactions found for {symbol}"

    params = {
        "symbol": symbol,
    }

    return _make_api_request("INSIDER_TRANSACTIONS", params)


def _normalize_news_payload(
    raw: dict[str, str] | str,
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    """Turn Alpha Vantage news JSON into agent-usable text; empty/error → no-news marker."""
    if isinstance(raw, dict):
        payload = raw
        text = json.dumps(raw)
    else:
        text = raw
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return text

    if not isinstance(payload, dict):
        return text

    error = payload.get("Error Message") or payload.get("Information") or payload.get("Note")
    if isinstance(error, str) and error.strip():
        # Keep the legacy empty prefix so route_to_vendor can try the next vendor.
        return f"No news found for {ticker} between {start_date} and {end_date}"

    feed = payload.get("feed")
    if not isinstance(feed, list) or not feed:
        return f"No news found for {ticker} between {start_date} and {end_date}"

    return text
