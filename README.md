# TradingAgents Report

**TradingAgents Report** is a multi-agent equity-research framework. It splits a ticker into evidence gathering, bull/bear debate, a trade proposal, risk review, and a five-level portfolio-manager rating. The output is a research report and a structured decision card. It is **not** a broker integration and it does **not** place live orders.

This repository is the self-hosted research engine. If you would rather not run models and data vendors yourself, use the hosted desk:

- Site: [tradingagentsreport.com](https://www.tradingagentsreport.com)
- Desk: [agent.tradingagentsreport.com](https://agent.tradingagentsreport.com)
- Hosted MCP (OAuth, Streamable HTTP): [mcp.tradingagentsreport.com/mcp](https://mcp.tradingagentsreport.com/mcp)

This project is an Apache 2.0 derivative of [Tauric Research / TradingAgents](https://github.com/TauricResearch/TradingAgents). Market data defaults to [TradingView Data API](https://www.tradingviewapi.com/).

> For research only. Not investment advice. TradingView Data API is an unofficial third-party market-data service and is not affiliated with TradingView, Inc.

## What this adds on top of upstream

| Capability | Notes |
|---|---|
| TradingView Data API | Exchange-level symbols, daily bars, indicators, fundamentals, news, calendars, peers, multi-timeframe TA |
| Structured decisions | Analyst-section signals, `decision_brief`, in-window price/fundamental chart snapshots |
| Multi-market tickers | Deterministic parsing for `600519.SS`, `HKEX:700`, `NASDAQ:AAPL` |
| Cache | In-process TTL by default; optional Redis to reuse requests across processes |
| Three local adapters | Interactive CLI, stdio MCP, thin HTTP API — all over the same engine and run store |

Upstream multi-agent debate, multi-LLM providers, checkpoints, and the five-level rating stay in place.

## Entry points

All three talk to the same graph and write the same local catalog. None of them is the hosted desk (no Clerk, credits, watchlists, or paper trading).

| Adapter | Command | When to use |
|---|---|---|
| CLI | `tradingagents` / `tradingagents-report` | Interactive terminal research |
| stdio MCP | `tradingagents-mcp` (`pip install ".[mcp]"`) | Cursor, Claude, or any MCP client |
| HTTP API | `tradingagents-api` (`pip install ".[api]"`) | curl, scripts, or a local service |

MCP lives in [`mcp_server/`](mcp_server/); the HTTP adapter lives in [`local_api/`](local_api/). They share [`application/local_desk.py`](application/local_desk.py).

**How to start each one** (install extras, commands, Cursor config, curl): [`docs/ENTRY_POINTS.md`](docs/ENTRY_POINTS.md).

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
pip install ".[mcp]"          # local stdio MCP (mcp 1.x)
pip install ".[api]"          # local HTTP API (FastAPI + uvicorn)
```

The `[mcp]` extra pins `mcp>=1.8.0,<2` (FastMCP). Do not install MCP SDK 2.x into the same environment.

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

OpenAI-compatible relays (vLLM, LM Studio, llama.cpp):

```bash
TRADINGAGENTS_LLM_PROVIDER=openai_compatible
TRADINGAGENTS_LLM_BACKEND_URL=https://your-endpoint/v1
OPENAI_COMPATIBLE_API_KEY=...
TRADINGAGENTS_QUICK_THINK_LLM=...
TRADINGAGENTS_DEEP_THINK_LLM=...
```

**Redis and PostgreSQL are not required.** Market-data cache lives in process memory by default. Set `REDIS_URL` if several processes analyze the same ticker and you want to share cache / save quota.

### 4. CLI

```bash
tradingagents-report
# or
tradingagents
# or
python -m cli.main
```

Follow the prompts for ticker, date, analysts, models, and debate rounds. Full start guide: [`docs/ENTRY_POINTS.md`](docs/ENTRY_POINTS.md#1-cli).

Set these to skip the matching prompts (ticker, date, and analyst checkboxes stay interactive):

```bash
TRADINGAGENTS_OUTPUT_LANGUAGE=English
TRADINGAGENTS_MAX_DEBATE_ROUNDS=1
TRADINGAGENTS_MAX_RISK_ROUNDS=1
TRADINGAGENTS_LLM_PROVIDER=openai
TRADINGAGENTS_QUICK_THINK_LLM=gpt-5.4-mini
TRADINGAGENTS_DEEP_THINK_LLM=gpt-5.5
```

## Local run store

CLI, MCP, HTTP, and `TradingAgentsGraph.propagate()` share one catalog when `run_store` is enabled (the default):

- Files: `~/.tradingagents/runs/{run_id}/` — `complete_report.md`, `decision.json`, `manifest.json`, `state.json`, `events.jsonl`
- Index: `~/.tradingagents/runs.sqlite`

Disable with `TRADINGAGENTS_RUN_STORE_ENABLED=false`. Override the directory with `TRADINGAGENTS_RUN_STORE_DIR`. The hosted product API does not use this store.

## MCP

Same research and market **tool names** as the [hosted MCP](https://www.tradingagentsreport.com/en/mcp), over **stdio**. How to install and start: [`docs/ENTRY_POINTS.md`](docs/ENTRY_POINTS.md#2-stdio-mcp).

```bash
pip install ".[mcp]"
```

Cursor / Claude Desktop (run the client from this repo so `.env` loads):

```json
{
  "mcpServers": {
    "tradingagents-report": {
      "command": "tradingagents-mcp"
    }
  }
}
```

Or `python -m mcp_server`.

Analysis is asynchronous:

1. `resolve_listing` if you need a canonical `EXCHANGE:SYMBOL`
2. `start_analysis` returns `{id, status: "running", ...}` immediately
3. poll `get_analysis` until `status` is `succeeded` (or `failed` / `cancelled`)
4. `get_analysis_report` for the decision card and sections

| Tool | Role |
|---|---|
| `resolve_listing` | Normalize `AAPL`, `0700.HK`, `HKEX:700`, … |
| `start_analysis` | Submit a job. `trade_date` is `YYYY-MM-DD`. `analysts` is a non-empty subset of `market`, `social`, `news`, `fundamentals` |
| `get_analysis` | Status and progress (`progress_percent`, `current_step`) |
| `get_analysis_events` | Stage / tool-call timeline |
| `get_analysis_report` | Full report after `succeeded` |
| `list_analyses` | Recent rows from the SQLite catalog |
| `cancel_analysis` | Request cancel of a running job |
| `get_quote` | Latest daily bar |
| `get_ohlcv` | Daily bars only (`timeframe` must be `D`) |
| `get_ta_summary` | TradingView multi-timeframe gauges when that vendor is configured |
| `get_news` | Headlines over the last 7 days |
| `get_fundamentals` | Name / exchange identity (full statements land on completed reports) |

Depth market data (intraday, more symbols) can still use [TradingView MCP](https://www.tradingviewapi.com/).

## Local HTTP API

A thin FastAPI process over the same run store. No PostgreSQL, Redis, or auth. **Binds to `127.0.0.1` by default.** How to start and call it: [`docs/ENTRY_POINTS.md`](docs/ENTRY_POINTS.md#3-local-http-api).

```bash
pip install ".[api]"
tradingagents-api --host 127.0.0.1 --port 8000
```

Or `python -m local_api`. OpenAPI: `http://127.0.0.1:8000/docs`.

```bash
curl -s http://127.0.0.1:8000/health
# {"status":"ok","store":"local"}

curl -s "http://127.0.0.1:8000/api/v1/listings/resolve?ticker=0700.HK"

curl -s "http://127.0.0.1:8000/api/v1/quote?symbol=NASDAQ:AAPL"

curl -s -X POST http://127.0.0.1:8000/api/v1/analyses \
  -H 'Content-Type: application/json' \
  -d '{"ticker":"AAPL","trade_date":"2026-08-28","analysts":["market"],"output_language":"English"}'
# 202 {"id":"...","status":"running","ticker":"AAPL","trade_date":"2026-08-28"}

curl -s http://127.0.0.1:8000/api/v1/analyses/<id>
curl -s http://127.0.0.1:8000/api/v1/analyses/<id>/events
curl -s http://127.0.0.1:8000/api/v1/analyses/<id>/report   # after succeeded
```

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health` | `{status, store: "local"}` |
| `GET` | `/api/v1/listings/resolve?ticker=` | Listing identity |
| `POST` | `/api/v1/analyses` | `202`; body: `ticker`, `trade_date`, optional `analysts`, `instrument_*`, `output_language` |
| `GET` | `/api/v1/analyses` | Query `ticker`, `status`, `limit` |
| `GET` | `/api/v1/analyses/{id}` | Job status |
| `GET` | `/api/v1/analyses/{id}/events` | Timeline |
| `GET` | `/api/v1/analyses/{id}/report` | `200` when succeeded; `409` if still running; `404` if missing |
| `POST` | `/api/v1/analyses/{id}/cancel` | Request cancel |
| `GET` | `/api/v1/quote?symbol=` | Daily quote |
| `GET` | `/api/v1/ohlcv?symbol=` | Daily bars; `timeframe=D`, optional `bar_count`, `as_of` |
| `GET` | `/api/v1/ta-summary?symbol=` | TA gauges |
| `GET` | `/api/v1/news?symbol=` | Recent news |
| `GET` | `/api/v1/fundamentals?ticker=` | Identity |

Intraday `timeframe` values are rejected (`400`). This API is not a drop-in for the hosted Core job service.

## Python

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

## Data sources

The default chain prefers TradingView, then yfinance / Alpha Vantage. Macro data uses FRED. Prediction markets use Polymarket.

China A-share examples: `600519.SS`, `000001.SZ`. Hong Kong: `0700.HK`. Without a TradingView key, Yahoo-compatible suffixes still work.

See [`tradingagents/dataflows/README.md`](tradingagents/dataflows/README.md) and [`docs/DATA_SOURCE_CONFIGURATION.md`](docs/DATA_SOURCE_CONFIGURATION.md).

## License

Apache License 2.0. Keep the upstream Tauric Research copyright notices in `LICENSE` and `NOTICE`.

This repository does not sublicense third-party market-data or LLM vendor rights. Use of TradingView Data API is subject to its [terms of service](https://www.tradingviewapi.com/).
