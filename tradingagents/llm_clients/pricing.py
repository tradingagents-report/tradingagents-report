from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

DEFAULT_PRICING_SOURCE = "https://models.dev/api.json"
BASELLM_SOURCE_URL = "https://basellm.github.io"
PRICING_SOURCE_URLS = [
    DEFAULT_PRICING_SOURCE,
    f"{BASELLM_SOURCE_URL}/api.json",
    f"{BASELLM_SOURCE_URL}/models.json",
    f"{BASELLM_SOURCE_URL}/pricing.json",
]
PRICING_REFRESH_INTERVAL = timedelta(hours=1)
USD_QUANT = Decimal("0.00000001")
MODEL_ALIASES = {
    "gpt-5.6-sol": "gpt-5.6-sol",
}

FALLBACK_MODEL_PRICES = [
    {
        "provider": "openai",
        "model": "gpt-5.6-sol",
        "billing_mode": "standard",
        "context_tier": "short",
        "currency": "USD",
        "unit_tokens": 1_000_000,
        "input_price": Decimal("5.00"),
        "cached_input_price": Decimal("0.50"),
        "cache_write_price": Decimal("6.25"),
        "output_price": Decimal("30.00"),
        "source_url": DEFAULT_PRICING_SOURCE,
    },
]


def model_key(model: str | None) -> str:
    normalized = str(model or "").strip()
    if normalized.startswith("gpt-5.6-sol"):
        return "gpt-5.6-sol"
    return MODEL_ALIASES.get(normalized, normalized)


def calculate_cost(token_usage: dict[str, Any] | None, price_rows: list[dict[str, Any]]) -> dict[str, Any]:
    usage = token_usage or {}
    prices = {model_key(row.get("model")): row for row in price_rows}
    by_model = usage.get("by_model") if isinstance(usage.get("by_model"), dict) else {}
    items: list[dict[str, Any]] = []
    total = Decimal("0")

    if by_model:
        for raw_model, model_usage in by_model.items():
            item = calculate_model_cost(str(raw_model), dict(model_usage or {}), prices)
            items.append(item)
            total += Decimal(str(item["total_cost"]))
    else:
        inferred_model = str(usage.get("model") or "")
        item = calculate_model_cost(inferred_model, usage, prices)
        items.append(item)
        total += Decimal(str(item["total_cost"]))

    rounded_total = quantize_usd(total)
    return {
        "currency": "USD",
        "total_cost": decimal_to_float(rounded_total),
        "total_cost_usd": decimal_to_float(rounded_total),
        "pricing_source": DEFAULT_PRICING_SOURCE,
        "items": items,
    }


def calculate_model_cost(
    raw_model: str,
    usage: dict[str, Any],
    prices: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    normalized_model = model_key(raw_model)
    price = prices.get(normalized_model)
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    cache_read_tokens = int(usage.get("cache_read_input_tokens") or 0)
    cache_write_tokens = int(usage.get("cache_creation_input_tokens") or 0)
    uncached_input_tokens = max(prompt_tokens - cache_read_tokens - cache_write_tokens, 0)

    if not price:
        return {
            "model": raw_model,
            "matched_model": normalized_model,
            "priced": False,
            "unit_tokens": None,
            "input_tokens": prompt_tokens,
            "uncached_input_tokens": uncached_input_tokens,
            "cached_input_tokens": cache_read_tokens,
            "cache_write_input_tokens": cache_write_tokens,
            "output_tokens": completion_tokens,
            "total_tokens": int(usage.get("total_tokens") or prompt_tokens + completion_tokens),
            "total_cost": 0.0,
            "total_cost_usd": 0.0,
        }

    unit_tokens = Decimal(str(price.get("unit_tokens") or 1_000_000))
    input_cost = token_cost(uncached_input_tokens, price.get("input_price"), unit_tokens)
    cached_input_cost = token_cost(cache_read_tokens, price.get("cached_input_price"), unit_tokens)
    cache_write_cost = token_cost(cache_write_tokens, price.get("cache_write_price"), unit_tokens)
    output_cost = token_cost(completion_tokens, price.get("output_price"), unit_tokens)
    total = quantize_usd(input_cost + cached_input_cost + cache_write_cost + output_cost)

    return {
        "model": raw_model,
        "matched_model": normalized_model,
        "priced": True,
        "billing_mode": price.get("billing_mode"),
        "context_tier": price.get("context_tier"),
        "currency": price.get("currency") or "USD",
        "unit_tokens": int(unit_tokens),
        "input_price": decimal_to_float(price.get("input_price")),
        "cached_input_price": decimal_to_float(price.get("cached_input_price")),
        "cache_write_price": decimal_to_float(price.get("cache_write_price")),
        "output_price": decimal_to_float(price.get("output_price")),
        "input_tokens": prompt_tokens,
        "uncached_input_tokens": uncached_input_tokens,
        "cached_input_tokens": cache_read_tokens,
        "cache_write_input_tokens": cache_write_tokens,
        "output_tokens": completion_tokens,
        "total_tokens": int(usage.get("total_tokens") or prompt_tokens + completion_tokens),
        "input_cost": decimal_to_float(input_cost),
        "cached_input_cost": decimal_to_float(cached_input_cost),
        "cache_write_cost": decimal_to_float(cache_write_cost),
        "output_cost": decimal_to_float(output_cost),
        "total_cost": decimal_to_float(total),
        "total_cost_usd": decimal_to_float(total),
    }


def token_cost(tokens: int, price_per_unit: Any, unit_tokens: Decimal) -> Decimal:
    if not tokens or price_per_unit is None:
        return Decimal("0")
    return quantize_usd((Decimal(tokens) / unit_tokens) * Decimal(str(price_per_unit)))


def quantize_usd(value: Decimal) -> Decimal:
    return value.quantize(USD_QUANT, rounding=ROUND_HALF_UP)


def decimal_to_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(quantize_usd(Decimal(str(value))))


def pricing_is_stale(last_success_at: Any) -> bool:
    if last_success_at is None:
        return True
    if isinstance(last_success_at, str):
        try:
            last_success_at = datetime.fromisoformat(last_success_at.replace("Z", "+00:00"))
        except ValueError:
            return True
    if not isinstance(last_success_at, datetime):
        return True
    if last_success_at.tzinfo is None:
        last_success_at = last_success_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last_success_at >= PRICING_REFRESH_INTERVAL


def fetch_price_rows(source_urls: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    rows: list[dict[str, Any]] = []
    source_results: list[dict[str, Any]] = []
    for source_url in source_urls or PRICING_SOURCE_URLS:
        try:
            payload = fetch_json(source_url)
            parsed = parse_price_rows(source_url, payload)
            rows.extend(parsed)
            source_results.append(
                {
                    "source_url": source_url,
                    "success": True,
                    "model_count": len(parsed),
                    "error": None,
                }
            )
        except Exception as exc:
            source_results.append(
                {
                    "source_url": source_url,
                    "success": False,
                    "model_count": 0,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return dedupe_price_rows(rows), source_results


def fetch_json(source_url: str) -> dict[str, Any]:
    request = urllib.request.Request(source_url, headers={"User-Agent": "tradingagents-api/0.1"})
    with urllib.request.urlopen(request, timeout=20) as response:
        status = getattr(response, "status", 200)
        if status >= 400:
            raise urllib.error.HTTPError(source_url, status, "HTTP error", response.headers, None)
        return json.loads(response.read().decode("utf-8"))


def parse_price_rows(source_url: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    if source_url.startswith("https://models.dev"):
        return parse_models_dev_price_rows(source_url, payload)
    return parse_generic_price_rows(source_url, payload)


def parse_models_dev_price_rows(source_url: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for provider, provider_payload in payload.items():
        if not isinstance(provider_payload, dict):
            continue
        models = provider_payload.get("models")
        if not isinstance(models, dict):
            continue
        for model_id, model_payload in models.items():
            if not isinstance(model_payload, dict):
                continue
            cost = model_payload.get("cost")
            if not isinstance(cost, dict):
                continue
            row = row_from_cost(
                provider=str(provider),
                model=str(model_payload.get("id") or model_id),
                cost=cost,
                source_url=source_url,
            )
            if row:
                rows.append(row)
    return rows


def parse_generic_price_rows(source_url: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    if "models" in payload and isinstance(payload["models"], dict):
        payload = {"basellm": {"models": payload["models"]}}
    return parse_models_dev_price_rows(source_url, payload)


def row_from_cost(
    *,
    provider: str,
    model: str,
    cost: dict[str, Any],
    source_url: str,
) -> dict[str, Any] | None:
    input_price = decimal_or_none(cost.get("input"))
    output_price = decimal_or_none(cost.get("output"))
    if input_price is None or output_price is None:
        return None
    return {
        "provider": provider,
        "model": model,
        "billing_mode": "standard",
        "context_tier": "short",
        "currency": "USD",
        "unit_tokens": 1_000_000,
        "input_price": input_price,
        "cached_input_price": decimal_or_none(cost.get("cache_read")),
        "cache_write_price": decimal_or_none(cost.get("cache_write")),
        "output_price": output_price,
        "source_url": source_url,
    }


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def dedupe_price_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row["provider"]),
            str(row["model"]),
            str(row["billing_mode"]),
            str(row["context_tier"]),
        )
        deduped[key] = row
    return list(deduped.values())
