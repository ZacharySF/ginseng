from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from ginseng.finance_models import HistoricalTransaction
from ginseng.information_snapshot import InformationSnapshot, information_at
from ginseng.personal_forecast import backtest_personal_history
from ginseng.workspace import CashBill

from tests.test_personal_forecast import historical_workspace


def test_late_arrival_correction_and_new_obligation_cannot_rewrite_frozen_information():
    earlier = historical_workspace(140)
    t = datetime(2025, 6, 1, tzinfo=UTC)
    frozen = InformationSnapshot.capture(earlier, t)
    later = earlier.model_copy(deep=True)
    later.revision += 1
    later.inputs.transactions.append(
        HistoricalTransaction(
            id=UUID(int=987654),
            date=earlier.as_of - timedelta(days=7),
            description="Late synthetic transaction",
            amount_cents=-12345,
            category="expense_essential_variable",
            source_key=None,
        )
    )
    later.inputs.transactions[0].amount_cents += 10000
    later.bills.append(
        CashBill(
            id=UUID(int=123123),
            label="Created after cutoff",
            amount_cents=20000,
            due_date=earlier.as_of + timedelta(days=4),
        )
    )
    newest = InformationSnapshot.capture(later, t + timedelta(days=1))
    restored = information_at([frozen, newest], t)
    assert restored == earlier
    assert len(restored.inputs.transactions) + 1 == len(later.inputs.transactions)
    assert (
        restored.inputs.transactions[0].amount_cents
        != later.inputs.transactions[0].amount_cents
    )
    assert not restored.bills
    # Returning a mutable validated workspace never makes the stored bytes mutable.
    restored.inputs.transactions.clear()
    assert frozen.workspace() == earlier
    assert information_at([frozen, newest], t + timedelta(days=2)) == later
    with pytest.raises(ValueError, match="retrospective"):
        information_at([newest], t)
    with pytest.raises(ValueError, match="timezone"):
        InformationSnapshot.capture(earlier, t.replace(tzinfo=None))


def test_legacy_backtest_explicitly_retrospective_even_with_effective_date_cutoffs():
    r = backtest_personal_history(historical_workspace(140), 14, paths=16)
    assert r.information_timing == "retrospective_current_records"
    assert r.calibration["information_timing"] == "retrospective_current_records"
    assert "retrospective" in r.calibration["source"].lower()
