"""TradingView screener-based peer comparison for relative valuation/context."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

from ..errors import NoMarketDataError
from ..exchange_catalog import tv_market_for_exchange, tv_market_for_symbol
from ..provider_models import parse_instrument
from .client import TradingViewClient
from .symbols import encode_path_symbol, resolve_tradingview_symbol


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


def _infer_market(ticker: str, resolved_symbol: str, explicit: str | None) -> str:
    if explicit and str(explicit).strip():
        return str(explicit).strip().lower()
    market = tv_market_for_symbol(ticker) or tv_market_for_symbol(resolved_symbol)
    if market:
        return market
    exchange = resolved_symbol.split(":", 1)[0] if ":" in resolved_symbol else ""
    market = tv_market_for_exchange(exchange)
    if market:
        return market
    raise NoMarketDataError(
        ticker,
        resolved_symbol,
        "could not infer TradingView market_code from exchange catalog; pass market= explicitly",
    )

def _fmt(value: Any, *, pct: bool = False) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        if pct:
            return f"{value:.2f}%"
        if abs(value) >= 1e9:
            return f"{value / 1e9:.2f}B"
        if abs(value) >= 1e6:
            return f"{value / 1e6:.2f}M"
        return f"{value:.4g}"
    if isinstance(value, int) and not isinstance(value, bool):
        if pct:
            return f"{value:.2f}%"
        if abs(value) >= 1_000_000_000:
            return f"{value / 1e9:.2f}B"
        if abs(value) >= 1_000_000:
            return f"{value / 1e6:.2f}M"
        return str(value)
    return str(value)


def _row_name(row: Mapping[str, Any]) -> str:
    view = row.get("ticker_view")
    if isinstance(view, Mapping):
        name = view.get("name") or view.get("description")
        if isinstance(name, str) and name.strip():
            return name.strip()
    symbol = row.get("symbol")
    if isinstance(symbol, str) and ":" in symbol:
        return symbol.split(":", 1)[1]
    return str(symbol or "?")


def get_tradingview_peer_comparison(
    ticker: str,
    curr_date: str | None = None,
    market: str | None = None,
    limit: int = 10,
    *,
    client: TradingViewClient | None = None,
) -> str:
    """Compare ``ticker`` against same-sector peers via the stock screener.

    ``curr_date`` is accepted for tool-signature consistency; screener rows are
    a live snapshot (not point-in-time historical peers).
    """
    del curr_date
    api = client or TradingViewClient()
    resolved = _resolve(ticker, api)
    path_symbol = encode_path_symbol(resolved)
    company = api.get(f"/api/market-data/{path_symbol}/company")
    if not isinstance(company, Mapping):
        raise NoMarketDataError(ticker, resolved, "TradingView returned no company profile")

    # /company may nest under "company" or return flat profile fields.
    profile = company.get("company") if isinstance(company.get("company"), Mapping) else company
    if not isinstance(profile, Mapping):
        raise NoMarketDataError(ticker, resolved, "TradingView company profile missing")

    sector = profile.get("sector") or profile.get("sector-i18n-en")
    if not isinstance(sector, str) or not sector.strip():
        raise NoMarketDataError(ticker, resolved, "company sector unavailable for peer scan")
    sector = sector.strip()

    market_code = _infer_market(ticker, resolved, market)
    page_size = max(5, min(int(limit), 25))
    scan = api.post(
        "/api/screener/scan",
        body={
            "market": market_code,
            "lang": "en",
            "range": [0, page_size],
            "preset_fields": ["overview", "valuation", "technicals"],
            "fields": ["Perf.1W", "Perf.1M"],
            "extra_fields": ["RSI", "Recommend.All"],
            "filters": {"sector": [sector]},
            "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
        },
    )
    if not isinstance(scan, Mapping):
        raise NoMarketDataError(ticker, resolved, "screener returned invalid payload")
    rows = scan.get("data")
    if not isinstance(rows, list) or not rows:
        raise NoMarketDataError(
            ticker, resolved, f"no peers found in sector={sector!r} market={market_code}"
        )

    subject_bare = resolved.split(":", 1)[-1].upper()
    lines = [
        f"# Peer Comparison for {resolved}",
        f"# Sector: {sector} | Market: {market_code}",
        "# Snapshot from TradingView screener (live peers, not historical point-in-time).",
        "",
        "| Symbol | Name | Close | Chg% | Mkt Cap | PE(TTM) | Div% | RSI | TA Rec | 1W% | 1M% |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    matched_subject = False
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        symbol = str(row.get("symbol") or "")
        bare = symbol.split(":", 1)[-1].upper() if symbol else ""
        marker = " ←" if bare == subject_bare or symbol.upper() == resolved.upper() else ""
        if marker:
            matched_subject = True
        pe = row.get("price_earnings_ttm", row.get("price_earnings"))
        rsi = row.get("rsi", row.get("RSI"))
        rec = row.get("recommend_all", row.get("Recommend.All"))
        lines.append(
            "| {symbol}{marker} | {name} | {close} | {chg} | {mcap} | {pe} | {div} | {rsi} | {rec} | {w1} | {m1} |".format(
                symbol=symbol or "?",
                marker=marker,
                name=_row_name(row),
                close=_fmt(row.get("close")),
                chg=_fmt(row.get("change"), pct=True),
                mcap=_fmt(row.get("market_cap_basic")),
                pe=_fmt(pe),
                div=_fmt(row.get("dividends_yield_current")),
                rsi=_fmt(rsi),
                rec=_fmt(rec),
                w1=_fmt(row.get("Perf.1W") or row.get("perf_1w"), pct=True),
                m1=_fmt(row.get("Perf.1M") or row.get("perf_1m"), pct=True),
            )
        )

    if not matched_subject:
        lines.append("")
        lines.append(
            f"Note: {resolved} was not in the top-{page_size} sector peers by market cap; "
            "compare using sector medians implied by the table."
        )
    lines.append("")
    lines.append(
        f"Total peers reported by screener: {scan.get('totalCount', 'n/a')}"
    )
    return "\n".join(lines)
