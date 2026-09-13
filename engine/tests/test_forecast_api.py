"""Read-only canonical personal forecast endpoint contracts."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from typing import Iterator
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ginseng.dependencies import require_identity
from ginseng.finance_api import get_finance_repository
from ginseng.finance_models import FinanceInputs, FinanceWorkspace
from ginseng.forecast_api import router
from ginseng.supabase import AuthenticatedIdentity
from ginseng.workspace import CashAccount, CashBill

_USER_ID = "00000000-0000-0000-0000-000000000201"
_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000202")
_BILL_ID = UUID("00000000-0000-0000-0000-000000000203")


class ForecastRepositoryStub:
    def __init__(self, workspace: FinanceWorkspace) -> None:
        self.workspace = workspace
        self.get_calls = 0
        self.save_calls = 0

    def get(self, _: str) -> FinanceWorkspace:
        self.get_calls += 1
        return self.workspace

    def save(self, *_: object) -> FinanceWorkspace:
        self.save_calls += 1
        return self.workspace


@contextmanager
def forecast_client(repository: ForecastRepositoryStub) -> Iterator[TestClient]:
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


def workspace() -> FinanceWorkspace:
    return FinanceWorkspace(
        revision=4,
        as_of=date(2026, 9, 12),
        currency="USD",
        accounts=[CashAccount(id=_ACCOUNT_ID, name="Checking", kind="checking", balance_cents=500_000)],
        bills=[CashBill(id=_BILL_ID, label="Rent", amount_cents=100_000, due_date=date(2026, 10, 1))],
        inputs=FinanceInputs(mode="scheduled"),
    )


def test_forecast_rejects_a_stale_revision_before_evaluating_or_saving() -> None:
    repository = ForecastRepositoryStub(workspace())

    with forecast_client(repository) as client:
        response = client.post(
            "/finance/forecast",
            json={"expected_revision": 3, "horizon_days": 14, "paths": 1},
        )

    assert response.status_code == 409
    assert repository.save_calls == 0


def test_recurring_forecast_preview_changes_cash_without_saving() -> None:
    saved = workspace()
    repository = ForecastRepositoryStub(saved)
    preview_bill = CashBill(
        id=_BILL_ID,
        label="Rent",
        amount_cents=125_000,
        due_date=date(2026, 10, 1),
    )

    with forecast_client(repository) as client:
        response = client.post(
            "/finance/forecast",
            json={
                "expected_revision": saved.revision,
                "horizon_days": 60,
                "paths": 1,
                "overrides": {
                    "bills": [preview_bill.model_dump(mode="json")],
                    "event_rules": [{"event_id": str(_BILL_ID), "recurrence": "monthly", "end_date": None}],
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["baseline"]["result"]["cash_paths"]["p50"][-1] == 4_000
    assert payload["preview"]["result"]["cash_paths"]["p50"][-1] == 2_500
    assert saved.bills[0].amount_cents == 100_000
    assert saved.inputs.event_rules == []
    assert repository.save_calls == 0


def test_backtest_reports_missing_history_as_an_actionable_client_error() -> None:
    repository = ForecastRepositoryStub(workspace())

    with forecast_client(repository) as client:
        response = client.post(
            "/finance/backtest",
            json={"expected_revision": 4, "horizon_days": 14},
        )

    assert response.status_code == 422
    assert "Complete classified history" in response.json()["detail"]
