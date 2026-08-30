"""Provider-neutral helpers for look-ahead-safe news filtering."""

from datetime import datetime

from dateutil.relativedelta import relativedelta


def in_news_window(pub_date, start_dt, end_dt) -> bool:
    """Return whether an article belongs in the inclusive news date window."""
    if pub_date is not None:
        naive = pub_date.replace(tzinfo=None) if hasattr(pub_date, "replace") else pub_date
        return start_dt <= naive <= end_dt + relativedelta(days=1)
    return end_dt >= datetime.now() - relativedelta(days=1)
