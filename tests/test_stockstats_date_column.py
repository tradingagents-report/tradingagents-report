"""Tests for tolerating a non-`Date` index column in stockstats_utils (#890).

Guards against a download frame whose date column is `index` or `Datetime`
instead of `Date`, which would otherwise silently drop every indicator.
"""

from __future__ import annotations

from unittest.mock import Mock

import pandas as pd
import pytest

from tradingagents.dataflows import stockstats_utils as su
from tradingagents.dataflows.yfinance import market as y_finance


def _ohlcv(date_col: str) -> pd.DataFrame:
    """OHLCV frame whose date column is named `date_col`."""
    dates = pd.bdate_range("2026-04-01", periods=10)
    return pd.DataFrame({
        date_col: dates,
        "Open": [100.0 + i for i in range(10)],
        "High": [101.0 + i for i in range(10)],
        "Low": [99.0 + i for i in range(10)],
        "Close": [100.5 + i for i in range(10)],
        "Volume": [1_000_000 + i for i in range(10)],
    })


@pytest.mark.unit
class TestEnsureDateColumn:
    def test_renames_index_column(self):
        out = su._ensure_date_column(_ohlcv("index"))
        assert "Date" in out.columns and "index" not in out.columns

    def test_renames_datetime_and_date_variants(self):
        assert "Date" in su._ensure_date_column(_ohlcv("Datetime")).columns
        assert "Date" in su._ensure_date_column(_ohlcv("date")).columns

    def test_leaves_existing_date_untouched(self):
        df = _ohlcv("Date")
        assert su._ensure_date_column(df) is df  # no-op short-circuit

    def test_no_datelike_column_is_left_alone(self):
        df = pd.DataFrame({"Close": [1, 2, 3]})
        out = su._ensure_date_column(df)
        assert "Date" not in out.columns  # nothing to rename; caller handles


@pytest.mark.unit
class TestCleanDataframeAcrossVersions:
    def test_clean_handles_index_column(self):
        """A frame with `index` instead of `Date` must still clean to a
        usable, date-parsed frame (was KeyError: 'Date')."""
        cleaned = su._clean_dataframe(_ohlcv("index"))
        assert "Date" in cleaned.columns
        assert pd.api.types.is_datetime64_any_dtype(cleaned["Date"])
        assert len(cleaned) == 10

    def test_clean_handles_legacy_date_column(self):
        cleaned = su._clean_dataframe(_ohlcv("Date"))
        assert len(cleaned) == 10

    def test_indicators_compute_after_index_rename(self):
        """stockstats must compute indicators on a frame whose date column
        arrived as `index`, instead of erroring per indicator."""
        from stockstats import wrap
        cleaned = su._clean_dataframe(_ohlcv("index"))
        df = wrap(cleaned)
        df["close_5_sma"]  # triggers calculation
        assert "close_5_sma" in df.columns
        assert df["close_5_sma"].notna().any()

    def test_indicator_window_accepts_legacy_date_column_and_preserves_text(self):
        result = su.calculate_indicator_window(
            _ohlcv("index"), "AAPL", "close_10_ema", "2026-04-14", 1
        )

        assert result.startswith(
            "## close_10_ema values from 2026-04-13 to 2026-04-14:\n\n"
        )
        assert "2026-04-14:" in result
        assert result.endswith(
            "10 EMA: A responsive short-term average. Usage: Capture quick shifts in momentum "
            "and potential entry points. Tips: Prone to noise in choppy markets; use alongside "
            "longer averages for filtering false signals."
        )


@pytest.mark.unit
class TestYahooIndicatorWindowCompatibility:
    def test_unsupported_indicator_is_rejected_before_loading_ohlcv(self, monkeypatch):
        load = Mock()
        monkeypatch.setattr(y_finance, "load_ohlcv", load)

        with pytest.raises(
            ValueError,
            match=r"Indicator unsupported is not supported\. Please choose from:",
        ):
            y_finance.get_stock_stats_indicators_window(
                "AAPL", "unsupported", "2026-04-14", 1
            )

        load.assert_not_called()

    def test_calculation_error_uses_established_per_day_fallback(
        self, monkeypatch, capsys
    ):
        monkeypatch.setattr(y_finance, "load_ohlcv", Mock(return_value=_ohlcv("Date")))
        monkeypatch.setattr(
            y_finance,
            "calculate_indicator_window",
            Mock(side_effect=RuntimeError("bad frame")),
        )
        fallback = Mock(side_effect=lambda symbol, indicator, date: f"fallback-{date}")
        monkeypatch.setattr(y_finance, "get_stockstats_indicator", fallback)

        result = y_finance.get_stock_stats_indicators_window(
            "AAPL", "close_10_ema", "2026-04-14", 1
        )

        assert result.startswith(
            "## close_10_ema values from 2026-04-13 to 2026-04-14:\n\n"
            "2026-04-14: fallback-2026-04-14\n"
            "2026-04-13: fallback-2026-04-13\n"
        )
        assert result.endswith(su.BEST_INDICATOR_PARAMS["close_10_ema"])
        assert fallback.call_count == 2
        assert "Error getting bulk stockstats data: bad frame" in capsys.readouterr().out
