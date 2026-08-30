"""TradingView news adapter tests."""

from datetime import datetime, timezone
from unittest.mock import Mock

from tradingagents.dataflows.tradingview.news import (
    get_tradingview_global_news,
    get_tradingview_news,
)


def epoch(date: str) -> int:
    """Convert an ISO date to Unix UTC seconds."""
    return int(datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def article(title: str, date: str, **overrides):
    item = {
        "title": title,
        "published": epoch(date),
        "link": f"https://example.com/{title.lower()}",
        "provider": {"name": "Reuters"},
    }
    item.update(overrides)
    return item


def test_company_news_filters_future_and_formats_source():
    client = Mock()
    client.get.return_value = {
        "items": [
            article("PAST", "2026-07-09", summary="Past summary"),
            article("FUTURE", "2026-07-13"),
        ]
    }

    output = get_tradingview_news(
        "NASDAQ:AAPL", "2026-07-08", "2026-07-10", client=client
    )

    assert "## NASDAQ:AAPL News, from 2026-07-08 to 2026-07-10:" in output
    assert "### PAST (source: Reuters)" in output
    assert "Past summary" in output
    assert "FUTURE" not in output
    client.get.assert_called_once_with(
        "/api/news",
        params={"symbol": "NASDAQ:AAPL", "lang": "en", "market": "stock"},
    )


def test_global_news_uses_economic_endpoint_and_limits_after_filter_and_deduplication():
    client = Mock()
    client.get.return_value = {
        "items": [
            article("FUTURE", "2026-07-13"),
            article("A", "2026-07-10"),
            article("A", "2026-07-10", link="https://duplicate"),
            article("B", "2026-07-09"),
        ]
    }

    output = get_tradingview_global_news(
        "2026-07-11", look_back_days=3, limit=2, client=client
    )

    client.get.assert_called_once_with("/api/news/economic", params={"lang": "en"})
    assert output.count("### ") == 2
    assert "### A" in output
    assert "### B" in output
    assert "FUTURE" not in output


def test_company_news_uses_story_path_only_without_direct_link():
    client = Mock()
    client.get.return_value = {
        "items": [
            article(
                "DIRECT",
                "2026-07-09",
                link="https://publisher.example/direct",
                storyPath="/news/direct-fallback/",
            ),
            article("FALLBACK", "2026-07-09", link="", storyPath="/news/fallback/"),
        ]
    }

    output = get_tradingview_news(
        "NASDAQ:AAPL", "2026-07-08", "2026-07-10", client=client
    )

    assert "Link: https://publisher.example/direct" in output
    assert "https://www.tradingview.com/news/direct-fallback/" not in output
    assert "Link: https://www.tradingview.com/news/fallback/" in output


def test_historical_undated_company_news_returns_existing_no_news_text():
    client = Mock()
    client.get.return_value = {
        "items": [{"title": "UNKNOWN DATE", "provider": {"name": "Reuters"}}]
    }

    output = get_tradingview_news(
        "NASDAQ:AAPL", "2025-05-01", "2025-05-09", client=client
    )

    assert output == (
        "No news found for NASDAQ:AAPL between 2025-05-01 and 2025-05-09"
    )


def test_company_news_excludes_undated_and_incomplete_current_articles():
    client = Mock()
    client.get.return_value = {
        "items": [
            {"title": "CURRENT BUT UNDATED", "provider": {"name": "Reuters"}, "link": "https://example.com"},
            article("   ", "2026-07-09"),
            article("NO PROVIDER", "2026-07-09", provider={"name": "Unknown"}),
            article("NO LINK", "2026-07-09", link="", storyPath="not-a-path"),
        ]
    }

    output = get_tradingview_news(
        "NASDAQ:AAPL", "2026-07-08", "2026-07-10", client=client
    )

    assert output == "No news found for NASDAQ:AAPL between 2026-07-08 and 2026-07-10"


def test_global_empty_window_returns_existing_no_news_text():
    client = Mock()
    client.get.return_value = {"items": [article("FUTURE", "2026-07-13")]}

    output = get_tradingview_global_news(
        "2026-07-11", look_back_days=3, limit=2, client=client
    )

    assert output == "No global news found between 2026-07-08 and 2026-07-11"
