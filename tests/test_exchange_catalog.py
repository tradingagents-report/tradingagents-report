"""Tests for the package-local exchanges.json catalog loader."""

from tradingagents.dataflows.exchange_catalog import (
    asset_type_for_exchange,
    catalog_path,
    country_for_exchange_code,
    get_exchange_entry,
    tv_market_for_exchange,
    tv_market_for_symbol,
)
from tradingagents.dataflows.listings import country_for_exchange


def test_catalog_loads_and_resolves_major_exchanges():
    path = catalog_path()
    assert path.name == "exchanges.json"
    assert get_exchange_entry("NASDAQ") is not None
    assert get_exchange_entry("HKEX")["country"].lower() == "hk"
    assert get_exchange_entry("XETR")["country"].lower() == "de"


def test_tv_market_mapping_from_catalog_country():
    assert tv_market_for_exchange("NASDAQ") == "america"
    assert tv_market_for_exchange("HKEX") == "hongkong"
    assert tv_market_for_exchange("SSE") == "china"
    assert tv_market_for_exchange("SZSE") == "china"
    assert tv_market_for_exchange("TSE") == "japan"
    assert tv_market_for_exchange("LSE") == "uk"
    assert tv_market_for_exchange("XETR") == "germany"
    assert tv_market_for_exchange("ASX") == "australia"
    assert tv_market_for_exchange("TWSE") == "taiwan"


def test_tv_market_for_symbol_supports_suffix_and_explicit():
    assert tv_market_for_symbol("NASDAQ:AAPL") == "america"
    assert tv_market_for_symbol("0700.HK") == "hongkong"
    assert tv_market_for_symbol("600519.SS") == "china"
    assert tv_market_for_symbol("7203.T") == "japan"


def test_listings_country_prefers_catalog():
    assert country_for_exchange("XETR") == "DE"
    assert country_for_exchange_code("ASX") == "AU"
    assert country_for_exchange("NASDAQ") == "US"


def test_catalog_asset_type_labels_primary_instrument_class():
    assert asset_type_for_exchange("NASDAQ") == "stock"
    assert asset_type_for_exchange("HKEX") == "stock"
    assert asset_type_for_exchange("CME") == "futures"
    assert asset_type_for_exchange("SHFE") == "futures"
    assert asset_type_for_exchange("DJ") == "index"
    assert asset_type_for_exchange("CBOE") == "options"
    assert asset_type_for_exchange("GATE") == "crypto"
    assert get_exchange_entry("NASDAQ")["asset_type"] == "stock"
