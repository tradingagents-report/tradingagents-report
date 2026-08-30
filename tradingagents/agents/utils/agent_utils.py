import functools
import logging
from collections.abc import Mapping
from typing import Any

from langchain_core.messages import HumanMessage, RemoveMessage

# Import tools from separate utility files
from tradingagents.agents.utils.core_stock_tools import get_stock_data
from tradingagents.agents.utils.fundamental_data_tools import (
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_peer_comparison,
)
from tradingagents.agents.utils.macro_data_tools import get_macro_indicators
from tradingagents.agents.utils.market_data_validation_tools import get_verified_market_snapshot
from tradingagents.agents.utils.news_data_tools import (
    get_earnings_calendar,
    get_economic_calendar,
    get_global_news,
    get_insider_transactions,
    get_news,
)
from tradingagents.agents.utils.prediction_markets_tools import get_prediction_markets
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators,
    get_ta_indicators,
    get_ta_summary,
)
from tradingagents.dataflows.structured_data import get_instrument_identity

# Public surface: the data tools are imported here so agents and the graph
# import them from one place, plus the instrument/language helpers defined below.
__all__ = [
    "get_stock_data",
    "get_indicators",
    "get_ta_summary",
    "get_ta_indicators",
    "get_fundamentals",
    "get_balance_sheet",
    "get_cashflow",
    "get_income_statement",
    "get_peer_comparison",
    "get_news",
    "get_global_news",
    "get_insider_transactions",
    "get_earnings_calendar",
    "get_economic_calendar",
    "get_macro_indicators",
    "get_prediction_markets",
    "get_verified_market_snapshot",
    "build_instrument_context",
    "merge_display_name_into_identity",
    "resolve_instrument_identity",
    "get_instrument_context_from_state",
    "get_language_instruction",
    "get_transaction_proposal_instruction",
    "get_section_recommendation_instruction",
    "get_chart_slot_instruction",
    "create_msg_delete",
]

logger = logging.getLogger(__name__)


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Always emits a directive — including for English. English used to return
    an empty string to save tokens, but Chinese-market context (A-share names,
    CN news/filings, DeepSeek defaults) then caused individual agents to
    drift into Chinese mid-report. Applied to every agent whose output reaches
    the saved report so one run stays in one language.
    """
    from tradingagents.dataflows.config import get_config

    lang = str(get_config().get("output_language", "English") or "English").strip()
    if not lang:
        lang = "English"
    is_english = lang.lower() == "english"

    base = (
        f" CRITICAL LANGUAGE RULE: Write your entire response in {lang}, "
        f"including all headings, section titles, labels, analysis, and "
        f"conclusions. Do not switch languages mid-response. Source materials "
        f"(tool outputs, news headlines, filings, calendars, fundamentals "
        f"tables, prior agent or debate messages) may be in another language "
        f"— paraphrase that evidence into {lang}; do not paste foreign-language "
        f"body paragraphs into the report."
    )

    if is_english:
        return (
            base
            + " Keep official non-English company names from the Resolved "
            + "identity when provided; keep tickers and exchange codes "
            + "unchanged."
        )

    return (
        base
        + " Do not leave English template phrases such as 'TRANSACTION "
        + "PROPOSAL', 'FINAL TRANSACTION PROPOSAL', 'Overall Sentiment', "
        + "'Recommendation', or 'Rationale'. Company-name rule (separate from "
        + "body language): prefer the Resolved identity Company name; if tool "
        + "data already provides a Chinese name, use that exact Chinese name; "
        + "if the name is Latin-script English, keep that English spelling by "
        + "default and never invent a phonetic Chinese transliteration (e.g. "
        + "do not turn JOVE into 杰夫 or 杰美特). Well-known companies may use "
        + f"their commonly accepted {lang} name (e.g. Apple → 苹果, Tencent → "
        + "腾讯). Keep tickers and exchange codes unchanged."
    )


def get_transaction_proposal_instruction() -> str:
    """Remind analysts that the trader proposal marker is not their job.

    Graph routing no longer greps for this phrase; it remains only so
    free-text analysts do not steal the Trader's chrome and confuse readers
    who treat the first ``…recommendation`` they see as the portfolio decision.
    """
    from tradingagents.agents.utils.report_i18n import (
        get_transaction_proposal_phrase,
        localize_report_value,
    )

    phrase = get_transaction_proposal_phrase()
    actions = "/".join(
        localize_report_value(token) for token in ("Buy", "Hold", "Sell")
    )
    return (
        f" Do not conclude or prefix your report with {phrase}. "
        f"That label is reserved for the Trader's later **{actions}** deliverable. "
        f"Your section only supplies analyst evidence for later debate — "
        f"it is not the team's final portfolio decision."
    )


def get_section_recommendation_instruction(section: str) -> str:
    """Tell an analyst how to label a directional view for its own section."""
    from tradingagents.agents.utils.report_i18n import (
        get_analyst_recommendation_phrase,
        get_report_language,
        get_transaction_proposal_phrase,
    )

    label = get_analyst_recommendation_phrase(section)
    reserved = get_transaction_proposal_phrase()
    if get_report_language() == "chinese":
        return (
            f" 若需要给出方向性结论，请使用「{label}：…」作为小节标题，"
            f"并写明这仅代表本环节观点，不是组合最终决策。"
            f"不要使用「{reserved}」或「最终交易建议」这类措辞。"
        )
    return (
        f" If you state a directional view, conclude with "
        f"'{label}: …' and make clear it is only this section's view, "
        f"not the team's final portfolio decision. "
        f"Do not use '{reserved}', 'FINAL TRANSACTION PROPOSAL', "
        f"or 'final trading recommendation' wording."
    )


def get_chart_slot_instruction(section: str) -> str:
    """Ask market/fundamentals analysts to reserve closed chart slots in markdown.

    The UI renders verified analysis-time snapshots at these comments. Other
    sections do not get charts; unknown ids are ignored at read time.
    """
    if section == "market":
        slots = (
            "- Price structure / moving averages / Bollinger: "
            "<!-- chart:price_structure -->\n"
            "- RSI / relative strength: <!-- chart:rsi -->\n"
            "- MACD / DIF / DEA: <!-- chart:macd -->\n"
        )
    elif section == "fundamentals":
        slots = (
            "- Income statement / revenue / operating income / net income: "
            "<!-- chart:income -->\n"
            "- Cash flow / operating cash flow / FCF: <!-- chart:cashflow -->\n"
            "- Quality / leverage / cash conversion: <!-- chart:quality -->\n"
        )
    else:
        return ""
    return (
        " Keep all three subsection headings even if the discussion is short. "
        "Use ##, ###, or ####. Immediately after each heading (or a one-sentence "
        "intro), insert the matching HTML comment on its own line. Insert every "
        "listed comment exactly once; do not omit a slot because evidence is thin.\n"
        f"{slots}"
        "Do not invent other chart ids. Do not replace the comments with images, "
        "ASCII charts, or Mermaid. They reserve placement for verified snapshots "
        "rendered by the product."
    )


def _clean_identity_value(value: Any) -> str | None:
    """Return a trimmed string, or None for empty / placeholder-ish values."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or cleaned.lower() in {"none", "n/a", "nan", "null"}:
        return None
    return cleaned


@functools.lru_cache(maxsize=256)
def resolve_instrument_identity(ticker: str) -> dict:
    """Resolve deterministic identity metadata (company name, sector, …) for a ticker.

    This exists to stop the pipeline from hallucinating a *different* company
    when a chart pattern suggests a different industry than the real one
    (#814): without a ground-truth name, the market analyst would pattern-match
    the price action to a narrative and invent an identity that then cascaded
    through every downstream agent.

    Best-effort by design: if identity data is unavailable or the provider
    doesn't recognise the ticker, we return ``{}`` and the caller falls back to
    ticker-only context rather than failing before analysis starts. Cached so
    the lookup happens at most once per ticker per process.
    """
    try:
        info = get_instrument_identity(ticker)
    except Exception as exc:  # noqa: BLE001 — fail open, never block the run
        logger.debug("Could not resolve instrument identity for %s: %s", ticker, exc)
        return {}

    identity: dict[str, str] = {}
    company_name = _clean_identity_value(info.get("company_name"))
    if company_name:
        identity["company_name"] = company_name
    english_name = _clean_identity_value(info.get("english_name"))
    if english_name and english_name != company_name:
        identity["english_name"] = english_name
    for source_key, target_key in (
        ("sector", "sector"),
        ("industry", "industry"),
        ("exchange", "exchange"),
        ("quote_type", "quote_type"),
        ("quote_currency", "quote_currency"),
        ("fundamental_currency", "fundamental_currency"),
    ):
        value = _clean_identity_value(info.get(source_key))
        if value:
            identity[target_key] = value
    return identity


def merge_display_name_into_identity(
    identity: Mapping[str, str] | None,
    display_name: str | None,
    *,
    english_name: str | None = None,
) -> dict[str, str]:
    """Prefer submit-time UI display name as the primary company label.

    TradingView English ``description`` alone is a common source of
    localized-report name hallucinations. The UI already prefers
    ``local_description``; when that name was captured at job submit, inject it
    as ground truth while retaining any alternate English name.
    """
    merged = dict(identity or {})
    preferred = _clean_identity_value(display_name)
    if preferred:
        existing = merged.get("company_name")
        if existing and existing != preferred:
            merged.setdefault("english_name", existing)
        merged["company_name"] = preferred
        if merged.get("english_name") == preferred:
            merged.pop("english_name", None)

    preferred_english = _clean_identity_value(english_name)
    company = merged.get("company_name")
    if (
        preferred_english
        and preferred_english != company
    ):
        merged["english_name"] = preferred_english
    elif merged.get("english_name") == company:
        merged.pop("english_name", None)
    return merged


def build_instrument_context(
    ticker: str,
    asset_type: str = "stock",
    identity: Mapping[str, str] | None = None,
) -> str:
    """Describe the exact instrument so agents preserve identity and ticker.

    When ``identity`` is provided (resolved deterministically via
    :func:`resolve_instrument_identity`), the company name and business
    classification are injected so agents anchor to the real company rather
    than pattern-matching the price chart to a wrong one (#814).
    """
    is_crypto = asset_type == "crypto"
    instrument_label = "asset" if is_crypto else "instrument"
    context = (
        f"The {instrument_label} to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`, `-USD`)."
    )

    details = []
    if identity:
        name = identity.get("company_name") or identity.get("name")
        if name:
            details.append(f"{'Name' if is_crypto else 'Company'}: {name}")
        english = identity.get("english_name")
        if english and english != name:
            details.append(f"English name: {english}")
        sector, industry = identity.get("sector"), identity.get("industry")
        if sector and industry:
            details.append(f"Business classification: {sector} / {industry}")
        elif sector:
            details.append(f"Sector: {sector}")
        elif industry:
            details.append(f"Industry: {industry}")
        if identity.get("exchange"):
            details.append(f"Exchange: {identity['exchange']}")
        if identity.get("quote_currency"):
            details.append(f"Quote currency: {identity['quote_currency']}")
        if identity.get("fundamental_currency"):
            details.append(
                f"Fundamental reporting currency: {identity['fundamental_currency']}"
            )

    if details:
        context += (
            f" Resolved identity: {'; '.join(details)}. "
            "Do not substitute a different company or ticker unless a tool "
            "result explicitly disproves this resolved identity. "
            "Use this resolved company name in reports. "
            "If Company is Chinese, use that exact Chinese name; if Company "
            "(or English name) is Latin-script English, keep that English "
            "spelling by default even in non-English reports — never invent a "
            "phonetic Chinese name for the same ticker. Well-known companies "
            "may use a commonly accepted local-language name."
        )

    if is_crypto:
        context += (
            " Treat it as a crypto asset rather than a company, and do not "
            "assume company fundamentals are available."
        )
    return context


def get_instrument_context_from_state(state: Mapping[str, Any]) -> str:
    """Return the instrument context for the current run.

    Prefers the identity-resolved context computed once at run start and
    stored on the state (see ``TradingAgentsGraph.resolve_instrument_context``).
    Falls back to a ticker-only context — with no network lookup — when the
    state was constructed without it (bare programmatic states, tests), so a
    consumer is never forced to make a provider call mid-graph.
    """
    context = state.get("instrument_context")
    if isinstance(context, str) and context.strip():
        return context
    return build_instrument_context(
        str(state["company_of_interest"]),
        state.get("asset_type", "stock"),
    )


def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add a context-anchored placeholder.

        The placeholder must not be a bare ``"Continue"``: some
        OpenAI-compatible providers interpret that literally as the user task
        and produce output about the word "continue" instead of analysing the
        instrument (#888). Anchoring it to the resolved instrument context and
        date keeps the next analyst on-task even if the provider treats the
        placeholder as a standalone request.
        """
        messages = state["messages"]
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        instrument_context = get_instrument_context_from_state(state)
        trade_date = state.get("trade_date", "the requested date")
        placeholder = HumanMessage(
            content=(
                f"Proceed with your assigned analysis for this workflow. "
                f"{instrument_context} The analysis date is {trade_date}."
            )
        )
        return {"messages": removal_operations + [placeholder]}

    return delete_messages

