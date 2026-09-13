"""Saved-workspace endpoint contracts: dates, cents, auth, and CAS failures."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
from typing import Iterator
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from ginseng.api import app, get_workspace_repository, require_identity
from ginseng.supabase import (
    AuthenticatedIdentity,
    SupabaseConfig,
    SupabaseConflictError,
    SupabaseGateway,
    SupabaseUnavailableError,
)
from ginseng.workspace import CashAccount, CashBill, CashWorkspace, CashWorkspaceRepository

_USER_ID = "00000000-0000-0000-0000-000000000001"
_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000010")
_BILL_ONE_ID = UUID("00000000-0000-0000-0000-000000000011")
_BILL_TWO_ID = UUID("00000000-0000-0000-0000-000000000012")
_BILL_OUTSIDE_ID = UUID("00000000-0000-0000-0000-000000000013")


class WorkspaceRepositoryStub:
    def __init__(self, workspace: CashWorkspace, save_error: Exception | None = None) -> None:
        self.workspace = workspace
        self.save_error = save_error
        self.save_calls = 0

    def get(self, _: str) -> CashWorkspace:
        return self.workspace

    def save(self, _: object, __: str) -> CashWorkspace:
        self.save_calls += 1
        if self.save_error is not None:
            raise self.save_error
        return self.workspace


@contextmanager
def authenticated_client(repository: WorkspaceRepositoryStub) -> Iterator[TestClient]:
    app.dependency_overrides[require_identity] = lambda: AuthenticatedIdentity(
        user_id=_USER_ID, access_token="test-token"
    )
    app.dependency_overrides[get_workspace_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(require_identity, None)
        app.dependency_overrides.pop(get_workspace_repository, None)


def cash_workspace() -> CashWorkspace:
    as_of = date(2026, 9, 12)
    return CashWorkspace(
        revision=4,
        as_of=as_of,
        currency="USD",
        accounts=[
            CashAccount(
                id=_ACCOUNT_ID,
                name="Checking",
                kind="checking",
                balance_cents=120,
            )
        ],
        bills=[
            CashBill(id=_BILL_ONE_ID, label="Today", amount_cents=20, due_date=as_of),
            CashBill(
                id=_BILL_TWO_ID,
                label="Horizon end",
                amount_cents=100,
                due_date=as_of + timedelta(days=13),
            ),
            CashBill(
                id=_BILL_OUTSIDE_ID,
                label="After horizon",
                amount_cents=99,
                due_date=as_of + timedelta(days=14),
            ),
        ],
    )




def test_save_maps_a_compare_and_swap_conflict_to_409() -> None:
    repository = WorkspaceRepositoryStub(
        cash_workspace(),
        save_error=SupabaseConflictError("Workspace changed. Reload before saving."),
    )
    with authenticated_client(repository) as client:
        response = client.put(
            "/workspace",
            json={
                "expected_revision": 4,
                "as_of": "2026-09-12",
                "accounts": [
                    {
                        "id": str(_ACCOUNT_ID),
                        "name": "Checking",
                        "kind": "checking",
                        "balance_cents": 120,
                    }
                ],
                "bills": [],
            },
        )

    assert response.status_code == 409


def test_protected_workspace_requires_a_bearer_token() -> None:
    with TestClient(app) as client:
        response = client.get("/workspace")

    assert response.status_code == 401

def test_repository_sanitizes_an_invalid_upstream_workspace_shape() -> None:
    class InvalidWorkspaceGateway:
        def rpc(self, *_: object) -> dict[str, object]:
            return {"revision": "upstream-private-payload"}

    repository = CashWorkspaceRepository(InvalidWorkspaceGateway())  # type: ignore[arg-type]
    with pytest.raises(SupabaseUnavailableError) as error:
        repository.get("caller-token")

    assert "upstream-private-payload" not in str(error.value)


def test_supabase_failure_never_surfaces_a_key_or_upstream_url() -> None:
    secret = "publishable-key-that-must-not-leak"
    request = httpx.Request("POST", "https://project.example/rest/v1/rpc/get_cash_workspace")
    response = httpx.Response(
        500,
        request=request,
        json={"message": f"https://project.example/?key={secret}"},
    )
    gateway = SupabaseGateway(
        config=SupabaseConfig(url="https://project.example", publishable_key=secret),
        client=httpx.Client(transport=httpx.MockTransport(lambda _: response)),
    )

    with pytest.raises(SupabaseUnavailableError) as error:
        gateway.rpc("get_cash_workspace", {}, "caller-token")

    assert secret not in str(error.value)
    assert "project.example" not in str(error.value)


def test_missing_migration_is_a_service_failure_not_invalid_user_data() -> None:
    gateway = SupabaseGateway(
        config=SupabaseConfig(url="https://project.example", publishable_key="public-key"),
        client=httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(404, request=request, json={"code": "PGRST202"})
        )),
    )
    with pytest.raises(SupabaseUnavailableError):
        gateway.rpc("get_cash_workspace", {}, "caller-token")
