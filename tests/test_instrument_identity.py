"""Tests for deterministic instrument-identity resolution (#814) and the
context-anchored message placeholder (#888)."""

import ast
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage

import tradingagents.agents.utils.agent_utils as agent_utils
import tradingagents.dataflows.structured_data as structured_data
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    create_msg_delete,
    get_instrument_context_from_state,
    merge_display_name_into_identity,
    resolve_instrument_identity,
)
from tradingagents.dataflows.provider_models import ProviderResult, parse_instrument


@pytest.mark.unit
class ResolveInstrumentIdentityTests(unittest.TestCase):
    def setUp(self):
        resolve_instrument_identity.cache_clear()

    def test_resolves_company_metadata_from_provider_router(self):
        fetch = Mock(
            return_value={
                "company_name": "TOTO LTD.",
                "sector": "Industrials",
                "industry": "Building Products & Equipment",
                "exchange": "PNK",
                "quote_type": "EQUITY",
                "quote_currency": "JPY",
                "fundamental_currency": "JPY",
            }
        )
        with patch.object(agent_utils, "get_instrument_identity", fetch):
            identity = resolve_instrument_identity("totdy")
        fetch.assert_called_once_with("totdy")
        self.assertEqual(identity["company_name"], "TOTO LTD.")
        self.assertEqual(identity["sector"], "Industrials")
        self.assertEqual(identity["industry"], "Building Products & Equipment")
        self.assertEqual(identity["exchange"], "PNK")
        self.assertEqual(identity["quote_currency"], "JPY")
        self.assertEqual(identity["fundamental_currency"], "JPY")

    def test_uses_provider_company_name(self):
        with patch.object(
            agent_utils,
            "get_instrument_identity",
            return_value={"company_name": "TOTO", "sector": "Industrials"},
        ):
            identity = resolve_instrument_identity("TOTDY")
        self.assertEqual(identity["company_name"], "TOTO")

    def test_skips_placeholder_values(self):
        with patch.object(
            agent_utils,
            "get_instrument_identity",
            return_value={"company_name": "  ", "sector": "None", "industry": "n/a"},
        ):
            identity = resolve_instrument_identity("TOTDY")
        self.assertEqual(identity, {})

    def test_fails_open_on_exception(self):
        with patch.object(
            agent_utils,
            "get_instrument_identity",
            side_effect=RuntimeError("rate limited"),
        ):
            self.assertEqual(resolve_instrument_identity("TOTDY"), {})

    def test_result_is_cached(self):
        fetch = Mock(return_value={"company_name": "TOTO LTD."})
        with patch.object(agent_utils, "get_instrument_identity", fetch):
            first = resolve_instrument_identity("TOTDY")
            second = resolve_instrument_identity("TOTDY")
        fetch.assert_called_once()  # second call served from cache
        self.assertEqual(first, second)


@pytest.mark.unit
class StructuredIdentityFacadeTests:
    def test_unwraps_provider_result_and_sanitizes_values(self, monkeypatch):
        routed = ProviderResult(
            data={
                "company_name": " Apple Inc. ",
                "exchange": " NASDAQ ",
                "sector": "",
                "employees": 100,
            },
            provider="tradingview",
            requested=parse_instrument("AAPL"),
            resolved_symbol="NASDAQ:AAPL",
        )
        monkeypatch.setattr(structured_data, "route_structured", lambda *args: routed)

        assert structured_data.get_instrument_identity("AAPL") == {
            "company_name": "Apple Inc.",
            "exchange": "NASDAQ",
        }

    def test_accepts_raw_identity_dict(self, monkeypatch):
        route = Mock(return_value={"company_name": "Apple Inc.", "exchange": "NASDAQ"})
        monkeypatch.setattr(structured_data, "route_structured", route)

        identity = structured_data.get_instrument_identity("AAPL")

        route.assert_called_once_with("get_instrument_identity", "AAPL")
        assert identity == {"company_name": "Apple Inc.", "exchange": "NASDAQ"}

    def test_rejects_unexpected_identity_type(self, monkeypatch):
        monkeypatch.setattr(structured_data, "route_structured", lambda *args: ["Apple"])

        with pytest.raises(TypeError):
            structured_data.get_instrument_identity("AAPL")


def _assert_provider_neutral_business_source(source: str, filename: str = "<source>"):
    tree = ast.parse(source, filename=filename)
    imported_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
            imported_names.update(modules)
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or ""]
            imported_names.update(alias.name for alias in node.names)
        else:
            continue
        assert not any(
            module == "yfinance" or module.startswith("yfinance.")
            for module in modules
        )

    references = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
    } | {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    }
    assert "normalize_symbol" not in imported_names | references
    assert "load_ohlcv" not in imported_names | references
    assert "yf.Ticker" not in source


@pytest.mark.unit
@pytest.mark.parametrize(
    "source",
    (
        "import yfinance as vendor",
        "from yfinance import Ticker",
        "from tradingagents.dataflows.yfinance.symbols import normalize_symbol as normalize",
        "from tradingagents.dataflows.stockstats_utils import load_ohlcv as load",
        "symbols.normalize_symbol('AAPL')",
        "stats.load_ohlcv('AAPL')",
        "yf.Ticker('AAPL')",
    ),
)
def test_business_dependency_guard_rejects_forbidden_forms(source):
    with pytest.raises(AssertionError):
        _assert_provider_neutral_business_source(source)


@pytest.mark.unit
def test_validator_and_identity_have_no_direct_yahoo_calls():
    source_root = Path(agent_utils.__file__).parents[2]
    business_files = (
        Path(agent_utils.__file__),
        source_root / "dataflows" / "market_data_validator.py",
    )

    for path in business_files:
        _assert_provider_neutral_business_source(
            path.read_text(encoding="utf-8"),
            filename=str(path),
        )


@pytest.mark.unit
def test_graph_identity_docstring_is_provider_neutral():
    source_root = Path(agent_utils.__file__).parents[2]
    graph_source = (source_root / "graph" / "trading_graph.py").read_text(encoding="utf-8")

    assert "Deterministic provider-routed lookup" in graph_source
    assert "Deterministic yfinance lookup" not in graph_source


@pytest.mark.unit
class BuildInstrumentContextTests(unittest.TestCase):
    def test_mentions_exact_symbol_without_identity(self):
        context = build_instrument_context("7203.T")
        self.assertIn("7203.T", context)
        self.assertIn("exchange suffix", context)
        self.assertNotIn("Resolved identity", context)

    def test_injects_resolved_identity(self):
        context = build_instrument_context(
            "TOTDY", "stock",
            {
                "company_name": "TOTO LTD.",
                "sector": "Industrials",
                "industry": "Building Products & Equipment",
                "exchange": "PNK",
                "quote_currency": "HKD",
                "fundamental_currency": "CNY",
            },
        )
        self.assertIn("Company: TOTO LTD.", context)
        self.assertIn("Industrials / Building Products & Equipment", context)
        self.assertIn("Exchange: PNK", context)
        self.assertIn("Quote currency: HKD", context)
        self.assertIn("Fundamental reporting currency: CNY", context)
        self.assertIn("Do not substitute a different company", context)
        self.assertIn("never invent a phonetic Chinese name", context)

    def test_includes_english_name_when_distinct(self):
        context = build_instrument_context(
            "300814.SZ",
            "stock",
            {
                "company_name": "中富电路",
                "english_name": "Shenzhen JOVE Enterprise Ltd. Class A",
            },
        )
        self.assertIn("Company: 中富电路", context)
        self.assertIn("English name: Shenzhen JOVE Enterprise Ltd. Class A", context)

    def test_crypto_uses_name_label_and_keeps_hint(self):
        context = build_instrument_context(
            "BTC-USD", "crypto", {"company_name": "Bitcoin USD"}
        )
        self.assertIn("Name: Bitcoin USD", context)
        self.assertIn("crypto asset rather than a company", context)


@pytest.mark.unit
class MergeDisplayNameIntoIdentityTests(unittest.TestCase):
    def test_prefers_display_name_and_keeps_english_alternate(self):
        merged = merge_display_name_into_identity(
            {"company_name": "Shenzhen JOVE Enterprise Ltd. Class A", "sector": "Tech"},
            "中富电路",
        )
        self.assertEqual(merged["company_name"], "中富电路")
        self.assertEqual(
            merged["english_name"], "Shenzhen JOVE Enterprise Ltd. Class A"
        )
        self.assertEqual(merged["sector"], "Tech")

    def test_prefers_submitted_english_name(self):
        merged = merge_display_name_into_identity(
            {"company_name": "宁德时代"},
            "宁德时代",
            english_name="Contemporary Amperex Technology Co., Limited Class A",
        )
        self.assertEqual(merged["company_name"], "宁德时代")
        self.assertEqual(
            merged["english_name"],
            "Contemporary Amperex Technology Co., Limited Class A",
        )

    def test_fills_empty_identity_from_display_name(self):
        merged = merge_display_name_into_identity({}, "中富电路")
        self.assertEqual(merged, {"company_name": "中富电路"})

    def test_ignores_blank_display_name(self):
        merged = merge_display_name_into_identity(
            {"company_name": "中富电路"}, "  "
        )
        self.assertEqual(merged, {"company_name": "中富电路"})


@pytest.mark.unit
class GetInstrumentContextFromStateTests(unittest.TestCase):
    def test_prefers_precomputed_context(self):
        state = {"company_of_interest": "TOTDY", "instrument_context": "PRECOMPUTED"}
        self.assertEqual(get_instrument_context_from_state(state), "PRECOMPUTED")

    def test_fallback_is_network_free_ticker_only(self):
        # No instrument_context and no provider call — must not hit the network.
        with patch.object(agent_utils, "get_instrument_identity") as mock:
            context = get_instrument_context_from_state(
                {"company_of_interest": "NVDA", "asset_type": "stock"}
            )
        mock.assert_not_called()
        self.assertIn("NVDA", context)

    def test_fallback_respects_asset_type(self):
        context = get_instrument_context_from_state(
            {"company_of_interest": "BTC-USD", "asset_type": "crypto"}
        )
        self.assertIn("crypto asset", context)


@pytest.mark.unit
class ContextAnchoredPlaceholderTests(unittest.TestCase):
    """#888 — the message-clear placeholder must not be a bare 'Continue'."""

    def _run(self, state_extra):
        state = {
            "messages": [
                HumanMessage(content="old", id="h1"),
                AIMessage(content="reply", id="a1"),
            ],
            **state_extra,
        }
        return create_msg_delete()(state)

    def test_placeholder_is_not_bare_continue(self):
        result = self._run(
            {"company_of_interest": "EC", "asset_type": "stock", "trade_date": "2026-05-28"}
        )
        placeholder = result["messages"][-1]
        self.assertIsInstance(placeholder, HumanMessage)
        self.assertNotEqual(placeholder.content.strip(), "Continue")

    def test_placeholder_carries_resolved_identity(self):
        result = self._run(
            {
                "company_of_interest": "EC",
                "instrument_context": "The instrument to analyze is `EC`. Resolved identity: Company: Ecopetrol.",
                "trade_date": "2026-05-28",
            }
        )
        content = result["messages"][-1].content
        self.assertIn("Ecopetrol", content)
        self.assertIn("2026-05-28", content)

    def test_old_messages_are_removed(self):
        result = self._run({"company_of_interest": "EC", "trade_date": "2026-05-28"})
        removals = [m for m in result["messages"] if isinstance(m, RemoveMessage)]
        humans = [m for m in result["messages"] if isinstance(m, HumanMessage)]
        self.assertEqual(len(removals), 2)
        self.assertEqual(len(humans), 1)

    def test_safe_defaults_when_state_minimal(self):
        result = create_msg_delete()({"messages": [], "company_of_interest": "EC"})
        placeholder = result["messages"][-1]
        self.assertNotEqual(placeholder.content.strip(), "Continue")
        self.assertIn("EC", placeholder.content)


if __name__ == "__main__":
    unittest.main()
