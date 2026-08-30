"""Pydantic schemas used by agents that produce structured output.

The framework's primary artifact is still prose: each agent's natural-language
reasoning is what users read in the saved markdown reports and what the
downstream agents read as context.  Structured output is layered onto the
three decision-making agents (Research Manager, Trader, Portfolio Manager)
so that:

- Their outputs follow consistent section headers across runs and providers
- Each provider's native structured-output mode is used (json_schema for
  OpenAI/xAI, response_schema for Gemini, tool-use for Anthropic)
- Schema field descriptions become the model's output instructions, freeing
  the prompt body to focus on context and the rating-scale guidance
- A render helper turns the parsed Pydantic instance back into the same
  markdown shape the rest of the system already consumes, so display,
  memory log, and saved reports keep working unchanged
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from tradingagents.agents.utils.report_i18n import (
    localize_report_value,
    report_labels,
)

# LLMs sometimes write a placeholder string ("None", "N/A", ...) into an optional
# numeric field instead of omitting it. Coerce those to None so the structured
# call validates instead of erroring (#1058). Pydantic still parses real numeric
# strings ("189.5") to float.
_NULLISH_FLOAT = {"", "none", "n/a", "na", "null", "nil", "-", "tbd", "unknown"}
NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

# Appended to every free-text Field description. Structured-output providers
# send schema descriptions separately from the agent prompt; without this,
# Research Manager / Trader / Portfolio Manager prose can drift into Chinese
# (or another language) when prior debate context is non-English.
_PROSE_LANGUAGE_RULE = (
    "Write this field entirely in the configured report output language "
    "(including English when that is configured). Do not switch languages "
    "even if source materials or prior agent messages are in another language."
)


def _coerce_optional_float(value):
    if isinstance(value, str) and value.strip().lower() in _NULLISH_FLOAT:
        return None
    return value


def _trim_watch_list(value: object) -> object:
    if isinstance(value, list) and len(value) > 3:
        return value[:3]
    return value


def _coerce_optional_list(value: object) -> object:
    """Treat JSON null / nullish placeholders as an omitted list.

    Qwen and similar providers often emit ``add_levels: null`` instead of
    ``[]``. Without this, the whole PortfolioDecision is discarded.
    """
    if value is None:
        return []
    if isinstance(value, str) and value.strip().lower() in _NULLISH_FLOAT:
        return []
    return value


# ---------------------------------------------------------------------------
# Shared rating types
# ---------------------------------------------------------------------------


class PortfolioRating(str, Enum):
    """5-tier rating used by the Research Manager and Portfolio Manager."""

    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"


class TraderAction(str, Enum):
    """3-tier transaction direction used by the Trader.

    The Trader's job is to translate the Research Manager's investment plan
    into a concrete transaction proposal: should the desk execute a Buy, a
    Sell, or sit on Hold this round.  Position sizing and the nuanced
    Overweight / Underweight calls happen later at the Portfolio Manager.
    """

    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"


class DecisionConviction(str, Enum):
    """Qualitative confidence for the final decision brief."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DecisionStance(str, Enum):
    """Directional stance shown for each analyst section."""

    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    UNAVAILABLE = "unavailable"


def _coerce_portfolio_rating(value: object) -> object:
    if isinstance(value, PortfolioRating) or not isinstance(value, str):
        return value
    from tradingagents.agents.utils.rating import parse_authoritative_rating

    return parse_authoritative_rating(value) or value


def _coerce_decision_conviction(value: object) -> object:
    if isinstance(value, DecisionConviction) or not isinstance(value, str):
        return value
    from tradingagents.agents.utils.report_i18n import conviction_value_aliases

    aliases = conviction_value_aliases()
    key = value.strip()
    return aliases.get(key) or aliases.get(key.lower()) or value


CoercedPortfolioRating = Annotated[
    PortfolioRating,
    BeforeValidator(_coerce_portfolio_rating),
]
CoercedDecisionConviction = Annotated[
    DecisionConviction,
    BeforeValidator(_coerce_decision_conviction),
]


class PriceRange(BaseModel):
    """Inclusive price zone in the instrument's quote currency."""

    low: float = Field(gt=0, description="Lower bound of the price zone.")
    high: float = Field(gt=0, description="Upper bound of the price zone.")

    @model_validator(mode="after")
    def _validate_bounds(self):
        if self.low > self.high:
            raise ValueError("low must be less than or equal to high")
        return self


class SectionSignal(BaseModel):
    """Compact directional result for one analyst report."""

    stance: DecisionStance = Field(
        description=(
            "Bullish, neutral, bearish, or unavailable when that analyst report "
            "was not selected or produced no usable evidence."
        )
    )
    note: str = Field(
        description=(
            "One concise sentence supporting the stance. "
            f"{_PROSE_LANGUAGE_RULE}"
        )
    )


class SectionStances(BaseModel):
    """The four evidence lanes displayed in the final result card."""

    market: SectionSignal
    sentiment: SectionSignal
    news: SectionSignal
    fundamentals: SectionSignal


class DecisionBriefDraft(BaseModel):
    """LLM-authored portion of the final result card."""

    headline: NonBlankText = Field(
        description=(
            f"One concise sentence stating the final action plan. {_PROSE_LANGUAGE_RULE}"
        ),
    )
    conviction: CoercedDecisionConviction = Field(
        description="Qualitative conviction: low, medium, or high."
    )
    position_guidance: str | None = Field(
        default=None,
        description=(
            "Optional target exposure or position-sizing guidance. "
            f"{_PROSE_LANGUAGE_RULE}"
        ),
    )
    entry_zone: PriceRange | None = Field(
        default=None,
        description="Optional initial entry or probe zone. Use a range, not a prose value.",
    )
    add_levels: list[PriceRange] = Field(
        default_factory=list,
        description="Zero or more confirmation zones for adding exposure.",
    )
    stop_or_reduce: float | None = Field(
        default=None,
        gt=0,
        description="Optional single price that triggers a stop or exposure reduction.",
    )
    bull_case: str = Field(
        description=(
            f"The strongest bullish argument in one sentence. {_PROSE_LANGUAGE_RULE}"
        ),
    )
    bear_case: str = Field(
        description=(
            f"The strongest bearish argument in one sentence. {_PROSE_LANGUAGE_RULE}"
        ),
    )
    key_risk: str = Field(
        description=(
            f"The most important current risk in one sentence. {_PROSE_LANGUAGE_RULE}"
        ),
    )
    what_to_watch: list[str] = Field(
        min_length=1,
        max_length=3,
        description=(
            f"One to three observable confirmation points. {_PROSE_LANGUAGE_RULE}"
        ),
    )
    invalidation: str = Field(
        description=(
            f"One sentence stating when the thesis is invalid. {_PROSE_LANGUAGE_RULE}"
        ),
    )
    conflict_note: str | None = Field(
        default=None,
        description=(
            "Optional sentence explaining how conflicting section signals were "
            f"resolved. {_PROSE_LANGUAGE_RULE}"
        ),
    )

    @field_validator("add_levels", mode="before")
    @classmethod
    def _nullish_add_levels_to_empty(cls, v):
        return _coerce_optional_list(v)

    @field_validator("stop_or_reduce", mode="before")
    @classmethod
    def _nullish_stop_to_none(cls, v):
        return _coerce_optional_float(v)

    @field_validator("what_to_watch", mode="before")
    @classmethod
    def _trim_what_to_watch(cls, v):
        return _trim_watch_list(v)


class DecisionBrief(DecisionBriefDraft):
    """Persisted and API-facing final result card."""

    rating: CoercedPortfolioRating
    as_of_price: float | None = Field(default=None, gt=0)
    as_of_date: str | None = None
    currency: str | None = None
    time_horizon: str | None = None
    target_price: float | None = Field(default=None, gt=0)
    section_stances: SectionStances


# ---------------------------------------------------------------------------
# Research Manager
# ---------------------------------------------------------------------------


class ResearchPlan(BaseModel):
    """Structured investment plan produced by the Research Manager.

    Hand-off to the Trader: the recommendation pins the directional view,
    the rationale captures which side of the bull/bear debate carried the
    argument, and the strategic actions translate that into concrete
    instructions the trader can execute against.
    """

    recommendation: CoercedPortfolioRating = Field(
        description=(
            "The investment recommendation. Exactly one of Buy / Overweight / "
            "Hold / Underweight / Sell. Reserve Hold for situations where the "
            "evidence on both sides is genuinely balanced; otherwise commit to "
            "the side with the stronger arguments."
        ),
    )
    rationale: str = Field(
        description=(
            "Conversational summary of the key points from both sides of the "
            "debate, ending with which arguments led to the recommendation. "
            f"Speak naturally, as if to a teammate. {_PROSE_LANGUAGE_RULE}"
        ),
    )
    strategic_actions: str = Field(
        description=(
            "Concrete steps for the trader to implement the recommendation, "
            "including position sizing guidance consistent with the rating. "
            f"{_PROSE_LANGUAGE_RULE}"
        ),
    )


def render_research_plan(plan: ResearchPlan) -> str:
    """Render a ResearchPlan to markdown for storage and the trader's prompt context."""
    labels = report_labels()
    return "\n".join([
        f"**{labels['recommendation']}**: {localize_report_value(plan.recommendation.value)}",
        "",
        f"**{labels['rationale']}**: {plan.rationale}",
        "",
        f"**{labels['strategic_actions']}**: {plan.strategic_actions}",
    ])


# ---------------------------------------------------------------------------
# Trader
# ---------------------------------------------------------------------------


class TraderProposal(BaseModel):
    """Structured transaction proposal produced by the Trader.

    The trader reads the Research Manager's investment plan and the analyst
    reports, then turns them into a concrete transaction: what action to
    take, the reasoning that justifies it, and the practical levels for
    entry, stop-loss, and sizing.
    """

    action: TraderAction = Field(
        description="The transaction direction. Exactly one of Buy / Hold / Sell.",
    )
    reasoning: str = Field(
        description=(
            "The case for this action, anchored in the analysts' reports and "
            f"the research plan. Two to four sentences. {_PROSE_LANGUAGE_RULE}"
        ),
    )
    entry_price: float | None = Field(
        default=None,
        description="Optional entry price target in the instrument's quote currency.",
    )
    stop_loss: float | None = Field(
        default=None,
        description="Optional stop-loss price in the instrument's quote currency.",
    )
    position_sizing: str | None = Field(
        default=None,
        description=(
            "Optional sizing guidance, e.g. '5% of portfolio'. "
            f"{_PROSE_LANGUAGE_RULE}"
        ),
    )

    @field_validator("entry_price", "stop_loss", mode="before")
    @classmethod
    def _nullish_float_to_none(cls, v):
        return _coerce_optional_float(v)


def render_trader_proposal(proposal: TraderProposal) -> str:
    """Render a TraderProposal to markdown.

    The trailing transaction-proposal line is preserved for backward
    compatibility with older prompts and greps. Its wording follows
    ``output_language`` (English ``TRANSACTION PROPOSAL`` or Chinese
    ``交易执行建议``). It is the Trader's execution view — not the
    Portfolio Manager's final rating.
    """
    labels = report_labels()
    action = localize_report_value(proposal.action.value)
    parts = [
        f"**{labels['action']}**: {action}",
        "",
        f"**{labels['reasoning']}**: {proposal.reasoning}",
    ]
    if proposal.entry_price is not None:
        parts.extend(["", f"**{labels['entry_price']}**: {proposal.entry_price}"])
    if proposal.stop_loss is not None:
        parts.extend(["", f"**{labels['stop_loss']}**: {proposal.stop_loss}"])
    if proposal.position_sizing:
        parts.extend(["", f"**{labels['position_sizing']}**: {proposal.position_sizing}"])
    # English keeps the historical ALL-CAPS action token; Chinese uses the
    # localized display value so the saved report stays fully localized.
    proposal_action = (
        proposal.action.value.upper()
        if action == proposal.action.value
        else action
    )
    parts.extend([
        "",
        f"{labels['final_transaction_proposal']}: **{proposal_action}**",
    ])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Portfolio Manager
# ---------------------------------------------------------------------------


class PortfolioDecision(BaseModel):
    """Structured output produced by the Portfolio Manager.

    The model fills every field as part of its primary LLM call; no separate
    extraction pass is required. Field descriptions double as the model's
    output instructions, so the prompt body only needs to convey context and
    the rating-scale guidance.
    """

    rating: CoercedPortfolioRating = Field(
        description=(
            "The final position rating. Exactly one of Buy / Overweight / Hold / "
            "Underweight / Sell, picked based on the analysts' debate."
        ),
    )
    executive_summary: str = Field(
        description=(
            "A concise action plan covering entry strategy, position sizing, "
            f"key risk levels, and time horizon. Two to four sentences. "
            f"{_PROSE_LANGUAGE_RULE}"
        ),
    )
    investment_thesis: str = Field(
        description=(
            "Detailed reasoning anchored in specific evidence from the analysts' "
            "debate. If prior lessons are referenced in the prompt context, "
            "incorporate them; otherwise rely solely on the current analysis. "
            f"{_PROSE_LANGUAGE_RULE}"
        ),
    )
    price_target: float = Field(
        gt=0,
        description=(
            "Required positive target price in the instrument's quote currency, "
            "consistent with the rating and recommended time horizon."
        ),
    )
    time_horizon: str | None = Field(
        default=None,
        description=(
            "Optional recommended holding period, e.g. '3-6 months'. "
            f"{_PROSE_LANGUAGE_RULE}"
        ),
    )
    brief: DecisionBriefDraft = Field(
        description=(
            "Required compact result-card data authored by the Portfolio Manager. "
            "Analyst section stances are attached separately from graph state."
        )
    )

    @field_validator("price_target", mode="before")
    @classmethod
    def _coerce_price_target(cls, v):
        return _coerce_optional_float(v)


def decision_brief_from_portfolio(
    decision: PortfolioDecision,
    section_stances: SectionStances,
) -> DecisionBrief:
    """Combine the PM brief with canonical fields and analyst-owned signals."""
    return DecisionBrief(
        rating=decision.rating,
        time_horizon=decision.time_horizon,
        target_price=decision.price_target,
        section_stances=section_stances,
        **decision.brief.model_dump(),
    )


class PortfolioDecisionRecovery(BaseModel):
    """Lighter schema used to recover a decision brief from free-text PM output.

    Nested price zones are omitted so a second-pass extraction is less likely
    to fail for the same reasons as the full ``PortfolioDecision`` call.
    """

    position_guidance: NonBlankText | None = Field(
        default=None,
        description=(
            f"Position-sizing guidance only when explicitly stated. {_PROSE_LANGUAGE_RULE}"
        ),
    )
    bull_case: NonBlankText | None = Field(
        default=None,
        description=(
            f"The bullish argument only when explicitly stated. {_PROSE_LANGUAGE_RULE}"
        ),
    )
    bear_case: NonBlankText | None = Field(
        default=None,
        description=(
            f"The bearish argument only when explicitly stated. {_PROSE_LANGUAGE_RULE}"
        ),
    )
    key_risk: NonBlankText | None = Field(
        default=None,
        description=(
            f"The key risk only when explicitly stated. {_PROSE_LANGUAGE_RULE}"
        ),
    )
    what_to_watch: list[NonBlankText] = Field(
        default_factory=list,
        max_length=3,
        description=(
            "Up to three confirmation points explicitly stated in the prose. "
            f"{_PROSE_LANGUAGE_RULE}"
        ),
    )
    invalidation: NonBlankText | None = Field(
        default=None,
        description=(
            f"The invalidation condition only when explicitly stated. {_PROSE_LANGUAGE_RULE}"
        ),
    )
    conflict_note: NonBlankText | None = Field(
        default=None,
        description=(
            f"A conflict note only when explicitly stated. {_PROSE_LANGUAGE_RULE}"
        ),
    )

    @field_validator("what_to_watch", mode="before")
    @classmethod
    def _trim_what_to_watch(cls, v):
        return _trim_watch_list(v)


def decision_brief_from_recovery(
    recovery: PortfolioDecisionRecovery,
    section_stances: SectionStances,
    *,
    rating: PortfolioRating,
    headline: str,
    target_price: float | None,
    currency: str | None,
    fallback_text: str,
    fallback_watch: str,
    degraded_note: str,
) -> DecisionBrief:
    """Combine non-authoritative recovery prose with verified text fields."""
    conflict_note = degraded_note
    if recovery.conflict_note:
        conflict_note = f"{degraded_note} {recovery.conflict_note}"
    return DecisionBrief(
        rating=rating,
        time_horizon=None,
        target_price=target_price,
        currency=currency,
        section_stances=section_stances,
        headline=headline,
        conviction=DecisionConviction.LOW,
        position_guidance=recovery.position_guidance,
        entry_zone=None,
        add_levels=[],
        stop_or_reduce=None,
        bull_case=recovery.bull_case or fallback_text,
        bear_case=recovery.bear_case or fallback_text,
        key_risk=recovery.key_risk or fallback_text,
        what_to_watch=list(recovery.what_to_watch) or [fallback_watch],
        invalidation=recovery.invalidation or fallback_text,
        conflict_note=conflict_note,
    )


def render_pm_decision(decision: PortfolioDecision) -> str:
    """Render a PortfolioDecision back to the markdown shape the rest of the system expects.

    Memory log, CLI display, and saved report files all read this markdown.
    Section headers follow ``output_language``; parsers accept both English
    and Chinese label/value forms.
    """
    labels = report_labels()
    parts = [
        f"**{labels['rating']}**: {localize_report_value(decision.rating.value)}",
        "",
        f"**{labels['executive_summary']}**: {decision.executive_summary}",
        "",
        f"**{labels['investment_thesis']}**: {decision.investment_thesis}",
    ]
    if decision.price_target is not None:
        parts.extend(["", f"**{labels['price_target']}**: {decision.price_target}"])
    if decision.time_horizon:
        parts.extend(["", f"**{labels['time_horizon']}**: {decision.time_horizon}"])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Sentiment Analyst
# ---------------------------------------------------------------------------


class SentimentBand(str, Enum):
    """Discrete sentiment direction produced by the Sentiment Analyst.

    Six tiers keep the signal granular enough to be actionable while remaining
    small enough for every provider to map reliably from its JSON output.
    """

    BULLISH = "Bullish"
    MILDLY_BULLISH = "Mildly Bullish"
    NEUTRAL = "Neutral"
    MIXED = "Mixed"
    MILDLY_BEARISH = "Mildly Bearish"
    BEARISH = "Bearish"


class SentimentReport(BaseModel):
    """Structured sentiment report produced by the Sentiment Analyst.

    Replaces the previous free-form prose output so downstream consumers
    (dashboards, audit logs, PDF renderers, other agents) can read
    ``overall_band`` and ``overall_score`` without maintaining fragile regex
    fallbacks that drift with every model release. ``narrative`` preserves the
    rich source-by-source analysis; ``render_sentiment_report`` prepends a
    deterministic header so the saved report stays human-readable.
    """

    overall_band: SentimentBand = Field(
        description=(
            "Overall sentiment direction. Exactly one of: "
            "Bullish / Mildly Bullish / Neutral / Mixed / Mildly Bearish / Bearish. "
            "Use Mixed when sources point in clearly different directions. "
            "Use Neutral only when all sources are genuinely silent or non-committal."
        ),
    )
    overall_score: float = Field(
        ge=0.0,
        le=10.0,
        description=(
            "Numeric sentiment intensity on a 0–10 scale. "
            "0 = maximally bearish, 5 = neutral, 10 = maximally bullish. "
            "Guideline for consistency with overall_band: "
            "Bullish ~6.5–10, Mildly Bullish ~5.5–6.4, Neutral/Mixed ~4.5–5.5, "
            "Mildly Bearish ~3.5–4.4, Bearish ~0–3.4. "
            "Only the 0–10 bounds are enforced."
        ),
    )
    confidence: Literal["low", "medium", "high"] = Field(
        description=(
            "Confidence in the assessment based on data quality and sample size. "
            "Use 'low' when one or more sources returned a placeholder or fewer "
            "than 5 data points; 'medium' when data is present but sparse; "
            "'high' when all three sources returned substantive data."
        ),
    )
    section_signal: SectionSignal = Field(
        description=(
            "The Sentiment Analyst's compact directional signal. Align bullish with "
            "Bullish / Mildly Bullish, bearish with Bearish / Mildly Bearish, and "
            "neutral with Neutral / Mixed. Cite the strongest evidence in the note."
        )
    )
    narrative: str = Field(
        description=(
            "Full sentiment report covering, in order: "
            "(1) source-by-source breakdown with specific evidence (cite message "
            "counts, ratios, notable posts); "
            "(2) cross-source divergences and alignments; "
            "(3) dominant narrative themes; "
            "(4) catalysts and risks surfaced by the data; "
            "(5) a markdown table summarising key sentiment signals, their "
            "direction, source, and supporting evidence. "
            "Keep it informative and substantive: develop each section thoroughly "
            "with concrete evidence so every point adds new signal for the trader. "
            f"{_PROSE_LANGUAGE_RULE}"
        ),
    )


def render_sentiment_report(report: SentimentReport) -> str:
    """Render a SentimentReport to the markdown shape the rest of the system expects.

    The structured header (band + score + confidence) is prepended to the
    narrative so the saved report is both human-readable and machine-parseable
    without regex. Labels and band/confidence values follow ``output_language``.
    """
    labels = report_labels()
    band = localize_report_value(report.overall_band.value)
    confidence = localize_report_value(report.confidence.capitalize())
    return "\n".join([
        f"**{labels['overall_sentiment']}:** **{band}** "
        f"({labels['score']}: {report.overall_score:.1f}/10)",
        f"**{labels['confidence']}:** {confidence}",
        "",
        report.narrative,
    ])
