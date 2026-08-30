"""TradingView OHLCV, identity, and indicator adapter tests."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pandas as pd
import pytest

from tradingagents.dataflows import interface
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.provider_models import ProviderResult, parse_instrument
from tradingagents.dataflows.tradingview import stock as tv

fetch_tradingview_ohlcv = tv.fetch_tradingview_ohlcv
get_tradingview_identity = tv.get_tradingview_identity


def _price_payload(history):
    return {
        "symbol": "NASDAQ:AAPL",
        "history": history,
        "info": {"timezone": "America/New_York", "currency_code": "USD"},
    }


def _epoch(date: str) -> int:
    return int(datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def test_ohlcv_explicitly_requests_japanese_candles():
    client = Mock()
    client.get.return_value = _price_payload(
        [
            {
                "time": 1783728000,
                "open": 100,
                "max": 105,
                "min": 99,
                "close": 104,
                "volume": 10,
            },
            {
                "time": 1783641600,
                "open": 98,
                "max": 101,
                "min": 97,
                "close": 100,
                "volume": 9,
            },
        ]
    )

    result = fetch_tradingview_ohlcv(
        "NASDAQ:AAPL", "2026-07-09", "2026-07-10", client=client
    )

    client.get.assert_called_once()
    path = client.get.call_args.args[0]
    params = client.get.call_args.kwargs["params"]
    assert path == "/api/price/NASDAQ%3AAAPL"
    assert "symbol" not in params
    assert params["type"] == "Japanese"
    assert params["timeframe"] == "D"
    assert params["range"] == 400
    assert params["to"] == int(
        datetime(2026, 7, 10, 23, 59, 59, tzinfo=timezone.utc).timestamp()
    )
    assert list(result.data.columns) == ["Date", "Open", "High", "Low", "Close", "Volume"]
    assert result.data["Date"].is_monotonic_increasing
    assert result.data["Date"].dt.tz is None
    assert result.resolved_symbol == "NASDAQ:AAPL"
    assert result.adjustment_mode == "Japanese"
    assert result.quote_currency == "USD"


def test_qualified_symbol_does_not_invoke_market_search():
    client = Mock()
    client.get.return_value = _price_payload(
        [
            {
                "time": _epoch("2026-07-10"),
                "open": 100,
                "max": 105,
                "min": 99,
                "close": 104,
                "volume": 10,
            }
        ]
    )

    fetch_tradingview_ohlcv("NASDAQ:AAPL", "2026-07-10", "2026-07-10", client=client)

    assert client.get.call_count == 1
    assert client.get.call_args.args[0] == "/api/price/NASDAQ%3AAAPL"


def test_bare_equity_is_resolved_with_documented_market_search():
    client = Mock()
    client.get.side_effect = [
        {
            "markets": [
                {
                    "symbol": "AAPL",
                    "source_id": "NASDAQ",
                    "full_name": "NASDAQ:AAPL",
                    "is_primary_listing": True,
                }
            ]
        },
        _price_payload(
            [
                {
                    "time": _epoch("2026-07-10"),
                    "open": 100,
                    "max": 105,
                    "min": 99,
                    "close": 104,
                    "volume": 10,
                }
            ]
        ),
    ]

    result = fetch_tradingview_ohlcv("AAPL", "2026-07-10", "2026-07-10", client=client)

    assert result.resolved_symbol == "NASDAQ:AAPL"
    assert client.get.call_args_list[0].args[0] == "/api/search/market/AAPL"
    assert client.get.call_args_list[0].kwargs["params"] == {"filter": "stock"}
    assert client.get.call_args_list[1].args[0] == "/api/price/NASDAQ%3AAAPL"


def test_ohlcv_sorts_and_filters_to_inclusive_requested_dates():
    client = Mock()
    client.get.return_value = _price_payload(
        [
            {"time": _epoch("2026-07-11"), "open": 3, "max": 4, "min": 2, "close": 3, "volume": 3},
            {"time": _epoch("2026-07-09"), "open": 1, "max": 2, "min": 0, "close": 1, "volume": 1},
            {"time": _epoch("2026-07-10"), "open": 2, "max": 3, "min": 1, "close": 2, "volume": 2},
        ]
    )

    result = fetch_tradingview_ohlcv(
        "NASDAQ:AAPL", "2026-07-09", "2026-07-10", client=client
    )

    assert result.data["Date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2026-07-09",
        "2026-07-10",
    ]
    assert result.data["High"].tolist() == [2, 3]
    assert result.data["Low"].tolist() == [0, 1]


def test_ohlcv_includes_end_date_candle_with_intraday_utc_timestamp():
    client = Mock()
    end_date_noon = datetime(2026, 7, 10, 12, tzinfo=timezone.utc)
    client.get.return_value = _price_payload(
        [
            {
                "time": int(end_date_noon.timestamp()),
                "open": 100,
                "max": 105,
                "min": 99,
                "close": 104,
                "volume": 10,
            }
        ]
    )

    result = fetch_tradingview_ohlcv(
        "NASDAQ:AAPL", "2026-07-10", "2026-07-10", client=client
    )

    assert len(result.data) == 1


def test_ohlcv_rejects_empty_history():
    client = Mock()
    client.get.return_value = _price_payload([])

    with pytest.raises(NoMarketDataError, match="no price history"):
        fetch_tradingview_ohlcv("NASDAQ:AAPL", "2026-07-09", "2026-07-10", client=client)


@pytest.mark.parametrize(
    "history",
    [
        [{"time": 1783728000, "open": 100, "max": 105, "min": 99, "volume": 10}],
        [
            {
                "time": 1783728000,
                "open": 100,
                "max": 105,
                "min": 99,
                "close": "not-a-price",
                "volume": 10,
            }
        ],
    ],
)
def test_ohlcv_rejects_invalid_ohlc(history):
    client = Mock()
    client.get.return_value = _price_payload(history)

    with pytest.raises(NoMarketDataError, match="OHLC"):
        fetch_tradingview_ohlcv("NASDAQ:AAPL", "2026-07-10", "2026-07-10", client=client)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("volume", None),
        ("volume", "not-a-number"),
        ("volume", float("inf")),
        ("open", float("inf")),
        ("close", float("-inf")),
    ],
)
def test_ohlcv_rejects_null_or_non_finite_numeric_fields(field, value):
    history = {
        "time": _epoch("2026-07-10"),
        "open": 100,
        "max": 105,
        "min": 99,
        "close": 104,
        "volume": 10,
    }
    history[field] = value
    client = Mock()
    client.get.return_value = _price_payload([history])

    with pytest.raises(NoMarketDataError, match="OHLCV"):
        fetch_tradingview_ohlcv("NASDAQ:AAPL", "2026-07-10", "2026-07-10", client=client)


@pytest.mark.parametrize("timestamp", [None, "not-a-timestamp", float("inf")])
def test_ohlcv_rejects_missing_invalid_or_non_finite_timestamp(timestamp):
    client = Mock()
    client.get.return_value = _price_payload(
        [{"time": timestamp, "open": 100, "max": 105, "min": 99, "close": 104, "volume": 10}]
    )

    with pytest.raises(NoMarketDataError, match="OHLCV"):
        fetch_tradingview_ohlcv("NASDAQ:AAPL", "2026-07-10", "2026-07-10", client=client)


def test_ohlcv_rejects_duplicate_timestamp():
    bar = {"time": _epoch("2026-07-10"), "open": 100, "max": 105, "min": 99, "close": 104, "volume": 10}
    client = Mock()
    client.get.return_value = _price_payload([bar, bar.copy()])

    with pytest.raises(NoMarketDataError, match="duplicate"):
        fetch_tradingview_ohlcv("NASDAQ:AAPL", "2026-07-10", "2026-07-10", client=client)


@pytest.mark.parametrize(
    "overrides",
    [
        {"max": 98, "min": 99},
        {"max": 99},
        {"min": 101},
        {"volume": -1},
    ],
)
def test_ohlcv_rejects_impossible_price_or_negative_volume(overrides):
    bar = {"time": _epoch("2026-07-10"), "open": 100, "max": 105, "min": 99, "close": 104, "volume": 10}
    bar.update(overrides)
    client = Mock()
    client.get.return_value = _price_payload([bar])

    with pytest.raises(NoMarketDataError, match="invalid OHLCV"):
        fetch_tradingview_ohlcv("NASDAQ:AAPL", "2026-07-10", "2026-07-10", client=client)


def test_ohlcv_accepts_zero_volume():
    client = Mock()
    client.get.return_value = _price_payload(
        [{"time": _epoch("2026-07-10"), "open": 100, "max": 105, "min": 99, "close": 104, "volume": 0}]
    )

    result = fetch_tradingview_ohlcv(
        "NASDAQ:AAPL", "2026-07-10", "2026-07-10", client=client
    )

    assert result.data.loc[0, "Volume"] == 0


def test_structured_ohlcv_route_falls_back_after_invalid_tradingview_bar(monkeypatch):
    client = Mock()
    client.get.return_value = _price_payload(
        [{"time": _epoch("2026-07-10"), "open": 100, "max": 99, "min": 98, "close": 99, "volume": 10}]
    )
    requested = parse_instrument("NASDAQ:AAPL")
    yahoo_result = ProviderResult(
        pd.DataFrame(
            {
                "Date": [pd.Timestamp("2026-07-10")],
                "Open": [100],
                "High": [105],
                "Low": [99],
                "Close": [104],
                "Volume": [10],
            }
        ),
        "yfinance",
        requested,
        "AAPL",
    )
    yahoo = Mock(return_value=yahoo_result)
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_ohlcv",
        {
            "tradingview": lambda *args: fetch_tradingview_ohlcv(*args, client=client),
            "yfinance": yahoo,
        },
    )

    result = interface.route_structured(
        "get_ohlcv", "NASDAQ:AAPL", "2026-07-10", "2026-07-10"
    )

    assert result is yahoo_result
    yahoo.assert_called_once_with("NASDAQ:AAPL", "2026-07-10", "2026-07-10")


def test_identity_maps_company_fields():
    client = Mock()
    client.get.return_value = {
        "symbol": "NASDAQ:AAPL",
        "company": {
            "description": "Apple Inc.",
            "sector": "Technology",
            "industry": "Hardware",
            "listed_exchange": "NASDAQ",
            "currency_code": "USD",
            "fundamental_currency_code": "USD",
        },
    }

    assert get_tradingview_identity("NASDAQ:AAPL", client=client) == {
        "company_name": "Apple Inc.",
        "sector": "Technology",
        "industry": "Hardware",
        "exchange": "NASDAQ",
        "quote_type": "stock",
        "quote_currency": "USD",
        "fundamental_currency": "USD",
    }
    client.get.assert_called_once_with("/api/market-data/NASDAQ%3AAAPL/company")


def test_identity_prefers_local_description_over_english():
    client = Mock()
    client.get.return_value = {
        "symbol": "SZSE:300814",
        "company": {
            "local_description": "中富电路",
            "description": "Shenzhen JOVE Enterprise Ltd. Class A",
            "sector": "Electronic Technology",
            "industry": "Electronic Components",
            "listed_exchange": "SZSE",
            "currency_code": "CNY",
            "fundamental_currency_code": "CNY",
        },
    }

    assert get_tradingview_identity("300814.SZ", client=client) == {
        "company_name": "中富电路",
        "english_name": "Shenzhen JOVE Enterprise Ltd. Class A",
        "sector": "Electronic Technology",
        "industry": "Electronic Components",
        "exchange": "SZSE",
        "quote_type": "stock",
        "quote_currency": "CNY",
        "fundamental_currency": "CNY",
    }
    client.get.assert_called_once_with("/api/market-data/SZSE%3A300814/company")


def test_identity_rejects_company_without_meaningful_fields():
    client = Mock()
    client.get.return_value = {"symbol": "NASDAQ:AAPL", "company": {}}

    with pytest.raises(NoMarketDataError, match="no company identity"):
        get_tradingview_identity("NASDAQ:AAPL", client=client)


def test_get_tradingview_stock_preserves_header_and_csv_format(monkeypatch):
    frame = pd.DataFrame(
        {
            "Date": [pd.Timestamp("2026-07-10")],
            "Open": [100],
            "High": [105],
            "Low": [99],
            "Close": [104],
            "Volume": [10],
        }
    )
    result = ProviderResult(
        data=frame,
        provider="tradingview",
        requested=parse_instrument("XAUUSD"),
        resolved_symbol="COMEX:GC1!",
        quote_currency="USD",
    )
    monkeypatch.setattr(tv, "fetch_tradingview_ohlcv", lambda *args: result)

    output = tv.get_tradingview_stock("XAUUSD", "2026-07-10", "2026-07-10")

    assert "# Quote currency: USD" in output

    assert output.startswith(
        "# Stock data for COMEX:GC1! (from XAUUSD) from 2026-07-10 to 2026-07-10\n"
        "# Total records: 1\n"
        "# Data retrieved on: "
    )
    assert "\n\nDate,Open,High,Low,Close,Volume\n2026-07-10,100,105,99,104,10\n" in output


def test_get_tradingview_indicators_fetches_warmup_and_delegates(monkeypatch):
    frame = pd.DataFrame({"Date": [pd.Timestamp("2026-07-10")], "Close": [104]})
    provider_result = ProviderResult(
        data=frame,
        provider="tradingview",
        requested=parse_instrument("NASDAQ:AAPL"),
        resolved_symbol="NASDAQ:AAPL",
    )
    fetch = Mock(return_value=provider_result)
    calculate = Mock(return_value="indicator report")
    monkeypatch.setattr(tv, "fetch_tradingview_ohlcv", fetch)
    monkeypatch.setattr(tv, "calculate_indicator_window", calculate)

    output = tv.get_tradingview_indicators("NASDAQ:AAPL", "rsi", "2026-07-10", 5)

    expected_start = (datetime(2026, 7, 10) - timedelta(days=255)).strftime("%Y-%m-%d")
    fetch.assert_called_once_with("NASDAQ:AAPL", expected_start, "2026-07-10")
    calculate.assert_called_once_with(frame, "NASDAQ:AAPL", "rsi", "2026-07-10", 5)
    assert output == "indicator report"


def test_get_tradingview_indicators_validates_before_fetching(monkeypatch):
    fetch = Mock()
    monkeypatch.setattr(tv, "fetch_tradingview_ohlcv", fetch)

    with pytest.raises(ValueError, match="not supported"):
        tv.get_tradingview_indicators("NASDAQ:AAPL", "not-an-indicator", "2026-07-10", 5)

    fetch.assert_not_called()
