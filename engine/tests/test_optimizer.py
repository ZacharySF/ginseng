"""Observable contracts for the bounded CVaR funding optimizer."""

from __future__ import annotations

import builtins
from datetime import date, timedelta
from math import isfinite
from unittest.mock import patch

import pytest

import ginseng.optimizer as optimizer
from ginseng.optimizer import optimize_funding
from ginseng.simulate import draw_bundle
from ginseng.state import CreditAccount, FinancialState, Holding, Obligation, TaxLot, Transaction, TransactionType


AS_OF = date(2026, 1, 1)
HISTORY_DAYS = 60


def _credit_account(
    account_id: str,
    available_credit: float,
    *,
    apr: float = 0.0,
    grace_period_eligible: bool = False,
) -> CreditAccount:
    return CreditAccount(
        account_id=account_id,
        credit_limit=available_credit,
        current_balance=0.0,
        purchase_apr=apr,
        statement_close_day=2,
        payment_due_day=25,
        grace_period_eligible=grace_period_eligible,
        minimum_payment=25.0,
    )


def _taxable_holding(market_value: float, cost_basis: float) -> Holding:
    quantity = 100.0
    return Holding(
        symbol="TEST",
        account="taxable",
        current_price=market_value / quantity,
        tax_lots=(
            TaxLot(
                lot_id="test-lot",
                symbol="TEST",
                quantity=quantity,
                cost_basis_per_share=cost_basis / quantity,
                purchase_date=AS_OF - timedelta(days=365),
            ),
        ),
    )


def _state(
    *,
    opening_cash: float = 0.0,
    cards: tuple[CreditAccount, ...] = (),
    holdings: tuple[Holding, ...] = (),
    daily_discretionary: float = 0.0,
    market_daily_return: float | None = None,
) -> FinancialState:
    start = AS_OF - timedelta(days=HISTORY_DAYS - 1)
    transactions = [
        Transaction(start, TransactionType.TRANSFER, opening_cash, "Opening balance"),
    ]
    for day_offset in range(HISTORY_DAYS):
        day = start + timedelta(days=day_offset)
        if daily_discretionary:
            # Matched daily income makes the resampled net flow identically
            # zero while retaining a known discretionary deferral series.
            transactions.extend(
                (
                    Transaction(day, TransactionType.INCOME_VARIABLE, daily_discretionary, "Income"),
                    Transaction(
                        day,
                        TransactionType.EXPENSE_DISCRETIONARY_VARIABLE,
                        daily_discretionary,
                        "Discretionary spending",
                    ),
                )
            )
    portfolio_daily_returns = (
        tuple(
            (start + timedelta(days=day_offset), market_daily_return)
            for day_offset in range(HISTORY_DAYS)
        )
        if market_daily_return is not None
        else ()
    )
    return FinancialState(
        as_of=AS_OF,
        transactions=tuple(transactions),
        fixed_income_schedule=(),
        fixed_obligations=(),
        planned_discretionary_events=(),
        credit_accounts=cards,
        holdings=holdings,
        operating_buffer=1000.0,
        coverage_target=0.95,
        forecast_horizon=30,
        portfolio_daily_returns=portfolio_daily_returns,
    )


def _bundle(state: FinancialState, horizon_days: int, n_paths: int = 4):
    return draw_bundle(
        state,
        horizon_days=horizon_days,
        n_paths=n_paths,
        seed=17,
        mean_block_length=7,
    )


def _require_cvxpy():
    return pytest.importorskip("cvxpy")


def test_returns_none_without_any_funding_lever():
    state = _state()

    assert optimize_funding(state, _bundle(state, 5), ()) is None


def test_returns_none_when_cvxpy_is_unavailable():
    state = _state(cards=(_credit_account("primary", 5_000.0),))
    real_import = builtins.__import__

    def unavailable_cvxpy(name, *args, **kwargs):
        if name == "cvxpy":
            raise ImportError("cvxpy unavailable")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=unavailable_cvxpy):
        assert optimize_funding(state, _bundle(state, 5), ()) is None


def test_returns_none_when_clarabel_is_unavailable(monkeypatch):
    cvxpy = _require_cvxpy()
    state = _state(cards=(_credit_account("primary", 5_000.0),))
    monkeypatch.setattr(cvxpy, "installed_solvers", lambda: [])

    assert optimize_funding(state, _bundle(state, 5), ()) is None


def test_returns_none_when_clarabel_fails(monkeypatch):
    cvxpy = _require_cvxpy()
    state = _state(cards=(_credit_account("primary", 5_000.0),))
    monkeypatch.setattr(
        cvxpy.Problem,
        "solve",
        lambda *args, **kwargs: (_ for _ in ()).throw(cvxpy.error.SolverError("failed")),
    )

    assert optimize_funding(state, _bundle(state, 5), ()) is None


def test_returns_none_when_model_exceeds_documented_resource_cap(monkeypatch):
    state = _state(cards=(_credit_account("primary", 5_000.0),))
    monkeypatch.setattr(optimizer, "MAX_SCENARIO_DAYS", 1)

    assert optimize_funding(state, _bundle(state, 2, n_paths=2), ()) is None


def test_credit_draw_is_limited_to_the_primary_card_not_all_card_limits():
    _require_cvxpy()
    primary = _credit_account("primary", 3_000.0)
    secondary = _credit_account("secondary", 2_000.0)
    state = _state(cards=(primary, secondary))
    result = optimize_funding(
        state,
        _bundle(state, 5),
        (Obligation("bill", "Bill", 4_000.0, 3),),
        buffer_tolerance_dollar_days=1e9,
    )

    assert result is not None
    assert result.credit_draw == pytest.approx(primary.available_credit, abs=1e-3)
    assert result.credit_draw <= primary.available_credit + 1e-6


def test_credit_repayment_beyond_the_chart_is_costed_on_its_actual_day():
    _require_cvxpy()
    state = _state(cards=(_credit_account("primary", 5_000.0),))
    result = optimize_funding(
        state,
        _bundle(state, 5),
        (Obligation("bill", "Bill", 3_000.0, 3),),
        overdraft_apr=0.365,
        buffer_tolerance_dollar_days=1e9,
    )

    assert result is not None
    # The day-24 repayment lies outside the five-day chart. Spec-14 extends
    # to day 27, leaving a $3,000 four-day overdraft: 3000 * 4 * .365 / 365.
    assert result.expected_cost == pytest.approx(12.0, abs=2e-4)


def test_liquidation_settlement_beyond_the_chart_is_not_clamped_earlier():
    _require_cvxpy()
    state = _state(holdings=(_taxable_holding(6_000.0, 6_000.0),))
    result = optimize_funding(
        state,
        _bundle(state, 2),
        (Obligation("bill", "Bill", 4_000.0, 2),),
        overdraft_apr=0.365,
        buffer_tolerance_dollar_days=1e9,
    )

    assert result is not None
    # Settlement is day 3, after the two-day chart. A $4,000 deficit therefore
    # remains for the second forecast day, costing $4 and triggering a path
    # shortfall on every deterministic path.
    assert result.expected_cost == pytest.approx(4.0, abs=2e-4)
    assert result.cash_shortfall_probability == pytest.approx(1.0)


def test_coverage_one_uses_a_finite_worst_case_objective():
    _require_cvxpy()
    state = _state(cards=(_credit_account("primary", 5_000.0),))
    result = optimize_funding(
        state,
        _bundle(state, 5),
        (Obligation("bill", "Bill", 3_000.0, 3),),
        coverage_target=1.0,
        overdraft_apr=0.365,
        buffer_tolerance_dollar_days=1e9,
    )

    assert result is not None
    assert result.cvar_cost == pytest.approx(result.var_cost, abs=2e-4)
    assert result.cvar_cost == pytest.approx(result.expected_cost, abs=2e-4)
    assert result.expected_cost == pytest.approx(12.0, abs=2e-4)
    assert 0.0 <= result.credit_draw <= 5_000.0
    assert result.liquidation_amount == pytest.approx(0.0, abs=1e-6)
    assert 0.0 <= result.deferral_fraction <= 1.0
    for value in (
        result.credit_draw,
        result.liquidation_amount,
        result.deferral_fraction,
        result.cvar_cost,
        result.var_cost,
        result.expected_cost,
        result.cash_shortfall_probability,
    ):
        assert isfinite(value)


def test_market_returns_change_the_liquidation_funding_mix():
    _require_cvxpy()
    holding = _taxable_holding(6_000.0, 4_800.0)
    up_market = _state(holdings=(holding,), market_daily_return=0.01)
    down_market = _state(holdings=(holding,), market_daily_return=-0.01)
    obligation = (Obligation("bill", "Bill", 4_000.0, 5),)

    up_plan = optimize_funding(
        up_market,
        _bundle(up_market, 10),
        obligation,
        overdraft_apr=0.365,
        capital_gains_rate=0.01,
        buffer_tolerance_dollar_days=1e9,
    )
    down_plan = optimize_funding(
        down_market,
        _bundle(down_market, 10),
        obligation,
        overdraft_apr=0.365,
        capital_gains_rate=0.01,
        buffer_tolerance_dollar_days=1e9,
    )

    assert up_plan is not None and down_plan is not None
    assert up_plan.cost_is_path_dependent is True
    assert down_plan.cost_is_path_dependent is True
    assert up_plan.liquidation_amount < down_plan.liquidation_amount
    assert up_plan.expected_cost > down_plan.expected_cost


def test_infeasible_buffer_constraint_fails_closed():
    _require_cvxpy()
    state = _state(holdings=(_taxable_holding(1.0, 1.0),))

    result = optimize_funding(
        state,
        _bundle(state, 5),
        (Obligation("bill", "Bill", 5_000.0, 2),),
        buffer_tolerance_dollar_days=0.0,
    )

    assert result is None


def test_already_funded_paths_need_no_shortfall_cost_or_extra_funding():
    _require_cvxpy()
    state = _state(
        opening_cash=5_000.0,
        cards=(_credit_account("primary", 1_000.0, apr=0.365),),
    )
    result = optimize_funding(state, _bundle(state, 30), (), operating_buffer=1_000.0)
    assert result is not None
    assert result.expected_cost == pytest.approx(0.0, abs=1e-6)
    assert result.cvar_cost == pytest.approx(0.0, abs=1e-6)
    assert result.cash_shortfall_probability == 0.0
    assert result.credit_draw == pytest.approx(0.0, abs=1e-5)
