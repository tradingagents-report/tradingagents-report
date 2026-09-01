"""Thin FastAPI adapter for the self-hosted research engine."""

from __future__ import annotations

from typing import Annotated, Any, NoReturn

from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field

from application import local_desk

app = FastAPI(
    title="TradingAgents Report (local)",
    version="0.3.1",
    description=(
        "Self-hosted research HTTP API. Uses the local run store "
        "(~/.tradingagents/runs). Not the hosted PostgreSQL job service, "
        "and not live brokerage."
    ),
)


class StartAnalysisRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    trade_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    analysts: list[str] | None = None
    instrument_exchange: str | None = Field(default=None, max_length=16)
    instrument_symbol: str | None = Field(default=None, max_length=32)
    display_ticker: str | None = Field(default=None, max_length=32)
    output_language: str | None = Field(default=None, max_length=64)


def desk_config() -> dict[str, Any]:
    return local_desk.store_config()


DeskConfig = Annotated[dict[str, Any], Depends(desk_config)]


def _raise_desk_error(exc: ValueError) -> NoReturn:
    message = str(exc)
    if "not found" in message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message) from exc
    if "unavailable until" in message:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message) from exc
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message) from exc


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "store": "local"}


@app.get("/api/v1/listings/resolve")
def resolve_listing_endpoint(ticker: str = Query(min_length=1, max_length=32)) -> dict[str, Any]:
    try:
        return local_desk.resolve_listing_tool(ticker)
    except ValueError as exc:
        _raise_desk_error(exc)


@app.post("/api/v1/analyses", status_code=status.HTTP_202_ACCEPTED)
def start_analysis_endpoint(
    body: StartAnalysisRequest,
    config: DeskConfig,
) -> dict[str, Any]:
    try:
        return local_desk.start_analysis(
            ticker=body.ticker,
            trade_date=body.trade_date,
            analysts=body.analysts,
            instrument_exchange=body.instrument_exchange,
            instrument_symbol=body.instrument_symbol,
            display_ticker=body.display_ticker,
            output_language=body.output_language,
            config=config,
        )
    except ValueError as exc:
        _raise_desk_error(exc)


@app.get("/api/v1/analyses")
def list_analyses_endpoint(
    config: DeskConfig,
    ticker: str | None = Query(default=None, max_length=32),
    job_status: str | None = Query(default=None, alias="status", max_length=32),
    limit: int | None = Query(default=None, ge=1, le=100),
) -> dict[str, Any]:
    return {
        "analyses": local_desk.list_analyses(
            ticker=ticker, status=job_status, limit=limit, config=config
        )
    }


@app.get("/api/v1/analyses/{analysis_id}")
def get_analysis_endpoint(
    analysis_id: str,
    config: DeskConfig,
) -> dict[str, Any]:
    try:
        return local_desk.get_analysis(analysis_id, config=config)
    except ValueError as exc:
        _raise_desk_error(exc)


@app.get("/api/v1/analyses/{analysis_id}/events")
def get_analysis_events_endpoint(
    analysis_id: str,
    config: DeskConfig,
) -> dict[str, Any]:
    try:
        return {"events": local_desk.get_analysis_events(analysis_id, config=config)}
    except ValueError as exc:
        _raise_desk_error(exc)


@app.get("/api/v1/analyses/{analysis_id}/report")
def get_analysis_report_endpoint(
    analysis_id: str,
    config: DeskConfig,
) -> dict[str, Any]:
    try:
        return local_desk.get_analysis_report(analysis_id, config=config)
    except ValueError as exc:
        _raise_desk_error(exc)


@app.post("/api/v1/analyses/{analysis_id}/cancel")
def cancel_analysis_endpoint(
    analysis_id: str,
    config: DeskConfig,
) -> dict[str, Any]:
    try:
        return local_desk.cancel_analysis(analysis_id, config=config)
    except ValueError as exc:
        _raise_desk_error(exc)


@app.get("/api/v1/quote")
def get_quote_endpoint(symbol: str = Query(min_length=1, max_length=32)) -> dict[str, Any]:
    try:
        return local_desk.get_quote(symbol)
    except ValueError as exc:
        _raise_desk_error(exc)


@app.get("/api/v1/ohlcv")
def get_ohlcv_endpoint(
    symbol: str = Query(min_length=1, max_length=32),
    timeframe: str | None = Query(default=None, max_length=8),
    bar_count: int | None = Query(default=None, ge=2, le=400),
    as_of: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
) -> dict[str, Any]:
    try:
        return local_desk.get_ohlcv_tool(
            symbol, timeframe=timeframe, bar_count=bar_count, as_of=as_of
        )
    except ValueError as exc:
        _raise_desk_error(exc)


@app.get("/api/v1/ta-summary")
def get_ta_summary_endpoint(symbol: str = Query(min_length=1, max_length=32)) -> dict[str, Any]:
    try:
        return local_desk.get_ta_summary(symbol)
    except ValueError as exc:
        _raise_desk_error(exc)


@app.get("/api/v1/news")
def get_news_endpoint(
    symbol: str = Query(min_length=1, max_length=32),
    lang: str | None = Query(default=None, max_length=8),
) -> dict[str, Any]:
    try:
        return local_desk.get_news(symbol, lang=lang)
    except ValueError as exc:
        _raise_desk_error(exc)


@app.get("/api/v1/fundamentals")
def get_fundamentals_endpoint(ticker: str = Query(min_length=1, max_length=32)) -> dict[str, Any]:
    try:
        return local_desk.get_fundamentals(ticker)
    except ValueError as exc:
        _raise_desk_error(exc)
