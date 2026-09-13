"""Addition previews preserve saved records and cannot impersonate an existing ID."""

from datetime import date
from uuid import uuid4

import pytest

from ginseng.chat_actions import build_additions_proposal
from ginseng.workspace import CashAccount, CashWorkspace


def empty_workspace() -> CashWorkspace:
    return CashWorkspace(revision=0, as_of=date(2026, 9, 12), currency="USD", accounts=[], bills=[])


def arguments() -> dict:
    return {
        "accounts": [{"name": "Checking", "kind": "checking", "balance_cents": 200_000}],
        "bills": [],
        "horizon_days": 30,
    }


def test_known_bill_cash_need_includes_existing_negative_balance():
    workspace = empty_workspace()
    workspace.accounts = [CashAccount(id=uuid4(), name="Overdrawn", kind="checking", balance_cents=-5_000)]
    args = arguments()
    args["accounts"][0]["balance_cents"] = 1_000
    args["bills"] = [{"label": "Rent", "amount_cents": 90_000, "due_date": "2026-10-01"}]
    proposal = build_additions_proposal(args, workspace)
    assert proposal["projection"]["additional_cash_needed_cents"] == 94_000
    assert proposal["draft"]["accounts"][0] == workspace.accounts[0].model_dump(mode="json")


@pytest.mark.parametrize("change", [
    {"id": str(uuid4())},
    {"balance_cents": 2000.5},
    {"balance_cents": True},
    {"balance_cents": "200000"},
    {"kind": "credit"},
    {"owner_id": "another-user"},
])
def test_model_cannot_supply_ids_or_bypass_account_save_validation(change):
    args = arguments()
    args["accounts"][0].update(change)
    with pytest.raises(ValueError):
        build_additions_proposal(args, empty_workspace())


@pytest.mark.parametrize("already_saved", [False, True])
def test_identical_additions_are_rejected_within_request_and_against_saved_data(already_saved):
    args = arguments()
    workspace = empty_workspace()
    duplicate = {**args["accounts"][0], "name": "CHECKING"}
    if already_saved:
        workspace.accounts = [CashAccount(id=uuid4(), **duplicate)]
    else:
        args["accounts"].append(duplicate)
    with pytest.raises(ValueError, match="identical account"):
        build_additions_proposal(args, workspace)


def test_capacity_limit_includes_saved_accounts_not_just_additions():
    workspace = empty_workspace()
    workspace.accounts = [CashAccount(id=uuid4(), name=f"Cash {i}", kind="checking", balance_cents=100) for i in range(50)]
    with pytest.raises(ValueError):
        build_additions_proposal(arguments(), workspace)


def test_bill_only_addition_reports_unavailable_projection_without_fabricated_cash():
    args = {"accounts": [], "bills": [{"label": "Rent", "amount_cents": 90000, "due_date": "2026-10-01"}], "horizon_days": 30}
    proposal = build_additions_proposal(args, empty_workspace())
    assert proposal["projection"] is None
    assert proposal["projection_error"] is not None
    assert proposal["draft"]["bills"][0]["amount_cents"] == 90000
    args["bills"][0]["due_date"] = "2026-02-30"
    with pytest.raises(ValueError):
        build_additions_proposal(args, empty_workspace())
