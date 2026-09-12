"""Tests for the fourth column, wrong-way risk metrics, and CVaR optimizer."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import numpy as np
import pytest

from ginseng.generate import canonical_shocks, generate_persona
from ginseng.metrics import compute_scenario_metrics, wrong_way_risk
from ginseng.simulate import draw_bundle, portfolio_value_paths, discretionary_resampled_paths
from ginseng.state import FinancialState, Obligation, Transaction, TransactionType

from tests.test_simulate import make_history_state


# ---------------------------------------------------------------------------
# Fourth column: portfolio_value_paths
# ---------------------------------------------------------------------------


def test_portfolio_value_paths_returns_none_when_no_portfolio_daily_returns():
    state = make_history_state()
    assert state.portfolio_daily_returns == ()
    bundle = draw_bundle(state, horizon_days=30, n_paths=50, seed=1, mean_block_length=10)
    assert portfolio_value_paths(state, bundle) is None


def test_portfolio_value_paths_shape_and_positivity():
    state = generate_persona()
    assert len(state.portfolio_daily_returns) > 0
    bundle = draw_bundle(state, horizon_days=30, n_paths=100, seed=2, mean_block_length=10)
    pv = portfolio_value_paths(state, bundle)
    assert pv is not None
    assert pv.shape == (100, 30)
    assert np.all(pv > 0), "all portfolio values must be positive"


def test_portfolio_value_paths_is_deterministic():
    state = generate_persona()
    bundle = draw_bundle(state, horizon_days=30, n_paths=80, seed=3, mean_block_length=10)
    pv1 = portfolio_value_paths(state, bundle)
    pv2 = portfolio_value_paths(state, bundle)
    assert pv1 is not None and pv2 is not None
    np.testing.assert_array_equal(pv1, pv2)


def test_per_path_liquidation_cost_varies_across_paths_with_market_data():
    """Regression: fourth column gives path-dependent liquidation, std > 0."""
    state = generate_persona()
    bundle = draw_bundle(state, horizon_days=30, n_paths=200, seed=4, mean_block_length=10)
    pv = portfolio_value_paths(state, bundle)
    assert pv is not None
    settle_col = 2  # T+1 + 2 days, col index 2
    initial_mv = state.marketable_backup_capital
    scale = pv[:, settle_col] / max(initial_mv, 1e-9)
    assert scale.std() > 0.0, "per-path liquidation scale must vary across paths"


# ---------------------------------------------------------------------------
# Wrong-way risk metrics
# ---------------------------------------------------------------------------


def test_wrong_way_risk_keys_and_fraction_in_bounds():
    state = generate_persona()
    bundle = draw_bundle(state, horizon_days=30, n_paths=100, seed=5, mean_block_length=10)
    from ginseng.simulate import cash_paths
    matrix = cash_paths(state, bundle, canonical_shocks())
    pv = portfolio_value_paths(state, bundle)
    assert pv is not None
    wwr = wrong_way_risk(
        matrix, pv, state.immediate_funding,
        state.operating_buffer, state.marketable_backup_capital
    )
    assert set(wwr) == {
        "fraction_forced_to_sell",
        "portfolio_return_all_paths",
        "portfolio_return_when_forced",
        "wrong_way_risk_present",
    }
    assert 0.0 <= wwr["fraction_forced_to_sell"] <= 1.0
    assert isinstance(wwr["wrong_way_risk_present"], bool)


def test_wrong_way_risk_is_none_when_no_portfolio_daily_returns():
    """ScenarioMetrics.wrong_way_risk is None for a state with no market data."""
    state = make_history_state()
    bundle = draw_bundle(state, horizon_days=30, n_paths=60, seed=6, mean_block_length=10)
    computed = compute_scenario_metrics(state, bundle, (), 0.95, 1000.0)
    assert computed.wrong_way_risk is None


def test_wrong_way_risk_is_populated_for_canonical_persona():
    """ScenarioMetrics.wrong_way_risk is a dict for the canonical persona."""
    state = generate_persona()
    bundle = draw_bundle(state, horizon_days=30, n_paths=100, seed=7, mean_block_length=10)
    computed = compute_scenario_metrics(
        state, bundle, canonical_shocks(), 0.95, 1000.0
    )
    assert computed.wrong_way_risk is not None
    assert isinstance(computed.wrong_way_risk, dict)


# ---------------------------------------------------------------------------
# CVaR optimizer
# ---------------------------------------------------------------------------


def test_optimizer_returns_none_when_cvxpy_unavailable():
    """Graceful degradation when cvxpy is not installed."""
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "cvxpy":
            raise ImportError("cvxpy not available")
        return real_import(name, *args, **kwargs)

    state = generate_persona()
    bundle = draw_bundle(state, horizon_days=30, n_paths=60, seed=8, mean_block_length=10)

    from ginseng.optimizer import optimize_funding
    with patch("builtins.__import__", side_effect=mock_import):
        result = optimize_funding(state, bundle, canonical_shocks())
    assert result is None


def test_optimizer_returns_none_when_no_credit_or_holdings():
    """Returns None when there is literally nothing to optimise."""
    state = make_history_state()  # no credit accounts, no holdings
    assert not state.credit_accounts
    assert not state.holdings
    bundle = draw_bundle(state, horizon_days=30, n_paths=60, seed=9, mean_block_length=10)
    from ginseng.optimizer import optimize_funding
    result = optimize_funding(state, bundle, ())
    assert result is None


def test_optimizer_solves_on_canonical_persona_with_shock():
    """Solver finds an optimal solution for the canonical shocked persona."""
    pytest.importorskip("cvxpy")
    state = generate_persona()
    bundle = draw_bundle(state, horizon_days=30, n_paths=200, seed=10, mean_block_length=10)
    from ginseng.optimizer import optimize_funding
    result = optimize_funding(state, bundle, canonical_shocks())
    assert result is not None
    assert result.solver_status in ("optimal", "optimal_inaccurate")
    assert result.credit_draw >= 0.0
    assert result.liquidation_amount >= 0.0
    assert result.deferral_fraction >= 0.0


def test_optimizer_respects_bounds():
    """Optimised controls stay within their declared bounds."""
    pytest.importorskip("cvxpy")
    state = generate_persona()
    bundle = draw_bundle(state, horizon_days=30, n_paths=200, seed=11, mean_block_length=10)
    from ginseng.optimizer import optimize_funding
    result = optimize_funding(state, bundle, canonical_shocks())
    assert result is not None

    available_credit = sum(a.available_credit for a in state.credit_accounts)
    assert result.credit_draw <= available_credit + 1e-6
    assert result.liquidation_amount <= state.marketable_backup_capital + 1e-6
    assert result.deferral_fraction <= 1.0 + 1e-6


def test_cost_is_path_dependent_flag():
    """Flag is True iff portfolio_daily_returns is non-empty."""
    pytest.importorskip("cvxpy")
    state_with_market = generate_persona()
    state_without_market = make_history_state()

    bundle_with = draw_bundle(state_with_market, horizon_days=30, n_paths=100, seed=12, mean_block_length=10)
    bundle_without = draw_bundle(state_without_market, horizon_days=30, n_paths=100, seed=12, mean_block_length=10)

    from ginseng.optimizer import optimize_funding
    result_with = optimize_funding(state_with_market, bundle_with, canonical_shocks())
    assert result_with is not None
    assert result_with.cost_is_path_dependent is True

    # make_history_state has no holdings/credit, so result_without is None — expected
    result_without = optimize_funding(state_without_market, bundle_without, ())
    assert result_without is None  # no credit or holdings → None


def test_implied_liquidity_price_nonnegative_when_present():
    """When the buffer constraint binds, its dual value should be ≥ 0."""
    pytest.importorskip("cvxpy")
    state = generate_persona()
    bundle = draw_bundle(state, horizon_days=30, n_paths=200, seed=13, mean_block_length=10)
    from ginseng.optimizer import optimize_funding
    # Use a very tight tolerance to force the constraint to bind
    result = optimize_funding(
        state, bundle, canonical_shocks(),
        buffer_tolerance_dollar_days=0.01,
    )
    if result is not None and result.implied_liquidity_price is not None:
        assert result.implied_liquidity_price >= 0.0
