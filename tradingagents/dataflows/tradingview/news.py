"""TradingView-based company and global news adapters."""

from __future__ import annotations

import contextlib
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlparse

from dateutil.relativedelta import relativedelta

from ..config import get_config
from ..news_utils import in_news_window
from ..provider_models import parse_instrument
from .client import TradingViewClient
from .symbols import resolve_tradingview_symbol


def _tradingview_market(asset_class: str) -> str:
    return {"equity": "stock"}.get(asset_class, asset_class)


def _search_markets(client: TradingViewClient, query: str, asset_class: str):
    payload = client.get(
        f"/api/search/market/{quote(query, safe='')}",
        params={"filter": _tradingview_market(asset_class)},
    )
    markets = payload.get("markets", [])
    return markets if isinstance(markets, list) else []


def _resolve(symbol: str, client: TradingViewClient):
    ref = parse_instrument(symbol)
    search = None
    if not ref.exchange_hint:

        def search(query: str):
            return _search_markets(client, query, ref.asset_class)

    return ref, resolve_tradingview_symbol(ref, search=search)


def _published_at(item: dict[str, Any]) -> datetime | None:
    published = item.get("published")
    if published is None:
        return None
    with contextlib.suppress(TypeError, ValueError, OSError, OverflowError):
        return datetime.fromtimestamp(float(published), tz=timezone.utc).replace(tzinfo=None)
    return None


def _article_data(item: dict[str, Any]) -> dict[str, Any]:
    provider = item.get("provider")
    publisher = _article_text(provider.get("name")) if isinstance(provider, dict) else ""
    direct_link = _direct_link(item.get("link"))
    story_path_link = _story_path_link(item.get("storyPath"))
    return {
        "title": _article_text(item.get("title")),
        "summary": item.get("summary") or item.get("description") or "",
        "publisher": publisher,
        "link": direct_link or story_path_link,
        "pub_date": _published_at(item),
    }


def _article_text(value: Any) -> str:
    text = value.strip() if isinstance(value, str) else ""
    return "" if text.lower() in {"", "-", "n/a", "na", "none", "null", "unknown", "no title"} else text


def _direct_link(value: Any) -> str:
    link = value.strip() if isinstance(value, str) else ""
    parsed = urlparse(link)
    return link if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def _story_path_link(value: Any) -> str:
    path = value.strip() if isinstance(value, str) else ""
    if not path.startswith("/") or path.startswith("//"):
        return ""
    return f"https://www.tradingview.com{path}"


def _filtered_articles(
    items: Any,
    start_dt: datetime,
    end_dt: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    filtered = []
    seen = set()
    if not isinstance(items, list):
        return filtered

    for item in items:
        if not isinstance(item, dict):
            continue
        data = _article_data(item)
        if not all((data["title"], data["publisher"], data["link"], data["pub_date"])):
            continue
        if not in_news_window(data["pub_date"], start_dt, end_dt):
            continue
        key = (data["title"], data["pub_date"])
        if key in seen:
            continue
        seen.add(key)
        filtered.append(data)
    return filtered[:limit]


def _format_articles(articles: list[dict[str, Any]]) -> str:
    news = ""
    for article in articles:
        news += f"### {article['title']} (source: {article['publisher']})\n"
        if article["summary"]:
            news += f"{article['summary']}\n"
        if article["link"]:
            news += f"Link: {article['link']}\n"
        news += "\n"
    return news


def get_tradingview_news(
    ticker: str,
    start_date: str,
    end_date: str,
    *,
    client: TradingViewClient | None = None,
) -> str:
    """Retrieve look-ahead-safe company news from TradingView."""
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    api = client or TradingViewClient()
    ref, resolved = _resolve(ticker, api)
    payload = api.get(
        "/api/news",
        params={
            "symbol": resolved.symbol,
            "lang": "en",
            "market": _tradingview_market(ref.asset_class),
        },
    )
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return f"No news found for {ticker}"

    limit = get_config()["news_article_limit"]
    articles = _filtered_articles(items, start_dt, end_dt, limit)
    if not articles:
        return f"No news found for {ticker} between {start_date} and {end_date}"
    return f"## {ticker} News, from {start_date} to {end_date}:\n\n{_format_articles(articles)}"


def get_tradingview_global_news(
    curr_date: str,
    look_back_days: int | None = None,
    limit: int | None = None,
    *,
    client: TradingViewClient | None = None,
) -> str:
    """Retrieve look-ahead-safe economic news from TradingView."""
    config = get_config()
    if look_back_days is None:
        look_back_days = config["global_news_lookback_days"]
    if limit is None:
        limit = config["global_news_article_limit"]

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - relativedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")
    api = client or TradingViewClient()
    payload = api.get("/api/news/economic", params={"lang": "en"})
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return f"No global news found for {curr_date}"

    articles = _filtered_articles(items, start_dt, curr_dt, limit)
    if not articles:
        return f"No global news found between {start_date} and {curr_date}"
    return (
        f"## Global Market News, from {start_date} to {curr_date}:\n\n"
        f"{_format_articles(articles)}"
    )
