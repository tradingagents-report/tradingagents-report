from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_news(
    ticker: Annotated[str, "Ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve news data for a given ticker symbol.
    Uses the configured news_data vendor.
    Args:
        ticker (str): Ticker symbol
        start_date (str): Start date in yyyy-mm-dd format
        end_date (str): End date in yyyy-mm-dd format
    Returns:
        str: A formatted string containing news data
    """
    return route_to_vendor("get_news", ticker, start_date, end_date)

@tool
def get_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int | None, "Days to look back; omit to use the configured default"] = None,
    limit: Annotated[int | None, "Max articles to return; omit to use the configured default"] = None,
) -> str:
    """
    Retrieve global news data.
    Uses the configured news_data vendor. Defaults for look_back_days and
    limit come from DEFAULT_CONFIG (global_news_lookback_days,
    global_news_article_limit); pass explicit values to override.

    Args:
        curr_date (str): Current date in yyyy-mm-dd format
        look_back_days (int): Number of days to look back; omit to inherit config
        limit (int): Maximum number of articles to return; omit to inherit config

    Returns:
        str: A formatted string containing global news data
    """
    return route_to_vendor("get_global_news", curr_date, look_back_days, limit)

@tool
def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """
    Retrieve insider transaction information about a company.
    Uses the configured news_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
    Returns:
        str: A report of insider transaction data
    """
    return route_to_vendor("get_insider_transactions", ticker)


@tool
def get_earnings_calendar(
    curr_date: Annotated[str, "Current analysis date in yyyy-mm-dd format"],
    look_forward_days: Annotated[int, "Days ahead to include"] = 14,
    market: Annotated[
        str | None,
        "Optional TradingView market code (america/china/hongkong/...). "
        "Omit to infer from ticker via the exchange catalog.",
    ] = None,
    ticker: Annotated[
        str | None,
        "Optional ticker to filter to one symbol; omit for market-wide list",
    ] = None,
) -> str:
    """
    Retrieve earnings calendar events around the analysis date.
    Future events omit realized surprise/actuals to reduce look-ahead bias.
    When market is omitted and ticker is set, market_code is inferred from
    the package-local exchanges.json catalog.
    """
    return route_to_vendor(
        "get_earnings_calendar",
        curr_date,
        look_forward_days,
        market,
        ticker,
    )


@tool
def get_economic_calendar(
    curr_date: Annotated[str, "Current analysis date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Days to look back"] = 7,
    look_forward_days: Annotated[int, "Days ahead to include"] = 14,
    market: Annotated[
        str | None,
        "Optional TradingView market code filter; omit for all markets",
    ] = None,
) -> str:
    """
    Retrieve macroeconomic calendar events (CPI, NFP, rates, etc.).
    Events after curr_date keep forecast/previous but redact actual prints.
    """
    return route_to_vendor(
        "get_economic_calendar",
        curr_date,
        look_back_days,
        look_forward_days,
        market,
    )
