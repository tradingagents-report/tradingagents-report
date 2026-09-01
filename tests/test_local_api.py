"""Thin self-hosted HTTP API over application.local_desk."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from application.analysis import AnalysisEvent, AnalysisResult
from local_api.app import app, desk_config
from tests.test_local_desk import _config, _join_local_threads, _state


def _client(tmp_path) -> TestClient:
    app.dependency_overrides[desk_config] = lambda: _config(tmp_path)
    return TestClient(app)


def test_health():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "store": "local"}


def test_resolve_listing():
    response = TestClient(app).get("/api/v1/listings/resolve", params={"ticker": "0700.HK"})
    assert response.status_code == 200
    body = response.json()
    assert body["exchange"] == "HKEX"
    assert body["symbol"] == "700"
    assert body["provider_symbol"] == "HKEX:700"


def test_start_analysis_and_report(tmp_path):
    client = _client(tmp_path)
    state = _state()

    def fake_run_analysis(command, *, callbacks=(), on_event=None):
        del callbacks
        if on_event is not None:
            on_event(AnalysisEvent(10, "Running Market Analyst"))
        return AnalysisResult(final_state=state, decision="Overweight", run_id=None)

    with patch("application.local_desk.run_analysis", fake_run_analysis):
        created = client.post(
            "/api/v1/analyses",
            json={"ticker": "AAPL", "trade_date": "2026-08-01", "analysts": ["market"]},
        )
        assert created.status_code == 202
        analysis_id = created.json()["id"]
        _join_local_threads()

    status = client.get(f"/api/v1/analyses/{analysis_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "succeeded"

    events = client.get(f"/api/v1/analyses/{analysis_id}/events")
    assert events.status_code == 200
    assert events.json()["events"][0]["message"] == "Running Market Analyst"

    report = client.get(f"/api/v1/analyses/{analysis_id}/report")
    assert report.status_code == 200
    assert report.json()["decision_brief"]["rating"] == "Overweight"

    listed = client.get("/api/v1/analyses", params={"ticker": "AAPL"})
    assert listed.status_code == 200
    assert listed.json()["analyses"][0]["id"] == analysis_id

    app.dependency_overrides.clear()


def test_report_not_found(tmp_path):
    client = _client(tmp_path)
    response = client.get("/api/v1/analyses/missing/report")
    assert response.status_code == 404
    app.dependency_overrides.clear()


def test_ohlcv_rejects_intraday():
    response = TestClient(app).get(
        "/api/v1/ohlcv", params={"symbol": "AAPL", "timeframe": "15"}
    )
    assert response.status_code == 400
    assert "daily" in response.json()["detail"]
