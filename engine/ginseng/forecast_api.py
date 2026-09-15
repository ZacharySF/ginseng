"""Authenticated, read-only forecast and history-backtest endpoints."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ginseng.dependencies import require_identity, supabase_http_error
from ginseng.finance_api import FinanceWorkspace, get_finance_repository
from ginseng.finance_models import ScenarioOverrides, PlanningPolicy
from ginseng.finance_repository import FinanceRepository
from ginseng.personal_forecast import (
    DEFAULT_FORECAST_PATHS,
    DEFAULT_FORECAST_SEED,
    MAX_FORECAST_PATHS,
    BacktestSummary,
    ForecastResponse,
    apply_scenario_overrides,
    backtest_personal_history,
    describe_scenario_changes,
    evaluate_personal_forecast,
)
from ginseng.supabase import AuthenticatedIdentity, SupabaseError
from ginseng.resources import forecast_capacity
from ginseng.workspace import MAX_EXPECTED_REVISION, MAX_WORKSPACE_REVISION, StrictInt

router = APIRouter(tags=["finance"])


class ForecastRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: Annotated[StrictInt, Field(ge=0, le=MAX_EXPECTED_REVISION)]
    horizon_days: Literal[14, 30, 60]
    overrides: ScenarioOverrides | None = None
    seed: Annotated[StrictInt, Field(ge=0, le=MAX_WORKSPACE_REVISION)] = DEFAULT_FORECAST_SEED
    paths: Annotated[StrictInt, Field(ge=1, le=MAX_FORECAST_PATHS)] = DEFAULT_FORECAST_PATHS


class BacktestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: Annotated[StrictInt, Field(ge=0, le=MAX_EXPECTED_REVISION)]
    horizon_days: Literal[14, 30, 60]
    policy: PlanningPolicy | None = None


def _current_workspace(
    expected_revision: int,
    identity: AuthenticatedIdentity,
    repository: FinanceRepository,
) -> FinanceWorkspace:
    try:
        workspace = repository.get(identity.access_token)
    except SupabaseError as error:
        raise supabase_http_error(error) from error
    if workspace.revision != expected_revision:
        raise HTTPException(status_code=409, detail="Workspace changed. Reload before forecasting.")
    return workspace


@router.post("/finance/forecast", response_model=ForecastResponse)
def forecast_finance(
    request: ForecastRequest,
    identity: Annotated[AuthenticatedIdentity, Depends(require_identity)],
    repository: Annotated[FinanceRepository, Depends(get_finance_repository)],
) -> ForecastResponse:
    """Evaluate canonical saved finances and an optional read-only scenario."""
    with forecast_capacity():
        workspace = _current_workspace(request.expected_revision, identity, repository)
        baseline = evaluate_personal_forecast(
            workspace,
            request.horizon_days,
            seed=request.seed,
            paths=request.paths,
        )
        if request.overrides is None:
            return ForecastResponse(baseline=baseline, preview=None, changes=[])

        try:
            preview_workspace = apply_scenario_overrides(workspace, request.overrides)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        preview = evaluate_personal_forecast(
            preview_workspace,
            request.horizon_days,
            seed=request.seed,
            paths=request.paths,
        )
        return ForecastResponse(
            baseline=baseline,
            preview=preview,
            changes=describe_scenario_changes(workspace, request.overrides),
        )


@router.post("/finance/backtest", response_model=BacktestSummary)
def backtest_finance(
    request: BacktestRequest,
    identity: Annotated[AuthenticatedIdentity, Depends(require_identity)],
    repository: Annotated[FinanceRepository, Depends(get_finance_repository)],
) -> BacktestSummary:
    """Run a bounded, training-only rolling-origin accuracy check."""
    with forecast_capacity():
        workspace = _current_workspace(request.expected_revision, identity, repository)
        if request.policy is not None:
            workspace = workspace.model_copy(update={
                "inputs": workspace.inputs.model_copy(update={"policy": request.policy})
            })
        try:
            return backtest_personal_history(workspace, request.horizon_days)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
