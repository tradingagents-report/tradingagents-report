from __future__ import annotations

from unittest import mock

import pytest

import tradingagents.dataflows.interface as interface
from tradingagents.dataflows.config import set_config

EXPECTED = {
    "pandaai": {"get_stock_data", "get_ohlcv"},
    "akshare": {
        "get_instrument_identity",
        "get_stock_data",
        "get_ohlcv",
        "get_indicators",
        "get_fundamentals",
        "get_balance_sheet",
        "get_cashflow",
        "get_income_statement",
        "get_news",
    },
    "tushare": {
        "get_instrument_identity",
        "get_stock_data",
        "get_ohlcv",
        "get_indicators",
        "get_fundamentals",
        "get_balance_sheet",
        "get_cashflow",
        "get_income_statement",
        "get_news",
        "get_global_news",
    },
    "baostock": {
        "get_instrument_identity",
        "get_stock_data",
        "get_ohlcv",
        "get_indicators",
        "get_fundamentals",
    },
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


def test_cn_market_chain_filters_unsupported_vendor_and_preserves_order():
    set_config(
        {
            "cn_data_vendors": ("pandaai", "akshare", "tushare"),
            "data_vendors": {"news_data": "default"},
            "tool_vendors": {},
        }
    )
    panda = mock.Mock(side_effect=AssertionError("PandaAI has no news capability"))
    akshare = mock.Mock(return_value="AK NEWS")
    tushare = mock.Mock(return_value="TS NEWS")
    with mock.patch.dict(
        interface.VENDOR_METHODS,
        {"get_news": {"akshare": akshare, "tushare": tushare}},
        clear=False,
    ):
        result = interface.route_to_vendor("get_news", "600519.SS", "2026-01-01", "2026-01-15")
    assert result == "AK NEWS"
    panda.assert_not_called()
    akshare.assert_called_once()
    tushare.assert_not_called()


def test_explicit_category_chain_overrides_market_chain():
    set_config(
        {
            "cn_data_vendors": ("akshare", "tushare"),
            "data_vendors": {"core_stock_apis": "yfinance"},
        }
    )
    akshare = mock.Mock(side_effect=AssertionError("outside explicit chain"))
    with mock.patch.dict(
        interface.VENDOR_METHODS,
        {"get_stock_data": {"yfinance": lambda *args: "YF", "akshare": akshare}},
        clear=False,
    ):
        result = interface.route_to_vendor(
            "get_stock_data", "600519.SS", "2026-01-01", "2026-01-15"
        )
    assert result == "YF"
    akshare.assert_not_called()


def test_market_chain_never_falls_through_to_unlisted_vendor():
    set_config(
        {
            "cn_data_vendors": ("akshare",),
            "data_vendors": {"core_stock_apis": "default"},
            "tool_vendors": {},
        }
    )
    tushare = mock.Mock(side_effect=AssertionError("outside configured market chain"))
    with mock.patch.dict(
        interface.VENDOR_METHODS,
        {
            "get_stock_data": {
                "akshare": lambda *args: "",
                "tushare": tushare,
            }
        },
        clear=False,
    ):
        result = interface.route_to_vendor(
            "get_stock_data", "600519.SS", "2026-01-01", "2026-01-15"
        )
    assert "NO_DATA_AVAILABLE" in result
    tushare.assert_not_called()
