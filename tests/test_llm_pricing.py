from decimal import Decimal

from tradingagents.llm_clients.pricing import calculate_cost


def test_calculate_cost_separates_cached_and_uncached_input():
    prices = [{
        "provider": "openai",
        "model": "gpt-test",
        "unit_tokens": 1_000_000,
        "input_price": Decimal("10"),
        "cached_input_price": Decimal("1"),
        "cache_write_price": None,
        "output_price": Decimal("20"),
        "billing_mode": "standard",
        "context_tier": "short",
        "currency": "USD",
    }]
    usage = {
        "model": "gpt-test",
        "prompt_tokens": 1000,
        "cache_read_input_tokens": 400,
        "completion_tokens": 200,
        "total_tokens": 1200,
    }

    result = calculate_cost(usage, prices)

    assert result["total_cost_usd"] == 0.0104
    assert result["items"][0]["uncached_input_tokens"] == 600
