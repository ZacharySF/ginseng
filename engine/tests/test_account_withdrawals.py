from dataclasses import asdict, replace
from datetime import date, timedelta

import numpy as np
import pytest

from ginseng.withdrawals import (
    WithdrawalAllocation, WithdrawalAssumptions, withdrawal_units, quote_withdrawals, account_liquidity,
)
from ginseng.state import Holding, TaxLot, Obligation
from ginseng.optimizer import optimize_funding, OptimalPlan, OptimizationFailure
from ginseng.funding import build_candidates, evaluate_plan_paths, PlanSpec, PlanKind
from ginseng.decision import frozen_plan_evaluation
from ginseng.simulate import draw_bundle
from ginseng.risk import probabilities
from tests.test_optimizer import _state, AS_OF


def holding(wrapper, value, basis_fraction=.8, days=400, key=None):
    # Every wrapper owns the SAME instrument; only its account rules differ.
    return Holding('SAME', wrapper, 100, (TaxLot(key or wrapper, 'SAME', value / 100,
                    100 * basis_fraction, AS_OF - timedelta(days=days)),))


def test_same_instrument_produces_different_net_cash_by_account_type():
    state = replace(_state(holdings=tuple(holding(k, 1000) for k in ('taxable','traditional','roth'))),
                    roth_contribution_basis=300)
    q = quote_withdrawals(state, (WithdrawalAllocation('taxable:taxable', 1000),
        WithdrawalAllocation('traditional',1000), WithdrawalAllocation('roth',300)))
    rows = {r.account_type: r for r in q.accounts}
    assert rows['taxable'].tax_reserve == pytest.approx(30)
    assert rows['taxable'].net_cash == pytest.approx(970)
    assert rows['traditional'].tax_reserve == pytest.approx(240)
    assert rows['traditional'].penalty_reserve == pytest.approx(100)
    assert rows['traditional'].net_cash == pytest.approx(660)
    assert rows['roth'].net_cash == 300
    assert q.gross == pytest.approx(q.net_cash + q.tax_reserve + q.penalty_reserve)


def test_taxable_holding_period_and_losses_are_priced_per_lot():
    state = _state(holdings=(holding('taxable',1000,days=365,key='short'),
                             holding('taxable',1000,days=366,key='long'),
                             holding('taxable',1000,basis_fraction=1.2,key='loss')))
    units = {u.lot_id: u for u in withdrawal_units(state)}
    assert units['short'].tax_per_dollar == pytest.approx(.2 * .24)
    assert units['long'].tax_per_dollar == pytest.approx(.2 * .15)
    assert units['loss'].tax_per_dollar == 0
    quote = quote_withdrawals(state, [WithdrawalAllocation(u.key,u.capacity) for u in units.values()])
    assert quote.tax_reserve == pytest.approx(78)  # loss cannot cancel either assumed reserve


def test_roth_contributions_are_not_lot_basis_and_cannot_be_used_twice():
    state = replace(_state(holdings=(holding('roth',1000,basis_fraction=.9),)), roth_contribution_basis=200)
    assert withdrawal_units(state)[0].capacity == 200  # not the $900 purchase basis
    with pytest.raises(ValueError, match='exceeds'):
        quote_withdrawals(state, [WithdrawalAllocation('roth',150), WithdrawalAllocation('roth',100)])
    assert withdrawal_units(replace(state, roth_contribution_basis=2000))[0].capacity == 1000
    assert not withdrawal_units(replace(state, roth_contribution_basis=0))


def test_unclassified_retirement_remains_unavailable():
    state = _state(holdings=(holding('retirement',1000),))
    assert withdrawal_units(state) == ()
    assert account_liquidity(state)['unclassified_retirement_balance'] == 1000


def test_optimizer_combines_wrappers_and_reserves_tax_before_spending():
    state = replace(_state(holdings=(holding('taxable',500), holding('traditional',2000), holding('roth',1000))),
                    roth_contribution_basis=200, operating_buffer=0)
    bundle = draw_bundle(state, 10, 20, 2)
    obligations = (Obligation('bill','Bill',1000,5),)
    plan = optimize_funding(state,bundle,obligations,operating_buffer=0,tail_deficit_limit=0)
    assert isinstance(plan, OptimalPlan)
    rows = {r.account_type:r for r in plan.withdrawal_accounts}
    assert rows['roth'].gross == pytest.approx(200,abs=1e-4)
    assert rows['taxable'].gross == pytest.approx(500,abs=1e-4)
    assert rows['traditional'].gross == pytest.approx(315/.66,abs=1e-3)
    assert plan.withdrawal_net_cash == pytest.approx(1000,abs=1e-4)
    assert plan.expected_cost == pytest.approx(15 + 315/.66*.34,abs=1e-3)
    frozen = frozen_plan_evaluation(state,bundle,obligations,plan,probabilities(20),.95,.15,.2999)
    assert frozen['expected_cost'] == pytest.approx(plan.expected_cost,abs=1e-4)
    assert frozen['tail_deficit'] == pytest.approx(plan.tail_deficit,abs=1e-5)


def test_equal_cost_tie_preserves_roth_contributions():
    state = replace(_state(holdings=(holding('taxable',2000,basis_fraction=1.1), holding('roth',2000))),
                    roth_contribution_basis=1000, operating_buffer=0)
    plan = optimize_funding(state,draw_bundle(state,10,10,3),(Obligation('bill','Bill',500,5),),
                            operating_buffer=0,tail_deficit_limit=0)
    assert isinstance(plan,OptimalPlan)
    rows = {r.account_type:r for r in plan.withdrawal_accounts}
    assert rows['taxable'].net_cash == pytest.approx(500,abs=.001)
    assert rows['roth'].gross == 0


def test_traditional_uses_full_withdrawal_and_cannot_cover_a_net_shortage_with_gross_value():
    state = replace(_state(holdings=(holding('traditional',1000,basis_fraction=1),)),operating_buffer=0)
    bundle=draw_bundle(state,10,10,4)
    plan=optimize_funding(state,bundle,(Obligation('bill','Bill',700,5),),operating_buffer=0,tail_deficit_limit=0)
    assert plan == OptimizationFailure('infeasible')  # only $660 spendable, even with zero investment gain


def test_named_sale_grosses_up_for_tax_and_frozen_withdrawal_waits_for_availability():
    state = replace(_state(holdings=(holding('taxable',2000), holding('traditional',1000))),operating_buffer=0)
    bundle=draw_bundle(state,10,10,5)
    spec=build_candidates(state,(),1000)[1]
    assert spec.liquidation_target == pytest.approx(1000/.97)
    result=evaluate_plan_paths(state,bundle,(),spec)
    np.testing.assert_allclose(result.cash_matrix[:,:2],0)
    np.testing.assert_allclose(result.cash_matrix[:,2:],1000)
    traditional=PlanSpec('traditional','Traditional',PlanKind.LIQUIDATE,
                        withdrawal_allocations=(WithdrawalAllocation('traditional',1000),))
    result=evaluate_plan_paths(state,bundle,(),traditional)
    np.testing.assert_allclose(result.cash_matrix[:,:2],0)
    np.testing.assert_allclose(result.cash_matrix[:,2:],660)


def test_assumptions_panel_reports_actual_override_and_roth_exclusion():
    state=replace(_state(holdings=(holding('roth',1000),)),roth_contribution_basis=200)
    report=account_liquidity(state,WithdrawalAssumptions(long_term_rate=.20))
    assert report['accounts'][2]['excluded_balance']==800
    assert report['assumptions'][1]['value']=='20%'
    assert all('source' in row for row in report['assumptions'])
