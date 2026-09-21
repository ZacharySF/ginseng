"""HTTP surface for the personal cash workspace and clearly labeled demo engine.

`/health` is public.  Every other endpoint authenticates the caller with
Supabase Auth, then forwards that caller's bearer token to Supabase RPCs so RLS
continues to apply.  The synthetic scenario remains a demo-only calculation;
it never substitutes data for a saved workspace.
"""

from __future__ import annotations

import asyncio
from ginseng.execution import execution_scope

from collections.abc import AsyncIterator, Awaitable
from dataclasses import asdict, replace
from functools import lru_cache
import os
from ginseng.resources import SCENARIO_GATE
import time
from ginseng import uncertainty
from typing import Annotated, Any, Literal

import anyio
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
import numpy as np
from starlette.requests import ClientDisconnect
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from ginseng.chat import (
    CHAT_DEADLINE_SECONDS,
    ChatConfigurationError,
    ChatProviderError,
    ChatQuota,
    ChatRateLimitError,
    ChatRequest,
    ChatTimeoutError,
    DemoChatRequest,
    PersonalChatRequest,
    ModelDelta,
    get_chat_quota,
    get_gemini_client,
    prepare_chat,
    stream_chat_events,
)
from ginseng.dependencies import get_supabase_gateway, require_identity, supabase_http_error
from ginseng.finance_api import get_finance_repository, router as finance_router
from ginseng.finance_repository import FinanceRepository
from ginseng.forecast_api import router as forecast_router
from ginseng.scenario_service import (
    CashPaths,
    CoveragePoint,
    ReserveBufferPoint,
    ScenarioResponse,
    SeverityMetrics,
    ShortfallDistribution,
    evaluate_scenario,
    evaluate_funding,
    optimizer_status as _optimizer_status,
)
from ginseng.funding import FundingConfig, build_candidates, optimizer_comparison_bundle, evaluate_plan
from ginseng.generate import DEFAULT_SEED, generate_persona
from ginseng.metrics import compute_scenario_metrics, required_liquidity_per_path
from ginseng.risk import probabilities, concentration, cvar, MONEY_TOLERANCE
from ginseng.stress import DroughtView, scenario_weights
from ginseng.provenance import fingerprint, model_card
from ginseng.calibration import walk_forward
from ginseng.decision import funding_analysis
from ginseng.portfolio import portfolio_lab
from ginseng.frontier import portfolio_frontier
from ginseng.withdrawals import WithdrawalAssumptions, LONG_TERM_CAPITAL_GAINS_RATE, account_liquidity
from ginseng.optimizer import (
    SOLVER_TIME_LIMIT_SECONDS,
    OptimalPlan,
    OptimizationFailure,
    OptimizationFailureReason,
    optimize_funding,
)
from ginseng.policy import FundingPolicy, recommend, to_contract
from ginseng.providers.nessie import NessieError, NessieProvider
from ginseng.simulate import draw_bundle, cash_paths
from ginseng.state import FinancialState, Obligation
from ginseng.supabase import AuthenticatedIdentity, SupabaseError
from ginseng.workspace import (
    CashWorkspace,
    CashWorkspaceRepository,
    SaveWorkspaceRequest,
)

from ginseng.risk_explorer import NumericalOptions, explore
from ginseng.inputs import InputCase
from ginseng.resources import forecast_capacity, cancellable_calculation

DEMO_MAX_HORIZON_DAYS = 365
DEMO_MAX_PATHS = 3_000
DEMO_MAX_OBLIGATIONS = 200
DEMO_MAX_OPERATING_BUFFER = 1_000_000.0
DEMO_MAX_OBLIGATION_AMOUNT = 1_000_000.0
_SCENARIO_GATE = SCENARIO_GATE
_SUPABASE_GATEWAY = get_supabase_gateway()


def _allowed_origins() -> list[str]:
    configured = os.environ.get("GINSENG_ALLOWED_ORIGINS", "http://localhost:5173")
    origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
    return origins or ["http://localhost:5173"]


class ObligationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=100)
    amount: float = Field(gt=0, le=DEMO_MAX_OBLIGATION_AMOUNT)
    due_in_days: int = Field(ge=0, le=DEMO_MAX_HORIZON_DAYS)


class DroughtViewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    probability: float = Field(ge=0, le=1)
    window_days: int = Field(default=14, ge=1, le=60)
    income_fraction: float = Field(default=0.5, ge=0, le=1)


class ScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    seed: int = Field(default=DEFAULT_SEED, ge=0, le=9_007_199_254_740_991)
    horizon_days: int = Field(default=30, ge=1, le=DEMO_MAX_HORIZON_DAYS)
    coverage_target: float = Field(default=0.95, gt=0, le=1)
    operating_buffer: float = Field(default=1000.0, ge=0, le=DEMO_MAX_OPERATING_BUFFER)
    paths: int = Field(default=2000, ge=10, le=DEMO_MAX_PATHS)
    mean_block_length: int | None = Field(default=None, ge=1, le=90)
    obligations: list[ObligationRequest] = Field(default_factory=list, max_length=DEMO_MAX_OBLIGATIONS)
    overdraft_apr: float = Field(default=0.2999, ge=0, le=10)
    buffer_tolerance_dollar_days: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    capital_gains_rate: float = Field(default=LONG_TERM_CAPITAL_GAINS_RATE, ge=0, le=1)
    tail_deficit_limit: float | None = Field(default=None, ge=0, le=1_000_000)
    drought_view: DroughtViewRequest | None = None

    @model_validator(mode="after")
    def unique_events(self):
        ids = [item.id for item in self.obligations]
        if len(ids) != len(set(ids)):
            raise ValueError("Scenario event identifiers must be unique.")
        return self




class HealthResponse(BaseModel):
    status: str
    seed_default: int


class NessieStatusResponse(BaseModel):
    configured: bool


class SampleCustomerResponse(BaseModel):
    external_id: str
    first_name: str | None = None
    last_name: str | None = None


class SampleAccountResponse(BaseModel):
    source: str
    external_id: str
    kind: str
    name: str
    balance: float


class SampleTransactionResponse(BaseModel):
    source: str
    external_id: str
    account_external_id: str
    date: str
    amount: float
    description: str | None = None


class SampleBillResponse(BaseModel):
    source: str
    external_id: str
    account_external_id: str
    payee: str
    amount: float
    payment_date: str
    recurring: bool


class NessieSampleResponse(BaseModel):
    label: str
    simulated: bool
    customer: SampleCustomerResponse
    accounts: list[SampleAccountResponse]
    transactions: list[SampleTransactionResponse]
    bills: list[SampleBillResponse]


app = FastAPI(title="Ginseng Engine")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["authorization", "content-type"],
)
app.include_router(finance_router)
app.include_router(forecast_router)



@app.exception_handler(RequestValidationError)
async def request_validation_error(_: Request, __: RequestValidationError) -> JSONResponse:
    """Keep every API error to the documented, non-sensitive detail shape."""

    return JSONResponse(status_code=422, content={"detail": "Request has invalid fields."})


# Retain the historical private import point while all routers use the shared
# public dependency mapper from ``ginseng.dependencies``.
_supabase_http_error = supabase_http_error

def get_workspace_repository() -> CashWorkspaceRepository:
    return CashWorkspaceRepository(_SUPABASE_GATEWAY)



@lru_cache(maxsize=64)
def _cached_persona(seed: int) -> FinancialState:
    """Generate each deterministic demo persona once per seed."""

    return generate_persona(seed)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", seed_default=DEFAULT_SEED)


@app.get("/workspace", response_model=CashWorkspace)
def get_workspace(
    identity: Annotated[AuthenticatedIdentity, Depends(require_identity)],
    repository: Annotated[CashWorkspaceRepository, Depends(get_workspace_repository)],
) -> CashWorkspace:
    try:
        return repository.get(identity.access_token)
    except SupabaseError as error:
        raise _supabase_http_error(error) from error


@app.put("/workspace", response_model=CashWorkspace)
def save_workspace(
    request: SaveWorkspaceRequest,
    identity: Annotated[AuthenticatedIdentity, Depends(require_identity)],
    repository: Annotated[CashWorkspaceRepository, Depends(get_workspace_repository)],
) -> CashWorkspace:
    try:
        return repository.save(request, identity.access_token)
    except SupabaseError as error:
        raise _supabase_http_error(error) from error






async def _watch_for_disconnect(request: Request) -> None:
    # FastAPI has consumed the validated body. No other task reads receive
    # until StreamingResponse starts, so await disconnect without polling.
    while True:
        if (await request.receive())["type"] == "http.disconnect":
            return

async def _await_or_disconnect(request: Request, operation: Awaitable[Any]) -> Any:
    """Await one pre-header operation while still reacting to a dropped client."""

    operation_task = asyncio.ensure_future(operation)
    disconnect_task = asyncio.create_task(_watch_for_disconnect(request))
    try:
        done, _pending = await asyncio.wait(
            {operation_task, disconnect_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if operation_task in done:
            return operation_task.result()
        raise ClientDisconnect("Client disconnected before the chat response could start.")
    finally:
        for task in (operation_task, disconnect_task):
            if not task.done():
                task.cancel()
        with anyio.CancelScope(shield=True):
            await asyncio.gather(operation_task, disconnect_task, return_exceptions=True)


async def _prepare_chat_or_disconnect(
    request: Request,
    chat_request: PersonalChatRequest | DemoChatRequest,
    identity: AuthenticatedIdentity,
    repository: FinanceRepository,
    deadline: float,
):
    """Resolve trusted context while monitoring a connection before headers commit."""

    return await _await_or_disconnect(
        request, prepare_chat(chat_request, identity, repository, deadline)
    )


class _ChatStreamingResponse(StreamingResponse):
    """Own the quota and upstream even if sending headers fails before iteration."""

    def __init__(
        self,
        content: AsyncIterator[bytes],
        provider: AsyncIterator[ModelDelta],
        quota: ChatQuota,
        user_id: str,
    ) -> None:
        super().__init__(
            content,
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
        self._provider = provider
        self._quota = quota
        self._user_id = user_id

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                try:
                    await self.body_iterator.aclose()
                finally:
                    try:
                        await self._provider.aclose()
                    finally:
                        self._quota.release(self._user_id)


@app.post("/chat")
async def chat(
    request: Request,
    chat_request: ChatRequest,
    identity: Annotated[AuthenticatedIdentity, Depends(require_identity)],
    repository: Annotated[FinanceRepository, Depends(get_finance_repository)],
    quota: Annotated[ChatQuota, Depends(get_chat_quota)],
) -> StreamingResponse:
    """Stream a fresh personal workspace or explicit synthetic demo explanation.

    Auth, body validation, Gemini configuration, quota admission, and (for personal
    chats) the caller's saved workspace are all resolved before any response bytes are
    sent, so ordinary JSON HTTP errors (401/422/429/503/504) still apply up to that
    point. After that the body is `application/x-ndjson`: zero or more
    `{"type":"delta","text":...}` events, then exactly one `{"type":"done",...}` event on
    a complete, validated reply, or one `{"type":"error",...}` event otherwise - never
    both, and never a `done` after an `error`.
    """

    try:
        model_client = get_gemini_client()
    except ChatConfigurationError as error:
        raise HTTPException(
            status_code=503,
            detail="The assistant is not configured. Ask the administrator to set GEMINI_API_KEY.",
        ) from error

    try:
        quota.acquire(identity.user_id)
    except ChatRateLimitError as error:
        raise HTTPException(status_code=429, detail="Too many chat requests. Try again shortly.") from error

    deadline = time.monotonic() + CHAT_DEADLINE_SECONDS
    provider_deltas = None
    try:
        prepared = await _prepare_chat_or_disconnect(request, chat_request, identity, repository, deadline)
        provider_deltas = model_client.stream(
            prepared.contents, deadline, allow_additions=prepared.source == "personal"
        )
        first_delta = await _await_or_disconnect(request, anext(provider_deltas))
    except BaseException as error:
        try:
            with anyio.CancelScope(shield=True):
                if provider_deltas is not None:
                    await provider_deltas.aclose()
        finally:
            quota.release(identity.user_id)
        if isinstance(error, SupabaseError):
            raise _supabase_http_error(error) from error
        if isinstance(error, ChatRateLimitError):
            raise HTTPException(status_code=429, detail="Too many chat requests. Try again shortly.") from error
        if isinstance(error, ChatTimeoutError):
            raise HTTPException(status_code=504, detail="Chat service timed out.") from error
        if isinstance(error, (ChatProviderError, StopAsyncIteration)):
            raise HTTPException(status_code=503, detail="Chat service is unavailable.") from error
        if isinstance(error, ClientDisconnect):
            raise HTTPException(status_code=499, detail="Client disconnected before the chat response could start.") from error
        raise

    return _ChatStreamingResponse(
        stream_chat_events(prepared, first_delta, provider_deltas),
        provider_deltas,
        quota,
        identity.user_id,
    )

def _scenario_context(request: ScenarioRequest):
    persona = replace(_cached_persona(request.seed), operating_buffer=request.operating_buffer,
                      coverage_target=request.coverage_target, forecast_horizon=request.horizon_days)
    obligations = tuple(Obligation(id=item.id, label=item.label, amount=item.amount, due_in_days=item.due_in_days)
                        for item in request.obligations)
    bundle = draw_bundle(persona, request.horizon_days, request.paths, request.seed, request.mean_block_length)
    view = DroughtView(**request.drought_view.model_dump()) if request.drought_view else None
    if view is not None:
        view = replace(view, window_days=min(view.window_days, request.horizon_days))
    weights, stress = scenario_weights(persona, bundle, view)
    return persona, obligations, bundle, view, weights, stress


def _optimizer_parameters(request: ScenarioRequest) -> dict:
    return {**{name: getattr(request, name) for name in ("coverage_target", "operating_buffer", "overdraft_apr",
            "buffer_tolerance_dollar_days", "capital_gains_rate", "tail_deficit_limit")},
            "funding_policy": FundingPolicy(max_buffer_breach_probability=1-request.coverage_target,
                max_cash_shortfall_probability=1-request.coverage_target,
                capital_gains_rate=request.capital_gains_rate,
                buffer_tolerance_dollar_days=request.buffer_tolerance_dollar_days,
                tail_deficit_limit=request.tail_deficit_limit)}


def _summary(computed) -> dict:
    return {"required_liquidity_reserve": computed.required_liquidity_reserve,
            "funding_gap": computed.funding_gap, "severity": computed.severity,
            "coverage_at_current_funding": computed.coverage_at_current_funding}


@app.post("/scenario", response_model=ScenarioResponse)
@execution_scope
def scenario(
    request: ScenarioRequest,
    _: Annotated[AuthenticatedIdentity, Depends(require_identity)],
) -> ScenarioResponse:
    """Run the explicitly synthetic demo through the shared scenario pipeline."""
    if not _SCENARIO_GATE.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="The scenario engine is busy. Try again shortly.")
    try:
        persona, obligations, bundle, view, weights, stress = _scenario_context(request)
        computed = compute_scenario_metrics(
            persona, bundle, obligations, request.coverage_target, request.operating_buffer, weights
        )
        unstressed = compute_scenario_metrics(persona, bundle, obligations, request.coverage_target, request.operating_buffer) if view else computed
        baseline = compute_scenario_metrics(persona, bundle, (), request.coverage_target, request.operating_buffer, weights) if obligations else computed
        matrix = cash_paths(persona, bundle, obligations)
        required = required_liquidity_per_path(matrix, request.operating_buffer)
        support = concentration(required, request.coverage_target, weights)
        stress.update(support)
        # These are an explicit support policy, not significance tests.
        weak_stress = stress["status"] == "active" and (support["ens_tail"] < 20 or support["max_weight"] > 0.1)
        stress["recommendation_supported"] = stress["status"] != "unsupported" and not weak_stress
        stress["support_policy"] = "Stress recommendations require tail ENS >= 20 and maximum scenario weight <= 10%; these are policy assumptions."
        optimizer_parameters = _optimizer_parameters(request)
        config = {**{key: value for key, value in optimizer_parameters.items() if key != "funding_policy"},
                  "funding": asdict(FundingConfig()), "policy": asdict(optimizer_parameters["funding_policy"]),
                  "horizon_days": request.horizon_days, "mean_block_length": bundle.mean_block_length,
                  "quantile_method": "inverse empirical CDF", "tail_ties": "proportional fractional mass"}
        withdrawal_assumptions = WithdrawalAssumptions(long_term_rate=request.capital_gains_rate)
        accounts = account_liquidity(persona, withdrawal_assumptions)
        config["withdrawals"] = {"version": accounts["assumptions_version"], **asdict(withdrawal_assumptions),
                                 "roth_earnings_and_conversions": "excluded", "tax_reserve_timing": "set aside at availability"}
        band = uncertainty.estimate_band(
            persona,
            obligations,
            coverage_target=request.coverage_target,
            operating_buffer=request.operating_buffer,
            point_estimate=computed.required_liquidity_reserve,
            point_mean_block_length=bundle.mean_block_length,
            horizon_days=request.horizon_days,
            n_paths=request.paths,
            n_outer=50,
            seed=request.seed,
        ) if view is None else None
        rows = uncertainty.persistence_sensitivity(
            persona,
            obligations,
            coverage_target=request.coverage_target,
            operating_buffer=request.operating_buffer,
            horizon_days=request.horizon_days,
            n_paths=request.paths,
            seed=request.seed,
        ) if view is None else []
        current_tail_deficit = cvar(np.maximum(0, request.operating_buffer - (persona.immediate_funding + matrix).min(axis=1)), request.coverage_target, weights)
        needs_tail_protection = request.tail_deficit_limit is not None and current_tail_deficit > request.tail_deficit_limit
        needs_mean_protection = (request.buffer_tolerance_dollar_days is not None
            and computed.severity["dollar_days_below_buffer"] > request.buffer_tolerance_dollar_days + MONEY_TOLERANCE)
        if computed.funding_gap > 0 or needs_tail_protection or needs_mean_protection:
            plans, recommendation_dict, optimal, active_policy, evaluation_bundle = evaluate_funding(
                persona, bundle, obligations, computed.funding_gap,
                weights=weights, **_optimizer_parameters(request))
            optimal_plan = asdict(optimal) if isinstance(optimal, OptimalPlan) else None
        else:
            plans = []
            recommendation_dict = None
            optimal_plan = None
            optimal = None
        if plans:
            config["policy"] = asdict(active_policy)
            config["funding"]["max_credit_utilization"] = active_policy.max_credit_utilization
        config["evaluation_horizon_days"] = evaluation_bundle.horizon_days if plans else bundle.horizon_days
        hashes = fingerprint(persona, bundle, obligations, weights, view, config, matrix)
        recommendation_status = "available"
        if not stress["recommendation_supported"]:
            recommendation_status = "stress_support_insufficient"
            recommendation_dict = {"plan_id": "", "explanation": "No recommendation: the stress assumption is unsupported or its tail is too concentrated under the disclosed support policy."}
            for plan in plans:
                plan["recommended"] = False
                plan["explanation"] = recommendation_dict["explanation"]
        elif recommendation_dict is not None and not recommendation_dict["plan_id"]:
            recommendation_status = "no_plan_meets_policy"
        return ScenarioResponse(
            as_of=persona.as_of.isoformat(),
            seed=request.seed,
            bootstrap_draw_id=bundle.bootstrap_draw_id,
            mean_block_length=bundle.mean_block_length,
            mean_block_length_was_clipped=bundle.mean_block_length_was_clipped,
            immediate_funding=persona.immediate_funding,
            marketable_backup_capital=persona.marketable_backup_capital,
            restricted_capital=persona.restricted_capital,
            coverage_target=request.coverage_target,
            operating_buffer=request.operating_buffer,
            required_liquidity_reserve=computed.required_liquidity_reserve,
            funding_gap=computed.funding_gap,
            coverage_at_current_funding=computed.coverage_at_current_funding,
            severity=SeverityMetrics(**computed.severity),
            estimate_band={"low": band.low, "high": band.high} if band else None,
            coverage_curve=[CoveragePoint(**point) for point in computed.coverage_curve],
            reserve_buffer_curve=[
                ReserveBufferPoint(**point) for point in computed.reserve_buffer_curve
            ],
            cash_paths=CashPaths(**computed.cash_paths),
            shortfall_distribution=ShortfallDistribution(**computed.shortfall_distribution),
            plans=plans,
            recommendation=recommendation_dict,
            sensitivity=[vars(row) for row in rows],
            sensitivity_verdict=uncertainty.stability_verdict(rows) if rows else "Unweighted estimate bands and persistence comparisons are unavailable while a stress view is selected.",
            wrong_way_risk=computed.wrong_way_risk,
            optimal_plan=optimal_plan,
            optimizer_status=_optimizer_status(optimal, request.paths),
            provenance=hashes, model_card=model_card(persona, bundle, config, stress, hashes), stress=stress,
            baseline_summary=_summary(baseline), unstressed_summary=_summary(unstressed),
            immediate_cash_coverage_ratio=persona.immediate_funding / computed.required_liquidity_reserve if computed.required_liquidity_reserve > 0 else None,
            recommendation_status=recommendation_status,
            excluded_obligations=[item.id for item in obligations if item.due_in_days > request.horizon_days],
            account_liquidity=accounts,
            funding_policy=asdict(active_policy) if plans else {},
            funding_evaluation_horizon_days=evaluation_bundle.horizon_days if plans else bundle.horizon_days,
        )
    finally:
        _SCENARIO_GATE.release()


@lru_cache(maxsize=8)
def _cached_calibration(seed: int, horizon: int, paths: int, q: float, buffer: float):
    return walk_forward(_cached_persona(seed), horizon, paths, seed, q, buffer)


@app.post("/analysis/calibration")
def calibration_analysis(request: ScenarioRequest, _: Annotated[AuthenticatedIdentity, Depends(require_identity)]) -> dict:
    if not _SCENARIO_GATE.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="The scenario engine is busy. Try again shortly.")
    try:
        return _cached_calibration(request.seed, request.horizon_days, request.paths, request.coverage_target, request.operating_buffer)
    finally:
        _SCENARIO_GATE.release()


@app.post("/analysis/funding")
@execution_scope
def decision_analysis(request: ScenarioRequest, _: Annotated[AuthenticatedIdentity, Depends(require_identity)]) -> dict:
    if not _SCENARIO_GATE.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="The scenario engine is busy. Try again shortly.")
    try:
        persona, obligations, bundle, view, weights, stress = _scenario_context(request)
        if stress["status"] == "unsupported":
            return {"status": "unavailable", "reason": "The requested stress has no supporting scenarios."}
        computed = compute_scenario_metrics(persona, bundle, obligations, request.coverage_target, request.operating_buffer, weights)
        parameters = _optimizer_parameters(request)
        funding_config = FundingConfig(max_credit_utilization=parameters["funding_policy"].max_credit_utilization)
        specs = build_candidates(persona, obligations, computed.funding_gap, funding_config,
                                 withdrawal_assumptions=WithdrawalAssumptions(long_term_rate=request.capital_gains_rate))
        evaluation = optimizer_comparison_bundle(persona, bundle, specs, funding_config)
        return funding_analysis(persona, evaluation, obligations, specs, weights, view,
                                {**parameters, "funding_config": funding_config, "decision_horizon_days": bundle.horizon_days})
    finally:
        _SCENARIO_GATE.release()


@app.post("/analysis/portfolio")
@execution_scope
def portfolio_analysis(request: ScenarioRequest, _: Annotated[AuthenticatedIdentity, Depends(require_identity)]) -> dict:
    if not _SCENARIO_GATE.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="The scenario engine is busy. Try again shortly.")
    try:
        persona, obligations, bundle, view, weights, stress = _scenario_context(request)
        if stress["status"] == "unsupported":
            return {"status": "unavailable", "message": "The requested stress has no supporting scenarios."}
        computed = compute_scenario_metrics(persona, bundle, obligations, request.coverage_target, request.operating_buffer, weights)
        return portfolio_lab(persona, bundle, obligations, computed.funding_gap, weights, request.capital_gains_rate)
    except ValueError as error:
        return {"status": "unavailable", "message": str(error)}
    finally:
        _SCENARIO_GATE.release()


@app.get("/providers/nessie/status", response_model=NessieStatusResponse)
def nessie_status(_: Annotated[AuthenticatedIdentity, Depends(require_identity)]) -> NessieStatusResponse:
    """Report whether the demo-only Nessie adapter is configured, never its key."""

    return NessieStatusResponse(configured=NessieProvider().configured)


@app.get("/providers/nessie/sample", response_model=NessieSampleResponse)
def nessie_sample(_: Annotated[AuthenticatedIdentity, Depends(require_identity)]) -> NessieSampleResponse:
    """Return explicitly simulated Nessie demo data, never personal account data."""

    provider = NessieProvider()
    if not provider.configured:
        raise HTTPException(status_code=503, detail="Nessie provider is unavailable.")
    try:
        payload = provider.sample_workspace()
    except NessieError as error:
        raise HTTPException(status_code=503, detail="Nessie provider is unavailable.") from error
    return NessieSampleResponse(**payload)




class DemoNumericalRequest(ScenarioRequest):
    options: NumericalOptions


@app.post('/demo/numerics')
async def numerical_demo(request: DemoNumericalRequest, http_request: Request,
                   _: Annotated[AuthenticatedIdentity, Depends(require_identity)]):
    def calculate(cancelled):
        with forecast_capacity():
            if request.drought_view is not None:
                raise HTTPException(status_code=422,detail='Disable stress weighting to use historical risk exploration.')
            state = replace(_cached_persona(request.seed),operating_buffer=request.operating_buffer,
                            coverage_target=request.coverage_target,forecast_horizon=request.horizon_days)
            obligations = tuple(Obligation(item.id,item.label,item.amount,item.due_in_days) for item in request.obligations)
            try:
                return explore(InputCase('synthetic-demo',state,obligations,request.seed),request.options,
                               seed=request.seed,block_length=request.mean_block_length,cancelled=cancelled)
            except ValueError as error:
                raise HTTPException(status_code=422,detail=str(error)) from error
    return await cancellable_calculation(http_request, calculate)


@app.post("/analysis/frontier")
def frontier_analysis(request: ScenarioRequest, _: Annotated[AuthenticatedIdentity, Depends(require_identity)]):
    """Read-only allocation research under the explicitly synthetic cash model."""
    if request.horizon_days > 60:
        raise HTTPException(status_code=422, detail="Portfolio research supports horizons up to 60 days.")
    if request.drought_view is not None:
        raise HTTPException(status_code=422, detail="Disable stress weighting before building the portfolio frontier.")
    with forecast_capacity():
        state = replace(_cached_persona(request.seed), operating_buffer=request.operating_buffer,
                        coverage_target=request.coverage_target, forecast_horizon=request.horizon_days)
        obligations = tuple(Obligation(item.id, item.label, item.amount, item.due_in_days) for item in request.obligations)
        try:
            return portfolio_frontier(state, obligations, seed=request.seed, block_length=request.mean_block_length)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
