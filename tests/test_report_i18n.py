"""Structured-report chrome follows output_language locale packs."""

from __future__ import annotations

import pytest

from tradingagents.agents.schemas import (
    DecisionBriefDraft,
    DecisionConviction,
    DecisionStance,
    PortfolioDecision,
    PortfolioRating,
    ResearchPlan,
    SectionSignal,
    SectionStances,
    SentimentBand,
    SentimentReport,
    TraderAction,
    TraderProposal,
    render_pm_decision,
    render_research_plan,
    render_sentiment_report,
    render_trader_proposal,
)
from tradingagents.agents.utils.agent_utils import (
    get_language_instruction,
    get_section_recommendation_instruction,
    get_transaction_proposal_instruction,
)
from tradingagents.agents.utils.decision_brief_recovery import (
    salvage_decision_brief_from_text,
)
from tradingagents.agents.utils.rating import parse_rating
from tradingagents.agents.utils.report_i18n import (
    REPORT_LOCALES,
    format_debate_argument,
    get_analyst_recommendation_phrase,
    get_debate_role_label,
    localize_report_value,
    normalize_report_language,
    report_labels,
)
from tradingagents.dataflows.config import set_config


@pytest.fixture(autouse=True)
def _reset_english_language():
    set_config({"output_language": "English"})
    yield
    set_config({"output_language": "English"})


@pytest.mark.unit
class TestNormalizeReportLanguage:
    def test_chinese_aliases(self):
        for value in ("Chinese", "chinese", "中文", "zh-CN", "zh_hans"):
            assert normalize_report_language(value) == "chinese"

    def test_frontend_language_ids(self):
        assert normalize_report_language("English") == "english"
        assert normalize_report_language("Japanese") == "japanese"
        assert normalize_report_language("한국어") == "korean"
        assert normalize_report_language("Español") == "spanish"
        assert normalize_report_language("Português") == "portuguese"
        assert normalize_report_language("Français") == "french"
        assert normalize_report_language("Deutsch") == "german"
        assert normalize_report_language("العربية") == "arabic"
        assert normalize_report_language("Русский") == "russian"
        assert normalize_report_language("हिन्दी") == "hindi"

    def test_unknown_falls_back_to_english(self):
        assert normalize_report_language(None) == "english"
        assert normalize_report_language("Turkish") == "english"
        assert normalize_report_language("custom-lang") == "english"


@pytest.mark.unit
class TestLocalePackCoverage:
    def test_all_frontend_locales_have_complete_labels(self):
        required = {
            "recommendation",
            "rating",
            "final_transaction_proposal",
            "bull_analyst",
            "price_target",
            "confidence",
        }
        assert REPORT_LOCALES == (
            "english",
            "chinese",
            "japanese",
            "korean",
            "hindi",
            "spanish",
            "portuguese",
            "french",
            "german",
            "arabic",
            "russian",
        )
        for locale in REPORT_LOCALES:
            labels = report_labels(locale)
            for key in required:
                assert labels[key].strip(), f"{locale}.{key} empty"

    @pytest.mark.parametrize(
        ("language", "buy", "bull"),
        [
            ("Chinese", "买入", "多头分析师"),
            ("Japanese", "買い", "強気アナリスト"),
            ("Korean", "매수", "강세 분석가"),
            ("Spanish", "Comprar", "Analista alcista"),
            ("French", "Acheter", "Analyste haussier"),
            ("German", "Kaufen", "Bullischer Analyst"),
            ("Russian", "Покупать", "Бычий аналитик"),
            ("Arabic", "شراء", "المحلل الصاعد"),
            ("Hindi", "खरीदें", "बुल विश्लेषक"),
            ("Portuguese", "Comprar", "Analista de alta"),
        ],
    )
    def test_locale_buy_and_bull_prefix(self, language, buy, bull):
        set_config({"output_language": language})
        assert localize_report_value("Buy") == buy
        assert get_debate_role_label("bull_analyst") == bull
        assert format_debate_argument("bull_analyst", "x").startswith(f"{bull}:")

    @pytest.mark.parametrize(
        ("language", "see_detail"),
        [
            ("English", "See the detailed report."),
            ("Chinese", "详见详细报告。"),
            ("Japanese", "詳細レポートを参照してください。"),
            ("Korean", "자세한 보고서를 참조하세요."),
            ("Hindi", "विस्तृत रिपोर्ट देखें।"),
            ("Spanish", "Consulte el informe detallado."),
            ("Portuguese", "Consulte o relatório detalhado."),
            ("French", "Consultez le rapport détaillé."),
            ("German", "Siehe ausführlichen Bericht."),
            ("Arabic", "راجع التقرير التفصيلي."),
            ("Russian", "См. подробный отчет."),
        ],
    )
    def test_salvage_copy_covers_every_report_locale(self, language, see_detail):
        set_config({"output_language": language})
        labels = report_labels(language)
        rating = localize_report_value("Hold", language)
        stances = SectionStances(
            market=SectionSignal(stance=DecisionStance.UNAVAILABLE, note="n"),
            sentiment=SectionSignal(stance=DecisionStance.UNAVAILABLE, note="n"),
            news=SectionSignal(stance=DecisionStance.UNAVAILABLE, note="n"),
            fundamentals=SectionSignal(stance=DecisionStance.UNAVAILABLE, note="n"),
        )

        brief = salvage_decision_brief_from_text(
            f"**{labels['rating']}**: {rating}\n\n"
            f"**{labels['executive_summary']}**: Summary.",
            stances,
        )

        assert brief is not None
        assert brief["bull_case"] == see_detail


@pytest.mark.unit
class TestChineseRenderHelpers:
    def test_research_plan_labels_and_rating(self):
        set_config({"output_language": "Chinese"})
        md = render_research_plan(
            ResearchPlan(
                recommendation=PortfolioRating.OVERWEIGHT,
                rationale="多头论据更强。",
                strategic_actions="分批建仓。",
            )
        )
        assert "**建议**: 增持" in md
        assert "**研究逻辑**: 多头论据更强。" in md
        assert "**执行计划**: 分批建仓。" in md
        assert "Recommendation" not in md

    def test_trader_proposal_labels(self):
        set_config({"output_language": "Chinese"})
        md = render_trader_proposal(
            TraderProposal(action=TraderAction.HOLD, reasoning="观望为主。")
        )
        assert "**操作**: 持有" in md
        assert "**理由**: 观望为主。" in md
        assert "交易执行建议: **持有**" in md
        assert "最终交易建议" not in md
        assert "FINAL TRANSACTION PROPOSAL" not in md

    def test_pm_decision_labels(self):
        set_config({"output_language": "Chinese"})
        md = render_pm_decision(
            PortfolioDecision(
                rating=PortfolioRating.BUY,
                executive_summary="逢低布局。",
                investment_thesis="基本面支撑。",
                price_target=100.0,
                brief=DecisionBriefDraft(
                    headline="等待确认后加仓。",
                    conviction=DecisionConviction.MEDIUM,
                    bull_case="盈利增长稳健。",
                    bear_case="现金流仍待验证。",
                    key_risk="资本开支维持高位。",
                    what_to_watch=["自由现金流改善"],
                    invalidation="盈利预期下调则失效。",
                ),
            )
        )
        assert "**评级**: 买入" in md
        assert "**执行摘要**: 逢低布局。" in md
        assert "**投资论点**: 基本面支撑。" in md
        assert "**目标价**: 100.0" in md

    def test_sentiment_header(self):
        set_config({"output_language": "Chinese"})
        md = render_sentiment_report(
            SentimentReport(
                overall_band=SentimentBand.BULLISH,
                overall_score=7.0,
                confidence="low",
                section_signal=SectionSignal(
                    stance=DecisionStance.BULLISH,
                    note="情绪偏多。",
                ),
                narrative="1. 分来源情绪拆解",
            )
        )
        assert "**整体情绪:** **看涨** (得分: 7.0/10)" in md
        assert "**置信度:** 低" in md
        assert "Overall Sentiment" not in md
        assert "1. 分来源情绪拆解" in md

    def test_english_render_unchanged(self):
        md = render_research_plan(
            ResearchPlan(
                recommendation=PortfolioRating.HOLD,
                rationale="Balanced.",
                strategic_actions="Wait.",
            )
        )
        assert "**Recommendation**: Hold" in md

    def test_korean_research_plan_chrome(self):
        set_config({"output_language": "Korean"})
        md = render_research_plan(
            ResearchPlan(
                recommendation=PortfolioRating.BUY,
                rationale="성장 가시성.",
                strategic_actions="분할 매수.",
            )
        )
        assert "**권고**: 매수" in md
        assert "Recommendation" not in md


@pytest.mark.unit
class TestParseLocalizedRatings:
    def test_chinese_rating_label(self):
        assert parse_rating("**评级**: 增持\n执行摘要：分批。") == "Overweight"

    def test_chinese_recommendation_label(self):
        assert parse_rating("**建议**: 买入\n研究逻辑：增长确定。") == "Buy"

    def test_english_still_works(self):
        assert parse_rating("**Rating**: Sell\nExit.") == "Sell"

    @pytest.mark.parametrize(
        "text",
        [
            "**レーティング**: 買い",
            "**등급**: 매수",
            "**Calificación**: Comprar",
            "**Notation**: Acheter",
            "**Bewertung**: Kaufen",
            "**Рейтинг**: Покупать",
            "**التصنيف**: شراء",
            "**रेटिंग**: खरीदें",
            "**Classificação**: Comprar",
        ],
    )
    def test_locale_rating_labels(self, text):
        assert parse_rating(text) == "Buy"


@pytest.mark.unit
class TestLanguagePromptHelpers:
    def test_english_language_instruction_forces_english(self):
        set_config({"output_language": "English"})
        out = get_language_instruction()
        assert "CRITICAL LANGUAGE RULE" in out
        assert "entire response in English" in out
        assert "prior agent or debate messages" in out
        assert "TRANSACTION PROPOSAL" not in out

    def test_chinese_language_instruction_mentions_headings(self):
        set_config({"output_language": "Chinese"})
        out = get_language_instruction()
        assert "Chinese" in out
        assert "headings" in out
        assert "TRANSACTION PROPOSAL" in out
        assert "paraphrase that evidence into Chinese" in out
        assert "never invent a phonetic Chinese transliteration" in out
        assert "JOVE" in out
        assert "Apple → 苹果" in out

    def test_chinese_transaction_phrase_forbids_trader_chrome(self):
        set_config({"output_language": "Chinese"})
        out = get_transaction_proposal_instruction()
        assert "交易执行建议" in out
        assert "Do not conclude or prefix" in out
        assert "买入/持有/卖出" in out
        assert "最终交易建议" not in out  # phrase itself renamed
        assert "FINAL TRANSACTION PROPOSAL" not in out

    def test_english_transaction_phrase_forbids_trader_chrome(self):
        out = get_transaction_proposal_instruction()
        assert "TRANSACTION PROPOSAL" in out
        assert "Do not conclude or prefix" in out
        assert "Buy/Hold/Sell" in out

    def test_korean_transaction_phrase_uses_localized_actions(self):
        set_config({"output_language": "Korean"})
        out = get_transaction_proposal_instruction()
        assert "거래 제안" in out
        assert "매수/보유/매도" in out

    def test_market_section_recommendation_chinese(self):
        set_config({"output_language": "Chinese"})
        assert get_analyst_recommendation_phrase("market") == "市场分析建议"
        out = get_section_recommendation_instruction("market")
        assert "市场分析建议" in out
        assert "最终交易建议" in out  # explicit ban of the old wording
        assert "组合最终决策" in out

    def test_market_section_recommendation_english(self):
        out = get_section_recommendation_instruction("market")
        assert "Market Analysis Recommendation" in out
        assert "final portfolio decision" in out


@pytest.mark.unit
class TestDebateRoleLabels:
    def test_chinese_speaker_prefixes(self):
        set_config({"output_language": "Chinese"})
        assert get_debate_role_label("bull_analyst") == "多头分析师"
        assert get_debate_role_label("bear_analyst") == "空头分析师"
        assert get_debate_role_label("aggressive_analyst") == "激进分析师"
        assert get_debate_role_label("conservative_analyst") == "保守分析师"
        assert get_debate_role_label("neutral_analyst") == "中性分析师"
        assert format_debate_argument("bull_analyst", "增长确定。") == (
            "多头分析师: 增长确定。"
        )

    def test_english_speaker_prefixes(self):
        assert get_debate_role_label("bull_analyst") == "Bull Analyst"
        assert format_debate_argument("bear_analyst", "Risks remain.") == (
            "Bear Analyst: Risks remain."
        )
