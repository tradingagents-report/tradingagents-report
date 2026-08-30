"""Vendor routing entry.

This module only selects vendors from config, runs an explicit fallback
chain, and unifies text vs structured failure semantics. Actual HTTP/SDK
calls stay in each vendor package.
"""

import logging
import re
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

import pandas as pd

from .akshare.fundamentals import (
    get_akshare_fundamentals,
    get_akshare_identity,
    get_balance_sheet as get_akshare_balance_sheet,
    get_cashflow as get_akshare_cashflow,
    get_income_statement as get_akshare_income_statement,
)
from .akshare.market import (
    fetch_akshare_ohlcv,
    get_akshare_indicators,
    get_akshare_stock,
)
from .akshare.news import get_akshare_news
from .alpha_vantage import (
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_global_news as get_alpha_vantage_global_news,
    get_income_statement as get_alpha_vantage_income_statement,
    get_indicator as get_alpha_vantage_indicator,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news,
    get_stock as get_alpha_vantage_stock,
)
from .alpha_vantage.stock import fetch_alpha_vantage_ohlcv
from .baostock.fundamentals import (
    get_baostock_fundamentals,
    get_baostock_identity,
)
from .baostock.market import (
    fetch_baostock_ohlcv,
    get_baostock_indicators,
    get_baostock_stock,
)
from .config import get_config
from .errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorRateLimitError,
)
from .finnhub import (
    get_finnhub_fundamentals,
    get_finnhub_global_news,
    get_finnhub_identity,
    get_finnhub_insider_transactions,
    get_finnhub_news,
)
from .fred import get_macro_data as get_fred_macro_data
from .market_routing import configured_market_chain
from .pandaai.market import fetch_pandaai_ohlcv, get_pandaai_stock
from .polymarket import get_prediction_markets as get_polymarket_prediction_markets
from .provider_models import ProviderResult
from .tradingview.calendar import (
    get_tradingview_earnings_calendar,
    get_tradingview_economic_calendar,
)
from .tradingview.fundamentals import (
    get_tradingview_balance_sheet,
    get_tradingview_cashflow,
    get_tradingview_fundamentals,
    get_tradingview_income_statement,
)
from .tradingview.news import get_tradingview_global_news, get_tradingview_news
from .tradingview.peers import get_tradingview_peer_comparison
from .tradingview.stock import (
    fetch_tradingview_ohlcv,
    get_tradingview_identity,
    get_tradingview_indicators,
    get_tradingview_stock,
)
from .tradingview.ta import (
    get_tradingview_ta_indicators,
    get_tradingview_ta_summary,
)
from .tushare.fundamentals import (
    get_balance_sheet as get_tushare_balance_sheet,
    get_cashflow as get_tushare_cashflow,
    get_income_statement as get_tushare_income_statement,
    get_tushare_fundamentals,
    get_tushare_identity,
)
from .tushare.market import (
    fetch_tushare_ohlcv,
    get_tushare_indicators,
    get_tushare_stock,
)
from .tushare.news import get_tushare_global_news, get_tushare_news
from .yfinance.market import (
    fetch_yfinance_ohlcv,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_fundamentals as get_yfinance_fundamentals,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
    get_stock_stats_indicators_window,
    get_YFin_data_online,
    get_yfinance_identity,
)
from .yfinance.news import get_global_news_yfinance, get_news_yfinance

logger = logging.getLogger(__name__)

# Tools grouped by data category. Category-level vendor config uses these keys.
TOOLS_CATEGORIES = {
    "instrument_data": {
        "description": "Instrument identity",
        "tools": ["get_instrument_identity"],
    },
    "core_stock_apis": {
        "description": "OHLCV stock price data",
        "tools": [
            "get_stock_data",
            "get_ohlcv",
        ]
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": [
            "get_indicators"
        ]
    },
    "technical_gauges": {
        "description": "Multi-timeframe TA gauges and indicator snapshots",
        "tools": [
            "get_ta_summary",
            "get_ta_indicators",
        ]
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement"
        ]
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
        ]
    },
    "event_calendar": {
        "description": "Earnings and economic event calendars",
        "tools": [
            "get_earnings_calendar",
            "get_economic_calendar",
        ]
    },
    "peer_comparison": {
        "description": "Same-sector peer valuation and relative strength",
        "tools": [
            "get_peer_comparison",
        ]
    },
    "macro_data": {
        "description": "Macroeconomic indicators (rates, inflation, labor, growth)",
        "tools": [
            "get_macro_indicators",
        ]
    },
    "prediction_markets": {
        "description": "Market-implied probabilities for forward-looking events",
        "tools": [
            "get_prediction_markets",
        ]
    }
}

VENDOR_LIST = [
    "tradingview",
    "yfinance",
    "fred",
    "polymarket",
    "alpha_vantage",
    "pandaai",
    "akshare",
    "tushare",
    "baostock",
    "finnhub",
]

# Optional extras supply macro or event context for news analysis, not core
# decision inputs. Vendor failures degrade to a readable sentinel. Price,
# fundamentals, and news stay hard failures so analysis cannot continue silently
# without the data.
OPTIONAL_CATEGORIES = {
    "macro_data",
    "prediction_markets",
    "technical_gauges",
    "event_calendar",
    "peer_comparison",
}

# Capability → vendor implementation. Update this map and the default chains
# together so routing never implicitly calls an undeclared provider.
VENDOR_METHODS = {
    # Instrument identity: normalize the user ticker to company name, exchange,
    # asset class, and related metadata for display and vendor symbol resolution.
    "get_instrument_identity": {
        "tradingview": get_tradingview_identity,
        "yfinance": get_yfinance_identity,
        "akshare": get_akshare_identity,
        "tushare": get_tushare_identity,
        "baostock": get_baostock_identity,
        "finnhub": get_finnhub_identity,
    },
    # Core prices: get_stock_data is history for text reports; get_ohlcv returns
    # structured OHLCV with ProviderResult provenance for indicators and checks.
    "get_stock_data": {
        "tradingview": get_tradingview_stock,
        "yfinance": get_YFin_data_online,
        "alpha_vantage": get_alpha_vantage_stock,
        "pandaai": get_pandaai_stock,
        "akshare": get_akshare_stock,
        "tushare": get_tushare_stock,
        "baostock": get_baostock_stock,
    },
    "get_ohlcv": {
        "tradingview": fetch_tradingview_ohlcv,
        "yfinance": fetch_yfinance_ohlcv,
        "alpha_vantage": fetch_alpha_vantage_ohlcv,
        "pandaai": fetch_pandaai_ohlcv,
        "akshare": fetch_akshare_ohlcv,
        "tushare": fetch_tushare_ohlcv,
        "baostock": fetch_baostock_ohlcv,
    },
    # Indicators: SMA, RSI, MACD, and similar from ticker, as-of date, and lookback.
    "get_indicators": {
        "tradingview": get_tradingview_indicators,
        "yfinance": get_stock_stats_indicators_window,
        "alpha_vantage": get_alpha_vantage_indicator,
        "akshare": get_akshare_indicators,
        "tushare": get_tushare_indicators,
        "baostock": get_baostock_indicators,
    },
    # Multi-timeframe TA dashboard: TradingView Buy/Sell/Neutral plus snapshots.
    # Optional category; degrades when the vendor is unavailable.
    "get_ta_summary": {
        "tradingview": get_tradingview_ta_summary,
    },
    "get_ta_indicators": {
        "tradingview": get_tradingview_ta_indicators,
    },
    # Fundamentals: overview and key ratios, plus the three financial statements.
    "get_fundamentals": {
        "tradingview": get_tradingview_fundamentals,
        "yfinance": get_yfinance_fundamentals,
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "akshare": get_akshare_fundamentals,
        "tushare": get_tushare_fundamentals,
        "baostock": get_baostock_fundamentals,
        "finnhub": get_finnhub_fundamentals,
    },
    "get_balance_sheet": {
        "tradingview": get_tradingview_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "akshare": get_akshare_balance_sheet,
        "tushare": get_tushare_balance_sheet,
    },
    "get_cashflow": {
        "tradingview": get_tradingview_cashflow,
        "yfinance": get_yfinance_cashflow,
        "alpha_vantage": get_alpha_vantage_cashflow,
        "akshare": get_akshare_cashflow,
        "tushare": get_tushare_cashflow,
    },
    "get_income_statement": {
        "tradingview": get_tradingview_income_statement,
        "yfinance": get_yfinance_income_statement,
        "alpha_vantage": get_alpha_vantage_income_statement,
        "akshare": get_akshare_income_statement,
        "tushare": get_tushare_income_statement,
    },
    # News and insider data. All three respect the historical as-of boundary.
    "get_news": {
        "tradingview": get_tradingview_news,
        "yfinance": get_news_yfinance,
        "alpha_vantage": get_alpha_vantage_news,
        "akshare": get_akshare_news,
        "tushare": get_tushare_news,
        "finnhub": get_finnhub_news,
    },
    "get_global_news": {
        "tradingview": get_tradingview_global_news,
        "yfinance": get_global_news_yfinance,
        "alpha_vantage": get_alpha_vantage_global_news,
        "tushare": get_tushare_global_news,
        "finnhub": get_finnhub_global_news,
    },
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
        "finnhub": get_finnhub_insider_transactions,
    },
    # Event calendars. Future events hide actuals to reduce look-ahead.
    "get_earnings_calendar": {
        "tradingview": get_tradingview_earnings_calendar,
    },
    "get_economic_calendar": {
        "tradingview": get_tradingview_economic_calendar,
    },
    # Same-sector peers in the same market for relative valuation/technicals.
    "get_peer_comparison": {
        "tradingview": get_tradingview_peer_comparison,
    },
    # FRED rates, inflation, labor, and growth as optional macro context.
    "get_macro_indicators": {
        "fred": get_fred_macro_data,
    },
    # Polymarket implied probabilities as optional forward-looking context.
    "get_prediction_markets": {
        "polymarket": get_polymarket_prediction_markets,
    },
}

# Fallback order when no vendor is configured. MappingProxyType keeps the
# chain immutable for a deterministic run.
DEFAULT_VENDOR_CHAINS: Mapping[str, tuple[str, ...]] = MappingProxyType({
    "get_instrument_identity": ("tradingview", "yfinance"),
    "get_stock_data": ("tradingview", "yfinance", "alpha_vantage"),
    "get_ohlcv": ("tradingview", "yfinance", "alpha_vantage"),
    "get_indicators": ("tradingview", "yfinance", "alpha_vantage"),
    "get_ta_summary": ("tradingview",),
    "get_ta_indicators": ("tradingview",),
    "get_fundamentals": ("tradingview", "yfinance", "alpha_vantage"),
    "get_balance_sheet": ("tradingview", "yfinance", "alpha_vantage"),
    "get_cashflow": ("tradingview", "yfinance", "alpha_vantage"),
    "get_income_statement": ("tradingview", "yfinance", "alpha_vantage"),
    "get_news": ("tradingview", "yfinance", "alpha_vantage"),
    "get_global_news": ("tradingview", "yfinance", "alpha_vantage"),
    "get_insider_transactions": ("yfinance", "alpha_vantage"),
    "get_earnings_calendar": ("tradingview",),
    "get_economic_calendar": ("tradingview",),
    "get_peer_comparison": ("tradingview",),
    "get_macro_indicators": ("fred",),
    "get_prediction_markets": ("polymarket",),
})

def get_category_for_method(method: str) -> str:
    """Return the data category for a capability, for category-level vendor config."""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")

def get_vendor(category: str, method: str = None) -> str:
    """Read vendor config. Tool-level ``tool_vendors`` wins over category config."""
    config = get_config()

    # A single tool can override the category default, e.g. news vs prices.
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # No tool override: fall back to category-level ``data_vendors``.
    return config.get("data_vendors", {}).get(category, "default")

def _vendor_chain(method: str, category: str, args: tuple[Any, ...] = ()) -> list[str]:
    """Build the vendor chain for one call. Only registered explicit config is used."""
    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")
    available = list(VENDOR_METHODS[method])
    config = get_config()
    tool_value = config.get("tool_vendors", {}).get(method, "default")
    category_value = config.get("data_vendors", {}).get(category, "default")
    configured_value = category_value if tool_value == "default" else tool_value

    configured = [
        vendor.strip() for vendor in str(configured_value).split(",")
    ]
    # A comma-separated explicit value is the full chain; defaults are not appended.
    explicit = [vendor for vendor in configured if vendor and vendor != "default"]
    if explicit:
        chain = [vendor for vendor in explicit if vendor in VENDOR_METHODS[method]]
        if not chain:
            raise ValueError(
                f"Configured vendor(s) {explicit} not available for '{method}'. "
                f"Available: {available}."
            )
        return chain

    market_chain = (
        configured_market_chain(config, str(args[0])) if args else None
    )
    if market_chain is not None:
        chain = [vendor for vendor in market_chain if vendor in VENDOR_METHODS[method]]
        if not chain:
            raise ValueError(
                f"No configured market vendor is registered for '{method}'"
            )
        return chain

    if method not in DEFAULT_VENDOR_CHAINS:
        raise ValueError(f"No default vendor policy declared for '{method}'")
    chain = [
        vendor
        for vendor in DEFAULT_VENDOR_CHAINS[method]
        if vendor in VENDOR_METHODS[method]
    ]
    if not chain:
        raise ValueError(f"No default vendor is registered for '{method}'")
    return chain


_SECRET_PATTERN = re.compile(
    r"(?i)(api[_ -]?key|authorization|username|password|token|secret)(\s*[=:]\s*|\s+)([^\s,;]+)"
)


def _safe_error(error: Exception) -> str:
    """Redact credentials that may appear in exception text for logs and returns."""
    return _SECRET_PATTERN.sub(r"\1=[REDACTED]", str(error))


def _no_data_message(error: NoMarketDataError) -> str:
    """Turn a total no-data outcome into a clear prompt the agent can consume."""
    resolved = (
        ""
        if error.canonical == error.symbol
        else f" (resolved to '{error.canonical}')"
    )
    reason = f" ({error.detail})" if error.detail else ""
    return (
        f"NO_DATA_AVAILABLE: No usable market data for '{error.symbol}'{resolved} from "
        f"any configured vendor{reason}. The symbol may be invalid, delisted, "
        f"not covered, or the vendor returned stale data. Do not estimate or "
        f"fabricate values — report that data is unavailable for this symbol."
    )


_LEGACY_NO_NEWS_PREFIXES = {
    "get_news": "no news found",
    "get_global_news": "no global news found",
}


def _is_legacy_no_news(method: str, result: Any) -> bool:
    """Recognize only legacy news no-content strings that require fallback."""
    prefix = _LEGACY_NO_NEWS_PREFIXES.get(method)
    return bool(
        prefix
        and isinstance(result, str)
        and result.strip().lower().startswith(prefix)
    )


def _execute_route(
    method: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    is_usable: Callable[[Any], bool],
) -> tuple[Any | None, str, NoMarketDataError | None, Exception | None, str | None]:
    """Run the vendor chain and keep failure type for raise vs degrade.

    Distinguishes no-data, vendor exceptions, and legacy empty-news strings so
    the text API does not conflate them and the structured API can keep
    ``NoMarketDataError``.
    """
    category = get_category_for_method(method)
    last_no_data: NoMarketDataError | None = None
    first_error: Exception | None = None
    last_no_news: str | None = None

    for vendor in _vendor_chain(method, category, args):
        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl
        try:
            result = impl_func(*args, **kwargs)
            # Legacy news APIs encode empty results as text; treat as fallback, not success.
            if _is_legacy_no_news(method, result):
                last_no_news = result
                continue
            if is_usable(result):
                return result, category, last_no_data, first_error, last_no_news
            symbol = str(args[0]) if args else method
            last_no_data = NoMarketDataError(
                symbol, detail=f"{vendor} returned an empty or invalid result"
            )
        except VendorRateLimitError as error:
            logger.warning(
                "Vendor %r rate-limited for %s; trying next vendor.", vendor, method
            )
            if first_error is None:
                first_error = error
        except VendorNotConfiguredError as error:
            logger.debug(
                "Vendor %r not configured for %s; trying next vendor.", vendor, method
            )
            if first_error is None:
                first_error = error
        except NoMarketDataError as error:
            last_no_data = error
        except Exception as error:
            logger.warning(
                "Vendor %r failed for %s: %s",
                vendor,
                method,
                _safe_error(error),
            )
            if first_error is None:
                first_error = error
    return None, category, last_no_data, first_error, last_no_news


def _is_usable_string(result: Any) -> bool:
    """Whether a text-compatible result is non-empty usable content, not an error."""
    if not isinstance(result, str) or not result.strip():
        return False
    return not result.lstrip().lower().startswith(
        ("error ", "error retrieving", "error fetching")
    )


def _is_usable_structured(result: Any) -> bool:
    """Whether a structured result contains a non-empty DataFrame or dict."""
    if isinstance(result, dict):
        return bool(result)
    if not isinstance(result, ProviderResult):
        return False
    data = result.data
    if isinstance(data, pd.DataFrame):
        return not data.empty
    if isinstance(data, dict):
        return bool(data)
    return False


def route_to_vendor(method: str, *args, **kwargs) -> str:
    """Route a text-compatible tool.

    Core categories raise vendor errors. Optional extras return a safe
    ``DATA_UNAVAILABLE`` string so callers can continue without the extra.
    """
    result, category, last_no_data, first_error, last_no_news = _execute_route(
        method, args, kwargs, _is_usable_string
    )
    if result is not None:
        return result
    if last_no_news is not None and last_no_data is None and first_error is None:
        return last_no_news
    if last_no_data is not None:
        if first_error is not None and not isinstance(
            first_error, VendorNotConfiguredError
        ):
            logger.warning(
                "Returning NO_DATA for %s, but a vendor errored earlier: %s",
                method,
                _safe_error(first_error),
            )
        return _no_data_message(last_no_data)
    if first_error is not None:
        if category in OPTIONAL_CATEGORIES:
            safe_error = _safe_error(first_error)
            logger.warning(
                "Optional %s unavailable for %s: %s", category, method, safe_error
            )
            return (
                f"DATA_UNAVAILABLE: optional {category} could not be retrieved "
                f"({safe_error}). Proceed without it; do not fabricate values."
            )
        raise first_error
    raise RuntimeError(f"No available vendor for '{method}'")


def route_structured(
    method: str, *args, **kwargs
) -> ProviderResult[Any] | dict[str, str]:
    """Route a structured tool and turn empty results into explicit exceptions.

    Callers that need ``ProviderResult`` metadata cannot substitute error
    strings the way the text API does, or downstream would treat failure as
    valid prices or fundamentals.
    """
    result, _, last_no_data, first_error, _ = _execute_route(
        method, args, kwargs, _is_usable_structured
    )
    if result is not None:
        return result
    if last_no_data is not None:
        raise last_no_data
    if first_error is not None:
        raise first_error
    raise RuntimeError(f"No available vendor for '{method}'")
