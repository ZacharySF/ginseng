"""Funding-policy decision invariants."""

from dataclasses import replace

import pytest

from ginseng.funding import PlanKind, PlanResult
from ginseng.policy import FundingPolicy, Recommendation, pareto_filter, recommend, to_contract


def _result(
    plan_id: str,
    *,
    feasible: bool,
    cash_shortfall_probability: float,
    credit_utilization: float = 0.0,
    reason: str | None = None,
) -> PlanResult:
    return PlanResult(
        id=plan_id,
        label=plan_id.title(),
        kind=PlanKind.CREDIT if plan_id == "credit" else PlanKind.LIQUIDATE,
        evaluation_horizon_days=30,
        evaluation_draw_id="draw",
        cash_shortfall_probability=cash_shortfall_probability,
        avg_cash_deficit_when_short=0.0,
        new_debt=0.0,
        interest_exposure=0.0,
        investment_sold=0.0,
        realized_gain_loss=0.0,
        deferred_spending=0.0,
        credit_utilization=credit_utilization,
        feasible=feasible,
        infeasibility_reason=reason,
    )


def test_recommendation_never_selects_a_structurally_infeasible_candidate():
    unavailable_credit = _result(
        "credit",
        feasible=False,
        cash_shortfall_probability=0.0,
        reason="credit draw exceeds available credit",
    )
    liquidate = _result("liquidate", feasible=True, cash_shortfall_probability=0.01)

    recommendation = recommend([unavailable_credit, liquidate], FundingPolicy())

    assert recommendation.plan_id == "liquidate"


@pytest.mark.parametrize(
    "changed_evaluation",
    [{"evaluation_horizon_days": 38}, {"evaluation_draw_id": "different-draw"}],
)
def test_policy_rejects_incomparable_evaluations(changed_evaluation):
    credit = _result("credit", feasible=True, cash_shortfall_probability=0.01)
    liquidate = replace(
        _result("liquidate", feasible=True, cash_shortfall_probability=0.02),
        **changed_evaluation,
    )
    results = [credit, liquidate]
    for compare in (
        pareto_filter,
        lambda rows: recommend(rows, FundingPolicy()),
        lambda rows: to_contract(rows, Recommendation("credit", "Example")),
    ):
        with pytest.raises(ValueError, match="same evaluation horizon and draw bundle"):
            compare(results)
