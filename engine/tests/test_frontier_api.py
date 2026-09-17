"""Authentication, resource limits, and active-scenario forwarding for the frontier."""

from threading import BoundedSemaphore
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from ginseng import api, resources
from ginseng.inputs import fixture
from ginseng.state import Obligation


@pytest.fixture
def frontier_client(monkeypatch):
    monkeypatch.setitem(
        api.app.dependency_overrides,
        api.require_identity,
        lambda: api.AuthenticatedIdentity(user_id="frontier-test", access_token="test"),
    )
    with TestClient(api.app) as client:
        yield client


def test_frontier_requires_identity_before_running_the_engine(monkeypatch):
    engine = Mock(side_effect=AssertionError("Unauthenticated requests cannot run analyses."))
    monkeypatch.setattr(api, "portfolio_frontier", engine)
    monkeypatch.delitem(api.app.dependency_overrides, api.require_identity, raising=False)
    with TestClient(api.app) as client:
        response = client.post("/analysis/frontier", json={})
    assert response.status_code == 401
    engine.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        {"horizon_days": 61},
        {"horizon_days": 365},
        {"drought_view": {"probability": 0.5}},
        {"horizon_days": 0},
        {"operating_buffer": -1},
        {"unexpected_option": True},
        {
            "obligations": [
                {"id": "duplicate", "label": "First", "amount": 100, "due_in_days": 3},
                {"id": "duplicate", "label": "Second", "amount": 200, "due_in_days": 17},
            ]
        },
    ],
)
def test_frontier_rejects_unsupported_or_invalid_inputs_before_computation(
    monkeypatch, frontier_client, payload
):
    engine = Mock(side_effect=AssertionError("Invalid inputs must not reach the engine."))
    monkeypatch.setattr(api, "portfolio_frontier", engine)
    response = frontier_client.post("/analysis/frontier", json=payload)
    assert response.status_code == 422, response.text
    engine.assert_not_called()


def test_frontier_uses_shared_forecast_capacity(monkeypatch, frontier_client):
    engine = Mock(side_effect=AssertionError("Busy requests cannot start work."))
    monkeypatch.setattr(api, "portfolio_frontier", engine)
    gate = BoundedSemaphore(value=1)
    monkeypatch.setattr(resources, "SCENARIO_GATE", gate)
    assert gate.acquire(blocking=False)
    try:
        response = frontier_client.post("/analysis/frontier", json={})
    finally:
        gate.release()
    assert response.status_code == 503, response.text
    assert "busy" in response.json()["detail"].lower()
    engine.assert_not_called()


@pytest.mark.parametrize("horizon", [1, 60])
def test_frontier_forwards_active_scenario_and_preserves_cached_persona(
    monkeypatch, frontier_client, horizon
):
    original = fixture("tiny").state
    persona = Mock(return_value=original)
    monkeypatch.setattr(api, "_cached_persona", persona)
    result = {
        "status": "ready",
        "symbols": ["CASH"],
        "points": [],
        "pressure": {
            "discovery_count": 200,
            "evaluation_count": 220,
            "discovery_probability": 0.1,
            "evaluation_probability": 0.11,
        },
        "metadata": {"model": "synthetic-demo"},
    }
    engine = Mock(return_value=result)
    monkeypatch.setattr(api, "portfolio_frontier", engine)
    response = frontier_client.post(
        "/analysis/frontier",
        json={
            "seed": 314159,
            "horizon_days": horizon,
            "operating_buffer": 321.5,
            "coverage_target": 0.9,
            "mean_block_length": 7,
            "paths": 120,
            "obligations": [
                {"id": "deposit", "label": "Repair deposit", "amount": 1500, "due_in_days": 3},
                {"id": "balance", "label": "Repair balance", "amount": 3000, "due_in_days": 17},
            ],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json() == result
    persona.assert_called_once_with(314159)
    engine.assert_called_once()
    state, obligations = engine.call_args.args
    assert state is not original
    assert state.forecast_horizon == horizon
    assert state.operating_buffer == 321.5
    assert state.coverage_target == 0.9
    assert state.transactions is original.transactions
    assert state.holdings is original.holdings
    assert state.asset_daily_returns is original.asset_daily_returns
    assert obligations == (
        Obligation("deposit", "Repair deposit", 1500, 3),
        Obligation("balance", "Repair balance", 3000, 17),
    )
    # The research engine owns its fixed work budget; request.paths belongs
    # to the ordinary forecast and must not expand this experiment's work.
    assert engine.call_args.kwargs == {"seed": 314159, "block_length": 7}
    assert original == fixture("tiny").state


def test_frontier_preserves_unavailable_result_and_releases_capacity(
    monkeypatch, frontier_client
):
    result = {
        "status": "unavailable",
        "message": "Too few cash-pressure scenarios to estimate the conditional tail.",
        "pressure": {"discovery_count": 0, "evaluation_count": 0},
    }
    engine = Mock(return_value=result)
    monkeypatch.setattr(api, "portfolio_frontier", engine)
    gate = BoundedSemaphore(value=1)
    monkeypatch.setattr(resources, "SCENARIO_GATE", gate)
    response = frontier_client.post("/analysis/frontier", json={})
    assert response.status_code == 200, response.text
    assert response.json() == result
    assert engine.call_args.kwargs["block_length"] is None
    assert gate.acquire(blocking=False), "Returning unavailable must release shared capacity."
    gate.release()
