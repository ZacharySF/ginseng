"""On-demand decision analysis with a shared budget and frozen-plan holdout."""

from dataclasses import asdict, replace
from time import monotonic

import numpy as np

from ginseng.funding import PlanKind, PlanSpec, evaluate_plan_paths, _select_primary_credit_account
from ginseng.optimizer import OptimalPlan, OptimizationFailure, optimize_funding
from ginseng.risk import cvar, quantile, weight_hash
from ginseng.simulate import draw_bundle
from ginseng.stress import scenario_weights

ANALYSIS_BUDGET_SECONDS = 40.0


def loss_metrics(evaluation, state, q, weights, tax_rate, overdraft_apr) -> dict:
    balances = state.immediate_funding + evaluation.cash_matrix
    result = evaluation.result
    cost = (result.interest_exposure + max(0.0, result.realized_gain_loss) * tax_rate
            + evaluation.spending_reduction + (overdraft_apr / 365) * np.maximum(0.0, -balances).sum(axis=1))
    worst_deficit = np.maximum(0.0, state.operating_buffer - balances.min(axis=1))
    return {
        "expected_cost": float(weights @ cost), "cvar_cost": cvar(cost, q, weights),
        "var_cost": quantile(cost, q, weights), "tail_deficit": cvar(worst_deficit, q, weights),
        "cash_shortfall_probability": float(weights @ (balances.min(axis=1) < 0)),
        "buffer_breach_probability": float(weights @ (balances.min(axis=1) < state.operating_buffer)),
        "dollar_days_below_buffer": float(weights @ np.maximum(0.0, state.operating_buffer - balances).sum(axis=1)),
    }


def frozen_plan_evaluation(state, bundle, obligations, plan, weights, q, tax_rate, overdraft_apr):
    account = _select_primary_credit_account(state)
    spec = PlanSpec("optimized", "Optimized", PlanKind.HYBRID,
                    credit_account_id=account.account_id if account else None,
                    credit_draw=plan.credit_draw, liquidation_target=plan.liquidation_amount,
                    lot_selection="proportional", discretionary_reduction_fraction=plan.deferral_fraction)
    evaluated = evaluate_plan_paths(state, bundle, obligations, spec, weights)
    return loss_metrics(evaluated, state, q, weights, tax_rate, overdraft_apr)


def funding_analysis(state, bundle, obligations, specs, weights, view, parameters) -> dict:
    deadline = monotonic() + ANALYSIS_BUDGET_SECONDS

    def solve(current_state=state, **overrides):
        remaining = deadline - monotonic()
        if remaining <= 0.1:
            return OptimizationFailure("solver_timeout")
        return optimize_funding(current_state, bundle, obligations, weights=weights,
                                **{**parameters, **overrides}, time_limit_seconds=min(10.0, remaining))

    q = parameters["coverage_target"]
    base = solve()
    anchors = []
    for spec in specs:
        evaluation = evaluate_plan_paths(state, bundle, obligations, spec, weights)
        anchors.append({"id": spec.id, "label": spec.label, "feasible": evaluation.result.feasible,
                        **loss_metrics(evaluation, state, q, weights, parameters["capital_gains_rate"], parameters["overdraft_apr"])})
    result = {
        "status": "ready", "evaluation_horizon_days": bundle.horizon_days,
        "evaluation_draw_id": bundle.bootstrap_draw_id, "evaluation_weight_hash": weight_hash(weights),
        "paths": bundle.n_paths, "anchors": anchors, "frontier": [], "shadow_checks": [], "holdout": None,
        "loss_definition": "Interest + assumed positive-gain tax cost + discretionary spending forgone + overdraft dollar-days priced at the assumed APR. Sale principal is not a cost.",
        "risk_definition": "Tail buffer deficit averages each path's largest dollar deficit in the worst (1-q) fraction of deficits. This need not select the same futures as the cost tail. At q=1 it is the largest modeled deficit.",
        "budget_seconds": ANALYSIS_BUDGET_SECONDS,
    }
    if not isinstance(base, OptimalPlan):
        return {**result, "status": "unavailable", "reason": base.reason}
    result["base"] = asdict(base)
    # Fresh random draws from the same historical model. Controls are frozen,
    # and this sample is never used to tune the solution or pick a frontier point.
    holdout_seed = int(np.random.SeedSequence([bundle.seed, 98173]).generate_state(1)[0])
    holdout = draw_bundle(state, bundle.horizon_days, bundle.n_paths, holdout_seed, bundle.mean_block_length)
    holdout_weights, holdout_stress = scenario_weights(state, holdout, view)
    if holdout_stress["status"] == "unsupported":
        result["holdout"] = {"status": "unavailable", "message": "Fresh scenarios do not support the active stress assumption."}
    else:
        observed = frozen_plan_evaluation(state, holdout, obligations, base, holdout_weights, q,
                                         parameters["capital_gains_rate"], parameters["overdraft_apr"])
        result["holdout"] = {"status": "ready", "evaluation_draw_id": holdout.bootstrap_draw_id,
            "evaluation_weight_hash": weight_hash(holdout_weights), "paths": holdout.n_paths,
            "label": "Fresh simulation check, not new historical evidence. The selected actions were not re-optimized.",
            **observed,
            "within_mean_buffer_limit": observed["dollar_days_below_buffer"] <= base.buffer_tolerance_dollar_days + 1e-6,
            "within_tail_deficit_limit": observed["tail_deficit"] <= base.tail_deficit_limit + 1e-6 if base.tail_deficit_limit is not None else None}

    # Verify marginal values near the current solution, never extrapolate
    # them over the entire credit limit or the entire deficit allowance.
    account = _select_primary_credit_account(state)
    for resource in ("credit_capacity", "mean_buffer_allowance"):
        dual = base.implied_credit_price if resource == "credit_capacity" else base.implied_liquidity_price
        checks = []
        if resource == "credit_capacity" and account is None:
            continue
        for bump in (1.0, 10.0, 100.0):
            if resource == "credit_capacity":
                nudged = replace(state, credit_accounts=tuple(replace(a, credit_limit=a.credit_limit + bump)
                    if a.account_id == account.account_id else a for a in state.credit_accounts))
                solution = solve(nudged)
            else:
                solution = solve(buffer_tolerance_dollar_days=base.buffer_tolerance_dollar_days + bump)
            checks.append({"bump": bump, "value_per_unit": (base.cvar_cost - solution.cvar_cost) / bump if isinstance(solution, OptimalPlan) else None,
                           "status": solution.solver_status if isinstance(solution, OptimalPlan) else solution.reason})
        values = [row["value_per_unit"] for row in checks if row["value_per_unit"] is not None]
        result["shadow_checks"].append({"resource": resource, "solver_dual": dual, "checks": checks,
            "range": {"low": min(values), "high": max(values)} if values else None,
            "stable": len(values) == 3 and max(values) - min(values) <= max(0.00001, 0.1 * max(abs(v) for v in values))})

    scale = max(100.0, state.operating_buffer)
    limits = sorted({0.0, scale / 4, scale / 2, scale, scale * 2, base.tail_deficit})
    for limit in limits:
        point = solve(tail_deficit_limit=limit, objective_kind="expected")
        result["frontier"].append({"limit": limit, "status": point.solver_status if isinstance(point, OptimalPlan) else point.reason,
                                   "plan": asdict(point) if isinstance(point, OptimalPlan) else None})
    result["budget_exhausted"] = monotonic() >= deadline
    return result
