from __future__ import annotations

import pandas as pd
import pytest


def test_resolve_cn_symbol_requires_supported_exchange():
    from tradingagents.dataflows.china.common import resolve_cn_symbol

    requested, exchange, code = resolve_cn_symbol("SSE:600519")
    assert requested.canonical_symbol == "600519"
    assert exchange == "SSE"
    assert code == "600519"

    requested, exchange, code = resolve_cn_symbol("000001.SZ")
    assert (exchange, code) == ("SZSE", "000001")

    with pytest.raises(ValueError, match="exchange-qualified"):
        resolve_cn_symbol("600519")


def test_normalize_ohlcv_maps_chinese_columns_and_filters_window():
    from tradingagents.dataflows.china.common import normalize_ohlcv

    raw = pd.DataFrame(
        {
            "日期": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "开盘": [1, 2, 3],
            "最高": [2, 3, 4],
            "最低": [0, 1, 2],
            "收盘": [1.5, 2.5, 3.5],
            "成交量": [10, 20, 30],
            "成交额": [100, 200, 300],
        }
    )
    result = normalize_ohlcv(
        raw,
        provider="akshare",
        requested_symbol="600519.SS",
        resolved_symbol="600519",
        start_date="2026-01-02",
        end_date="2026-01-02",
        adjustment_mode="qfq",
    )
    assert list(result.data.columns) == ["Date", "Open", "High", "Low", "Close", "Volume", "Amount"]
    assert result.data["Close"].tolist() == [2.5]
    assert result.provider == "akshare"
    assert result.quote_currency == "CNY"
    assert result.adjustment_mode == "qfq"


def test_normalize_ohlcv_rejects_missing_or_empty_data():
    from tradingagents.dataflows.china.common import normalize_ohlcv
    from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError

    kwargs = {
        "provider": "akshare",
        "requested_symbol": "600519.SS",
        "resolved_symbol": "600519",
        "start_date": "2026-01-01",
        "end_date": "2026-01-02",
    }
    with pytest.raises(NoMarketDataError):
        normalize_ohlcv(pd.DataFrame(), **kwargs)
    with pytest.raises(VendorUnavailableError):
        normalize_ohlcv(pd.DataFrame({"Date": ["2026-01-01"]}), **kwargs)


def test_format_stock_data_uses_normalized_result():
    from tradingagents.dataflows.china.common import format_stock_data, normalize_ohlcv

    raw = pd.DataFrame(
        {
            "Date": ["2026-01-02"],
            "Open": [1],
            "High": [2],
            "Low": [0.5],
            "Close": [1.5],
            "Volume": [10],
        }
    )
    result = normalize_ohlcv(
        raw,
        provider="tushare",
        requested_symbol="600519.SS",
        resolved_symbol="600519.SH",
        start_date="2026-01-01",
        end_date="2026-01-02",
    )
    text = format_stock_data(result, "2026-01-01", "2026-01-02")
    assert "tushare" in text
    assert "600519.SH" in text
    assert "2026-01-02" in text


def test_stock_text_from_fetch_uses_existing_text_contract():
    from tradingagents.dataflows.china.common import (
        normalize_ohlcv,
        stock_text_from_fetch,
    )

    calls = []

    def fetch(symbol, start_date, end_date):
        calls.append((symbol, start_date, end_date))
        return normalize_ohlcv(
            pd.DataFrame(
                {
                    "Date": ["2026-01-02"],
                    "Open": [1],
                    "High": [2],
                    "Low": [0.5],
                    "Close": [1.5],
                    "Volume": [10],
                }
            ),
            provider="akshare",
            requested_symbol=symbol,
            resolved_symbol="600519",
            start_date=start_date,
            end_date=end_date,
        )

    output = stock_text_from_fetch(fetch, "600519.SS", "2026-01-01", "2026-01-03")

    assert calls == [("600519.SS", "2026-01-01", "2026-01-03")]
    assert "Provider: akshare" in output


def test_indicators_from_fetch_adds_warmup_and_delegates(monkeypatch):
    import tradingagents.dataflows.china.common as common

    calls = []
    raw = pd.DataFrame(
        {
            "Date": ["2026-01-02"],
            "Open": [1],
            "High": [2],
            "Low": [0.5],
            "Close": [1.5],
            "Volume": [10],
        }
    )

    def fetch(symbol, start_date, end_date):
        calls.append((symbol, start_date, end_date))
        return common.normalize_ohlcv(
            raw,
            provider="akshare",
            requested_symbol=symbol,
            resolved_symbol="600519",
            start_date=start_date,
            end_date=end_date,
        )

    delegated = []

    def calculate(data, symbol, indicator, curr_date, look_back_days):
        delegated.append((data, symbol, indicator, curr_date, look_back_days))
        return "INDICATOR"

    monkeypatch.setattr(common, "calculate_indicator_window", calculate)
    output = common.indicators_from_fetch(fetch, "600519.SS", "rsi", "2026-01-02", 5)

    assert calls == [("600519.SS", "2025-04-22", "2026-01-02")]
    assert delegated[0][1:] == ("600519.SS", "rsi", "2026-01-02", 5)
    assert output == "INDICATOR"
