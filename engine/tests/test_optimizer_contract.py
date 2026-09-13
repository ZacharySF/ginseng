"""Scenario calculations preserve useful results when optimization is unavailable."""

import pytest

from ginseng import api, scenario_service
from ginseng.optimizer import OptimizationFailure


@pytest.mark.parametrize(
    "reason",
    ["invalid_input", "no_funding_levers", "resource_limit", "cvxpy_unavailable",
     "solver_unavailable", "solver_timeout", "solver_limit", "solver_error",
     "infeasible", "unbounded", "invalid_solution"],
)
def test_optimizer_failure_is_explicit_and_keeps_named_plans(monkeypatch, reason):
    monkeypatch.setattr(scenario_service, "optimize_funding", lambda *args, **kwargs: OptimizationFailure(reason))
    response = api.scenario(api.ScenarioRequest(
        paths=120,
        obligations=[{"id": "repair", "label": "Repair", "amount": 4500.0, "due_in_days": 3}],
    ), None)

    assert response.funding_gap > 0
    assert len(response.plans) == 4
    assert response.recommendation is not None
    assert response.optimal_plan is None
    assert response.optimizer_status.code == reason
    assert response.optimizer_status.message
    assert response.optimizer_status.paths == 120
    assert response.optimizer_status.time_limit_seconds == 10.0
    if reason == "solver_timeout":
        assert "120 paths" in response.optimizer_status.message
        assert "10 seconds" in response.optimizer_status.message


def test_covered_reserve_is_not_reported_as_solver_failure(monkeypatch):
    def unexpected_optimization(*args, **kwargs):
        raise AssertionError("No optimizer is needed for a covered reserve")

    monkeypatch.setattr(api, "optimize_funding", unexpected_optimization)
    response = api.scenario(api.ScenarioRequest(paths=120), None)
    assert response.funding_gap == 0.0
    assert response.optimal_plan is None
    assert response.optimizer_status.code == "not_needed"
