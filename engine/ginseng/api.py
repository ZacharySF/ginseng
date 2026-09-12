"""FastAPI surface: `GET /health` and `POST /scenario`.

The frontend never computes a financial number; every field in a
`/scenario` response is derived by the engine. `plans`, `recommendation`,
and `estimate_band` are populated in a later phase; here they are always an
empty list and nulls, per the frozen contract.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ginseng.generate import DEFAULT_SEED, generate_persona
from ginseng.metrics import compute_scenario_metrics
from ginseng.simulate import draw_bundle
from ginseng.funding import FundingConfig, build_candidates, evaluate_plan
from ginseng.policy import FundingPolicy, recommend, to_contract
from ginseng.state import FinancialState, Obligation
from ginseng import uncertainty

ALLOWED_ORIGIN = "http://localhost:5173"


class ObligationRequest(BaseModel):
    id: str
    label: str
    amount: float
    due_in_days: int


class ScenarioRequest(BaseModel):
    seed: int = DEFAULT_SEED
    horizon_days: int = 30
    coverage_target: float = 0.95
    operating_buffer: float = 1000.0
    paths: int = 2000
    mean_block_length: int | None = None
    obligations: list[ObligationRequest] = Field(default_factory=list)


class SeverityMetrics(BaseModel):
    cash_shortfall_probability: float
    avg_cash_deficit_when_short: float
    dollar_days_below_buffer: float


class CoveragePoint(BaseModel):
    funding: float
    coverage: float


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


class ScenarioResponse(BaseModel):
    as_of: str
    seed: int
    bootstrap_draw_id: str
    mean_block_length: int
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
    cash_paths: CashPaths
    shortfall_distribution: ShortfallDistribution
    plans: list[dict[str, Any]] = Field(default_factory=list)
    recommendation: dict[str, Any] | None = None
    sensitivity: list[dict[str, Any]] = Field(default_factory=list)
    sensitivity_verdict: str | None = None


class HealthResponse(BaseModel):
    status: str
    seed_default: int


app = FastAPI(title="Ginseng Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN],
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache(maxsize=64)
def _cached_persona(seed: int) -> FinancialState:
    """Generate once per seed; `generate_persona` is a pure function of
    `seed`, so repeated requests are fast and identical."""
    return generate_persona(seed)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", seed_default=DEFAULT_SEED)


@app.post("/scenario", response_model=ScenarioResponse)
def scenario(request: ScenarioRequest) -> ScenarioResponse:
    persona = _cached_persona(request.seed)
    obligations = tuple(
        Obligation(id=o.id, label=o.label, amount=o.amount, due_in_days=o.due_in_days)
        for o in request.obligations
    )

    bundle = draw_bundle(
        persona,
        horizon_days=request.horizon_days,
        n_paths=request.paths,
        seed=request.seed,
        mean_block_length=request.mean_block_length,
    )
    computed = compute_scenario_metrics(
        persona, bundle, obligations, request.coverage_target, request.operating_buffer
    )

    # Spec 29-31: the outer dependent bootstrap widens the point estimate
    # into a model-estimate range. Same seed, same band.
    band = uncertainty.estimate_band(
        persona,
        obligations,
        coverage_target=request.coverage_target,
        operating_buffer=request.operating_buffer,
        horizon_days=request.horizon_days,
        n_paths=request.paths,
        n_outer=50,
        seed=request.seed,
    )

    # Spec 18: persistence sensitivity across fixed and data-estimated
    # block lengths, evaluated on the shared bundle discipline.
    rows = uncertainty.persistence_sensitivity(
        persona,
        obligations,
        coverage_target=request.coverage_target,
        operating_buffer=request.operating_buffer,
        horizon_days=request.horizon_days,
        n_paths=request.paths,
        seed=request.seed,
    )

    # Spec 38/45/60: candidate funding plans exist only once there is a
    # gap to close; every plan is evaluated on this request's bundle so
    # plan deltas are not Monte Carlo noise (spec 20).
    if computed.funding_gap > 0:
        specs = build_candidates(persona, obligations, computed.funding_gap, FundingConfig())
        results = [evaluate_plan(persona, bundle, obligations, spec) for spec in specs]
        recommendation = recommend(results, FundingPolicy())
        plans, recommendation_dict = to_contract(results, recommendation)
    else:
        plans = []
        recommendation_dict = None

    return ScenarioResponse(
        as_of=persona.as_of.isoformat(),
        seed=request.seed,
        bootstrap_draw_id=bundle.bootstrap_draw_id,
        mean_block_length=bundle.mean_block_length,
        immediate_funding=persona.immediate_funding,
        marketable_backup_capital=persona.marketable_backup_capital,
        restricted_capital=persona.restricted_capital,
        coverage_target=request.coverage_target,
        operating_buffer=request.operating_buffer,
        required_liquidity_reserve=computed.required_liquidity_reserve,
        funding_gap=computed.funding_gap,
        coverage_at_current_funding=computed.coverage_at_current_funding,
        severity=SeverityMetrics(**computed.severity),
        estimate_band={"low": band.low, "high": band.high},
        coverage_curve=[CoveragePoint(**point) for point in computed.coverage_curve],
        cash_paths=CashPaths(**computed.cash_paths),
        shortfall_distribution=ShortfallDistribution(**computed.shortfall_distribution),
        plans=plans,
        recommendation=recommendation_dict,
        sensitivity=[vars(row) for row in rows],
        sensitivity_verdict=uncertainty.stability_verdict(rows),
    )
