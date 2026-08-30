from __future__ import annotations

import threading
from collections import defaultdict
from contextlib import suppress
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

TOKEN_KEYS = {
    "input_tokens": "prompt_tokens",
    "prompt_tokens": "prompt_tokens",
    "cache_read_input_tokens": "cache_read_input_tokens",
    "cache_creation_input_tokens": "cache_creation_input_tokens",
    "output_tokens": "completion_tokens",
    "completion_tokens": "completion_tokens",
    "reasoning_tokens": "reasoning_tokens",
    "total_tokens": "total_tokens",
}


class TokenUsageCallback(BaseCallbackHandler):
    """Collect token and tool usage returned by LangChain callbacks."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.calls = 0
        self.tool_calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.reasoning_tokens = 0
        self.cache_read_input_tokens = 0
        self.cache_creation_input_tokens = 0
        self.total_tokens = 0
        self.by_model: dict[str, dict[str, int]] = defaultdict(new_counter)

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        usage_items = list(extract_usage_items(response))
        if not usage_items:
            return

        with self._lock:
            self.calls += 1
            for usage, model_name in usage_items:
                self._add_usage(normalize_usage(usage), model_name)

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs: Any) -> None:
        with self._lock:
            self.tool_calls += 1

    def summary(self) -> dict[str, Any]:
        with self._lock:
            total = self.total_tokens or self.prompt_tokens + self.completion_tokens
            return {
                "calls": self.calls,
                "tool_calls": self.tool_calls,
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "reasoning_tokens": self.reasoning_tokens,
                "cache_read_input_tokens": self.cache_read_input_tokens,
                "cache_creation_input_tokens": self.cache_creation_input_tokens,
                "total_tokens": total,
                "by_model": {model: dict(values) for model, values in self.by_model.items()},
            }

    def get_stats(self) -> dict[str, int]:
        summary = self.summary()
        return {
            "llm_calls": summary["calls"],
            "tool_calls": summary["tool_calls"],
            "tokens_in": summary["prompt_tokens"],
            "tokens_out": summary["completion_tokens"],
        }

    def _add_usage(self, usage: dict[str, int], model_name: str | None) -> None:
        if not usage:
            return

        self.prompt_tokens += usage.get("prompt_tokens", 0)
        self.completion_tokens += usage.get("completion_tokens", 0)
        self.reasoning_tokens += usage.get("reasoning_tokens", 0)
        self.cache_read_input_tokens += usage.get("cache_read_input_tokens", 0)
        self.cache_creation_input_tokens += usage.get("cache_creation_input_tokens", 0)
        self.total_tokens += usage.get("total_tokens", 0)

        if model_name:
            model_bucket = self.by_model[model_name]
            for key, value in usage.items():
                model_bucket[key] = int(model_bucket.get(key, 0)) + int(value)


def new_counter() -> dict[str, int]:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "reasoning_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "total_tokens": 0,
    }


def extract_usage_items(response: Any):
    message_items = []
    for generation_list in getattr(response, "generations", None) or []:
        for generation in generation_list:
            message = getattr(generation, "message", None)
            if message is None:
                continue
            metadata = getattr(message, "response_metadata", None) or {}
            usage_metadata = getattr(message, "usage_metadata", None) or {}
            usage = first_dict(
                usage_metadata,
                metadata.get("token_usage"),
                metadata.get("usage"),
                metadata.get("usage_metadata"),
            )
            if usage:
                message_items.append((usage, model_from_metadata(metadata)))

    if message_items:
        yield from message_items
        return

    llm_output = getattr(response, "llm_output", None) or {}
    usage = first_dict(
        llm_output.get("token_usage"),
        llm_output.get("usage"),
        llm_output.get("usage_metadata"),
    )
    if usage:
        yield usage, model_from_metadata(llm_output)


def normalize_usage(usage: dict[str, Any]) -> dict[str, int]:
    normalized: dict[str, int] = {}
    for source_key, target_key in TOKEN_KEYS.items():
        value = usage.get(source_key)
        if isinstance(value, dict):
            value = value.get("total") or value.get("tokens")
        if value is None:
            continue
        try:
            normalized[target_key] = normalized.get(target_key, 0) + int(value)
        except (TypeError, ValueError):
            continue

    output_details = usage.get("output_token_details") or usage.get("completion_tokens_details") or {}
    if isinstance(output_details, dict):
        reasoning = output_details.get("reasoning") or output_details.get("reasoning_tokens")
        if reasoning is not None:
            with suppress(TypeError, ValueError):
                normalized["reasoning_tokens"] = normalized.get("reasoning_tokens", 0) + int(reasoning)

    input_details = usage.get("input_token_details") or usage.get("prompt_tokens_details") or {}
    if isinstance(input_details, dict):
        cache_read = input_details.get("cache_read") or input_details.get("cached_tokens")
        if cache_read is not None:
            with suppress(TypeError, ValueError):
                normalized["cache_read_input_tokens"] = (
                    normalized.get("cache_read_input_tokens", 0) + int(cache_read)
                )

    if "total_tokens" not in normalized:
        total = normalized.get("prompt_tokens", 0) + normalized.get("completion_tokens", 0)
        if total:
            normalized["total_tokens"] = total
    return normalized


def first_dict(*values: Any) -> dict[str, Any] | None:
    for value in values:
        if isinstance(value, dict) and value:
            return value
    return None


def model_from_metadata(metadata: dict[str, Any]) -> str | None:
    for key in ("model_name", "model", "model_id"):
        value = metadata.get(key)
        if value:
            return str(value)
    return None
