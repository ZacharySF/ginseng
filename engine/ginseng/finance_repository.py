"""Authenticated RPC adapter for canonical personal-finance snapshots."""

from __future__ import annotations

from pydantic import ValidationError

from ginseng.finance_models import FinanceWorkspace, SaveFinanceRequest
from ginseng.supabase import SupabaseGateway, SupabaseUnavailableError


class FinanceRepository:
    """Forward only the caller JWT to the owner-scoped finance RPCs."""

    def __init__(self, gateway: SupabaseGateway | None = None) -> None:
        self._gateway = gateway or SupabaseGateway()

    def get(self, access_token: str) -> FinanceWorkspace:
        payload = self._gateway.rpc("get_finance_workspace", {}, access_token)
        return self._parse_workspace(payload)

    def save(self, request: SaveFinanceRequest, access_token: str) -> FinanceWorkspace:
        payload = self._gateway.rpc(
            "save_finance_workspace",
            {
                "p_expected_revision": request.expected_revision,
                "p_as_of": request.as_of.isoformat(),
                "p_accounts": [account.model_dump(mode="json") for account in request.accounts],
                "p_bills": [bill.model_dump(mode="json") for bill in request.bills],
                "p_inputs": request.inputs.model_dump(mode="json"),
            },
            access_token,
        )
        return self._parse_workspace(payload)

    @staticmethod
    def _parse_workspace(payload: dict[str, object]) -> FinanceWorkspace:
        try:
            return FinanceWorkspace.model_validate(payload)
        except ValidationError as error:
            raise SupabaseUnavailableError("Workspace service returned an invalid response.") from error
