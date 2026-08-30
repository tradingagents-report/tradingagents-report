# Agents

`agents` defines the research-graph roles, the state they pass, and the shared
tools they use to call data sources and LLMs. Roles emit research opinions,
structured plans, or decision recommendations. This package does not include
broker connectivity, cash management, or live order execution.

## Collaboration

Graph setup constructs these factories and wires them into LangGraph. Typical
flow: analysts form market, fundamental, news, and sentiment views; bull and
bear researchers debate; the research manager writes an investment plan; the
trader turns that plan into a proposal; risk debaters review the proposal; the
portfolio manager issues the final decision.

Data access goes through tools in `utils` into
`tradingagents.dataflows.interface.route_to_vendor()`, so roles do not couple
to a vendor package. LLM instances are injected by graph runtime config into
each `create_*` factory.

## Packages

### `analysts/`

First-line analyst nodes, one research slice each:

| Module | Role |
| --- | --- |
| `market_analyst.py` | Price, volume, and technicals from history and indicators |
| `fundamentals_analyst.py` | Company overview, statements, and fundamental metrics |
| `news_analyst.py` | Equity news, market news, and insider activity |
| `sentiment_analyst.py` | Combined news, Reddit, and StockTwits sentiment |
| `social_media_analyst.py` | Compatibility shim toward the current sentiment analyst |

### `researchers/`

Investment-view debate. `bull_researcher.py` argues the long case;
`bear_researcher.py` argues the short case and risks. Both write into
`investment_debate_state` for the research manager.

### `risk_mgmt/`

Risk debate. `aggressive_debator.py`, `neutral_debator.py`, and
`conservative_debator.py` review the trade proposal from aggressive, neutral, and
conservative stances and write `risk_debate_state`. They evaluate the proposal;
they do not trade.

### `trader/`

`trader.py` converts the research manager's structured plan into a concrete
proposal (direction, rationale, plan context) for risk review. "Trade" here is
a research recommendation, not an exchange order.

### `managers/`

Coordination roles:

| Module | Role |
| --- | --- |
| `research_manager.py` | Synthesizes the bull/bear debate into a structured plan |
| `portfolio_manager.py` | Synthesizes risk debate and the trade proposal into the final decision |

### `utils/`

Shared tools, state, and output helpers:

| Module | Role |
| --- | --- |
| `agent_utils.py` | Public data tools, language instructions, identity helpers |
| `agent_states.py` | Analysis, investment-debate, and risk-debate LangGraph state |
| `core_stock_tools.py` | Historical prices and OHLCV |
| `technical_indicators_tools.py` | Indicator requests |
| `fundamental_data_tools.py` | Fundamentals and statements |
| `news_data_tools.py` | Equity news, market news, insider activity |
| `macro_data_tools.py` | FRED and other macro series |
| `prediction_markets_tools.py` | Prediction-market probabilities |
| `market_data_validation_tools.py` | Quality-checked market snapshots |
| `structured.py` | Structured LLM output with text fallback |
| `rating.py` | Five-level rating vocabulary and extraction |
| `memory.py` | Optional append-only Markdown decision memory |

## Top-level modules

`schemas.py` holds Pydantic models produced by agents (research plan, trade
action, risk and portfolio fields) plus shared `PortfolioRating` and
`TraderAction` enums. `__init__.py` does not export extra public API.

## Conventions

- New roles keep the factory → node reads state → returns state-update pattern.
  Graph setup owns call order.
- Prefer `utils` wrappers for external data. Vendor choice, fallback, and
  auth stay in `dataflows`.
- When changing state fields, check graph assembly and routing so read/write
  contracts stay aligned.
- Roles that need machine-readable output should reuse `schemas.py` and the
  `structured.py` fallback instead of forking provider-specific logic.
