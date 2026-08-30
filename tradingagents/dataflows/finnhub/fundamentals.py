"""Finnhub company identity and metric summary."""

from __future__ import annotations

import json
from typing import Any

from ..errors import NoMarketDataError
from ..listings import resolve_listing
from .client import get_client, translate_error


def _symbol(symbol: str) -> str:
    return resolve_listing(symbol).symbol.upper()


def get_finnhub_identity(symbol: str, *, client: Any | None = None) -> dict[str, str]:
    ticker = _symbol(symbol)
    try:
        profile = (client or get_client()).company_profile2(symbol=ticker)
    except Exception as exc:
        raise translate_error(exc, "identity request") from exc
    if not profile:
        raise NoMarketDataError(symbol, ticker, "Finnhub returned no company profile")
    exchange_text = str(profile.get("exchange", "")).upper()
    exchange = next(
        (name for name in ("NASDAQ", "NYSE", "AMEX") if name in exchange_text),
        exchange_text,
    )
    return {
        "company_name": str(profile.get("name") or ticker),
        "exchange": exchange,
        "industry": str(profile.get("finnhubIndustry") or ""),
        "currency": str(profile.get("currency") or "USD"),
        "quote_type": "stock",
    }


def get_finnhub_fundamentals(
    symbol: str,
    curr_date: str | None = None,
    *,
    client: Any | None = None,
) -> str:
    ticker = _symbol(symbol)
    api = client or get_client()
    try:
        profile = api.company_profile2(symbol=ticker)
        metrics = api.company_basic_financials(ticker, "all")
    except Exception as exc:
        raise translate_error(exc, "fundamentals request") from exc
    if not profile and not metrics:
        raise NoMarketDataError(symbol, ticker, "Finnhub returned no fundamentals")
    payload = {"profile": profile or {}, "metrics": (metrics or {}).get("metric", {})}
    return f"# Finnhub fundamentals for {ticker}\n\n" + json.dumps(payload, ensure_ascii=False)
