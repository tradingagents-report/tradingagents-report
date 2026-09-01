# Starting the three local entry points

This repo exposes one research engine through **three adapters**. They share `.env`, the same LangGraph run, and the same local catalog under `~/.tradingagents/runs/`. None of them is the hosted desk (no login, credits, watchlists, or paper trading).

| Adapter | Start command | Listens on |
|---|---|---|
| CLI | `tradingagents` | your terminal |
| stdio MCP | `tradingagents-mcp` | stdin/stdout (spawned by the client) |
| HTTP API | `tradingagents-api` | `127.0.0.1:8000` by default |

Step-by-step: prerequisites below, then pick one adapter.

## 0. Prerequisites (all three)

From the clone:

```bash
cd tradingagents-report
python3.12 -m venv .venv
source .venv/bin/activate
pip install .
cp .env.example .env
```

Put at least an LLM key and a market-data key in `.env`:

```bash
OPENAI_API_KEY=...            # or another provider
TRADINGVIEW_API_KEY=...       # https://www.tradingviewapi.com/
```

OpenAI-compatible relays:

```bash
TRADINGAGENTS_LLM_PROVIDER=openai_compatible
TRADINGAGENTS_LLM_BACKEND_URL=https://your-endpoint/v1
OPENAI_COMPATIBLE_API_KEY=...
TRADINGAGENTS_QUICK_THINK_LLM=...
TRADINGAGENTS_DEEP_THINK_LLM=...
```

Always start processes **from the repo root** so `python-dotenv` finds `.env`. Redis and PostgreSQL are not required.

Install extras only for the adapter you use:

```bash
pip install ".[mcp]"    # stdio MCP (pins mcp 1.x)
pip install ".[api]"    # local HTTP
```

## 1. CLI

Interactive Typer app. No extra pip extra.

```bash
source .venv/bin/activate
tradingagents
# aliases:
tradingagents-report
python -m cli.main
```

Flags:

```bash
python -m cli.main --help
python -m cli.main --no-checkpoint
python -m cli.main --clear-checkpoints
```

The questionnaire asks for ticker, analysis date (`YYYY-MM-DD`), analysts, research depth, LLM provider, and models. These environment variables skip the matching prompts (ticker, date, and analyst checkboxes stay interactive):

```bash
export TRADINGAGENTS_OUTPUT_LANGUAGE=English
export TRADINGAGENTS_MAX_DEBATE_ROUNDS=1
export TRADINGAGENTS_MAX_RISK_ROUNDS=1
export TRADINGAGENTS_LLM_PROVIDER=openai
export TRADINGAGENTS_QUICK_THINK_LLM=gpt-5.4-mini
export TRADINGAGENTS_DEEP_THINK_LLM=gpt-5.5
```

When the graph finishes, the CLI prints the run directory. Reports land in `~/.tradingagents/runs/{run_id}/`.

## 2. stdio MCP

For Cursor, Claude Desktop, or any MCP client that can spawn a stdio process.

```bash
source .venv/bin/activate
pip install ".[mcp]"
```

Smoke-test in a TTY (the process waits on stdin; Ctrl-C to quit):

```bash
tradingagents-mcp
# or
python -m mcp_server
```

If the extra is missing you get: `The MCP extra is required: pip install ".[mcp]"`. If you installed MCP SDK 2.x, uninstall it and reinstall `".[mcp]"` (`mcp>=1.8.0,<2`).

### Cursor / Claude Desktop

Point the client at the venv script and this repo as cwd so `.env` loads:

```json
{
  "mcpServers": {
    "tradingagents-report": {
      "command": "/ABS/PATH/tradingagents-report/.venv/bin/tradingagents-mcp",
      "cwd": "/ABS/PATH/tradingagents-report"
    }
  }
}
```

If `tradingagents-mcp` is already on `PATH` inside that venv:

```json
{
  "mcpServers": {
    "tradingagents-report": {
      "command": "tradingagents-mcp"
    }
  }
}
```

Restart the MCP server in the client after changing `.env`.

### After connect: run a research job

Tools are the same names as the hosted MCP, without OAuth.

1. Optional: `resolve_listing` with `ticker` = `AAPL` or `0700.HK`
2. `start_analysis` with `ticker`, `trade_date` (`YYYY-MM-DD`), optional `analysts` (`market`, `social`, `news`, `fundamentals`)
3. Poll `get_analysis` with the returned `id` until `status` is `succeeded` (or `failed` / `cancelled`)
4. `get_analysis_report` for the decision card and sections

Useful extras: `get_analysis_events`, `list_analyses`, `cancel_analysis`. Market: `get_quote`, `get_ohlcv` (daily `timeframe` `D` only), `get_ta_summary`, `get_news`, `get_fundamentals`.

This process does **not** listen on a TCP port. The hosted URL `https://mcp.tradingagentsreport.com/mcp` is a different OAuth HTTP service.

## 3. Local HTTP API

Thin FastAPI over the same run store. No auth.

```bash
source .venv/bin/activate
pip install ".[api]"
tradingagents-api --host 127.0.0.1 --port 8000
```

Or:

```bash
python -m local_api --host 127.0.0.1 --port 8000
```

Default bind is **localhost only**. Open `http://127.0.0.1:8000/docs` for Swagger. Health check:

```bash
curl -s http://127.0.0.1:8000/health
# {"status":"ok","store":"local"}
```

Listings and market:

```bash
curl -s "http://127.0.0.1:8000/api/v1/listings/resolve?ticker=0700.HK"
curl -s "http://127.0.0.1:8000/api/v1/quote?symbol=NASDAQ:AAPL"
curl -s "http://127.0.0.1:8000/api/v1/ohlcv?symbol=NASDAQ:AAPL&timeframe=D&bar_count=5"
```

Submit an analysis, poll, then fetch the report (`202` on submit):

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/analyses \
  -H 'Content-Type: application/json' \
  -d '{"ticker":"AAPL","trade_date":"2026-08-28","analysts":["market"],"output_language":"English"}'

curl -s http://127.0.0.1:8000/api/v1/analyses/<id>
curl -s http://127.0.0.1:8000/api/v1/analyses/<id>/events
curl -s http://127.0.0.1:8000/api/v1/analyses/<id>/report
```

Cancel: `POST /api/v1/analyses/<id>/cancel`. List: `GET /api/v1/analyses?ticker=AAPL&limit=20`.

| Method | Path |
|---|---|
| `GET` | `/health` |
| `GET` | `/api/v1/listings/resolve?ticker=` |
| `POST` | `/api/v1/analyses` |
| `GET` | `/api/v1/analyses` |
| `GET` | `/api/v1/analyses/{id}` |
| `GET` | `/api/v1/analyses/{id}/events` |
| `GET` | `/api/v1/analyses/{id}/report` |
| `POST` | `/api/v1/analyses/{id}/cancel` |
| `GET` | `/api/v1/quote?symbol=` |
| `GET` | `/api/v1/ohlcv?symbol=` |
| `GET` | `/api/v1/ta-summary?symbol=` |
| `GET` | `/api/v1/news?symbol=` |
| `GET` | `/api/v1/fundamentals?ticker=` |

Report is `409` while the job is not `succeeded`, `404` if the id is unknown. Intraday OHLCV timeframes return `400`. This is not the hosted PostgreSQL job API.

Stop the server with Ctrl-C.

## Shared outputs

Successful MCP and HTTP jobs (and CLI / `propagate()` when run store is on) write:

- `~/.tradingagents/runs/{id}/complete_report.md`
- `decision.json`, `manifest.json`, `state.json`, `events.jsonl`
- catalog `~/.tradingagents/runs.sqlite`

Override the directory with `TRADINGAGENTS_RUN_STORE_DIR`. Disable with `TRADINGAGENTS_RUN_STORE_ENABLED=false`.

## Troubleshooting

| Symptom | What to check |
|---|---|
| `The MCP extra is required` | `pip install ".[mcp]"` in the same venv |
| FastMCP / `mcp.server.fastmcp` import error | MCP SDK 2.x — reinstall `".[mcp]"` so you get `mcp<2` |
| `The API extra is required` | `pip install ".[api]"` |
| Empty market data / LLM errors | `.env` present in cwd; keys set; start from repo root |
| Cursor MCP has no tools | `command` path, `cwd`, restart MCP; confirm `tradingagents-mcp` runs in a terminal |
| HTTP connection refused | process running; port `8000`; curl `127.0.0.1` not a public host |
| CLI asks for an API key | provider env var missing; `ensure_api_key` will prompt |

Market-data vendors and ticker formats: [`DATA_SOURCE_CONFIGURATION.md`](DATA_SOURCE_CONFIGURATION.md).
