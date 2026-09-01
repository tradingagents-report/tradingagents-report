"""Local run store: files for one report, SQLite catalog for lookup."""

from __future__ import annotations

import json

from tradingagents.run_store import (
    begin_run,
    get_run,
    list_runs,
    persist_completed_run,
    request_cancel,
    update_run_progress,
)


def _state(**overrides):
    state = {
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
    state.update(overrides)
    return state


def _config(tmp_path):
    store = tmp_path / "runs"
    return {
        "run_store_enabled": True,
        "run_store_dir": str(store),
        "llm_provider": "openai",
        "deep_think_llm": "gpt-5.5",
        "quick_think_llm": "gpt-5.4-mini",
        "output_language": "English",
    }


def test_persist_writes_files_and_index(tmp_path):
    config = _config(tmp_path)
    state = _state()
    snapshot = {"company_of_interest": "AAPL", "decision_brief": state["decision_brief"]}
    persisted = persist_completed_run(
        config=config,
        ticker="NASDAQ:AAPL",
        trade_date="2026-08-01",
        final_state=state,
        state_snapshot=snapshot,
        analysts=("market", "news"),
    )
    assert persisted is not None
    directory = persisted.directory
    assert (directory / "complete_report.md").exists()
    assert (directory / "1_analysts" / "market.md").read_text() == "MKT"
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_id"] == persisted.run_id
    assert manifest["ticker"] == "NASDAQ:AAPL"
    assert manifest["status"] == "succeeded"
    assert manifest["rating"] == "Overweight"
    assert manifest["analysts"] == ["market", "news"]
    decision = json.loads((directory / "decision.json").read_text(encoding="utf-8"))
    assert decision["rating"] == "Overweight"
    snapshot_on_disk = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    assert snapshot_on_disk["company_of_interest"] == "AAPL"
    assert (tmp_path / "runs.sqlite").exists()
    row = get_run(config, persisted.run_id)
    assert row is not None
    assert row["ticker"] == "NASDAQ:AAPL"
    assert row["directory"] == str(directory)
    listed = list_runs(config, ticker="NASDAQ:AAPL")
    assert [item["run_id"] for item in listed] == [persisted.run_id]


def test_persist_skips_when_disabled(tmp_path):
    config = _config(tmp_path)
    config["run_store_enabled"] = False
    persisted = persist_completed_run(
        config=config,
        ticker="AAPL",
        trade_date="2026-08-01",
        final_state=_state(),
        state_snapshot={},
    )
    assert persisted is None
    assert not (tmp_path / "runs").exists()
    assert list_runs(config) == []


def test_persist_skips_without_store_dir(tmp_path):
    persisted = persist_completed_run(
        config={"run_store_enabled": True, "results_dir": str(tmp_path)},
        ticker="AAPL",
        trade_date="2026-08-01",
        final_state=_state(),
        state_snapshot={},
    )
    assert persisted is None


def test_persist_skips_when_flag_absent(tmp_path):
    persisted = persist_completed_run(
        config={"run_store_dir": str(tmp_path / "runs")},
        ticker="AAPL",
        trade_date="2026-08-01",
        final_state=_state(),
        state_snapshot={},
    )
    assert persisted is None
    assert list(tmp_path.iterdir()) == []


def test_list_runs_filters_by_ticker(tmp_path):
    config = _config(tmp_path)
    persist_completed_run(
        config=config,
        ticker="AAPL",
        trade_date="2026-08-01",
        final_state=_state(),
        state_snapshot={},
    )
    persist_completed_run(
        config=config,
        ticker="MSFT",
        trade_date="2026-08-01",
        final_state=_state(),
        state_snapshot={},
    )
    apple = list_runs(config, ticker="AAPL")
    assert len(apple) == 1
    assert apple[0]["ticker"] == "AAPL"
    assert len(list_runs(config)) == 2


def test_get_run_rejects_path_like_ids(tmp_path):
    config = _config(tmp_path)
    assert get_run(config, "../etc/passwd") is None
    assert get_run(config, "abc/def") is None


def test_propagate_persists_into_run_store(tmp_path):
    import functools
    from unittest.mock import MagicMock

    from tradingagents.graph.trading_graph import TradingAgentsGraph

    fake_state = _state()
    mock_graph = MagicMock()
    mock_graph.memory_log = MagicMock()
    mock_graph.log_states_dict = {}
    mock_graph.debug = False
    mock_graph.config = _config(tmp_path)
    mock_graph.config["results_dir"] = str(tmp_path / "logs")
    mock_graph.graph.stream.return_value = [fake_state]
    mock_graph.propagator.create_initial_state.return_value = fake_state
    mock_graph.propagator.get_graph_args.return_value = {}
    mock_graph.signal_processor.process_signal.return_value = "Overweight"
    mock_graph.selected_analysts = ("market",)
    mock_graph._run_graph = functools.partial(TradingAgentsGraph._run_graph, mock_graph)
    TradingAgentsGraph.propagate(mock_graph, "AAPL", "2026-08-01")
    persisted = mock_graph.last_run
    assert persisted is not None
    assert (persisted.directory / "decision.json").exists()
    assert get_run(mock_graph.config, persisted.run_id)["ticker"] == "AAPL"


def test_log_state_skips_files_when_run_store_disabled(tmp_path):
    import functools
    from unittest.mock import MagicMock

    from tradingagents.graph.trading_graph import TradingAgentsGraph

    fake_state = _state()
    mock_graph = MagicMock()
    mock_graph.memory_log = MagicMock()
    mock_graph.log_states_dict = {}
    mock_graph.debug = False
    mock_graph.config = {
        "run_store_enabled": False,
        "run_store_dir": str(tmp_path / "runs"),
        "results_dir": str(tmp_path / "logs"),
    }
    mock_graph.graph.stream.return_value = [fake_state]
    mock_graph.propagator.create_initial_state.return_value = fake_state
    mock_graph.propagator.get_graph_args.return_value = {}
    mock_graph.signal_processor.process_signal.return_value = "Overweight"
    mock_graph.selected_analysts = ("market",)
    mock_graph._run_graph = functools.partial(TradingAgentsGraph._run_graph, mock_graph)
    TradingAgentsGraph.propagate(mock_graph, "NASDAQ:AAPL", "2026-08-01")
    assert mock_graph.last_run is None
    assert not (tmp_path / "runs").exists()
    assert not (tmp_path / "logs").exists()


def test_begin_run_then_persist_reuses_id(tmp_path):
    config = _config(tmp_path)
    started = begin_run(
        config=config,
        ticker="AAPL",
        trade_date="2026-08-01",
        analysts=("market",),
    )
    assert started is not None
    assert get_run(config, started.run_id)["status"] == "running"
    persisted = persist_completed_run(
        config=config,
        ticker="AAPL",
        trade_date="2026-08-01",
        final_state=_state(),
        state_snapshot=_state(),
        analysts=("market",),
        run_id=started.run_id,
    )
    assert persisted is not None
    assert persisted.run_id == started.run_id
    row = get_run(config, started.run_id)
    assert row["status"] == "succeeded"
    assert row["created_at"] == started.manifest["created_at"]
    assert list_runs(config, status="succeeded")[0]["run_id"] == started.run_id


def test_request_cancel_running_sets_flag(tmp_path):
    config = _config(tmp_path)
    started = begin_run(config=config, ticker="AAPL", trade_date="2026-08-01")
    result = request_cancel(config, started.run_id)
    assert result["status"] == "cancel_requested"
    assert get_run(config, started.run_id)["cancel_requested"] == 1


def test_update_run_progress_writes_events(tmp_path):
    config = _config(tmp_path)
    started = begin_run(config=config, ticker="AAPL", trade_date="2026-08-01")
    update_run_progress(config, started.run_id, progress_percent=40, current_step="Researching")
    row = get_run(config, started.run_id)
    assert row["progress_percent"] == 40
    assert row["current_step"] == "Researching"
    from tradingagents.run_store import list_run_events

    events = list_run_events(config, started.run_id)
    assert events[0]["message"] == "Researching"
