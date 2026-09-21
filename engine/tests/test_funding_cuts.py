"""The compact LP must agree with the full scenario LP and its risk limits."""

from dataclasses import replace

import numpy as np
import pytest

import ginseng.optimizer as optimizer
from ginseng.generate import generate_persona
from ginseng.optimizer import OptimalPlan, OptimizationFailure, optimize_funding
from ginseng.simulate import draw_bundle
from ginseng.state import Obligation
from tests.test_optimizer import _state, _credit_account, _taxable_holding


@pytest.mark.parametrize("q,objective,tail_limit", [
    (.95, "cvar", None), (1., "cvar", None), (.95, "expected", None),
    (.95, "cvar", 1500.), (1., "cvar", 1500.), (1., "expected", 1500.),
])
def test_supporting_planes_match_full_lp_on_weighted_account_withdrawals(monkeypatch, q, objective, tail_limit):
    state = generate_persona()
    bundle = draw_bundle(state, 30, 40, 71)
    obligations = (Obligation("bill", "Bill", 30000, 7),)
    weights = np.arange(40, dtype=float)  # includes a zero-probability scenario
    parameters = dict(weights=weights, coverage_target=q, objective_kind=objective,
                      tail_deficit_limit=tail_limit)
    monkeypatch.setattr(optimizer, "CONSTRAINT_GENERATION_THRESHOLD", 1_000_000)
    full = optimize_funding(state, bundle, obligations, **parameters)
    monkeypatch.setattr(optimizer, "CONSTRAINT_GENERATION_THRESHOLD", 0)
    compact = optimize_funding(state, bundle, obligations, **parameters)
    assert isinstance(full, OptimalPlan)
    assert isinstance(compact, OptimalPlan)
    metric = "expected_cost" if objective == "expected" else "cvar_cost"
    assert getattr(compact, metric) == pytest.approx(getattr(full, metric), abs=.005)
    assert compact.dollar_days_below_buffer <= compact.buffer_tolerance_dollar_days + 1e-5
    if tail_limit is not None:
        assert compact.tail_deficit <= tail_limit + 1e-5
    assert compact.evaluation_draw_id == full.evaluation_draw_id
    assert compact.evaluation_weight_hash == full.evaluation_weight_hash
    assert compact.evaluation_paths == 40
    assert compact.solver_method == "highs_constraint_generation"
    assert compact.withdrawal_net_cash == pytest.approx(compact.liquidation_amount
        - compact.withdrawal_tax_reserve - compact.withdrawal_penalty_reserve)


def test_compact_credit_dual_matches_the_next_dollar(monkeypatch):
    monkeypatch.setattr(optimizer, "CONSTRAINT_GENERATION_THRESHOLD", 0)
    state = _state(cards=(_credit_account("card", 50, grace_period_eligible=True),),
                   holdings=(_taxable_holding(1000, 1000),))
    bundle = draw_bundle(state, 30, 20, 9)
    obligations = (Obligation("bill", "Bill", 100, 1),)
    parameters = dict(operating_buffer=0, buffer_tolerance_dollar_days=10000, overdraft_apr=.365)
    base = optimize_funding(state, bundle, obligations, **parameters)
    nudged_state = replace(state, credit_accounts=(replace(state.credit_accounts[0], credit_limit=51),))
    nudged = optimize_funding(nudged_state, bundle, obligations, **parameters)
    assert isinstance(base, OptimalPlan) and isinstance(nudged, OptimalPlan)
    assert base.implied_credit_price == pytest.approx(base.cvar_cost - nudged.cvar_cost, abs=1e-6)


def test_compact_solver_fails_explicitly_when_time_is_exhausted(monkeypatch):
    monkeypatch.setattr(optimizer, "CONSTRAINT_GENERATION_THRESHOLD", 0)
    state = _state(holdings=(_taxable_holding(1000, 1000),))
    result = optimize_funding(state, draw_bundle(state, 30, 10, 9), (), time_limit_seconds=1e-12)
    assert result == OptimizationFailure("solver_timeout")


def test_compact_solver_cannot_spend_traditional_gross_proceeds(monkeypatch):
    monkeypatch.setattr(optimizer, "CONSTRAINT_GENERATION_THRESHOLD", 0)
    state = _state(holdings=(replace(_taxable_holding(1000, 1000), account="traditional"),))
    result = optimize_funding(state, draw_bundle(state, 30, 10, 9),
        (Obligation("bill", "Bill", 700, 5),), operating_buffer=0, tail_deficit_limit=0)
    assert result == OptimizationFailure("infeasible")


def test_exported_lower_bound_contains_independent_full_lp_objective(monkeypatch):
    state = _state(holdings=(_taxable_holding(1000,0),))
    bundle=draw_bundle(state,30,8,17)
    bills=(Obligation('bill','Bill',100,3),)
    monkeypatch.setattr(optimizer,'CONSTRAINT_GENERATION_THRESHOLD',0)
    plan=optimize_funding(state,bundle,bills,operating_buffer=0,buffer_tolerance_dollar_days=0)
    assert isinstance(plan,OptimalPlan)
    oracle_cost=100/.76*.24
    e=plan.solver_evidence
    assert e['lower_bound']<=oracle_cost+1e-7
    assert e['executed_objective']>=oracle_cost-1e-6
    assert e['absolute_gap']<.001
    assert e['iterations']>=1
    assert e['solver_version']!='unavailable'
    assert e['global_lower_bound'] is None
