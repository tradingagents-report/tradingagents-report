"""TradingView adapters for fundamentals and financial statements."""

from __future__ import annotations

import time
from collections.abc import Mapping
from datetime import date, datetime, timezone
from threading import Lock
from typing import Any
from urllib.parse import quote

import pandas as pd

from ..errors import NoMarketDataError
from ..provider_models import parse_instrument
from .client import TradingViewClient
from .symbols import encode_path_symbol, resolve_tradingview_symbol

_MARKET_DATA_CACHE_TTL_SECONDS = 300
_MARKET_DATA_CACHE: dict[str, tuple[float, str, dict[str, Any]]] = {}
_MARKET_DATA_CACHE_LOCK = Lock()

_FUNDAMENTAL_FIELDS = (
    # Name is resolved via _company_name() so localized names win over English.
    ("company", "sector", "Sector"),
    ("company", "industry", "Industry"),
    ("company", "founded", "Founded"),
    ("company", "number_of_employees", "Employees"),
    ("company", "business_description", "Business Description"),
    ("indicators", "market_cap_basic", "Market Cap"),
    ("indicators", "price_earnings", "PE Ratio (TTM)"),
    ("indicators", "price_book_ratio", "Price to Book"),
    ("indicators", "price_sales_ratio", "Price to Sales"),
    ("indicators", "price_52_week_high", "52 Week High"),
    ("indicators", "price_52_week_low", "52 Week Low"),
    ("indicators", "price_percent_change_52_week", "52 Week Change %"),
    ("indicators", "beta_1_year", "Beta (1Y)"),
    ("indicators", "quick_ratio", "Quick Ratio"),
    ("indicators", "earnings_release_date", "Last Earnings Date"),
    ("indicators", "earnings_release_next_date", "Next Earnings Date"),
    ("indicators", "earnings_per_share_forecast_next_fh", "EPS Forecast (Next)"),
    ("ttm", "earnings_per_share_diluted_ttm", "EPS (TTM)"),
    ("ttm", "total_revenue_ttm", "Revenue (TTM)"),
    ("ttm", "gross_profit_ttm", "Gross Profit"),
    ("ttm", "ebitda_ttm", "EBITDA"),
    ("ttm", "net_income_ttm", "Net Income"),
    ("ttm", "net_margin_ttm", "Profit Margin"),
    ("ttm", "operating_margin_ttm", "Operating Margin"),
    ("ttm", "return_on_equity_ttm", "Return on Equity"),
    ("ttm", "return_on_assets_ttm", "Return on Assets"),
    ("ttm", "debt_to_equity_ttm", "Debt to Equity"),
    ("ttm", "dividend_payout_ratio_ttm", "Dividend Payout Ratio (TTM)"),
    ("ttm", "free_cash_flow_ttm", "Free Cash Flow"),
    ("current", "current_ratio_current", "Current Ratio"),
    ("current", "book_value_per_share_current", "Book Value"),
    ("current", "dividends_yield_current", "Dividend Yield"),
)

_EPOCH_FIELDS = frozenset(
    {
        "earnings_release_date",
        "earnings_release_next_date",
        "earnings_release_calendar_date",
        "earnings_release_next_calendar_date",
        "ipo_offer_date",
        "dividend_ex_date_recent",
        "dividend_payment_date_recent",
    }
)

_ANALYST_FIELDS = (
    ("recommendation_buy", "Buy"),
    ("recommendation_over", "Outperform"),
    ("recommendation_hold", "Hold"),
    ("recommendation_under", "Underperform"),
    ("recommendation_sell", "Sell"),
    ("recommendation_total", "Total Analysts"),
    ("recommendation_mark", "Consensus Mark"),
    ("price_target_average", "Price Target (Avg)"),
    ("price_target_median", "Price Target (Median)"),
    ("price_target_high", "Price Target (High)"),
    ("price_target_low", "Price Target (Low)"),
    ("price_target_estimates_num", "Price Target Estimates"),
    ("recommendation_date", "Recommendation Date"),
    ("price_target_date", "Price Target Date"),
)

_DIVIDEND_FIELDS = (
    ("dividend_yield_recent", "Dividend Yield"),
    ("dividend_amount_recent", "Recent Dividend Amount"),
    ("continuous_dividend_payout", "Continuous Payout Years"),
    ("continuous_dividend_growth", "Continuous Growth Years"),
    ("dividend_ex_date_recent", "Ex-Dividend Date"),
    ("dividend_payment_date_recent", "Payment Date"),
)

_BUSINESS_DESCRIPTION_MAX_CHARS = 500

# TradingView exposes all statement fields in the same response shape. These
# provider-native families keep the compatibility adapters semantically distinct.
_BALANCE_SHEET_FIELDS = frozenset(
    {
        "accounts_payable",
        "accounts_receivables_net",
        "cash_n_equivalents",
        "cash_n_short_term_invest",
        "common_equity_total",
        "common_stock_par",
        "current_port_debt_capital_leases",
        "deferred_income_current",
        "goodwill",
        "invested_capital",
        "long_term_debt",
        "long_term_debt_excl_capital_lease",
        "long_term_investments",
        "minority_interest",
        "net_debt",
        "other_common_equity",
        "other_current_assets_total",
        "other_current_liabilities",
        "other_liabilities_total",
        "other_receivables",
        "paid_in_capital",
        "ppe_total_gross",
        "ppe_total_net",
        "preferred_stock_carrying_value",
        "retained_earnings",
        "shrhldrs_equity",
        "short_term_debt",
        "short_term_debt_excl_current_port",
        "short_term_invest",
        "tangible_assets",
        "total_assets",
        "total_current_assets",
        "total_current_liabilities",
        "total_debt",
        "total_equity",
        "total_inventory",
        "total_liabilities",
        "total_liabilities_shrhldrs_equity",
        "total_non_current_assets",
        "total_non_current_liabilities",
        "total_receivables_net",
        "treasury_stock_common",
        "working_capital",
    }
)
_CASH_FLOW_FIELDS = frozenset(
    {
        "capital_expenditures",
        "capital_expenditures_fixed_assets",
        "capital_expenditures_other_assets",
        "cash_f_financing_activities",
        "cash_f_investing_activities",
        "cash_f_operating_activities",
        "cash_flow_deferred_taxes",
        "cash_flow_deprecation_n_amortization",
        "change_in_accounts_payable",
        "change_in_accounts_receivable",
        "change_in_inventories",
        "change_in_other_assets",
        "changes_in_working_capital",
        "common_dividends_cash_flow",
        "free_cash_flow",
        "funds_f_operations",
        "issuance_of_debt_net",
        "issuance_of_long_term_debt",
        "issuance_of_short_term_debt",
        "issuance_of_stock_net",
        "non_cash_items",
        "other_financing_cash_flow_items_total",
        "other_financing_cash_flow_sources",
        "other_financing_cash_flow_uses",
        "other_investing_cash_flow_items_total",
        "other_investing_cash_flow_sources",
        "other_investing_cash_flow_uses",
        "preferred_dividends_cash_flow",
        "proceeds_from_stock_options",
        "purchase_of_business",
        "purchase_of_investments",
        "purchase_of_stock",
        "purchase_sale_business",
        "purchase_sale_investments",
        "reduction_of_long_term_debt",
        "sale_of_stock",
        "sales_of_business",
        "sales_of_investments",
        "supplying_of_long_term_debt",
        "total_cash_dividends_paid",
    }
)
_INCOME_STATEMENT_FIELDS = frozenset(
    {
        "after_tax_other_income",
        "cost_of_goods",
        "cost_of_goods_excl_dep_amort",
        "dep_amort_exp_income_s",
        "depreciation_depletion",
        "diluted_net_income",
        "discontinued_operations",
        "earnings_per_share",
        "earnings_per_share_basic",
        "earnings_per_share_diluted",
        "ebit",
        "ebitda",
        "equity_in_earnings",
        "gross_profit",
        "income_tax",
        "interest_expense_on_debt",
        "minority_interest_exp",
        "net_income",
        "net_income_bef_disc_oper",
        "net_income_starting_line",
        "non_oper_income",
        "non_oper_interest_income",
        "oper_income",
        "operating_expenses",
        "other_income",
        "other_oper_expense_total",
        "pretax_equity_in_earnings",
        "pretax_income",
        "research_and_dev",
        "revenue",
        "sell_gen_admin_exp_other",
        "sell_gen_admin_exp_total",
        "total_extra_items",
        "total_non_oper_income",
        "total_oper_expense",
        "total_revenue",
        "unusual_expense_inc",
    }
)

FUNDAMENTALS_CHART_MAX_PERIODS = 8
FUNDAMENTALS_CHART_FIELDS: tuple[str, ...] = (
    "total_revenue",
    "oper_income",
    "net_income",
    "cash_f_operating_activities",
    "free_cash_flow",
    "total_debt",
    "total_equity",
)
_FUNDAMENTALS_CHART_FIELD_SET = frozenset(FUNDAMENTALS_CHART_FIELDS)


def _search_markets(client: TradingViewClient, query: str, asset_class: str):
    filter_name = {"equity": "stock"}.get(asset_class, asset_class)
    payload = client.get(
        f"/api/search/market/{quote(query, safe='')}",
        params={"filter": filter_name},
    )
    markets = payload.get("markets", [])
    return markets if isinstance(markets, list) else []


def _resolve(ticker: str, client: TradingViewClient) -> str:
    ref = parse_instrument(ticker)
    search = None
    if not ref.exchange_hint:

        def search(query: str):
            return _search_markets(client, query, ref.asset_class)

    return resolve_tradingview_symbol(ref, search=search).symbol


def _get_market_data(
    ticker: str,
    client: TradingViewClient | None,
) -> tuple[str, dict[str, Any]]:
    if client is not None:
        symbol = _resolve(ticker, client)
        return symbol, client.get(f"/api/market-data/{encode_path_symbol(symbol)}")

    cache_key = ticker.strip().upper()
    with _MARKET_DATA_CACHE_LOCK:
        now = time.monotonic()
        cached = _MARKET_DATA_CACHE.get(cache_key)
        if cached is not None and now - cached[0] < _MARKET_DATA_CACHE_TTL_SECONDS:
            return cached[1], cached[2]

        api = TradingViewClient()
        symbol = _resolve(ticker, api)
        payload = api.get(f"/api/market-data/{encode_path_symbol(symbol)}")
        _MARKET_DATA_CACHE[cache_key] = (time.monotonic(), symbol, payload)
        return symbol, payload


def _company_name(company: Any) -> str | None:
    """Prefer localized company name when TradingView provides one."""
    if not isinstance(company, Mapping):
        return None
    for key in ("local_description", "local-description", "description"):
        value = company.get(key)
        if isinstance(value, str) and value.strip():
            text = value.strip()
            if text.lower() not in {"-", "n/a", "na", "none", "null", "unknown"}:
                return text
    return None


def _header(
    title: str,
    symbol: str,
    freq: str | None = None,
    *,
    quote_currency: str | None = None,
    fundamental_currency: str | None = None,
) -> str:
    suffix = f" ({freq})" if freq is not None else ""
    header = f"# {title} for {symbol}{suffix}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    if quote_currency:
        header += f"# Quote currency: {quote_currency}\n"
    if fundamental_currency:
        header += f"# Fundamental reporting currency: {fundamental_currency}\n"
    header += "\n"
    return header


def _currencies(payload: Mapping[str, Any]) -> tuple[str | None, str | None]:
    company = payload.get("company")
    if not isinstance(company, Mapping):
        return None, None
    quote = company.get("currency_code") or company.get("currency")
    fundamental = company.get("fundamental_currency_code") or company.get("currency_fund")
    return _currency(quote), _currency(fundamental)


def _currency(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    currency = value.strip().upper()
    return currency or None


def _format_scalar(field: str, value: Any) -> str | None:
    if isinstance(value, (dict, list)) or value is None:
        return None
    if field in _EPOCH_FIELDS and isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m-%d")
        except (OverflowError, OSError, ValueError):
            return None
    if field == "business_description" and isinstance(value, str):
        text = value.strip()
        if len(text) > _BUSINESS_DESCRIPTION_MAX_CHARS:
            return text[:_BUSINESS_DESCRIPTION_MAX_CHARS].rstrip() + "…"
        return text
    return str(value)


def _section_lines(section: Any, fields: tuple[tuple[str, str], ...]) -> list[str]:
    if not isinstance(section, Mapping):
        return []
    lines = []
    for field, label in fields:
        formatted = _format_scalar(field, section.get(field))
        if formatted is not None:
            lines.append(f"{label}: {formatted}")
    return lines


def get_tradingview_fundamentals(
    ticker: str,
    curr_date: str | None = None,
    *,
    client: TradingViewClient | None = None,
) -> str:
    """Return a TradingView fundamentals overview in the existing text format."""
    del curr_date
    symbol, payload = _get_market_data(ticker, client)
    quote_currency, fundamental_currency = _currencies(payload)

    lines = []
    name = _company_name(payload.get("company"))
    if name:
        lines.append(f"Name: {name}")
    for section_name, field, label in _FUNDAMENTAL_FIELDS:
        section = payload.get(section_name)
        value = section.get(field) if isinstance(section, Mapping) else None
        formatted = _format_scalar(field, value)
        if formatted is not None:
            lines.append(f"{label}: {formatted}")

    analyst_lines = _section_lines(payload.get("analyst_recommendations"), _ANALYST_FIELDS)
    if analyst_lines:
        lines.append("")
        lines.append("## Analyst Recommendations")
        lines.extend(analyst_lines)

    dividend_lines = _section_lines(payload.get("dividend"), _DIVIDEND_FIELDS)
    if dividend_lines:
        lines.append("")
        lines.append("## Dividends")
        lines.extend(dividend_lines)

    if not lines:
        raise NoMarketDataError(ticker, symbol, "no fundamental fields returned")
    return _header(
        "Company Fundamentals",
        symbol,
        quote_currency=quote_currency,
        fundamental_currency=fundamental_currency,
    ) + "\n".join(lines)


def _fiscal_end(value: Any) -> date | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).date()
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _is_cell(value: Any) -> bool:
    return value is not None and not isinstance(value, (dict, list))


def _allowed_fields(
    data: Mapping[str, Any], suffix: str, field_family: frozenset[str]
) -> dict[str, Any]:
    fields = {}
    for key, value in data.items():
        if not isinstance(key, str) or not key.endswith(suffix):
            continue
        field = key[: -len(suffix)]
        if field in field_family:
            fields[field] = value
    return fields


def _collect_statement_periods(
    current: Mapping[str, Any],
    history: Mapping[str, Any],
    frequency: str,
    curr_date: str | None,
    field_family: frozenset[str],
) -> dict[str, dict[str, Any]]:
    period_suffix = "fq" if frequency == "quarterly" else "fy"
    period_key = f"fiscal_period_{period_suffix}"
    period_end_key = f"fiscal_period_end_{period_suffix}"
    value_suffix = f"_{period_suffix}"
    cutoff = date.fromisoformat(curr_date) if curr_date is not None else None
    periods: dict[str, dict[str, Any]] = {}

    current_period = current.get(period_key)
    current_end = _fiscal_end(current.get(period_end_key))
    if isinstance(current_period, str) and current_period:
        values = {
            field: value
            for field, value in _allowed_fields(current, value_suffix, field_family).items()
            if _is_cell(value)
        }
        if values:
            periods[current_period] = {"end": current_end, "values": values}

    history_periods = history.get(f"{period_key}_h")
    history_ends = history.get(f"{period_end_key}_h")
    history_fields = _allowed_fields(history, f"{value_suffix}_h", field_family)
    if isinstance(history_periods, list) and isinstance(history_ends, list):
        for index, period in enumerate(history_periods):
            if not isinstance(period, str) or not period or index >= len(history_ends):
                continue
            fiscal_end = _fiscal_end(history_ends[index])
            existing = periods.get(period)
            if existing is not None and existing["end"] is None and fiscal_end is not None:
                existing["end"] = fiscal_end
            values = {
                field: series[index]
                for field, series in history_fields.items()
                if isinstance(series, list) and index < len(series) and _is_cell(series[index])
            }
            if not values:
                continue
            if existing is not None:
                for field, value in values.items():
                    existing["values"].setdefault(field, value)
            else:
                periods[period] = {"end": fiscal_end, "values": values}

    if cutoff is not None:
        periods = {
            period: data
            for period, data in periods.items()
            if data["end"] is not None and data["end"] <= cutoff
        }
    return periods


def _statement_frame(
    current: Mapping[str, Any],
    history: Mapping[str, Any],
    frequency: str,
    curr_date: str | None,
    field_family: frozenset[str],
) -> pd.DataFrame:
    periods = _collect_statement_periods(
        current, history, frequency, curr_date, field_family
    )
    ordered_periods = sorted(
        periods,
        key=lambda period: (periods[period]["end"] or date.min, period),
        reverse=True,
    )
    fields = sorted({field for period in ordered_periods for field in periods[period]["values"]})
    return pd.DataFrame(
        {
            period: {field: periods[period]["values"].get(field) for field in fields}
            for period in ordered_periods
        },
        index=fields,
    )


def _get_statement(
    ticker: str,
    freq: str,
    curr_date: str | None,
    title: str,
    detail: str,
    field_family: frozenset[str],
    client: TradingViewClient | None,
) -> str:
    frequency = "quarterly" if freq.lower() == "quarterly" else "annual"
    symbol, payload = _get_market_data(ticker, client)
    quote_currency, fundamental_currency = _currencies(payload)
    current_key = f"financials_{frequency}"
    history_key = f"history_{frequency}"
    current = payload.get(current_key)
    history = payload.get(history_key)
    frame = _statement_frame(
        current if isinstance(current, Mapping) else {},
        history if isinstance(history, Mapping) else {},
        frequency,
        curr_date,
        field_family,
    )
    if frame.empty:
        raise NoMarketDataError(ticker, symbol, f"no {detail} data")
    return _header(
        title,
        symbol,
        freq,
        quote_currency=quote_currency,
        fundamental_currency=fundamental_currency,
    ) + frame.to_csv()


def get_tradingview_balance_sheet(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str | None = None,
    *,
    client: TradingViewClient | None = None,
) -> str:
    """Return a TradingView balance sheet in the existing CSV format."""
    return _get_statement(
        ticker,
        freq,
        curr_date,
        "Balance Sheet data",
        "balance sheet",
        _BALANCE_SHEET_FIELDS,
        client,
    )


def get_tradingview_cashflow(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str | None = None,
    *,
    client: TradingViewClient | None = None,
) -> str:
    """Return a TradingView cash-flow statement in the existing CSV format."""
    return _get_statement(
        ticker,
        freq,
        curr_date,
        "Cash Flow data",
        "cash flow",
        _CASH_FLOW_FIELDS,
        client,
    )


def get_tradingview_income_statement(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str | None = None,
    *,
    client: TradingViewClient | None = None,
) -> str:
    """Return a TradingView income statement in the existing CSV format."""
    return _get_statement(
        ticker,
        freq,
        curr_date,
        "Income Statement data",
        "income statement",
        _INCOME_STATEMENT_FIELDS,
        client,
    )


def _chart_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def build_fundamentals_chart(
    ticker: str,
    curr_date: str,
    *,
    client: TradingViewClient | None = None,
    max_periods: int = FUNDAMENTALS_CHART_MAX_PERIODS,
    payload_available_on: str | None = None,
) -> dict[str, object] | None:
    """Build a quarterly snapshot only from a payload available by curr_date."""
    cutoff = date.fromisoformat(curr_date)
    available_on = (
        date.fromisoformat(payload_available_on)
        if payload_available_on is not None
        else cutoff
    )
    if available_on > cutoff:
        return None
    window = max(1, min(int(max_periods), FUNDAMENTALS_CHART_MAX_PERIODS))
    try:
        _symbol, payload = _get_market_data(ticker, client)
    except Exception:  # noqa: BLE001 - missing statements must not fail analysis
        return None
    if not isinstance(payload, Mapping):
        return None

    current = payload.get("financials_quarterly")
    history = payload.get("history_quarterly")
    current_map = current if isinstance(current, Mapping) else {}
    history_map = history if isinstance(history, Mapping) else {}
    merged: dict[str, dict[str, Any]] = {}
    for field_family in (
        _INCOME_STATEMENT_FIELDS,
        _CASH_FLOW_FIELDS,
        _BALANCE_SHEET_FIELDS,
    ):
        periods = _collect_statement_periods(
            current_map,
            history_map,
            "quarterly",
            curr_date,
            field_family,
        )
        for period, data in periods.items():
            bucket = merged.setdefault(period, {"end": data.get("end"), "values": {}})
            if bucket["end"] is None and data.get("end") is not None:
                bucket["end"] = data["end"]
            values = data.get("values")
            if not isinstance(values, Mapping):
                continue
            for field, value in values.items():
                if field in _FUNDAMENTALS_CHART_FIELD_SET:
                    bucket["values"].setdefault(field, value)

    ordered = sorted(
        (
            period
            for period, data in merged.items()
            if data.get("end") is not None
        ),
        key=lambda period: (merged[period]["end"], period),
    )[-window:]
    rows: list[dict[str, object]] = []
    for period in ordered:
        data = merged[period]
        end = data["end"]
        row: dict[str, object] = {"end": end.isoformat()}
        values = data.get("values") if isinstance(data.get("values"), Mapping) else {}
        for field in FUNDAMENTALS_CHART_FIELDS:
            number = _chart_float(values.get(field))
            if number is not None:
                row[field] = number
        if len(row) > 1:
            rows.append(row)
    if not rows:
        return None

    _quote_currency, fundamental_currency = _currencies(payload)
    return {
        "as_of": curr_date,
        "frequency": "quarterly",
        "currency": fundamental_currency or _quote_currency,
        "source": "tradingview",
        "periods": rows,
    }
