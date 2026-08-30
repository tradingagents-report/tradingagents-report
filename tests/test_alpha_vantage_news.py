"""Alpha Vantage news: China A-share skip and error-payload normalization."""

from unittest.mock import patch

import pytest

from tradingagents.dataflows.alpha_vantage import news as av_news


@pytest.mark.unit
@pytest.mark.parametrize("ticker", ["300814.SZ", "SZSE:300814", "600519.SS"])
def test_get_news_skips_china_a_shares_without_http(ticker):
    with patch.object(av_news, "_make_api_request") as request:
        out = av_news.get_news(ticker, "2026-07-17", "2026-07-24")
    request.assert_not_called()
    assert out.startswith("No news found for")
    assert ticker in out


@pytest.mark.unit
def test_get_news_turns_error_json_into_no_news_marker():
    with patch.object(
        av_news,
        "_make_api_request",
        return_value='{"Error Message": "Invalid ticker format: 300814.SZ"}',
    ):
        out = av_news.get_news("AAPL", "2026-07-17", "2026-07-24")
    assert out == "No news found for AAPL between 2026-07-17 and 2026-07-24"


@pytest.mark.unit
def test_get_news_turns_empty_feed_into_no_news_marker():
    with patch.object(
        av_news,
        "_make_api_request",
        return_value='{"feed": []}',
    ):
        out = av_news.get_news("AAPL", "2026-07-17", "2026-07-24")
    assert out == "No news found for AAPL between 2026-07-17 and 2026-07-24"
