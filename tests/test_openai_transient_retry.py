"""Outer retry for transient OpenAI-compatible gateway errors (5xx / do_request_failed)."""

from unittest.mock import Mock

import pytest
from openai import InternalServerError

from tradingagents.llm_clients import openai_client as oc


def _internal_server_error() -> InternalServerError:
    response = Mock()
    response.status_code = 500
    response.headers = {}
    response.json.return_value = {
        "error": {
            "message": "upstream error: do request failed",
            "type": "new_api_error",
            "code": "do_request_failed",
        }
    }
    response.text = "upstream error"
    return InternalServerError(
        "Error code: 500 - upstream error: do request failed",
        response=response,
        body={
            "error": {
                "message": "upstream error: do request failed",
                "type": "new_api_error",
                "code": "do_request_failed",
            }
        },
    )


def test_is_transient_llm_error_detects_gateway_500():
    assert oc._is_transient_llm_error(_internal_server_error())
    assert oc._is_transient_llm_error(RuntimeError("Error code: 503 - unavailable"))
    assert not oc._is_transient_llm_error(ValueError("bad request"))


def test_call_with_transient_retry_waits_then_continues(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(oc.time, "sleep", lambda seconds: sleeps.append(seconds))
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise _internal_server_error()
        return "ok"

    assert oc._call_with_transient_retry(flaky) == "ok"
    assert calls["n"] == 2
    assert sleeps == [oc._TRANSIENT_LLM_BACKOFF_SECONDS]


def test_call_with_transient_retry_gives_up_after_budget(monkeypatch):
    monkeypatch.setattr(oc.time, "sleep", lambda _seconds: None)
    calls = {"n": 0}

    def always_fail():
        calls["n"] += 1
        raise _internal_server_error()

    with pytest.raises(InternalServerError):
        oc._call_with_transient_retry(always_fail)

    assert calls["n"] == oc._TRANSIENT_LLM_OUTER_RETRIES + 1


def test_call_with_transient_retry_does_not_retry_non_transient(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(oc.time, "sleep", lambda seconds: sleeps.append(seconds))
    calls = {"n": 0}

    def bad_request():
        calls["n"] += 1
        raise ValueError("invalid schema")

    with pytest.raises(ValueError, match="invalid schema"):
        oc._call_with_transient_retry(bad_request)

    assert calls["n"] == 1
    assert sleeps == []
