# TradingAgents Report

**TradingAgents Report** is a multi-agent equity-research framework. It splits a ticker into evidence gathering, bull/bear debate, a trade proposal, risk review, and a five-level portfolio-manager rating. The output is a research report and a structured decision card. It is **not** a broker integration and it does **not** place live orders.

This repository is the self-hosted research engine. If you would rather not run models and data vendors yourself, use the hosted desk:

- Site: [tradingagentsreport.com](https://www.tradingagentsreport.com)
- Desk: [agent.tradingagentsreport.com](https://agent.tradingagentsreport.com)

This project is an Apache 2.0 derivative of [Tauric Research / TradingAgents](https://github.com/TauricResearch/TradingAgents). Market data defaults to [TradingView Data API](https://www.tradingviewapi.com/).

> For research only. Not investment advice. TradingView Data API is an unofficial third-party market-data service and is not affiliated with TradingView, Inc.

## What this adds on top of upstream

| Capability | Notes |
|---|---|
| TradingView Data API | Exchange-level symbols, daily bars, indicators, fundamentals, news, calendars, peers, multi-timeframe TA |
| Structured decisions | Analyst-section signals, `decision_brief`, in-window price/fundamental chart snapshots |
| Multi-market tickers | Deterministic parsing for `600519.SS`, `HKEX:700`, `NASDAQ:AAPL` |
| Cache | In-process TTL by default; optional Redis to reuse requests across processes |

Upstream multi-agent debate, multi-LLM providers, checkpoints, and the five-level rating stay in place.

## Quick start

### 1. Get a market-data key

Open [https://www.tradingviewapi.com/](https://www.tradingviewapi.com/) and create a Console API key. Full multi-market coverage needs that key. Without it, the engine falls back to Yahoo Finance and other enabled vendors.

### 2. Install

```bash
git clone https://github.com/tradingagents-report/tradingagents-report.git
cd tradingagents-report
python3.12 -m venv .venv
source .venv/bin/activate
pip install .
```

Optional extras:

```bash
pip install ".[finnhub]"      # Finnhub
pip install ".[bedrock]"      # Amazon Bedrock
pip install ".[mcp]"          # local stdio MCP for Cursor / Claude
pip install ".[api]"          # local HTTP API (uvicorn)
```

### 3. Configure

```bash
cp .env.example .env
```

Minimum:

```bash
OPENAI_API_KEY=...           # or another LLM provider
TRADINGVIEW_API_KEY=...      # https://www.tradingviewapi.com/
```

The client calls `https://api.tradingviewapi.com` with `Authorization: Bearer`. Legacy `TRADINGVIEW_RAPIDAPI_KEY` still works as a Console credential. Set `TRADINGVIEW_BACKEND=rapid` only if you want the RapidAPI host.

**Redis and PostgreSQL are not required.** Market-data cache lives in process memory by default. Set `REDIS_URL` if several processes analyze the same ticker and you want to share cache / save quota.

### 4. Run the CLI

```bash
tradingagents-report
# or
tradingagents
```

Follow the prompts for ticker, date, models, and debate rounds.

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

Completed CLI / programmatic runs are saved under `~/.tradingagents/runs/{run_id}/` (`complete_report.md`, `decision.json`, `manifest.json`, `state.json`). A SQLite catalog at `~/.tradingagents/runs.sqlite` lists them by ticker and date. Set `TRADINGAGENTS_RUN_STORE_ENABLED=false` to disable. The hosted product API does not use this store.

Self-hosting has three adapters over the same engine: CLI (`tradingagents`), stdio MCP (`tradingagents-mcp`), and a thin local HTTP API (`tradingagents-api`). None of them is the hosted desk at agent.tradingagentsreport.com. The MCP server and local HTTP API are maintained in this public repository (`mcp_server/`, `local_api/`); they are not copied from the private Core tree.

## MCP

The same research tools as the [hosted MCP](https://www.tradingagentsreport.com/en/mcp) (`start_analysis` → poll `get_analysis` → `get_analysis_report`, plus `get_quote` / `get_ohlcv` / `get_news` / `get_ta_summary` / `get_fundamentals`) run **locally over stdio**. There is no OAuth; the process uses your `.env` keys and writes runs to `~/.tradingagents/runs/`. Paper trading, credits, and watchlists stay on the hosted desk.

```bash
pip install ".[mcp]"
```

Cursor / Claude config (stdio):

```json
{
  "mcpServers": {
    "tradingagents-report": {
      "command": "tradingagents-mcp"
    }
  }
}
```

Or `python -m mcp_server`. Analysis is asynchronous: `start_analysis` returns an id immediately; poll `get_analysis` until `succeeded`. Daily bars only for `get_ohlcv` (`timeframe` `D`). Depth market data can still use [TradingView MCP](https://www.tradingviewapi.com/).

## Local HTTP API

A thin FastAPI process over the same local run store. No PostgreSQL, Redis, Clerk, or credits.

```bash
pip install ".[api]"
tradingagents-api --host 127.0.0.1 --port 8000
```

Or `python -m local_api`. Health: `GET /health`. Research: `POST /api/v1/analyses` (202 + id), poll `GET /api/v1/analyses/{id}`, then `GET /api/v1/analyses/{id}/report`. Market: `GET /api/v1/quote`, `/ohlcv`, `/ta-summary`, `/news`, `/fundamentals`. Listing: `GET /api/v1/listings/resolve?ticker=AAPL`. Bind stays on localhost by default.

## Data sources

The default chain prefers TradingView, then yfinance / Alpha Vantage. Macro data uses FRED. Prediction markets use Polymarket.

China A-share examples: `600519.SS`, `000001.SZ`. Hong Kong: `0700.HK`. Without a TradingView key, Yahoo-compatible suffixes still work.

See [`tradingagents/dataflows/README.md`](tradingagents/dataflows/README.md) and [`docs/DATA_SOURCE_CONFIGURATION.md`](docs/DATA_SOURCE_CONFIGURATION.md).

## License

Apache License 2.0. Keep the upstream Tauric Research copyright notices in `LICENSE` and `NOTICE`.

This repository does not sublicense third-party market-data or LLM vendor rights. Use of TradingView Data API is subject to its [terms of service](https://www.tradingviewapi.com/).
