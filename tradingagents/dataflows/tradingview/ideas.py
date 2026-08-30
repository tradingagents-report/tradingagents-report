"""TradingView community ideas / minds adapters for sentiment context."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from ..errors import (
    NoMarketDataError,
    VendorAuthenticationError,
    VendorNotConfiguredError,
    VendorRateLimitError,
    VendorUnavailableError,
)
from ..provider_models import parse_instrument
from .client import TradingViewClient
from .symbols import encode_path_symbol, resolve_tradingview_symbol

logger = logging.getLogger(__name__)

_DIRECTION_LABELS = {
    0: "Neutral",
    1: "Long",
    2: "Short",
}


def _search_markets(client: TradingViewClient, query: str, asset_class: str):
    market = {"equity": "stock"}.get(asset_class, asset_class)
    payload = client.get(
        f"/api/search/market/{quote(query, safe='')}",
        params={"filter": market},
    )
    markets = payload.get("markets", []) if isinstance(payload, Mapping) else []
    return markets if isinstance(markets, list) else []


def _resolve(symbol: str, client: TradingViewClient) -> str:
    ref = parse_instrument(symbol)
    search = None
    if not ref.exchange_hint:

        def search(query: str):
            return _search_markets(client, query, ref.asset_class)

    return resolve_tradingview_symbol(ref, search=search).symbol


def _direction_label(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "Unknown"
    return _DIRECTION_LABELS.get(int(value), f"Unknown({value})")


def _idea_timestamp(item: Mapping[str, Any]) -> datetime | None:
    ts = item.get("date_timestamp")
    if isinstance(ts, (int, float)) and not isinstance(ts, bool):
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    created = item.get("created_at")
    if isinstance(created, str) and created.strip():
        text = created.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _truncate(text: str, limit: int = 220) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "…"


def get_tradingview_ideas(
    ticker: str,
    curr_date: str | None = None,
    limit: int = 10,
    *,
    client: TradingViewClient | None = None,
) -> str:
    """Return recent TradingView chart ideas for ``ticker`` as prompt text.

    When ``curr_date`` is set, ideas created after that date are excluded to
    reduce look-ahead bias in historical runs.
    """
    api = client or TradingViewClient()
    resolved = _resolve(ticker, api)
    path_symbol = encode_path_symbol(resolved)
    payload = api.get(
        f"/api/ideas/list/{path_symbol}",
        params={"page": 1, "per_page": max(1, min(int(limit), 20)), "lang": "en"},
    )
    if not isinstance(payload, list) or not payload:
        raise NoMarketDataError(ticker, resolved, "TradingView returned no ideas")

    as_of: datetime | None = None
    if curr_date:
        as_of = datetime.strptime(curr_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )

    lines = [
        f"# TradingView Ideas for {resolved}",
        "# Chart-community ideas (direction: Long/Short/Neutral). Weight below news.",
        "",
    ]
    long_n = short_n = neutral_n = 0
    kept = 0
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        created = _idea_timestamp(item)
        if as_of is not None and created is not None and created > as_of:
            continue
        symbol_meta = item.get("symbol") if isinstance(item.get("symbol"), Mapping) else {}
        direction = _direction_label(
            item.get("direction", symbol_meta.get("direction") if symbol_meta else None)
        )
        if direction == "Long":
            long_n += 1
        elif direction == "Short":
            short_n += 1
        else:
            neutral_n += 1

        title = str(item.get("name") or "Untitled idea").strip()
        author = "?"
        user = item.get("user")
        if isinstance(user, Mapping):
            author = str(user.get("username") or "?")
        likes = item.get("likes_count")
        comments = item.get("comments_count")
        when = created.strftime("%Y-%m-%d") if created else "n/a"
        desc = item.get("description")
        excerpt = _truncate(str(desc)) if isinstance(desc, str) and desc.strip() else ""

        lines.append(f"## [{direction}] {title}")
        lines.append(f"Author: {author} | Date: {when} | Likes: {likes} | Comments: {comments}")
        if excerpt:
            lines.append(excerpt)
        lines.append("")
        kept += 1
        if kept >= limit:
            break

    if kept == 0:
        raise NoMarketDataError(
            ticker, resolved, "no ideas on or before the analysis date"
        )

    lines.insert(
        2,
        f"# Direction mix (shown): Long={long_n}, Short={short_n}, Neutral/Other={neutral_n}",
    )
    return "\n".join(lines).rstrip() + "\n"


def fetch_tradingview_ideas(
    ticker: str,
    curr_date: str | None = None,
    limit: int = 10,
    *,
    client: TradingViewClient | None = None,
) -> str:
    """Sentiment-safe wrapper: never raises; returns a placeholder on failure."""
    try:
        return get_tradingview_ideas(ticker, curr_date=curr_date, limit=limit, client=client)
    except VendorNotConfiguredError:
        return "<tradingview ideas unavailable: VendorNotConfiguredError>"
    except (
        VendorAuthenticationError,
        VendorRateLimitError,
        VendorUnavailableError,
        NoMarketDataError,
        ValueError,
        TypeError,
        OSError,
    ) as exc:
        logger.warning("TradingView ideas fetch failed for %s: %s", ticker, exc)
        return f"<tradingview ideas unavailable: {type(exc).__name__}>"
