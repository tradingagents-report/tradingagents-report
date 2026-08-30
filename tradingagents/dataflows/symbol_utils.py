"""跨供应商复用的标的符号辅助函数。"""

from __future__ import annotations

_CRYPTO_BASES = frozenset(
    {"BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LTC", "BCH", "DOT", "AVAX", "LINK"}
)
_CRYPTO_QUOTES = ("USDT", "USDC", "USD")


def crypto_base(raw: str) -> str | None:
    """返回已知 USD、USDT 或 USDC 计价加密资产的基础币种。

    该函数不转换供应商符号，只识别 ``BTC-USD``、``BTCUSD``、
    ``BTC-USDT`` 等形式，供社交数据源和 Yahoo 规范化逻辑共用。
    """
    if not isinstance(raw, str):
        return None
    compact = raw.strip().upper().rstrip("+").replace("-", "")
    for quote in _CRYPTO_QUOTES:
        if compact.endswith(quote):
            base = compact[: -len(quote)]
            return base if base in _CRYPTO_BASES else None
    return None
