import json
from dataclasses import asdict, replace
from datetime import date

import numpy as np
import pytest
from pydantic import ValidationError

import ginseng.api as api
from ginseng.generate import canonical_shocks
from ginseng.metrics import compute_scenario_metrics
from ginseng.funding import _next_charge_payment_offset, _day_of_month_offset
from tests.test_optimizer import _credit_account


def repair_request(**overrides):
    return api.ScenarioRequest(paths=120, obligations=[{k: v for k,v in asdict(o).items()
        if k in ("id", "label", "amount", "due_in_days")} for o in canonical_shocks()], **overrides)


@pytest.mark.parametrize('payload', [
    {"operating_buffer": float('nan')}, {"overdraft_apr": float('inf')},
    {"tail_deficit_limit": -1}, {"drought_view": {"probability": 1.1}},
    {"obligations": [{"id":"x","label":" ","amount":2,"due_in_days":2}]},
    {"obligations": [{"id":"x","label":"Bill","amount":2,"due_in_days":2}] * 2},
])
def test_invalid_or_ambiguous_inputs_are_rejected_before_work(payload):
    with pytest.raises(ValidationError):
        api.ScenarioRequest(**payload)


def test_every_plan_receives_the_selected_buffer_and_horizon(monkeypatch):
    seen = []
    evaluate = api.evaluate_plan
    def observed(state, *args, **kwargs):
        seen.append((state.operating_buffer, state.forecast_horizon))
        return evaluate(state, *args, **kwargs)
    monkeypatch.setattr(api, 'evaluate_plan', observed)
    result = api.scenario(repair_request(operating_buffer=777, horizon_days=60), None)
    assert seen == [(777, 60)] * 4
    assert {p['evaluation_horizon_days'] for p in result.plans} == {60}
    assert result.optimal_plan['evaluation_weight_hash'] == result.provenance['weight_hash']


def test_api_uses_stress_weights_for_cash_metrics_and_comparison_plans():
    request = repair_request(drought_view={"probability": .3})
    state, obligations, bundle, _, weights, _ = api._scenario_context(request)
    expected = compute_scenario_metrics(state, bundle, obligations, request.coverage_target, request.operating_buffer, weights)
    response = api.scenario(request, None)
    assert response.required_liquidity_reserve == expected.required_liquidity_reserve
    assert response.severity.cash_shortfall_probability == expected.severity['cash_shortfall_probability']
    assert response.cash_paths.p50 == expected.cash_paths['p50']
    assert len({p['evaluation_weight_hash'] for p in response.plans}) == 1
    assert response.estimate_band is None  # unweighted band must not dress up stress as calibration
    assert not response.stress['recommendation_supported']  # insufficient tail support at 120 draws
    assert all(not p['recommended'] for p in response.plans)


def test_shrinking_horizon_does_not_move_a_later_bill():
    request = api.ScenarioRequest(paths=100, horizon_days=14,
        obligations=[{"id":"bill","label":"Bill","amount":10000,"due_in_days":17}])
    response = api.scenario(request, None)
    assert response.excluded_obligations == ['bill']
    assert request.obligations[0].due_in_days == 17
    assert response.required_liquidity_reserve == response.baseline_summary['required_liquidity_reserve']


def test_credit_payment_uses_calendar_date_in_february_instead_of_adding_30():
    account = replace(_credit_account('card',100), statement_close_day=25, payment_due_day=16)
    # Feb 11 -> close Feb 25 -> payment Mar 16, 33 days in 2026, not 35.
    assert _next_charge_payment_offset(date(2026,2,11), account) == 33


def test_calendar_occurrence_can_skip_a_month_without_that_day():
    assert _day_of_month_offset(date(2026,2,1), 31) == 58
    with pytest.raises(ValueError):
        _day_of_month_offset(date(2026,2,1), 32)


def test_new_analysis_endpoints_are_authenticated_and_return_json(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv('GINSENG_ALLOW_ANONYMOUS_DEMO', '0')
    dependency = getattr(api, 'require_scenario_access', api.require_identity)
    with TestClient(api.app) as client:
        for kind in ('calibration','funding','portfolio'):
            assert client.post(f'/analysis/{kind}', json={}).status_code == 401
        api.app.dependency_overrides[dependency] = lambda: None
        try:
            for kind in ('calibration','funding','portfolio'):
                response = client.post(f'/analysis/{kind}', json=repair_request().model_dump())
                assert response.status_code == 200
                body = response.json()
                assert body['status'] == 'ready'
                json.dumps(body, allow_nan=False)
        finally:
            api.app.dependency_overrides.pop(dependency, None)
