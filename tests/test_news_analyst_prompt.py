"""Guard the news analyst prompt against tool-signature drift (#1116).

The prompt used to advertise ``get_news(query, ...)`` while the tool takes a
``ticker``, tricking the LLM into hallucinating free-text query calls.
"""
import inspect

import pytest

import tradingagents.agents.analysts.news_analyst as na
import tradingagents.agents.analysts.sentiment_analyst as sentiment_analyst
import tradingagents.agents.analysts.social_media_analyst as social_media_analyst
from tradingagents.agents.utils.news_data_tools import get_news


@pytest.mark.unit
def test_get_news_takes_ticker_not_query():
    arg_names = set(get_news.args.keys())
    assert "ticker" in arg_names
    assert "query" not in arg_names


@pytest.mark.unit
def test_news_prompt_matches_get_news_signature():
    src = inspect.getsource(na)
    assert "get_news(ticker, start_date, end_date)" in src
    assert "get_news(query" not in src


@pytest.mark.unit
@pytest.mark.parametrize("module", [sentiment_analyst, social_media_analyst])
def test_sentiment_prompts_are_news_provider_neutral(module):
    src = inspect.getsource(module)
    assert "Yahoo Finance" not in src


@pytest.mark.unit
def test_sentiment_prompt_names_configured_market_news_providers():
    src = inspect.getsource(sentiment_analyst)
    assert "configured market news providers" in src
