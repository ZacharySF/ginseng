from dataclasses import replace
from datetime import timedelta

import numpy as np
import pytest

from ginseng.calibration import empirical_crps, pinball_loss, randomized_pit, training_state, walk_forward, formal_tests, expected_shortfall_test
from ginseng.generate import generate_persona
from ginseng.simulate import draw_bundle, cash_paths
from ginseng.state import Transaction, TransactionType


def test_scoring_rules_have_hand_computed_values():
    assert pinball_loss(100, 120, .95) == pytest.approx(19)
    assert pinball_loss(100, 80, .95) == pytest.approx(1)
    # E|X-5| = 5, E|X-X'|/2 = 2.5.
    assert empirical_crps(np.array([0., 10.]), 5.) == 2.5
    assert empirical_crps(np.array([5., 5.]), 5.) == 0


def test_randomized_pit_spreads_zero_ties_only_inside_the_atom():
    rng = np.random.default_rng(17)
    predicted = np.array([0., 0., 0., 10.])
    draws = np.array([randomized_pit(predicted, 0, rng) for _ in range(1000)])
    assert draws.min() >= 0 and draws.max() <= .75
    assert draws.std() > .15
    assert randomized_pit(predicted, 5, rng) == .75


def test_training_and_predictions_cannot_read_future_transactions_or_holdings():
    state = generate_persona()
    cutoff = state.as_of - timedelta(days=60)
    poisoned = replace(state, transactions=state.transactions + (
        Transaction(cutoff + timedelta(days=1), TransactionType.INCOME_FIXED, 999999., "Monthly retainer"),))
    a = training_state(state, cutoff, 30)
    b = training_state(poisoned, cutoff, 30)
    assert a == b
    assert not a.holdings and not a.asset_daily_returns
    assert all(t.txn_date <= cutoff for t in a.transactions)
    bundle = draw_bundle(a, 30, 100, 5)
    np.testing.assert_array_equal(cash_paths(a, bundle), cash_paths(b, bundle))


def test_walk_forward_counts_only_nonoverlapping_windows_after_training():
    state = generate_persona()
    report = walk_forward(state, 30, 100, 19, .95, 1000)
    assert report["primary"]["windows"] == 12
    assert report["descriptive_windows"] > 12
    assert report["expected_tail_failures"] == pytest.approx(.6)
    sample = [r for r in report["windows"] if r["in_primary_sample"]]
    assert all(a["end"] < b["start"] for a,b in zip(sample, sample[1:]))
    assert all(r["training_cutoff"] < r["start"] for r in sample)
    assert sum(report["pit"]["counts"]) == 12
    assert report["primary"]["interval"]["high"] - report["primary"]["interval"]["low"] > .15
    assert all(test["status"] == "unavailable" for test in report["formal_tests"].values())
    assert report == walk_forward(state, 30, 100, 19, .95, 1000)


def test_formal_test_screening_never_prints_an_underpowered_pass():
    rows = [{"covered": True}] * 24
    assert all(item["status"] == "unavailable" for item in formal_tests(rows, .95).values())
    # Enough expected observations for the count test, but not a PASS label.
    rows = [{"covered": i % 20 != 0} for i in range(200)]
    result = formal_tests(rows, .95)
    assert result["kupiec"]["p_value"] == pytest.approx(1)
    assert result["christoffersen"]["status"] == "unavailable"  # sparse transitions


def test_expected_shortfall_test_handles_atoms_and_detects_underestimated_severity():
    predictions = [np.array([0., 0., 100., 100.])] * 120
    rows = [{"covered": i % 2 == 0, "realized_required": 0. if i % 2 == 0 else 100.} for i in range(120)]
    calibrated = expected_shortfall_test(rows, predictions, .5, 17)
    assert calibrated['status'] == 'computed'
    assert calibrated['statistic'] == pytest.approx(0)
    assert .05 < calibrated['p_value'] < .95
    severe = expected_shortfall_test([{"covered":False, "realized_required":300.}] * 120, predictions, .5, 17)
    assert severe['p_value'] < .01
    assert severe['statistic'] < 0
    assert expected_shortfall_test(rows[:12], predictions[:12], .95, 17)['status'] == 'unavailable'
