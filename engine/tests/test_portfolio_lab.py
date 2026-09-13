from dataclasses import replace
from datetime import date

import numpy as np
import pytest

from ginseng.generate import generate_persona, canonical_shocks
from ginseng.portfolio import aligned_asset_returns, ledoit_wolf_covariance, sell_only_lp, portfolio_lab
from ginseng.simulate import draw_bundle, portfolio_value_paths
from ginseng.state import AssetReturnHistory


def test_missing_asset_observations_disable_the_lab_instead_of_zero_filling():
    state = generate_persona()
    incomplete = replace(state, asset_daily_returns=(replace(state.asset_daily_returns[0], daily_returns=state.asset_daily_returns[0].daily_returns[1:]), *state.asset_daily_returns[1:]))
    assert aligned_asset_returns(incomplete) is None
    bundle = draw_bundle(state, 30, 20, 5)
    assert portfolio_lab(incomplete, bundle, (), 100)["status"] == "unavailable"


def test_asset_paths_share_indices_and_sum_to_the_remaining_buy_and_hold_portfolio():
    state = generate_persona()
    symbols, history = aligned_asset_returns(state)
    bundle = draw_bundle(state, 30, 10, 7)
    expected = np.zeros((10, 30))
    for i, holding in enumerate(state.taxable_portfolio):
        expected += holding.market_value * np.cumprod(1 + history[bundle.index_matrix, i], axis=1)
    np.testing.assert_allclose(portfolio_value_paths(state, bundle), expected)


def test_ledoit_wolf_has_a_known_two_asset_solution_and_is_scale_equivariant():
    # Centered rows have sample covariance diag(2,8).
    x = np.array([[2., 0.], [-2., 0.], [0., 4.], [0., -4.]])
    covariance, shrinkage = ledoit_wolf_covariance(x)
    # Direct fourth moments: (16+16+256+256)/4 = 136; ||S||²=68.
    # beta=(136-68)/4=17; delta=18 => shrinkage 17/18.
    assert shrinkage == pytest.approx(17 / 18)
    np.testing.assert_allclose(covariance, np.diag([29/6, 31/6]))
    scaled, intensity = ledoit_wolf_covariance(3 * x + 19)
    np.testing.assert_allclose(scaled, 9 * covariance)
    assert intensity == pytest.approx(shrinkage)
    assert np.linalg.eigvalsh(covariance).min() >= 0


def test_fractional_sell_only_lp_meets_proceeds_without_loss_rebates():
    lots = [
        {"value": 100., "tax_per_dollar": .1, "symbol": "A"},
        {"value": 80., "tax_per_dollar": 0., "symbol": "B"},
    ]
    sales = sell_only_lp(lots, 125.5)
    np.testing.assert_allclose(sales, [45.5, 80.])
    assert np.dot(sales, [.1, 0]) == pytest.approx(4.55)
    with pytest.raises(ValueError, match="exceeds"):
        sell_only_lp(lots, 200)


def test_all_sale_methods_raise_the_same_cash_and_recompute_remaining_risk():
    state = generate_persona()
    bundle = draw_bundle(state, 30, 100, 3)
    report = portfolio_lab(state, bundle, canonical_shocks(), 1200.)
    assert len(report["variants"]) == 3
    for variant in report["variants"]:
        assert variant["proceeds"] == pytest.approx(1200.)
        assert sum(lot["dollars"] for lot in variant["lots"]) == pytest.approx(1200.)
        assert variant["estimated_positive_gain_tax"] >= 0
        assert variant["after"]["remaining_value"] == pytest.approx(report["before"]["remaining_value"] - 1200)
    assert report["variants"][1]["estimated_positive_gain_tax"] <= report["variants"][0]["estimated_positive_gain_tax"] + 1e-6
