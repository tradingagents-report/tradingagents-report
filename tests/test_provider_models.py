"""Provider-neutral market-data contract tests."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from tradingagents.dataflows.provider_models import (
    InstrumentRef,
    ProviderResult,
    ProviderSymbol,
    parse_instrument,
)


def test_parse_instrument_is_provider_neutral():
    ref = parse_instrument(" xauusd+ ")

    assert ref.raw_symbol == "xauusd+"
    assert ref.canonical_symbol == "XAUUSD"
    assert ref.asset_class == "futures"
    assert "=" not in ref.canonical_symbol


def test_parse_instrument_retains_exchange_hint():
    ref = parse_instrument("nasdaq:aapl")

    assert ref.canonical_symbol == "AAPL"
    assert ref.exchange_hint == "NASDAQ"
    assert ref.asset_class == "equity"


def test_provider_result_keeps_provenance_without_changing_data():
    ref = parse_instrument("AAPL")
    result = ProviderResult(
        data={"company_name": "Apple Inc."},
        provider="tradingview",
        requested=ref,
        resolved_symbol="NASDAQ:AAPL",
        as_of=datetime(2026, 7, 11, tzinfo=timezone.utc),
        provenance={"endpoint": "/api/market-data/{symbol}/company"},
    )

    assert result.data["company_name"] == "Apple Inc."
    assert result.provider == "tradingview"


@pytest.mark.parametrize(
    "contract",
    [
        InstrumentRef("AAPL", "AAPL", "equity"),
        ProviderSymbol("tradingview", "NASDAQ:AAPL"),
    ],
)
def test_provider_contracts_are_immutable(contract):
    with pytest.raises(FrozenInstanceError):
        contract.provider = "yahoo"
