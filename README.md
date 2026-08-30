# TradingAgents Report

**TradingAgents Report** 是一套多智能体投研框架：把一只标的拆成证据收集、多空辩论、交易提案、风险审查，以及投资组合经理的五档评级。产物是研究报告和结构化决策卡，**不是**券商接入或真实下单。

本仓库是可自托管的研究引擎。不想自己跑模型与数据源时，可以直接使用托管研究台：

- 官网：[tradingagentsreport.com](https://www.tradingagentsreport.com)
- 研究台：[agent.tradingagentsreport.com](https://agent.tradingagentsreport.com)

本项目基于 [Tauric Research / TradingAgents](https://github.com/TauricResearch/TradingAgents)（Apache 2.0）增强，默认行情走 [TradingView Data API](https://www.tradingviewapi.com/)。

> 仅供研究参考，不构成投资建议。TradingView Data API 为非官方第三方数据服务，与 TradingView, Inc. 无隶属关系。

## 相对上游的增强

| 能力 | 说明 |
|---|---|
| TradingView Data API | 交易所级代码、日线、指标、基本面、新闻、日历、同行、多周期 TA |
| 结构化决策 | 分析师分区信号、`decision_brief`、分析日边界内的价格/基本面图表快照 |
| 多市场标的 | `600519.SS`、`HKEX:700`、`NASDAQ:AAPL` 确定性解析 |
| A 股可选源 | AKShare / Tushare / BaoStock / PandaAI（`pip install ".[china-data]"`） |
| 缓存 | 默认进程内 TTL；可选 Redis 跨进程复用，减少 API 调用 |

上游已有的多智能体辩论、多 LLM Provider、checkpoint、五档评级，这里继续保留。

## 快速开始

### 1. 申请行情 Key

打开 [https://www.tradingviewapi.com/](https://www.tradingviewapi.com/)，在 Console 领取 API Key。完整多市场能力需要该 Key；未配置时会回退到 Yahoo Finance 等已启用供应商。

### 2. 安装

```bash
git clone https://github.com/tradingagents-report/tradingagents-report.git
cd tradingagents-report
python3.12 -m venv .venv
source .venv/bin/activate
pip install .
```

可选：

```bash
pip install ".[china-data]"   # A 股适配器
pip install ".[bedrock]"      # Amazon Bedrock
```

### 3. 配置

```bash
cp .env.example .env
```

最少填写：

```bash
OPENAI_API_KEY=...           # 或你选用的其他 LLM Provider
TRADINGVIEW_API_KEY=...      # https://www.tradingviewapi.com/
```

客户端使用 `Authorization: Bearer` 调用 `https://api.tradingviewapi.com`。旧的 `TRADINGVIEW_RAPIDAPI_KEY` 仍可作为 Console 凭据；只有设置 `TRADINGVIEW_BACKEND=rapid` 才会改走 RapidAPI 主机。

**不需要 Redis 或 PostgreSQL。** 行情缓存默认在进程内存中。多进程分析同一标的时，可设置 `REDIS_URL` 共享缓存、节省额度。

### 4. 运行 CLI

```bash
tradingagents-report
# 或
tradingagents
```

按提示选择标的、日期、模型和辩论轮次。

### Python

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"
config["deep_think_llm"] = "gpt-5.5"
config["quick_think_llm"] = "gpt-5.4-mini"

ta = TradingAgentsGraph(config=config)
_, decision = ta.propagate("NASDAQ:AAPL", "2026-08-01")
print(decision)
```

## 数据源

默认链优先 TradingView，然后 yfinance / Alpha Vantage。宏观用 FRED，预测市场用 Polymarket。

A 股示例：`600519.SS`、`000001.SZ`。港股：`0700.HK`。未配置 TradingView Key 时，仍可走 Yahoo 兼容后缀。

详见 [`tradingagents/dataflows/README.md`](tradingagents/dataflows/README.md) 与 [`docs/DATA_SOURCE_CONFIGURATION.md`](docs/DATA_SOURCE_CONFIGURATION.md)。

## 许可

Apache License 2.0。请保留上游 Tauric Research 的版权声明，见 `LICENSE` 与 `NOTICE`。

本仓库不转授任何第三方行情或 LLM 供应商的数据权利。使用 TradingView Data API 须遵守其[服务条款](https://www.tradingviewapi.com/)。
