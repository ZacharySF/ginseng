"""Bearer-authenticated HTTP surface for canonical finance snapshots."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ginseng.dependencies import get_supabase_gateway, require_identity, supabase_http_error
from ginseng.finance_models import FinanceWorkspace, SaveFinanceRequest
from ginseng.finance_repository import FinanceRepository
from ginseng.supabase import AuthenticatedIdentity, SupabaseError

router = APIRouter(tags=["finance"])


def get_finance_repository() -> FinanceRepository:
    """Build a repository that preserves the caller JWT through each RPC."""

    return FinanceRepository(get_supabase_gateway())


@router.get("/finance", response_model=FinanceWorkspace)
def get_finance_workspace(
    identity: Annotated[AuthenticatedIdentity, Depends(require_identity)],
    repository: Annotated[FinanceRepository, Depends(get_finance_repository)],
) -> FinanceWorkspace:
    try:
        return repository.get(identity.access_token)
    except SupabaseError as error:
        raise supabase_http_error(error) from error


@router.put("/finance", response_model=FinanceWorkspace)
def save_finance_workspace(
    request: SaveFinanceRequest,
    identity: Annotated[AuthenticatedIdentity, Depends(require_identity)],
    repository: Annotated[FinanceRepository, Depends(get_finance_repository)],
) -> FinanceWorkspace:
    try:
        return repository.save(request, identity.access_token)
    except SupabaseError as error:
        raise supabase_http_error(error) from error


__all__ = [
    "FinanceWorkspace",
    "get_finance_repository",
    "router",
]
