"""Local desk backend: file-backed jobs shared by stdio MCP and local HTTP."""

from __future__ import annotations

import threading
from unittest.mock import patch

import pandas as pd
import pytest

from application import local_desk
from application.analysis import AnalysisEvent, AnalysisResult


def _config(tmp_path):
    return {
        "run_store_enabled": True,
        "run_store_dir": str(tmp_path / "runs"),
        "llm_provider": "openai",
        "deep_think_llm": "gpt-5.5",
        "quick_think_llm": "gpt-5.4-mini",
        "output_language": "English",
        "results_dir": str(tmp_path / "logs"),
    }


def _state():
    return {
        "company_of_interest": "AAPL",
        "trade_date": "2026-08-01",
        "market_report": "MKT",
        "sentiment_report": "",
        "news_report": "NEWS",
        "fundamentals_report": "",
        "investment_debate_state": {
            "bull_history": "",
            "bear_history": "",
            "history": "",
            "current_response": "",
            "latest_speaker": "",
            "judge_decision": "RM PLAN",
        },
        "investment_plan": "PLAN",
        "trader_investment_plan": "TRADE",
        "risk_debate_state": {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "history": "",
            "judge_decision": "Rating: Overweight",
        },
        "final_trade_decision": "Rating: Overweight\nHold the name.",
        "decision_brief": {"rating": "Overweight", "confidence": "medium"},
    }


def _join_local_threads():
    for thread in threading.enumerate():
        if thread.name.startswith(local_desk.THREAD_PREFIX) and thread is not threading.current_thread():
            thread.join(timeout=5)


def test_resolve_listing_tool():
    listing = local_desk.resolve_listing_tool("0700.HK")
    assert listing["exchange"] == "HKEX"
    assert listing["symbol"] == "700"
    assert listing["display_ticker"] == "0700.HK"
    assert listing["provider_symbol"] == "HKEX:700"


def test_start_analysis_completes_into_run_store(tmp_path):
    config = _config(tmp_path)
    state = _state()

    def fake_run_analysis(command, *, callbacks=(), on_event=None):
        del callbacks
        if on_event is not None:
            on_event(AnalysisEvent(10, "Running Market Analyst"))
        return AnalysisResult(final_state=state, decision="Overweight", run_id=None)

    with patch("application.local_desk.run_analysis", fake_run_analysis):
        created = local_desk.start_analysis(
            ticker="AAPL",
            trade_date="2026-08-01",
            analysts=["market", "news"],
            config=config,
        )
        _join_local_threads()

    assert created["status"] == "running"
    status = local_desk.get_analysis(created["id"], config=config)
    assert status["status"] == "succeeded"
    assert status["progress_percent"] == 100
    events = local_desk.get_analysis_events(created["id"], config=config)
    assert events[0]["message"] == "Running Market Analyst"
    report = local_desk.get_analysis_report(created["id"], config=config)
    assert report["decision_brief"]["rating"] == "Overweight"
    assert report["reports"]["market_report"] == "MKT"
    listed = local_desk.list_analyses(ticker="AAPL", config=config)
    assert listed[0]["id"] == created["id"]


def test_cancel_running_analysis(tmp_path):
    config = _config(tmp_path)
    gate = threading.Event()
    progressed = threading.Event()

    def fake_run_analysis(command, *, callbacks=(), on_event=None):
        del command, callbacks
        if on_event is not None:
            on_event(AnalysisEvent(10, "Running Market Analyst"))
        progressed.set()
        gate.wait(timeout=5)
        if on_event is not None:
            on_event(AnalysisEvent(50, "Should cancel"))
        return AnalysisResult(final_state=_state(), decision="Hold", run_id=None)

    with patch("application.local_desk.run_analysis", fake_run_analysis):
        created = local_desk.start_analysis(
            ticker="AAPL",
            trade_date="2026-08-01",
            analysts=["market"],
            config=config,
        )
        assert progressed.wait(timeout=5)
        cancelled = local_desk.cancel_analysis(created["id"], config=config)
        assert cancelled["status"] == "cancel_requested"
        gate.set()
        _join_local_threads()

    status = local_desk.get_analysis(created["id"], config=config)
    assert status["status"] == "cancelled"


def test_get_analysis_report_rejects_incomplete(tmp_path):
    config = _config(tmp_path)
    from tradingagents.run_store import begin_run

    started = begin_run(config=config, ticker="AAPL", trade_date="2026-08-01")
    with pytest.raises(ValueError, match="succeeded"):
        local_desk.get_analysis_report(started.run_id, config=config)


def test_get_ohlcv_rejects_intraday():
    with pytest.raises(ValueError, match="daily"):
        local_desk.get_ohlcv_tool("AAPL", timeframe="15")


def test_get_quote_uses_ohlcv_tail(tmp_path):
    del tmp_path
    frame = pd.DataFrame(
        [
            {"Date": "2026-08-01", "Close": 100.0},
            {"Date": "2026-08-03", "Close": 110.0},
        ]
    )
    with patch("application.local_desk.get_ohlcv", return_value=frame):
        quote = local_desk.get_quote("AAPL")
    assert quote["quote"]["Close"] == 110.0
