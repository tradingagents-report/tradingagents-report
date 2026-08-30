"""Lazy Finnhub SDK construction and error translation."""

from __future__ import annotations

import importlib
import os

from ..errors import (
    VendorAuthenticationError,
    VendorNotConfiguredError,
    VendorRateLimitError,
    VendorUnavailableError,
)


def get_client():
    api_key = os.getenv("FINNHUB_API_KEY", "").strip()
    if not api_key:
        raise VendorNotConfiguredError("FINNHUB_API_KEY is not configured")
    try:
        sdk = importlib.import_module("finnhub")
    except ImportError as exc:
        raise VendorNotConfiguredError(
            "Finnhub requires the optional finnhub-python package"
        ) from exc
    return sdk.Client(api_key=api_key)


def translate_error(exc: Exception, action: str) -> Exception:
    message = str(exc).lower()
    if "401" in message or "403" in message or "unauthorized" in message:
        return VendorAuthenticationError(f"Finnhub authentication failed during {action}")
    if "429" in message or "rate limit" in message:
        return VendorRateLimitError(f"Finnhub rate limited during {action}")
    return VendorUnavailableError(f"Finnhub {action} failed")
