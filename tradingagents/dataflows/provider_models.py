"""Provider-neutral instrument and market-data contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, TypeVar


@dataclass(frozen=True)
class InstrumentRef:
    raw_symbol: str
    canonical_symbol: str
    asset_class: str
    exchange_hint: str | None = None
    currency_hint: str | None = None


@dataclass(frozen=True)
class ProviderSymbol:
    provider: str
    symbol: str
    exchange: str | None = None
    resolution_source: str = "deterministic"


T = TypeVar("T")


@dataclass(frozen=True)
class ProviderResult(Generic[T]):
    data: T
    provider: str
    requested: InstrumentRef
    resolved_symbol: str
    as_of: datetime | None = None
    delay: str | None = None
    adjustment_mode: str | None = None
    provenance: Mapping[str, Any] = field(default_factory=dict)
    quote_currency: str | None = None
    fundamental_currency: str | None = None


_FOREX_CURRENCIES = frozenset(
    {
        "USD",
        "EUR",
        "GBP",
        "JPY",
        "CHF",
        "CAD",
        "AUD",
        "NZD",
        "CNY",
        "CNH",
        "HKD",
        "SGD",
        "SEK",
        "NOK",
        "DKK",
        "PLN",
        "MXN",
        "ZAR",
        "TRY",
        "INR",
        "KRW",
        "BRL",
        "RUB",
        "THB",
    }
)

_CRYPTO_BASES = frozenset(
    {"BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LTC", "BCH", "DOT", "AVAX", "LINK"}
)
_CRYPTO_QUOTES = ("USDT", "USDC", "USD")

_INDEX_ALIASES = frozenset(
    {
        "SPX500",
        "US500",
        "SPX",
        "NAS100",
        "US100",
        "USTEC",
        "US30",
        "DJI30",
        "WS30",
        "GER40",
        "GER30",
        "DE40",
        "UK100",
        "JP225",
        "JPN225",
        "FRA40",
        "EU50",
        "HK50",
    }
)

_COMMODITY_ALIASES = frozenset(
    {
        "XAUUSD",
        "XAU",
        "GOLD",
        "XAGUSD",
        "XAG",
        "SILVER",
        "XPTUSD",
        "XPDUSD",
        "WTICOUSD",
        "USOIL",
        "WTI",
        "BCOUSD",
        "UKOIL",
        "BRENT",
        "NATGAS",
        "XNGUSD",
        "COPPER",
        "XCUUSD",
    }
)


def _is_crypto(symbol: str) -> bool:
    compact = symbol.replace("-", "")
    for quote in _CRYPTO_QUOTES:
        if compact.endswith(quote) and compact[: -len(quote)] in _CRYPTO_BASES:
            return True
    return False


def _is_forex(symbol: str) -> bool:
    return (
        len(symbol) == 6
        and symbol[:3] in _FOREX_CURRENCIES
        and symbol[3:] in _FOREX_CURRENCIES
    )


def parse_instrument(raw_symbol: str) -> InstrumentRef:
    """Parse broker/user input without introducing provider-specific syntax."""
    raw = raw_symbol.strip()
    canonical = raw.upper().rstrip("+")
    exchange_hint = None
    if ":" in canonical:
        exchange_hint, canonical = canonical.split(":", 1)

    if canonical in _COMMODITY_ALIASES:
        asset_class = "futures"
    elif canonical in _INDEX_ALIASES:
        asset_class = "index"
    elif _is_crypto(canonical):
        asset_class = "crypto"
    elif _is_forex(canonical):
        asset_class = "forex"
    else:
        asset_class = "equity"

    return InstrumentRef(
        raw_symbol=raw,
        canonical_symbol=canonical,
        asset_class=asset_class,
        exchange_hint=exchange_hint,
    )
