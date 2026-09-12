"""Liquidity-metric invariants (spec sections 23-27, 32; section 74: RLR,
Coverage-Target, Buffer, and Funding monotonicity, Running-Minimum
semantics) plus the section 36 generator acceptance conditions.

Hand-constructed matrices use round magnitudes so expected metrics are exact
arithmetic; pipeline tests assert the invariants on real simulated draws.
"""

import numpy as np
import pytest

from ginseng.generate import acceptance_report, generate_persona
from ginseng.metrics import (
    coverage_at_funding,
    coverage_curve,
    required_liquidity_per_path,
    required_liquidity_reserve,
    severity_metrics,
)
from ginseng.simulate import cash_paths, draw_bundle
from ginseng.state import Obligation

from tests.test_simulate import make_history_state


BUFFER = 1000.0


def _simulated_required(state, bundle, obligations=(), buffer=BUFFER):
    return required_liquidity_per_path(cash_paths(state, bundle, obligations), buffer)


# --- Section 74: RLR monotonicity ---


def test_increasing_a_future_expense_never_decreases_the_reserve():
    state = make_history_state()
    bundle = draw_bundle(state, horizon_days=30, n_paths=240, seed=11, mean_block_length=10)
    reserves = [
        required_liquidity_reserve(
            _simulated_required(state, bundle, (Obligation("bill", "Future bill", amount, 8),)),
            0.95,
        )
        for amount in (0.0, 400.0, 1200.0, 2600.0)
    ]
    assert all(later >= earlier for earlier, later in zip(reserves, reserves[1:]))


def test_a_larger_expense_strictly_raises_the_requirement_when_it_binds():
    # The path's minimum sits on day 3, where the extra expense lands, so the
    # requirement must absorb the full amount.
    path = np.array([[100.0, -100.0, -1500.0, -1400.0, 1200.0]])
    expensive = path.copy()
    expensive[:, 2:] -= 800.0  # an extra $800 bill due on day 3
    before = required_liquidity_per_path(path, BUFFER)
    after = required_liquidity_per_path(expensive, BUFFER)
    assert before[0] == 2500.0
    assert after[0] == before[0] + 800.0


# --- Section 74: Coverage-target monotonicity ---


def test_reserve_is_strictly_monotone_in_the_coverage_target_on_known_values():
    required = np.array([0.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0])
    targets = (0.1, 0.25, 0.5, 0.75, 0.9, 1.0)
    reserves = [required_liquidity_reserve(required, q) for q in targets]
    assert reserves == pytest.approx([125.0, 312.5, 750.0, 1750.0, 3000.0, 4000.0])
    assert all(later > earlier for earlier, later in zip(reserves, reserves[1:]))


def test_simulated_reserve_is_monotone_in_the_coverage_target():
    state = make_history_state()
    bundle = draw_bundle(state, horizon_days=30, n_paths=300, seed=21, mean_block_length=10)
    required = _simulated_required(state, bundle)
    assert float(np.max(required)) > float(np.min(required))  # the paths genuinely disagree
    reserves = [required_liquidity_reserve(required, q) for q in (0.5, 0.75, 0.9, 0.95, 0.99)]
    assert all(later >= earlier for earlier, later in zip(reserves, reserves[1:]))


# --- Section 74: Buffer monotonicity ---


def test_reserve_shifts_one_for_one_with_the_buffer_while_it_binds():
    # The path bottoms out at -2000, so every buffer dollar adds a required
    # dollar: R(b) = b + 2000.
    path = np.array([[100.0, -50.0, -2000.0, -1800.0, 500.0, 1500.0]])
    requirements = {
        buffer: required_liquidity_per_path(path, buffer)[0]
        for buffer in (500.0, 1000.0, 1500.0, 2000.0)
    }
    assert requirements == {500.0: 2500.0, 1000.0: 3000.0, 1500.0: 3500.0, 2000.0: 4000.0}


def test_simulated_reserve_is_monotone_in_the_operating_buffer():
    state = make_history_state()
    bundle = draw_bundle(state, horizon_days=30, n_paths=240, seed=31, mean_block_length=10)
    reserves = [
        required_liquidity_reserve(_simulated_required(state, bundle, buffer=buffer), 0.9)
        for buffer in (0.0, 500.0, 1000.0, 2000.0)
    ]
    assert all(later >= earlier for earlier, later in zip(reserves, reserves[1:]))


# --- Section 74: Funding monotonicity ---


def test_more_funding_never_reduces_coverage():
    required = np.array([1000.0, 2000.0, 3000.0])
    assert coverage_at_funding(required, 999.0) == 0.0  # below the safest path
    assert coverage_at_funding(required, 1500.0) == pytest.approx(1 / 3)
    assert coverage_at_funding(required, 2500.0) == pytest.approx(2 / 3)
    assert coverage_at_funding(required, 2500.0) > coverage_at_funding(required, 1500.0)
    assert coverage_at_funding(required, 3000.0) == 1.0  # covers even the worst path


def test_simulated_coverage_is_monotone_in_funding():
    state = make_history_state()
    bundle = draw_bundle(state, horizon_days=30, n_paths=240, seed=41, mean_block_length=10)
    required = _simulated_required(state, bundle)
    grid = np.linspace(float(required.min()) - 100.0, float(required.max()) + 100.0, 25)
    coverages = [coverage_at_funding(required, float(f)) for f in grid]
    assert coverages[0] == 0.0
    assert coverages[-1] == 1.0
    assert all(later >= earlier for earlier, later in zip(coverages, coverages[1:]))


def test_coverage_curve_is_monotone_and_spans_zero_funding_to_beyond_today():
    state = make_history_state()
    bundle = draw_bundle(state, horizon_days=30, n_paths=240, seed=43, mean_block_length=10)
    required = _simulated_required(state, bundle)
    curve = coverage_curve(required, state.immediate_funding)
    fundings = [point["funding"] for point in curve]
    coverages = [point["coverage"] for point in curve]
    assert len(curve) >= 2
    assert fundings[0] == 0.0
    assert max(fundings) >= state.immediate_funding
    assert all(later > earlier for earlier, later in zip(fundings, fundings[1:]))
    assert all(later >= earlier for earlier, later in zip(coverages, coverages[1:]))
    assert all(0.0 <= coverage <= 1.0 for coverage in coverages)


# --- Section 74: Running-minimum semantics ---


def _two_path_matrix():
    # Path 1 dips to -2000 on day 3 yet finishes at +1500; path 2 stays above
    # the buffer every day.
    return np.array(
        [
            [100.0, -50.0, -2000.0, -1800.0, 500.0, 1500.0],
            [1200.0, 1300.0, 1400.0, 1500.0, 1600.0, 1700.0],
        ]
    )


def test_a_mid_horizon_dip_that_recovers_still_requires_liquidity():
    required = required_liquidity_per_path(_two_path_matrix(), BUFFER)
    assert required[0] == 3000.0  # the running minimum, not the recovered final day
    assert required[1] == 0.0  # a path that never nears the buffer requires nothing
    assert required_liquidity_reserve(required, 0.5) == pytest.approx(1500.0)
    assert coverage_at_funding(required, 1500.0) == pytest.approx(0.5)


def test_severity_reads_the_path_minimum_not_the_ending_balance():
    severity = severity_metrics(_two_path_matrix(), 1500.0, BUFFER)
    # Only the dipping path ever goes below zero: available cash bottoms at
    # 1500 - 2000 = -500 on day 3, then recovers.
    assert severity["cash_shortfall_probability"] == pytest.approx(0.5)
    assert severity["avg_cash_deficit_when_short"] == pytest.approx(500.0)
    # The dipping path spends days 3-4 below the buffer (deficits 1500 + 1300);
    # the healthy path spends none. Mean over paths: 2800 / 2.
    assert severity["dollar_days_below_buffer"] == pytest.approx(1400.0)


# --- Section 36: generator acceptance ---


def test_generated_persona_meets_the_section_36_acceptance_conditions():
    report = acceptance_report(generate_persona())
    assert report["meets_acceptance"] is True

    before = report["before"]
    # Before the shock: no funding gap and cash-shortfall risk under 2%.
    assert before["funding_gap"] == 0.0
    assert before["cash_shortfall_probability"] < 0.02
    assert before["required_liquidity_reserve"] <= report["immediate_funding"]

    # After the canonical $4,500-due-in-3-days repair: a real but coverable gap.
    after = report["after"]
    assert 1000.0 <= after["funding_gap"] <= 3000.0
    assert after["cash_shortfall_probability"] > 0.0
    assert report["marketable_backup_capital"] >= after["funding_gap"]
    assert report["available_credit"] > 0.0
