"""Observable contracts for the bounded CVaR funding optimizer."""

from __future__ import annotations

import builtins
from dataclasses import replace
from datetime import date, timedelta
from math import isfinite
from unittest.mock import patch

import numpy as np
import pytest

import ginseng.optimizer as optimizer
from ginseng.funding import FundingConfig
from ginseng.optimizer import OptimalPlan, OptimizationFailure, optimize_funding
from ginseng.policy import FundingPolicy
from ginseng.scenario_service import evaluate_scenario
from ginseng.simulate import PathBundle, draw_bundle
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


def _multi_lot_taxable_holding(lot_market_value: float = 5_000.0) -> Holding:
    """Two equal-value lots whose FIFO and HIFO basis differ materially."""
    current_price = 100.0
    quantity = lot_market_value / current_price
    return Holding(
        symbol="MULTI",
        account="taxable",
        current_price=current_price,
        tax_lots=(
            TaxLot(
                lot_id="older-low-basis",
                symbol="MULTI",
                quantity=quantity,
                cost_basis_per_share=20.0,
                purchase_date=AS_OF - timedelta(days=730),
            ),
            TaxLot(
                lot_id="newer-high-basis",
                symbol="MULTI",
                quantity=quantity,
                cost_basis_per_share=90.0,
                purchase_date=AS_OF - timedelta(days=365),
            ),
        ),
    )


def _mix_bundle() -> PathBundle:
    """A bounded direct path with credit repayment cash at its actual day."""
    full_horizon = 30
    n_paths = 2
    daily_cash_flows = np.zeros((n_paths, full_horizon))
    daily_cash_flows[:, :5] = -200.0
    daily_cash_flows[:, 23] = 1_000.0
    discretionary_daily = np.zeros((n_paths, full_horizon))
    discretionary_daily[:, :5] = 200.0
    return PathBundle(
        source="optimizer-test",
        seed=23,
        horizon_days=5,
        n_paths=n_paths,
        bootstrap_draw_id="optimizer-mix",
        daily_cash_flows=daily_cash_flows,
        known_income_daily=np.zeros(full_horizon),
        known_obligation_daily=np.zeros(full_horizon),
        discretionary_daily=discretionary_daily,
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


def test_reports_reason_without_any_funding_lever():
    state = _state()

    assert optimize_funding(state, _bundle(state, 5), ()) == OptimizationFailure("no_funding_levers")


def test_reports_reason_when_cvxpy_is_unavailable():
    state = _state(cards=(_credit_account("primary", 5_000.0),))
    real_import = builtins.__import__

    def unavailable_cvxpy(name, *args, **kwargs):
        if name == "cvxpy":
            raise ImportError("cvxpy unavailable")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=unavailable_cvxpy):
        assert optimize_funding(state, _bundle(state, 5), ()) == OptimizationFailure("cvxpy_unavailable")


def test_reports_reason_when_clarabel_is_unavailable(monkeypatch):
    cvxpy = _require_cvxpy()
    state = _state(cards=(_credit_account("primary", 5_000.0),))
    monkeypatch.setattr(cvxpy, "installed_solvers", lambda: [])

    assert optimize_funding(state, _bundle(state, 5), ()) == OptimizationFailure("solver_unavailable")


def test_reports_reason_when_clarabel_fails(monkeypatch):
    cvxpy = _require_cvxpy()
    state = _state(cards=(_credit_account("primary", 5_000.0),))
    monkeypatch.setattr(
        cvxpy.Problem,
        "solve",
        lambda *args, **kwargs: (_ for _ in ()).throw(cvxpy.error.SolverError("failed")),
    )

    assert optimize_funding(state, _bundle(state, 5), ()) == OptimizationFailure("solver_error")


def test_reports_reason_when_model_exceeds_documented_resource_cap(monkeypatch):
    state = _state(cards=(_credit_account("primary", 5_000.0),))
    monkeypatch.setattr(optimizer, "MAX_SCENARIO_DAYS", 1)

    assert optimize_funding(state, _bundle(state, 2, n_paths=2), ()) == OptimizationFailure("resource_limit")




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
        funding_policy=FundingPolicy(max_credit_utilization=1.0),
    )

    assert isinstance(result, OptimalPlan)
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
        funding_policy=FundingPolicy(max_credit_utilization=1.0),
    )

    assert isinstance(result, OptimalPlan)
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

    assert isinstance(result, OptimalPlan)
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
        funding_policy=FundingPolicy(max_credit_utilization=1.0),
    )

    assert isinstance(result, OptimalPlan)
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


@pytest.mark.parametrize("market_return", [None, -0.5, 0.5])
def test_optimizer_prices_todays_sale_at_execution(market_return):
    _require_cvxpy()
    holding = _taxable_holding(6_000.0, 4_800.0)
    holding = replace(holding, tax_lots=(replace(holding.tax_lots[0], purchase_date=AS_OF - timedelta(days=366)),))
    state = _state(holdings=(holding,), market_daily_return=market_return)
    obligation = (Obligation("bill", "Bill", 4_000.0, 5),)

    plan = optimize_funding(
        state,
        _bundle(state, 10),
        obligation,
        overdraft_apr=0.365,
        capital_gains_rate=0.01,
        buffer_tolerance_dollar_days=1e9,
    )
    assert isinstance(plan, OptimalPlan)
    # The long-term gain is 20% of proceeds. Gross up the sale so the
    # 1% assumed gain-tax reserve still leaves $4,000 available for the bill.
    gross = 4_000 / (1 - .2 * .01)
    assert plan.liquidation_amount == pytest.approx(gross, abs=1e-3)
    assert plan.withdrawal_net_cash == pytest.approx(4_000, abs=1e-3)
    assert plan.expected_cost == pytest.approx(gross * .2 * .01, abs=1e-4)
    assert plan.cvar_cost == pytest.approx(gross * .2 * .01, abs=1e-4)
    assert plan.cost_is_path_dependent is False


@pytest.mark.parametrize("market_return", [None, -0.01, 0.01])
def test_tax_losses_cannot_make_an_already_funded_plan_profitable(market_return):
    _require_cvxpy()
    state = _state(
        opening_cash=5_000.0,
        holdings=(_taxable_holding(6_000.0, 7_200.0),),
        market_daily_return=market_return,
    )
    plan = optimize_funding(state, _bundle(state, 10), ())

    assert isinstance(plan, OptimalPlan)
    assert plan.expected_cost == pytest.approx(0.0, abs=1e-6)
    assert plan.cvar_cost == pytest.approx(0.0, abs=1e-6)
    assert plan.liquidation_amount == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("buffer_tolerance, expected_sale", [(1e9, 4000.0), (2600.0, 4900.0)])
def test_loss_sale_keeps_only_proceeds_needed_for_cash_and_buffer_limits(
    buffer_tolerance, expected_sale
):
    _require_cvxpy()
    state = _state(holdings=(_taxable_holding(6_000.0, 7_200.0),))
    plan = optimize_funding(
        state, _bundle(state, 10), (Obligation("bill", "Bill", 4_000.0, 5),),
        operating_buffer=1000.0, buffer_tolerance_dollar_days=buffer_tolerance,
    )

    assert isinstance(plan, OptimalPlan)
    assert plan.liquidation_amount == pytest.approx(expected_sale, abs=1e-3)
    assert plan.expected_cost == pytest.approx(0.0, abs=1e-6)
    assert plan.cvar_cost == pytest.approx(0.0, abs=1e-6)
    assert plan.cash_shortfall_probability == 0.0
    # Before day-3 settlement the buffer is missed by $1,000 for two days.
    # The tighter limit leaves $600 dollar-days for the six days after the
    # bill, requiring a further $900 of cash beyond the $4,000 sale.
    dollar_days = 2000.0 + 6.0 * max(0.0, 5000.0 - plan.liquidation_amount)
    assert dollar_days <= buffer_tolerance + 1e-6
    assert plan.buffer_breach_probability == 1.0
    assert plan.dollar_days_below_buffer == pytest.approx(dollar_days)
    assert plan.buffer_tolerance_dollar_days == buffer_tolerance
    assert plan.buffer_constraint_binding is (buffer_tolerance == 2600.0)
    assert plan.evaluation_paths == 4
    assert plan.cost_coverage_target == 0.95


def test_cost_variation_is_detected_from_cash_paths_without_market_history(monkeypatch):
    _require_cvxpy()
    state = _state(holdings=(_taxable_holding(1.0, 1.0),))
    cash = np.array([[0.0] * 5, [0.0, 0.0, -100.0, -100.0, -100.0]])
    direct=PathBundle(source="direct",seed=42,horizon_days=5,n_paths=2,bootstrap_draw_id="cost-variation",
        daily_cash_flows=np.diff(np.column_stack((np.zeros(2),cash)),axis=1),
        known_income_daily=np.zeros(5),known_obligation_daily=np.zeros(5),discretionary_daily=np.zeros((2,5)))
    plan = optimize_funding(
        state, direct, (),
        operating_buffer=0.0, buffer_tolerance_dollar_days=1e9, overdraft_apr=0.365,
    )

    assert isinstance(plan, OptimalPlan)
    assert plan.cost_is_path_dependent is True
    assert plan.expected_cost == pytest.approx(0.1485, abs=1e-5)
    assert plan.cvar_cost == pytest.approx(0.297, abs=1e-5)


def test_infeasible_buffer_constraint_fails_closed():
    _require_cvxpy()
    state = _state(holdings=(_taxable_holding(1.0, 1.0),))

    result = optimize_funding(
        state,
        _bundle(state, 5),
        (Obligation("bill", "Bill", 5_000.0, 2),),
        buffer_tolerance_dollar_days=0.0,
    )

    assert result == OptimizationFailure("infeasible")


def test_already_funded_paths_need_no_shortfall_cost_or_extra_funding():
    _require_cvxpy()
    state = _state(
        opening_cash=5_000.0,
        cards=(_credit_account("primary", 1_000.0, apr=0.365),),
    )
    result = optimize_funding(state, _bundle(state, 30), (), operating_buffer=1_000.0)
    assert isinstance(result, OptimalPlan)
    assert result.expected_cost == pytest.approx(0.0, abs=1e-6)
    assert result.cvar_cost == pytest.approx(0.0, abs=1e-6)
    assert result.cash_shortfall_probability == 0.0
    assert result.credit_draw == pytest.approx(0.0, abs=1e-5)
    assert result.deferral_fraction == 0.0


@pytest.mark.parametrize("solve_time, reason", [(10.1, "solver_timeout"), (0.1, "solver_limit")])
def test_solver_limits_have_explicit_reasons(monkeypatch, solve_time, reason):
    from types import SimpleNamespace

    cvxpy = _require_cvxpy()
    state = _state(cards=(_credit_account("primary", 5000.0),))

    def limited(problem, **kwargs):
        assert kwargs["time_limit"] == 10.0
        problem._status = cvxpy.USER_LIMIT
        problem._solver_stats = SimpleNamespace(solve_time=solve_time)

    monkeypatch.setattr(cvxpy.Problem, "solve", limited)
    assert optimize_funding(state, _bundle(state, 5), ()) == OptimizationFailure(reason)


def test_invalid_solver_output_is_not_returned_as_a_plan(monkeypatch):
    cvxpy = _require_cvxpy()
    state = _state(cards=(_credit_account("primary", 5000.0),))

    def missing_values(problem, **kwargs):
        problem._status = cvxpy.OPTIMAL

    monkeypatch.setattr(cvxpy.Problem, "solve", missing_values)
    assert optimize_funding(state, _bundle(state, 5), ()) == OptimizationFailure("invalid_solution")


def test_spending_reduction_is_an_available_lever_without_assets_or_credit():
    _require_cvxpy()
    state = _state(daily_discretionary=10.0)
    result = optimize_funding(
        state, _bundle(state, 5), (Obligation("bill", "Bill", 25.0, 5),),
        operating_buffer=0.0, buffer_tolerance_dollar_days=0.0,
    )
    assert isinstance(result, OptimalPlan)
    assert result.deferral_fraction == pytest.approx(0.5, abs=1e-5)


def test_credit_draw_respects_the_actual_utilization_policy():
    _require_cvxpy()
    account = _credit_account("primary", 10_000.0)
    policy = FundingPolicy(max_credit_utilization=0.20)
    state = _state(cards=(account,))

    result = optimize_funding(
        state,
        _bundle(state, 5),
        (Obligation("bill", "Bill", 4_000.0, 3),),
        overdraft_apr=0.365,
        buffer_tolerance_dollar_days=1e9,
        funding_policy=policy,
    )

    assert result is not None
    utilization = (account.current_balance + result.credit_draw) / account.credit_limit
    assert utilization <= policy.max_credit_utilization + 1e-6
    assert result.credit_draw == pytest.approx(2_000.0, abs=1e-3)




def test_shared_scenario_pipeline_optimizes_taxable_lots_instead_of_refusing_them():
    _require_cvxpy()
    state = _state(holdings=(_multi_lot_taxable_holding(),))
    config = FundingConfig(
        settlement_days=0,
        external_transfer_days=0,
        lot_selection="fifo",
    )

    evaluation = evaluate_scenario(
        state,
        _bundle(state, 5),
        (Obligation("bill", "Bill", 6_000.0, 5),),
        coverage_target=0.95,
        operating_buffer=0.0,
        funding_config=config,
        funding_policy=FundingPolicy(max_credit_utilization=1.0),
        overdraft_apr=0.0,
        buffer_tolerance_dollar_days=0.0,
        capital_gains_rate=0.10,
    )

    assert evaluation.optimizer_reason is None
    assert evaluation.response.optimal_plan is not None


def test_tax_loss_liquidation_never_becomes_a_spendable_optimizer_credit():
    _require_cvxpy()
    state = _state(holdings=(_taxable_holding(6_000.0, 12_000.0),))
    result = optimize_funding(
        state,
        _bundle(state, 5),
        (Obligation("bill", "Bill", 1_000.0, 5),),
        operating_buffer=0.0,
        overdraft_apr=0.0,
        buffer_tolerance_dollar_days=0.0,
        capital_gains_rate=0.20,
        funding_config=FundingConfig(settlement_days=0, external_transfer_days=0),
    )

    assert result is not None
    assert result.liquidation_amount >= 1_000.0 - 1e-3
    assert result.expected_cost == pytest.approx(0.0, abs=2e-3)
    assert result.cvar_cost >= -1e-6
