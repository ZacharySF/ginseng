"""Regressions for the personal/demo funding comparison and reserve contract."""
from dataclasses import replace
from datetime import date, timedelta
from uuid import UUID

import numpy as np
import pytest

from ginseng.finance_models import (FinanceInputs, FinanceWorkspace, PlanningPolicy,
    PersonalHolding, PersonalTaxLot, PersonalCreditAccount, ModelAssumptions)
from ginseng.workspace import CashAccount, CashBill
from ginseng.personal_forecast import evaluate_personal_forecast, backtest_personal_history
from ginseng.policy import FundingPolicy, Recommendation, to_contract
from ginseng.funding import PlanResult, PlanKind
from ginseng.optimizer import OptimalPlan, optimize_funding
from ginseng.generate import generate_persona
from ginseng.simulate import draw_bundle
from ginseng.state import Obligation


def workspace(rate=.15, buffer=0):
    opening = date(2026, 9, 13)
    return FinanceWorkspace(revision=1, as_of=opening, currency="USD",
        accounts=[CashAccount(id=UUID(int=1), name="Checking", kind="checking", balance_cents=50000)],
        bills=[CashBill(id=UUID(int=2), label="Bill", amount_cents=100000, due_date=opening+timedelta(days=7))],
        inputs=FinanceInputs(mode="scheduled", policy=PlanningPolicy(capital_gains_rate=rate, operating_buffer_cents=buffer),
            holdings=[PersonalHolding(id=UUID(int=3), symbol="FUND", account="taxable", current_price_cents=10000,
                tax_lots=[PersonalTaxLot(id=UUID(int=4), quantity=100, cost_basis_per_share_cents=0, purchase_date=date(2020,1,1))])]))


def card():
    return PersonalCreditAccount(id=UUID(int=5), name="Card", credit_limit_cents=100000,
        current_balance_cents=60000, purchase_apr=.2, statement_close_day=20, payment_due_day=18,
        grace_period_eligible=False, minimum_payment_cents=1000)


def test_dominated_first_plan_has_its_own_explanation():
    expensive = PlanResult("a", "A", PlanKind.CREDIT, 30, "same", 0, 0, 100, 1, 0, 0, 0, .1, True)
    cheap = replace(expensive, id="b", label="B", new_debt=0, interest_exposure=0)
    plans, _ = to_contract([expensive, cheap], Recommendation("b", "B is best"))
    assert plans[0]["dominated"] and plans[0]["explanation"] != plans[1]["explanation"]


def test_buffer_gap_cannot_recommend_a_noop():
    w = workspace(buffer=100000)
    w.bills = []
    result = evaluate_personal_forecast(w, 30).result
    assert result.funding_gap == 500
    assert result.recommendation["plan_id"] == ""
    protective = next(p for p in result.plans if p["id"] == "protective")
    assert protective["buffer_breach_probability"] == 1
    assert not protective["meets_policy"]
    assert result.optimizer_status.code == "infeasible"  # money cannot arrive before settlement


@pytest.mark.parametrize("rate", [0., .15, .5])
def test_named_and_optimized_tax_rates_and_evaluation_match(rate):
    result = evaluate_personal_forecast(workspace(rate), 30).result
    sale = next(p for p in result.plans if p["id"] == "liquidate")
    optimal = result.optimal_plan
    assert sale["withdrawal_tax_reserve"] == pytest.approx(500 * rate / (1-rate), abs=.001)
    assert optimal["withdrawal_tax_reserve"] == pytest.approx(sale["withdrawal_tax_reserve"], abs=.001)
    assert optimal["meets_policy"]
    assert {(p["evaluation_horizon_days"], p["evaluation_draw_id"], p["evaluation_weight_hash"]) for p in result.plans} == {
        (optimal["evaluation_horizon_days"], optimal["evaluation_draw_id"], optimal["evaluation_weight_hash"])}
    assert result.account_liquidity["total_net_accessible"] == pytest.approx(10000 * (1-rate))
    assert len(result.provenance["run_hash"]) == 64
    assert result.model_card["history_days"] == 0


def test_no_credit_capacity_does_not_shorten_optimizer_horizon():
    w = workspace()
    w.inputs.credit_accounts = [card()]
    result = evaluate_personal_forecast(w, 30).result
    assert result.optimal_plan["evaluation_horizon_days"] == 39
    assert all(p["evaluation_horizon_days"] == 39 for p in result.plans)
    assert result.optimal_plan["credit_draw"] == pytest.approx(0, abs=1e-5)
    assert result.optimal_plan["meets_policy"]  # existing utilization cannot prohibit a sale


def test_personal_roth_access_is_capped_at_contributions_and_survives_horizon_copy():
    w = workspace()
    w.inputs.holdings[0].account = "roth"
    w.inputs.roth_contribution_basis_cents = 50000
    result = evaluate_personal_forecast(w, 30).result
    assert result.optimal_plan["withdrawal_net_cash"] == pytest.approx(500, abs=.001)
    assert result.optimal_plan["withdrawal_tax_reserve"] == 0
    assert result.account_liquidity["total_net_accessible"] == 500
    assert result.account_liquidity["accounts"][2]["excluded_balance"] == 9500
    w.inputs.roth_contribution_basis_cents = 10000
    assert evaluate_personal_forecast(w, 30).result.optimal_plan is None


def test_personal_traditional_prices_entire_pretax_withdrawal():
    w = workspace()
    w.inputs.holdings[0].account = "traditional"
    result = evaluate_personal_forecast(w, 30).result
    gross = 500 / .66
    assert result.optimal_plan["liquidation_amount"] == pytest.approx(gross, abs=.001)
    assert result.optimal_plan["withdrawal_tax_reserve"] == pytest.approx(gross * .24, abs=.001)
    assert result.optimal_plan["withdrawal_penalty_reserve"] == pytest.approx(gross * .1, abs=.001)


def test_purchase_limit_cannot_be_used_as_cash_and_cash_advance_fee_is_not_free():
    w = workspace()
    w.inputs.policy.overdraft_apr = 0
    c = card().model_copy(update={"current_balance_cents": 0, "credit_limit_cents": 1000000})
    w.inputs.credit_accounts = [c]
    result = evaluate_personal_forecast(w, 30).result
    assert not next(p for p in result.plans if p["id"] == "credit")["feasible"]
    c.cash_advance_limit_cents = 100000
    c.cash_advance_apr = .365
    c.cash_advance_fee_pct = .05
    result = evaluate_personal_forecast(w, 30).result
    credit = next(p for p in result.plans if p["id"] == "credit")
    assert credit["new_debt"] == pytest.approx(500/.95)
    # 35 days of interest plus a fee withheld from today's cash proceeds.
    assert credit["interest_exposure"] == pytest.approx(credit["new_debt"] * (.05 + .001*35))


@pytest.mark.parametrize("q", [.8, .95, 1.])
def test_signed_coverage_constraint_agrees_between_solvers(monkeypatch, q):
    import ginseng.optimizer as optimizer
    state = generate_persona()
    bundle = draw_bundle(state, 30, 35, 71)
    parameters = dict(coverage_target=q, weights=np.arange(35),
        funding_policy=FundingPolicy(max_buffer_breach_probability=1-q,
                                     max_cash_shortfall_probability=1-q))
    bill = (Obligation("bill", "Bill", 30000, 7),)
    monkeypatch.setattr(optimizer, "CONSTRAINT_GENERATION_THRESHOLD", 1000000)
    full = optimize_funding(state, bundle, bill, **parameters)
    monkeypatch.setattr(optimizer, "CONSTRAINT_GENERATION_THRESHOLD", 0)
    cuts = optimize_funding(state, bundle, bill, **parameters)
    assert isinstance(full, OptimalPlan) and isinstance(cuts, OptimalPlan)
    assert full.cvar_cost == pytest.approx(cuts.cvar_cost, abs=.005)
    assert full.meets_policy and cuts.meets_policy
    assert cuts.buffer_breach_probability <= 1-q+1e-12


def test_personal_calibration_counts_non_overlapping_reserve_windows():
    w = workspace()
    w.inputs = FinanceInputs(mode="history", history_start=date(2026,1,1), history_end=date(2026,5,7), history_complete=True)
    report = backtest_personal_history(w, 30, paths=20)
    assert report.periods == 1  # eight daily origins are not eight independent tests
    assert report.warning
    assert report.calibration["nominal_coverage"] == .95
    assert report.calibration["primary"]["interval"]["low"] < .1
    assert report.calibration["formal_tests"]["kupiec"]["status"] == "unavailable"


def test_assumed_payment_arrivals_include_unpaid_days_and_preserve_the_mean():
    from ginseng.personal_forecast import _assumption_bundle, _state_for_workspace, _with_horizon, _schedule_for_workspace
    w = workspace()
    w.bills = []
    w.inputs.mode = "assumptions"
    w.inputs.assumptions = ModelAssumptions(monthly_variable_income_cents=300000, income_payments_per_month=2)
    state = _with_horizon(_state_for_workspace(w, _schedule_for_workspace(w,400), history=False),30)
    bundle = _assumption_bundle(state, w.inputs, 17, 4000)
    daily = bundle.daily_cash_flows
    assert np.mean(daily == 0) > .9
    assert np.mean(daily.sum(axis=1)) == pytest.approx(3000*400/(365.2425/12), rel=.02)


@pytest.mark.parametrize('advance_limit,utilization', [(None, 1.), (None, .3), (100., .3), (0., .3)])
def test_shadow_nudge_adds_usable_credit_after_all_limits(advance_limit, utilization):
    from ginseng.decision import _increase_credit_capacity
    from tests.test_optimizer import _credit_account
    account = replace(_credit_account('card', 2000), current_balance=200,
                      cash_advance_limit=advance_limit)
    def capacity(a):
        return max(0., min(a.available_credit, a.credit_limit * utilization - a.current_balance))
    for bump in (1., 10., 100.):
        nudged = _increase_credit_capacity(account, utilization, bump)
        assert capacity(nudged) - capacity(account) == pytest.approx(bump)
    assert _increase_credit_capacity(account, 0., 1.) is None


def test_fresh_sample_preserves_the_selected_credit_account_and_availability_days():
    from tests.test_optimizer import _credit_account, _state, _taxable_holding
    from ginseng.decision import frozen_plan_evaluation
    from ginseng.risk import probabilities
    from ginseng.funding import FundingConfig
    expensive = _credit_account('large-purchase-limit', 10000, apr=.5)
    cheap = replace(_credit_account('usable-cash', 3000, apr=.01), cash_advance_fee_pct=.03)
    state = replace(_state(opening_cash=100, cards=(replace(expensive, current_balance=9500), cheap),
                           holdings=(_taxable_holding(1000, 500),)), operating_buffer=0)
    bundle = draw_bundle(state, 40, 20, 3)
    obligations = (Obligation('bill', 'Bill', 500, 1),)
    plan = optimize_funding(state, bundle, obligations, operating_buffer=0,
        funding_policy=FundingPolicy(max_credit_utilization=.3),
        funding_config=FundingConfig(settlement_days=2, external_transfer_days=3, use_business_days=True))
    assert isinstance(plan, OptimalPlan)
    assert plan.credit_account_id == cheap.account_id and plan.credit_draw > 1
    frozen = frozen_plan_evaluation(state, bundle, obligations, plan, probabilities(20), .95, .15, .2999)
    assert frozen['expected_cost'] == pytest.approx(plan.expected_cost, abs=.001)
    assert frozen['tail_deficit'] == pytest.approx(plan.tail_deficit, abs=.001)


def test_explicit_mean_deficit_limit_applies_even_with_no_reserve_gap():
    from tests.test_optimizer import _state, _taxable_holding
    from ginseng.simulate import PathBundle
    from ginseng.scenario_service import evaluate_scenario
    state = replace(_state(opening_cash=1000, holdings=(_taxable_holding(5000, 5000),)),
                    operating_buffer=1000, coverage_target=.95)
    daily = np.zeros((100, 60))
    daily[:4, 9] = -100
    bundle = PathBundle(source='assumptions', seed=1, horizon_days=30, n_paths=100,
        bootstrap_draw_id='mean-limit-regression', daily_cash_flows=daily,
        known_income_daily=np.zeros(60), known_obligation_daily=np.zeros(60),
        discretionary_daily=np.zeros((100, 60)))
    response = evaluate_scenario(state, bundle, (), coverage_target=.95,
        operating_buffer=1000, buffer_tolerance_dollar_days=0,
        include_reserve_uncertainty=False, include_persistence_sensitivity=False).response
    assert response.funding_gap == 0
    assert response.severity.dollar_days_below_buffer > 0
    assert response.optimal_plan['liquidation_amount'] == pytest.approx(100, abs=.001)
    assert response.optimal_plan['meets_policy']
