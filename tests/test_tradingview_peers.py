"""TradingView peer-comparison screener adapter tests."""

from unittest.mock import Mock

import pytest

from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.tradingview.peers import get_tradingview_peer_comparison


def test_peer_comparison_uses_sector_screener_and_marks_subject():
    client = Mock()
    client.get.return_value = {
        "sector": "Electronic Technology",
        "description": "Apple Inc.",
    }
    client.post.return_value = {
        "totalCount": 2,
        "data": [
            {
                "symbol": "NASDAQ:AAPL",
                "ticker_view": {"name": "AAPL", "description": "Apple Inc."},
                "close": 200.0,
                "change": 1.5,
                "market_cap_basic": 3e12,
                "price_earnings_ttm": 30.0,
                "dividends_yield_current": 0.4,
                "rsi": 55.0,
                "recommend_all": 0.2,
                "Perf.1W": 2.0,
                "Perf.1M": 5.0,
            },
            {
                "symbol": "NASDAQ:NVDA",
                "ticker_view": {"name": "NVDA"},
                "close": 100.0,
                "change": -1.0,
                "market_cap_basic": 2e12,
                "price_earnings_ttm": 40.0,
                "rsi": 45.0,
                "recommend_all": -0.1,
                "Perf.1W": -2.0,
                "Perf.1M": 1.0,
            },
        ],
    }

    output = get_tradingview_peer_comparison(
        "NASDAQ:AAPL", "2026-07-11", limit=10, client=client
    )

    assert "# Peer Comparison for NASDAQ:AAPL" in output
    assert "Sector: Electronic Technology" in output
    assert "Market: america" in output
    assert "NASDAQ:AAPL ←" in output
    assert "NASDAQ:NVDA" in output
    client.get.assert_called_once_with("/api/market-data/NASDAQ%3AAAPL/company")
    client.post.assert_called_once()
    path, kwargs = client.post.call_args
    assert path[0] == "/api/screener/scan"
    body = kwargs["body"]
    assert body["market"] == "america"
    assert body["filters"] == {"sector": ["Electronic Technology"]}


def test_peer_comparison_requires_sector():
    client = Mock()
    client.get.return_value = {"description": "No sector here"}
    with pytest.raises(NoMarketDataError, match="sector unavailable"):
        get_tradingview_peer_comparison("NASDAQ:AAPL", client=client)


def test_peer_comparison_infers_hongkong_market_from_catalog():
    client = Mock()
    client.get.return_value = {"sector": "Consumer Non-Durables"}
    client.post.return_value = {"totalCount": 1, "data": [{"symbol": "HKEX:700", "close": 300}]}

    output = get_tradingview_peer_comparison("HKEX:700", "2026-07-11", limit=5, client=client)

    assert "Market: hongkong" in output
    assert client.post.call_args.kwargs["body"]["market"] == "hongkong"
