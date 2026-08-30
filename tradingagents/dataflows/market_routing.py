"""Market-aware vendor-chain parsing without provider-specific requests."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .listings import ListingRef, country_for_exchange, resolve_listing

CN_VENDORS = frozenset({"pandaai", "akshare", "tushare", "baostock"})
US_VENDORS = frozenset({"pandaai", "tradingview", "yfinance", "alpha_vantage", "finnhub"})
MARKET_VENDORS = {"CN": CN_VENDORS, "US": US_VENDORS}


def parse_market_vendor_chain(
    raw: str | None,
    market: str,
) -> tuple[str, ...] | None:
    """Parse one exact, ordered market chain or return ``None`` when disabled."""
    normalized_market = str(market).strip().upper()
    if normalized_market not in MARKET_VENDORS:
        raise ValueError(f"unsupported market {market!r}; expected CN or US")
    value = str(raw or "").strip().lower()
    if not value or value == "disabled":
        return None
    vendors = tuple(part.strip() for part in value.split(",") if part.strip())
    if "disabled" in vendors:
        raise ValueError("disabled cannot be combined with market vendors")
    if len(set(vendors)) != len(vendors):
        raise ValueError(f"duplicate vendor in {normalized_market} chain: {vendors}")
    invalid = [vendor for vendor in vendors if vendor not in MARKET_VENDORS[normalized_market]]
    if invalid:
        raise ValueError(
            f"invalid {normalized_market} vendor(s) {invalid}; "
            f"allowed: {sorted(MARKET_VENDORS[normalized_market])}"
        )
    return vendors


def market_for_listing(listing: ListingRef) -> str | None:
    """Return CN/US for a normalized listing without guessing numeric tickers."""
    country = country_for_exchange(listing.exchange)
    if country in MARKET_VENDORS:
        return country
    if listing.exchange is None and listing.symbol.isalpha():
        return "US"
    return None


def configured_market_chain(
    config: Mapping[str, Any],
    symbol: str,
) -> tuple[str, ...] | None:
    """Read the configured chain for ``symbol`` after provider-neutral resolution."""
    market = market_for_listing(resolve_listing(symbol))
    if market is None:
        return None
    value = config.get(f"{market.lower()}_data_vendors")
    if value is None or isinstance(value, tuple):
        return value
    return parse_market_vendor_chain(str(value), market)
