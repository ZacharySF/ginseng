"""Shared scenario metrics, funding, and response serialization.

The demo endpoint and authenticated personal forecasts both enter this module
with an already-built financial state and one reusable path bundle.  Keeping the
pipeline here prevents a personal forecast from becoming a second, divergent
set of liquidity and funding calculations.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Sequence

import numpy as np
from pydantic import BaseModel, Field

from ginseng import uncertainty
from ginseng.funding import (
    FundingConfig,
    build_candidates,
    evaluate_plan,
    extend_draw_bundle,
    plan_evaluation_horizon,
)
from ginseng.metrics import compute_scenario_metrics
from ginseng.optimizer import (
    SOLVER_TIME_LIMIT_SECONDS,
    OptimalPlan,
    OptimizationFailure,
    OptimizationFailureReason,
    optimize_funding,
)
from ginseng.policy import FundingPolicy, recommend, to_contract
from ginseng.simulate import DrawBundle, PathBundle
from ginseng.state import FinancialState, Obligation


class SeverityMetrics(BaseModel):
    cash_shortfall_probability: float
    avg_cash_deficit_when_short: float
    dollar_days_below_buffer: float


class CoveragePoint(BaseModel):
    funding: float
    coverage: float


class ReserveBufferPoint(BaseModel):
    operating_buffer: float
    required_liquidity_reserve: float


class CashPaths(BaseModel):
    days: list[int]
    p10: list[float]
    p50: list[float]
    p90: list[float]
    known_income: list[float]
    known_obligations: list[float]


class ShortfallDistribution(BaseModel):
    bin_edges: list[float]
    counts: list[int]

    probabilities: list[float] = Field(default_factory=list)


class OptimizerStatus(BaseModel):
    code: OptimizationFailureReason | str
    message: str
    paths: int
    time_limit_seconds: float


def optimizer_status(
    result: OptimalPlan | OptimizationFailure | None, paths: int
) -> OptimizerStatus:
    if result is None:
        code = "not_needed"
        message = "Current cash covers the scenario's required reserve; no additional funding is needed."
    elif isinstance(result, OptimalPlan):
        code = result.solver_status
        message = (
            "Optimized funding mix ready."
            if code == "optimal"
            else "An approximate solution passed the numerical checks."
        )
    else:
        code = result.reason
        messages = {
            "invalid_input": "The scenario contains inputs the optimizer cannot evaluate.",
            "no_funding_levers": "No available credit, investments, or reducible spending can fund this scenario.",
            "resource_limit": f"This {paths:,}-path scenario exceeds the optimizer's size limit. Try a shorter forecast window.",
            "cvxpy_unavailable": "The optimization library is unavailable on this server.",
            "solver_unavailable": "The optimization solver is unavailable on this server.",
            "solver_timeout": f"Optimization timed out after {SOLVER_TIME_LIMIT_SECONDS:g} seconds at {paths:,} paths. Try again or shorten the forecast window.",
            "solver_limit": "The solver reached a time or iteration limit before finding an acceptable solution.",
            "solver_error": "The solver could not finish this scenario. Try again or adjust the scenario.",
            "infeasible": "No funding mix meets the selected deficit limits with the available resources.",
            "unbounded": "The solver could not establish a bounded funding solution.",
            "invalid_solution": "The solver result failed numerical checks and cannot be shown.",
        }
        message = messages[code]
    return OptimizerStatus(
        code=code,
        message=message,
        paths=paths,
        time_limit_seconds=SOLVER_TIME_LIMIT_SECONDS,
    )

class ScenarioResponse(BaseModel):
    """The shared financial-output contract consumed by demo and personal UI."""

    as_of: str
    seed: int
    bootstrap_draw_id: str
    mean_block_length: int
    mean_block_length_was_clipped: bool
    immediate_funding: float
    marketable_backup_capital: float
    restricted_capital: float
    coverage_target: float
    operating_buffer: float
    required_liquidity_reserve: float
    funding_gap: float
    coverage_at_current_funding: float
    severity: SeverityMetrics
    estimate_band: dict[str, float] | None = None
    coverage_curve: list[CoveragePoint]
    reserve_buffer_curve: list[ReserveBufferPoint]
    cash_paths: CashPaths
    shortfall_distribution: ShortfallDistribution
    plans: list[dict[str, Any]] = Field(default_factory=list)
    recommendation: dict[str, Any] | None = None
    sensitivity: list[dict[str, Any]] = Field(default_factory=list)
    sensitivity_verdict: str | None = None
    wrong_way_risk: dict[str, Any] | None = None
    optimal_plan: dict[str, Any] | None = None
    optimizer_status: OptimizerStatus
    provenance: dict[str, Any] = Field(default_factory=dict)
    model_card: dict[str, Any] = Field(default_factory=dict)
    stress: dict[str, Any] = Field(default_factory=dict)
    baseline_summary: dict[str, Any] = Field(default_factory=dict)
    unstressed_summary: dict[str, Any] = Field(default_factory=dict)
    immediate_cash_coverage_ratio: float | None = None
    recommendation_status: str = "available"
    excluded_obligations: list[str] = Field(default_factory=list)
    account_liquidity: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class ScenarioEvaluation:
    response: ScenarioResponse
    optimizer_reason: str | None


def _direct_average_discretionary(bundle: DrawBundle | PathBundle) -> float | None:
    if not isinstance(bundle, PathBundle):
        return None
    paths = bundle.discretionary_daily[:, : bundle.horizon_days]
    return float(np.mean(paths)) if paths.size else 0.0


def _optimizer_unavailable_reason(
    state: FinancialState,
    *,
    include_optimizer: bool,
) -> str | None:
    if not include_optimizer:
        return "Funding optimization is not meaningful for this forecast mode."
    if not state.credit_accounts and not state.taxable_portfolio:
        return "Add an actual credit account or taxable holding before requesting an optimized funding mix."
    return None


def evaluate_scenario(
    state: FinancialState,
    bundle: DrawBundle | PathBundle,
    obligations: Sequence[Obligation],
    *,
    coverage_target: float,
    operating_buffer: float,
    funding_config: FundingConfig = FundingConfig(),
    funding_policy: FundingPolicy = FundingPolicy(),
    overdraft_apr: float = 0.2999,
    buffer_tolerance_dollar_days: float | None = None,
    capital_gains_rate: float = 0.15,
    include_reserve_uncertainty: bool = False,
    include_persistence_sensitivity: bool = False,
    include_optimizer: bool = True,
    deterministic: bool = False,
    uncertainty_outer_paths: int | None = None,
) -> ScenarioEvaluation:
    """Evaluate every shared ScenarioResponse field on one matched bundle.

    Bootstrap-only uncertainty is deliberately unavailable for direct
    assumption/schedule paths.  Candidate plans always reuse ``bundle`` and
    policy timing, so none can silently receive a different horizon or random
    realization.
    """

    computed = compute_scenario_metrics(
        state,
        bundle,
        obligations,
        coverage_target,
        operating_buffer,
    )

    estimate_band: dict[str, float] | None = None
    sensitivity: list[dict[str, Any]] = []
    sensitivity_verdict: str | None = None
    if isinstance(bundle, DrawBundle) and include_reserve_uncertainty:
        outer_paths = uncertainty_outer_paths if uncertainty_outer_paths is not None else 50
        band = uncertainty.estimate_band(
            state,
            obligations,
            coverage_target=coverage_target,
            operating_buffer=operating_buffer,
            point_estimate=computed.required_liquidity_reserve,
            point_mean_block_length=bundle.mean_block_length,
            horizon_days=bundle.horizon_days,
            n_paths=bundle.n_paths,
            n_outer=outer_paths,
            seed=bundle.seed,
        )
        estimate_band = {"low": band.low, "high": band.high}
    if isinstance(bundle, DrawBundle) and include_persistence_sensitivity:
        rows = uncertainty.persistence_sensitivity(
            state,
            obligations,
            coverage_target=coverage_target,
            operating_buffer=operating_buffer,
            horizon_days=bundle.horizon_days,
            n_paths=bundle.n_paths,
            seed=bundle.seed,
        )
        sensitivity = [vars(row) for row in rows]
        sensitivity_verdict = uncertainty.stability_verdict(rows)

    plans: list[dict[str, Any]] = []
    recommendation: dict[str, Any] | None = None
    optimal_plan: dict[str, Any] | None = None
    optimizer_reason: str | None = None
    optimizer_result: OptimalPlan | OptimizationFailure | None = None
    resolved_funding_policy = replace(
        funding_policy,
        capital_gains_rate=capital_gains_rate,
        overdraft_apr=overdraft_apr,
    )
    if computed.funding_gap > 0:
        specs = build_candidates(
            state,
            obligations,
            computed.funding_gap,
            funding_config,
            average_daily_discretionary_spending=_direct_average_discretionary(bundle),
        )
        comparison_horizon = max(
            plan_evaluation_horizon(state, bundle, spec)
            for spec in specs
        )
        comparison_bundle = extend_draw_bundle(bundle, comparison_horizon)
        results = [
            evaluate_plan(
                state,
                comparison_bundle,
                obligations,
                spec,
                operating_buffer=operating_buffer,
                overdraft_apr=overdraft_apr,
                evaluation_horizon_days=comparison_horizon,
                decision_horizon_days=bundle.horizon_days,
            )
            for spec in specs
        ]
        chosen = recommend(results, resolved_funding_policy)
        plans, recommendation = to_contract(results, chosen)

        optimizer_reason = _optimizer_unavailable_reason(
            state,
            include_optimizer=include_optimizer,
        )
        if optimizer_reason is None:
            optimizer_result = optimize_funding(
                state,
                bundle,
                obligations,
                coverage_target=coverage_target,
                operating_buffer=operating_buffer,
                overdraft_apr=overdraft_apr,
                buffer_tolerance_dollar_days=buffer_tolerance_dollar_days,
                capital_gains_rate=capital_gains_rate,
                funding_config=funding_config,
                funding_policy=resolved_funding_policy,
            )
            if isinstance(optimizer_result, OptimizationFailure):
                optimizer_reason = optimizer_status(
                    optimizer_result, bundle.n_paths
                ).message
            elif isinstance(optimizer_result, OptimalPlan):
                optimal_plan = asdict(optimizer_result)

    cash_paths = dict(computed.cash_paths)
    if deterministic:
        # The median remains the exact deterministic cash trajectory. Empty
        # uncertainty bands let the surface omit percentile/probability claims.
        cash_paths["p10"] = []
        cash_paths["p90"] = []

    return ScenarioEvaluation(
        response=ScenarioResponse(
            as_of=state.as_of.isoformat(),
            seed=bundle.seed,
            bootstrap_draw_id=bundle.bootstrap_draw_id,
            mean_block_length=bundle.mean_block_length,
            mean_block_length_was_clipped=bundle.mean_block_length_was_clipped,
            immediate_funding=state.immediate_funding,
            marketable_backup_capital=state.marketable_backup_capital,
            restricted_capital=state.restricted_capital,
            coverage_target=coverage_target,
            operating_buffer=operating_buffer,
            required_liquidity_reserve=computed.required_liquidity_reserve,
            funding_gap=computed.funding_gap,
            coverage_at_current_funding=computed.coverage_at_current_funding,
            severity=SeverityMetrics(**computed.severity),
            estimate_band=estimate_band,
            coverage_curve=[CoveragePoint(**point) for point in computed.coverage_curve],
            reserve_buffer_curve=[
                ReserveBufferPoint(**point) for point in computed.reserve_buffer_curve
            ],
            cash_paths=CashPaths(**cash_paths),
            shortfall_distribution=ShortfallDistribution(**computed.shortfall_distribution),
            plans=plans,
            recommendation=recommendation,
            sensitivity=sensitivity,
            sensitivity_verdict=sensitivity_verdict,
            wrong_way_risk=computed.wrong_way_risk,
            optimal_plan=optimal_plan,
            optimizer_status=optimizer_status(optimizer_result, bundle.n_paths),
        ),
        optimizer_reason=optimizer_reason,
    )
