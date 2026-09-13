"""Fourth-column portfolio paths, shared sampling, and wrong-way risk
(spec 8.3-8.4): the market series must ride the same stationary-bootstrap
day indices the cash forecast resamples, liquidation proceeds must settle
path by path, and portfolio returns conditioned on forced-liquidity paths
must expose wrong-way risk - or be honestly absent when no market history
or marketable assets exist."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from ginseng.funding import PlanKind, PlanSpec, evaluate_plan
from ginseng.generate import generate_persona
from ginseng.metrics import compute_scenario_metrics, wrong_way_risk
from ginseng.simulate import (
    cash_paths,
    discretionary_resampled_paths,
    draw_bundle,
    portfolio_value_paths,
)
from ginseng.state import (
    FinancialState,
    Holding,
    Obligation,
    TaxLot,
    Transaction,
    TransactionType,
)

AS_OF = date(2026, 8, 31)
HISTORY_DAYS = 45


def make_market_state(
    market_returns: list[float] | None = None,
    holdings_value: float | None = 2000.0,
    opening_balance: float = 100.0,
) -> FinancialState:
    """A state whose every recorded day carries a uniquely identifiable
    discretionary amount (`$100 + day_index`), so the historical day any
    bootstrap path-day actually drew can be recovered from the observable
    cash forecast, plus an optional per-day market-return series."""
    start = AS_OF - timedelta(days=HISTORY_DAYS - 1)
    transactions = [
        Transaction(start, TransactionType.TRANSFER, opening_balance, "Opening balance")
    ]
    for i in range(HISTORY_DAYS):
        transactions.append(
            Transaction(
                start + timedelta(days=i),
                TransactionType.EXPENSE_DISCRETIONARY_VARIABLE,
                100.0 + i,
                "Dining",
            )
        )
    holdings = ()
    if holdings_value is not None:
        lots = (TaxLot("lot-1", "VTI", holdings_value / 100.0, 80.0, start),)
        holdings = (Holding("VTI", "taxable", 100.0, lots),)
    daily_returns = (
        tuple(
            (start + timedelta(days=i), market_returns[i]) for i in range(HISTORY_DAYS)
        )
        if market_returns is not None
        else ()
    )
    return FinancialState(
        as_of=AS_OF,
        transactions=tuple(transactions),
        fixed_income_schedule=(),
        fixed_obligations=(),
        planned_discretionary_events=(),
        credit_accounts=(),
        holdings=holdings,
        operating_buffer=1000.0,
        coverage_target=0.95,
        forecast_horizon=30,
        portfolio_daily_returns=daily_returns,
    )


def make_settlement_state(market_return: float | None) -> FinancialState:
    """One taxable holding worth $1,000, $100 of settled cash, and nothing
    else stochastic, so every evaluated cash path is deterministic until a
    plan moves money."""
    lots = (TaxLot("lot-1", "VTI", 10.0, 80.0, AS_OF),)
    daily_returns = ((AS_OF, market_return),) if market_return is not None else ()
    return FinancialState(
        as_of=AS_OF,
        transactions=(Transaction(AS_OF, TransactionType.TRANSFER, 100.0, "Opening balance"),),
        fixed_income_schedule=(),
        fixed_obligations=(),
        planned_discretionary_events=(),
        credit_accounts=(),
        holdings=(Holding("VTI", "taxable", 100.0, lots),),
        operating_buffer=1000.0,
        coverage_target=0.95,
        forecast_horizon=30,
        portfolio_daily_returns=daily_returns,
    )


BILL = (Obligation("bill", "Bill", 500.0, 10, TransactionType.EXPENSE_FIXED),)
SELL_SPEC = PlanSpec(id="sell", label="Sell holdings", kind=PlanKind.LIQUIDATE, liquidation_target=500.0)
WAIT_SPEC = PlanSpec(id="wait", label="Do nothing", kind=PlanKind.PROTECTIVE)


# ---------------------------------------------------------------------------
# Shared cash/market sampling (spec 15, 8.3)
# ---------------------------------------------------------------------------


def test_discretionary_paths_are_exactly_what_cash_paths_spent():
    state = make_market_state()
    bundle = draw_bundle(state, horizon_days=12, n_paths=40, seed=3, mean_block_length=7)
    matrix = cash_paths(state, bundle)
    prior = np.concatenate([np.zeros((matrix.shape[0], 1)), matrix[:, :-1]], axis=1)
    # No income, essential, or fixed flows exist in this state, so the
    # day-over-day cash movement is exactly the discretionary spend of the
    # day the bootstrap drew.
    np.testing.assert_allclose(discretionary_resampled_paths(state, bundle), -(matrix - prior))


def test_market_paths_ride_the_same_bootstrap_indices_as_cash_paths():
    state = make_market_state(market_returns=[0.001 * (i + 1) for i in range(HISTORY_DAYS)])
    bundle = draw_bundle(state, horizon_days=12, n_paths=40, seed=4, mean_block_length=7)
    matrix = cash_paths(state, bundle)
    disc = discretionary_resampled_paths(state, bundle)

    # Recover the historical day index each path-day drew from the cash
    # forecast alone (spend on day i is 100 + i).
    drawn_index = (disc - 100.0).astype(int)
    assert drawn_index.min() >= 0 and drawn_index.max() < HISTORY_DAYS

    returns = np.array([0.001 * (i + 1) for i in range(HISTORY_DAYS)])
    expected = state.marketable_backup_capital * np.cumprod(1.0 + returns[drawn_index], axis=1)
    pv = portfolio_value_paths(state, bundle)
    assert pv is not None
    np.testing.assert_allclose(pv, expected, rtol=1e-12)
    # The very first forecast day already grows by the drawn day's return,
    # i.e. market days align with cash days one-for-one.
    np.testing.assert_allclose(pv[:, 0], state.marketable_backup_capital * (1.0 + returns[drawn_index[:, 0]]))


def test_canonical_persona_market_history_aligns_with_the_ledger_window():
    state = generate_persona()
    first_day = min(t.txn_date for t in state.transactions)
    assert state.portfolio_daily_returns[0][0] == first_day
    assert state.portfolio_daily_returns[-1][0] == state.as_of
    # Simple returns derived from GBM log returns keep every growth factor
    # strictly positive, so portfolio paths can never cross zero.
    assert all(r > -1.0 for _, r in state.portfolio_daily_returns)


# ---------------------------------------------------------------------------
# Wrong-way risk (spec 8.4)
# ---------------------------------------------------------------------------


def test_wrong_way_risk_conditions_returns_on_the_forced_paths():
    # available = 0 + cash; buffer = 1000. Paths 0-1 dip below the buffer,
    # paths 2-3 never do.
    cash = np.array(
        [
            [500.0, -200.0, 300.0, 800.0],
            [500.0, 500.0, 600.0, 700.0],
            [1200.0, 1300.0, 1250.0, 1400.0],
            [1500.0, 1600.0, 1700.0, 1800.0],
        ]
    )
    portfolio = np.array(
        [
            [1000.0, 900.0, 850.0, 800.0],  # forced path loses 20%
            [1000.0, 950.0, 920.0, 900.0],  # forced path loses 10%
            [1000.0, 1150.0, 1250.0, 1300.0],  # unforced path gains 30%
            [1000.0, 1000.0, 1000.0, 1000.0],  # unforced path is flat
        ]
    )
    wwr = wrong_way_risk(
        cash,
        portfolio,
        immediate_funding=0.0,
        operating_buffer=1000.0,
        initial_portfolio_value=1000.0,
    )
    assert wwr["fraction_forced_to_sell"] == pytest.approx(0.5)
    assert wwr["portfolio_return_all_paths"] == pytest.approx((-0.2 - 0.1 + 0.3 + 0.0) / 4)
    assert wwr["portfolio_return_when_forced"] == pytest.approx((-0.2 - 0.1) / 2)
    assert wwr["wrong_way_risk_present"] is True


def test_wrong_way_risk_reports_none_when_no_path_is_ever_forced():
    cash = np.full((3, 4), 2000.0)
    portfolio = np.array(
        [
            [1000.0, 1000.0, 1000.0, 800.0],
            [1000.0, 1000.0, 1000.0, 1200.0],
            [1000.0, 1000.0, 1000.0, 1100.0],
        ]
    )
    wwr = wrong_way_risk(cash, portfolio, 0.0, 1000.0, 1000.0)
    assert wwr["fraction_forced_to_sell"] == 0.0
    assert wwr["portfolio_return_all_paths"] == pytest.approx((-0.2 + 0.2 + 0.1) / 3)
    assert wwr["portfolio_return_when_forced"] is None
    assert wwr["wrong_way_risk_present"] is False


def test_wrong_way_risk_absent_when_forced_paths_do_not_underperform():
    cash = np.array(
        [
            [500.0, -100.0, 300.0],  # forced
            [2000.0, 2100.0, 2200.0],  # never forced
        ]
    )
    portfolio = np.array(
        [
            [1000.0, 1400.0, 1500.0],  # forced path gains 50%
            [1000.0, 950.0, 900.0],  # unforced path loses 10%
        ]
    )
    wwr = wrong_way_risk(cash, portfolio, 0.0, 1000.0, 1000.0)
    assert wwr["portfolio_return_when_forced"] == pytest.approx(0.5)
    assert wwr["wrong_way_risk_present"] is False


# ---------------------------------------------------------------------------
# Honest absence without market history or marketable assets
# ---------------------------------------------------------------------------


def test_portfolio_features_are_absent_without_market_history_or_marketable_assets():
    returns = [0.001] * HISTORY_DAYS
    no_history = make_market_state(market_returns=None)  # holdings, no returns
    no_assets = make_market_state(market_returns=returns, holdings_value=None)

    for state in (no_history, no_assets):
        bundle = draw_bundle(state, horizon_days=10, n_paths=20, seed=6, mean_block_length=7)
        assert portfolio_value_paths(state, bundle) is None
        computed = compute_scenario_metrics(state, bundle, (), 0.95, 1000.0)
        assert computed.wrong_way_risk is None


def test_canonical_persona_reports_wrong_way_risk_consistent_with_its_paths():
    state = generate_persona()
    bundle = draw_bundle(state, horizon_days=30, n_paths=120, seed=5, mean_block_length=10)
    pv = portfolio_value_paths(state, bundle)
    assert pv is not None
    assert pv.shape == (120, 30)
    assert np.all(pv > 0.0)

    computed = compute_scenario_metrics(state, bundle, (), state.coverage_target, state.operating_buffer)
    wwr = computed.wrong_way_risk
    assert wwr is not None
    assert set(wwr) == {
        "fraction_forced_to_sell",
        "portfolio_return_all_paths",
        "portfolio_return_when_forced",
        "wrong_way_risk_present",
    }

    # The reported conditioning is exactly the forced subset of these paths.
    available = state.immediate_funding + cash_paths(state, bundle)
    forced = np.any(available < state.operating_buffer, axis=1)
    terminal = (pv[:, -1] - state.marketable_backup_capital) / state.marketable_backup_capital
    assert wwr["fraction_forced_to_sell"] == pytest.approx(forced.mean())
    assert wwr["portfolio_return_all_paths"] == pytest.approx(terminal.mean())
    assert wwr["portfolio_return_when_forced"] == (
        pytest.approx(terminal[forced].mean()) if forced.any() else None
    )
    assert wwr["wrong_way_risk_present"] == bool(forced.any() and terminal[forced].mean() < terminal.mean())


# ---------------------------------------------------------------------------
# Path-scaled settlement proceeds (spec 8.3, 41)
# ---------------------------------------------------------------------------


def _settlement_results(market_return: float | None):
    state = make_settlement_state(market_return)
    bundle = draw_bundle(state, horizon_days=15, n_paths=25, seed=7, mean_block_length=7)
    wait = evaluate_plan(state, bundle, BILL, WAIT_SPEC)
    sell = evaluate_plan(state, bundle, BILL, SELL_SPEC)
    return wait, sell


def test_settlement_proceeds_cover_the_bill_when_no_market_history_exists():
    wait, sell = _settlement_results(market_return=None)
    assert wait.cash_shortfall_probability == 1.0  # $100 cash cannot pay a $500 bill
    assert sell.investment_sold == pytest.approx(500.0)
    assert sell.cash_shortfall_probability == 0.0  # flat T+3 proceeds cover it


def test_market_moves_scale_settlement_proceeds_path_by_path():
    # A -50% daily market means the $500 sale is worth 500 * 0.5^3 = $62.50
    # by the T+1-plus-2-day settlement, so the bill is no longer covered.
    wait, sell = _settlement_results(market_return=-0.5)
    assert wait.cash_shortfall_probability == 1.0
    assert sell.cash_shortfall_probability == 1.0

    # A flat market keeps proceeds at the nominal amount, matching the
    # no-market-history evaluation exactly.
    _, sell_flat = _settlement_results(market_return=0.0)
    assert sell_flat.cash_shortfall_probability == 0.0
