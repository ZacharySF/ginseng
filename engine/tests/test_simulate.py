"""Forecast invariants (spec sections 12, 16-21; section 74: Future
Obligation, Scenario Pairing, Horizon).

`make_history_state` is a small handcrafted persona: fixed magnitudes on a
60-day window, no RNG, so every forecast number is explainable by hand.
Settled cash is exactly 3000 opening + 20 x 120 client income
- 15 x 60 essential spending - 12 x 40 discretionary spending = 4020.
"""

from datetime import date, timedelta

import numpy as np

from ginseng.simulate import cash_paths, draw_bundle, known_flows
from ginseng.state import FinancialState, Obligation, Transaction, TransactionType

AS_OF = date(2026, 8, 31)
HISTORY_DAYS = 60


def make_history_state() -> FinancialState:
    transactions = [
        Transaction(
            AS_OF - timedelta(days=HISTORY_DAYS - 1),
            TransactionType.TRANSFER,
            3000.0,
            "Opening balance",
        )
    ]
    for i in range(HISTORY_DAYS):
        day = AS_OF - timedelta(days=HISTORY_DAYS - 1 - i)
        if i % 3 == 0:
            transactions.append(
                Transaction(day, TransactionType.INCOME_VARIABLE, 120.0, "Client payment")
            )
        if i % 4 == 1:
            transactions.append(
                Transaction(day, TransactionType.EXPENSE_ESSENTIAL_VARIABLE, 60.0, "Groceries")
            )
        if i % 5 == 2:
            transactions.append(
                Transaction(day, TransactionType.EXPENSE_DISCRETIONARY_VARIABLE, 40.0, "Dining")
            )
    return FinancialState(
        as_of=AS_OF,
        transactions=tuple(transactions),
        fixed_income_schedule=(
            Obligation(
                "retainer",
                "Monthly retainer",
                350.0,
                2,
                TransactionType.INCOME_FIXED,
                30,
            ),
        ),
        fixed_obligations=(
            Obligation("rent", "Rent", 1200.0, 5, TransactionType.EXPENSE_FIXED, 30),
            Obligation("insurance", "Insurance", 140.0, 9, TransactionType.EXPENSE_FIXED, 30),
        ),
        planned_discretionary_events=(),
        credit_accounts=(),
        holdings=(),
        operating_buffer=1000.0,
        coverage_target=0.95,
        forecast_horizon=30,
    )


def test_future_obligation_changes_the_forecast_but_not_todays_cash():
    state = make_history_state()
    bundle = draw_bundle(state, horizon_days=30, n_paths=240, seed=7, mean_block_length=10)
    baseline = cash_paths(state, bundle)
    assert baseline.shape == (240, 30)

    repair = Obligation("repair", "Emergency vehicle repair", 800.0, 6)
    shocked = cash_paths(state, bundle, (repair,))

    # Same draws, so days before the bill is due are untouched...
    assert np.array_equal(baseline[:, :5], shocked[:, :5])
    # ...and from the due day onward every path is lower by exactly the bill.
    np.testing.assert_allclose(baseline[:, 5:] - shocked[:, 5:], 800.0, rtol=0.0, atol=1e-6)
    # The bill lives in the forecast inputs, never in the settled-cash ledger.
    assert state.immediate_funding == 4020.0


def test_obligation_beyond_the_horizon_never_enters_the_forecast():
    state = make_history_state()
    bundle = draw_bundle(state, horizon_days=30, n_paths=200, seed=13, mean_block_length=10)
    baseline = cash_paths(state, bundle)
    beyond = cash_paths(
        state, bundle, (Obligation("far", "Bill due far beyond the horizon", 5000.0, 45),)
    )
    assert np.array_equal(baseline, beyond)


def test_obligation_due_today_lands_on_the_first_forecast_day():
    state = make_history_state()
    base_income, base_outflow = known_flows(state, (), 30)
    income, outflow = known_flows(
        state, (Obligation("today", "Bill due today", 800.0, 0),), 30
    )
    assert base_outflow[0] == 0.0  # nothing lands on day 1 without the bill
    assert outflow[0] == 800.0
    np.testing.assert_allclose(outflow - base_outflow, 800.0, rtol=0.0, atol=1e-9)
    assert np.array_equal(income, base_income)  # the bill never touches income


def test_recurring_obligations_land_on_every_recurrence_inside_the_horizon():
    state = make_history_state()
    income, outflow = known_flows(state, (), 65)
    # Rent (1200, due day 5) repeats on days 5, 35, 65; insurance (140, day 9)
    # on days 9 and 39; retainer income (350, day 2) on days 2, 32, 62.
    assert outflow[3] == 0.0
    assert outflow[4] == 1200.0  # day 5: first rent
    assert outflow[7] == 1200.0
    assert outflow[8] == 1340.0  # day 9: insurance lands
    assert outflow[33] == 1340.0
    assert outflow[34] == 2540.0  # day 35: second rent
    assert outflow[37] == 2540.0
    assert outflow[38] == 2680.0  # day 39: second insurance
    assert outflow[64] == 3880.0  # day 65: third rent
    assert income[1] == 350.0  # day 2: first retainer
    assert income[31] == 700.0  # day 32
    assert income[61] == 1050.0  # day 62
    assert income[62] == 1050.0


def test_same_seed_reproduces_the_same_draw_bundle():
    state = make_history_state()
    first = draw_bundle(state, horizon_days=30, n_paths=240, seed=42, mean_block_length=10)
    second = draw_bundle(state, horizon_days=30, n_paths=240, seed=42, mean_block_length=10)
    assert np.array_equal(first.index_matrix, second.index_matrix)
    assert first.bootstrap_draw_id == second.bootstrap_draw_id
    assert (
        first.seed,
        first.horizon_days,
        first.n_paths,
        first.mean_block_length,
        first.history_length,
    ) == (
        second.seed,
        second.horizon_days,
        second.n_paths,
        second.mean_block_length,
        second.history_length,
    )


def test_a_different_seed_produces_a_different_draw_id():
    first = draw_bundle(make_history_state(), horizon_days=30, n_paths=240, seed=1, mean_block_length=10)
    second = draw_bundle(make_history_state(), horizon_days=30, n_paths=240, seed=2, mean_block_length=10)
    assert first.bootstrap_draw_id != second.bootstrap_draw_id
    assert not np.array_equal(first.index_matrix, second.index_matrix)


def test_cash_paths_are_deterministic_for_a_fixed_state_and_bundle():
    state = make_history_state()
    bundle = draw_bundle(state, horizon_days=30, n_paths=240, seed=99, mean_block_length=10)
    assert np.array_equal(cash_paths(state, bundle), cash_paths(state, bundle))
    shocked = (Obligation("repair", "Emergency vehicle repair", 800.0, 6),)
    assert np.array_equal(cash_paths(state, bundle, shocked), cash_paths(state, bundle, shocked))


def test_block_length_estimator_falls_back_when_arch_rejects_series(monkeypatch):
    import arch.bootstrap

    from ginseng.simulate import estimate_mean_block_length

    def reject_series(_):
        raise ValueError("series is degenerate")

    monkeypatch.setattr(arch.bootstrap, "optimal_block_length", reject_series)
    assert estimate_mean_block_length(np.array([120.0, 110.0, 90.0, 80.0])) == 7


def test_data_estimated_block_length_records_when_the_upper_bound_applies(monkeypatch):
    import arch.bootstrap
    import pandas as pd

    def oversized_estimate(_):
        return pd.DataFrame({"b_sb": [99.0]})

    monkeypatch.setattr(arch.bootstrap, "optimal_block_length", oversized_estimate)
    bundle = draw_bundle(make_history_state(), horizon_days=30, n_paths=20, seed=7)
    assert bundle.mean_block_length == 28
    assert bundle.mean_block_length_was_clipped is True
