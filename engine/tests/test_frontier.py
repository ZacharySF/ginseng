import json
import time
from dataclasses import replace
from datetime import timedelta

import numpy as np
import pytest
from ginseng import frontier
from ginseng.generate import canonical_shocks, generate_persona
from ginseng.portfolio import aligned_asset_returns
from ginseng.sampling import prepare_history, sample_bundle
from ginseng.simulate import cash_paths


@pytest.fixture(scope="module")
def state():
    return generate_persona()


@pytest.fixture(scope="module")
def report(state):
    return frontier.portfolio_frontier(state, canonical_shocks())


def test_first_breach_uses_that_days_asset_value_not_terminal_or_worst_cash_day():
    growth = np.array([
        [[1.1, .8], [1.2, .7], [.2, 1.5]],
        [[.7, 1.2], [1.3, .9], [.8, 1.1]],
        [[1.1, 1.2], [1.2, 1.1], [1.3, 1.4]],
    ])
    cash = np.array([[100., 99., -100.], [99., 120., 80.], [100., 100., 100.]])
    terminal, pressure, days = frontier._first_pressure_returns(growth, cash, 100.)
    np.testing.assert_array_equal(days, [2, 1])
    np.testing.assert_allclose(pressure, [[.2, -.3, 0], [-.3, .2, 0]])
    np.testing.assert_allclose(terminal, [[-.8, .5, 0], [-.2, .1, 0], [.3, .4, 0]])
    assert not np.array_equal(pressure[:, :2], terminal[:2, :2])


def test_no_pressure_is_empty_and_buffer_equality_survives():
    terminal, pressure, days = frontier._first_pressure_returns(
        np.ones((2, 1, 2)), np.array([[0.], [1.]]), 0.,
    )
    assert terminal.shape == (2, 3)
    assert pressure.shape == (0, 3)
    assert days.size == 0
    with pytest.raises(ValueError, match="aligned"):
        frontier._first_pressure_returns(np.ones((2, 1, 2)), np.ones((2, 2)), 0)


def test_exact_fractional_tail_and_signed_gain_convention():
    losses = np.array([0.] * 23 + [.3, .5])
    # The worst 5% of 25 equal observations is exactly 1.25 observations.
    pressure = np.column_stack((-losses, np.zeros(25)))
    terminal = np.array([[.1, 0], [.3, 0]])
    metric = frontier._metrics(terminal, pressure, np.array([1., 0]))
    assert metric["pressure_cvar"] == pytest.approx((.5 + .25 * .3) / 1.25)
    assert metric["volatility"] == pytest.approx(np.sqrt(.02))
    assert metric["mean_return"] == pytest.approx(.2)
    gain = frontier._metrics(terminal, np.full((25, 2), .2), np.array([1., 0]))
    assert gain["pressure_cvar"] == pytest.approx(-.2)


def test_ties_and_cash_sleeve_scale_all_three_objectives():
    terminal = np.array([[.1, 0], [-.2, 0], [.3, 0]])
    pressure = np.column_stack((-np.array([.1] * 17 + [.4] * 8), np.zeros(25)))
    original = frontier._metrics(terminal, pressure, np.array([1., 0]))
    half = frontier._metrics(terminal, pressure, np.array([.5, .5]))
    cash = frontier._metrics(terminal, pressure, np.array([0., 1]))
    assert original["pressure_cvar"] == pytest.approx(.4)
    for name in original:
        assert half[name] == pytest.approx(original[name] / 2)
        assert cash[name] == 0


def test_pareto_direction_preserves_tradeoffs_and_duplicates():
    def point(mean, vol, tail):
        return {"mean_return": mean, "volatility": vol, "pressure_cvar": tail}
    points = [point(.1, .2, .3), point(.1, .2, .3), point(.05, .3, .4),
              point(.2, .3, .4), point(.1, .2, .2)]
    assert frontier._pareto_mask(points) == [False, False, False, True, True]
    assert frontier._pareto_mask(points[:2]) == [True, True]


def test_third_axis_preserves_a_backstop_rejected_by_mean_volatility_alone():
    # Both assets have 20% mean terminal return. A has lower terminal
    # volatility, but loses half its value exactly when bank cash is tight.
    # B preserves its value on those first-breach days. All cash earns zero.
    growth = np.array([
        [[.5, 1.], [1.1, 1.0]],
        [[.5, 1.], [1.2, 1.2]],
        [[.5, 1.], [1.3, 1.4]],
    ])
    terminal, pressure, _ = frontier._first_pressure_returns(
        growth, np.array([[0., 2.], [0., 2.], [0., 2.]]), 1.,
    )
    a, b, cash = [frontier._metrics(terminal, pressure, w) for w in np.eye(3)]
    assert a["mean_return"] == pytest.approx(b["mean_return"])
    assert a["volatility"] < b["volatility"]
    assert a["pressure_cvar"] == .5
    assert b["pressure_cvar"] == 0
    assert frontier._pareto_mask([a, b, cash]) == [True, True, True]


def test_weights_reject_material_solver_residuals():
    assert frontier._feasible_weights(None, 3) is None
    assert frontier._feasible_weights(np.array([.4, .4, .4]), 3) is None
    assert frontier._feasible_weights(np.array([-.01, .4, .61]), 3) is None
    assert frontier._feasible_weights(np.array([np.nan, 0., 1.]), 3) is None
    fixed = frontier._feasible_weights(np.array([-1e-9, .4, .600000001]), 3)
    assert fixed.min() == 0
    assert fixed.sum() == pytest.approx(1)


def test_real_repair_experiment_has_finite_feasible_points_and_current_anchor(state, report):
    assert report["status"] == "ready"
    json.dumps(report, allow_nan=False)
    assert report["symbols"] == ["VTI", "VXUS", "CASH"]
    assert len(report["points"]) >= frontier.RANDOM_CANDIDATES + 5
    for point in report["points"]:
        weights = np.array(point["weights"])
        assert weights.min() >= 0
        assert weights.sum() == pytest.approx(1)
        assert weights.shape == (3,)
        assert point["discovery"]["volatility"] >= 0
        assert point["evaluation"]["volatility"] >= 0
    current = next(p for p in report["points"] if p["id"] == "current")
    np.testing.assert_allclose(current["weights"], [.7, .3, 0])
    cash = next(p for p in report["points"] if p["label"] == "100% CASH")
    assert cash["discovery"] == {"mean_return": 0., "volatility": 0., "pressure_cvar": 0.}
    metadata = report["metadata"]
    assert metadata["discovery_draw_id"] != metadata["evaluation_draw_id"]
    assert metadata["paths_per_split"] == 2048
    assert report["pressure"]["discovery_count"] >= frontier.MIN_PRESSURE_PATHS
    assert "not an out-of-time backtest" in metadata["evaluation_scope"]
    assert [p["pareto"] for p in report["points"]] == frontier._pareto_mask([p["discovery"] for p in report["points"]])


def test_public_discovery_metric_replays_shared_cash_and_asset_indices(state, report):
    prepared = prepare_history(state)
    bundle = sample_bundle(prepared, 30, 2048, 42, domain=600)
    _, returns = aligned_asset_returns(state)
    growth = np.cumprod(1 + returns[bundle.index_matrix], axis=1)
    balances = state.immediate_funding + cash_paths(state, bundle, canonical_shocks())
    breach = balances < state.operating_buffer
    affected = np.flatnonzero(breach.any(axis=1))
    days = breach[affected].argmax(axis=1)
    allocation = np.array([.7, .3])
    losses = -((growth[affected, days] - 1) @ allocation)
    # Independent fractional-tail implementation, with a partial last row.
    descending = np.sort(losses)[::-1]
    tail_count = len(descending) * .05
    whole = int(tail_count)
    expected_tail = (descending[:whole].sum() + (tail_count - whole) * descending[whole]) / tail_count
    current = next(p for p in report["points"] if p["id"] == "current")
    assert current["discovery"]["pressure_cvar"] == pytest.approx(expected_tail)
    assert report["pressure"]["discovery_count"] == len(affected)


def test_explicit_history_boundaries_preserve_joint_alignment_and_do_not_fill_future_days(state):
    first = state.as_of - timedelta(days=200)
    last = state.as_of - timedelta(days=10)
    bounded = replace(state, history_start=first, history_end=last)
    _, returns = aligned_asset_returns(bounded)
    assert len(returns) == 191
    for index, item in enumerate(bounded.asset_daily_returns):
        expected = [value for day, value in item.daily_returns if first <= day <= last]
        np.testing.assert_array_equal(returns[:, index], expected)
    prepared = prepare_history(bounded)
    assert len(prepared.joint) == len(returns)
    bundle = sample_bundle(prepared, 30, 2048, 42, domain=600)
    growth = np.cumprod(1 + returns[bundle.index_matrix], axis=1)
    balances = bounded.immediate_funding + cash_paths(bounded, bundle, canonical_shocks())
    terminal, pressure, _ = frontier._first_pressure_returns(growth, balances, bounded.operating_buffer)
    result = frontier.portfolio_frontier(bounded, canonical_shocks())
    assert result["status"] == "ready"
    assert result["metadata"]["history_days"] == 191
    current = next(p for p in result["points"] if p["id"] == "current")
    assert current["discovery"] == pytest.approx(frontier._metrics(terminal, pressure, np.array([.7, .3, 0])))
    assert result["pressure"]["discovery_count"] == len(pressure)


def test_explicit_full_history_has_same_input_identity_as_implicit_boundaries(state, report):
    explicit = replace(
        state,
        history_start=min(item.txn_date for item in state.transactions),
        history_end=state.as_of,
    )
    result = frontier.portfolio_frontier(explicit, canonical_shocks())
    assert result["metadata"]["input_id"] == report["metadata"]["input_id"]
    future = replace(state, history_end=state.as_of + timedelta(days=1))
    unavailable = frontier.portfolio_frontier(future, canonical_shocks())
    assert unavailable["status"] == "unavailable"
    assert "as-of date" in unavailable["message"]


def test_same_input_reproduces_candidates_and_independent_evaluation(state, report):
    repeated = frontier.portfolio_frontier(state, canonical_shocks())
    assert repeated["pressure"] == report["pressure"]
    assert repeated["metadata"]["input_id"] == report["metadata"]["input_id"]
    assert [p["id"] for p in repeated["points"]] == [p["id"] for p in report["points"]]
    for first, second in zip(report["points"], repeated["points"]):
        np.testing.assert_allclose(first["weights"], second["weights"], atol=1e-10)
        assert first["pareto"] == second["pareto"]
        assert first["evaluation"] == pytest.approx(second["evaluation"])


def test_fresh_evaluation_cannot_change_candidate_weights_or_discovery_selection(state, report, monkeypatch):
    original = frontier.sample_bundle
    def changed_evaluation(*args, **kwargs):
        if kwargs.get("domain") == 601:
            kwargs["domain"] = 603
        return original(*args, **kwargs)
    monkeypatch.setattr(frontier, "sample_bundle", changed_evaluation)
    changed = frontier.portfolio_frontier(state, canonical_shocks())
    assert changed["metadata"]["evaluation_draw_id"] != report["metadata"]["evaluation_draw_id"]
    for first, second in zip(report["points"], changed["points"]):
        np.testing.assert_allclose(first["weights"], second["weights"], atol=1e-10)
        assert first["discovery"] == pytest.approx(second["discovery"])
        assert first["pareto"] == second["pareto"]


def test_quiet_case_reports_insufficient_pressure_instead_of_zero_tail(state):
    result = frontier.portfolio_frontier(state)
    assert result["status"] == "unavailable"
    assert result["pressure"]["discovery_count"] < 128
    assert "Too few" in result["message"]
    assert "points" not in result


def test_evaluation_split_must_also_clear_the_pressure_gate(state, monkeypatch):
    original = frontier._first_pressure_returns
    calls = 0
    def trim_evaluation(*args):
        nonlocal calls
        calls += 1
        terminal, pressure, days = original(*args)
        return (terminal, pressure[:127], days[:127]) if calls == 2 else (terminal, pressure, days)
    monkeypatch.setattr(frontier, "_first_pressure_returns", trim_evaluation)
    result = frontier.portfolio_frontier(state, canonical_shocks())
    assert result["status"] == "unavailable"
    assert result["pressure"]["discovery_count"] > 128
    assert result["pressure"]["evaluation_count"] == 127


@pytest.mark.parametrize("change", [
    {"forecast_horizon": 61}, {"forecast_horizon": 0}, {"operating_buffer": np.nan},
    {"asset_daily_returns": ()}, {"holdings": ()},
])
def test_invalid_inputs_return_explicit_unavailability(state, change):
    result = frontier.portfolio_frontier(replace(state, **change), canonical_shocks())
    assert result["status"] == "unavailable"
    json.dumps(result, allow_nan=False)


def test_history_bounds_checked_before_large_daily_history_allocation(state, monkeypatch):
    oversized = replace(state, history_start=state.as_of - timedelta(days=3660))
    monkeypatch.setattr(frontier, "aligned_asset_returns", lambda _: pytest.fail("Must reject before alignment"))
    assert frontier.portfolio_frontier(oversized)["status"] == "unavailable"


@pytest.mark.parametrize("kwargs", [{"seed": -1}, {"seed": True}, {"block_length": 0}, {"block_length": 1.5}])
def test_invalid_sampling_configuration_rejected(state, kwargs):
    assert frontier.portfolio_frontier(state, **kwargs)["status"] == "unavailable"


def test_changed_cash_schedule_changes_provenance_and_pressure(state, report):
    changed = tuple(replace(o, amount=o.amount * 1.1) for o in canonical_shocks())
    result = frontier.portfolio_frontier(state, changed)
    assert result["metadata"]["input_id"] != report["metadata"]["input_id"]
    assert result["pressure"]["discovery_probability"] >= report["pressure"]["discovery_probability"]


def test_missing_solver_preserves_valid_cloud_with_explicit_partial_status(state, monkeypatch):
    import cvxpy as cp
    monkeypatch.setattr(cp, "installed_solvers", list)
    result = frontier.portfolio_frontier(state, canonical_shocks())
    assert result["status"] == "ready"
    assert result["metadata"]["partial_optimization"]
    assert "unavailable" in result["metadata"]["solver"]["message"]
    assert all(p["source"] != "optimized" for p in result["points"])


def test_solver_failures_are_reported_and_never_fabricate_optimized_points(state, monkeypatch):
    import cvxpy as cp
    def failed_solve(*args, **kwargs):
        raise cp.error.SolverError("Deliberate test solver failure")
    monkeypatch.setattr(cp.Problem, "solve", failed_solve)
    result = frontier.portfolio_frontier(state, canonical_shocks())
    assert result["status"] == "ready"
    statistics = result["metadata"]["solver"]
    assert statistics["failed"] == statistics["attempted"] == 15
    assert statistics["succeeded"] == 0
    assert result["metadata"]["partial_optimization"]
    assert all(p["source"] != "optimized" for p in result["points"])


def test_elapsed_budget_skips_solves_without_inventing_solutions():
    terminal = np.array([[.1, 0], [-.2, 0], [.3, 0]])
    pressure = np.array([[.1, 0], [-.2, 0], [-.3, 0]])
    candidates, statistics = frontier._optimized_candidates(terminal, pressure, time.monotonic() - 1)
    assert candidates == []
    assert statistics["attempted"] == 0
    assert statistics["budget_exhausted"]


def test_convex_anchors_match_known_simplex_extrema(report):
    minimum = next(p for p in report["points"] if p["id"] == "min-volatility")
    maximum = next(p for p in report["points"] if p["id"] == "max-return")
    assert minimum["weights"] == [0, 0, 1]
    assert minimum["discovery"]["volatility"] == 0
    assert maximum["discovery"]["mean_return"] == max(p["discovery"]["mean_return"] for p in report["points"])
