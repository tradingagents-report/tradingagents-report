"""TradingView earnings/economic calendar adapter tests."""

from datetime import datetime, timezone
from unittest.mock import Mock

from tradingagents.dataflows.tradingview.calendar import (
    get_tradingview_earnings_calendar,
    get_tradingview_economic_calendar,
)


def epoch(date: str, hour: int = 12) -> int:
    return int(
        datetime.strptime(f"{date} {hour:02d}", "%Y-%m-%d %H")
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )


def test_earnings_calendar_redacts_future_actuals_and_filters_ticker():
    client = Mock()
    client.get.return_value = {
        "data": [
            {
                "symbol": "NASDAQ:AAPL",
                "description": "Apple Inc.",
                "earnings_release_next_date": epoch("2026-07-20"),
                "earnings_per_share_fq": 1.5,
                "earnings_per_share_forecast_fq": 1.4,
                "eps_surprise_percent_fq": 7.0,
                "earnings_per_share_forecast_next_fq": 1.6,
                "revenue_forecast_next_fq": 90000000000,
            },
            {
                "symbol": "NASDAQ:MSFT",
                "description": "Microsoft",
                "earnings_release_next_date": epoch("2026-07-18"),
                "earnings_per_share_forecast_next_fq": 3.0,
            },
        ]
    }

    output = get_tradingview_earnings_calendar(
        "2026-07-11",
        look_forward_days=14,
        market=None,
        ticker="NASDAQ:AAPL",
        client=client,
    )

    assert "# Earnings Calendar (america)" in output
    assert "## NASDAQ:AAPL" in output
    assert "EPS forecast (next): 1.6" in output
    assert "Actuals omitted" in output
    assert "EPS surprise %" not in output
    assert "NASDAQ:MSFT" not in output
    client.get.assert_called_once()
    path, kwargs = client.get.call_args
    assert path[0] == "/api/calendar/earnings"
    assert kwargs["params"]["market"] == "america"


def test_economic_calendar_redacts_future_actual_keeps_past():
    client = Mock()
    client.get.return_value = {
        "result": [
            {
                "title": "CPI YoY",
                "country": "US",
                "importance": 1,
                "date": "2026-07-10T12:30:00.000Z",
                "previous": 2.5,
                "forecast": 2.6,
                "actual": 2.7,
            },
            {
                "title": "Retail Sales MoM",
                "country": "US",
                "importance": 0,
                "date": "2026-07-15T12:30:00.000Z",
                "previous": 0.4,
                "forecast": 0.5,
                "actual": 0.9,
            },
        ]
    }

    output = get_tradingview_economic_calendar(
        "2026-07-11",
        look_back_days=7,
        look_forward_days=14,
        market="america",
        client=client,
    )

    assert "## CPI YoY (US)" in output
    assert "Actual: 2.7" in output
    assert "## Retail Sales MoM (US)" in output
    assert "Actual: n/a (event after analysis date" in output
    assert "Forecast: 0.5" in output
    client.get.assert_called_once()
    assert client.get.call_args[0][0] == "/api/calendar/economic"
