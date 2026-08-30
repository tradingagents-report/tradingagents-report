from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest


class FakePanda:
    def __init__(self):
        self.calls = []

    def init_token(self, **kwargs):
        self.calls.append(("init_token", kwargs))

    def get_market_data(self, **kwargs):
        self.calls.append(("get_market_data", kwargs))
        return pd.DataFrame(
            {
                "date": ["20260102"],
                "open": [1],
                "high": [2],
                "low": [0.5],
                "close": [1.5],
                "volume": [10],
            }
        )

    def get_us_daily(self, **kwargs):
        self.calls.append(("get_us_daily", kwargs))
        return pd.DataFrame(
            {
                "date": ["20260102"],
                "open": [10],
                "high": [12],
                "low": [9],
                "close": [11],
                "volume": [100],
            }
        )


def test_pandaai_routes_cn_and_us_sdk_calls(monkeypatch):
    from tradingagents.dataflows.pandaai.market import fetch_pandaai_ohlcv

    monkeypatch.setenv("PANDAAI_USERNAME", "user")
    monkeypatch.setenv("PANDAAI_PASSWORD", "secret")
    fake = FakePanda()
    cn = fetch_pandaai_ohlcv("600519.SS", "2026-01-01", "2026-01-03", sdk=fake)
    us = fetch_pandaai_ohlcv("NASDAQ:AAPL", "2026-01-01", "2026-01-03", sdk=fake)

    assert [name for name, _ in fake.calls].count("init_token") == 2
    assert any(name == "get_market_data" for name, _ in fake.calls)
    assert any(name == "get_us_daily" for name, _ in fake.calls)
    assert cn.quote_currency == "CNY"
    assert us.quote_currency == "USD"


def test_pandaai_requires_credentials(monkeypatch):
    from tradingagents.dataflows.errors import VendorNotConfiguredError
    from tradingagents.dataflows.pandaai.market import fetch_pandaai_ohlcv

    monkeypatch.delenv("PANDAAI_USERNAME", raising=False)
    monkeypatch.delenv("PANDAAI_PASSWORD", raising=False)
    with pytest.raises(VendorNotConfiguredError):
        fetch_pandaai_ohlcv("600519.SS", "2026-01-01", "2026-01-03", sdk=FakePanda())


def test_akshare_calls_a_share_history_endpoint():
    from tradingagents.dataflows.akshare.market import fetch_akshare_ohlcv

    class FakeAk:
        def stock_zh_a_hist(self, **kwargs):
            assert kwargs == {
                "symbol": "600519",
                "period": "daily",
                "start_date": "20260101",
                "end_date": "20260103",
                "adjust": "qfq",
            }
            return pd.DataFrame(
                {
                    "日期": ["2026-01-02"],
                    "开盘": [1],
                    "最高": [2],
                    "最低": [0.5],
                    "收盘": [1.5],
                    "成交量": [10],
                }
            )

    result = fetch_akshare_ohlcv("600519.SS", "2026-01-01", "2026-01-03", sdk=FakeAk())
    assert result.provider == "akshare"
    assert result.resolved_symbol == "600519"


def test_tushare_calls_pro_bar_with_ts_code(monkeypatch):
    from tradingagents.dataflows.tushare.market import fetch_tushare_ohlcv

    monkeypatch.setenv("TUSHARE_TOKEN", "token")

    class FakeTs:
        def set_token(self, token):
            assert token == "token"

        def pro_bar(self, **kwargs):
            assert kwargs["ts_code"] == "000001.SZ"
            assert kwargs["adj"] == "qfq"
            return pd.DataFrame(
                {
                    "trade_date": ["20260102"],
                    "open": [1],
                    "high": [2],
                    "low": [0.5],
                    "close": [1.5],
                    "vol": [10],
                    "amount": [100],
                }
            )

    result = fetch_tushare_ohlcv("000001.SZ", "2026-01-01", "2026-01-03", sdk=FakeTs())
    assert result.resolved_symbol == "000001.SZ"


def test_baostock_logs_in_queries_and_logs_out():
    from tradingagents.dataflows.baostock.market import fetch_baostock_ohlcv

    events = []

    class Cursor:
        error_code = "0"
        error_msg = ""
        fields = ["date", "open", "high", "low", "close", "volume", "amount"]

        def __init__(self):
            self.done = False

        def next(self):
            if self.done:
                return False
            self.done = True
            return True

        def get_row_data(self):
            return ["2026-01-02", "1", "2", "0.5", "1.5", "10", "100"]

    class FakeBao:
        def login(self):
            events.append("login")
            return SimpleNamespace(error_code="0", error_msg="")

        def logout(self):
            events.append("logout")

        def query_history_k_data_plus(self, **kwargs):
            events.append(kwargs["code"])
            return Cursor()

    result = fetch_baostock_ohlcv("600519.SS", "2026-01-01", "2026-01-03", sdk=FakeBao())
    assert events == ["login", "sh.600519", "logout"]
    assert result.provider == "baostock"
