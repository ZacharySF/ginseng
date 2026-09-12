"""Read-only Nessie adapter.

Nessie (https://prod.nessieisreal.com/) is a banking *simulation* API
sponsored for hackathons. It can never connect a real person's bank, so
in Ginseng it serves exactly one purpose: a clearly-labeled sample
workspace. This adapter only reads (customers, accounts, deposits,
bills); it performs no writes against Nessie ever.

Auth note: Nessie authenticates with the API key as a ``key`` query
parameter, not a header (getting-started docs). The key lives in the
``NESSIE_API_KEY`` environment variable on the engine process and is
never included in any response this module produces.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

# HTTPS only: the plain-HTTP host refuses connections.
NESSIE_BASE_URL = "https://api.nessieisreal.com"


class NessieError(RuntimeError):
    """A Nessie request failed after retries or returned bad data."""


class NessieProvider:
    """Thin read-only client with Ginseng-shaped normalization."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = NESSIE_BASE_URL,
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("NESSIE_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    # --- raw requests -------------------------------------------------

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self.api_key:
            raise NessieError("NESSIE_API_KEY is not configured on the engine.")
        query = dict(params or {})
        query["key"] = self.api_key
        try:
            response = httpx.get(f"{self.base_url}{path}", params=query, timeout=self.timeout)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise NessieError(f"Nessie request failed: {error}") from error
        try:
            return response.json()
        except ValueError as error:
            raise NessieError("Nessie returned a non-JSON body.") from error

    def list_customers(self) -> list[dict[str, Any]]:
        data = self._get("/enterprise/customers")
        return data if isinstance(data, list) else []

    def accounts_for_customer(self, customer_id: str) -> list[dict[str, Any]]:
        data = self._get(f"/customers/{customer_id}/accounts")
        return data if isinstance(data, list) else []

    def deposits_for_account(self, account_id: str) -> list[dict[str, Any]]:
        data = self._get(f"/accounts/{account_id}/deposits")
        return data if isinstance(data, list) else []

    def bills_for_account(self, account_id: str) -> list[dict[str, Any]]:
        data = self._get(f"/accounts/{account_id}/bills")
        return data if isinstance(data, list) else []

    # --- normalization ------------------------------------------------
    # Provider-neutral shapes consumed by the frontend sample review;
    # field names intentionally match the onboarding UI types.

    @staticmethod
    def _kind(account_type: Any) -> str:
        normalized = str(account_type or "").strip().lower()
        if normalized == "credit card":
            return "credit"
        return normalized if normalized in ("checking", "savings") else "checking"

    @staticmethod
    def _amount(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def normalize_account(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "source": "nessie",
            "external_id": str(raw.get("_id", "")),
            "kind": self._kind(raw.get("type")),
            "name": str(raw.get("nickname") or "Untitled account"),
            "balance": self._amount(raw.get("balance")),
        }

    def normalize_deposit(self, raw: dict[str, Any], account_id: str) -> dict[str, Any]:
        return {
            "source": "nessie",
            "external_id": str(raw.get("_id", "")),
            "account_external_id": account_id,
            "date": str(raw.get("transaction_date", "")),
            "amount": self._amount(raw.get("amount")),
            "description": raw.get("description"),
        }

    def normalize_bill(self, raw: dict[str, Any], account_id: str) -> dict[str, Any]:
        return {
            "source": "nessie",
            "external_id": str(raw.get("_id", "")),
            "account_external_id": account_id,
            "payee": str(raw.get("payee") or raw.get("nickname") or "Unknown payee"),
            "amount": self._amount(raw.get("payment_amount")),
            "payment_date": str(raw.get("payment_date", "")),
            "recurring": bool(raw.get("recurring_date")),
        }

    # --- sample workspace ---------------------------------------------

    def _activity(
        self, accounts: list[dict[str, Any]], max_transactions_per_account: int
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        transactions: list[dict[str, Any]] = []
        bills: list[dict[str, Any]] = []
        for raw_account in accounts:
            account_id = str(raw_account.get("_id", ""))
            deposits = self.deposits_for_account(account_id)[: max(0, max_transactions_per_account)]
            transactions.extend(self.normalize_deposit(deposit, account_id) for deposit in deposits)
            bills.extend(
                self.normalize_bill(bill, account_id)
                for bill in self.bills_for_account(account_id)
            )
        transactions.sort(key=lambda item: item["date"], reverse=True)
        bills.sort(key=lambda item: item["payment_date"])
        return transactions, bills

    def _payload(
        self,
        customer: dict[str, Any],
        accounts: list[dict[str, Any]],
        transactions: list[dict[str, Any]],
        bills: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "label": "sample",
            "simulated": True,
            "customer": {
                "external_id": str(customer.get("_id", "")),
                "first_name": customer.get("first_name"),
                "last_name": customer.get("last_name"),
            },
            "accounts": [self.normalize_account(raw_account) for raw_account in accounts],
            "transactions": transactions,
            "bills": bills,
        }

    def sample_workspace(
        self,
        max_accounts: int = 3,
        max_transactions_per_account: int = 10,
        customer_attempts: int = 12,
    ) -> dict[str, Any]:
        """Build a compact review payload. Most Nessie mock customers
        have accounts but no deposits or bills, which makes for a
        pointless preview, so candidates are scanned for one with real
        activity and the first account-holder is only the fallback.
        Every record carries ``source: nessie`` and the response is
        flagged ``simulated: True`` so no consumer can mistake it for
        the user's real finances."""
        fallback: tuple[dict[str, Any], list[dict[str, Any]]] | None = None

        for candidate in self.list_customers()[: max(1, customer_attempts)]:
            accounts = self.accounts_for_customer(str(candidate.get("_id", "")))
            if not accounts:
                continue
            selected = accounts[: max(1, max_accounts)]
            if fallback is None:
                fallback = (candidate, selected)
            transactions, bills = self._activity(selected, max_transactions_per_account)
            if transactions or bills:
                return self._payload(candidate, selected, transactions, bills)

        if fallback is None:
            raise NessieError("No Nessie customer with accounts was found.")

        customer, selected = fallback
        transactions, bills = self._activity(selected, max_transactions_per_account)
        return self._payload(customer, selected, transactions, bills)
