from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.schemas import SectionSignal
from tradingagents.agents.utils.agent_utils import (
    get_balance_sheet,
    get_cashflow,
    get_chart_slot_instruction,
    get_fundamentals,
    get_income_statement,
    get_instrument_context_from_state,
    get_language_instruction,
    get_peer_comparison,
    get_section_recommendation_instruction,
    get_transaction_proposal_instruction,
)
from tradingagents.agents.utils.section_signal import extract_section_signal
from tradingagents.agents.utils.structured import bind_structured


def create_fundamentals_analyst(llm):
    structured_signal_llm = bind_structured(
        llm,
        SectionSignal,
        "Fundamentals Analyst signal",
    )

    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
            get_peer_comparison,
        ]

        system_message = (
            "You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
            + " Use the available tools: `get_fundamentals` for comprehensive company analysis (including valuation ratios, beta, earnings dates, analyst consensus/price targets, and dividend summary when present), `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements, and `get_peer_comparison` for same-sector relative valuation (PE, dividend yield, market cap vs peers). If peer comparison returns DATA_UNAVAILABLE, note the gap and continue."
            + " Valuation and cash-quality evidence (present both sides fairly; do not hard-bias the section rating):"
            + " (1) Treat sell-side ratings, average/median price targets, and implied upside as lagging consensus — useful context, not standalone proof of undervaluation or overvaluation."
            + " (2) Weigh peer PE / headline TTM PE together with earnings quality: if large non-operating/one-time items or CapEx-driven FCF compression distort the picture, say so and explain how that affects (not automatically vetoes) a bullish or bearish read."
            + " (3) Prefer operating income, operating cash flow, CapEx intensity, free cash flow, and normalized earnings over headline net income/EPS when they diverge — cite the divergence as evidence either side can use."
            + " (4) If CapEx exceeds operating cash flow or FCF turns negative while revenue/operating profit still look strong, report both the growth strength and the cash-return gap with the evidence still missing; let the overall balance of facts drive the section view rather than assuming re-pricing weakness."
            + get_section_recommendation_instruction("fundamentals")
            + get_chart_slot_instruction("fundamentals")
            + get_language_instruction(),
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
            "fundamentals_report": report,
        }
        if report:
            update["fundamentals_signal"] = extract_section_signal(
                structured_signal_llm,
                report,
                "Fundamentals Analyst",
            )
        return update

    return fundamentals_analyst_node
