"""Research Manager: turns the bull/bear debate into a structured investment plan for the trader."""

from __future__ import annotations

from tradingagents.agents.schemas import ResearchPlan, render_research_plan
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_research_manager(llm):
    structured_llm = bind_structured(llm, ResearchPlan, "Research Manager")

    def research_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state)
        history = state["investment_debate_state"].get("history", "")

        investment_debate_state = state["investment_debate_state"]

        prompt = f"""As the Research Manager and debate facilitator, your role is to critically evaluate this round of debate and deliver a clear, actionable investment plan for the trader.

{instrument_context}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction in the bull thesis; recommend taking or growing the position
- **Overweight**: Constructive view; recommend gradually increasing exposure
- **Hold**: Balanced view; recommend maintaining the current position
- **Underweight**: Cautious view; recommend trimming exposure
- **Sell**: Strong conviction in the bear thesis; recommend exiting or avoiding the position

Commit to a clear stance whenever the debate's strongest arguments warrant one; reserve Hold for situations where the evidence on both sides is genuinely balanced. Do not default to Underweight/Sell merely because evidence is incomplete or mixed — weigh bull and bear arguments symmetrically, and let the stronger, better-supported case decide.

**Evidence-weighing guidance (use facts from the debate; do not hard-default any rating):**
- Cash-flow quality (CapEx vs operating cash flow, FCF trend, monetization proof) and growth/franchise strength are both material. Present how each side uses them; upgrade or cut exposure only when that side's evidence is stronger overall — not because cash-flow uncertainty alone forces Underweight.
- Sell-side price targets, peer PE discounts, and headline TTM PE are lagging context for either thesis. They should not be the sole basis for Buy/Overweight or Sell/Underweight when earnings quality or FCF diverge from the headline story.
- When daily structure and longer-horizon gauges conflict, state the conflict and size the plan to the time horizon that the stronger evidence supports (add, hold, or trim). Do not assume shorter-horizon weakness automatically wins, and do not assume longer-horizon strength automatically wins.
- Prefer actionable confirmation levels and position-sizing notes that match the chosen rating, whether constructive or cautious.

---

**Debate History:**
{history}""" + get_language_instruction()

        investment_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_research_plan,
            "Research Manager",
        )

        new_investment_debate_state = {
            "judge_decision": investment_plan,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": investment_plan,
            "latest_speaker": investment_debate_state.get("latest_speaker", ""),
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": investment_plan,
        }

    return research_manager_node
