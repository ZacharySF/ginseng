import numpy as np
import pytest
from fastapi.testclient import TestClient
from ginseng.api import app
from ginseng.dependencies import require_identity
from ginseng.forecast_api import router
from ginseng.inputs import fixture
from ginseng.resources import SCENARIO_GATE
from ginseng.risk_explorer import NumericalOptions, explore, surface_from_paths
from ginseng.supabase import AuthenticatedIdentity

from tests.test_forecast_api import ForecastRepositoryStub, forecast_client, workspace
from tests.test_personal_forecast import historical_workspace


def test_surface_exact_cash_time_and_recovery():
    # Row one recovers after a failure: "by day" risk must not disappear.
    paths = np.array([[-10, 20, -5], [0, -20, 10]])
    probability, deficit = surface_from_paths(paths, 0, [0, 10, 20])
    np.testing.assert_allclose(probability, [[0.5, 1, 1], [0, 0.5, 0.5], [0, 0, 0]])
    np.testing.assert_allclose(deficit, [[5, 15, 15], [0, 5, 5], [0, 0, 0]])
    assert np.all(np.diff(probability, axis=1) >= 0)
    assert np.all(np.diff(probability, axis=0) <= 0)
    assert np.all(np.diff(deficit, axis=0) <= 0)


def test_bounded_exploration_replay():
    result = explore(
        fixture("tiny"), NumericalOptions(action="surface"), block_length=7
    )
    assert result == explore(
        fixture("tiny"), NumericalOptions(action="surface"), block_length=7
    )
    assert len(result["additional_cash"]) == 21
    assert len(result["shortfall_probability"]) == 21
    assert len(result["shortfall_probability"][0]) == 4
    precision = explore(
        fixture("tiny"),
        NumericalOptions(action="precision", max_paths=1024),
        block_length=7,
    )
    assert precision["summary"]["actual_n"] == 1024
    assert not precision["summary"]["precision_met"]
    assert "transactions" not in str(precision)


def test_personal_revision_mode_and_capacity():
    repo = ForecastRepositoryStub(workspace())
    with forecast_client(repo) as client:
        assert (
            client.post(
                "/finance/numerics",
                json={
                    "expected_revision": 3,
                    "horizon_days": 14,
                    "options": {"action": "surface"},
                },
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/finance/numerics",
                json={
                    "expected_revision": 4,
                    "horizon_days": 14,
                    "options": {"action": "surface"},
                },
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/finance/numerics",
                json={
                    "expected_revision": 4,
                    "horizon_days": 14,
                    "options": {"action": "precision", "max_paths": 1000000},
                },
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/finance/numerics",
                json={
                    "expected_revision": 4,
                    "horizon_days": 14,
                    "options": {"action": "precision", "max_paths": True},
                },
            ).status_code
            == 422
        )
        SCENARIO_GATE.acquire()
        SCENARIO_GATE.acquire()
        try:
            assert (
                client.post(
                    "/finance/numerics",
                    json={
                        "expected_revision": 4,
                        "horizon_days": 14,
                        "options": {"action": "surface"},
                    },
                ).status_code
                == 503
            )
        finally:
            SCENARIO_GATE.release()
            SCENARIO_GATE.release()
    assert repo.save_calls == 0


def test_personal_surface_and_preview():
    repo = ForecastRepositoryStub(historical_workspace())
    with forecast_client(repo) as client:
        payload = {
            "expected_revision": repo.workspace.revision,
            "horizon_days": 14,
            "options": {"action": "surface"},
        }
        response = client.post("/finance/numerics", json=payload)
        assert response.status_code == 200, response.text
        result = response.json()
        assert len(result["days"]) == 14
        assert result["opening_cash"] == 5000
        assert repo.save_calls == 0


def test_demo_auth_and_reject_stress():
    app.dependency_overrides[require_identity] = lambda: AuthenticatedIdentity(
        user_id="test", access_token="test"
    )
    try:
        with TestClient(app) as client:
            payload = {"options": {"action": "surface"}, "horizon_days": 30}
            response = client.post("/demo/numerics", json=payload)
            assert response.status_code == 200, response.text
            assert response.json()["kind"] == "surface"
            assert (
                client.post(
                    "/demo/numerics",
                    json={**payload, "drought_view": {"probability": 0.5}},
                ).status_code
                == 422
            )
            assert (
                client.post(
                    "/demo/numerics", json={**payload, "horizon_days": 365}
                ).status_code
                == 422
            )
    finally:
        app.dependency_overrides.pop(require_identity, None)


def test_saved_revision_changes_during_computation(monkeypatch):
    repo = ForecastRepositoryStub(historical_workspace())
    revision = repo.workspace.revision

    def finish(*args, **kwargs):
        repo.workspace = repo.workspace.model_copy(update={"revision": revision + 1})
        return {"kind": "surface"}

    monkeypatch.setattr("ginseng.forecast_api.explore", finish)
    with forecast_client(repo) as client:
        response = client.post(
            "/finance/numerics",
            json={
                "expected_revision": revision,
                "horizon_days": 14,
                "options": {"action": "surface"},
            },
        )
        assert response.status_code == 409


def test_numerical_endpoints_require_identity():
    with TestClient(app) as client:
        assert (
            client.post(
                "/demo/numerics", json={"options": {"action": "surface"}}
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/finance/numerics",
                json={
                    "expected_revision": 0,
                    "horizon_days": 14,
                    "options": {"action": "surface"},
                },
            ).status_code
            == 401
        )


def test_preview_bill_changes_surface_without_saving():
    from datetime import timedelta

    repo = ForecastRepositoryStub(historical_workspace())
    with forecast_client(repo) as client:
        payload = {
            "expected_revision": repo.workspace.revision,
            "horizon_days": 14,
            "options": {"action": "surface"},
        }
        base = client.post("/finance/numerics", json=payload).json()
        payload["overrides"] = {
            "bills": [
                {
                    "id": "00000000-0000-0000-0000-000000000203",
                    "label": "Repair",
                    "amount_cents": 10000000,
                    "due_date": str(repo.workspace.as_of + timedelta(days=1)),
                }
            ]
        }
        changed = client.post("/finance/numerics", json=payload)
        assert changed.status_code == 200, changed.text
        assert changed.json()["input_id"] != base["input_id"]
        assert (
            changed.json()["shortfall_probability"][0][-1]
            >= base["shortfall_probability"][0][-1]
        )
        assert (
            changed.json()["expected_max_deficit"][0][-1]
            > base["expected_max_deficit"][0][-1]
        )
        assert repo.save_calls == 0


def test_history_size_rejected_before_allocating_daily_arrays(monkeypatch):
    from dataclasses import replace
    from datetime import date

    case = fixture("tiny")
    case = replace(case, state=replace(case.state, history_start=date(1900, 1, 1)))

    def forbidden(*args, **kwargs):
        raise AssertionError("History must be rejected before preparation.")

    monkeypatch.setattr("ginseng.risk_explorer.prepare_history", forbidden)
    with pytest.raises(ValueError, match="ten years"):
        explore(case, NumericalOptions(action="surface"))
