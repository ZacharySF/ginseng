from dataclasses import replace

import numpy as np
import pytest

from ginseng.risk import quantile, cvar, tail_probabilities, concentration, weight_hash
from ginseng.stress import entropy_project, DroughtView, scenario_weights
from ginseng.metrics import required_liquidity_reserve, coverage_at_funding, severity_metrics
from ginseng.provenance import fingerprint
from ginseng.generate import generate_persona
from ginseng.simulate import draw_bundle, cash_paths


def test_discrete_reserve_attains_coverage_including_a_zero_atom():
    losses = np.array([0., 0., 100., 500.])
    weights = np.array([.4, .3, .2, .1])
    assert quantile(losses, .7, weights) == 0
    assert quantile(losses, .71, weights) == 100
    assert quantile(losses, .95, weights) == 500
    for q in (.05, .5, .7, .71, .95, 1.):
        assert coverage_at_funding(losses, quantile(losses, q, weights), weights) >= q - 1e-12


def test_fractional_tail_uses_exact_mass_and_splits_ties_without_index_bias():
    losses = np.array([0., 0., 10.])
    weights = np.array([.48, .48, .04])
    # Worst 5% = 4% at $10 plus 1% at $0, hence $8, not $10.
    assert cvar(losses, .95, weights) == pytest.approx(8.)
    np.testing.assert_allclose(tail_probabilities(losses, .95, weights), [.1, .1, .8])
    assert cvar(np.array([1., 9., 1000.]), 1, np.array([.5, .5, 0])) == 9
    assert concentration(losses, .95, weights)["ens_tail"] < 2


def test_a_certain_bill_can_correctly_remain_additive_after_reweighting():
    losses = np.array([100., 500., 3000.])
    weights = np.array([.4, .4, .2])
    assert required_liquidity_reserve(losses + 4500, .95, weights) - required_liquidity_reserve(losses, .95, weights) == 4500


def test_entropy_projection_changes_only_group_mass_and_preserves_prior_ratios():
    prior = np.array([.1, .2, .3, .4])
    event = np.array([True, True, False, False])
    weights = entropy_project(event, .6, prior)
    assert weights[event].sum() == pytest.approx(.6)
    assert weights.sum() == pytest.approx(1)
    assert weights[0] / weights[1] == pytest.approx(prior[0] / prior[1])
    assert weights[2] / weights[3] == pytest.approx(prior[2] / prior[3])
    with pytest.raises(ValueError, match="no supporting"):
        entropy_project(np.zeros(4, dtype=bool), .1)


def test_all_event_stress_rejects_missing_complement_despite_rounding():
    # Seven uniform weights do not sum to exactly one in floating point.
    with pytest.raises(ValueError, match="no supporting"):
        entropy_project(np.ones(7, dtype=bool), .3)
    assert entropy_project(np.ones(7, dtype=bool), 1).sum() == pytest.approx(1)


def test_weighted_severity_respects_rare_large_losses():
    result = severity_metrics(np.array([[-100., -50.], [10., 20.]]), 0., 0., np.array([.1, .9]))
    assert result["cash_shortfall_probability"] == pytest.approx(.1)
    assert result["avg_cash_deficit_when_short"] == 100
    assert result["dollar_days_below_buffer"] == pytest.approx(15.)


def test_fingerprints_distinguish_weights_views_configuration_and_actual_inputs():
    state = generate_persona()
    bundle = draw_bundle(state, 30, 100, 12)
    paths = cash_paths(state, bundle)
    before_indices = bundle.index_matrix.copy()
    first_weights, _ = scenario_weights(state, bundle, None)
    view = DroughtView(.3)
    stressed_weights, meta = scenario_weights(state, bundle, view)
    assert meta["status"] == "active"
    a = fingerprint(state, bundle, (), first_weights, None, {"q": .95}, paths)
    b = fingerprint(state, bundle, (), stressed_weights, view, {"q": .95}, paths)
    assert a["path_hash"] == b["path_hash"]
    assert a["weight_hash"] != b["weight_hash"]
    assert a["view_hash"] != b["view_hash"]
    assert a["model_hash"] == b["model_hash"]
    assert a["run_hash"] != b["run_hash"]
    c = fingerprint(state, bundle, (), first_weights, None, {"q": .9}, paths)
    assert c["model_hash"] != a["model_hash"]
    np.testing.assert_array_equal(bundle.index_matrix, before_indices)
