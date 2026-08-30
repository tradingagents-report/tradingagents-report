# Agent 模块

`agents` 定义投研流程中的角色节点、角色之间传递的状态，以及角色调用数据源和 LLM 的公共工具。各角色输出研究意见、结构化计划或决策建议；本目录不包含券商接入、资金管理或真实下单执行。

## 协作边界

这些工厂函数由图编排层创建并接入 LangGraph。典型流程是：分析师分别形成市场、基本面、新闻和情绪意见；多空研究员辩论后由研究经理生成投资计划；交易员将计划转换为交易建议；风险辩论角色评估该建议，最后由投资组合经理综合风险意见给出最终决策。

数据访问由 `utils` 中的工具封装进入 `tradingagents.dataflows.interface.route_to_vendor()`，因此角色本身不直接耦合具体数据供应商。LLM 模型则由图的运行配置注入各 `create_*` 工厂函数。

## 子目录

### `analysts/`

一线分析师节点，分别产出不同维度的标的研究结果：

| 模块 | 角色职责 |
| --- | --- |
| `market_analyst.py` | 基于历史行情和技术指标分析价格走势、成交量与技术面。 |
| `fundamentals_analyst.py` | 分析公司概览、财务报表和基本面指标。 |
| `news_analyst.py` | 汇总个股、市场新闻及内部人交易等事件信息。 |
| `sentiment_analyst.py` | 合并新闻、Reddit 与 StockTwits 信号，生成标的情绪判断。 |
| `social_media_analyst.py` | 对旧模块名的兼容层，转向当前的情绪分析师实现。 |

### `researchers/`

投资观点辩论角色。`bull_researcher.py` 从看多角度审视分析师结论，`bear_researcher.py` 从看空角度提出反驳和风险；两者将回合内容更新到 `investment_debate_state`，为研究经理形成计划提供正反两面的依据。

### `risk_mgmt/`

风险评估辩论角色。`aggressive_debator.py`、`neutral_debator.py` 和 `conservative_debator.py` 分别采用进取、中性和保守的风险立场审视交易建议，并把讨论结果写入 `risk_debate_state`。它们仅评估建议的风险与适当性，不执行交易。

### `trader/`

`trader.py` 中的交易员角色将研究经理的结构化投资计划转换为具体的交易提案，包括方向、理由和计划上下文，供后续风险评估使用。这里的“交易”是研究流程中的建议表达，不会连接交易所或提交订单。

### `managers/`

协调研究和决策输出的管理角色：

| 模块 | 角色职责 |
| --- | --- |
| `research_manager.py` | 综合多空研究辩论，输出供交易员使用的结构化投资计划。 |
| `portfolio_manager.py` | 综合风险辩论与交易提案，输出最终的投资组合决策。 |

### `utils/`

跨角色共享的工具、状态与输出辅助逻辑：

| 模块 | 职责 |
| --- | --- |
| `agent_utils.py` | 聚合公开数据工具，提供语言指令和标的身份解析等通用帮助函数。 |
| `agent_states.py` | 定义分析、投资辩论和风险辩论在 LangGraph 中传递的状态。 |
| `core_stock_tools.py` | 路由历史行情和 OHLCV 请求。 |
| `technical_indicators_tools.py` | 路由技术指标请求，并处理多个指标参数。 |
| `fundamental_data_tools.py` | 路由基本面、资产负债表、现金流量表和利润表请求。 |
| `news_data_tools.py` | 路由个股新闻、市场新闻和内部人交易请求。 |
| `macro_data_tools.py` | 路由 FRED 等宏观指标请求。 |
| `prediction_markets_tools.py` | 路由预测市场概率请求。 |
| `market_data_validation_tools.py` | 构建经过数据质量与日期边界校验的市场快照。 |
| `structured.py` | 调用 LLM 的结构化输出，并在不支持或解析失败时降级为文本输出。 |
| `rating.py` | 定义统一的五档评级词汇，并从文本中稳定提取评级。 |
| `memory.py` | 管理可选的追加式 Markdown 决策记忆日志。 |

## 顶层模块

`schemas.py` 定义由 Agent 产出的 Pydantic 结构化模型，包括研究计划、交易动作、风险和投资组合相关字段；它同时规范共享的 `PortfolioRating` 与 `TraderAction` 枚举。`__init__.py` 当前不暴露额外公共接口。

## 开发约定

- 新增角色应保持“工厂函数创建节点、节点读取状态并返回状态更新”的既有模式，由图编排层决定调用顺序。
- 角色需要外部数据时，优先复用 `utils` 的工具包装；供应商选择、fallback 和认证应保留在 `dataflows` 层。
- 新增或修改状态字段时，同时检查图装配与路由逻辑，确保角色之间的读写契约一致。
- 需要稳定机器可读输出的角色，优先复用 `schemas.py` 与 `structured.py` 的降级机制，避免把 Provider 或模型差异散落到角色逻辑中。
