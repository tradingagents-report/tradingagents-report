"""Closed chart-slot markers for market and fundamentals markdown."""

from tradingagents.agents.utils.agent_utils import get_chart_slot_instruction


def test_market_chart_slot_instruction_lists_closed_ids():
    text = get_chart_slot_instruction("market")
    assert "<!-- chart:price_structure -->" in text
    assert "<!-- chart:rsi -->" in text
    assert "<!-- chart:macd -->" in text
    assert "do not omit a slot" in text.lower()
    assert "<!-- chart:income -->" not in text


def test_fundamentals_chart_slot_instruction_lists_closed_ids():
    text = get_chart_slot_instruction("fundamentals")
    assert "<!-- chart:income -->" in text
    assert "<!-- chart:cashflow -->" in text
    assert "<!-- chart:quality -->" in text
    assert "do not omit a slot" in text.lower()
    assert "<!-- chart:rsi -->" not in text


def test_other_sections_have_no_chart_slot_instruction():
    assert get_chart_slot_instruction("news") == ""
    assert get_chart_slot_instruction("sentiment") == ""
