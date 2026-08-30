from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest


class FakeAkCapabilities:
    def stock_individual_info_em(self, symbol):
        return pd.DataFrame(
            {"item": ["股票简称", "行业", "上市时间"], "value": ["贵州茅台", "白酒", "20010827"]}
        )

    def stock_financial_abstract_ths(self, symbol):
        return pd.DataFrame({"报告期": ["2025-12-31", "2026-12-31"], "净利润": [10, 999]})

    def stock_balance_sheet_by_report_em(self, symbol):
        return pd.DataFrame({"REPORT_DATE": ["2025-12-31", "2026-12-31"], "资产": [1, 999]})

    def stock_profit_sheet_by_report_em(self, symbol):
        return pd.DataFrame({"REPORT_DATE": ["2025-12-31", "2026-12-31"], "利润": [2, 999]})

    def stock_cash_flow_sheet_by_report_em(self, symbol):
        return pd.DataFrame({"REPORT_DATE": ["2025-12-31", "2026-12-31"], "现金": [3, 999]})

    def stock_news_em(self, symbol):
        return pd.DataFrame(
            {
                "发布时间": ["2026-01-02 10:00:00", "2026-02-01 10:00:00"],
                "新闻标题": ["inside", "future"],
                "新闻内容": ["ok", "no"],
                "新闻链接": ["https://inside", "https://future"],
            }
        )


def test_akshare_identity_and_fundamentals_are_cutoff_safe():
    from tradingagents.dataflows.akshare.fundamentals import (
        get_akshare_fundamentals,
        get_akshare_identity,
    )

    sdk = FakeAkCapabilities()
    identity = get_akshare_identity("600519.SS", sdk=sdk)
    assert identity["company_name"] == "贵州茅台"
    assert identity["exchange"] == "SSE"
    text = get_akshare_fundamentals("600519.SS", "2026-01-15", sdk=sdk)
    assert "10" in text
    assert "999" not in text


@pytest.mark.parametrize(
    "function_name,expected",
    [("get_balance_sheet", "资产"), ("get_income_statement", "利润"), ("get_cashflow", "现金")],
)
def test_akshare_statements_exclude_future_reports(function_name, expected):
    from tradingagents.dataflows.akshare import fundamentals

    text = getattr(fundamentals, function_name)(
        "600519.SS", curr_date="2026-01-15", sdk=FakeAkCapabilities()
    )
    assert expected in text
    assert "999" not in text


def test_akshare_news_excludes_future_articles():
    from tradingagents.dataflows.akshare.news import get_akshare_news

    text = get_akshare_news("600519.SS", "2026-01-01", "2026-01-15", sdk=FakeAkCapabilities())
    assert "inside" in text
    assert "future" not in text


class FakeTusharePro:
    def stock_basic(self, **kwargs):
        return pd.DataFrame({"name": ["平安银行"], "industry": ["银行"], "list_date": ["19910403"]})

    def daily_basic(self, **kwargs):
        return pd.DataFrame({"trade_date": ["20260102"], "pe_ttm": [6.5], "pb": [0.7]})

    def balancesheet(self, **kwargs):
        return pd.DataFrame({"end_date": ["20251231", "20261231"], "total_assets": [1, 999]})

    def income(self, **kwargs):
        return pd.DataFrame({"end_date": ["20251231", "20261231"], "revenue": [2, 999]})

    def cashflow(self, **kwargs):
        return pd.DataFrame({"end_date": ["20251231", "20261231"], "n_cashflow_act": [3, 999]})

    def news(self, **kwargs):
        return pd.DataFrame(
            {
                "datetime": ["2026-01-02 10:00:00", "2026-02-01 10:00:00"],
                "title": ["inside", "future"],
                "content": ["ok", "no"],
            }
        )


class FakeTushare:
    def pro_api(self, token):
        assert token == "token"
        return FakeTusharePro()


def test_tushare_capabilities_use_token_and_cutoff(monkeypatch):
    from tradingagents.dataflows.tushare.fundamentals import (
        get_balance_sheet,
        get_cashflow,
        get_income_statement,
        get_tushare_fundamentals,
        get_tushare_identity,
    )
    from tradingagents.dataflows.tushare.news import get_tushare_news

    monkeypatch.setenv("TUSHARE_TOKEN", "token")
    sdk = FakeTushare()
    assert get_tushare_identity("000001.SZ", sdk=sdk)["company_name"] == "平安银行"
    assert "6.5" in get_tushare_fundamentals("000001.SZ", "2026-01-15", sdk=sdk)
    statement = get_balance_sheet("000001.SZ", curr_date="2026-01-15", sdk=sdk)
    assert "999" not in statement
    assert "999" not in get_income_statement("000001.SZ", curr_date="2026-01-15", sdk=sdk)
    assert "999" not in get_cashflow("000001.SZ", curr_date="2026-01-15", sdk=sdk)
    news = get_tushare_news("000001.SZ", "2026-01-01", "2026-01-15", sdk=sdk)
    assert "inside" in news and "future" not in news


def test_baostock_identity_and_fundamentals():
    from tradingagents.dataflows.baostock.fundamentals import (
        get_baostock_fundamentals,
        get_baostock_identity,
    )

    class Cursor:
        error_code = "0"
        fields = ["code", "code_name", "ipoDate", "type", "status"]

        def __init__(self, row):
            self.row = row
            self.done = False

        def next(self):
            if self.done:
                return False
            self.done = True
            return True

        def get_row_data(self):
            return self.row

    class FakeBao:
        def login(self):
            return SimpleNamespace(error_code="0", error_msg="")

        def logout(self):
            pass

        def query_stock_basic(self, **kwargs):
            return Cursor(["sh.600519", "贵州茅台", "2001-08-27", "1", "1"])

        def query_profit_data(self, **kwargs):
            cursor = Cursor(["sh.600519", "2025-12-31", "0.2"])
            cursor.fields = ["code", "pubDate", "roeAvg"]
            return cursor

    sdk = FakeBao()
    assert get_baostock_identity("600519.SS", sdk=sdk)["company_name"] == "贵州茅台"
    assert "0.2" in get_baostock_fundamentals("600519.SS", "2026-01-15", sdk=sdk)
