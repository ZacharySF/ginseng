"""CVaR-optimal funding plan (Telser safety-first + Rockafellar-Uryasev).

The model evaluates every supplied bootstrap path under common random numbers.
Buffer-shortfall and overdraft auxiliaries are created only for path-days that
can incur those costs under the control bounds. Provably zero terms are omitted,
never paths or their probability weights. Requests whose evaluation bundle
exceeds ``MAX_SCENARIO_DAYS`` return an explicit resource-limit failure.

The default Telser tolerance is a *mean* dollar-day limit:
``operating_buffer * evaluation_horizon_days * policy shortfall probability``.
It allows the same aggregate buffer erosion as fully missing the operating
buffer on the policy's permitted fraction of forecast days, and is independent
of the number of bootstrap paths.

Liquidation assumes execution today at the recorded holding prices. Gross
proceeds become cash only after settlement and transfer. The tax cost is an
estimate on positive gains from a proportional sale across all taxable lots;
the configured rate is an assumption, not a final tax liability. Losses never
create a negative tax cost or a cash rebate. Future market returns do not
reprice an executed sale. Cash-flow uncertainty can still make costs vary.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal, Sequence

import numpy as np
from scipy.sparse import csr_matrix

from ginseng.funding import (
    FundingConfig,
    _next_charge_payment_offset,
    _select_primary_credit_account,
    extend_draw_bundle,
)
from ginseng.policy import FundingPolicy
from ginseng.risk import probabilities, quantile, cvar, weight_hash
from ginseng.simulate import (
    DrawBundle,
    cash_paths,
    discretionary_resampled_paths,
)
from ginseng.state import FinancialState, Obligation

# Keep the worst-case LP within an interactive request's memory/time envelope.
# This covers the UI's 14/30/60-day horizons at up to 3,000 paths; larger
# evaluations omit the optional optimizer, never substitute fewer paths.
MAX_SCENARIO_DAYS = 200_000
SOLVER_TIME_LIMIT_SECONDS = 10.0
_NUMERICAL_TOLERANCE = 1e-6
_OPTIMAL_STATUSES = frozenset(("optimal", "optimal_inaccurate"))


OptimizationFailureReason = Literal[
    "invalid_input", "no_funding_levers", "resource_limit", "cvxpy_unavailable",
    "solver_unavailable", "solver_timeout", "solver_limit", "solver_error",
    "infeasible", "unbounded", "invalid_solution",
]


@dataclass(frozen=True)
class OptimizationFailure:
    reason: OptimizationFailureReason


@dataclass(frozen=True)
class OptimalPlan:
    credit_draw: float
    liquidation_amount: float
    deferral_fraction: float
    cvar_cost: float
    var_cost: float
    expected_cost: float
    cash_shortfall_probability: float
    implied_liquidity_price: float | None
    cost_is_path_dependent: bool
    solver_status: str
    evaluation_horizon_days: int
    evaluation_draw_id: str
    evaluation_paths: int
    cost_coverage_target: float
    buffer_breach_probability: float
    dollar_days_below_buffer: float
    buffer_tolerance_dollar_days: float
    buffer_constraint_binding: bool
    evaluation_weight_hash: str = ""
    tail_deficit: float = 0.0
    tail_deficit_limit: float | None = None
    implied_credit_price: float | None = None
    credit_constraint_binding: bool = False
    objective_kind: str = "cvar"


def _finite_nonnegative(value: float) -> bool:
    return isfinite(value) and value >= 0.0


def _scalar_value(value: object) -> float | None:
    if value is None:
        return None
    array = np.asarray(value)
    if array.size != 1:
        return None
    result = float(array.item())
    return result if isfinite(result) else None


def _bound_tolerance(lower: float, upper: float) -> float:
    return _NUMERICAL_TOLERANCE * max(1.0, abs(lower), abs(upper))


def _bounded_solution(value: object, lower: float, upper: float) -> float | None:
    result = _scalar_value(value)
    if result is None:
        return None
    tolerance = _bound_tolerance(lower, upper)
    if result < lower - tolerance or result > upper + tolerance:
        return None
    return float(np.clip(result, lower, upper))


def _trim_redundant_liquidation(
    balances: np.ndarray,
    liquidation: float,
    settlement_column: int,
    operating_buffer: float,
    buffer_tolerance: float,
    weights: np.ndarray | None = None,
    tail_deficit_limit: float | None = None,
    q: float = 0.95,
) -> float:
    """Remove surplus from a sale with zero tax cost, holding other levers fixed.

    With no assumed tax benefit, multiple sale amounts can have the same
    objective. Reduce proceeds only where every post-settlement balance
    remains nonnegative and the mean buffer dollar-day constraint holds.
    This preserves every path's cost without an invented penalty weight or
    a second solver run. It does not claim a global minimum-sale solution.
    """
    if liquidation <= 0.0:
        return liquidation
    settled = balances[:, settlement_column:]
    removable = min(
        liquidation, max(0.0, float(np.min(settled)) - _NUMERICAL_TOLERANCE)
    )
    if removable <= 0.0:
        return liquidation

    w = probabilities(len(balances), weights)
    fixed_shortfall = np.maximum(0.0, operating_buffer - balances[:, :settlement_column]).sum(axis=1)

    def fits_buffer(reduction: float) -> bool:
        shortfall = fixed_shortfall + np.maximum(
            0.0, operating_buffer - settled + reduction
        ).sum(axis=1)
        if np.dot(w, shortfall) > buffer_tolerance:
            return False
        if tail_deficit_limit is not None:
            adjusted = balances.copy()
            adjusted[:, settlement_column:] -= reduction
            deficits = np.maximum(0.0, operating_buffer - adjusted.min(axis=1))
            if cvar(deficits, q, w) > tail_deficit_limit:
                return False
        return True

    if fits_buffer(removable):
        return liquidation - removable

    lower, upper = 0.0, removable
    for _ in range(40):
        middle = (lower + upper) / 2.0
        if fits_buffer(middle):
            lower = middle
        else:
            upper = middle
    return liquidation - lower


def optimize_funding(
    state: FinancialState,
    bundle: DrawBundle,
    obligations: Sequence[Obligation],
    coverage_target: float = 0.95,
    operating_buffer: float = 1000.0,
    overdraft_apr: float = 0.2999,
    buffer_tolerance_dollar_days: float | None = None,
    capital_gains_rate: float = 0.15,
    *,
    weights: np.ndarray | None = None,
    tail_deficit_limit: float | None = None,
    objective_kind: Literal["cvar", "expected"] = "cvar",
    time_limit_seconds: float = SOLVER_TIME_LIMIT_SECONDS,
) -> OptimalPlan | OptimizationFailure:
    """Return the bounded CLARABEL CVaR-optimal funding mix, if it solves.

    The scalar credit leg is deliberately limited to the funding module's
    primary account: it uses that account's payment timing, APR, and available
    credit rather than applying one card's APR to a sum of unrelated limits.
    Material payment and settlement events extend the supplied draw bundle by
    the same spec-14 mechanism used for ordinary funding-plan evaluation.

    ``coverage_target == 1`` is the empirical worst-case objective. Other
    targets in ``[0, 1)`` use the Rockafellar-Uryasev CVaR formulation.
    Returns an ``OptimizationFailure`` with a stable reason when unavailable,
    infeasible, resource-limited, or rejected by the numerical checks.
    """
    q = float(coverage_target)
    if not isfinite(q) or q < 0.0 or q > 1.0:
        return OptimizationFailure("invalid_input")
    if not _finite_nonnegative(float(operating_buffer)):
        return OptimizationFailure("invalid_input")
    if not _finite_nonnegative(float(overdraft_apr)):
        return OptimizationFailure("invalid_input")
    if not _finite_nonnegative(float(capital_gains_rate)):
        return OptimizationFailure("invalid_input")
    if buffer_tolerance_dollar_days is not None and not _finite_nonnegative(
        float(buffer_tolerance_dollar_days)
    ):
        return OptimizationFailure("invalid_input")
    if bundle.n_paths <= 0 or bundle.horizon_days <= 0:
        return OptimizationFailure("invalid_input")
    if (tail_deficit_limit is not None and not _finite_nonnegative(tail_deficit_limit)) or objective_kind not in ("cvar", "expected"):
        return OptimizationFailure("invalid_input")
    if not isfinite(time_limit_seconds) or time_limit_seconds <= 0:
        return OptimizationFailure("invalid_input")
    try:
        w = probabilities(bundle.n_paths, weights)
    except ValueError:
        return OptimizationFailure("invalid_input")
    funding_config = FundingConfig()
    primary_account = _select_primary_credit_account(state)
    available_credit = (
        float(primary_account.available_credit) if primary_account is not None else 0.0
    )
    initial_market_value = float(state.marketable_backup_capital)
    if not _finite_nonnegative(available_credit) or not _finite_nonnegative(initial_market_value):
        return OptimizationFailure("invalid_input")

    credit_due_day = 0
    interest_per_credit_dollar = 0.0
    if primary_account is not None and available_credit > 0.0:
        due_offset = _next_charge_payment_offset(state.as_of, primary_account)
        credit_due_day = max(1, due_offset)
        grace_applies = (
            primary_account.grace_period_eligible and primary_account.current_balance <= 0.0
        )
        if not grace_applies:
            interest_per_credit_dollar = primary_account.purchase_apr / 365.0 * due_offset
            if not _finite_nonnegative(interest_per_credit_dollar):
                return OptimizationFailure("invalid_input")

    settlement_day = max(
        1, funding_config.settlement_days + funding_config.external_transfer_days
    )
    material_days = [bundle.horizon_days]
    if available_credit > 0.0:
        material_days.append(credit_due_day)
    if initial_market_value > 0.0:
        material_days.append(settlement_day)
    latest_material_day = max(material_days)
    evaluation_horizon = (
        latest_material_day
        if latest_material_day <= bundle.horizon_days
        else latest_material_day + funding_config.trailing_days
    )
    if bundle.n_paths * evaluation_horizon > MAX_SCENARIO_DAYS:
        return OptimizationFailure("resource_limit")
    evaluation_bundle = extend_draw_bundle(bundle, evaluation_horizon)

    try:
        import cvxpy as cp
    except ImportError:
        return OptimizationFailure("cvxpy_unavailable")
    if cp.CLARABEL not in cp.installed_solvers():
        return OptimizationFailure("solver_unavailable")

    baseline_cash = cash_paths(state, evaluation_bundle, obligations)
    discretionary_savings = np.cumsum(
        discretionary_resampled_paths(state, evaluation_bundle), axis=1
    )
    n_paths, horizon_days = baseline_cash.shape
    if (
        baseline_cash.shape != (evaluation_bundle.n_paths, evaluation_bundle.horizon_days)
        or discretionary_savings.shape != baseline_cash.shape
        or n_paths != bundle.n_paths
        or horizon_days != evaluation_horizon
    ):
        return OptimizationFailure("invalid_input")
    if not np.all(np.isfinite(baseline_cash)) or not np.all(np.isfinite(discretionary_savings)):
        return OptimizationFailure("invalid_input")
    if available_credit == 0.0 and initial_market_value == 0.0 and not np.any(discretionary_savings > 0.0):
        return OptimizationFailure("no_funding_levers")
    credit_effect_daily = np.zeros(horizon_days, dtype=float)
    if available_credit > 0.0:
        credit_effect_daily[0] = 1.0
        credit_effect_daily[credit_due_day - 1] -= 1.0 + interest_per_credit_dollar
    credit_effect = np.cumsum(credit_effect_daily)

    settlement_column = settlement_day - 1
    liquidation_effect = np.zeros((n_paths, horizon_days), dtype=float)
    liquidation_effect[:, settlement_column:] = 1.0
    total_cost_basis = float(sum(holding.cost_basis for holding in state.taxable_portfolio))
    if not isfinite(total_cost_basis):
        return OptimizationFailure("invalid_input")
    cost_basis_fraction = total_cost_basis / max(initial_market_value, 1e-9)
    if not isfinite(cost_basis_fraction):
        return OptimizationFailure("invalid_input")

    # A proportional sale disposes the same fraction of every taxable lot
    # at today's prices. Loss relief depends on the household's wider tax
    # situation, so it cannot subsidize the objective or fund a cash path.
    tax_per_liquidation_dollar = max(0.0, 1.0 - cost_basis_fraction) * capital_gains_rate
    if not _finite_nonnegative(tax_per_liquidation_dollar):
        return OptimizationFailure("invalid_input")

    deferred_cost_per_fraction = float(np.dot(w, discretionary_savings[:, -1]))
    if not isfinite(deferred_cost_per_fraction):
        return OptimizationFailure("invalid_input")
    if buffer_tolerance_dollar_days is None:
        buffer_tolerance = (
            operating_buffer
            * horizon_days
            * FundingPolicy().max_cash_shortfall_probability
        )
    else:
        buffer_tolerance = float(buffer_tolerance_dollar_days)

    credit = cp.Variable(nonneg=True)
    liquidation = cp.Variable(nonneg=True)
    deferral_fraction = cp.Variable(nonneg=True)
    eta = cp.Variable()

    credit_effect_matrix = np.broadcast_to(credit_effect, (n_paths, horizon_days))
    # Drop only hinge terms that are provably zero throughout the control
    # bounds. All paths remain in the objective and its probability weights.
    # This avoids solving for two auxiliaries on every already-funded day.
    minimum_balance = (
        float(state.immediate_funding) + baseline_cash
        + np.minimum(0.0, available_credit * credit_effect_matrix)
        + np.minimum(0.0, initial_market_value * liquidation_effect)
        + np.minimum(0.0, discretionary_savings)
    )

    def selected_balance(rows: np.ndarray, columns: np.ndarray):
        return (
            float(state.immediate_funding) + baseline_cash[rows, columns]
            + credit * credit_effect[columns]
            + liquidation * liquidation_effect[rows, columns]
            + deferral_fraction * discretionary_savings[rows, columns]
        )

    credit_constraint = credit <= available_credit
    constraints = [
        credit_constraint,
        liquidation <= initial_market_value,
        deferral_fraction <= 1.0,
    ]
    buffer_rows, buffer_columns = np.nonzero(minimum_balance < operating_buffer)
    buffer_total = cp.Constant(0.0)
    if buffer_rows.size:
        buffer_shortfall = cp.Variable(buffer_rows.size, nonneg=True)
        constraints.append(
            buffer_shortfall >= operating_buffer - selected_balance(buffer_rows, buffer_columns)
        )
        buffer_total = w[buffer_rows] @ buffer_shortfall
    buffer_constraint = buffer_total <= buffer_tolerance
    constraints.append(buffer_constraint)

    if tail_deficit_limit is not None:
        worst_buffer_deficit = cp.Variable(n_paths, nonneg=True)
        if buffer_rows.size:
            constraints.append(worst_buffer_deficit[buffer_rows] >= operating_buffer - selected_balance(buffer_rows, buffer_columns))
        if q == 1:
            constraints.append(worst_buffer_deficit[w > 0] <= tail_deficit_limit)
        else:
            deficit_eta = cp.Variable()
            deficit_excess = cp.Variable(n_paths, nonneg=True)
            constraints.append(deficit_excess >= worst_buffer_deficit - deficit_eta)
            constraints.append(deficit_eta + w @ deficit_excess / (1 - q) <= tail_deficit_limit)

    overdraft_rows, overdraft_columns = np.nonzero(minimum_balance < 0.0)
    overdraft_cost = cp.Constant(np.zeros(n_paths))
    if overdraft_rows.size and overdraft_apr > 0.0:
        overdraft = cp.Variable(overdraft_rows.size, nonneg=True)
        constraints.append(overdraft >= -selected_balance(overdraft_rows, overdraft_columns))
        per_path_sum = csr_matrix(
            (np.ones(overdraft_rows.size), (overdraft_rows, np.arange(overdraft_rows.size))),
            shape=(n_paths, overdraft_rows.size),
        )
        overdraft_cost = (overdraft_apr / 365.0) * (per_path_sum @ overdraft)
    tax_cost = liquidation * tax_per_liquidation_dollar
    path_cost = (
        interest_per_credit_dollar * credit
        + discretionary_savings[:, -1] * deferral_fraction
        + tax_cost
        + overdraft_cost
    )

    if q == 1.0:
        constraints.append(eta >= path_cost[w > 0])
        objective = eta
    else:
        cvar_excess = cp.Variable(n_paths, nonneg=True)
        constraints.append(cvar_excess >= path_cost - eta)
        objective = eta + w @ cvar_excess / (1.0 - q)

    if objective_kind == "expected":
        objective = w @ path_cost

    problem = cp.Problem(cp.Minimize(objective), constraints)
    try:
        problem.solve(
            solver=cp.CLARABEL,
            verbose=False,
            time_limit=time_limit_seconds,
        )
    except cp.error.SolverError:
        return OptimizationFailure("solver_error")

    status = str(problem.status or "")
    if status == cp.USER_LIMIT:
        solve_time = getattr(problem.solver_stats, "solve_time", None)
        reason = (
            "solver_timeout"
            if solve_time is not None and solve_time >= time_limit_seconds
            else "solver_limit"
        )
        return OptimizationFailure(reason)
    if status in (cp.INFEASIBLE, cp.INFEASIBLE_INACCURATE):
        return OptimizationFailure("infeasible")
    if status in (cp.UNBOUNDED, cp.UNBOUNDED_INACCURATE):
        return OptimizationFailure("unbounded")
    if status not in _OPTIMAL_STATUSES:
        return OptimizationFailure("solver_error")

    credit_value = _bounded_solution(credit.value, 0.0, available_credit)
    liquidation_value = _bounded_solution(liquidation.value, 0.0, initial_market_value)
    deferral_value = _bounded_solution(deferral_fraction.value, 0.0, 1.0)
    eta_value = _scalar_value(eta.value)
    cvar_value = _scalar_value(problem.value)
    if (
        credit_value is None
        or liquidation_value is None
        or deferral_value is None
        or eta_value is None
        or cvar_value is None
    ):
        return OptimizationFailure("invalid_solution")
    if deferred_cost_per_fraction == 0.0:
        # A free auxiliary choice cannot imply reducing nonexistent spending.
        deferral_value = 0.0

    adjusted_balance_value = (
        float(state.immediate_funding)
        + baseline_cash
        + credit_value * credit_effect_matrix
        + liquidation_value * liquidation_effect
        + deferral_value * discretionary_savings
    )
    if not np.all(np.isfinite(adjusted_balance_value)):
        return OptimizationFailure("invalid_solution")

    if tax_per_liquidation_dollar == 0.0:
        trimmed = _trim_redundant_liquidation(
            adjusted_balance_value, liquidation_value, settlement_column,
            operating_buffer, buffer_tolerance,
            w, tail_deficit_limit, q,
        )
        adjusted_balance_value -= (liquidation_value - trimmed) * liquidation_effect
        liquidation_value = trimmed

    actual_buffer_shortfall = float(
        np.dot(w, np.maximum(0.0, operating_buffer - adjusted_balance_value).sum(axis=1))
    )
    buffer_feasibility_tolerance = _NUMERICAL_TOLERANCE * max(1.0, abs(buffer_tolerance))
    if actual_buffer_shortfall > buffer_tolerance + buffer_feasibility_tolerance:
        return OptimizationFailure("invalid_solution")
    actual_tail_deficit = cvar(np.maximum(0.0, operating_buffer - adjusted_balance_value.min(axis=1)), q, w)
    if tail_deficit_limit is not None and actual_tail_deficit > tail_deficit_limit + _NUMERICAL_TOLERANCE * max(1.0, tail_deficit_limit):
        return OptimizationFailure("invalid_solution")

    actual_overdraft_cost = (overdraft_apr / 365.0) * np.maximum(
        0.0, -adjusted_balance_value
    ).sum(axis=1)
    tax_cost_value = liquidation_value * tax_per_liquidation_dollar
    path_cost_value = (
        interest_per_credit_dollar * credit_value
        + discretionary_savings[:, -1] * deferral_value
        + tax_cost_value
        + actual_overdraft_cost
    )
    if not np.all(np.isfinite(path_cost_value)):
        return OptimizationFailure("invalid_solution")
    if q == 1.0:
        maximum_path_cost = float(np.max(path_cost_value[w > 0]))
        eta_feasibility_tolerance = _NUMERICAL_TOLERANCE * max(
            1.0, abs(eta_value), abs(maximum_path_cost)
        )
        if eta_value < maximum_path_cost - eta_feasibility_tolerance:
            return OptimizationFailure("invalid_solution")

    expected_cost = float(np.dot(w, path_cost_value))
    # Report observed variation in this plan's costs, including cash-flow
    # risk without market history. Market data alone cannot make this true.
    cost_is_path_dependent = bool(
        np.ptp(path_cost_value)
        > _NUMERICAL_TOLERANCE * max(1.0, float(np.max(np.abs(path_cost_value))))
    )
    cash_shortfall_probability = float(
        np.dot(w, np.any(adjusted_balance_value < 0.0, axis=1))
    )
    if not isfinite(expected_cost) or not isfinite(cash_shortfall_probability):
        return OptimizationFailure("invalid_solution")

    dual_value = _scalar_value(buffer_constraint.dual_value)
    if dual_value is None:
        implied_liquidity_price = None
    elif dual_value < -_NUMERICAL_TOLERANCE:
        return OptimizationFailure("invalid_solution")
    else:
        implied_liquidity_price = max(0.0, dual_value)

    return OptimalPlan(
        credit_draw=credit_value,
        liquidation_amount=liquidation_value,
        deferral_fraction=deferral_value,
        cvar_cost=cvar(path_cost_value, q, w),
        var_cost=quantile(path_cost_value, q, w),
        expected_cost=expected_cost,
        cash_shortfall_probability=cash_shortfall_probability,
        implied_liquidity_price=implied_liquidity_price,
        cost_is_path_dependent=cost_is_path_dependent,
        solver_status=status,
        evaluation_horizon_days=evaluation_bundle.horizon_days,
        evaluation_draw_id=evaluation_bundle.bootstrap_draw_id,
        evaluation_paths=n_paths,
        cost_coverage_target=q,
        buffer_breach_probability=float(np.dot(w, np.any(adjusted_balance_value < operating_buffer, axis=1))),
        dollar_days_below_buffer=actual_buffer_shortfall,
        buffer_tolerance_dollar_days=buffer_tolerance,
        buffer_constraint_binding=abs(buffer_tolerance - actual_buffer_shortfall) <= buffer_feasibility_tolerance,
        evaluation_weight_hash=weight_hash(w),
        tail_deficit=actual_tail_deficit,
        tail_deficit_limit=tail_deficit_limit,
        implied_credit_price=_scalar_value(credit_constraint.dual_value),
        credit_constraint_binding=abs(available_credit - credit_value) <= _bound_tolerance(0, available_credit),
        objective_kind=objective_kind,
    )
