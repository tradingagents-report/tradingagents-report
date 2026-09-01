"""Local research desk: async analysis via run_store + vendor market tools.

Used by the stdio MCP and the self-hosted HTTP adapters. Not the hosted
PostgreSQL job API.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import date, datetime, timedelta
from typing import Any

from application.analysis import AnalysisCommand, AnalysisEvent, run_analysis
from tradingagents.dataflows.listings import listing_from_parts, resolve_listing
from tradingagents.dataflows.structured_data import get_instrument_identity, get_ohlcv
from tradingagents.dataflows.symbol_utils import crypto_base
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.run_store import (
    begin_run,
    get_run,
    is_cancel_requested,
    list_run_events,
    list_runs,
    load_run_report,
    mark_run_failed,
    persist_completed_run,
    request_cancel,
    update_run_progress,
)

logger = logging.getLogger(__name__)

DEFAULT_ANALYSTS = ("market", "social", "news", "fundamentals")
ALLOWED_ANALYSTS = frozenset(DEFAULT_ANALYSTS)
THREAD_PREFIX = "local-analysis-"


class AnalysisCancelled(Exception):
    """Raised from the progress callback when the user cancels a local run."""


def resolve_listing_tool(ticker: str) -> dict[str, Any]:
    listing = resolve_listing(ticker)
    payload = listing.as_dict()
    payload["provider_symbol"] = listing.provider_symbol
    return payload


def start_analysis(
    *,
    ticker: str,
    trade_date: str,
    analysts: list[str] | None = None,
    instrument_exchange: str | None = None,
    instrument_symbol: str | None = None,
    display_ticker: str | None = None,
    output_language: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a running catalog row and start the graph on a background thread."""
    datetime.strptime(trade_date, "%Y-%m-%d")
    if instrument_exchange and instrument_symbol:
        listing = listing_from_parts(
            instrument_exchange, instrument_symbol, display_ticker
        )
        resolved_ticker = listing.provider_symbol or listing.display_ticker
    else:
        listing = resolve_listing(ticker)
        resolved_ticker = listing.provider_symbol or listing.display_ticker
    asset_type = "crypto" if crypto_base(resolved_ticker) else "stock"
    selected = _filter_analysts(analysts, asset_type)
    run_config = analysis_config(config, output_language)
    started = begin_run(
        config=run_config,
        ticker=resolved_ticker,
        trade_date=trade_date,
        analysts=selected,
    )
    if started is None:
        raise RuntimeError("run store is disabled; set TRADINGAGENTS_RUN_STORE_ENABLED=true")
    run_config["run_store_run_id"] = started.run_id
    thread = threading.Thread(
        target=_run_analysis_job,
        kwargs={
            "run_id": started.run_id,
            "ticker": resolved_ticker,
            "trade_date": trade_date,
            "asset_type": asset_type,
            "analysts": selected,
            "config": run_config,
        },
        name=f"{THREAD_PREFIX}{started.run_id[:8]}",
        daemon=False,
    )
    thread.start()
    return {
        "id": started.run_id,
        "status": "running",
        "ticker": resolved_ticker,
        "trade_date": trade_date,
    }


def get_analysis(analysis_id: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    row = get_run(store_config(config), analysis_id)
    if row is None:
        raise ValueError("analysis not found")
    return {
        "id": row["run_id"],
        "status": row.get("status"),
        "ticker": row.get("ticker"),
        "trade_date": row.get("trade_date"),
        "progress_percent": row.get("progress_percent") or 0,
        "current_step": row.get("current_step"),
        "error": row.get("error"),
        "finished_at": row.get("finished_at"),
    }


def get_analysis_events(
    analysis_id: str, config: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    if get_run(store_config(config), analysis_id) is None:
        raise ValueError("analysis not found")
    return list_run_events(store_config(config), analysis_id)


def get_analysis_report(
    analysis_id: str, config: dict[str, Any] | None = None
) -> dict[str, Any]:
    report = load_run_report(store_config(config), analysis_id)
    if report is None:
        raise ValueError("analysis not found")
    if report.get("status") != "succeeded":
        raise ValueError(
            f"report unavailable until status is succeeded (now {report.get('status')})"
        )
    return report


def list_analyses(
    *,
    ticker: str | None = None,
    status: str | None = None,
    limit: int | None = None,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows = list_runs(
        store_config(config),
        ticker=ticker,
        status=status,
        limit=limit or 20,
    )
    return [
        {
            "id": row["run_id"],
            "status": row.get("status"),
            "ticker": row.get("ticker"),
            "trade_date": row.get("trade_date"),
            "created_at": row.get("created_at"),
            "rating": row.get("rating"),
        }
        for row in rows
    ]


def cancel_analysis(analysis_id: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    return request_cancel(store_config(config), analysis_id)


def get_quote(symbol: str) -> dict[str, Any]:
    bars = _ohlcv_records(symbol, bar_count=2)
    last = bars[-1] if bars else None
    return {"symbol": symbol, "quote": last, "bars": bars}


def get_ohlcv_tool(
    symbol: str,
    timeframe: str | None = None,
    bar_count: int | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    if timeframe and timeframe not in {"D", "1D", "d", "1d"}:
        raise ValueError("local get_ohlcv only supports daily bars (timeframe D)")
    count = max(2, min(int(bar_count or 120), 400))
    records = _ohlcv_records(symbol, bar_count=count, as_of=as_of)
    return {
        "symbol": symbol,
        "timeframe": "D",
        "bar_count": len(records),
        "bars": records,
    }


def get_ta_summary(symbol: str) -> dict[str, Any]:
    from tradingagents.dataflows.interface import route_to_vendor

    return {"symbol": symbol, "summary": str(route_to_vendor("get_ta_summary", symbol))}


def get_news(symbol: str, lang: str | None = None) -> dict[str, Any]:
    from tradingagents.dataflows.interface import route_to_vendor

    del lang
    end = date.today()
    start = end - timedelta(days=7)
    return {
        "symbol": symbol,
        "news": str(route_to_vendor("get_news", symbol, start.isoformat(), end.isoformat())),
    }


def get_fundamentals(ticker: str) -> dict[str, Any]:
    identity = get_instrument_identity(ticker)
    listing = resolve_listing_tool(ticker)
    return {"ticker": ticker, "listing": listing, "identity": identity}


def analysis_config(
    config: dict[str, Any] | None, output_language: str | None
) -> dict[str, Any]:
    merged = DEFAULT_CONFIG.copy()
    if config:
        merged.update(config)
    merged["run_store_enabled"] = True
    home_runs = os.path.join(os.path.expanduser("~"), ".tradingagents", "runs")
    merged["run_store_dir"] = (
        merged.get("run_store_dir") or DEFAULT_CONFIG.get("run_store_dir") or home_runs
    )
    if output_language:
        merged["output_language"] = output_language.strip()
    return merged


def store_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    return analysis_config(config, None)


def _run_analysis_job(
    *,
    run_id: str,
    ticker: str,
    trade_date: str,
    asset_type: str,
    analysts: tuple[str, ...],
    config: dict[str, Any],
) -> None:
    def on_event(event: AnalysisEvent) -> None:
        if is_cancel_requested(config, run_id):
            raise AnalysisCancelled("Cancelled by user")
        update_run_progress(
            config,
            run_id,
            progress_percent=event.progress_percent,
            current_step=event.message,
            kind=event.kind,
        )

    try:
        if is_cancel_requested(config, run_id):
            raise AnalysisCancelled("Cancelled by user")
        command = AnalysisCommand(
            ticker=ticker,
            trade_date=trade_date,
            asset_type=asset_type,
            analysts=analysts,
            config=config,
        )
        result = run_analysis(command, on_event=on_event)
        if is_cancel_requested(config, run_id):
            raise AnalysisCancelled("Cancelled by user")
        if getattr(result, "run_id", None) is None:
            persist_completed_run(
                config=config,
                ticker=ticker,
                trade_date=trade_date,
                final_state=result.final_state,
                state_snapshot=result.final_state,
                analysts=analysts,
                run_id=run_id,
            )
    except AnalysisCancelled:
        mark_run_failed(config, run_id, error="Cancelled by user", cancelled=True)
    except Exception as exc:
        logger.exception("Local analysis failed run_id=%s", run_id)
        mark_run_failed(config, run_id, error=f"{type(exc).__name__}: {exc}")


def _filter_analysts(analysts: list[str] | None, asset_type: str) -> tuple[str, ...]:
    selected = list(dict.fromkeys(analysts or list(DEFAULT_ANALYSTS)))
    unknown = [item for item in selected if item not in ALLOWED_ANALYSTS]
    if unknown:
        raise ValueError(f"unsupported analysts: {', '.join(unknown)}")
    if not selected:
        raise ValueError("analysts must be a non-empty subset of market, social, news, fundamentals")
    if asset_type == "crypto":
        selected = [item for item in selected if item != "fundamentals"]
    if not selected:
        raise ValueError("crypto analysis requires at least one non-fundamentals analyst")
    return tuple(selected)


def _ohlcv_records(
    symbol: str, *, bar_count: int, as_of: str | None = None
) -> list[dict[str, Any]]:
    end = datetime.strptime(as_of, "%Y-%m-%d").date() if as_of else date.today()
    start = end - timedelta(days=max(bar_count * 2, 14))
    frame = get_ohlcv(symbol, start.isoformat(), end.isoformat())
    trimmed = frame.tail(bar_count).copy()
    records = []
    for row in trimmed.to_dict(orient="records"):
        item = {}
        for key, value in row.items():
            if hasattr(value, "isoformat"):
                item[str(key)] = value.isoformat()
            elif hasattr(value, "item"):
                item[str(key)] = value.item()
            else:
                item[str(key)] = value
        records.append(item)
    return records
