"""HTTP surface for the personal cash workspace and clearly labeled demo engine.

`/health` is public.  Every other endpoint authenticates the caller with
Supabase Auth, then forwards that caller's bearer token to Supabase RPCs so RLS
continues to apply.  The synthetic scenario remains a demo-only calculation;
it never substitutes data for a saved workspace.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable
from functools import lru_cache
import os
from threading import BoundedSemaphore
import time
from typing import Annotated, Any

import anyio
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
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
from ginseng.scenario_service import ScenarioResponse, evaluate_scenario
from ginseng.generate import DEFAULT_SEED, generate_persona
from ginseng.providers.nessie import NessieError, NessieProvider
from ginseng.simulate import draw_bundle
from ginseng.state import FinancialState, Obligation
from ginseng.supabase import AuthenticatedIdentity, SupabaseError
from ginseng.workspace import (
    CashWorkspace,
    CashWorkspaceRepository,
    SaveWorkspaceRequest,
)

DEMO_MAX_HORIZON_DAYS = 365
DEMO_MAX_PATHS = 3_000
DEMO_MAX_OBLIGATIONS = 200
DEMO_MAX_OPERATING_BUFFER = 1_000_000.0
DEMO_MAX_OBLIGATION_AMOUNT = 1_000_000.0
_SCENARIO_GATE = BoundedSemaphore(value=2)
_SUPABASE_GATEWAY = get_supabase_gateway()


def _allowed_origins() -> list[str]:
    configured = os.environ.get("GINSENG_ALLOWED_ORIGINS", "http://localhost:5173")
    origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
    return origins or ["http://localhost:5173"]


class ObligationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=100)
    amount: float = Field(gt=0, le=DEMO_MAX_OBLIGATION_AMOUNT)
    due_in_days: int = Field(ge=0, le=DEMO_MAX_HORIZON_DAYS)


class ScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: int = Field(default=DEFAULT_SEED, ge=0, le=9_007_199_254_740_991)
    horizon_days: int = Field(default=30, ge=1, le=DEMO_MAX_HORIZON_DAYS)
    coverage_target: float = Field(default=0.95, gt=0, le=1)
    operating_buffer: float = Field(default=1000.0, ge=0, le=DEMO_MAX_OPERATING_BUFFER)
    paths: int = Field(default=2000, ge=10, le=DEMO_MAX_PATHS)
    mean_block_length: int | None = Field(default=None, ge=1, le=90)
    obligations: list[ObligationRequest] = Field(default_factory=list, max_length=DEMO_MAX_OBLIGATIONS)
    overdraft_apr: float = Field(default=0.2999, ge=0, le=10)
    buffer_tolerance_dollar_days: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    capital_gains_rate: float = Field(default=0.15, ge=0, le=1)



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

@app.post("/scenario", response_model=ScenarioResponse)
def scenario(
    request: ScenarioRequest,
    _: Annotated[AuthenticatedIdentity, Depends(require_identity)],
) -> ScenarioResponse:
    """Run the explicitly synthetic demo through the shared scenario pipeline."""
    if not _SCENARIO_GATE.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="The scenario engine is busy. Try again shortly.")
    try:
        persona = _cached_persona(request.seed)
        obligations = tuple(
            Obligation(id=item.id, label=item.label, amount=item.amount, due_in_days=item.due_in_days)
            for item in request.obligations
        )
        bundle = draw_bundle(
            persona,
            horizon_days=request.horizon_days,
            n_paths=request.paths,
            seed=request.seed,
            mean_block_length=request.mean_block_length,
        )
        return evaluate_scenario(
            persona,
            bundle,
            obligations,
            coverage_target=request.coverage_target,
            operating_buffer=request.operating_buffer,
            overdraft_apr=request.overdraft_apr,
            buffer_tolerance_dollar_days=request.buffer_tolerance_dollar_days,
            capital_gains_rate=request.capital_gains_rate,
            include_reserve_uncertainty=True,
            include_persistence_sensitivity=True,
        ).response
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
