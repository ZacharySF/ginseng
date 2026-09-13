"""CVaR-optimal funding plan (Telser safety-first + Rockafellar-Uryasev).

The model evaluates every supplied bootstrap path under common random numbers.
Buffer-shortfall and overdraft auxiliaries are created only for path-days that
can incur those costs under the control bounds. Provably zero terms are omitted,
never paths or their probability weights. Requests whose evaluation bundle or
complete exact tax-lot partition exceeds the resource bounds fail closed with
``None``.

The default Telser tolerance is a *mean* dollar-day limit:
``operating_buffer * evaluation_horizon_days * policy shortfall probability``.
It allows the same aggregate buffer erosion as fully missing the operating
buffer on the policy's permitted fraction of forecast days, and is independent
of the number of bootstrap paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from time import monotonic
from typing import Sequence

import numpy as np
from scipy.sparse import csr_matrix

from ginseng.funding import (
    FundingConfig,
    LiquidationBasisSegment,
    _next_charge_payment_offset,
    _select_primary_credit_account,
    extend_draw_bundle,
    liquidation_basis_segments,
    liquidation_cost_basis,
    settlement_forecast_day,
)
from ginseng.policy import FundingPolicy
from ginseng.simulate import (
    DrawBundle,
    PathBundle,
    cash_paths,
    discretionary_resampled_paths,
    portfolio_value_paths,
)
from ginseng.state import FinancialState, Obligation

# Keep the worst-case LP within an interactive request's memory/time envelope.
# This covers the UI's 14/30/60-day horizons at up to 3,000 paths; larger
# evaluations omit the optional optimizer, never substitute fewer paths.
MAX_SCENARIO_DAYS = 200_000
# Every branch must be solved before an optimum is returned, so this bound
# fails closed instead of silently searching only the first tax lots.
MAX_LIQUIDATION_SEGMENTS = 256
SOLVER_TIME_LIMIT_SECONDS = 3.0
_NUMERICAL_TOLERANCE = 1e-6
_OPTIMAL_STATUSES = frozenset(("optimal", "optimal_inaccurate"))
_INFEASIBLE_STATUSES = frozenset(("infeasible",))

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


def _empirical_cvar(path_cost: np.ndarray, coverage_target: float) -> float | None:
    """Return the equally weighted upper-tail mean represented by the LP."""
    if path_cost.ndim != 1 or path_cost.size == 0 or not np.all(np.isfinite(path_cost)):
        return None
    if coverage_target == 1.0:
        return float(np.max(path_cost))

    tail_weight = (1.0 - coverage_target) * path_cost.size
    if not isfinite(tail_weight) or tail_weight <= 0.0:
        return None
    ordered_costs = np.sort(path_cost)[::-1]
    whole_paths = min(path_cost.size, int(np.floor(tail_weight)))
    fractional_path = tail_weight - whole_paths
    tail_total = float(np.sum(ordered_costs[:whole_paths]))
    if fractional_path > 0.0 and whole_paths < path_cost.size:
        tail_total += fractional_path * float(ordered_costs[whole_paths])
    return tail_total / tail_weight


def optimize_funding(
    state: FinancialState,
    bundle: DrawBundle | PathBundle,
    obligations: Sequence[Obligation],
    coverage_target: float = 0.95,
    operating_buffer: float = 1000.0,
    overdraft_apr: float = 0.2999,
    buffer_tolerance_dollar_days: float | None = None,
    capital_gains_rate: float = 0.15,
    funding_config: FundingConfig | None = None,
    funding_policy: FundingPolicy | None = None,
) -> OptimalPlan | None:
    """Return the bounded CLARABEL CVaR-optimal funding mix, if it solves.

    The credit leg uses only the funding module's primary card and respects
    both that account's available credit and the supplied policy's utilization
    ceiling. Taxable liquidation is partitioned at every exact pro-rata
    FIFO/HIFO lot boundary, so each solved branch has its real affine disposed
    basis. A branch that cannot be solved or checked invalidates the optional
    result rather than allowing a partial search to be marketed as optimal.

    Material payment and settlement events extend the supplied draw bundle by
    the same mechanism used for ordinary funding-plan evaluation. A funding
    decision may not assume discretionary cuts after the visible decision
    horizon. ``coverage_target == 1`` is the empirical worst-case objective;
    other targets use the Rockafellar-Uryasev CVaR formulation.
    """
    q = float(coverage_target)
    if not isfinite(q) or q < 0.0 or q > 1.0:
        return None
    if not _finite_nonnegative(float(operating_buffer)):
        return None
    if not _finite_nonnegative(float(overdraft_apr)):
        return None
    if not _finite_nonnegative(float(capital_gains_rate)):
        return None
    if buffer_tolerance_dollar_days is not None and not _finite_nonnegative(
        float(buffer_tolerance_dollar_days)
    ):
        return None
    if bundle.n_paths <= 0 or bundle.horizon_days <= 0:
        return None
    if not state.credit_accounts and not state.taxable_portfolio:
        return None

    resolved_funding_policy = funding_policy or FundingPolicy()
    max_cash_shortfall_probability = float(
        resolved_funding_policy.max_cash_shortfall_probability
    )
    max_credit_utilization = float(resolved_funding_policy.max_credit_utilization)
    if (
        not isfinite(max_cash_shortfall_probability)
        or not 0.0 <= max_cash_shortfall_probability <= 1.0
        or not isfinite(max_credit_utilization)
        or not 0.0 <= max_credit_utilization <= 1.0
    ):
        return None

    resolved_funding_config = funding_config or FundingConfig()
    primary_account = _select_primary_credit_account(state)
    available_credit = 0.0
    if primary_account is not None:
        credit_limit = float(primary_account.credit_limit)
        current_balance = float(primary_account.current_balance)
        raw_available_credit = float(primary_account.available_credit)
        if (
            not _finite_nonnegative(credit_limit)
            or not _finite_nonnegative(current_balance)
            or not _finite_nonnegative(raw_available_credit)
        ):
            return None
        utilization_capacity = max(
            0.0,
            credit_limit * max_credit_utilization - current_balance,
        )
        available_credit = min(raw_available_credit, utilization_capacity)

    initial_market_value = float(state.marketable_backup_capital)
    if not _finite_nonnegative(initial_market_value):
        return None

    if initial_market_value > 0.0:
        liquidation_segments = liquidation_basis_segments(
            state.taxable_portfolio,
            resolved_funding_config.lot_selection,
            resolved_funding_config.specific_lot_ids,
            max_segments=MAX_LIQUIDATION_SEGMENTS,
        )
        if not liquidation_segments:
            return None
        if abs(liquidation_segments[-1].upper_proceeds - initial_market_value) > _bound_tolerance(
            liquidation_segments[-1].upper_proceeds,
            initial_market_value,
        ):
            return None
    else:
        liquidation_segments = (
            LiquidationBasisSegment(
                lower_proceeds=0.0,
                upper_proceeds=0.0,
                cost_basis_intercept=0.0,
                cost_basis_slope=0.0,
            ),
        )
    if any(
        not all(
            isfinite(value)
            for value in (
                segment.lower_proceeds,
                segment.upper_proceeds,
                segment.cost_basis_intercept,
                segment.cost_basis_slope,
            )
        )
        or segment.lower_proceeds < 0.0
        or segment.upper_proceeds < segment.lower_proceeds
        for segment in liquidation_segments
    ):
        return None
    if (
        abs(liquidation_segments[0].lower_proceeds)
        > _bound_tolerance(0.0, liquidation_segments[0].lower_proceeds)
        or any(
            abs(previous.upper_proceeds - following.lower_proceeds)
            > _bound_tolerance(
                previous.upper_proceeds,
                following.lower_proceeds,
            )
            for previous, following in zip(
                liquidation_segments,
                liquidation_segments[1:],
            )
        )
    ):
        return None

    credit_due_day = 0
    interest_per_credit_dollar = 0.0
    if primary_account is not None and available_credit > 0.0:
        credit_due_day = _next_charge_payment_offset(
            state.as_of,
            primary_account,
            one_indexed=resolved_funding_config.use_business_days,
        )
        grace_applies = (
            primary_account.grace_period_eligible and primary_account.current_balance <= 0.0
        )
        if not grace_applies:
            elapsed_days = (
                credit_due_day - 1
                if resolved_funding_config.use_business_days
                else credit_due_day
            )
            interest_per_credit_dollar = primary_account.purchase_apr / 365.0 * elapsed_days
            if not _finite_nonnegative(interest_per_credit_dollar):
                return None

    settlement_day = settlement_forecast_day(
        state.as_of,
        resolved_funding_config.settlement_days,
        resolved_funding_config.external_transfer_days,
        use_business_days=resolved_funding_config.use_business_days,
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
        else latest_material_day + resolved_funding_config.trailing_days
    )
    if bundle.n_paths * evaluation_horizon > MAX_SCENARIO_DAYS:
        return None
    try:
        evaluation_bundle = extend_draw_bundle(bundle, evaluation_horizon)
    except ValueError:
        return None

    try:
        import cvxpy as cp
    except ImportError:
        return None
    if cp.CLARABEL not in cp.installed_solvers():
        return None

    baseline_cash = cash_paths(state, evaluation_bundle, obligations)
    discretionary_savings = np.cumsum(
        discretionary_resampled_paths(state, evaluation_bundle), axis=1
    )
    portfolio_values = portfolio_value_paths(state, evaluation_bundle)
    n_paths, horizon_days = baseline_cash.shape
    # A funding decision may be evaluated through a later repayment date, but
    # it must not pay for that debt by assuming discretionary cuts beyond the
    # user-visible decision horizon.
    if bundle.horizon_days < horizon_days:
        discretionary_savings[:, bundle.horizon_days:] = discretionary_savings[
            :, [bundle.horizon_days - 1]
        ]
    if (
        baseline_cash.shape != (evaluation_bundle.n_paths, evaluation_bundle.horizon_days)
        or discretionary_savings.shape != baseline_cash.shape
        or n_paths != bundle.n_paths
        or horizon_days != evaluation_horizon
    ):
        return None
    if not np.all(np.isfinite(baseline_cash)) or not np.all(np.isfinite(discretionary_savings)):
        return None
    if portfolio_values is not None and (
        portfolio_values.shape != baseline_cash.shape or not np.all(np.isfinite(portfolio_values))
    ):
        return None

    credit_effect_daily = np.zeros(horizon_days, dtype=float)
    if available_credit > 0.0:
        credit_effect_daily[0] = 1.0
        credit_effect_daily[credit_due_day - 1] -= 1.0 + interest_per_credit_dollar
    credit_effect = np.cumsum(credit_effect_daily)
    credit_effect_matrix = np.broadcast_to(credit_effect, (n_paths, horizon_days))

    settlement_column = settlement_day - 1
    liquidation_effect = np.zeros((n_paths, horizon_days), dtype=float)
    settlement_scale = np.zeros(n_paths, dtype=float)
    cost_is_path_dependent = portfolio_values is not None
    if initial_market_value > 0.0:
        if portfolio_values is not None:
            settlement_scale = portfolio_values[:, settlement_column] / initial_market_value
            liquidation_effect[:, settlement_column:] = settlement_scale[:, np.newaxis]
        else:
            settlement_scale.fill(1.0)
            liquidation_effect[:, settlement_column:] = 1.0
    if not np.all(np.isfinite(liquidation_effect)) or not np.all(np.isfinite(settlement_scale)):
        return None

    deferred_cost_per_fraction = float(np.mean(discretionary_savings[:, -1]))
    if not isfinite(deferred_cost_per_fraction):
        return None
    if buffer_tolerance_dollar_days is None:
        buffer_tolerance = (
            operating_buffer * horizon_days * max_cash_shortfall_probability
        )
    else:
        buffer_tolerance = float(buffer_tolerance_dollar_days)

    credit = cp.Variable(nonneg=True)
    liquidation = cp.Variable(nonneg=True)
    deferral_fraction = cp.Variable(nonneg=True)
    eta = cp.Variable()
    # CVXPY permits repeated solves of one immutable problem through Parameter
    # values: https://www.cvxpy.org/api_reference/cvxpy.problems.html
    segment_lower = cp.Parameter(nonneg=True)
    segment_upper = cp.Parameter(nonneg=True)
    segment_basis_intercept = cp.Parameter()
    segment_basis_slope = cp.Parameter()

    # Drop only hinge terms that are provably zero throughout the control
    # bounds. All paths remain in the objective and its probability weights.
    # This avoids solving for two auxiliaries on every already-funded day.
    minimum_balance = (
        float(state.immediate_funding)
        + baseline_cash
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

    constraints = [
        credit <= available_credit,
        liquidation >= segment_lower,
        liquidation <= segment_upper,
        deferral_fraction <= 1.0,
    ]
    buffer_rows, buffer_columns = np.nonzero(minimum_balance < operating_buffer)
    buffer_total = cp.Constant(0.0)
    if buffer_rows.size:
        buffer_shortfall = cp.Variable(buffer_rows.size, nonneg=True)
        constraints.append(
            buffer_shortfall >= operating_buffer - selected_balance(buffer_rows, buffer_columns)
        )
        buffer_total = cp.sum(buffer_shortfall)
    buffer_constraint = buffer_total / n_paths <= buffer_tolerance
    constraints.append(buffer_constraint)

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
    tax_cost = capital_gains_rate * cp.pos(
        cp.multiply(settlement_scale, liquidation)
        - segment_basis_intercept
        - segment_basis_slope * liquidation
    )
    path_cost = (
        interest_per_credit_dollar * credit
        + deferred_cost_per_fraction * deferral_fraction
        + tax_cost
        + overdraft_cost
    )

    if q == 1.0:
        constraints.append(eta >= path_cost)
        objective = eta
    else:
        cvar_excess = cp.Variable(n_paths, nonneg=True)
        constraints.append(cvar_excess >= path_cost - eta)
        objective = eta + cp.sum(cvar_excess) / ((1.0 - q) * n_paths)

    problem = cp.Problem(cp.Minimize(objective), constraints)
    # The deadline covers the complete partition, never each branch in isolation.
    deadline = monotonic() + SOLVER_TIME_LIMIT_SECONDS
    best_plan: OptimalPlan | None = None
    for segment in liquidation_segments:
        segment_lower.value = segment.lower_proceeds
        segment_upper.value = segment.upper_proceeds
        segment_basis_intercept.value = segment.cost_basis_intercept
        segment_basis_slope.value = segment.cost_basis_slope
        remaining_seconds = deadline - monotonic()
        if remaining_seconds <= 0.0:
            return None
        try:
            problem.solve(
                solver=cp.CLARABEL,
                verbose=False,
                time_limit=remaining_seconds,
                warm_start=True,
            )
        except cp.error.SolverError:
            return None
        if monotonic() > deadline:
            return None

        status = str(problem.status or "")
        if status in _INFEASIBLE_STATUSES:
            continue
        if status not in _OPTIMAL_STATUSES:
            return None

        credit_value = _bounded_solution(credit.value, 0.0, available_credit)
        liquidation_value = _bounded_solution(
            liquidation.value,
            segment.lower_proceeds,
            segment.upper_proceeds,
        )
        deferral_value = _bounded_solution(deferral_fraction.value, 0.0, 1.0)
        eta_value = _scalar_value(eta.value)
        objective_value = _scalar_value(problem.value)
        if (
            credit_value is None
            or liquidation_value is None
            or deferral_value is None
            or eta_value is None
            or objective_value is None
        ):
            return None

        exact_basis = liquidation_cost_basis(
            state.taxable_portfolio,
            liquidation_value,
            resolved_funding_config.lot_selection,
            resolved_funding_config.specific_lot_ids,
        )
        modeled_basis = (
            segment.cost_basis_intercept
            + segment.cost_basis_slope * liquidation_value
        )
        if (
            not isfinite(exact_basis)
            or not isfinite(modeled_basis)
            or abs(exact_basis - modeled_basis)
            > _bound_tolerance(exact_basis, modeled_basis)
        ):
            return None

        adjusted_balance_value = (
            float(state.immediate_funding)
            + baseline_cash
            + credit_value * credit_effect_matrix
            + liquidation_value * liquidation_effect
            + deferral_value * discretionary_savings
        )
        if not np.all(np.isfinite(adjusted_balance_value)):
            return None

        actual_buffer_shortfall = float(
            np.maximum(0.0, operating_buffer - adjusted_balance_value).sum() / n_paths
        )
        buffer_feasibility_tolerance = _NUMERICAL_TOLERANCE * max(
            1.0,
            abs(buffer_tolerance),
        )
        if actual_buffer_shortfall > buffer_tolerance + buffer_feasibility_tolerance:
            return None

        actual_overdraft_cost = (overdraft_apr / 365.0) * np.maximum(
            0.0,
            -adjusted_balance_value,
        ).sum(axis=1)
        tax_cost_value = capital_gains_rate * np.maximum(
            0.0,
            settlement_scale * liquidation_value - exact_basis,
        )
        path_cost_value = (
            interest_per_credit_dollar * credit_value
            + deferred_cost_per_fraction * deferral_value
            + tax_cost_value
            + actual_overdraft_cost
        )
        cvar_value = _empirical_cvar(path_cost_value, q)
        if cvar_value is None or not np.all(np.isfinite(path_cost_value)):
            return None
        if abs(objective_value - cvar_value) > _bound_tolerance(
            objective_value,
            cvar_value,
        ):
            return None
        if q == 1.0:
            maximum_path_cost = float(np.max(path_cost_value))
            if eta_value < maximum_path_cost - _bound_tolerance(
                eta_value,
                maximum_path_cost,
            ):
                return None

        expected_cost = float(np.mean(path_cost_value))
        cash_shortfall_probability = float(
            np.mean(np.any(adjusted_balance_value < 0.0, axis=1))
        )
        if (
            not isfinite(expected_cost)
            or not isfinite(cash_shortfall_probability)
            or expected_cost < -_NUMERICAL_TOLERANCE
        ):
            return None

        dual_value = _scalar_value(buffer_constraint.dual_value)
        if dual_value is None:
            implied_liquidity_price = None
        elif dual_value < -_NUMERICAL_TOLERANCE:
            return None
        else:
            implied_liquidity_price = max(0.0, dual_value)

        candidate = OptimalPlan(
            credit_draw=credit_value,
            liquidation_amount=liquidation_value,
            deferral_fraction=deferral_value,
            cvar_cost=cvar_value,
            var_cost=eta_value,
            expected_cost=expected_cost,
            cash_shortfall_probability=cash_shortfall_probability,
            implied_liquidity_price=implied_liquidity_price,
            cost_is_path_dependent=cost_is_path_dependent,
            solver_status=status,
        )
        if best_plan is None or candidate.cvar_cost < best_plan.cvar_cost:
            best_plan = candidate

    return best_plan
