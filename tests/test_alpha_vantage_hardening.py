"""Alpha Vantage request hardening.

Regressions for #990 (no request timeout -> can hang), #991 (invalid-key
responses mislabeled as rate limits and silently treated as transient), and
#1115 (fundamentals look-ahead filter never ran because the payload is a JSON
string, not a dict).
"""
import json

import pandas as pd
import pytest

import tradingagents.dataflows.alpha_vantage.common as av
import tradingagents.dataflows.alpha_vantage.fundamentals as avf
import tradingagents.dataflows.alpha_vantage.stock as avs
from tradingagents.dataflows.errors import NoMarketDataError


class _FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def _patched_get(body, capture=None):
    def fake_get(url, params=None, **kwargs):
        if capture is not None:
            capture.update(kwargs)
        return _FakeResponse(body)
    return fake_get


@pytest.mark.unit
def test_request_passes_timeout(monkeypatch):
    captured = {}
    monkeypatch.setattr(av.requests, "get", _patched_get("Date,Close\n2025-01-02,1.0", captured))
    av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})
    assert captured.get("timeout") == av.REQUEST_TIMEOUT  # #990


def test_structured_alpha_vantage_ohlcv_parses_filtered_stock_response(monkeypatch):
    csv = (
        "timestamp,open,high,low,close,adjusted_close,volume,dividend_amount,split_coefficient\n"
        "2026-07-10,100,105,99,104,104,1234,0,1\n"
    )
    monkeypatch.setattr(avs, "get_stock", lambda *args: csv)

    result = avs.fetch_alpha_vantage_ohlcv("AAPL", "2026-07-10", "2026-07-10")

    assert result.provider == "alpha_vantage"
    assert result.resolved_symbol == "AAPL"
    assert list(result.data.columns) == ["Date", "Open", "High", "Low", "Close", "Volume"]
    assert result.data.equals(
        pd.DataFrame(
            {
                "Date": [pd.Timestamp("2026-07-10")],
                "Open": [100], "High": [105], "Low": [99],
                "Close": [104], "Volume": [1234],
            }
        )
    )


def test_structured_alpha_vantage_ohlcv_rejects_invalid_end_date(monkeypatch):
    monkeypatch.setattr(avs, "get_stock", lambda *args: "")
    with pytest.raises(ValueError, match="time data"):
        avs.fetch_alpha_vantage_ohlcv("AAPL", "2026-07-10", "not-a-date")


def test_structured_alpha_vantage_ohlcv_rejects_reversed_range(monkeypatch):
    monkeypatch.setattr(avs, "get_stock", lambda *args: "")
    with pytest.raises(ValueError, match="end_date"):
        avs.fetch_alpha_vantage_ohlcv("AAPL", "2026-07-11", "2026-07-10")


def test_structured_alpha_vantage_ohlcv_refilters_upstream_rows(monkeypatch):
    csv = (
        "Date,open,high,low,close,volume\n"
        "2026-07-11,110,115,109,114,1300\n"
        "2026-07-10,100,105,99,104,1234\n"
        "2026-07-09,90,95,89,94,1200\n"
    )
    monkeypatch.setattr(avs, "get_stock", lambda *args: csv)

    result = avs.fetch_alpha_vantage_ohlcv("AAPL", "2026-07-10", "2026-07-10")

    assert result.data["Date"].tolist() == [pd.Timestamp("2026-07-10")]


@pytest.mark.parametrize(
    "csv",
    [
        "open,high,low,close,volume\n1,2,0,1,10\n",
        "timestamp,open,high,low,close,volume\nnot-a-date,1,2,0,1,10\n",
        "timestamp,open,high,low,close,volume\n2026-07-09,1,2,0,1,10\n",
    ],
)
def test_structured_alpha_vantage_ohlcv_rejects_unusable_dates(monkeypatch, csv):
    monkeypatch.setattr(avs, "get_stock", lambda *args: csv)

    with pytest.raises(NoMarketDataError):
        avs.fetch_alpha_vantage_ohlcv("AAPL", "2026-07-10", "2026-07-10")


@pytest.mark.unit
def test_rate_limit_detected(monkeypatch):
    body = '{"Information": "Our standard API rate limit is 25 requests per day. ... your API key ..."}'
    monkeypatch.setattr(av.requests, "get", _patched_get(body))
    with pytest.raises(av.AlphaVantageRateLimitError):
        av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})


@pytest.mark.unit
def test_invalid_key_not_mislabeled_as_rate_limit(monkeypatch):
    # AV's invalid-key notice mentions "API key"; it must NOT be treated as a
    # (transient) rate limit, but surface as a real configuration error (#991).
    body = ('{"Information": "the parameter apikey is invalid or missing. '
            'Please claim your free API key on (https://www.alphavantage.co/support/#api-key)."}')
    monkeypatch.setattr(av.requests, "get", _patched_get(body))
    with pytest.raises(av.AlphaVantageNotConfiguredError):
        av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})
    with pytest.raises(av.AlphaVantageRateLimitError):  # sanity: rate-limit path still distinct
        monkeypatch.setattr(av.requests, "get", _patched_get('{"Note": "API call frequency is 5 calls per minute."}'))
        av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})


_FUNDAMENTALS_JSON = json.dumps({
    "symbol": "AAPL",
    "annualReports": [
        {"fiscalDateEnding": "2025-12-31", "totalAssets": "1"},   # future -> must drop
        {"fiscalDateEnding": "2023-12-31", "totalAssets": "2"},   # past   -> must keep
    ],
    "quarterlyReports": [
        {"fiscalDateEnding": "2024-06-30", "totalAssets": "3"},   # future -> must drop
        {"fiscalDateEnding": "2023-09-30", "totalAssets": "4"},   # past   -> must keep
    ],
})


@pytest.mark.unit
def test_fundamentals_look_ahead_filter_runs_on_json_string(monkeypatch):
    # #1115: the payload arrives as a JSON *string*; the old dict-only guard let
    # future-dated fiscal periods leak into historical runs.
    monkeypatch.setattr(avf, "_make_api_request", lambda fn, params: _FUNDAMENTALS_JSON)
    out = avf.get_balance_sheet("AAPL", curr_date="2024-01-01")
    assert isinstance(out, str)  # callers still receive a str
    parsed = json.loads(out)
    assert [r["fiscalDateEnding"] for r in parsed["annualReports"]] == ["2023-12-31"]
    assert [r["fiscalDateEnding"] for r in parsed["quarterlyReports"]] == ["2023-09-30"]


@pytest.mark.unit
def test_fundamentals_no_curr_date_passes_through(monkeypatch):
    monkeypatch.setattr(avf, "_make_api_request", lambda fn, params: _FUNDAMENTALS_JSON)
    assert avf.get_income_statement("AAPL") == _FUNDAMENTALS_JSON


@pytest.mark.unit
def test_fundamentals_non_json_body_unchanged(monkeypatch):
    monkeypatch.setattr(avf, "_make_api_request", lambda fn, params: "not-json")
    assert avf.get_cashflow("AAPL", curr_date="2024-01-01") == "not-json"
