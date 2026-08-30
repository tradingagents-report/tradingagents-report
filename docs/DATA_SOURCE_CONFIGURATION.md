# Data-source configuration, auth, and license boundaries

This document covers install, routing, authentication, and licensing for
market-data vendors. Data is used for research analysis only. This project
does not provide broker connectivity or live order execution.

## Install

The Finnhub SDK is optional. Skip it unless you enable that vendor:

```bash
pip install ".[finnhub]"      # finnhub-python
pip install ".[market-data]"  # currently the same as the Finnhub extra
```

Adapters import lazily. If routing selects a vendor whose SDK is missing, you
get `VendorNotConfiguredError` and fallback continues only inside the explicit
chain.

A-share and other non-US listings use the default TradingView-first chain
(TradingView → yfinance → Alpha Vantage). There is no separate mainland-China
vendor stack.

## Market-level routing

Current policy: **Finnhub is registered, not used by default**. Runtime still
follows the TradingView-first chains in `default_config.data_vendors`.

```env
# Keep disabled until you explicitly enable a US market chain
TRADINGAGENTS_US_DATA_VENDORS=disabled

# Enable later (order is priority)
# TRADINGAGENTS_US_DATA_VENDORS=yfinance,alpha_vantage,finnhub
```

The value is a comma-separated full priority chain. Unset, empty, or
`disabled` means the market chain is off. Unknown vendors, duplicates, or
mixing `disabled` with other values raise `ValueError` when config loads. The
US chain applies only to US listings; A-shares and other markets ignore it.

Actual precedence:

1. Non-`default` `tool_vendors[method]`
2. Non-`default` `data_vendors[category]` (defaults are already explicit
   TradingView chains, so a market chain is ignored unless you set `default`)
3. US env chain for the ticker
4. `DEFAULT_VENDOR_CHAINS[method]`

A selected market chain is intersected with each tool's capabilities.
Filtering never appends providers outside the chain. If every vendor in the
final chain fails, the engine returns a clear no-data result or the existing
vendor exception.

## Ticker format

External tickers stay provider-neutral. A-shares must include an exchange:

- Shanghai: `600519.SS` or `SSE:600519`
- Shenzhen: `000001.SZ` or `SZSE:000001`
- US: `AAPL` or `NASDAQ:AAPL`

A bare six-digit number is not guessed as an A-share.

## Capability matrix

| Vendor | Market | Registered capabilities |
| --- | --- | --- |
| TradingView | Multi-market | Identity, daily bars, OHLCV, indicators, TA dashboard, fundamentals, statements, news, calendars, peers |
| yfinance | US and others | Identity, daily bars, OHLCV, indicators, fundamentals, statements, news, insider transactions |
| Alpha Vantage | US | Daily bars, OHLCV, indicators, fundamentals, statements, news, insider transactions |
| Finnhub | US | Identity, fundamentals, stock/market news, insider transactions |
| FRED | Macro | Rates, inflation, labor, growth series |
| Polymarket | Prediction markets | Implied probabilities for unsettled markets |

Finnhub does not register historical OHLCV; a live quote is never treated as a
historical bar.

## Authentication

Request a TradingView Data API key in Console: https://www.tradingviewapi.com/

```env
TRADINGVIEW_API_KEY=
# Legacy RapidAPI names still work as Console credentials
# TRADINGVIEW_RAPIDAPI_KEY=
FINNHUB_API_KEY=
FRED_API_KEY=
ALPHA_VANTAGE_API_KEY=
```

Finnhub needs an API key. yfinance and Polymarket have no project-level
credential.

Credentials are read from the process environment only. They do not enter
`default_config.py`, request-level config, checkpoints, reports, or durable
storage. Auth errors become generic exceptions without the vendor response
body. The shared log redactor covers username, password, authorization, API
key, token, and secret.

## Licensing and data rights

Adapter code in this repository is released under this repo's Apache License
2.0. A software license is not a data license. Access, commercial use,
caching, display, and redistribution of TradingView Data API, Finnhub, Yahoo
Finance, Alpha Vantage, FRED, Polymarket, and their upstream feeds are governed
by those vendors' own licenses and terms. Operators must confirm rights, rate
limits, and attribution before enabling a vendor. This project only provides
technical adapters and does not sublicense third-party data rights. This is
not legal advice.

## Historical-analysis boundary

Price bars are filtered to the requested closed date range. Fundamentals and
news are filtered to the analysis cutoff date so future information cannot
enter a historical run. Empty vendor data, schema drift, auth failure, and
rate limits are not papered over with synthetic rows. Live connectivity tests
should run separately after extras are installed, test accounts are provided,
and vendor terms are accepted. Default unit tests use fake SDKs and do not
call external services.
