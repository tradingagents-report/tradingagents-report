"""Packaging contract for optional market-data SDKs."""

from pathlib import Path

import tomllib


def test_market_data_sdks_are_optional_extras():
    project = tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]
    required = set(project["dependencies"])
    extras = project["optional-dependencies"]

    china = {"akshare>=1.17.86", "tushare>=1.4.21", "baostock>=0.8.8"}
    pandaai = {"panda_data>=0.0.1"}
    finnhub = {"finnhub-python>=2.4.23"}

    assert set(extras["china-data"]) == china
    assert set(extras["pandaai"]) == pandaai
    assert set(extras["finnhub"]) == finnhub
    assert set(extras["market-data"]) == china | pandaai | finnhub
    assert not (china | pandaai | finnhub) & required
