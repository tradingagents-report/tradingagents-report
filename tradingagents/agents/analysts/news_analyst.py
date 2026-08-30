from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.schemas import SectionSignal
from tradingagents.agents.utils.agent_utils import (
    get_earnings_calendar,
    get_economic_calendar,
    get_global_news,
    get_insider_transactions,
    get_instrument_context_from_state,
    get_language_instruction,
    get_macro_indicators,
    get_news,
    get_prediction_markets,
    get_section_recommendation_instruction,
    get_transaction_proposal_instruction,
)
from tradingagents.agents.utils.section_signal import extract_section_signal
from tradingagents.agents.utils.structured import bind_structured


def create_news_analyst(llm):
    structured_signal_llm = bind_structured(llm, SectionSignal, "News Analyst signal")

    def news_analyst_node(state):
        current_date = state["trade_date"]
        asset_type = state.get("asset_type", "stock")
        asset_label = "company" if asset_type == "stock" else "asset"
        instrument_context = get_instrument_context_from_state(state)

        tools = [
            get_news,
            get_global_news,
            get_insider_transactions,
            get_earnings_calendar,
            get_economic_calendar,
            get_macro_indicators,
            get_prediction_markets,
        ]

        system_message = (
            f"You are a news researcher tasked with analyzing recent news and trends over the past week. Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. Use the available tools: get_news(ticker, start_date, end_date) for {asset_label}-specific news by ticker symbol, get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news, get_insider_transactions(ticker) for recent insider buys/sells when available, get_earnings_calendar(curr_date, look_forward_days, market, ticker) for upcoming/recent earnings event risk (pass the ticker to focus on this name; omit market to infer it from the exchange catalog), get_economic_calendar(curr_date, look_back_days, look_forward_days, market) for scheduled macro releases, get_macro_indicators(indicator, curr_date, look_back_days) to ground macro commentary in actual data from FRED (e.g. 'cpi', 'core_pce', 'unemployment', 'fed_funds_rate', '10y_treasury', 'yield_curve'), and get_prediction_markets(topic, limit) for live market-implied probabilities of forward-looking events (e.g. 'Fed rate cut', 'recession 2026', geopolitical or sector events). If a calendar or optional tool returns DATA_UNAVAILABLE, note the gap and continue. Treat actual prints after the analysis date as unavailable — do not invent them. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + get_section_recommendation_instruction("news")
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
            "news_report": report,
        }
        if report:
            update["news_signal"] = extract_section_signal(
                structured_signal_llm,
                report,
                "News Analyst",
            )
        return update

    return news_analyst_node
