"""Tests for structured-output agents (Trader, Research Manager, Sentiment Analyst).

The Portfolio Manager has its own coverage in tests/test_memory_log.py
(which exercises the full memory-log → PM injection cycle).  This file
covers the parallel schemas, render functions, and graceful-fallback
behavior we added for the Trader, Research Manager, and Sentiment Analyst
so they share the same deterministic output shape.
"""

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from tradingagents.agents.analysts.sentiment_analyst import create_sentiment_analyst
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.schemas import (
    DecisionBriefDraft,
    DecisionConviction,
    DecisionStance,
    PortfolioDecision,
    PortfolioDecisionRecovery,
    PortfolioRating,
    PriceRange,
    ResearchPlan,
    SectionSignal,
    SectionStances,
    SentimentBand,
    SentimentReport,
    TraderAction,
    TraderProposal,
    render_research_plan,
    render_sentiment_report,
    render_trader_proposal,
)
from tradingagents.agents.trader.trader import create_trader
from tradingagents.agents.utils.decision_brief_recovery import (
    extract_decision_brief_from_text,
    salvage_decision_brief_from_text,
)
from tradingagents.agents.utils.section_signal import extract_section_signal

# ---------------------------------------------------------------------------
# Render functions
# ---------------------------------------------------------------------------


def _decision_brief() -> DecisionBriefDraft:
    return DecisionBriefDraft(
        headline="Wait for trend confirmation.",
        conviction=DecisionConviction.MEDIUM,
        position_guidance="Keep exposure below 4%.",
        entry_zone=PriceRange(low=180, high=185),
        add_levels=[PriceRange(low=190, high=192)],
        stop_or_reduce=175,
        bull_case="Earnings growth remains durable.",
        bear_case="Cash returns remain unproven.",
        key_risk="Capital spending stays elevated.",
        what_to_watch=["Free cash flow recovery", "A close above the 50-day average"],
        invalidation="Reduce exposure if earnings estimates fall.",
        conflict_note="Fundamentals are resilient while the daily trend remains weak.",
    )


@pytest.mark.unit
class TestRenderTraderProposal:
    def test_minimal_required_fields(self):
        p = TraderProposal(action=TraderAction.HOLD, reasoning="Balanced setup; no edge.")
        md = render_trader_proposal(p)
        assert "**Action**: Hold" in md
        assert "**Reasoning**: Balanced setup; no edge." in md
        # Trailing TRANSACTION PROPOSAL line is the Trader deliverable chrome.
        assert "TRANSACTION PROPOSAL: **HOLD**" in md

    def test_optional_fields_included_when_present(self):
        p = TraderProposal(
            action=TraderAction.BUY,
            reasoning="Strong technicals + fundamentals.",
            entry_price=189.5,
            stop_loss=178.0,
            position_sizing="6% of portfolio",
        )
        md = render_trader_proposal(p)
        assert "**Action**: Buy" in md
        assert "**Entry Price**: 189.5" in md
        assert "**Stop Loss**: 178.0" in md
        assert "**Position Sizing**: 6% of portfolio" in md
        assert "TRANSACTION PROPOSAL: **BUY**" in md

    def test_optional_fields_omitted_when_absent(self):
        p = TraderProposal(action=TraderAction.SELL, reasoning="Guidance cut.")
        md = render_trader_proposal(p)
        assert "Entry Price" not in md
        assert "Stop Loss" not in md
        assert "Position Sizing" not in md
        assert "TRANSACTION PROPOSAL: **SELL**" in md


@pytest.mark.unit
class TestNullishFloatCoercion:
    """A weak LLM may write "None"/"N/A" into an optional float field (#1058);
    coerce those to None so the structured call validates instead of erroring."""

    def test_trader_nullish_strings_coerce_to_none(self):
        for sentinel in ("None", "N/A", "null", "-", "", "TBD"):
            p = TraderProposal(
                action=TraderAction.HOLD,
                reasoning="x",
                entry_price=sentinel,
                stop_loss=sentinel,
            )
            assert p.entry_price is None
            assert p.stop_loss is None

    def test_trader_real_numeric_string_still_parses(self):
        p = TraderProposal(action=TraderAction.BUY, reasoning="x", entry_price="189.5")
        assert p.entry_price == 189.5

    @pytest.mark.parametrize("price_target", [None, "N/A", 0, -1])
    def test_pm_requires_positive_price_target(self, price_target):
        with pytest.raises(ValidationError, match="price_target"):
            PortfolioDecision(
                rating=PortfolioRating.OVERWEIGHT,
                executive_summary="s",
                investment_thesis="t",
                price_target=price_target,
                brief=_decision_brief(),
            )

    def test_pm_requires_price_target_field(self):
        with pytest.raises(ValidationError, match="price_target"):
            PortfolioDecision(
                rating=PortfolioRating.OVERWEIGHT,
                executive_summary="s",
                investment_thesis="t",
                brief=_decision_brief(),
            )

    def test_price_range_rejects_reversed_bounds(self):
        with pytest.raises(ValidationError, match="low must be less than or equal to high"):
            PriceRange(low=200, high=190)

    def test_section_stance_supports_unavailable(self):
        signal = SectionSignal(
            stance=DecisionStance.UNAVAILABLE,
            note="Fundamentals were not selected for this run.",
        )
        assert signal.stance is DecisionStance.UNAVAILABLE

    def test_decision_brief_rejects_whitespace_headline(self):
        with pytest.raises(ValidationError, match="headline"):
            DecisionBriefDraft(
                headline="   ",
                conviction=DecisionConviction.LOW,
                bull_case="Quality remains intact.",
                bear_case="Trend remains weak.",
                key_risk="Guidance risk.",
                what_to_watch=["Next earnings release"],
                invalidation="Exit if the thesis breaks.",
            )


@pytest.mark.unit
class TestLocalizedStructuredCoercion:
    def test_pm_accepts_localized_rating_and_conviction(self):
        decision = PortfolioDecision(
            rating="持有",
            executive_summary="s",
            investment_thesis="t",
            price_target=210.0,
            brief=DecisionBriefDraft(
                headline="Wait for confirmation.",
                conviction="中等",
                bull_case="Demand remains firm.",
                bear_case="Valuation is stretched.",
                key_risk="Guidance risk.",
                what_to_watch=["Next earnings release"],
                invalidation="Exit if the thesis breaks.",
            ),
        )
        assert decision.rating is PortfolioRating.HOLD
        assert decision.brief.conviction is DecisionConviction.MEDIUM

    def test_pm_trims_what_to_watch_instead_of_rejecting(self):
        brief = DecisionBriefDraft(
            headline="Wait for confirmation.",
            conviction=DecisionConviction.LOW,
            bull_case="Demand remains firm.",
            bear_case="Valuation is stretched.",
            key_risk="Guidance risk.",
            what_to_watch=["a", "b", "c", "d"],
            invalidation="Exit if the thesis breaks.",
        )
        assert brief.what_to_watch == ["a", "b", "c"]

    def test_pm_coerces_null_add_levels_instead_of_rejecting(self):
        decision = PortfolioDecision.model_validate(
            {
                "rating": "Hold",
                "executive_summary": "Wait for confirmation.",
                "investment_thesis": "Evidence is balanced.",
                "price_target": 493.0,
                "brief": {
                    "headline": "Hold near the mid-band.",
                    "conviction": "medium",
                    "bull_case": "Franchise quality remains intact.",
                    "bear_case": "Free cash flow is compressed.",
                    "key_risk": "Capital spending stays elevated.",
                    "what_to_watch": ["Next free-cash-flow print"],
                    "invalidation": "Reassess if price loses the mid-band.",
                    "add_levels": None,
                },
            }
        )
        assert decision.brief.add_levels == []

    def test_recovery_schema_trims_what_to_watch(self):
        recovery = PortfolioDecisionRecovery(
            what_to_watch=["a", "b", "c", "d"],
        )
        assert recovery.what_to_watch == ["a", "b", "c"]


@pytest.mark.unit
class TestAnalystSectionSignal:
    def test_extracts_typed_signal_from_completed_report(self):
        structured = MagicMock()
        structured.invoke.return_value = SectionSignal(
            stance=DecisionStance.BEARISH,
            note="Daily trend remains below key averages.",
        )

        signal = extract_section_signal(
            structured,
            "Price remains below the 50-day average.",
            "Market Analyst",
        )

        assert signal == {
            "stance": "bearish",
            "note": "Daily trend remains below key averages.",
        }

    def test_extraction_failure_is_unavailable_not_text_guessing(self):
        structured = MagicMock()
        structured.invoke.side_effect = ValueError("invalid structured result")

        signal = extract_section_signal(
            structured,
            "Strong bullish language that must not be regex-classified.",
            "News Analyst",
        )

        assert signal["stance"] == "unavailable"


def _section_stances() -> SectionStances:
    return SectionStances(
        market=SectionSignal(stance=DecisionStance.BEARISH, note="Trend is weak."),
        sentiment=SectionSignal(stance=DecisionStance.NEUTRAL, note="Mixed tone."),
        news=SectionSignal(stance=DecisionStance.BULLISH, note="Supportive headlines."),
        fundamentals=SectionSignal(
            stance=DecisionStance.UNAVAILABLE,
            note="Fundamentals Analyst did not produce a structured signal.",
        ),
    )


@pytest.mark.unit
class TestDecisionBriefRecovery:
    def test_extracts_narrative_but_keeps_authoritative_fields_from_text(self):
        recovery = PortfolioDecisionRecovery(
            bull_case="Balance sheet remains solid.",
            bear_case="Cash conversion is deteriorating.",
            key_risk="CapEx stays elevated.",
            what_to_watch=["Next FCF print"],
            invalidation="Re-add only after trend repair.",
        )
        structured = MagicMock()
        structured.invoke.return_value = recovery

        brief = extract_decision_brief_from_text(
            structured,
            "**Rating**: Underweight\n\n"
            "**Executive Summary**: Reduce exposure into strength.\n\n"
            "**Price Target**: 1,250.50\n\n"
            "Balance sheet remains solid, but cash conversion is deteriorating. "
            "CapEx stays elevated; watch the next FCF print.",
            _section_stances(),
        )

        assert brief is not None
        assert brief["rating"] == "Underweight"
        assert brief["headline"] == "Reduce exposure into strength."
        assert brief["target_price"] == 1250.5
        assert brief["conviction"] == "low"
        assert "Degraded brief" in brief["conflict_note"]
        assert brief["section_stances"]["market"]["stance"] == "bearish"

    def test_extract_ignores_authoritative_fields_in_recovery_payload(self):
        structured = MagicMock()
        structured.invoke.return_value = {
            "rating": "Buy",
            "price_target": 250.0,
            "headline": "Add aggressively.",
            "bull_case": "Quality remains intact.",
        }

        brief = extract_decision_brief_from_text(
            structured,
            "**Rating**: Sell\n\n"
            "**Executive Summary**: Exit now.\n\n"
            "**Price Target**: 150",
            _section_stances(),
        )

        assert brief is not None
        assert brief["rating"] == "Sell"
        assert brief["target_price"] == 150.0
        assert brief["headline"] == "Exit now."

    def test_extract_returns_none_without_explicit_rating(self):
        structured = MagicMock()

        assert (
            extract_decision_brief_from_text(
                structured,
                "The provider could not produce a final recommendation.",
                _section_stances(),
            )
            is None
        )
        structured.invoke.assert_not_called()

    def test_extract_returns_none_on_failure(self):
        structured = MagicMock()
        structured.invoke.side_effect = ValueError("bad recovery payload")

        assert (
            extract_decision_brief_from_text(
                structured,
                "**Rating**: Hold\n\nStay flat.",
                _section_stances(),
            )
            is None
        )

    def test_salvage_builds_degraded_brief_from_markdown(self):
        brief = salvage_decision_brief_from_text(
            "**Rating**: Buy\n\n"
            "**Executive Summary**: Add on dips toward support. Keep risk capped.\n\n"
            "**Price Target**: 210.5",
            _section_stances(),
        )

        assert brief["rating"] == "Buy"
        assert brief["headline"] == "Add on dips toward support."
        assert brief["target_price"] == 210.5
        assert brief["conviction"] == "low"
        assert "Degraded brief" in brief["conflict_note"]
        assert brief["bull_case"] == "See the detailed report."

    def test_salvage_skips_bold_rating_and_preserves_abbreviation(self):
        brief = salvage_decision_brief_from_text(
            "**Rating**: Sell\n\nU.S. demand remains weak. Exit on strength.",
            _section_stances(),
        )

        assert brief is not None
        assert brief["headline"] == "U.S. demand remains weak."

    def test_salvage_uses_only_unambiguous_top_level_rating(self):
        brief = salvage_decision_brief_from_text(
            "**Investment Thesis**: The analyst Rating: Buy is too optimistic.\n\n"
            "**Rating**: Sell\n\n"
            "**Executive Summary**: Exit ahead of guidance.",
            _section_stances(),
        )

        assert brief is not None
        assert brief["rating"] == "Sell"

    @pytest.mark.parametrize(
        "text",
        [
            "The provider could not produce a final recommendation.",
            "**Rating**: Buy\n**Rating**: Sell\nConflicting output.",
        ],
    )
    def test_salvage_rejects_missing_or_conflicting_rating(self, text):
        assert salvage_decision_brief_from_text(text, _section_stances()) is None

    def test_salvage_preserves_explicit_currency_for_later_validation(self):
        brief = salvage_decision_brief_from_text(
            "**Rating**: Hold\n\n"
            "**Executive Summary**: Wait.\n\n"
            "**Price Target**: $1,250.50",
            _section_stances(),
        )

        assert brief is not None
        assert brief["target_price"] == 1250.5
        assert brief["currency"] == "USD"

    def test_salvage_ignores_quoted_target_and_uses_top_level_field(self):
        brief = salvage_decision_brief_from_text(
            "**Rating**: Sell\n\n"
            "**Investment Thesis**: The analyst Price Target: 250 is too high.\n\n"
            "**Price Target**: 150",
            _section_stances(),
        )

        assert brief is not None
        assert brief["target_price"] == 150.0

    def test_salvage_drops_conflicting_top_level_targets(self):
        brief = salvage_decision_brief_from_text(
            "**Rating**: Hold\n\n"
            "**Price Target**: 150\n"
            "**Price Target**: 175",
            _section_stances(),
        )

        assert brief is not None
        assert brief["target_price"] is None

    def test_salvage_accepts_portfolio_manager_markdown_table(self):
        brief = salvage_decision_brief_from_text(
            "# Final decision report\n\n"
            "| Decision | Value |\n"
            "|:--|:--|\n"
            "| **\u6700\u7ec8\u8bc4\u7ea7** | **Underweight\uff08\u51cf\u6301\uff09** |\n"
            "| **\u76ee\u6807\u4ef7** | **4.90 \u5143** |\n"
            "| **\u6838\u5fc3\u64cd\u4f5c** | **\u5c06\u4ed3\u4f4d\u964d\u81f3\u57fa\u51c6\u768450%-70%** |",
            _section_stances(),
            output_language="Chinese",
        )

        assert brief is not None
        assert brief["rating"] == "Underweight"
        assert brief["headline"] == "\u5c06\u4ed3\u4f4d\u964d\u81f3\u57fa\u51c6\u768450%-70%"
        assert brief["target_price"] == 4.9
        assert brief["section_stances"]["market"]["stance"] == "bearish"

    def test_salvage_accepts_columnar_rating_and_price_table(self):
        brief = salvage_decision_brief_from_text(
            "**\u6700\u7ec8\u4ea4\u6613\u51b3\u7b56\u62a5\u544a\uff1a\u5fae\u8f6f\u516c\u53f8\uff08MSFT\uff09**\n\n"
            "### \u4e00\u3001\u6838\u5fc3\u7ed3\u8bba\n\n"
            "| \u8bc4\u7ea7 | \u4ef7\u683c\u76ee\u6807\uff08USD\uff09 |\n"
            "|------|----------------|\n"
            "| **Hold** | **493.00 \u7f8e\u5143** |\n",
            _section_stances(),
            output_language="Chinese",
        )

        assert brief is not None
        assert brief["rating"] == "Hold"
        assert brief["target_price"] == 493.0
        assert brief["currency"] == "USD"
        assert brief["headline"] == (
            "\u6700\u7ec8\u4ea4\u6613\u51b3\u7b56\u62a5\u544a\uff1a\u5fae\u8f6f\u516c\u53f8\uff08MSFT\uff09"
        )

    def test_salvage_rejects_trader_action_as_portfolio_rating(self):
        assert (
            salvage_decision_brief_from_text(
                "**\u64cd\u4f5c**: \u5356\u51fa\n\n\u4ea4\u6613\u6267\u884c\u5efa\u8bae: **\u5356\u51fa**",
                _section_stances(),
                output_language="Chinese",
            )
            is None
        )


@pytest.mark.unit
class TestRenderResearchPlan:
    def test_required_fields(self):
        p = ResearchPlan(
            recommendation=PortfolioRating.OVERWEIGHT,
            rationale="Bull case carried; tailwinds intact.",
            strategic_actions="Build position over two weeks; cap at 5%.",
        )
        md = render_research_plan(p)
        assert "**Recommendation**: Overweight" in md
        assert "**Rationale**: Bull case carried" in md
        assert "**Strategic Actions**: Build position" in md

    def test_all_5_tier_ratings_render(self):
        for rating in PortfolioRating:
            p = ResearchPlan(
                recommendation=rating,
                rationale="r",
                strategic_actions="s",
            )
            md = render_research_plan(p)
            assert f"**Recommendation**: {rating.value}" in md


# ---------------------------------------------------------------------------
# Trader agent: structured happy path + fallback
# ---------------------------------------------------------------------------


def _make_trader_state():
    return {
        "company_of_interest": "NVDA",
        "investment_plan": "**Recommendation**: Buy\n**Rationale**: ...\n**Strategic Actions**: ...",
    }


def _structured_trader_llm(captured: dict, proposal: TraderProposal | None = None):
    """Build a MagicMock LLM whose with_structured_output binding captures the
    prompt and returns a real TraderProposal so render_trader_proposal works.
    """
    if proposal is None:
        proposal = TraderProposal(
            action=TraderAction.BUY,
            reasoning="Strong setup.",
        )
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or proposal
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.unit
def test_invoke_structured_falls_back_when_result_is_none():
    # A thinking model can answer in plain text, leaving the parser with None.
    # That must fall back to free text, not crash on render(None) (#1051).
    from tradingagents.agents.utils.structured import invoke_structured_or_freetext

    structured = MagicMock()
    structured.invoke.return_value = None
    plain = MagicMock()
    plain.invoke.return_value = MagicMock(content="FREETEXT")

    out = invoke_structured_or_freetext(
        structured, plain, "prompt", render=lambda r: r.rating, agent_name="t"
    )
    assert out == "FREETEXT"
    plain.invoke.assert_called_once()


@pytest.mark.unit
def test_structured_invocation_reports_sanitized_fallback_reason():
    from tradingagents.agents.utils.structured import invoke_structured_with_fallback

    structured = MagicMock()
    structured.invoke.side_effect = ValueError("raw provider response")
    plain = MagicMock()
    plain.invoke.return_value = MagicMock(content="FREETEXT")

    result = invoke_structured_with_fallback(
        structured,
        plain,
        "prompt",
        render=lambda value: value.rating,
        agent_name="Portfolio Manager",
    )

    assert result.text == "FREETEXT"
    assert result.value is None
    assert result.fallback_reason == "ValueError"
    assert "raw provider response" not in result.fallback_reason


@pytest.mark.unit
class TestTraderAgent:
    def test_structured_path_produces_rendered_markdown(self):
        captured = {}
        proposal = TraderProposal(
            action=TraderAction.BUY,
            reasoning="AI capex cycle intact; institutional flows constructive.",
            entry_price=189.5,
            stop_loss=178.0,
            position_sizing="6% of portfolio",
        )
        llm = _structured_trader_llm(captured, proposal)
        trader = create_trader(llm)
        result = trader(_make_trader_state())
        plan = result["trader_investment_plan"]
        assert "**Action**: Buy" in plan
        assert "**Entry Price**: 189.5" in plan
        assert "TRANSACTION PROPOSAL: **BUY**" in plan
        # The same rendered markdown is also added to messages for downstream agents.
        assert plan in result["messages"][0].content

    def test_prompt_includes_investment_plan(self):
        captured = {}
        llm = _structured_trader_llm(captured)
        trader = create_trader(llm)
        trader(_make_trader_state())
        # The investment plan is in the user message of the captured prompt.
        prompt = captured["prompt"]
        assert any("Proposed Investment Plan" in m["content"] for m in prompt)

    def test_falls_back_to_freetext_when_structured_unavailable(self):
        plain_response = (
            "**Action**: Sell\n\nGuidance cut hits margins.\n\n"
            "TRANSACTION PROPOSAL: **SELL**"
        )
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("provider unsupported")
        llm.invoke.return_value = MagicMock(content=plain_response)
        trader = create_trader(llm)
        result = trader(_make_trader_state())
        assert result["trader_investment_plan"] == plain_response


# ---------------------------------------------------------------------------
# Research Manager agent: structured happy path + fallback
# ---------------------------------------------------------------------------


def _make_rm_state():
    return {
        "company_of_interest": "NVDA",
        "investment_debate_state": {
            "history": "Bull and bear arguments here.",
            "bull_history": "Bull says...",
            "bear_history": "Bear says...",
            "current_response": "",
            "judge_decision": "",
            "count": 1,
        },
    }


def _structured_rm_llm(captured: dict, plan: ResearchPlan | None = None):
    if plan is None:
        plan = ResearchPlan(
            recommendation=PortfolioRating.HOLD,
            rationale="Balanced view across both sides.",
            strategic_actions="Hold current position; reassess after earnings.",
        )
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or plan
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.unit
class TestResearchManagerAgent:
    def test_structured_path_produces_rendered_markdown(self):
        captured = {}
        plan = ResearchPlan(
            recommendation=PortfolioRating.OVERWEIGHT,
            rationale="Bull case is stronger; AI tailwind intact.",
            strategic_actions="Build position gradually over two weeks.",
        )
        llm = _structured_rm_llm(captured, plan)
        rm = create_research_manager(llm)
        result = rm(_make_rm_state())
        ip = result["investment_plan"]
        assert "**Recommendation**: Overweight" in ip
        assert "**Rationale**: Bull case" in ip
        assert "**Strategic Actions**: Build position" in ip

    def test_prompt_uses_5_tier_rating_scale(self):
        """The RM prompt must list all five tiers so the schema enum matches user expectations."""
        captured = {}
        llm = _structured_rm_llm(captured)
        rm = create_research_manager(llm)
        rm(_make_rm_state())
        prompt = captured["prompt"]
        for tier in ("Buy", "Overweight", "Hold", "Underweight", "Sell"):
            assert f"**{tier}**" in prompt, f"missing {tier} in prompt"

    def test_falls_back_to_freetext_when_structured_unavailable(self):
        plain_response = "**Recommendation**: Sell\n\n**Rationale**: ...\n\n**Strategic Actions**: ..."
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("provider unsupported")
        llm.invoke.return_value = MagicMock(content=plain_response)
        rm = create_research_manager(llm)
        result = rm(_make_rm_state())
        assert result["investment_plan"] == plain_response


# ---------------------------------------------------------------------------
# Sentiment Analyst: schema, render, structured happy path + fallback
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRenderSentimentReport:
    def test_header_contains_band_and_score(self):
        report = SentimentReport(
            overall_band=SentimentBand.BULLISH,
            overall_score=7.2,
            confidence="high",
            section_signal=SectionSignal(
                stance=DecisionStance.BULLISH,
                note="Sources are constructive.",
            ),
            narrative="Source breakdown here.",
        )
        md = render_sentiment_report(report)
        assert "**Overall Sentiment:** **Bullish**" in md
        assert "(Score: 7.2/10)" in md

    def test_header_contains_confidence(self):
        report = SentimentReport(
            overall_band=SentimentBand.NEUTRAL,
            overall_score=5.0,
            confidence="low",
            section_signal=SectionSignal(
                stance=DecisionStance.NEUTRAL,
                note="Evidence is limited.",
            ),
            narrative="Limited data.",
        )
        assert "**Confidence:** Low" in render_sentiment_report(report)

    def test_narrative_preserved_in_output(self):
        narrative = "## Breakdown\n\nStockTwits: 70% bullish.\n\n| Signal | Direction |\n|---|---|\n| News | Neutral |"
        report = SentimentReport(
            overall_band=SentimentBand.MILDLY_BULLISH,
            overall_score=6.0,
            confidence="medium",
            section_signal=SectionSignal(
                stance=DecisionStance.BULLISH,
                note="Sources lean constructive.",
            ),
            narrative=narrative,
        )
        assert narrative in render_sentiment_report(report)

    def test_all_six_bands_render(self):
        for band in SentimentBand:
            report = SentimentReport(
                overall_band=band, overall_score=5.0,
                confidence="medium",
                section_signal=SectionSignal(
                    stance=DecisionStance.NEUTRAL,
                    note="Test signal.",
                ),
                narrative="n",
            )
            assert band.value in render_sentiment_report(report)

    def test_score_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            SentimentReport(
                overall_band=SentimentBand.BULLISH, overall_score=11.0,
                confidence="high",
                section_signal=SectionSignal(
                    stance=DecisionStance.BULLISH,
                    note="Test signal.",
                ),
                narrative="n",
            )


def _make_sentiment_state():
    return {
        "company_of_interest": "NVDA",
        "trade_date": "2026-01-15",
        "asset_type": "stock",
        "messages": [],
    }


def _structured_sentiment_llm(captured: dict, report: SentimentReport | None = None):
    """MagicMock LLM whose structured binding captures the prompt and returns
    a real SentimentReport so render_sentiment_report works."""
    if report is None:
        report = SentimentReport(
            overall_band=SentimentBand.BULLISH, overall_score=7.5,
            confidence="high",
            section_signal=SectionSignal(
                stance=DecisionStance.BULLISH,
                note="Social sources are constructive.",
            ),
            narrative="StockTwits 75% bullish. News constructive. Reddit upbeat.",
        )
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or report
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.unit
class TestSentimentAnalystAgent:
    def test_structured_path_produces_rendered_markdown(self):
        captured = {}
        report = SentimentReport(
            overall_band=SentimentBand.MILDLY_BEARISH, overall_score=4.0,
            confidence="medium",
            section_signal=SectionSignal(
                stance=DecisionStance.BEARISH,
                note="Sources lean bearish.",
            ),
            narrative="Mixed signals across sources.",
        )
        analyst = create_sentiment_analyst(_structured_sentiment_llm(captured, report))
        sr = analyst(_make_sentiment_state())["sentiment_report"]
        assert "**Overall Sentiment:** **Mildly Bearish**" in sr
        assert "(Score: 4.0/10)" in sr
        assert "Mixed signals across sources." in sr

    def test_sentiment_report_also_in_messages(self):
        captured = {}
        analyst = create_sentiment_analyst(_structured_sentiment_llm(captured))
        result = analyst(_make_sentiment_state())
        assert len(result["messages"]) == 1
        assert result["sentiment_report"] == result["messages"][0].content
        assert result["sentiment_signal"]["stance"] == "bullish"

    def test_prompt_contains_ticker(self):
        captured = {}
        create_sentiment_analyst(_structured_sentiment_llm(captured))(_make_sentiment_state())
        assert any("NVDA" in str(m) for m in captured["prompt"])

    def test_falls_back_to_freetext_when_structured_unavailable(self):
        plain = "**Overall Sentiment:** **Bearish** (Score: 3.0/10)\n**Confidence:** Low\n\nLimited data."
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("provider unsupported")
        llm.invoke.return_value = MagicMock(content=plain)
        assert create_sentiment_analyst(llm)(_make_sentiment_state())["sentiment_report"] == plain

    def test_falls_back_to_freetext_when_structured_call_fails(self):
        plain = "Fallback free-text sentiment."
        structured = MagicMock()
        structured.invoke.side_effect = ValueError("bad JSON from model")
        llm = MagicMock()
        llm.with_structured_output.return_value = structured
        llm.invoke.return_value = MagicMock(content=plain)
        assert create_sentiment_analyst(llm)(_make_sentiment_state())["sentiment_report"] == plain
