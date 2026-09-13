"""Nessie provider invariants: key handling, normalization, and the
sample-workspace assembly — all against a stubbed HTTP layer, never the
live API. These pin the contract the onboarding sample review depends
on: every record is provider-tagged, the payload is always flagged
simulated, and the API key never leaks into responses or errors.
"""

from __future__ import annotations

from typing import Any

import pytest

from ginseng.api import AuthenticatedIdentity, app, require_identity
from ginseng.providers.nessie import NessieError, NessieProvider

from fastapi.testclient import TestClient

client = TestClient(app)

def _authenticated_get(path: str):
    app.dependency_overrides[require_identity] = lambda: AuthenticatedIdentity(
        user_id="00000000-0000-0000-0000-000000000001", access_token="test-token"
    )
    try:
        return client.get(path)
    finally:
        app.dependency_overrides.pop(require_identity, None)

CUSTOMER = {"_id": "cust-1", "first_name": "Ada", "last_name": "Lovelace", "account_ids": ["acc-1"]}
ACCOUNT = {
    "_id": "acc-1",
    "type": "Checking",
    "nickname": "Everyday",
    "balance": 1523,
    "account_number": "123456789",
    "customer_id": "cust-1",
}
CREDIT_ACCOUNT = {"_id": "acc-2", "type": "Credit Card", "nickname": "Card", "balance": 240}
DEPOSIT = {
    "_id": "dep-1",
    "medium": "balance",
    "transaction_date": "2026-09-01",
    "status": "completed",
    "amount": 180,
    "description": "Payment from client",
}
BILL = {
    "_id": "bill-1",
    "status": "upcoming",
    "payee": "Utilities Co",
    "nickname": None,
    "payment_date": "2026-09-20",
    "recurring_date": 20,
    "payment_amount": 95,
    "account_id": "acc-1",
}


@pytest.fixture()
def provider(monkeypatch: pytest.MonkeyPatch) -> NessieProvider:
    instance = NessieProvider(api_key="test-key")

    def fake_get(path: str, params: dict[str, Any] | None = None) -> Any:
        if path == "/enterprise/customers":
            return [CUSTOMER]
        if path == "/customers/cust-1/accounts":
            return [ACCOUNT, CREDIT_ACCOUNT]
        if path == "/accounts/acc-1/deposits":
            return [DEPOSIT]
        if path == "/accounts/acc-1/bills":
            return [BILL]
        raise AssertionError(f"unexpected path {path}")

    monkeypatch.setattr(instance, "_get", fake_get)
    return instance


class TestKeyHandling:
    def test_unconfigured_provider_reports_not_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NESSIE_API_KEY", raising=False)
        assert NessieProvider().configured is False

    def test_configured_provider_reports_configured(self) -> None:
        assert NessieProvider(api_key="k").configured is True

    def test_request_without_key_raises_before_any_http(self) -> None:
        with pytest.raises(NessieError, match="not configured"):
            NessieProvider()._get("/enterprise/customers")


class TestNormalization:
    def test_account_normalization_maps_type_kind_and_balance(self, provider: NessieProvider) -> None:
        record = provider.normalize_account(ACCOUNT)
        assert record == {
            "source": "nessie",
            "external_id": "acc-1",
            "kind": "checking",
            "name": "Everyday",
            "balance": 1523.0,
        }

    def test_credit_card_accounts_map_to_credit_kind(self, provider: NessieProvider) -> None:
        assert provider.normalize_account(CREDIT_ACCOUNT)["kind"] == "credit"

    def test_deposit_normalization_keeps_account_link(self, provider: NessieProvider) -> None:
        record = provider.normalize_deposit(DEPOSIT, "acc-1")
        assert record["account_external_id"] == "acc-1"
        assert record["amount"] == 180.0
        assert record["description"] == "Payment from client"

    def test_bill_normalization_marks_recurring_from_schedule(self, provider: NessieProvider) -> None:
        record = provider.normalize_bill(BILL, "acc-1")
        assert record["payee"] == "Utilities Co"
        assert record["recurring"] is True
        assert record["amount"] == 95.0

    def test_bill_without_recurring_date_is_not_recurring(self, provider: NessieProvider) -> None:
        one_off = dict(BILL, recurring_date=None)
        assert provider.normalize_bill(one_off, "acc-1")["recurring"] is False

    def test_non_numeric_amounts_fall_back_to_zero(self, provider: NessieProvider) -> None:
        assert provider.normalize_account({"_id": "x", "balance": "not-a-number"})["balance"] == 0.0


class TestSampleWorkspace:
    def test_payload_is_flagged_simulated_and_provider_tagged(self, provider: NessieProvider) -> None:
        payload = provider.sample_workspace(max_accounts=1, max_transactions_per_account=5)
        assert payload["label"] == "sample"
        assert payload["simulated"] is True
        assert payload["customer"]["first_name"] == "Ada"
        assert all(record["source"] == "nessie" for record in payload["accounts"])
        assert all(record["source"] == "nessie" for record in payload["transactions"])
        assert all(record["source"] == "nessie" for record in payload["bills"])

    def test_account_cap_limits_the_review_size(self, provider: NessieProvider) -> None:
        payload = provider.sample_workspace(max_accounts=1, max_transactions_per_account=5)
        assert len(payload["accounts"]) == 1
        assert all(
            record["account_external_id"] == "acc-1" for record in payload["transactions"]
        )

    def test_no_customer_with_accounts_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        instance = NessieProvider(api_key="test-key")
        monkeypatch.setattr(instance, "list_customers", lambda: [{"_id": "empty"}])
        monkeypatch.setattr(instance, "accounts_for_customer", lambda customer_id: [])
        with pytest.raises(NessieError, match="No Nessie customer"):
            instance.sample_workspace()

    def test_status_reports_configured_true_with_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NESSIE_API_KEY", "secret-value")
        response = _authenticated_get("/providers/nessie/status")
        assert response.status_code == 200
        assert response.json() == {"configured": True}
        assert "secret-value" not in response.text

    def test_sample_returns_503_when_key_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NESSIE_API_KEY", raising=False)
        response = _authenticated_get("/providers/nessie/sample")
        assert response.status_code == 503

    def test_sample_sanitizes_provider_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NESSIE_API_KEY", "k")

        import ginseng.api as api_module

        original = api_module.NessieProvider
        api_module.NessieProvider = lambda *args, **kwargs: _FailingProvider()
        try:
            response = _authenticated_get("/providers/nessie/sample")
        finally:
            api_module.NessieProvider = original
        assert response.status_code == 503
        assert response.json() == {"detail": "Nessie provider is unavailable."}


class _FailingProvider(NessieProvider):
    def __init__(self) -> None:
        super().__init__(api_key="k")

    def sample_workspace(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise NessieError("Nessie request failed: boom")


