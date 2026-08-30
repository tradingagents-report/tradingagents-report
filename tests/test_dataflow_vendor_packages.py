"""Regression coverage for the provider-oriented dataflows package layout."""

import importlib

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "tradingagents.dataflows.alpha_vantage.common",
        "tradingagents.dataflows.alpha_vantage.fundamentals",
        "tradingagents.dataflows.alpha_vantage.indicator",
        "tradingagents.dataflows.alpha_vantage.news",
        "tradingagents.dataflows.alpha_vantage.stock",
        "tradingagents.dataflows.tradingview.client",
        "tradingagents.dataflows.tradingview.fundamentals",
        "tradingagents.dataflows.tradingview.news",
        "tradingagents.dataflows.tradingview.stock",
        "tradingagents.dataflows.tradingview.symbols",
        "tradingagents.dataflows.yfinance.market",
        "tradingagents.dataflows.yfinance.news",
        "tradingagents.dataflows.market_routing",
        "tradingagents.dataflows.china.common",
        "tradingagents.dataflows.pandaai.market",
        "tradingagents.dataflows.akshare.market",
        "tradingagents.dataflows.akshare.fundamentals",
        "tradingagents.dataflows.akshare.news",
        "tradingagents.dataflows.tushare.market",
        "tradingagents.dataflows.tushare.fundamentals",
        "tradingagents.dataflows.tushare.news",
        "tradingagents.dataflows.baostock.market",
        "tradingagents.dataflows.baostock.fundamentals",
        "tradingagents.dataflows.finnhub.client",
        "tradingagents.dataflows.finnhub.fundamentals",
        "tradingagents.dataflows.finnhub.news",
        "tradingagents.dataflows.fred",
        "tradingagents.dataflows.polymarket",
        "tradingagents.dataflows.reddit",
        "tradingagents.dataflows.stocktwits",
    ],
)
def test_vendor_implementation_module_is_importable(module_name):
    assert importlib.import_module(module_name)
