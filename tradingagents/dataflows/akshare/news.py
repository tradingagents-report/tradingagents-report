"""Look-ahead-safe AKShare company news."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from ..china.common import resolve_cn_symbol
from ..errors import VendorUnavailableError
from ..news_utils import in_news_window
from .market import _sdk


def get_akshare_news(symbol: str, start_date: str, end_date: str, *, sdk: Any | None = None) -> str:
    _, _, code = resolve_cn_symbol(symbol)
    try:
        frame = pd.DataFrame(_sdk(sdk).stock_news_em(symbol=code))
    except Exception as exc:
        raise VendorUnavailableError("AKShare news request failed") from exc
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    articles = []
    for row in frame.to_dict(orient="records"):
        published = pd.to_datetime(row.get("发布时间"), errors="coerce")
        pub_date = None if pd.isna(published) else published.to_pydatetime()
        if in_news_window(pub_date, start, end):
            articles.append(row)
    if not articles:
        return f"No news found for {symbol} between {start_date} and {end_date}"
    return f"# AKShare news for {symbol}\n\n" + pd.DataFrame(articles).to_json(
        orient="records", force_ascii=False, date_format="iso"
    )
