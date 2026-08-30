"""Vendor router must respect the configured chain and never silently hide a
broken primary.

Regressions for #988 (explicit single-vendor config still fell back to others),
#289 (fallback ran for unchosen vendors), and #989 (serious primary failures
were swallowed without a trace).
"""
import copy
import unittest
from unittest import mock

import pandas as pd
import pytest

import tradingagents.dataflows.config as config_module
import tradingagents.default_config as default_config
from tradingagents.dataflows import interface
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.errors import NoMarketDataError, VendorNotConfiguredError
from tradingagents.dataflows.provider_models import ProviderResult, parse_instrument


def _reset_config():
    # Hard reset: set_config() merges, so empty DEFAULT dicts (e.g. tool_vendors)
    # don't clear keys leaked by other tests. Replace the global outright.
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)
    config_module._config["us_data_vendors"] = None


def _no_data(symbol, *a, **k):
    raise NoMarketDataError(symbol, symbol, "no rows")


def _returns(value):
    def impl(symbol, *a, **k):
        return value
    return impl


def _raises(exc):
    def impl(symbol, *a, **k):
        raise exc
    return impl


@pytest.mark.unit
class VendorRoutingTests(unittest.TestCase):
    def setUp(self):
        _reset_config()

    def tearDown(self):
        _reset_config()

    def _route(self, vendors_for_get_stock_data):
        return mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_stock_data": vendors_for_get_stock_data},
            clear=False,
        )

    def test_explicit_single_vendor_does_not_fall_back(self):
        # #988: with yfinance pinned, a healthy alpha_vantage must NOT be used.
        set_config({"data_vendors": {"core_stock_apis": "yfinance"}})
        av = mock.Mock(side_effect=_returns("AV_DATA"))
        with self._route({"yfinance": _no_data, "alpha_vantage": av}):
            result = interface.route_to_vendor("get_stock_data", "FAKE", "2026-01-01", "2026-01-10")
        self.assertIn("NO_DATA_AVAILABLE", result)
        av.assert_not_called()  # the unchosen vendor was never tried

    def test_explicit_multi_vendor_falls_back_within_chain(self):
        # Listing both vendors opts in to ordered fallback.
        set_config({"data_vendors": {"core_stock_apis": "yfinance,alpha_vantage"}})
        with self._route({"yfinance": _no_data, "alpha_vantage": _returns("AV_DATA")}):
            result = interface.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-10")
        self.assertEqual(result, "AV_DATA")

    def test_primary_error_is_logged_not_masked(self):
        # #989: primary errors + fallback no-data -> NO_DATA, but the failure
        # must be visible in logs (broken primary not hidden).
        set_config({"data_vendors": {"core_stock_apis": "yfinance,alpha_vantage"}})
        with self._route({"yfinance": _raises(ValueError("boom")), "alpha_vantage": _no_data}), \
                self.assertLogs("tradingagents.dataflows.interface", level="WARNING") as cm:
            result = interface.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-10")
        self.assertIn("NO_DATA_AVAILABLE", result)
        joined = "\n".join(cm.output)
        self.assertIn("boom", joined)            # the real error surfaced in logs
        self.assertIn("yfinance", joined)

    def test_unknown_configured_vendor_raises(self):
        set_config({"data_vendors": {"core_stock_apis": "bogus_vendor"}})
        with self.assertRaises(ValueError) as ctx:
            interface.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-10")
        self.assertIn("bogus_vendor", str(ctx.exception))

    def test_default_sentinel_uses_all_vendors(self):
        # No explicit choice ("default") uses the declared method policy.
        set_config({"data_vendors": {"core_stock_apis": "default"}})
        with self._route({"alpha_vantage": _returns("AV_DATA"), "yfinance": _returns("YF_DATA")}):
            result = interface.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-10")
        self.assertEqual(result, "YF_DATA")

    def test_default_policy_is_explicit_not_registry_order(self):
        set_config({"data_vendors": {"core_stock_apis": "default"}})
        with self._route(
            {
                "alpha_vantage": _returns("AV"),
                "yfinance": _returns("YF"),
                "tradingview": _returns("TV"),
            }
        ):
            result = interface.route_to_vendor("get_stock_data", "AAPL")
        self.assertEqual(result, "TV")

    def test_default_policy_is_immutable(self):
        with self.assertRaises(TypeError):
            interface.DEFAULT_VENDOR_CHAINS["get_stock_data"] = ("yfinance",)

    def test_missing_configuration_falls_back_without_warning(self):
        set_config({"data_vendors": {"core_stock_apis": "tradingview,yfinance"}})
        with self._route(
            {
                "tradingview": _raises(VendorNotConfiguredError("missing")),
                "yfinance": _returns("YF"),
            }
        ), self.assertLogs("tradingagents.dataflows.interface", level="DEBUG") as cm:
            result = interface.route_to_vendor("get_stock_data", "AAPL")
        self.assertEqual(result, "YF")
        warning_lines = [line for line in cm.output if "WARNING" in line]
        self.assertEqual(warning_lines, [])

    def test_string_route_rejects_empty_and_provider_error_text(self):
        set_config(
            {"data_vendors": {"core_stock_apis": "tradingview,yfinance,alpha_vantage"}}
        )
        with self._route(
            {
                "tradingview": _returns("Error fetching data"),
                "yfinance": _returns(""),
                "alpha_vantage": _returns("AV"),
            }
        ):
            result = interface.route_to_vendor("get_stock_data", "AAPL")
        self.assertEqual(result, "AV")

    def test_company_news_falls_back_after_legacy_no_news_text(self):
        set_config(
            {"data_vendors": {"news_data": "tradingview,yfinance,alpha_vantage"}}
        )
        alpha_vantage = mock.Mock(side_effect=AssertionError("outside fallback chain"))
        with self._route_method(
            "get_news",
            {
                "tradingview": _returns("No news found for AAPL between 2026-07-01 and 2026-07-10"),
                "yfinance": _returns("## AAPL News, from 2026-07-01 to 2026-07-10:\n\n### Article"),
                "alpha_vantage": alpha_vantage,
            },
        ):
            result = interface.route_to_vendor(
                "get_news", "AAPL", "2026-07-01", "2026-07-10"
            )
        self.assertIn("### Article", result)
        alpha_vantage.assert_not_called()

    def test_global_news_falls_back_after_legacy_no_news_text(self):
        set_config(
            {"data_vendors": {"news_data": "tradingview,yfinance,alpha_vantage"}}
        )
        alpha_vantage = mock.Mock(side_effect=AssertionError("outside fallback chain"))
        with self._route_method(
            "get_global_news",
            {
                "tradingview": _returns("No global news found between 2026-07-03 and 2026-07-10"),
                "yfinance": _returns("## Global News\n\n### Article"),
                "alpha_vantage": alpha_vantage,
            },
        ):
            result = interface.route_to_vendor("get_global_news", "2026-07-10", 7, 50)
        self.assertIn("### Article", result)
        alpha_vantage.assert_not_called()

    def test_company_news_returns_legacy_no_news_after_configured_chain_is_empty(self):
        set_config(
            {"data_vendors": {"news_data": "tradingview,yfinance,alpha_vantage"}}
        )
        with self._route_method(
            "get_news",
            {
                "tradingview": _returns("No news found for AAPL between 2026-07-01 and 2026-07-10"),
                "yfinance": _returns("No news found for AAPL between 2026-07-01 and 2026-07-10"),
                "alpha_vantage": _returns("No news found for AAPL between 2026-07-01 and 2026-07-10"),
            },
        ):
            result = interface.route_to_vendor(
                "get_news", "AAPL", "2026-07-01", "2026-07-10"
            )
        self.assertEqual(
            result, "No news found for AAPL between 2026-07-01 and 2026-07-10"
        )

    def test_global_news_returns_legacy_no_news_after_configured_chain_is_empty(self):
        set_config(
            {"data_vendors": {"news_data": "tradingview,yfinance,alpha_vantage"}}
        )
        with self._route_method(
            "get_global_news",
            {
                "tradingview": _returns("No global news found between 2026-07-03 and 2026-07-10"),
                "yfinance": _returns("No global news found between 2026-07-03 and 2026-07-10"),
                "alpha_vantage": _returns("No global news found between 2026-07-03 and 2026-07-10"),
            },
        ):
            result = interface.route_to_vendor("get_global_news", "2026-07-10", 7, 50)
        self.assertEqual(
            result, "No global news found between 2026-07-03 and 2026-07-10"
        )

    def test_explicit_news_chain_does_not_fall_back_beyond_its_boundary(self):
        set_config({"tool_vendors": {"get_news": "tradingview"}})
        yfinance = mock.Mock(side_effect=AssertionError("outside explicit chain"))
        with self._route_method(
            "get_news",
            {
                "tradingview": _returns("No news found for AAPL"),
                "yfinance": yfinance,
            },
        ):
            result = interface.route_to_vendor("get_news", "AAPL", "2026-07-01", "2026-07-10")
        self.assertEqual(result, "No news found for AAPL")
        yfinance.assert_not_called()

    def test_insider_no_transactions_text_remains_a_usable_response(self):
        set_config({"data_vendors": {"news_data": "yfinance,alpha_vantage"}})
        alpha_vantage = mock.Mock(side_effect=AssertionError("must not fall back"))
        with self._route_method(
            "get_insider_transactions",
            {
                "yfinance": _returns("No insider transactions reported for symbol 'AAPL'"),
                "alpha_vantage": alpha_vantage,
            },
        ):
            result = interface.route_to_vendor("get_insider_transactions", "AAPL")
        self.assertIn("No insider transactions", result)
        alpha_vantage.assert_not_called()

    def test_structured_route_rejects_empty_provider_result(self):
        set_config({"data_vendors": {"core_stock_apis": "default"}})
        requested = parse_instrument("AAPL")
        empty = ProviderResult(pd.DataFrame(), "tradingview", requested, "NASDAQ:AAPL")
        good = ProviderResult(
            pd.DataFrame({"Close": [1]}), "yfinance", requested, "AAPL"
        )
        with self._route_method(
            "get_ohlcv",
            {"tradingview": lambda: empty, "yfinance": lambda: good},
        ):
            result = interface.route_structured("get_ohlcv")
        self.assertEqual(result.provider, "yfinance")

    def test_structured_route_accepts_only_declared_result_shapes(self):
        set_config({"data_vendors": {"core_stock_apis": "default"}})
        requested = parse_instrument("AAPL")
        good = ProviderResult(
            pd.DataFrame({"Close": [1]}), "yfinance", requested, "AAPL"
        )

        invalid_results = (
            42,
            ["not", "structured"],
            pd.DataFrame({"Close": [999]}),
            ProviderResult([1, 2], "tradingview", requested, "NASDAQ:AAPL"),
        )
        for invalid in invalid_results:
            with self.subTest(invalid=type(invalid).__name__), self._route_method(
                "get_ohlcv",
                {
                    "alpha_vantage": lambda: ProviderResult(
                        pd.DataFrame({"Close": [2]}),
                        "alpha_vantage",
                        requested,
                        "AAPL",
                    ),
                    "yfinance": lambda: good,
                    "tradingview": lambda invalid=invalid: invalid,
                },
            ):
                result = interface.route_structured("get_ohlcv")
            self.assertIs(result, good)

    def test_structured_route_rejects_empty_identity_dict(self):
        set_config({"data_vendors": {"instrument_data": "tradingview,yfinance"}})
        with self._route_method(
            "get_instrument_identity",
            {"tradingview": lambda: {}, "yfinance": lambda: {"company_name": "Apple"}},
        ):
            result = interface.route_structured("get_instrument_identity")
        self.assertEqual(result, {"company_name": "Apple"})

    def test_structured_identity_falls_back_after_tradingview_has_no_data(self):
        set_config({"data_vendors": {"instrument_data": "tradingview,yfinance"}})
        with self._route_method(
            "get_instrument_identity",
            {
                "tradingview": _raises(
                    NoMarketDataError("AAPL", "NASDAQ:AAPL", "no company identity")
                ),
                "yfinance": lambda: {"company_name": "Apple Inc.", "quote_type": "stock"},
            },
        ):
            result = interface.route_structured("get_instrument_identity")
        self.assertEqual(result["company_name"], "Apple Inc.")

    def _route_method(self, method, vendors):
        return mock.patch.dict(interface.VENDOR_METHODS, {method: vendors}, clear=False)

    def test_optional_category_degrades_instead_of_raising(self):
        # An optional enrichment vendor (FRED macro) that raises must NOT abort
        # the run — the router returns a sentinel so the analysis proceeds.
        set_config({"data_vendors": {"macro_data": "fred"}})
        with self._route_method(
            "get_macro_indicators", {"fred": _raises(ValueError("FRED 400: bad series"))}
        ):
            result = interface.route_to_vendor("get_macro_indicators", "cpi", "2026-01-01")
        self.assertIn("DATA_UNAVAILABLE", result)
        self.assertIn("macro_data", result)

    def test_core_category_still_raises_on_error(self):
        # A core category (single configured vendor) propagates the error so a
        # broken primary is loud, not silently degraded.
        set_config({"data_vendors": {"core_stock_apis": "yfinance"}})
        with self._route({"yfinance": _raises(ValueError("boom"))}), \
                self.assertRaises(ValueError):
            interface.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-10")


if __name__ == "__main__":
    unittest.main()
