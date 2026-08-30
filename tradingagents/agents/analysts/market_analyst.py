from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.schemas import SectionSignal
from tradingagents.agents.utils.agent_utils import (
    get_chart_slot_instruction,
    get_indicators,
    get_instrument_context_from_state,
    get_language_instruction,
    get_peer_comparison,
    get_section_recommendation_instruction,
    get_stock_data,
    get_ta_indicators,
    get_ta_summary,
    get_transaction_proposal_instruction,
    get_verified_market_snapshot,
)
from tradingagents.agents.utils.section_signal import extract_section_signal
from tradingagents.agents.utils.structured import bind_structured


def create_market_analyst(llm):
    structured_signal_llm = bind_structured(llm, SectionSignal, "Market Analyst signal")

    def market_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)

        tools = [
            get_stock_data,
            get_indicators,
            get_ta_summary,
            get_ta_indicators,
            get_peer_comparison,
            get_verified_market_snapshot,
        ]

        system_message = (
            """You are a trading assistant tasked with analyzing financial markets. Your role is to select the **most relevant indicators** for a given market condition or trading strategy from the following list. The goal is to choose up to **8 indicators** that provide complementary insights without redundancy. Categories and each category's indicators are:

Moving Averages:
- close_50_sma: 50 SMA: A medium-term trend indicator. Usage: Identify trend direction and serve as dynamic support/resistance. Tips: It lags price; combine with faster indicators for timely signals.
- close_200_sma: 200 SMA: A long-term trend benchmark. Usage: Confirm overall market trend and identify golden/death cross setups. Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries.
- close_10_ema: 10 EMA: A responsive short-term average. Usage: Capture quick shifts in momentum and potential entry points. Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals.

MACD Related:
- macd: MACD: Computes momentum via differences of EMAs. Usage: Look for crossovers and divergence as signals of trend changes. Tips: Confirm with other indicators in low-volatility or sideways markets.
- macds: MACD Signal: An EMA smoothing of the MACD line. Usage: Use crossovers with the MACD line to trigger trades. Tips: Should be part of a broader strategy to avoid false positives.
- macdh: MACD Histogram: Shows the gap between the MACD line and its signal. Usage: Visualize momentum strength and spot divergence early. Tips: Can be volatile; complement with additional filters in fast-moving markets.

Momentum Indicators:
- rsi: RSI: Measures momentum to flag overbought/oversold conditions. Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis.

Volatility Indicators:
- boll: Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. Usage: Acts as a dynamic benchmark for price movement. Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals.
- boll_ub: Bollinger Upper Band: Typically 2 standard deviations above the middle line. Usage: Signals potential overbought conditions and breakout zones. Tips: Confirm signals with other tools; prices may ride the band in strong trends.
- boll_lb: Bollinger Lower Band: Typically 2 standard deviations below the middle line. Usage: Indicates potential oversold conditions. Tips: Use additional analysis to avoid false reversal signals.
- atr: ATR: Averages true range to measure volatility. Usage: Set stop-loss levels and adjust position sizes based on current market volatility. Tips: It's a reactive measure, so use it as part of a broader risk management strategy.

Volume-Based Indicators:
- vwma: VWMA: A moving average weighted by volume. Usage: Confirm trends by integrating price action with volume data. Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses.

- Select indicators that provide diverse and complementary information. Avoid redundancy (e.g., do not select both rsi and stochrsi). Also briefly explain why they are suitable for the given market context. When you tool call, please use the exact name of the indicators provided above as they are defined parameters, otherwise your call will fail. Please make sure to call get_stock_data first to retrieve the CSV that is needed to generate indicators. Then use get_indicators with the specific indicator names.

Also call get_ta_summary for multi-timeframe Buy/Sell/Neutral gauges and get_ta_indicators for the curated TradingView snapshot. Optionally call get_peer_comparison for same-sector relative strength (RSI/TA rec/1W-1M vs peers). If a tool returns DATA_UNAVAILABLE, continue with stockstats indicators and note the gap.

Conflict and weighting rules (mandatory for data integrity; keep directional judgment balanced):
- Exact OHLCV, price levels, and daily stockstats values come only from get_verified_market_snapshot. TradingView gauges/indicators are complementary live snapshots, not a second source of truth for exact prices.
- Do not mix TradingView close/EMA/RSI numbers with verified daily figures as if they share the same as-of date. If they conflict, report both with their as-of, then use verified daily figures for exact levels while still weighing multi-timeframe gauges as horizon context.
- When daily structure and 1W/1M gauges disagree, state the conflict explicitly and explain which horizon the section view emphasizes and why. Do not let either timeframe alone dictate Buy or Sell; shorter-horizon weakness and longer-horizon strength are both legitimate inputs.
- Low ADX means trend strength is limited; it does not by itself prove small downside or small upside — treat it as weak-trend context for either side.

When get_ta_indicators is available, explicitly cover these if present (do not stop at RSI/MACD/ADX/classic pivots):
- Oscillator extremes: Stoch.K/D, CCI20, W.R, and their Rec.* scores — note when RSI is only mildly weak/strong while these are deeply oversold or overbought.
- Momentum acceleration: Mom, AO, and any [1]/[2] prior values showing deterioration or improvement.
- Signal breadth both ways: Recommend.MA vs Recommend.Other / Recommend.All — e.g. MA strongly sell while oscillators are mixed, or MA strongly buy while oscillators lag, means incomplete confirmation either way.
- Secondary levels: Ichimoku.BLine, HullMA9, VWMA, BBPower only as supporting context; keep classic pivots as the primary pivot set and ignore Camarilla/Fibonacci/Woodie/Demark clutter unless uniquely informative.

Before writing the final report, call get_verified_market_snapshot for this ticker and the current date, and treat it as the source of truth for any exact OHLCV, price-level, or indicator-value claim. If another tool's output conflicts with the verified snapshot, flag the discrepancy rather than inventing a reconciled number. Do not claim historical validation, support/resistance bounces, or exact percentage moves unless they are directly supported by tool output with concrete dates and prices.

Write a very detailed and nuanced report of the trends you observe. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."""
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + get_section_recommendation_instruction("market")
            + get_chart_slot_instruction("market")
            + get_language_instruction()
        )

        system_prompt = (
            "You are a helpful AI assistant, collaborating with other assistants."
            " Use the provided tools to progress towards answering the question."
            " If you are unable to fully answer, that's OK; another assistant with different tools"
            " will help where you left off. Execute what you can to make progress."
            + get_transaction_proposal_instruction()
            + (
                " You have access to the following tools: {tool_names}."
                " Today's date is {current_date}; treat it as 'now' for all analysis and tool-call date ranges. {instrument_context}\n"
                "{system_message}"
            )
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        update = {
            "messages": [result],
            "market_report": report,
        }
        if report:
            update["market_signal"] = extract_section_signal(
                structured_signal_llm,
                report,
                "Market Analyst",
            )
        return update

    return market_analyst_node
