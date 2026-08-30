from datetime import datetime
from io import StringIO

import pandas as pd

from ..errors import NoMarketDataError, VendorUnavailableError
from ..provider_models import ProviderResult, parse_instrument
from .common import _filter_csv_by_date_range, _make_api_request


def get_stock(
    symbol: str,
    start_date: str,
    end_date: str
) -> str:
    """
    Returns raw daily OHLCV values, adjusted close values, and historical split/dividend events
    filtered to the specified date range.

    Args:
        symbol: The name of the equity. For example: symbol=IBM
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        CSV string containing the daily adjusted time series data filtered to the date range.
    """
    # Parse dates to determine the range
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    today = datetime.now()

    # Choose outputsize based on whether the requested range is within the latest 100 days
    # Compact returns latest 100 data points, so check if start_date is recent enough
    days_from_today_to_start = (today - start_dt).days
    outputsize = "compact" if days_from_today_to_start < 100 else "full"

    params = {
        "symbol": symbol,
        "outputsize": outputsize,
        "datatype": "csv",
    }

    response = _make_api_request("TIME_SERIES_DAILY_ADJUSTED", params)

    return _filter_csv_by_date_range(response, start_date, end_date)


def fetch_alpha_vantage_ohlcv(
    symbol: str,
    start_date: str,
    end_date: str,
) -> ProviderResult[pd.DataFrame]:
    """Parse Alpha Vantage's filtered daily response into provider-neutral OHLCV."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    if end < start:
        raise ValueError("end_date must not be before start_date")

    response = get_stock(symbol, start_date, end_date)
    try:
        raw = pd.read_csv(StringIO(response))
    except (TypeError, ValueError, pd.errors.ParserError) as exc:
        raise VendorUnavailableError("Alpha Vantage returned malformed OHLCV CSV") from exc

    if raw.empty:
        raise NoMarketDataError(symbol, symbol, "Alpha Vantage returned no price rows")

    date_column = next(
        (column for column in ("Date", "timestamp") if column in raw.columns),
        None,
    )
    if date_column is None:
        serialized_index = next(
            (column for column in raw.columns if str(column).startswith("Unnamed:")),
            None,
        )
        date_column = serialized_index
    if date_column is None:
        raise NoMarketDataError(symbol, symbol, "Alpha Vantage returned no date field")

    value_columns = ("open", "high", "low", "close", "volume")
    if any(column not in raw.columns for column in value_columns):
        raise VendorUnavailableError("Alpha Vantage OHLCV CSV is missing required columns")

    frame = raw[[date_column, *value_columns]].rename(
        columns={
            date_column: "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    numeric = ["Open", "High", "Low", "Close", "Volume"]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="coerce")
    if frame["Date"].isna().any():
        raise NoMarketDataError(symbol, symbol, "Alpha Vantage returned invalid dates")
    if frame[numeric].isna().any().any():
        raise VendorUnavailableError("Alpha Vantage returned invalid OHLCV fields")
    frame = frame[(frame["Date"] >= start) & (frame["Date"] <= end)]
    if frame.empty:
        raise NoMarketDataError(
            symbol,
            symbol,
            f"no rows between {start_date} and {end_date}",
        )
    frame = frame.sort_values("Date").reset_index(drop=True)

    return ProviderResult(
        data=frame,
        provider="alpha_vantage",
        requested=parse_instrument(symbol),
        resolved_symbol=symbol.upper(),
        as_of=frame["Date"].max().to_pydatetime(),
        adjustment_mode="adjusted",
        provenance={"function": "TIME_SERIES_DAILY_ADJUSTED"},
    )
