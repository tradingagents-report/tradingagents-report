# TradingAgents/graph/conditional_logic.py

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.report_i18n import iter_label_spellings


class ConditionalLogic:
    """Handles conditional logic for determining graph flow."""

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        """Initialize with configuration parameters."""
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds

    @staticmethod
    def _is_bull_turn(latest_speaker: str, current_response: str) -> bool:
        """True when the last research-debate turn was the bull side.

        Prefer the stable ``latest_speaker`` wire id (Bull / Bear). Fall back to
        localized ``current_response`` prefixes so mid-run checkpoints from
        before ``latest_speaker`` still alternate correctly under i18n.
        """
        speaker = (latest_speaker or "").strip()
        if speaker.startswith("Bull"):
            return True
        if speaker.startswith("Bear"):
            return False

        text = current_response or ""
        if text.startswith("Bull"):
            return True
        return any(
            text.startswith(label)
            for label in iter_label_spellings("bull_analyst")
        )

    def should_continue_market(self, state: AgentState):
        """Determine if market analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_market"
        return "Msg Clear Market"

    def should_continue_social(self, state: AgentState):
        """Determine if sentiment-analyst tool round should continue.

        Method name keeps the legacy ``social`` suffix to match the
        ``AnalystType.SOCIAL = "social"`` wire value (saved-config
        back-compat); the returned ``clear_node`` label uses the v0.2.5
        rename so it matches the node registered by the execution plan.
        """
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_social"
        return "Msg Clear Sentiment"

    def should_continue_news(self, state: AgentState):
        """Determine if news analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_news"
        return "Msg Clear News"

    def should_continue_fundamentals(self, state: AgentState):
        """Determine if fundamentals analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_fundamentals"
        return "Msg Clear Fundamentals"

    def should_continue_debate(self, state: AgentState) -> str:
        """Determine if debate should continue."""

        debate = state["investment_debate_state"]
        if (
            debate["count"] >= 2 * self.max_debate_rounds
        ):  # 3 rounds of back-and-forth between 2 agents
            return "Research Manager"
        if self._is_bull_turn(
            str(debate.get("latest_speaker") or ""),
            str(debate.get("current_response") or ""),
        ):
            return "Bear Researcher"
        return "Bull Researcher"

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """Determine if risk analysis should continue."""
        if (
            state["risk_debate_state"]["count"] >= 3 * self.max_risk_discuss_rounds
        ):  # 3 rounds of back-and-forth between 3 agents
            return "Portfolio Manager"
        if state["risk_debate_state"]["latest_speaker"].startswith("Aggressive"):
            return "Conservative Analyst"
        if state["risk_debate_state"]["latest_speaker"].startswith("Conservative"):
            return "Neutral Analyst"
        return "Aggressive Analyst"
