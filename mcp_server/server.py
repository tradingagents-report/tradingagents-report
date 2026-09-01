"""stdio MCP server for the self-hosted research engine."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from application import local_desk

MCP_SERVER_NAME = "tradingagents-report"
MCP_SERVER_VERSION = "1.0.0"
MCP_INSTRUCTIONS = (
    "Self-hosted TradingAgents Report research engine. Not live brokerage. "
    "Research: resolve_listing, start_analysis, poll get_analysis, then "
    "get_analysis_report. Market: get_quote, get_ohlcv, get_ta_summary, "
    "get_news, get_fundamentals. Analysis runs locally and writes "
    "~/.tradingagents/runs/{id}/. The hosted desk at "
    "https://mcp.tradingagentsreport.com/mcp is a separate OAuth service."
)

mcp = FastMCP(
    MCP_SERVER_NAME,
    instructions=MCP_INSTRUCTIONS,
)


@mcp.tool()
def resolve_listing(ticker: str) -> dict[str, Any]:
    """Normalize a ticker or exchange:symbol into listing identity (exchange, symbol, display_ticker, provider_symbol)."""
    return local_desk.resolve_listing_tool(ticker)


@mcp.tool()
def start_analysis(
    ticker: str,
    trade_date: str,
    analysts: list[str] | None = None,
    instrument_exchange: str | None = None,
    instrument_symbol: str | None = None,
    display_ticker: str | None = None,
    output_language: str | None = None,
) -> dict[str, Any]:
    """Submit an asynchronous research job and return its id immediately. Poll get_analysis until status is succeeded, then call get_analysis_report. trade_date is YYYY-MM-DD. analysts is a non-empty subset of market, social, news, fundamentals."""
    return local_desk.start_analysis(
        ticker=ticker,
        trade_date=trade_date,
        analysts=analysts,
        instrument_exchange=instrument_exchange,
        instrument_symbol=instrument_symbol,
        display_ticker=display_ticker,
        output_language=output_language,
    )


@mcp.tool()
def get_analysis(analysis_id: str) -> dict[str, Any]:
    """Fetch job status and progress for an analysis id from start_analysis. Does not include the full report; use get_analysis_report when succeeded."""
    return local_desk.get_analysis(analysis_id)


@mcp.tool()
def get_analysis_events(analysis_id: str) -> dict[str, Any]:
    """Stage timeline for an analysis job (progress messages)."""
    return {"events": local_desk.get_analysis_events(analysis_id)}


@mcp.tool()
def get_analysis_report(analysis_id: str) -> dict[str, Any]:
    """Return the decision card and report sections after the job succeeded. Call get_analysis first; this payload is large."""
    return local_desk.get_analysis_report(analysis_id)


@mcp.tool()
def list_analyses(
    ticker: str | None = None,
    status: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """List recent local analysis runs from ~/.tradingagents/runs.sqlite."""
    return {"analyses": local_desk.list_analyses(ticker=ticker, status=status, limit=limit)}


@mcp.tool()
def cancel_analysis(analysis_id: str) -> dict[str, Any]:
    """Request cancellation of a running local analysis job."""
    return local_desk.cancel_analysis(analysis_id)


@mcp.tool()
def get_quote(symbol: str) -> dict[str, Any]:
    """Latest daily quote for an EXCHANGE:SYMBOL or Yahoo-style ticker (e.g. NASDAQ:AAPL)."""
    return local_desk.get_quote(symbol)


@mcp.tool()
def get_ohlcv(
    symbol: str,
    timeframe: str | None = None,
    bar_count: int | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Daily OHLCV bars. timeframe must be D. bar_count defaults to 120."""
    return local_desk.get_ohlcv_tool(
        symbol, timeframe=timeframe, bar_count=bar_count, as_of=as_of
    )


@mcp.tool()
def get_ta_summary(symbol: str) -> dict[str, Any]:
    """Multi-timeframe TradingView Buy/Sell/Neutral gauges when that vendor is configured."""
    return local_desk.get_ta_summary(symbol)


@mcp.tool()
def get_news(symbol: str, lang: str | None = None) -> dict[str, Any]:
    """Recent news for a ticker over the last 7 days."""
    return local_desk.get_news(symbol, lang=lang)


@mcp.tool()
def get_fundamentals(ticker: str) -> dict[str, Any]:
    """Company identity (name, exchange). Full statements live on completed analysis reports."""
    return local_desk.get_fundamentals(ticker)


def run() -> None:
    mcp.run(transport="stdio")
