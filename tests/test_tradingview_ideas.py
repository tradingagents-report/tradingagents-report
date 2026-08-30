"""TradingView ideas adapter tests."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from tradingagents.dataflows.errors import NoMarketDataError, VendorNotConfiguredError
from tradingagents.dataflows.tradingview.ideas import (
    fetch_tradingview_ideas,
    get_tradingview_ideas,
)


def epoch(date: str) -> int:
    return int(
        datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
    )


def test_ideas_formats_direction_mix_and_filters_future():
    client = Mock()
    client.get.return_value = [
        {
            "name": "Future short thesis",
            "description": "After the analysis date",
            "date_timestamp": epoch("2026-07-20"),
            "likes_count": 9,
            "comments_count": 1,
            "symbol": {"direction": 2},
            "user": {"username": "future_trader"},
        },
        {
            "name": "AAPL long setup",
            "description": "Breakout above resistance with volume confirmation.",
            "date_timestamp": epoch("2026-07-10"),
            "likes_count": 12,
            "comments_count": 3,
            "symbol": {"direction": 1},
            "user": {"username": "chart_pro"},
        },
        {
            "name": "Neutral range",
            "description": "Sideways",
            "date_timestamp": epoch("2026-07-09"),
            "likes_count": 2,
            "comments_count": 0,
            "direction": 0,
            "user": {"username": "range_king"},
        },
    ]

    output = get_tradingview_ideas("NASDAQ:AAPL", curr_date="2026-07-11", limit=10, client=client)

    assert "# TradingView Ideas for NASDAQ:AAPL" in output
    assert "Long=1, Short=0, Neutral/Other=1" in output
    assert "[Long] AAPL long setup" in output
    assert "[Neutral] Neutral range" in output
    assert "Future short thesis" not in output
    client.get.assert_called_once_with(
        "/api/ideas/list/NASDAQ%3AAAPL",
        params={"page": 1, "per_page": 10, "lang": "en"},
    )


def test_fetch_ideas_degrades_when_not_configured():
    client = Mock()
    client.get.side_effect = VendorNotConfiguredError("missing key")

    out = fetch_tradingview_ideas("AAPL", client=client)
    assert out.startswith("<tradingview ideas unavailable:")


def test_ideas_rejects_empty_list():
    client = Mock()
    client.get.return_value = []
    with pytest.raises(NoMarketDataError):
        get_tradingview_ideas("NASDAQ:AAPL", client=client)
