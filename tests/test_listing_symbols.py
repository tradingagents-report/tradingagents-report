import pytest

from tradingagents.dataflows.listings import (
    country_for_exchange,
    is_china_a_share,
    listing_from_parts,
    resolve_listing,
)


@pytest.mark.parametrize(
    ("ticker", "exchange", "symbol", "display_ticker"),
    [
        ("0005.HK", "HKEX", "5", "0005.HK"),
        ("0700.HK", "HKEX", "700", "0700.HK"),
        ("600519.SS", "SSE", "600519", "600519.SS"),
        ("000001.SZ", "SZSE", "000001", "000001.SZ"),
        ("7203.T", "TSE", "7203", "7203.T"),
        ("2330.TW", "TWSE", "2330", "2330.TW"),
        ("6488.TWO", "TPEX", "6488", "6488.TWO"),
    ],
)
def test_resolve_listing_maps_market_qualified_tickers(
    ticker, exchange, symbol, display_ticker
):
    listing = resolve_listing(ticker)

    assert listing.exchange == exchange
    assert listing.symbol == symbol
    assert listing.display_ticker == display_ticker


def test_resolve_listing_accepts_explicit_exchange_symbol():
    listing = resolve_listing("hkex:5")

    assert listing.exchange == "HKEX"
    assert listing.symbol == "5"
    assert listing.display_ticker == "0005.HK"
    assert listing.provider_symbol == "HKEX:5"


def test_resolve_listing_normalizes_exchange_aliases():
    listing = resolve_listing("SHE:300750")

    assert listing.exchange == "SZSE"
    assert listing.symbol == "300750"
    assert listing.display_ticker == "300750.SZ"
    assert listing.provider_symbol == "SZSE:300750"


def test_listing_from_parts_validates_display_ticker_matches_listing():
    with pytest.raises(ValueError, match="does not match"):
        listing_from_parts("HKEX", "5", "0700.HK")


@pytest.mark.parametrize("ticker", ["../AAPL", "HKEX:5/../secret", "..."])
def test_resolve_listing_rejects_unsafe_ticker(ticker):
    with pytest.raises(ValueError):
        resolve_listing(ticker)


@pytest.mark.parametrize(
    ("exchange", "country"),
    [
        ("HKEX", "HK"),
        ("SSE", "CN"),
        ("SZSE", "CN"),
        ("TSE", "JP"),
        ("TWSE", "TW"),
        ("TPEX", "TW"),
        ("NASDAQ", "US"),
        ("NYSE", "US"),
        ("AMEX", "US"),
        ("SHE", "CN"),
        (None, None),
    ],
)
def test_country_for_exchange(exchange, country):
    assert country_for_exchange(exchange) == country


@pytest.mark.parametrize(
    "ticker",
    ["300814.SZ", "600519.SS", "SZSE:300814", "SSE:600519", "SHE:300750", "300814"],
)
def test_is_china_a_share_true(ticker):
    assert is_china_a_share(ticker) is True


@pytest.mark.parametrize("ticker", ["AAPL", "0700.HK", "7203.T", "NASDAQ:AAPL", ""])
def test_is_china_a_share_false(ticker):
    assert is_china_a_share(ticker) is False
