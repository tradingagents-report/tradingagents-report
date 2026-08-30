# Data-source configuration, auth, and license boundaries

This document covers install, routing, authentication, and licensing for US and
China A-share vendors. Data is used for research analysis only. This project
does not provide broker connectivity or live order execution.

## Install

The extra SDKs are optional. Skip them unless you enable the matching vendor:

```bash
pip install ".[china-data]"   # AKShare + Tushare + BaoStock
pip install ".[pandaai]"      # panda_data
pip install ".[finnhub]"      # finnhub-python
pip install ".[market-data]"  # all of the above
```

Adapters import lazily. If routing selects a vendor whose SDK is missing, you
get `VendorNotConfiguredError` and fallback continues only inside the explicit
chain.

## Market-level routing

Current policy: **new vendors are registered, not used by default**. Runtime
still follows the TradingView-first chains in `default_config.data_vendors`.

```env
# Keep disabled until you explicitly enable a market chain
TRADINGAGENTS_CN_DATA_VENDORS=disabled
TRADINGAGENTS_US_DATA_VENDORS=disabled

# Enable later (order is priority)
# TRADINGAGENTS_CN_DATA_VENDORS=pandaai,akshare,tushare,baostock
# TRADINGAGENTS_US_DATA_VENDORS=yfinance,alpha_vantage,finnhub
```

The value is a comma-separated full priority chain. Unset, empty, or
`disabled` means the market chain is off. Unknown vendors, cross-market
vendors, duplicates, or mixing `disabled` with other values raise `ValueError`
when config loads.

Actual precedence:

1. Non-`default` `tool_vendors[method]`
2. Non-`default` `data_vendors[category]` (defaults are already explicit
   TradingView chains, so a market chain is ignored unless you set `default`)
3. CN/US env chain for the ticker
4. `DEFAULT_VENDOR_CHAINS[method]`

A selected market chain is intersected with each tool's capabilities. PandaAI
has no news capability, so a CN news chain `pandaai,akshare,tushare` runs as
`akshare,tushare`. Filtering never appends providers outside the chain. If
every vendor in the final chain fails, the engine returns a clear no-data
result or the existing vendor exception.

## Ticker format

External tickers stay provider-neutral. A-shares must include an exchange:

- Shanghai: `600519.SS` or `SSE:600519`
- Shenzhen: `000001.SZ` or `SZSE:000001`
- US: `AAPL` or `NASDAQ:AAPL`

A bare six-digit number is not guessed as an A-share. Adapters convert
internally to AKShare `600519`, Tushare `600519.SH`, or BaoStock `sh.600519`.

## Capability matrix

| Vendor | Market | Registered capabilities |
| --- | --- | --- |
| PandaAI | A-share, US | Daily text bars, structured OHLCV |
| AKShare | A-share | Identity, daily bars, OHLCV, indicators, fundamentals, statements, stock news |
| Tushare | A-share | Identity, daily bars, OHLCV, indicators, fundamentals, statements, stock and market news |
| BaoStock | A-share | Identity, daily bars, OHLCV, indicators, summary fundamentals |
| yfinance | US and others | Existing capabilities |
| Alpha Vantage | US | Existing capabilities |
| Finnhub | US | Identity, fundamentals, stock/market news, insider transactions |

Finnhub does not register historical OHLCV; a live quote is never treated as a
historical bar. BaoStock daily bars are not described as real-time quotes.
Indicators are computed from that vendor's date-filtered OHLCV.

## Authentication

Request a TradingView Data API key in Console: https://www.tradingviewapi.com/

```env
TRADINGVIEW_API_KEY=
# Legacy RapidAPI names still work as Console credentials
# TRADINGVIEW_RAPIDAPI_KEY=
PANDAAI_USERNAME=
PANDAAI_PASSWORD=
PANDAAI_BASE_URL=       # optional; empty uses the SDK default
TUSHARE_TOKEN=
FINNHUB_API_KEY=
```

AKShare has no project-level credential. BaoStock calls SDK `login()` and
always `logout()` after a query. Tushare and Finnhub need a token / API key.

### PandaAI-only surface

The PandaAI adapter authenticates with `panda_data.init_token(username=...,
password=..., base_url=...)`. `base_url` is passed only when `PANDAAI_BASE_URL`
is set. This integration calls:

- A-share daily: `get_market_data(type="stock", fields=[])`
- US daily: `get_us_daily(fields=[])`

Hong Kong and minute APIs exist upstream but are not registered here. PandaAI
identity, news, fundamentals, and live quotes are also unregistered; the adapter
does not invent stand-in data.

PandaAI credentials are read from the process environment only. They do not
enter `default_config.py`, request-level config, checkpoints, reports, or
durable storage. Auth errors become generic exceptions without the vendor
response body. The shared log redactor covers username, password, authorization,
API key, token, and secret.

## Licensing and data rights

Adapter code in this repository is released under this repo's Apache License
2.0. The implementation follows public provider call contracts. A software
license is not a data license. Access, commercial use, caching, display, and
redistribution of `panda_data`, PandaAI, AKShare, Tushare, BaoStock, Finnhub,
Yahoo Finance, Alpha Vantage, and their upstream feeds are governed by those
vendors' own licenses and terms. Operators must confirm rights, rate limits, and
attribution before enabling a vendor. This project only provides technical
adapters and does not sublicense third-party data rights. This is not legal
advice.

## Historical-analysis boundary

Price bars are filtered to the requested closed date range. Fundamentals and
news are filtered to the analysis cutoff date so future information cannot
enter a historical run. Empty vendor data, schema drift, auth failure, and
rate limits are not papered over with synthetic rows. Live connectivity tests
should run separately after extras are installed, test accounts are provided,
and vendor terms are accepted. Default unit tests use fake SDKs and do not
call external services.
