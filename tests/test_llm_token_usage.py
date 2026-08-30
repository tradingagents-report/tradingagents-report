from types import SimpleNamespace

from tradingagents.llm_clients.token_usage import TokenUsageCallback


def test_usage_callback_exposes_api_summary_and_cli_stats():
    message = SimpleNamespace(
        usage_metadata={"input_tokens": 12, "output_tokens": 5, "total_tokens": 17},
        response_metadata={"model_name": "gpt-test"},
    )
    response = SimpleNamespace(
        generations=[[SimpleNamespace(message=message)]],
        llm_output={},
    )
    callback = TokenUsageCallback()

    callback.on_llm_end(response)
    callback.on_tool_start({"name": "get_stock_data"}, "AAPL")

    assert callback.summary()["by_model"]["gpt-test"]["total_tokens"] == 17
    assert callback.get_stats() == {
        "llm_calls": 1,
        "tool_calls": 1,
        "tokens_in": 12,
        "tokens_out": 5,
    }
