from __future__ import annotations

import importlib

import pytest

import tradingagents.default_config as default_config


def _reload(monkeypatch, **env):
    for key in ("TRADINGAGENTS_CN_DATA_VENDORS", "TRADINGAGENTS_US_DATA_VENDORS"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return importlib.reload(default_config)


def test_market_vendor_env_defaults_to_disabled(monkeypatch):
    module = _reload(monkeypatch)
    assert module.DEFAULT_CONFIG["cn_data_vendors"] is None
    assert module.DEFAULT_CONFIG["us_data_vendors"] is None


def test_market_vendor_env_preserves_order(monkeypatch):
    module = _reload(
        monkeypatch,
        TRADINGAGENTS_CN_DATA_VENDORS="pandaai,akshare,tushare,baostock",
        TRADINGAGENTS_US_DATA_VENDORS="yfinance,alpha_vantage,finnhub",
    )
    assert module.DEFAULT_CONFIG["cn_data_vendors"] == ("pandaai", "akshare", "tushare", "baostock")
    assert module.DEFAULT_CONFIG["us_data_vendors"] == ("yfinance", "alpha_vantage", "finnhub")


def test_invalid_market_vendor_env_fails_at_reload(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CN_DATA_VENDORS", "akshare,finnhub")
    with pytest.raises(ValueError, match="TRADINGAGENTS_CN_DATA_VENDORS"):
        importlib.reload(default_config)
    monkeypatch.delenv("TRADINGAGENTS_CN_DATA_VENDORS", raising=False)
    importlib.reload(default_config)
