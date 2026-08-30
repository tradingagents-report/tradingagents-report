from __future__ import annotations

from datetime import datetime, timezone

import pytest


class FakeFinnhub:
    def company_profile2(self, symbol):
        return {
            "name": "Apple Inc.",
            "exchange": "NASDAQ NMS - GLOBAL MARKET",
            "currency": "USD",
            "finnhubIndustry": "Technology",
        }

    def company_basic_financials(self, symbol, metric):
        return {"metric": {"peTTM": 30.5, "pbQuarterly": 12.0}}

    def company_news(self, symbol, _from, to):
        return [
            {"datetime": _epoch("2026-01-02"), "headline": "inside", "summary": "ok"},
            {"datetime": _epoch("2026-02-01"), "headline": "future", "summary": "no"},
        ]

    def general_news(self, category, min_id=0):
        return [
            {"datetime": _epoch("2026-01-02"), "headline": "inside global"},
            {"datetime": _epoch("2026-02-01"), "headline": "future global"},
        ]

    def stock_insider_transactions(self, symbol, _from, to):
        return {
            "data": [
                {"transactionDate": "2026-01-02", "name": "inside"},
                {"transactionDate": "2026-02-01", "name": "future"},
            ]
        }


def _epoch(value):
    return int(datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def test_finnhub_requires_api_key_without_injected_client(monkeypatch):
    from tradingagents.dataflows.errors import VendorNotConfiguredError
    from tradingagents.dataflows.finnhub.client import get_client

    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    with pytest.raises(VendorNotConfiguredError):
        get_client()


def test_finnhub_identity_and_fundamentals():
    from tradingagents.dataflows.finnhub.fundamentals import (
        get_finnhub_fundamentals,
        get_finnhub_identity,
    )

    client = FakeFinnhub()
    identity = get_finnhub_identity("NASDAQ:AAPL", client=client)
    assert identity["company_name"] == "Apple Inc."
    assert identity["exchange"] == "NASDAQ"
    text = get_finnhub_fundamentals("AAPL", "2026-01-15", client=client)
    assert "30.5" in text
    assert "Technology" in text


def test_finnhub_news_and_insiders_exclude_future_rows():
    from tradingagents.dataflows.finnhub.news import (
        get_finnhub_global_news,
        get_finnhub_insider_transactions,
        get_finnhub_news,
    )

    client = FakeFinnhub()
    company = get_finnhub_news("AAPL", "2026-01-01", "2026-01-15", client=client)
    global_news = get_finnhub_global_news("2026-01-15", 14, 50, client=client)
    insiders = get_finnhub_insider_transactions("AAPL", "2026-01-15", client=client)
    assert "inside" in company and "future" not in company
    assert "inside global" in global_news and "future global" not in global_news
    assert "inside" in insiders and "future" not in insiders


def test_finnhub_does_not_claim_historical_ohlcv():
    import tradingagents.dataflows.finnhub as module

    assert not hasattr(module, "fetch_finnhub_ohlcv")
