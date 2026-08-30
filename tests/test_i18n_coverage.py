"""Every report-producing agent must apply the configured output language
(#740/#801).

A run should produce a fully single-language report, not a mix of languages.
English used to omit the instruction (token savings); that let Chinese-market
context drift agents into Chinese. Every report agent must call
``get_language_instruction()``, which now always emits a directive.
"""
from pathlib import Path

import pytest

from tradingagents.agents.utils.agent_utils import get_language_instruction

_AGENTS_DIR = Path(__file__).resolve().parents[1] / "tradingagents" / "agents"

# Every node whose text reaches the saved report. If you add a report-producing
# agent, add it here — and make it call get_language_instruction().
REPORT_AGENTS = [
    "analysts/market_analyst.py",
    "analysts/news_analyst.py",
    "analysts/fundamentals_analyst.py",
    "analysts/sentiment_analyst.py",
    "researchers/bull_researcher.py",
    "researchers/bear_researcher.py",
    "managers/research_manager.py",
    "managers/portfolio_manager.py",
    "risk_mgmt/aggressive_debator.py",
    "risk_mgmt/conservative_debator.py",
    "risk_mgmt/neutral_debator.py",
    "trader/trader.py",
]

# UI reading-order chapters → producing agent. Keep in sync with
# the hosted desk report-flow order so a missing language hook can't hide.
REPORT_CHAPTER_AGENTS = {
    "market_report": "analysts/market_analyst.py",
    "sentiment_report": "analysts/sentiment_analyst.py",
    "news_report": "analysts/news_analyst.py",
    "fundamentals_report": "analysts/fundamentals_analyst.py",
    "bull_researcher": "researchers/bull_researcher.py",
    "bear_researcher": "researchers/bear_researcher.py",
    "research_team_decision": "managers/research_manager.py",
    "trader_investment_plan": "trader/trader.py",
    "risky_analyst": "risk_mgmt/aggressive_debator.py",
    "safe_analyst": "risk_mgmt/conservative_debator.py",
    "neutral_analyst": "risk_mgmt/neutral_debator.py",
    "final_trade_decision": "managers/portfolio_manager.py",
}


@pytest.mark.unit
class TestLanguageInstruction:
    def test_english_emits_directive(self):
        from tradingagents.dataflows.config import set_config
        set_config({"output_language": "English"})
        out = get_language_instruction()
        assert "CRITICAL LANGUAGE RULE" in out
        assert "entire response in English" in out
        assert "Do not switch languages" in out
        assert "prior agent or debate messages" in out

    def test_non_english_emits_directive(self):
        from tradingagents.dataflows.config import set_config
        set_config({"output_language": "中文"})
        out = get_language_instruction()
        assert "中文" in out
        assert "entire response" in out
        assert "CRITICAL LANGUAGE RULE" in out
        assert "TRANSACTION PROPOSAL" in out


@pytest.mark.unit
@pytest.mark.parametrize("rel", REPORT_AGENTS)
def test_report_agent_applies_language_instruction(rel):
    path = _AGENTS_DIR / rel
    assert path.exists(), f"missing agent module: {rel}"
    src = path.read_text(encoding="utf-8")
    assert "get_language_instruction()" in src, (
        f"{rel} does not apply get_language_instruction(); its output would "
        f"ignore the configured output_language (#740/#801)."
    )


@pytest.mark.unit
@pytest.mark.parametrize("chapter,rel", sorted(REPORT_CHAPTER_AGENTS.items()))
def test_ui_report_chapters_have_language_coverage(chapter, rel):
    assert rel in REPORT_AGENTS, (
        f"UI chapter {chapter!r} maps to {rel} which is missing from REPORT_AGENTS"
    )


@pytest.mark.unit
def test_structured_prose_fields_require_output_language():
    """Research/trader/PM schema descriptions travel separately from the prompt."""
    from tradingagents.agents.schemas import (
        DecisionBriefDraft,
        PortfolioDecision,
        ResearchPlan,
        SentimentReport,
        TraderProposal,
        _PROSE_LANGUAGE_RULE,
    )

    prose_models = (
        ResearchPlan,
        TraderProposal,
        PortfolioDecision,
        DecisionBriefDraft,
        SentimentReport,
    )
    found = 0
    for model in prose_models:
        for name, field in model.model_fields.items():
            desc = field.description or ""
            if name in {
                "rationale",
                "strategic_actions",
                "reasoning",
                "position_sizing",
                "executive_summary",
                "investment_thesis",
                "time_horizon",
                "headline",
                "position_guidance",
                "bull_case",
                "bear_case",
                "key_risk",
                "what_to_watch",
                "invalidation",
                "conflict_note",
                "narrative",
            }:
                assert _PROSE_LANGUAGE_RULE in desc, (
                    f"{model.__name__}.{name} missing prose language rule"
                )
                found += 1
    assert found >= 12
