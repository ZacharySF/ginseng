"""Funding-policy decision invariants."""

from ginseng.funding import PlanKind, PlanResult
from ginseng.policy import FundingPolicy, recommend


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
