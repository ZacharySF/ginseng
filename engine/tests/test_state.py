"""Funding-class and ledger invariants (spec sections 7-11; section 74:
Accounting, Future Obligation, Internal Transfer).

Every ledger here is hand-built from round dollar magnitudes so the expected
balances are exact, observable arithmetic rather than formulas re-derived
from the implementation.
"""

from datetime import date, timedelta

import numpy as np

from ginseng.generate import DEFAULT_SEED, acceptance_report, generate_persona

from ginseng.state import (
    FinancialState,
    Holding,
    TaxLot,
    Transaction,
    TransactionType,
)

AS_OF = date(2026, 8, 31)


def _txn(days_back, txn_type, amount, label):
    return Transaction(AS_OF - timedelta(days=days_back), txn_type, amount, label)


def _state(transactions, holdings=()):
    return FinancialState(
        as_of=AS_OF,
        transactions=tuple(transactions),
        fixed_income_schedule=(),
        fixed_obligations=(),
        planned_discretionary_events=(),
        credit_accounts=(),
        holdings=tuple(holdings),
        operating_buffer=1000.0,
        coverage_target=0.95,
        forecast_horizon=30,
    )


def test_derived_balance_equals_initial_balance_plus_net_transaction_flows():
    # Initial balance 5000; settled flows: +300 retainer, +1200 client,
    # +250 investment sale, -180 groceries, -90 dining, -260 irregular,
    # -110 card payment, -600 investment buy = +510 net.
    # The 120 card purchase and the 2000 future repair are not settled cash.
    state = _state(
        [
            _txn(30, TransactionType.TRANSFER, 5000.0, "Opening balance"),
            _txn(29, TransactionType.INCOME_FIXED, 300.0, "Retainer"),
            _txn(28, TransactionType.INCOME_VARIABLE, 1200.0, "Client payment"),
            _txn(27, TransactionType.EXPENSE_ESSENTIAL_VARIABLE, 180.0, "Groceries"),
            _txn(26, TransactionType.EXPENSE_DISCRETIONARY_VARIABLE, 90.0, "Dining"),
            _txn(25, TransactionType.EXPENSE_IRREGULAR, 260.0, "Vet bill"),
            _txn(24, TransactionType.CREDIT_PAYMENT, 110.0, "Card payment"),
            _txn(23, TransactionType.INVESTMENT_BUY, 600.0, "Buy VTI"),
            _txn(22, TransactionType.CREDIT_PURCHASE, 120.0, "Card purchase"),
            _txn(21, TransactionType.INVESTMENT_SELL, 250.0, "Sell VTI"),
            _txn(-3, TransactionType.FUTURE_OBLIGATION, 2000.0, "Future repair"),
        ]
    )
    assert state.immediate_funding == 5000.0 + 510.0


def test_future_bill_and_card_purchases_do_not_move_todays_settled_cash():
    settled = [
        _txn(10, TransactionType.TRANSFER, 2000.0, "Opening balance"),
        _txn(9, TransactionType.INCOME_VARIABLE, 500.0, "Client payment"),
    ]
    base = _state(settled)
    with_future_bill = _state(
        settled
        + [
            _txn(-3, TransactionType.FUTURE_OBLIGATION, 4500.0, "Emergency vehicle repair"),
            _txn(5, TransactionType.CREDIT_PURCHASE, 120.0, "Card purchase"),
        ]
    )
    assert base.immediate_funding == 2500.0
    assert with_future_bill.immediate_funding == base.immediate_funding


def test_transfer_between_immediate_funding_accounts_preserves_the_total():
    before = _state([_txn(10, TransactionType.TRANSFER, 4000.0, "Opening balance")])
    after = _state(
        [
            _txn(10, TransactionType.TRANSFER, 4000.0, "Opening balance"),
            _txn(1, TransactionType.TRANSFER, -800.0, "Checking to savings"),
            _txn(1, TransactionType.TRANSFER, 800.0, "Savings from checking"),
        ]
    )
    assert before.immediate_funding == 4000.0
    assert after.immediate_funding == before.immediate_funding


def test_funding_classes_partition_holdings_by_account():
    taxable = Holding(
        "VTI",
        "taxable",
        100.0,
        (TaxLot("vti-1", "VTI", 10.0, 80.0, date(2026, 1, 5)),),
    )
    retirement = Holding(
        "TARGET2055",
        "retirement",
        50.0,
        (TaxLot("ret-1", "TARGET2055", 20.0, 40.0, date(2025, 6, 1)),),
    )
    state = _state(
        [_txn(5, TransactionType.TRANSFER, 1500.0, "Opening balance")],
        holdings=(taxable, retirement),
    )
    assert state.immediate_funding == 1500.0
    assert state.marketable_backup_capital == 1000.0  # the retirement holding is excluded
    assert state.restricted_capital == 1000.0  # the taxable holding is excluded


def test_daily_series_is_dense_zero_filled_and_sums_same_day_activity():
    state = _state(
        [
            _txn(30, TransactionType.TRANSFER, 1000.0, "Opening balance"),
            _txn(10, TransactionType.INCOME_VARIABLE, 200.0, "Client payment"),
            _txn(10, TransactionType.INCOME_VARIABLE, 300.0, "Client payment"),
            _txn(2, TransactionType.INCOME_VARIABLE, 150.0, "Client payment"),
        ]
    )
    series = state.daily_series(TransactionType.INCOME_VARIABLE, AS_OF - timedelta(days=12), AS_OF)
    # 13 calendar days, zero-filled wherever no payment landed.
    assert len(series) == 13
    nonzero = set(np.nonzero(series.to_numpy())[0])
    assert nonzero == {2, 10}  # 10 days back and 2 days back
    assert series.iloc[2] == 500.0  # two same-day payments aggregate
    assert series.iloc[10] == 150.0
    assert float(series.sum()) == 650.0


def test_generate_persona_is_deterministic_in_its_seed():
    first = generate_persona(DEFAULT_SEED)
    second = generate_persona(DEFAULT_SEED)
    assert len(first.transactions) == len(second.transactions)
    assert first.transactions == second.transactions
    assert first.immediate_funding == second.immediate_funding
    assert first.holdings == second.holdings
    assert first.credit_accounts == second.credit_accounts
    assert acceptance_report(first, n_paths=300) == acceptance_report(second, n_paths=300)
