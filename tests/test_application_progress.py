from application.progress import ProgressEventProjector, estimate_progress


def test_progress_moves_from_analysts_to_bull_researcher():
    state = {"market_report": "done", "news_report": "done"}
    progress, message = estimate_progress(
        state,
        analysts=("market", "news"),
        config={"max_debate_rounds": 1, "max_risk_discuss_rounds": 1},
    )
    assert progress == 50
    assert message == "Running Bull Researcher"


def test_progress_alternates_bear_after_bull_turn():
    state = {
        "market_report": "done",
        "investment_debate_state": {"count": 1, "latest_speaker": "Bull"},
    }
    progress, message = estimate_progress(
        state,
        analysts=("market",),
        config={"max_debate_rounds": 1, "max_risk_discuss_rounds": 1},
    )
    assert progress == 55
    assert message == "Running Bear Researcher"


def test_progress_shows_research_manager_after_debate_rounds():
    state = {
        "market_report": "done",
        "investment_debate_state": {"count": 2, "latest_speaker": "Bear"},
    }
    assert estimate_progress(
        state,
        analysts=("market",),
        config={"max_debate_rounds": 1, "max_risk_discuss_rounds": 1},
    ) == (62, "Running Research Manager")


def test_progress_shows_aggressive_then_conservative_risk_analysts():
    base = {
        "market_report": "done",
        "investment_debate_state": {"judge_decision": "research"},
        "trader_investment_plan": "plan",
    }
    assert estimate_progress(
        {**base, "risk_debate_state": {"count": 0}},
        analysts=("market",),
        config={"max_debate_rounds": 1, "max_risk_discuss_rounds": 1},
    ) == (72, "Running Aggressive Analyst")

    assert estimate_progress(
        {
            **base,
            "risk_debate_state": {"count": 1, "latest_speaker": "Aggressive"},
        },
        analysts=("market",),
        config={"max_debate_rounds": 1, "max_risk_discuss_rounds": 1},
    )[1] == "Running Conservative Analyst"


def test_progress_shows_portfolio_manager_while_running():
    state = {
        "market_report": "done",
        "investment_debate_state": {"judge_decision": "research"},
        "trader_investment_plan": "plan",
        "risk_debate_state": {"count": 3, "judge_decision": ""},
    }
    assert estimate_progress(
        state,
        analysts=("market",),
        config={"max_debate_rounds": 1, "max_risk_discuss_rounds": 1},
    ) == (90, "Running Portfolio Manager")


def test_progress_finishes_at_portfolio_manager():
    state = {
        "market_report": "done",
        "investment_debate_state": {"judge_decision": "research"},
        "trader_investment_plan": "plan",
        "risk_debate_state": {"judge_decision": "risk"},
    }
    assert estimate_progress(
        state,
        analysts=("market",),
        config={"max_debate_rounds": 1, "max_risk_discuss_rounds": 1},
    ) == (92, "Portfolio Manager completed")


def test_progress_projects_diagnostic_warnings_once():
    state = {
        "market_report": "done",
        "investment_debate_state": {"judge_decision": "research"},
        "trader_investment_plan": "plan",
        "risk_debate_state": {"judge_decision": "risk"},
        "diagnostic_events": [
            {
                "kind": "warning",
                "message": "Decision brief unavailable after free-text recovery.",
            }
        ],
    }
    projector = ProgressEventProjector(
        analysts=("market",),
        config={"max_debate_rounds": 1, "max_risk_discuss_rounds": 1},
    )

    first = projector.consume(state, state)
    second = projector.consume(state, state)

    assert [(event.kind, event.message) for event in first] == [
        ("warning", "Decision brief unavailable after free-text recovery."),
        ("stage", "Portfolio Manager completed"),
    ]
    assert second == []
