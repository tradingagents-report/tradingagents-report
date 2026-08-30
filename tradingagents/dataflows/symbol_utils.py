"""Ticker helpers shared across vendors."""

from __future__ import annotations

_CRYPTO_BASES = frozenset(
    {"BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LTC", "BCH", "DOT", "AVAX", "LINK"}
)
_CRYPTO_QUOTES = ("USDT", "USDC", "USD")


def crypto_base(raw: str) -> str | None:
    """Return the base asset for known USD, USDT, or USDC crypto quotes.

    Does not convert vendor symbols. It only recognizes forms such as
    ``BTC-USD``, ``BTCUSD``, and ``BTC-USDT`` for social feeds and Yahoo
    normalization.
    """
    if not isinstance(raw, str):
        return None
    compact = raw.strip().upper().rstrip("+").replace("-", "")
    for quote in _CRYPTO_QUOTES:
        if compact.endswith(quote):
            base = compact[: -len(quote)]
            return base if base in _CRYPTO_BASES else None
    return None
