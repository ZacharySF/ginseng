"""Funding comparisons must include the same future days for every candidate."""

from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest

from ginseng.funding import (
    PlanKind,
    PlanSpec,
    comparison_draw_bundle,
    evaluate_plan,
)
from ginseng.simulate import draw_bundle
from ginseng.state import CreditAccount, FinancialState, Holding, Obligation, TaxLot, Transaction, TransactionType


@pytest.fixture
def comparison_state():
    as_of = date(2026, 9, 11)
    return FinancialState(
        as_of=as_of,
        transactions=(
            Transaction(as_of - timedelta(days=60), TransactionType.TRANSFER, 100.0, "Cash"),
        ),
        fixed_income_schedule=(),
        fixed_obligations=(),
        planned_discretionary_events=(),
        credit_accounts=(
            CreditAccount(
                account_id="card",
                credit_limit=1000.0,
                current_balance=0.0,
                purchase_apr=0.0,
                statement_close_day=25,
                payment_due_day=16,
                grace_period_eligible=True,
                minimum_payment=25.0,
            ),
        ),
        holdings=(
            Holding("TEST", "taxable", 100.0, (TaxLot("lot", "TEST", 10.0, 100.0, as_of),)),
        ),
        operating_buffer=0.0,
        coverage_target=0.95,
        forecast_horizon=30,
    )


def _specs():
    return [
        PlanSpec("credit", "Credit", PlanKind.CREDIT, credit_account_id="card", credit_draw=50.0),
        PlanSpec("sell", "Sell", PlanKind.LIQUIDATE, liquidation_target=50.0),
        PlanSpec(
            "hybrid", "Hybrid", PlanKind.HYBRID,
            credit_account_id="card", credit_draw=25.0, liquidation_target=25.0,
        ),
        PlanSpec("wait", "Wait", PlanKind.PROTECTIVE),
    ]


def test_every_plan_faces_a_bill_after_the_requested_chart(comparison_state):
    bundle = draw_bundle(comparison_state, horizon_days=30, n_paths=12, seed=4, mean_block_length=7)
    specs = _specs()
    # The new card purchase is due on day 35. The same household also has
    # a day-36 bill: a 30-day evaluation would hide it from non-credit plans.
    obligations = (Obligation("late-bill", "Late bill", 200.0, 36),)
    short_window = evaluate_plan(comparison_state, bundle, obligations, specs[-1])
    assert short_window.cash_shortfall_probability == 0.0

    shared = comparison_draw_bundle(comparison_state, bundle, specs)
    results = [evaluate_plan(comparison_state, shared, obligations, spec) for spec in specs]

    assert {result.evaluation_horizon_days for result in results} == {38}
    assert {result.evaluation_draw_id for result in results} == {shared.bootstrap_draw_id}
    assert all(result.cash_shortfall_probability == 1.0 for result in results)
    # The credit repayment is included too: drawing $50 cannot erase debt.
    assert results[0].avg_cash_deficit_when_short == pytest.approx(100.0)
    assert results[1].avg_cash_deficit_when_short == pytest.approx(50.0)


def test_latest_settlement_and_trailing_days_extend_every_plan(comparison_state):
    bundle = draw_bundle(comparison_state, horizon_days=30, n_paths=12, seed=4, mean_block_length=7)
    original_indices = bundle.index_matrix.copy()
    specs = _specs()
    specs[1] = replace(specs[1], settlement_days=40, external_transfer_days=2, trailing_days=4)

    shared = comparison_draw_bundle(comparison_state, bundle, specs)
    reversed_shared = comparison_draw_bundle(comparison_state, bundle, list(reversed(specs)))
    repeated_shared = comparison_draw_bundle(comparison_state, shared, specs)

    assert shared.horizon_days == 46
    assert reversed_shared.bootstrap_draw_id == shared.bootstrap_draw_id
    assert repeated_shared is shared  # No additional trailing window is appended.
    np.testing.assert_array_equal(shared.index_matrix[:, :30], original_indices)
    np.testing.assert_array_equal(bundle.index_matrix, original_indices)
    results = [evaluate_plan(comparison_state, shared, (), spec) for spec in specs]
    assert {result.evaluation_horizon_days for result in results} == {46}
    assert {result.evaluation_draw_id for result in results} == {shared.bootstrap_draw_id}


def test_no_extension_when_requested_window_already_covers_every_plan(comparison_state):
    bundle = draw_bundle(comparison_state, horizon_days=60, n_paths=12, seed=4, mean_block_length=7)
    assert comparison_draw_bundle(comparison_state, bundle, _specs()) is bundle
    assert comparison_draw_bundle(comparison_state, bundle, []) is bundle
