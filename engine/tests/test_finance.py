"""Finance API contracts: canonical export, authentication, CAS, and schema guards."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from typing import Iterator
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ginseng.dependencies import require_identity
from ginseng.finance_api import get_finance_repository, router
from ginseng.finance_models import (
    FinanceInputs,
    FinanceWorkspace,
    NamedScenario,
    PlanningPolicy,
    SaveFinanceRequest,
    ScenarioOverrides,
    default_finance_inputs,
)
from ginseng.supabase import AuthenticatedIdentity, SupabaseConflictError
from ginseng.workspace import CashAccount, CashBill

_USER_ID = "00000000-0000-0000-0000-000000000001"
_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000010")
_BILL_ID = UUID("00000000-0000-0000-0000-000000000011")
_TRANSACTION_ID = "00000000-0000-0000-0000-000000000012"


class FinanceRepositoryStub:
    def __init__(self, workspace: FinanceWorkspace, save_error: Exception | None = None) -> None:
        self.workspace = workspace
        self.save_error = save_error
        self.save_calls = 0

    def get(self, _: str) -> FinanceWorkspace:
        return self.workspace

    def save(self, _: SaveFinanceRequest, __: str) -> FinanceWorkspace:
        self.save_calls += 1
        if self.save_error is not None:
            raise self.save_error
        return self.workspace


@contextmanager
def authenticated_client(repository: FinanceRepositoryStub) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_identity] = lambda: AuthenticatedIdentity(
        user_id=_USER_ID,
        access_token="test-token",
    )
    app.dependency_overrides[get_finance_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def finance_workspace() -> FinanceWorkspace:
    return FinanceWorkspace(
        revision=3,
        as_of=date(2026, 9, 12),
        currency="USD",
        accounts=[
            CashAccount(
                id=_ACCOUNT_ID,
                name="Checking",
                kind="checking",
                balance_cents=5_000,
            )
        ],
        bills=[CashBill(id=_BILL_ID, label="Rent", amount_cents=1_000, due_date=date(2026, 10, 1))],
        inputs=default_finance_inputs(),
    )


def finance_draft_payload(workspace: FinanceWorkspace) -> dict[str, object]:
    return {
        "expected_revision": workspace.revision,
        "as_of": workspace.as_of.isoformat() if workspace.as_of is not None else None,
        "accounts": [account.model_dump(mode="json") for account in workspace.accounts],
        "bills": [bill.model_dump(mode="json") for bill in workspace.bills],
        "inputs": workspace.inputs.model_dump(mode="json"),
    }


def test_scenario_names_use_locale_independent_ascii_case_matching() -> None:
    names = ["Straße", "STRASSE", "ΟΣ", "ος"]
    scenarios = [
        NamedScenario(
            id=UUID(int=index + 1),
            name=name,
            base_revision=0,
            overrides=ScenarioOverrides(mode="scheduled"),
        )
        for index, name in enumerate(names)
    ]
    inputs = FinanceInputs(scenarios=scenarios)
    assert [scenario.name for scenario in inputs.scenarios] == names

    scenarios[0] = scenarios[0].model_copy(update={"name": "Plan"})
    scenarios[1] = scenarios[1].model_copy(update={"name": "plan"})
    with pytest.raises(ValidationError):
        FinanceInputs(scenarios=scenarios)


def test_export_omits_absent_named_scenario_overrides_without_dropping_nested_nulls() -> None:
    baseline = finance_workspace()
    workspace = FinanceWorkspace(
        revision=baseline.revision,
        as_of=baseline.as_of,
        currency=baseline.currency,
        accounts=baseline.accounts,
        bills=baseline.bills,
        inputs=FinanceInputs(
            scenarios=[
                NamedScenario(
                    id=UUID("00000000-0000-0000-0000-000000000013"),
                    name="Scheduled comparison",
                    base_revision=baseline.revision,
                    overrides=ScenarioOverrides(mode="scheduled", policy=PlanningPolicy()),
                )
            ]
        ),
    )

    with authenticated_client(FinanceRepositoryStub(workspace)) as client:
        response = client.get("/finance")

    assert response.status_code == 200
    overrides = response.json()["inputs"]["scenarios"][0]["overrides"]
    assert set(overrides) == {"mode", "policy"}
    assert overrides["policy"]["buffer_tolerance_dollar_days"] is None


def test_finance_routes_require_a_bearer_token() -> None:
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.get("/finance")

    assert response.status_code == 401


def test_invalid_financial_schema_is_rejected_before_any_save() -> None:
    workspace = finance_workspace()
    repository = FinanceRepositoryStub(workspace)
    payload = finance_draft_payload(workspace)
    inputs = payload["inputs"]
    assert isinstance(inputs, dict)
    inputs["transactions"] = [
        {
            "id": _TRANSACTION_ID,
            "date": "2026-09-11",
            "description": "Invalid expense direction",
            "amount_cents": 1,
            "category": "expense_fixed",
            "source_key": None,
        }
    ]

    with authenticated_client(repository) as client:
        response = client.put("/finance", json=payload)

    assert response.status_code == 422
    assert repository.save_calls == 0


def test_finance_save_maps_shared_cash_cas_conflicts_to_409() -> None:
    workspace = finance_workspace()
    repository = FinanceRepositoryStub(
        workspace,
        save_error=SupabaseConflictError("Workspace changed. Reload before saving."),
    )

    with authenticated_client(repository) as client:
        response = client.put("/finance", json=finance_draft_payload(workspace))

    assert response.status_code == 409
    assert repository.save_calls == 1
