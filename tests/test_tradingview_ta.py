"""TradingView TA summary and indicator adapter tests."""

from unittest.mock import Mock

import pytest

from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.tradingview.ta import (
    get_tradingview_ta_indicators,
    get_tradingview_ta_summary,
)


def test_ta_summary_formats_timeframes_and_endpoint():
    client = Mock()
    client.get.return_value = {
        "1D": {"All": 0.8, "MA": 1.0, "Other": 0.4},
        "1W": {"All": -0.2, "MA": -0.5, "Other": 0.0},
    }

    output = get_tradingview_ta_summary("NASDAQ:AAPL", "2026-07-11", client=client)

    assert "# TradingView TA Summary for NASDAQ:AAPL" in output
    assert "| 1D | 0.800 (Strong Buy)" in output
    assert "| 1W | -0.200 (Sell)" in output
    client.get.assert_called_once_with("/api/ta/NASDAQ%3AAAPL")


def test_ta_summary_rejects_empty_payload():
    client = Mock()
    client.get.return_value = {}

    with pytest.raises(NoMarketDataError, match="no TA summary"):
        get_tradingview_ta_summary("NASDAQ:AAPL", client=client)


def test_ta_indicators_groups_curated_fields():
    client = Mock()
    client.get.return_value = {
        "RSI": 55.5,
        "Stoch.K": 12.0,
        "Stoch.K[1]": 18.0,
        "CCI20": -120.0,
        "CCI20[1]": -80.0,
        "Mom": -5.0,
        "Mom[1]": -2.0,
        "AO": -1.5,
        "AO[1]": -0.5,
        "AO[2]": 0.2,
        "MACD.macd": 1.2,
        "MACD.signal": 0.9,
        "ADX": 22.0,
        "ADX+DI": 18.0,
        "ADX+DI[1]": 20.0,
        "ADX-DI": 25.0,
        "ADX-DI[1]": 22.0,
        "Pivot.M.Classic.Middle": 100.0,
        "Recommend.All": 0.3,
        "Recommend.MA": -0.8,
        "Recommend.Other": 0.0,
        "Pivot.M.Fibonacci.R1": 110.0,  # not in curated classic set
    }

    output = get_tradingview_ta_indicators("NASDAQ:AAPL", "2026-07-11", client=client)

    assert "# TradingView TA Indicators for NASDAQ:AAPL" in output
    assert "prior bars" in output
    assert "Recommend.MA vs Recommend.Other" in output
    assert "## Momentum" in output
    assert "RSI: 55.5" in output
    assert "Stoch.K[1]: 18" in output
    assert "CCI20[1]: -80" in output
    assert "AO[2]: 0.2" in output
    assert "## Trend" in output
    assert "MACD.macd: 1.2" in output
    assert "ADX-DI[1]: 22" in output
    assert "## Classic Pivots" in output
    assert "Pivot.M.Classic.Middle: 100" in output
    assert "Recommend.All: 0.3" in output
    assert "Recommend.MA: -0.8" in output
    assert "Pivot.M.Fibonacci.R1" not in output
    client.get.assert_called_once_with("/api/ta/NASDAQ%3AAAPL/indicators")
