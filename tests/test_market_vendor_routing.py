from __future__ import annotations

import pytest

from tradingagents.dataflows.listings import resolve_listing


def test_parse_market_vendor_chain_preserves_priority():
    from tradingagents.dataflows.market_routing import parse_market_vendor_chain

    assert parse_market_vendor_chain("pandaai,akshare,tushare,baostock", "CN") == (
        "pandaai",
        "akshare",
        "tushare",
        "baostock",
    )


@pytest.mark.parametrize("raw", [None, "", "disabled", " DISABLED "])
def test_parse_market_vendor_chain_can_be_disabled(raw):
    from tradingagents.dataflows.market_routing import parse_market_vendor_chain

    assert parse_market_vendor_chain(raw, "US") is None


@pytest.mark.parametrize(
    "raw,market",
    [
        ("akshare,akshare", "CN"),
        ("disabled,akshare", "CN"),
        ("finnhub", "CN"),
        ("bogus", "US"),
    ],
)
def test_parse_market_vendor_chain_rejects_invalid_values(raw, market):
    from tradingagents.dataflows.market_routing import parse_market_vendor_chain

    with pytest.raises(ValueError):
        parse_market_vendor_chain(raw, market)


@pytest.mark.parametrize(
    "ticker,market",
    [
        ("600519.SS", "CN"),
        ("SZSE:000001", "CN"),
        ("NASDAQ:AAPL", "US"),
        ("AAPL", "US"),
        ("600519", None),
    ],
)
def test_market_for_listing(ticker, market):
    from tradingagents.dataflows.market_routing import market_for_listing

    assert market_for_listing(resolve_listing(ticker)) == market


def test_configured_market_chain_uses_resolved_market():
    from tradingagents.dataflows.market_routing import configured_market_chain

    config = {
        "cn_data_vendors": ("akshare", "tushare"),
        "us_data_vendors": ("yfinance", "finnhub"),
    }
    assert configured_market_chain(config, "600519.SS") == ("akshare", "tushare")
    assert configured_market_chain(config, "AAPL") == ("yfinance", "finnhub")
