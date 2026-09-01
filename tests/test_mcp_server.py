"""stdio MCP adapter wiring."""

from __future__ import annotations

import pytest

pytest.importorskip("mcp")

from mcp_server.server import mcp


def test_mcp_exposes_research_and_market_tools():
    names = {tool.name for tool in mcp._tool_manager.list_tools()}
    assert names >= {
        "resolve_listing",
        "start_analysis",
        "get_analysis",
        "get_analysis_events",
        "get_analysis_report",
        "list_analyses",
        "cancel_analysis",
        "get_quote",
        "get_ohlcv",
        "get_ta_summary",
        "get_news",
        "get_fundamentals",
    }
