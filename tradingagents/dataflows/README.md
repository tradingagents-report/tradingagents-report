# Dataflows

`dataflows` is the shared access layer for prices, fundamentals, news, macro,
and sentiment used by the research graph. It fetches and shapes analysis
inputs. It does not execute trades, connect to a broker, or place orders.

## Routing

The graph and agents should call the stable tools in [`interface.py`](./interface.py)
instead of importing a vendor package directly. Routing reads `data_vendors`
and `tool_vendors` from `default_config.py`. Tool-level config wins over
category-level config. A comma-separated explicit value is the full fallback
chain. Unconfigured tools use `DEFAULT_VENDOR_CHAINS`.

### Market-aware vendor chains

`TRADINGAGENTS_CN_DATA_VENDORS` and `TRADINGAGENTS_US_DATA_VENDORS` enable
ordered CN/US chains. Unset, empty, or `disabled` preserves the immutable
method defaults. Routing precedence is tool override, category override,
market chain, then method default. A selected market chain is intersected with
`VENDOR_METHODS[method]` and never falls through to an unlisted provider.

The CN adapters are PandaAI, AKShare, Tushare, and BaoStock. The US chain may
use PandaAI, TradingView, yfinance, Alpha Vantage, and Finnhub. SDK imports are
lazy, and no adapter fabricates missing data. Provider credentials remain in
environment variables and are not part of API request overrides.

See [data-source configuration, capability matrix, authentication, and licensing](../../docs/DATA_SOURCE_CONFIGURATION.md).

Capabilities currently owned by the router:

| Category | Tools | Default vendor order |
| --- | --- | --- |
| Instrument identity | `get_instrument_identity` | TradingView, yfinance |
| Prices | `get_stock_data`, `get_ohlcv` | TradingView, yfinance, Alpha Vantage |
| Indicators | `get_indicators` | TradingView, yfinance, Alpha Vantage |
| TA dashboard | `get_ta_summary`, `get_ta_indicators` | TradingView (optional; degrades if unavailable) |
| Fundamentals and statements | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement` | TradingView, yfinance, Alpha Vantage |
| News and insider activity | `get_news`, `get_global_news`, `get_insider_transactions` | TradingView / yfinance / Alpha Vantage (varies by tool) |
| Event calendars | `get_earnings_calendar`, `get_economic_calendar` | TradingView (optional; future events hide `actual`) |
| Peer comparison | `get_peer_comparison` | TradingView screener (optional) |
| Macro | `get_macro_indicators` | FRED |
| Prediction markets | `get_prediction_markets` | Polymarket |

Macro, prediction markets, the TA dashboard, calendars, and peers are
optional extras: an unavailable vendor returns a readable degraded result.
Prices, fundamentals, and news are core. Routing failures raise instead of
continuing silently without the data.

## Vendor packages

### `alpha_vantage/`

Alpha Vantage adapter. Uses `ALPHA_VANTAGE_API_KEY`. Provides historical
daily bars and attributed OHLCV, SMA/RSI/MACD-style indicators, company
overview, balance sheet, cash flow, income statement, equity and market news,
and insider transactions. `__init__.py` re-exports the public surface;
`common.py` handles auth, HTTP, rate limits, and date-range filters.

### `tradingview/`

TradingView Data API adapter. Default path is [Console](https://www.tradingviewapi.com/)
(`TRADINGVIEW_API_KEY`, `Authorization: Bearer`). Legacy `TRADINGVIEW_RAPIDAPI_KEY`
/ `RAPIDAPI_KEY` still work as Console credentials. `TRADINGVIEW_BACKEND=rapid`
switches to the RapidAPI host. Coverage includes identity resolution, equity and
multi-asset OHLCV, daily-bar indicators, multi-timeframe TA dashboards, company
overview (analyst consensus, dividends, earnings date, and related fields),
financial statements, equity and market news, earnings/macro calendars, peer
screener comparison, and community Ideas (sentiment prefetch). `symbols.py`
maps a generic instrument to a vendor symbol. `client.py` wraps GET/POST and
list/object `data` payloads. `cache.py` uses an in-process memory TTL keyed by
method+path+params+body, with optional Redis (`REDIS_URL`); identical in-flight
requests are coalesced. Set `TRADINGVIEW_CACHE_ENABLED=false` to disable.

### `yfinance/`

yfinance adapter. No project-level API key. `market.py` covers Yahoo identity,
history, OHLCV, stockstats indicators, fundamentals, statements, and insider
activity. `news.py` covers equity and market news. `symbols.py` normalizes and
validates Yahoo-style equity and crypto symbols.

### `fred/`

FRED (Federal Reserve Economic Data) macro adapter. Uses a free `FRED_API_KEY`.
`get_macro_data()` accepts friendly aliases or raw FRED series IDs for policy
rates, Treasuries, inflation, labor, growth, money and markets, consumer
confidence, and housing. Results include units, frequency, window change, and
recent observations, clipped to the requested as-of date.

### `polymarket/`

Polymarket adapter over the public Gamma API. No auth. `get_prediction_markets()`
finds open markets that have not resolved, ranked by volume, and returns implied
probabilities, volume, resolution date, and one-week price change. Treat this
as market-implied context, not a forecast.

### `reddit/`

Reddit discussion collector. No API key. `fetch_reddit_posts()` searches
public Atom/RSS feeds on `wallstreetbets`, `stocks`, and `investing` by
default and formats posts for sentiment agents. Supports a feature flag, 429
cooldown, and a single retry. Public JSON search is often WAF-limited, so it
is not the default path. This collector is not registered in `interface.py`.

### `stocktwits/`

StockTwits public stream collector. No API key. `fetch_stocktwits_messages()`
loads recent messages, aggregates Bullish / Bearish / unlabeled sentiment, and
keeps timestamp, author, and body. Crypto pairs map to StockTwits `<BASE>.X`.
Network or parse failures return placeholder text. Also unregistered in the
router.

## Shared modules

| Module | Role |
| --- | --- |
| `interface.py` | Capability registry, config precedence, explicit fallback, call entry |
| `config.py` | Runtime data-source config |
| `provider_models.py` | Vendor-neutral instrument refs, vendor symbols, `ProviderResult` |
| `symbol_utils.py` | Ticker, crypto, and filename-safe normalization |
| `market_data_validator.py` | Quality and date-boundary checks |
| `news_utils.py` | Shared news date/content helpers |
| `structured_data.py` | Structured-data conversion helpers |
| `stockstats_utils.py` | Indicators from OHLCV |
| `listings.py` | Exchange / listing helpers |
| `exchange_catalog.py` | Package `data/exchanges.json` → region, `asset_type`, TradingView `market_code` |
| `utils.py` | Shared dataflow utilities |
| `errors.py` | Unconfigured, rate-limit, no-market-data, and vendor-unavailable errors |

## Conventions

- New vendor capabilities must update `VENDOR_METHODS` and
  `DEFAULT_VENDOR_CHAINS`, and declare the optional vendor or fallback in
  default config.
- Direct vendor calls still honor auth and date arguments. Historical runs
  must stay on or before the requested as-of date.
- The router must not silently call an unconfigured vendor. Core failures stay
  explicit. Only marked optional extras may degrade.
