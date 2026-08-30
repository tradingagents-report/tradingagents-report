"""Symbol resolution must remain owned by each provider-facing data path.

Regression tests for provider-neutral instrument identity and return paths,
plus the remaining Yahoo-specific news path.
"""
import pandas as pd

import tradingagents.agents.utils.agent_utils as au
import tradingagents.dataflows.yfinance.news as ynews
import tradingagents.graph.trading_graph as tg
from tradingagents.graph.trading_graph import TradingAgentsGraph


def test_identity_lookup_delegates_raw_symbol_to_structured_facade(monkeypatch):
    seen = {}

    def fake_identity(symbol):
        seen["symbol"] = symbol
        return {"company_name": "Gold Futures", "quote_type": "FUTURE"}

    monkeypatch.setattr(au, "get_instrument_identity", fake_identity)
    au.resolve_instrument_identity.cache_clear()

    identity = au.resolve_instrument_identity("XAUUSD")

    assert seen["symbol"] == "XAUUSD"  # provider-neutral facade owns symbol resolution
    assert identity.get("company_name") == "Gold Futures"


def test_fetch_returns_delegates_raw_symbols_to_structured_facade(monkeypatch):
    queried = []

    def fake_ohlcv(symbol, start_date, end_date):
        queried.append(symbol)
        return pd.DataFrame(
            {
                "Date": pd.date_range("2025-01-02", periods=7, freq="D"),
                "Close": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0],
            }
        )

    monkeypatch.setattr(tg, "get_ohlcv", fake_ohlcv)

    # _fetch_returns does not use ``self``; call unbound to avoid building the graph.
    raw, alpha, days = TradingAgentsGraph._fetch_returns(
        None, "XAUUSD", "2025-01-02", holding_days=5, benchmark="SPY"
    )

    assert queried == ["XAUUSD", "SPY"]
    assert raw is not None and days is not None


def test_news_lookup_normalizes_symbol(monkeypatch):
    seen = {}

    class FakeTicker:
        def __init__(self, symbol):
            seen["symbol"] = symbol

        def get_news(self, count):
            return []

    monkeypatch.setattr(ynews.yf, "Ticker", FakeTicker)
    monkeypatch.setattr(ynews, "yf_retry", lambda fn: fn())

    out = ynews.get_news_yfinance("XAUUSD", "2025-01-01", "2025-01-10")

    assert seen["symbol"] == "GC=F"   # news queried with the canonical symbol
    assert "XAUUSD" in out            # the user's ticker stays in the report
    assert "GC=F" in out              # provenance noted
