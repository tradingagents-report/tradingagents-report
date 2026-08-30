"""Exchange catalog loaded from package-local ``data/exchanges.json``.

Resolves TradingView exchange codes (``NASDAQ``, ``HKEX``, …) to catalog
metadata, primary ``asset_type``, and stock-screener ``market_code`` values
(``america``, ``hongkong``, …).

Override path with ``TRADINGAGENTS_EXCHANGES_JSON`` when needed for tests/ops.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

# ISO-ish country codes from exchanges.json → TradingView stock market_code.
# Countries without a stock screener market (eu/ng/tn/ve, …) are omitted.
_COUNTRY_TO_TV_MARKET: Mapping[str, str] = {
    "ae": "uae",
    "ar": "argentina",
    "at": "austria",
    "au": "australia",
    "bd": "bangladesh",
    "be": "belgium",
    "bh": "bahrain",
    "br": "brazil",
    "ca": "canada",
    "ch": "switzerland",
    "cl": "chile",
    "cn": "china",
    "co": "colombia",
    "cy": "cyprus",
    "cz": "czech",
    "de": "germany",
    "dk": "denmark",
    "ee": "estonia",
    "eg": "egypt",
    "es": "spain",
    "fi": "finland",
    "fr": "france",
    "gr": "greece",
    "hk": "hongkong",
    "hu": "hungary",
    "id": "indonesia",
    "ie": "ireland",
    "il": "israel",
    "in": "india",
    "is": "iceland",
    "it": "italy",
    "jp": "japan",
    "ke": "kenya",
    "kr": "korea",
    "kw": "kuwait",
    "lk": "srilanka",
    "lt": "lithuania",
    "lu": "luxembourg",
    "lv": "latvia",
    "ma": "morocco",
    "mx": "mexico",
    "my": "malaysia",
    "nl": "netherlands",
    "no": "norway",
    "nz": "newzealand",
    "pe": "peru",
    "ph": "philippines",
    "pk": "pakistan",
    "pl": "poland",
    "pt": "portugal",
    "qa": "qatar",
    "ro": "romania",
    "rs": "serbia",
    "ru": "russia",
    "sa": "saudiarabia",
    "se": "sweden",
    "sg": "singapore",
    "sk": "slovakia",
    "th": "thailand",
    "tr": "turkey",
    "tw": "taiwan",
    "uk": "uk",
    "us": "america",
    "vn": "vietnam",
    "za": "southafrica",
}


def _catalog_file() -> Path:
    env_path = os.getenv("TRADINGAGENTS_EXCHANGES_JSON")
    if env_path:
        return Path(env_path)
    return Path(__file__).resolve().parent / "data" / "exchanges.json"


@lru_cache(maxsize=1)
def _load_catalog() -> tuple[dict[str, dict[str, Any]], Path]:
    path = _catalog_file()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        exchanges = payload.get("exchanges")
        if not isinstance(exchanges, list):
            raise ValueError(f"{path}: missing exchanges list")
        by_value: dict[str, dict[str, Any]] = {}
        for entry in exchanges:
            if not isinstance(entry, Mapping):
                continue
            value = entry.get("value")
            if not isinstance(value, str) or not value.strip():
                continue
            key = value.strip().upper()
            existing = by_value.get(key)
            # Prefer non-hidden rows when duplicates exist.
            if existing is None or (existing.get("hidden") and not entry.get("hidden")):
                by_value[key] = dict(entry)
        if not by_value:
            raise ValueError(f"{path}: no usable exchanges")
        return by_value, path
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise FileNotFoundError(
            f"exchanges.json catalog not found at {path}; "
            "ship data/exchanges.json with tg-core or set TRADINGAGENTS_EXCHANGES_JSON"
        ) from error


def catalog_path() -> Path:
    """Return the exchanges.json path currently loaded."""
    return _load_catalog()[1]


def get_exchange_entry(exchange: str | None) -> dict[str, Any] | None:
    """Return one catalog row for an exchange code, or ``None``."""
    if not exchange or not str(exchange).strip():
        return None
    by_value, _ = _load_catalog()
    return by_value.get(str(exchange).strip().upper())


_GROUP_TO_ASSET_TYPE: Mapping[str, str] = {
    "cryptocurrency": "crypto",
    "forex": "forex",
    "economy": "economy",
}


def asset_type_for_exchange(exchange: str | None) -> str | None:
    """Return the catalog primary instrument class (``stock``, ``futures``, …)."""
    entry = get_exchange_entry(exchange)
    if entry is None:
        return None
    asset_type = entry.get("asset_type")
    if isinstance(asset_type, str) and asset_type.strip():
        return asset_type.strip().lower()
    group = str(entry.get("group") or "").strip().lower()
    return _GROUP_TO_ASSET_TYPE.get(group)


def country_for_exchange_code(exchange: str | None) -> str | None:
    """Return uppercase country/region code from the catalog (e.g. ``US``, ``HK``)."""
    entry = get_exchange_entry(exchange)
    if entry is None:
        return None
    country = entry.get("country")
    if isinstance(country, str) and country.strip():
        return country.strip().upper()
    group = str(entry.get("group") or "")
    if "crypto" in group.lower():
        return "CRYPTO"
    return None


def tv_market_for_country(country: str | None) -> str | None:
    """Map a catalog country code to a TradingView stock ``market_code``."""
    if not country or not str(country).strip():
        return None
    return _COUNTRY_TO_TV_MARKET.get(str(country).strip().lower())


def tv_market_for_exchange(exchange: str | None) -> str | None:
    """Map an exchange code to TradingView stock ``market_code`` via the catalog."""
    return tv_market_for_country(country_for_exchange_code(exchange))


def tv_market_for_symbol(symbol: str | None) -> str | None:
    """Infer TV market from ``EXCHANGE:TICKER`` (or bare exchange-qualified forms)."""
    if not symbol or not isinstance(symbol, str):
        return None
    text = symbol.strip()
    if not text:
        return None
    # Prefer listing helper for suffix forms (0700.HK → HKEX).
    try:
        from .listings import resolve_listing

        listing = resolve_listing(text)
        if listing.exchange:
            market = tv_market_for_exchange(listing.exchange)
            if market:
                return market
    except ValueError:
        pass

    if ":" in text:
        exchange = text.split(":", 1)[0].strip().upper()
        return tv_market_for_exchange(exchange)
    return None


def clear_exchange_catalog_cache() -> None:
    """Test helper to reload catalog after env/path changes."""
    _load_catalog.cache_clear()
