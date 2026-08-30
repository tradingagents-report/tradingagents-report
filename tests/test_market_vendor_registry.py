from __future__ import annotations

from unittest import mock

import pytest

import tradingagents.dataflows.interface as interface
from tradingagents.dataflows.config import set_config

EXPECTED = {
    "finnhub": {
        "get_instrument_identity",
        "get_fundamentals",
        "get_news",
        "get_global_news",
        "get_insider_transactions",
    },
}


@pytest.mark.parametrize("vendor,methods", EXPECTED.items())
def test_declared_vendor_capabilities_are_registered(vendor, methods):
    registered = {
        method for method, vendors in interface.VENDOR_METHODS.items() if vendor in vendors
    }
    assert registered == methods


def test_us_market_chain_filters_unsupported_vendor_and_preserves_order():
    set_config(
        {
            "us_data_vendors": ("yfinance", "finnhub"),
            "data_vendors": {"news_data": "default"},
            "tool_vendors": {},
        }
    )
    yfinance = mock.Mock(side_effect=AssertionError("yfinance is not registered here"))
    finnhub = mock.Mock(return_value="FH NEWS")
    with mock.patch.dict(
        interface.VENDOR_METHODS,
        {"get_news": {"finnhub": finnhub}},
        clear=False,
    ):
        result = interface.route_to_vendor("get_news", "AAPL", "2026-01-01", "2026-01-15")
    assert result == "FH NEWS"
    yfinance.assert_not_called()
    finnhub.assert_called_once()


def test_explicit_category_chain_overrides_market_chain():
    set_config(
        {
            "us_data_vendors": ("finnhub",),
            "data_vendors": {"core_stock_apis": "yfinance"},
        }
    )
    finnhub = mock.Mock(side_effect=AssertionError("outside explicit chain"))
    with mock.patch.dict(
        interface.VENDOR_METHODS,
        {"get_stock_data": {"yfinance": lambda *args: "YF", "finnhub": finnhub}},
        clear=False,
    ):
        result = interface.route_to_vendor(
            "get_stock_data", "AAPL", "2026-01-01", "2026-01-15"
        )
    assert result == "YF"
    finnhub.assert_not_called()


def test_market_chain_never_falls_through_to_unlisted_vendor():
    set_config(
        {
            "us_data_vendors": ("finnhub",),
            "data_vendors": {"news_data": "default"},
            "tool_vendors": {},
        }
    )
    yfinance = mock.Mock(side_effect=AssertionError("outside configured market chain"))
    with mock.patch.dict(
        interface.VENDOR_METHODS,
        {
            "get_news": {
                "finnhub": lambda *args: "",
                "yfinance": yfinance,
            }
        },
        clear=False,
    ):
        result = interface.route_to_vendor(
            "get_news", "AAPL", "2026-01-01", "2026-01-15"
        )
    assert "NO_DATA_AVAILABLE" in result
    yfinance.assert_not_called()
