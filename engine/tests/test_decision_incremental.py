"""An edit sequence through real metrics/funding callers vs fresh contexts."""

from dataclasses import asdict, replace

import numpy as np
from ginseng.decision_artifact import numerical_differences
from ginseng.execution import EvaluationContext
from ginseng.funding import PlanKind, PlanSpec, evaluate_plan
from ginseng.metrics import compute_scenario_metrics
from ginseng.sampling import prepare_history, sample_bundle
from ginseng.simulate import cash_paths
from ginseng.state import Obligation, Transaction, TransactionType

from tests.test_optimizer import _state, _taxable_holding


def test_incremental_actual_callers_full_recompute_after_edit_sequence():
    state = _state(
        opening_cash=200,
        holdings=(_taxable_holding(1000, 500),),
        daily_discretionary=10,
    )
    bills = (Obligation("bill", "Bill", 100, 5),)
    cases = []
    for edit in (
        "base",
        "coverage",
        "buffer",
        "opening",
        "bill_amount",
        "bill_date",
        "weights",
        "history",
        "model",
        "holdings",
        "visible",
        "material",
    ):
        cases.append((edit, state, bills))

    def execute(edit, context):
        s = state
        b = bills
        q = 0.95
        buffer = 20
        weights = None
        visible = 14
        material = 30
        block = 14
        if edit == "coverage":
            q = 0.8
        if edit == "buffer":
            buffer = 50
        if edit == "opening":
            s = replace(
                s,
                transactions=s.transactions
                + (
                    Transaction(
                        s.as_of, TransactionType.TRANSFER, 50, "Cash adjustment"
                    ),
                ),
            )
        if edit == "bill_amount":
            b = (replace(b[0], amount=200),)
        if edit == "bill_date":
            b = (replace(b[0], due_in_days=7),)
        if edit == "weights":
            weights = np.arange(16, dtype=float)
        if edit == "history":
            s = replace(
                s,
                transactions=s.transactions
                + (
                    Transaction(
                        s.transactions[-1].txn_date,
                        TransactionType.INCOME_VARIABLE,
                        70,
                        "Edited synthetic record",
                    ),
                ),
            )
        if edit == "model":
            block = 7
        if edit == "holdings":
            s = replace(s, holdings=(_taxable_holding(2000, 100),))
        if edit == "visible":
            visible = 30
        if edit == "material":
            material = 45
        history = prepare_history(s, block)
        bundle = sample_bundle(history, visible, 16, 7, "mc", material)
        before = cash_paths(s, bundle, b).copy()
        metrics = compute_scenario_metrics(s, bundle, b, q, buffer, weights)
        spec = PlanSpec("sale", "Sale", PlanKind.LIQUIDATE, liquidation_target=100)
        funded = evaluate_plan(s, bundle, b, spec, weights, operating_buffer=buffer)
        np.testing.assert_array_equal(before, cash_paths(s, bundle, b))
        return dict(metrics=asdict(metrics), funded=asdict(funded))

    with EvaluationContext() as reused:
        for edit, _, _ in cases:
            incremental = execute(edit, reused)
            with EvaluationContext() as fresh:
                full = execute(edit, fresh)
            assert not numerical_differences(incremental, full), edit
        assert reused.counters["cache_hits"] > 0
