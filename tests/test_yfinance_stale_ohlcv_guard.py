"""Stale OHLCV guard (#1021): a vendor returning a year-old partial frame must
be rejected, not fed into the report as if it were current.

The guard raises NoMarketDataError with a stale-specific detail, so the router's
existing try-next-vendor + single-sentinel handling applies and the sentinel
surfaces the reason.
"""
import copy
import unittest
from unittest import mock

import pandas as pd
import pytest

import tradingagents.dataflows.config as config_module
import tradingagents.dataflows.yfinance.market as y_finance
import tradingagents.default_config as default_config
from tradingagents.dataflows import interface
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.stockstats_utils import _assert_ohlcv_not_stale


def _frame(date):
    return pd.DataFrame(
        {
            "Date": [pd.Timestamp(date)],
            "Open": [330.0],
            "High": [332.0],
            "Low": [328.0],
            "Close": [330.58],
            "Volume": [1_000_000],
        }
    )


@pytest.mark.unit
class StaleGuardUnitTests(unittest.TestCase):
    def test_recent_prior_trading_day_is_accepted(self):
        # 1 day before curr_date — well within the freshness window.
        _assert_ohlcv_not_stale(_frame("2026-06-10"), "2026-06-11", "CB")

    def test_year_old_row_is_rejected_with_detail(self):
        with self.assertRaises(NoMarketDataError) as ctx:
            _assert_ohlcv_not_stale(_frame("2025-06-11"), "2026-06-11", "CB", "CB")
        msg = str(ctx.exception)
        self.assertIn("2025-06-11", msg)
        self.assertIn("2026-06-11", msg)
        self.assertIn("stale", msg)

    def test_empty_frame_is_left_to_caller(self):
        # Empty is a no-data condition handled elsewhere, not a staleness one.
        _assert_ohlcv_not_stale(
            pd.DataFrame(columns=["Date", "Close"]), "2026-06-11", "X"
        )

    def test_long_holiday_gap_within_threshold_is_accepted(self):
        _assert_ohlcv_not_stale(_frame("2026-06-02"), "2026-06-11", "X")  # 9 days


@pytest.mark.unit
class StaleGuardPropagationTests(unittest.TestCase):
    def test_structured_fetch_and_compatibility_output_share_validated_data(self):
        frame = pd.DataFrame(
            {
                "Open": [100.123], "High": [102.456], "Low": [99.0],
                "Close": [101.999], "Volume": [1_000],
            },
            index=pd.DatetimeIndex([pd.Timestamp("2026-06-11")], name="Date"),
        )

        ticker = mock.Mock()
        ticker.history.return_value = frame
        with mock.patch.object(y_finance.yf, "Ticker", return_value=ticker):
            result = y_finance.fetch_yfinance_ohlcv(
                "AAPL", "2026-06-01", "2026-06-11"
            )
        self.assertEqual(result.provider, "yfinance")
        self.assertEqual(result.resolved_symbol, "AAPL")
        self.assertEqual(list(result.data.columns), ["Date", "Open", "High", "Low", "Close", "Volume"])
        self.assertEqual(result.data.loc[0, "Close"], 102.0)

        with mock.patch.object(y_finance, "fetch_yfinance_ohlcv", return_value=result):
            output = y_finance.get_YFin_data_online(
                "AAPL", "2026-06-01", "2026-06-11"
            )
        self.assertIn("# Total records: 1", output)
        self.assertIn("2026-06-11,100.12,102.46,99.0,102.0,1000", output)

    def test_yfinance_identity_maps_vendor_fields(self):
        ticker = mock.Mock()
        ticker.info = {
            "longName": "Apple Inc.",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "exchange": "NMS",
            "quoteType": "EQUITY",
        }
        with mock.patch.object(y_finance.yf, "Ticker", return_value=ticker):
            identity = y_finance.get_yfinance_identity("AAPL")
        self.assertEqual(
            identity,
            {
                "company_name": "Apple Inc.",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "exchange": "NMS",
                "quote_type": "EQUITY",
            },
        )

    def test_yfinance_identity_falls_back_to_short_name(self):
        ticker = mock.Mock()
        ticker.info = {"shortName": "Apple"}

        with mock.patch.object(y_finance.yf, "Ticker", return_value=ticker):
            identity = y_finance.get_yfinance_identity("AAPL")

        self.assertEqual(identity["company_name"], "Apple")

    def test_get_yfin_data_online_raises_on_stale_frame(self):
        stale = pd.DataFrame(
            {
                "Open": [280.0], "High": [286.0], "Low": [278.0],
                "Close": [284.45], "Volume": [1_000_000],
            },
            index=pd.DatetimeIndex([pd.Timestamp("2025-06-11")], name="Date"),
        )

        class DummyTicker:
            def __init__(self, symbol):
                pass

            def history(self, start, end):
                return stale

        with mock.patch.object(y_finance.yf, "Ticker", DummyTicker), \
                self.assertRaises(NoMarketDataError):
            y_finance.get_YFin_data_online("CB", "2026-06-01", "2026-06-11")


@pytest.mark.unit
class StaleGuardRoutingTests(unittest.TestCase):
    def setUp(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    def tearDown(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    def test_router_sentinel_surfaces_stale_reason(self):
        set_config({"data_vendors": {"core_stock_apis": "yfinance"}})

        def _stale(symbol, *a, **k):
            raise NoMarketDataError(
                symbol, symbol, "latest row is 2025-06-11, 365 days before ... (stale)"
            )

        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_stock_data": {"yfinance": _stale}},
            clear=False,
        ):
            out = interface.route_to_vendor(
                "get_stock_data", "CB", "2026-06-01", "2026-06-11"
            )
        self.assertIn("NO_DATA_AVAILABLE", out)
        self.assertIn("stale", out)  # the typed detail is surfaced to the agent


if __name__ == "__main__":
    unittest.main()
