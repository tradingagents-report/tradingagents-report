"""Portfolio Manager: synthesises the risk-analyst debate into the final decision.

Uses LangChain's ``with_structured_output`` so the LLM produces a typed
``PortfolioDecision`` directly, in a single call.  The result is rendered
back to markdown for storage in ``final_trade_decision`` so memory log,
CLI display, and saved reports continue to consume the same shape they do
today.  When a provider does not expose structured output, the agent falls
back gracefully to free-text generation and recovers a decision brief via a
lighter second-pass extraction or deterministic salvage.
"""

from __future__ import annotations

from tradingagents.agents.schemas import (
    DecisionStance,
    PortfolioDecision,
    PortfolioDecisionRecovery,
    SectionSignal,
    SectionStances,
    decision_brief_from_portfolio,
    render_pm_decision,
)
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.decision_brief_recovery import (
    extract_decision_brief_from_text,
    salvage_decision_brief_from_text,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_with_fallback,
)


def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")
    recovery_llm = bind_structured(
        llm,
        PortfolioDecisionRecovery,
        "Portfolio Manager brief recovery",
    )

    def portfolio_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state)

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]
        source_reports = {
            "Market": state.get("market_report") or "REPORT_UNAVAILABLE",
            "Sentiment": state.get("sentiment_report") or "REPORT_UNAVAILABLE",
            "News": state.get("news_report") or "REPORT_UNAVAILABLE",
            "Fundamentals": state.get("fundamentals_report") or "REPORT_UNAVAILABLE",
        }
        source_report_context = "\n\n".join(
            f"**{name} Analyst Report:**\n{report}"
            for name, report in source_reports.items()
        )
        section_stances = _section_stances_from_state(state)
        source_signal_context = "\n".join(
            f"- {name}: {signal.stance.value} — {signal.note}"
            for name, signal in (
                ("Market", section_stances.market),
                ("Sentiment", section_stances.sentiment),
                ("News", section_stances.news),
                ("Fundamentals", section_stances.fundamentals),
            )
        )

        past_context = state.get("past_context", "")
        lessons_line = (
            f"- Lessons from prior decisions and outcomes:\n{past_context}\n"
            if past_context
            else ""
        )

        prompt = f"""As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.

{instrument_context}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry

**Final-decision discipline:**
- Always provide a positive numeric price_target in the instrument's quote currency for every rating, including Hold, Underweight, and Sell. Make it consistent with the rating and time horizon; for Underweight/Sell, use the expected downside or exit-value level rather than omitting it.
- If structured output is unavailable, put the final rating and price target in explicit top-level fields or a two-column Markdown summary table; do not bury them only in prose.
- Adjudicate neutrally across the five-tier scale. CapEx/FCF stress, franchise quality, net cash, sell-side targets, peer valuation, and multi-timeframe technicals are inputs to weigh — not automatic reasons to Prefer Underweight or to block Overweight/Buy.
- Incomplete cash-return proof or a broken daily trend argues for caution in sizing and confirmation levels; it does not by itself force Underweight/Sell when the constructive case is better supported overall.
- Ground the executive summary in the risk debate's best-supported plan. When aggressive and conservative views conflict, pick the side with stronger, more specific evidence — do not resolve ties by defaulting to capital protection.

**Context:**
- Research Manager's investment plan: **{research_plan}**
- Trader's transaction proposal: **{trader_plan}**
{lessons_line}
**Source Analyst Reports:**
{source_report_context}

**Analyst-owned directional signals (use as evidence; do not rewrite them):**
{source_signal_context}

**Risk Analysts Debate History:**
{history}

---

Be decisive and ground every conclusion in specific evidence from the analysts.{get_language_instruction()}"""

        invocation = invoke_structured_with_fallback(
            structured_llm,
            llm,
            prompt,
            render_pm_decision,
            "Portfolio Manager",
        )
        final_trade_decision = invocation.text
        diagnostic_events: list[dict[str, str]] = []
        if invocation.value is not None:
            decision_brief = decision_brief_from_portfolio(
                invocation.value,
                section_stances,
            ).model_dump(mode="json")
        else:
            reason = invocation.fallback_reason or "unknown"
            diagnostic_events.append(
                {
                    "kind": "warning",
                    "message": (
                        "Portfolio Manager used free-text fallback "
                        f"(reason: {reason})."
                    ),
                }
            )
            recovered_brief = extract_decision_brief_from_text(
                recovery_llm,
                final_trade_decision,
                section_stances,
            )
            if recovered_brief is not None:
                decision_brief = recovered_brief
                recovery_mode = "structured recovery"
            else:
                decision_brief = salvage_decision_brief_from_text(
                    final_trade_decision,
                    section_stances,
                )
                recovery_mode = (
                    "deterministic recovery"
                    if decision_brief is not None
                    else "unavailable"
                )
            diagnostic_events.append(
                {
                    "kind": "warning",
                    "message": (
                        "Decision brief recovered from Portfolio Manager free text "
                        f"({recovery_mode})."
                        if decision_brief is not None
                        else "Decision brief unavailable after free-text recovery."
                    ),
                }
            )

        new_risk_debate_state = {
            "judge_decision": final_trade_decision,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": final_trade_decision,
            "decision_brief": decision_brief,
            "diagnostic_events": diagnostic_events,
        }

    return portfolio_manager_node


def _section_stances_from_state(state: dict) -> SectionStances:
    def signal(key: str, label: str) -> SectionSignal:
        try:
            return SectionSignal.model_validate(state.get(key))
        except Exception:  # noqa: BLE001 - optional state must degrade safely
            return SectionSignal(
                stance=DecisionStance.UNAVAILABLE,
                note=f"{label} did not produce a structured signal.",
            )

    return SectionStances(
        market=signal("market_signal", "Market Analyst"),
        sentiment=signal("sentiment_signal", "Sentiment Analyst"),
        news=signal("news_signal", "News Analyst"),
        fundamentals=signal("fundamentals_signal", "Fundamentals Analyst"),
    )
