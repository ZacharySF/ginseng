"""Saved cash-workspace contracts, RPC adapter, and deterministic schedule math."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ginseng.supabase import SupabaseGateway, SupabaseUnavailableError

MAX_WORKSPACE_REVISION = 9_007_199_254_740_991
MAX_EXPECTED_REVISION = MAX_WORKSPACE_REVISION - 1
MAX_ABS_BALANCE_CENTS = 100_000_000_000
MAX_BILL_CENTS = 100_000_000_000
MIN_WORKSPACE_DATE = date(1900, 1, 1)
MAX_WORKSPACE_DATE = date(2100, 12, 31)

StrictInt = Annotated[int, Field(strict=True)]
WorkspaceDate = Annotated[date, Field(ge=MIN_WORKSPACE_DATE, le=MAX_WORKSPACE_DATE)]


class CashAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: Annotated[str, Field(min_length=1, max_length=100)]
    kind: Literal["checking", "savings"]
    balance_cents: Annotated[StrictInt, Field(ge=-MAX_ABS_BALANCE_CENTS, le=MAX_ABS_BALANCE_CENTS)]

    @field_validator("name")
    @classmethod
    def name_is_trimmed(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("Account names cannot start or end with whitespace.")
        return value


class CashBill(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    label: Annotated[str, Field(min_length=1, max_length=100)]
    amount_cents: Annotated[StrictInt, Field(ge=1, le=MAX_BILL_CENTS)]
    due_date: WorkspaceDate

    @field_validator("label")
    @classmethod
    def label_is_trimmed(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("Bill labels cannot start or end with whitespace.")
        return value


class CashWorkspace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: Annotated[StrictInt, Field(ge=0, le=MAX_WORKSPACE_REVISION)]
    as_of: WorkspaceDate | None
    currency: Literal["USD"]
    accounts: list[CashAccount] = Field(max_length=50)
    bills: list[CashBill] = Field(max_length=200)


class SaveWorkspaceRequest(BaseModel):
    """Full replacement snapshot written through the owner-scoped RPC."""

    model_config = ConfigDict(extra="forbid")

    expected_revision: Annotated[StrictInt, Field(ge=0, le=MAX_EXPECTED_REVISION)]
    as_of: WorkspaceDate
    accounts: list[CashAccount] = Field(max_length=50)
    bills: list[CashBill] = Field(max_length=200)


class ProjectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    horizon_days: Literal[14, 30, 60]


class ScheduledProjectionDay(BaseModel):
    date: date
    bills_cents: StrictInt
    balance_cents: StrictInt


class ScheduledProjection(BaseModel):
    input_revision: Annotated[StrictInt, Field(ge=1, le=MAX_WORKSPACE_REVISION)]
    as_of: WorkspaceDate
    horizon_days: Literal[14, 30, 60]
    currency: Literal["USD"] = "USD"
    model_version: Literal["scheduled-cash-v1"] = "scheduled-cash-v1"
    opening_balance_cents: StrictInt
    scheduled_bills_cents: StrictInt
    ending_balance_cents: StrictInt
    lowest_balance_cents: StrictInt
    first_shortfall_date: date | None
    days: list[ScheduledProjectionDay]


class CashWorkspaceRepository:
    """Repository that forwards the authenticated caller's JWT to Supabase RPCs."""

    def __init__(self, gateway: SupabaseGateway | None = None) -> None:
        self._gateway = gateway or SupabaseGateway()

    def get(self, access_token: str) -> CashWorkspace:
        payload = self._gateway.rpc("get_cash_workspace", {}, access_token)
        try:
            return CashWorkspace.model_validate(payload)
        except ValidationError as error:
            raise SupabaseUnavailableError("Workspace service returned an invalid response.") from error

    def save(self, request: SaveWorkspaceRequest, access_token: str) -> CashWorkspace:
        payload = self._gateway.rpc(
            "save_cash_workspace",
            {
                "p_expected_revision": request.expected_revision,
                "p_as_of": request.as_of.isoformat(),
                "p_accounts": [account.model_dump(mode="json") for account in request.accounts],
                "p_bills": [bill.model_dump(mode="json") for bill in request.bills],
            },
            access_token,
        )
        try:
            return CashWorkspace.model_validate(payload)
        except ValidationError as error:
            raise SupabaseUnavailableError("Workspace service returned an invalid response.") from error


def project_saved_workspace(workspace: CashWorkspace, horizon_days: Literal[14, 30, 60]) -> ScheduledProjection:
    """Project one-time saved bills from the snapshot's opening-of-day balance."""

    if workspace.as_of is None or not workspace.accounts:
        raise ValueError("Save an opening balance and at least one cash account before projecting.")

    as_of = workspace.as_of
    overdue = [bill for bill in workspace.bills if bill.due_date < as_of]
    if overdue:
        raise ValueError("Resolve bills dated before the opening balance date before projecting.")

    opening_balance = sum(account.balance_cents for account in workspace.accounts)
    last_day = as_of + timedelta(days=horizon_days - 1)
    bills_by_date: dict[date, int] = {}
    for bill in workspace.bills:
        if as_of <= bill.due_date <= last_day:
            bills_by_date[bill.due_date] = bills_by_date.get(bill.due_date, 0) + bill.amount_cents

    balance = opening_balance
    lowest_balance = opening_balance
    first_shortfall = as_of if opening_balance < 0 else None
    days: list[ScheduledProjectionDay] = []
    for offset in range(horizon_days):
        current_date = as_of + timedelta(days=offset)
        bills_cents = bills_by_date.get(current_date, 0)
        balance -= bills_cents
        if balance < lowest_balance:
            lowest_balance = balance
        if first_shortfall is None and balance < 0:
            first_shortfall = current_date
        days.append(
            ScheduledProjectionDay(
                date=current_date,
                bills_cents=bills_cents,
                balance_cents=balance,
            )
        )

    return ScheduledProjection(
        input_revision=workspace.revision,
        as_of=as_of,
        horizon_days=horizon_days,
        opening_balance_cents=opening_balance,
        scheduled_bills_cents=sum(bills_by_date.values()),
        ending_balance_cents=balance,
        lowest_balance_cents=lowest_balance,
        first_shortfall_date=first_shortfall,
        days=days,
    )
