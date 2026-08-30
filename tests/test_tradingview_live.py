"""Opt-in contract smoke tests against the live TradingView Data API."""

import os
from datetime import date, timedelta

import pytest

from tradingagents.dataflows.tradingview.stock import fetch_tradingview_ohlcv


@pytest.mark.integration
@pytest.mark.skipif(
    not (
        os.getenv("TRADINGVIEW_API_KEY")
        or os.getenv("TRADINGVIEW_RAPIDAPI_KEY")
        or os.getenv("RAPIDAPI_KEY")
    ),
    reason="TradingView API key is not configured",
)
def test_live_aapl_daily_japanese_ohlcv():
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=10)).isoformat()

    result = fetch_tradingview_ohlcv("NASDAQ:AAPL", start, end)

    assert not result.data.empty
    assert result.resolved_symbol == "NASDAQ:AAPL"
    assert result.adjustment_mode == "Japanese"
