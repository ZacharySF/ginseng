from dataclasses import replace

import numpy as np
import pytest

from ginseng.optimizer import optimize_funding, OptimalPlan
from ginseng.decision import funding_analysis, frozen_plan_evaluation
from ginseng.funding import build_candidates, optimizer_comparison_bundle, FundingConfig, PlanSpec, PlanKind, evaluate_plan
from ginseng.policy import recommend, FundingPolicy, to_contract
from ginseng.simulate import draw_bundle
from ginseng.state import Obligation
from ginseng.risk import probabilities
from tests.test_optimizer import _state, _credit_account, _taxable_holding


def test_hybrid_uses_only_new_funding_and_rejects_an_invented_cash_contribution():
    state = _state(holdings=(_taxable_holding(5000, 5000),))
    config = FundingConfig()
    assert config.hybrid_cash_fraction == 0
    hybrid = build_candidates(state, (), 1000, config)[2]
    assert hybrid.unfunded_cash_amount == 0
    assert hybrid.credit_draw == 250 and hybrid.liquidation_target == 600
    with pytest.raises(ValueError, match="already included"):
        FundingConfig(hybrid_cash_fraction=.3, hybrid_liquidation_fraction=.3)
    bundle = draw_bundle(state, 30, 10, 1)
    broken = evaluate_plan(state, bundle, (), replace(hybrid, unfunded_cash_amount=300))
    assert not broken.feasible


def test_no_plan_is_recommended_when_every_option_violates_the_hard_policy():
    state = _state()
    bundle = draw_bundle(state, 30, 10, 1)
    result = evaluate_plan(state, bundle, (Obligation("bill", "Bill", 1000, 1),), PlanSpec("wait", "Wait", PlanKind.PROTECTIVE))
    recommendation = recommend([result], FundingPolicy())
    assert recommendation.plan_id == ""
    assert not to_contract([result], recommendation)[0][0]["recommended"]


def test_weighted_cvar_and_tail_deficit_limits_use_actual_path_losses():
    state = _state(holdings=(_taxable_holding(5000, 5000),), opening_cash=1000)
    bundle = draw_bundle(state, 30, 20, 1)
    obligations = (Obligation("bill", "Bill", 2000, 5),)
    weights = probabilities(20, np.arange(1, 21))
    plan = optimize_funding(state, bundle, obligations, operating_buffer=1000, weights=weights, tail_deficit_limit=0)
    assert isinstance(plan, OptimalPlan)
    assert plan.tail_deficit <= 1e-6
    assert plan.liquidation_amount == pytest.approx(2000, abs=.001)
    assert plan.expected_cost == pytest.approx(0, abs=1e-6)


def test_credit_shadow_price_matches_small_resolves_and_holdout_freezes_actions():
    state = _state(cards=(_credit_account("card", 50, grace_period_eligible=True),),
                   holdings=(_taxable_holding(1000, 1000),))
    state = replace(state, operating_buffer=0)
    base_bundle = draw_bundle(state, 30, 20, 9)
    obligations = (Obligation("bill", "Bill", 100, 1),)
    specs = build_candidates(state, obligations, 100)
    bundle = optimizer_comparison_bundle(state, base_bundle, specs)
    parameters = dict(coverage_target=.95, operating_buffer=0., overdraft_apr=.365,
                      buffer_tolerance_dollar_days=10000., capital_gains_rate=.15, tail_deficit_limit=None)
    report = funding_analysis(state, bundle, obligations, specs, probabilities(20), None, parameters)
    assert report["status"] == "ready"
    assert report["base"]["implied_credit_price"] == pytest.approx(.002, abs=1e-5)
    credit = report["shadow_checks"][0]
    for row in credit["checks"][:2]:
        assert row["value_per_unit"] == pytest.approx(.002, abs=1e-5)
    # The $100 bump reaches diminishing returns after the $50 shortage.
    assert credit["checks"][2]["value_per_unit"] < .002
    assert not credit["stable"]
    assert report["holdout"]["evaluation_draw_id"] != report["evaluation_draw_id"]
    assert report["holdout"]["expected_cost"] == pytest.approx(report["base"]["expected_cost"], abs=1e-5)
    for point in report["frontier"]:
        if point["plan"]:
            assert point["plan"]["evaluation_draw_id"] == report["evaluation_draw_id"]
            assert point["plan"]["evaluation_weight_hash"] == report["evaluation_weight_hash"]
