"""Look-ahead-safe Tushare company and market news."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from ..errors import VendorNotConfiguredError, VendorUnavailableError
from ..news_utils import in_news_window
from .fundamentals import _pro


def _news(start_date: str, end_date: str, symbol: str | None, sdk: Any | None) -> str:
    try:
        frame = pd.DataFrame(
            _pro(sdk).news(start_date=f"{start_date} 00:00:00", end_date=f"{end_date} 23:59:59")
        )
    except Exception as exc:
        if isinstance(exc, VendorNotConfiguredError):
            raise
        raise VendorUnavailableError("Tushare news request failed") from exc
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    articles = []
    for row in frame.to_dict(orient="records"):
        published = pd.to_datetime(row.get("datetime"), errors="coerce")
        pub_date = None if pd.isna(published) else published.to_pydatetime()
        if in_news_window(pub_date, start, end):
            articles.append(row)
    label = symbol or "global"
    if not articles:
        return f"No news found for {label} between {start_date} and {end_date}"
    return f"# Tushare news for {label}\n\n" + pd.DataFrame(articles).to_json(
        orient="records", force_ascii=False, date_format="iso"
    )


def get_tushare_news(symbol: str, start_date: str, end_date: str, *, sdk: Any | None = None) -> str:
    return _news(start_date, end_date, symbol, sdk)


def get_tushare_global_news(
    curr_date: str, look_back_days: int = 7, limit: int = 50, *, sdk: Any | None = None
) -> str:
    end = datetime.strptime(curr_date, "%Y-%m-%d")
    start = end - timedelta(days=look_back_days)
    return _news(start.strftime("%Y-%m-%d"), curr_date, None, sdk)
