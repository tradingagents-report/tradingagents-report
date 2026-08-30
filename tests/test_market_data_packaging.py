"""Packaging contract for optional market-data SDKs."""

from pathlib import Path

import tomllib


def test_market_data_sdks_are_optional_extras():
    project = tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]
    required = set(project["dependencies"])
    extras = project["optional-dependencies"]
    finnhub = {"finnhub-python>=2.4.23"}

    assert "china-data" not in extras
    assert "pandaai" not in extras
    assert set(extras["finnhub"]) == finnhub
    assert set(extras["market-data"]) == finnhub
    assert not finnhub & required
