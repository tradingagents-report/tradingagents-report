"""TradingView symbol resolution tests."""

import pytest

from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.provider_models import parse_instrument
from tradingagents.dataflows.tradingview.symbols import resolve_tradingview_symbol


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("NASDAQ:AAPL", "NASDAQ:AAPL"),
        ("0005.HK", "HKEX:5"),
        ("0700.HK", "HKEX:700"),
        ("HKEX:5", "HKEX:5"),
        ("600519.SS", "SSE:600519"),
        ("300814.SZ", "SZSE:300814"),
        ("000001.SZ", "SZSE:000001"),
        ("BTC-USDT", "BINANCE:BTCUSDT"),
        ("EURUSD", "OANDA:EURUSD"),
        ("SPX500", "SP:SPX"),
        ("XAUUSD", "COMEX:GC1!"),
    ],
)
def test_deterministic_tradingview_symbols(raw, expected):
    assert resolve_tradingview_symbol(parse_instrument(raw)).symbol == expected


def test_search_prefers_primary_exact_listing():
    markets = [
        {"symbol": "AAPL", "type": "stock", "source_id": "PYTH", "full_name": "PYTH:AAPL"},
        {
            "symbol": "AAPL",
            "type": "stock",
            "source_id": "NASDAQ",
            "full_name": "NASDAQ:AAPL",
            "is_primary_listing": True,
        },
    ]

    resolved = resolve_tradingview_symbol(parse_instrument("AAPL"), search=lambda _: markets)

    assert resolved.symbol == "NASDAQ:AAPL"
    assert resolved.exchange == "NASDAQ"
    assert resolved.resolution_source == "search"


def test_search_prefers_china_exchanges_for_bare_six_digit_codes():
    markets = [
        {
            "symbol": "300814",
            "source_id": "LUXSE",
            "full_name": "LUXSE:300814",
            "is_primary_listing": True,
        },
        {
            "symbol": "300814",
            "source_id": "SZSE",
            "full_name": "SZSE:300814",
            "is_primary_listing": True,
        },
    ]

    resolved = resolve_tradingview_symbol(
        parse_instrument("300814"), search=lambda _: markets
    )

    assert resolved.symbol == "SZSE:300814"
    assert resolved.resolution_source == "search"


def test_search_ignores_non_exact_symbols():
    markets = [
        {"symbol": "AAPL.P", "source_id": "NASDAQ", "full_name": "NASDAQ:AAPL.P"},
        {"symbol": "AAPL", "source_id": "NYSE", "id": "NYSE:AAPL"},
    ]

    resolved = resolve_tradingview_symbol(parse_instrument("AAPL"), search=lambda _: markets)

    assert resolved.symbol == "NYSE:AAPL"


def test_unresolved_bare_equity_raises_no_market_data():
    with pytest.raises(NoMarketDataError, match="TradingView symbol could not be resolved") as exc:
        resolve_tradingview_symbol(parse_instrument("AAPL"), search=lambda _: [])

    assert exc.value.symbol == "AAPL"
